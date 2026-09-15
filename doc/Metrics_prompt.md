# Metrics Prompt

Use this prompt when adding metrics to an app that is **already instrumented for tracing** via [Instrumentation_prompt.md](./Instrumentation_prompt.md). Metrics layer on top of an existing OTEL bootstrap — they do not replace it.

Write the code. Do not stop at recommendations.

Keep the implementation lean, debuggable, and environment-driven.

## Goal

Emit metrics through the same OTEL pipeline as traces so they land in **Google Managed Prometheus (GMP)** and surface in **Google Cloud Monitoring** dashboards and alerts.

Current backend assumptions:

- metrics -> Google Managed Prometheus (GMP) via the shared in-cluster OTEL collector
- traces -> Google Cloud Trace (already wired per Instrumentation_prompt.md)
- logs -> Google Cloud Logging (already wired)
- no app should export metrics directly to a vendor backend

## Core Rules

1. Require tracing to already be in place (Instrumentation_prompt.md applied first). Metrics share the OTLP endpoint, propagation, and resource attributes from that bootstrap.
2. Use one meter per app, named after the app/service.
3. Cover every user-facing request path with the **RED method**: Rate (requests counter), Errors (failures counter), Duration (latency histogram).
4. Also emit the standard semantic-convention HTTP metric `http.server.request.duration` so Google Cloud's Application Monitoring auto-recognizes it.
5. Record metrics from **every exit path** — success and every error branch. A helper function called from each path is the only reliable way.
6. Bound attribute cardinality. Only use attributes whose value set is small and finite.
7. Use environment variables / Helm values for OTLP configuration. Reuse the same endpoint as traces.
8. Do not hardcode collector endpoints, project IDs, or instrument names that should be derived from the service identity.

## Default Strategy

For each user-facing request path (HTTP route, queue handler, scheduled job), emit four instruments:

- **Custom request counter**: `<service>.<operation>.requests` — counts every invocation. Attributes: `outcome` (`success`/`error`), plus 0-2 low-cardinality operational dimensions.
- **Custom duration histogram**: `<service>.<operation>.duration`, unit `ms`. Same attributes as the counter. Captures the latency distribution.
- **Custom failure counter**: `<service>.<operation>.failures` — counts only error exits. Attributes: the operational dimensions only (no `outcome`, since the instrument's identity already encodes it).
- **Standard HTTP semantic metric**: `http.server.request.duration`, unit `s`. Standard attributes only: `http.request.method`, `http.route`, `http.response.status_code`. Required for Google Cloud Application Monitoring's auto-built dashboards.

Do not also emit gauges for "current latency" or "current error count" — both are derived from the histogram and counter at query time.

## Infra Assumptions

Metrics ride the same OTLP pipeline as traces.

Typical in-cluster endpoints (inherited from the trace bootstrap):

- OTLP HTTP: `http://otel-agent.observability.svc.cluster.local:4318`
- OTLP gRPC: `otel-agent.observability.svc.cluster.local:4317`

The collector translates OTLP metrics → Prometheus and forwards to GMP. Apps do not need a Prometheus client library and do not need to expose `/metrics` for scraping. **OTLP push, not Prometheus pull.**

Expected config style (env vars):

- shared: `OTEL_EXPORTER_OTLP_ENDPOINT` (base — both traces and metrics derive from it)
- shared: `OTEL_EXPORTER_OTLP_PROTOCOL` (e.g. `http/protobuf`)
- metrics-specific override: `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`
- gate: `OTEL_METRICS_EXPORTER` — set to `otlp` to enable, `none` to disable. Default off so the bootstrap stays opt-in.

If env vars are already present, preserve them.

## What To Instrument

Always instrument with RED + standard HTTP:

- inbound HTTP routes that do real work (one set of RED instruments per logical operation, not per route — group e.g. `/api/generate?demo=slow` and `/api/generate?demo=error` under one `<service>.generate.*` instrument family with `demo.mode` as an attribute)
- queue consumers (operation = the message type or handler name)
- background jobs (operation = job name)
- LLM/AI generation paths (these are slow and failure-prone — the histogram is where you'll see latency regressions)

Also useful, but only when the value of the data justifies the cardinality cost:

- DB query duration, sliced by `db.operation.name` (only if you have a small finite set of named queries; do not slice by raw SQL)
- External API call duration, sliced by `peer.service`

**Do not instrument:**

- Health check endpoints
- Static asset serves
- Helper functions inside a request — let the parent request's metrics speak for them
- Per-user, per-session, per-request-id slicing — that's what traces are for

## Cardinality Discipline

Every attribute multiplies the number of time series stored. **Only use attributes with a small, bounded, predictable value set.**

Safe attributes:

- `outcome` — 2 values (`success`/`error`)
- `http.request.method` — handful of values
- `http.route` — bounded by your route table
- `http.response.status_code` — bounded
- operational mode flags (`demo.mode`, `cache.hit`, `auth.source`) — small enumeration

Dangerous attributes (never use):

- `user.id`, `session.id`, `request.id`, `tenant.id` — unbounded
- raw URL or query string — unbounded
- error message text — unbounded
- timestamps, durations as attributes — these are the measurement, not the dimension
- raw SQL, raw prompt text — unbounded and may leak PII

When you need a per-user or per-request signal, that's a trace or a log, not a metric. Metrics tell you "are 5xx errors spiking"; traces tell you "which specific request failed."

## Implementation Pattern

1. Confirm tracing is already wired (instrumentation.mjs exists, sets up NodeSDK, exports to OTLP). If not, run Instrumentation_prompt.md first.
2. Add the metrics SDK dependencies (`@opentelemetry/sdk-metrics`, `@opentelemetry/exporter-metrics-otlp-proto` for Node.js, or the language equivalent).
3. Extend the existing bootstrap (instrumentation.mjs) to register a `PeriodicExportingMetricReader` wrapping an `OTLPMetricExporter`. Gate it on `OTEL_METRICS_EXPORTER !== 'none'` so the bootstrap stays opt-in.
4. In the application code, create the meter and instruments once at module top level (not per request).
5. Write one `record<operation>Metrics(outcome, ...attrs, startedAt, statusCode)` helper per operation. Call it from every success path and every error path.
6. Add Helm env vars to enable metrics export, mirroring how traces are configured.

### Bootstrap pattern (Node.js, extending the existing instrumentation.mjs)

```js
import { OTLPMetricExporter } from '@opentelemetry/exporter-metrics-otlp-proto';
import { PeriodicExportingMetricReader } from '@opentelemetry/sdk-metrics';

function resolveMetricsUrl() {
  if (process.env.OTEL_EXPORTER_OTLP_METRICS_ENDPOINT) {
    return process.env.OTEL_EXPORTER_OTLP_METRICS_ENDPOINT;
  }
  const baseEndpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT;
  if (!baseEndpoint) return undefined;
  return `${baseEndpoint.replace(/\/$/, '')}/v1/metrics`;
}

const metricsEnabled = (process.env.OTEL_METRICS_EXPORTER || 'none') !== 'none';
const metricReader = metricsEnabled
  ? new PeriodicExportingMetricReader({
      exporter: new OTLPMetricExporter({ url: resolveMetricsUrl() }),
    })
  : undefined;

const sdk = new NodeSDK({
  traceExporter,                              // already there from Instrumentation_prompt.md
  metricReaders: metricReader ? [metricReader] : [],
});
```

### Application pattern (Node.js example)

```js
import { metrics } from '@opentelemetry/api';

const meter = metrics.getMeter('<service>-manual');

const generateRequests = meter.createCounter('<service>.generate.requests', {
  description: 'Number of generate requests.',
});
const generateDuration = meter.createHistogram('<service>.generate.duration', {
  description: 'Duration of generate requests.',
  unit: 'ms',
});
const generateFailures = meter.createCounter('<service>.generate.failures', {
  description: 'Number of failed generate requests.',
});
// Eager zero-increment so the series registers with GMP at startup, even if no
// failure has occurred yet. Without this, Cloud Monitoring alert policies that
// reference the metric name fail to create with "PromQL metric(s) are invalid".
// Same rule for any "on-error-only" counter (e.g. a dead-letter counter).
generateFailures.add(0);

const httpServerRequestDuration = meter.createHistogram('http.server.request.duration', {
  description: 'Standard HTTP server duration for Cloud Application Monitoring.',
  unit: 's',
});

function recordGenerateMetrics(outcome, demoMode, startedAt, statusCode) {
  const durationMs = Date.now() - startedAt;
  const attributes = { outcome, 'demo.mode': demoMode };

  generateRequests.add(1, attributes);
  generateDuration.record(durationMs, attributes);
  if (outcome === 'error') {
    generateFailures.add(1, { 'demo.mode': demoMode });
  }
  httpServerRequestDuration.record(durationMs / 1000, {
    'http.request.method': 'POST',
    'http.route': '/api/generate',
    'http.response.status_code': statusCode,
  });
}

app.post('/api/generate', async (req, res) => {
  const startedAt = Date.now();
  try {
    // ... real work ...
    recordGenerateMetrics('success', demoMode, startedAt, 200);
    res.json({ ok: true });
  } catch (error) {
    recordGenerateMetrics('error', demoMode, startedAt, 500);
    res.status(500).json({ error: error.message });
  }
});
```

The helper is called from **both** the success branch and the error branch. Every code path that produces a response must call it exactly once.

### tRPC applications — use middleware, not per-procedure wrapping

For apps built on tRPC (Next.js + `@trpc/server`), the per-route pattern above does NOT scale — every tRPC call comes in through the single `/api/trpc/[trpc]` HTTP route, so `HttpInstrumentation` sees the whole batched envelope as one call and can't distinguish procedures. Wrapping each of N procedures by hand is unmaintainable (someone always forgets, and new procedures land uninstrumented).

Instead, attach a tRPC middleware to the root procedure. Every procedure inherits it automatically. Reference implementations: `~/VSC/athena-ui/src/server/api/{metrics,trpc}.ts` and `~/VSC/csr-qbr-slide-generator/src/server/api/{metrics,trpc}.ts` — identical shape.

`src/server/api/metrics.ts`:

```typescript
import { metrics } from '@opentelemetry/api';

const meter = metrics.getMeter('<service>');

const trpcRequestDuration = meter.createHistogram('<service>.trpc.request.duration', {
  description: 'Duration of tRPC procedure calls.',
  unit: 's',
});
const trpcInflight = meter.createUpDownCounter('<service>.trpc.inflight', {
  description: 'In-flight tRPC procedure calls.',
});

type TrpcMiddlewareArgs<R extends { ok: boolean }> = {
  path: string;
  type: 'query' | 'mutation' | 'subscription';
  next: () => Promise<R>;
};

export async function recordTrpcMetrics<R extends { ok: boolean }>({
  path, type, next,
}: TrpcMiddlewareArgs<R>): Promise<R> {
  const inflightAttrs = { procedure: path } as const;
  trpcInflight.add(1, inflightAttrs);
  const startedAt = process.hrtime.bigint();
  let outcome: 'success' | 'error' = 'success';
  try {
    const result = await next();
    if (!result.ok) outcome = 'error';   // tRPC's { ok: false } — validation, NOT_FOUND, FORBIDDEN, etc.
    return result;
  } catch (error) {
    outcome = 'error';                    // thrown exceptions — 500-class
    throw error;
  } finally {
    const durationSeconds = Number(process.hrtime.bigint() - startedAt) / 1e9;
    trpcRequestDuration.record(durationSeconds, { procedure: path, type, outcome });
    trpcInflight.add(-1, inflightAttrs);
  }
}
```

`src/server/api/trpc.ts` — apply the middleware to every exported procedure builder:

```typescript
import { recordTrpcMetrics } from '@/server/api/metrics';

const metricsMiddleware = t.middleware(({ path, type, next }) =>
  recordTrpcMetrics({ path, type, next }),
);

// Apply to EVERY procedure builder the app exports. Middleware chains
// left-to-right, so put metrics FIRST — it must observe every call, including
// ones that fail in later middleware (e.g. auth).
export const publicProcedure = t.procedure.use(metricsMiddleware);
export const protectedProcedure = t.procedure.use(metricsMiddleware).use(enforceUser);
```

Notes:

- **Both `{ok: false}` results and thrown exceptions are `outcome=error`.** tRPC swallows unhandled errors into `{ok: false}` shapes; a bare exception check would miss most user-facing errors. The pattern above catches both.
- **Do NOT put the heartbeat counter in this file** if the app's bootstrap (`instrumentation.node.ts`) already emits a `<service>.heartbeat` — you'll double-count. csr-qbr keeps heartbeat in `metrics.ts` because its bootstrap does not emit one; athena-ui keeps heartbeat in the bootstrap file. Pick one.
- **`procedure` label cardinality is bounded** by the number of tRPC procedures in the router (dozens, not millions). Safe to attach. Do NOT add per-user or per-request-id labels here.
- The resulting GMP series are `<service>_trpc_request_duration_seconds_{count,bucket,sum}{procedure,type,outcome,...}` and `<service>_trpc_inflight{procedure,...}` — reference these in alerts (see Alerting_prompt.md).

## Instrument Design

Naming:

- Custom instruments: `<service>.<operation>.<measure>` — dotted, lowercased. Examples: `coach.generate.requests`, `slides.render.duration`, `qbr.export.failures`.
- Use standard semantic-convention names where they exist (`http.server.request.duration`, `db.client.operation.duration`, `messaging.client.consumed.messages`). Do not rename them.
- Unit on histograms is mandatory and must be the actual unit (`ms`, `s`, `By`, `1`). Wrong units silently break dashboards.

Counter vs histogram vs gauge:

- **Counter** (`createCounter`) — for things that only go up: requests, errors, bytes processed, messages consumed. Never for "current value."
- **Histogram** (`createHistogram`) — for distributions: latency, payload sizes, queue depths at sample time. Preserves percentiles.
- **Gauge** (`createObservableGauge`) — for current-state observations only: queue depth measured by a callback, pool size, in-flight count. Rare — usually a counter or histogram is the right choice.

## Error Handling

For every operation that records metrics:

- The success path records `outcome=success`.
- Every error path records `outcome=error` AND increments the failures counter.
- An exception that escapes the handler without metric recording is an instrumentation bug — wrap the handler in try/catch and record from the catch.
- Recording metrics must never throw. If the SDK is misconfigured, the app continues. The OTel SDK swallows export errors by default; preserve that behavior.

## Environment And Helm

Add these to the existing OTEL env block in `helm/templates/deployment.yaml` (alongside the trace vars wired by Instrumentation_prompt.md):

```yaml
- name: OTEL_METRICS_EXPORTER
  value: "otlp"                       # or "none" to disable
- name: OTEL_EXPORTER_OTLP_PROTOCOL
  value: "http/protobuf"              # shared with traces; safe to leave if already set
# OTEL_EXPORTER_OTLP_ENDPOINT is shared with traces — do not re-declare
```

Optional overrides:

- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` if metrics must go to a different collector than traces (rare)
- Gate the entire OTEL block on a single `.Values.observability.enabled` value so dev/prod can toggle independently

For local development:

- leave `OTEL_METRICS_EXPORTER=none` by default — local runs do not need a collector
- if a local collector is available, set `OTEL_EXPORTER_OTLP_ENDPOINT` to it; metrics will follow

## Verification

After instrumentation:

1. Trigger the endpoint multiple times — at least 5 successes and 3 errors. For a smoketest, use a `demo.mode=error` query param or equivalent to force errors on demand.
2. In Google Cloud Console → Monitoring → Metrics Explorer, search for `prometheus.googleapis.com/<service>_generate_requests_total` (OTLP names get the `_total` suffix and dots become underscores in GMP).
3. Confirm the time series splits correctly by `outcome` and any operational attributes. Each combination should be a separate series, none should be missing.
4. Confirm the histogram (`<service>_generate_duration_bucket`) shows percentiles — try a `histogram_quantile(0.95, ...)` query.
5. Confirm `http_server_request_duration_seconds_bucket` appears under Application Monitoring's automatic HTTP dashboards.
6. Trigger one failure and confirm the failures counter increments while the request counter also increments — the two should never be out of sync by more than one in-flight request.

## Deliverable Expectations

When applying this prompt to a project, the agent should:

- confirm tracing is already in place (Instrumentation_prompt.md applied)
- inspect the repo for existing meters or instruments before adding new ones
- implement the four instruments + one helper per user-facing operation
- update Helm env wiring
- add only necessary code and docs
- verify the result by triggering real traffic and querying Cloud Monitoring, not just by reading the code
