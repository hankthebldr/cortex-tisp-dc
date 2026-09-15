# Instrumentation Prompt

Use this prompt when instrumenting an app to work with our shared OpenTelemetry setup on GKE.

Write the code. Do not stop at recommendations.

Keep the implementation lean, debuggable, and environment-driven.

## Goal

Instrument the app so traces flow through our shared OTEL collectors and appear in Google Trace Explorer.

Current backend assumptions:

- traces -> Google Cloud only
- logs -> Google Cloud only
- metrics -> see [Metrics_prompt.md](./Metrics_prompt.md). Apply this prompt first; metrics layer on top of an existing trace bootstrap.
- no app should export directly to a vendor backend

## Pre-flight: Detect Existing State (do this FIRST, before any edit)

Before touching a single file, classify the app into one of three states. The correct action for each is different, and getting this wrong wastes a code review or worse.

**State A — No OTEL at all.** No `observability` block in `helm/values.yaml`, no `opentelemetry-*` in the dependency file, no instrumentation code. → Apply this prompt fully.

**State B — OTEL wired but broken or partial.** Some scaffolding exists but doesn't produce the traces the user wants (missing annotation, wrong mode, wrong endpoint, no manual spans on a critical path, no propagation across an async boundary, etc.). → Diagnose the specific gap and fix ONLY that gap. Do not rewrite what already works.

**State C — OTEL fully working.** Chart matches the app-template's canonical operator-injected pattern, the deployed pod has the init container, and the user has confirmed traces reach Cloud Trace. → **STOP. Do not make cosmetic template changes.** Report state to the user and exit.

### How to classify

Run these checks in order. Note failures as you go; do not stop at the first failure — you need the full picture to distinguish A from B.

1. **Chart scaffolding present?** Pass if EITHER form is in place:
   - **Shape A (values-driven):** `helm/values.yaml` has `observability.enabled: true` + `observability.mode` (`operator-injected` or `app-bootstrap`), AND `helm template ./helm` renders the `instrumentation.opentelemetry.io/inject-<language>` annotation on the pod template.
   - **Shape B / C (hand-authored, single or multi-workload):** each `kind: Deployment` template under `helm/**/templates/` has the annotation on the pod template metadata AND a per-workload `OTEL_SERVICE_NAME` env var on the container. Missing on any one workload → fails this check (that workload is untraced).

2. **Cluster-side operator present?**
   ```
   kubectl get instrumentation -n observability
   ```
   Expect `otel-<language>` matching `observability.language`.

3. **Pod actually mutated?** For a multi-workload chart, check EACH workload — not just one.
   ```
   kubectl -n <ns> get pod -l app=<workload> -o yaml | grep -A2 initContainers
   kubectl -n <ns> exec deploy/<workload> -- env | grep OTEL_
   ```
   Expect an init container named `opentelemetry-auto-instrumentation-<language>` and CR-supplied env vars (`OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_PROPAGATORS`, `OTEL_TRACES_SAMPLER*`) on every workload that should be traced.

4. **App code calls the SDK?**
   - Dependency file includes `opentelemetry-api` (Python) or equivalent for the language.
   - A manual span exists on at least one critical business path (skip this criterion for smoketests whose only job is to prove the pipeline — auto-spans are enough there).

5. **User has confirmed traces in Cloud Trace?** Ask before assuming — do not infer this from the pod being healthy.

**Decision:**

- All five pass → **State C.** Report:
  > "Inspection shows OTEL is already fully wired and verified working:
  > - values.yaml: mode=operator-injected, language=&lt;x&gt;, enabled=true
  > - pod: init container present, CR env vars flowing
  > - code: manual span at &lt;path&gt;
  >
  > No changes needed. If you want additional instrumentation (new spans, propagation across a new async boundary, coverage for a new endpoint, etc.), tell me the specific gap."
- Any of 1–4 fail → **State B.** Diagnose the specific gap and fix ONLY that gap. Do not "clean up" adjacent code.
- All of 1–4 fail → **State A.** Apply the rest of this prompt.

### What "cosmetic template change" means (do not do this)

If `helm/templates/deployment.yaml` was hand-edited BEFORE the app-template's chart was updated to the values-driven pattern, and `helm template ./helm` still renders the same annotation and env vars as the canonical chart, do NOT replace the hand-edited file just to "align with the template." **Rendered YAML is what deploys; template code style is not.** A refactor that produces byte-identical rendered output is churn, not instrumentation.

Only replace or restructure the chart when the rendered YAML actually needs to change. When it does need to change, always run `helm template ./helm` before and after and diff the output — confirm the change is what you intended.

## Core Rules

1. Reuse any existing OTEL bootstrap if the app already has one.
2. Prefer one tracing pipeline per app.
3. Use auto-instrumentation as the baseline.
4. Add manual spans for critical business and AI paths.
5. Propagate trace context across frontend, backend, jobs, queues, and downstream calls.
6. Use environment variables or Helm values for OTLP configuration.
7. Do not hardcode cluster-specific or vendor-specific endpoints in source code.
8. Set stable service identity with OTEL resource attributes.
9. Keep dependencies minimal and prefer official OpenTelemetry libraries for the language/framework.

## Default Strategy

Use both:

- auto-instrumentation for baseline HTTP/framework/library coverage
- manual instrumentation for important flows that support and engineering actually need

Do not rely on auto-instrumentation alone for:

- AI or model calls
- agent or workflow steps
- retrieval and file-processing stages
- queue boundaries
- long-running jobs
- critical DB operations tied to user requests

## Infra Assumptions

Apps send OTLP once to the in-cluster collector.

Typical in-cluster endpoints:

- OTLP HTTP: `http://otel-agent.observability.svc.cluster.local:4318`
- OTLP gRPC: `otel-agent.observability.svc.cluster.local:4317`

But do not hardcode these blindly in code. Read from env/config first and wire Helm values if needed.

Expected config style:

- backend: `OTEL_EXPORTER_OTLP_ENDPOINT`
- backend: `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`
- backend: `OTEL_SERVICE_NAME`
- backend: `OTEL_RESOURCE_ATTRIBUTES`
- frontend: `VITE_OTEL_EXPORTER_OTLP_ENDPOINT`
- frontend: `VITE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`

If env vars are already present, preserve them.

For frontend frameworks, use the framework's public env naming convention rather than hardcoding one pattern.
Examples:

- Vite: `VITE_*`
- Next.js: `NEXT_PUBLIC_*`

Service identity guidance:

- set `OTEL_SERVICE_NAME` to the actual app/service name
- use `OTEL_RESOURCE_ATTRIBUTES` for stable attributes such as environment, version, and namespace when the repo already has those values available
- do not invent fake or low-value resource attributes
- for web OTLP exporters, normalize a base OTLP HTTP endpoint to the traces path if required by the exporter, typically `/v1/traces`

## What To Instrument

Always instrument:

- inbound HTTP routes
- outbound API calls
- LLM/model calls
- tool calls
- agent/workflow boundaries
- retrieval/file-processing stages
- queue publish/consume
- background jobs
- important DB reads/writes in user-facing flows

If the app has a frontend, instrument:

- browser startup only if client traces are actually needed
- outgoing browser requests so trace context reaches the backend
- add direct browser OTLP export only if the browser has a reachable OTLP endpoint or same-origin proxy path
- do not point browser code at in-cluster `*.svc.cluster.local` collector addresses

Do not over-instrument:

- tiny helpers
- noisy loops
- every UI click
- high-frequency chunk/event handlers unless required

## Propagation

This is mandatory.

If the app has both frontend and backend, propagate trace context from browser to server.

Requirements:

- use W3C Trace Context with `tracecontext,baggage`
- browser requests must carry trace headers
- backend must continue incoming context instead of always starting fresh traces
- downstream service calls should use the active span context

End goal:

- one logical trace can be followed from frontend action to backend processing and downstream dependencies

If direct browser trace export is not feasible in the current deployment model, backend tracing is still valid. In that case, preserve request trace headers and make backend traces correct rather than adding a broken browser exporter.

### Async queue boundaries

HTTP auto-instrumentation does not cross async queue boundaries (Pub/Sub, Kafka, SQS, RabbitMQ, Celery, etc.). The publisher finishes its trace; the consumer starts a fresh, unrelated trace. The single business operation appears as two disconnected traces in Cloud Trace.

If the app publishes to or consumes from an async queue, add manual context propagation:

- On publish: extract the active trace context with `TraceContextTextMapPropagator().inject()` and write it into the message's `attributes` / `headers` dict (whatever the client library exposes).
- On receive: `extract()` the context back from the message attributes and attach it to the consumer's root span so the consumer span becomes a child of the publisher's span.

Use the same W3C `tracecontext,baggage` propagator as for HTTP — message attributes carry the `traceparent` string the same way HTTP headers do. End result: one logical trace from publisher to consumer to downstream calls, even though the boundary is asynchronous.

**Enumeration rule (do this or you WILL miss a boundary):** grep the entire repo for every publish site and every subscriber callback, then wire each one. It is not enough to wire "the obvious" API→consumer boundary; secondary publishes (status events, retry queues, dead-letter topics, fan-out topics) count too, even if no consumer subscribes to them in this codebase today. A future subscriber that lands on those messages must be able to continue the trace.

Concrete checklist to run before declaring done:

- Grep for the client library's publish call in the target language. Examples:
  - Python / GCP Pub/Sub: `grep -rn "publisher\.publish\|PublisherClient" --include="*.py"`
  - Python / Kafka: `grep -rn "producer\.send\|KafkaProducer" --include="*.py"`
  - Python / Celery: `grep -rn "\.apply_async\|\.delay(" --include="*.py"`
  - Node / GCP Pub/Sub: `grep -rn "\.publishMessage\|PublisherClient" --include="*.{ts,js,mjs}"`
  - Node / Kafka: `grep -rn "\.send({" --include="*.{ts,js,mjs}"` (narrow further as needed)
- Every hit must be wrapped in a PRODUCER span AND have `_propagator.inject(carrier)` before the publish call, with the carrier keys passed to the publish call as message attributes / headers.
- Grep for the subscriber callback / consumer loop in the target language. Examples:
  - Python / GCP Pub/Sub: `grep -rn "SubscriberClient\|streaming_pull\|def callback" --include="*.py"`
  - Python / Kafka: `grep -rn "KafkaConsumer\|for msg in consumer" --include="*.py"`
- Every hit must `_propagator.extract(dict(message.attributes))` (or headers equivalent), `context.attach(parent_ctx)` before opening the CONSUMER root span, and `context.detach(token)` in a `finally` block.

Report the enumerated hits in your summary — literally list each publish site and each callback, and confirm each got inject/extract. If your enumeration finds N publish sites and your diff has fewer than N inject calls, the deliverable is incomplete.

## Implementation Pattern

1. Run the **Pre-flight** classification above. If the result is State C, stop here — do not proceed to the steps below.
2. For State B, name the specific gap you're fixing before writing anything. Everything you touch must be justified by that gap.
3. **For State A, default to `app-bootstrap` mode for every language.** The app ships a bootstrap file (`bootstrap.py` for Python, `instrumentation.mjs` for Node) that explicitly wires TracerProvider + MeterProvider + LoggerProvider with OTLP exporters. Auto-instrumentors (FastAPI, requests, etc.) are installed via language-specific `opentelemetry-instrumentation-*` packages and called from the bootstrap file.

   **Do NOT use operator-injected mode.** It has two silent-failure gotchas that only appear post-deploy:
   - **Python:** the operator's auto-config sets up a `MeterProvider` but does NOT attach a global `MetricReader` for custom code. Custom metrics (`_meter.create_counter(...)` etc.) silently discard. Traces work; metrics don't. See "OTEL Python Metrics Pipeline" for the mechanism.
   - **Node ESM / Next.js:** the init container's monkey-patching can't hook into ESM entrypoints cleanly. Instrumentation misses most of the app.

   Operator-injected is still supported by the chart as an escape hatch (`observability.mode: operator-injected`), but only use it when you cannot ship a bootstrap file (e.g., a legacy runtime you can't modify). For everything else, app-bootstrap.

4. **For State A, do all of the following in the same pass — do not phase.** A chart-only diff is an incomplete deliverable, not a milestone. Specifically, in one session you must produce:
   - the bootstrap file (`bootstrap.py` for Python — see the canonical template in "Python app-bootstrap: canonical bootstrap.py" section below)
   - the chart wiring (per-workload `OTEL_SERVICE_NAME` + `OTEL_EXPORTER_OTLP_ENDPOINT` env vars; NO operator annotation)
   - all SDK deps in `requirements.txt`: `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, plus `opentelemetry-instrumentation-*` for each auto-instrumentor you want (fastapi/requests/logging etc.)
   - Dockerfile update to `COPY *.py .` (or an explicit line for `bootstrap.py`) so the new file lands in the image
   - `import bootstrap  # noqa: F401` as the FIRST import in each service's main.py
   - manual spans at every high-value boundary listed in "What To Instrument"
   - manual `traceparent` inject/extract on every async queue boundary (see "Async queue boundaries" — mandatory)
   - RED metrics if the app is user-facing (see Metrics_prompt.md)

   Do NOT propose "chart first, verify, then add code." A chart-only PR leaves the app with disconnected traces and silent-failure metrics. Verify all of it together against the deployed pod at the end.
5. Keep existing startup behavior unless there is a clear OTEL bootstrap gap.
6. Add manual spans only at high-value boundaries.
7. Return or surface a trace ID or support ID where practical.
8. Before declaring done: run `helm template ./helm` and diff against the pre-change output. Every change in the rendered YAML must be one you intended. Byte-identical rendered output means you made a churn edit — revert it.

Concrete implementation examples:

### Detect chart shape first

Before applying the values snippets below, figure out what shape this chart is in. This determines HOW you wire the annotation and env vars — the values-driven `observability:` block is one option, not the only one.

- **Shape A — app-template canonical.** `helm/values.yaml` has an `observability:` block and `helm/templates/deployment.yaml` renders the annotation from `.Values.observability.mode`. → Use the values-file snippets below as-is.
- **Shape B — hand-authored single workload.** One Deployment template, no `observability:` block in values.yaml. → Add the annotation on the pod template metadata + the per-app OTEL env vars on the container env, directly in the Deployment template. The values-snippet examples below describe WHAT gets rendered; you're rendering it by hand.
- **Shape C — hand-authored multi-workload.** Multiple Deployment templates in one chart (e.g. `api-deployment.yaml`, `email-deployment.yaml`, `slack-deployment.yaml`). → Same as Shape B, repeated for each workload. **Each workload gets its own `OTEL_SERVICE_NAME`** — Cloud Trace groups spans by service name, so distinct names are what let you filter `api` vs `email-consumer` vs `slack-consumer`.

Quick detection:

```
grep -l 'kind: Deployment\|kind: StatefulSet\|kind: Job' helm/**/templates/*.yaml 2>/dev/null
grep -n '^observability:' helm/**/values.yaml 2>/dev/null
```

Multiple workload files → Shape C. Single workload file with `observability:` in values.yaml → Shape A. Single workload file without → Shape B.

**Do NOT replace a Shape B or C chart with the app-template's canonical chart just to convert it to Shape A.** You'll collapse the app's deployment topology. If the app deploys three separate workloads today, it must still deploy three separate workloads after instrumentation.

For Shape B or C in operator-injected mode, the per-workload additions look like:

```yaml
# Pod template metadata — one annotation per workload
spec:
  template:
    metadata:
      annotations:
        instrumentation.opentelemetry.io/inject-python: "observability/otel-python"
    spec:
      containers:
        - name: <container>
          env:
            - name: OTEL_SERVICE_NAME
              value: "<workload-name>"    # e.g. notification-api, email-consumer, slack-consumer
            - name: OTEL_TRACES_EXPORTER
              value: "otlp"
            - name: OTEL_METRICS_EXPORTER
              value: "none"
            - name: OTEL_LOGS_EXPORTER
              value: "none"
```

Endpoint / propagator / sampler come from the Instrumentation CR — do NOT set them at pod level, same rule as Shape A operator-injected mode.

For Shape B or C in app-bootstrap mode, add the full env block per workload (endpoint, protocol, propagators, sampler) — see the Shape A app-bootstrap example below for the exact env vars, and repeat them on each workload's container spec.

The rest of this section shows the Shape A (values-driven) form. Read it to understand what values you're wiring, even if you're actually hand-editing for Shape B or C.

### Shape A: values-driven (app-template canonical)

**Default: `app-bootstrap` mode for every language.**

```yaml
# helm/values.yaml
observability:
  enabled: true
  mode: app-bootstrap      # DEFAULT
```

The chart then emits only `OTEL_SERVICE_NAME` + `OTEL_EXPORTER_OTLP_ENDPOINT` on the pod. The app's bootstrap file (`bootstrap.py` for Python, `instrumentation.mjs` for Node) reads them and wires the SDK. No operator annotation, no init container.

### Python app-bootstrap: canonical bootstrap.py

Every Python app needs a `bootstrap.py` next to `main.py`, imported first from `main.py` via `import bootstrap  # noqa: F401` before any other module. Canonical content:

```python
"""OTEL app-bootstrap. Imported first from main.py so provider setup happens
before any app code runs.
"""
import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
# Add FastAPIInstrumentor for FastAPI apps; skip for pure Pub/Sub consumers.
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pythonjsonlogger import jsonlogger

_SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "my-app")
_OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").rstrip("/")
_PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "wwss-as-trust-dev")
_METRIC_INTERVAL_MS = int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "10000"))

_resource = Resource.create({"service.name": _SERVICE_NAME})

_tracer_provider = TracerProvider(resource=_resource)
_tracer_provider.add_span_processor(
    BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{_OTLP_ENDPOINT}/v1/traces"))
)
trace.set_tracer_provider(_tracer_provider)

metrics.set_meter_provider(
    MeterProvider(
        resource=_resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=f"{_OTLP_ENDPOINT}/v1/metrics"),
                export_interval_millis=_METRIC_INTERVAL_MS,
            )
        ],
    )
)

# Auto-instrumentors — only enable what you use. DO NOT enable
# opentelemetry-instrumentation-grpc: it breaks google-cloud-pubsub's
# bidi streaming pull (see "Known compatibility gotcha" below).
LoggingInstrumentor().instrument(set_logging_format=False)
RequestsInstrumentor().instrument()
# For FastAPI, exclude kubelet health probes to keep /health out of Cloud Trace
# and out of http.server.request.duration percentiles:
# FastAPIInstrumentor().instrument(excluded_urls="health,healthz")

# Heartbeat counter — required for absence alerts (see Alerting_prompt.md).
# A dedicated counter incremented on a 30s timer, existing SOLELY to produce
# a continuous OTLP export. `absent_over_time(<service>_heartbeat_total[5m])`
# fires only when the whole SDK → collector → GMP pipeline is broken —
# independent of whether users are hitting the app.
import threading

_heartbeat = metrics.get_meter(_SERVICE_NAME).create_counter(
    f"{_SERVICE_NAME.replace('-', '_')}.heartbeat",
    description="Liveness signal incremented on a 30s timer, for absence alerting.",
)

def _pulse():
    _heartbeat.add(1)
    t = threading.Timer(30.0, _pulse)
    t.daemon = True
    t.start()

_pulse()


class _CloudTraceJSONFormatter(jsonlogger.JsonFormatter):
    """Emits Cloud Logging's `logging.googleapis.com/trace` field so
    Cloud Trace's "View logs" button joins logs to spans."""
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        # Cloud Logging severity mapping. Without this, every log line lands
        # as ERROR because Python's default StreamHandler writes to stderr
        # and GKE's fluent-bit maps stderr → ERROR unless a `severity` field
        # is present in the JSON payload. Fleet-wide bug caught 2026-07-23
        # via a notification-system alert investigation.
        log_record["severity"] = record.levelname
        trace_id = getattr(record, "otelTraceID", None)
        span_id = getattr(record, "otelSpanID", None)
        if trace_id and trace_id != "0":
            log_record["logging.googleapis.com/trace"] = (
                f"projects/{_PROJECT_ID}/traces/{trace_id}"
            )
        if span_id and span_id != "0":
            log_record["logging.googleapis.com/spanId"] = span_id


_handler = logging.StreamHandler()
_handler.setFormatter(
    _CloudTraceJSONFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
)
logging.getLogger().handlers = [_handler]
logging.getLogger().setLevel(logging.INFO)
```

Deps for `requirements.txt` — **pin every entry to an exact `==X.Y.Z`** (no `~=`, no `X.Y.*`, no unpinned). Same reasoning as the Node pinning rule below: fresh CI installs will pick a newer patch otherwise, and OTEL's `0.x` instrumentors ship breaking changes in patch releases. Example:

```
opentelemetry-api==1.44.0
opentelemetry-sdk==1.44.0
opentelemetry-exporter-otlp-proto-http==1.44.0
opentelemetry-instrumentation-logging==0.65b0
opentelemetry-instrumentation-requests==0.65b0
opentelemetry-instrumentation-fastapi==0.65b0     # only for FastAPI apps
python-json-logger==4.1.0
```

To find today's resolved patch versions for existing wildcards, run `pip install --dry-run --report -` against the file and pin to whatever the resolver picked.

**Python 3.9 apps** (e.g., doc-generator, hosted-xsiam-pov): `opentelemetry-api==1.44.0` requires Python≥3.10. Also `python-json-logger==4.x` requires Python≥3.10. Pin to the last 3.9-compatible line instead — `1.41.0` / `0.62b0` (NOT `1.41.1` — its transitive `semantic-conventions==0.62b1` mismatches instrumentors' `0.62b0`):

```
opentelemetry-api==1.41.0
opentelemetry-sdk==1.41.0
opentelemetry-exporter-otlp-proto-http==1.41.0
opentelemetry-instrumentation-*==0.62b0
python-json-logger==3.3.0
```

Symptoms if you skip this: kaniko fails with `Could not find a version that satisfies the requirement opentelemetry-api==1.44.0 ... requires Python >=3.10` OR `ResolutionImpossible: sdk 1.41.1 depends on semantic-conventions==0.62b1, instrumentation-* 0.62b0 depends on 0.62b0`.

Dockerfile: `COPY api/*.py .` (or whatever path) — must include `bootstrap.py`, not just `main.py`.

### Node.js app-bootstrap

For Node the bootstrap file is `instrumentation.mjs` or `instrumentation.node.ts` (Next.js 15+), invoked via:

```bash
node --import ./instrumentation.mjs server.js
```

(For Next.js 15+: create both `instrumentation.ts` at repo root that dynamically imports `./instrumentation.node.ts` when `NEXT_RUNTIME === 'nodejs'`. Next.js's build system auto-loads it at server startup.)

Same principles as Python: TracerProvider + MeterProvider set explicitly, auto-instrumentors registered from within the bootstrap. **Register specific instrumentors (`HttpInstrumentation` + `UndiciInstrumentation`) explicitly, NOT `getNodeAutoInstrumentations()`.** See "Node OTEL line selection" below for the pinned deps and the pnpm reason behind this default. Full reference: `/Users/dnguyen/VSC/athena-ui/src/instrumentation.node.ts`.

**Next.js 14 apps (e.g., asset-portal 14.0.4) — this pattern DOES NOT WORK.** Next 14 + `output: standalone` has multiple bundling issues that don't exist in Next 15:

1. `experimental.instrumentationHook: true` must be set in `next.config.js` — without it, `register()` is a silent no-op. (Stable in Next 15, no config needed.)
2. Next 14's standalone output tracing does NOT follow relative dynamic imports — `import('./instrumentation.node')` results in the file being compiled but never included in `.next/server/`. SDK silently unloaded.
3. `@opentelemetry/sdk-node` transitively imports `@grpc/grpc-js` (native code) via its auto-configure path. Webpack can't bundle native code.
4. `getNodeAutoInstrumentations()` bundles 40+ instrumentors (aws-lambda, kafka, undici, net, etc.) — many touch Node builtins (`fs`, `tls`, `net`, `diagnostics_channel`) that webpack can't resolve.
5. `experimental.serverComponentsExternalPackages` only covers RSC, NOT `instrumentation.ts`. Need webpack externals separately.

**Next 14 canonical pattern** (asset-portal is the reference):
- Single `src/instrumentation.ts` file (no separate `.node.ts`), all setup inlined inside `if (NEXT_RUNTIME === 'nodejs')`.
- Dynamic imports of npm packages directly (`await import('@opentelemetry/sdk-trace-node')`) — Next 14 traces these correctly, unlike relative dynamic imports.
- **Skip `sdk-node`** — build `NodeTracerProvider` + `MeterProvider` manually from `@opentelemetry/sdk-trace-node` + `@opentelemetry/sdk-metrics` + `@opentelemetry/resources` + `@opentelemetry/instrumentation` primitives.
- **Skip `auto-instrumentations-node`** — register only `HttpInstrumentation` + `UndiciInstrumentation` explicitly. HTTP covers Next.js SSR + api routes + outbound http. Undici covers Node's global fetch (Next server components use it).
- `next.config.js`: set `experimental.instrumentationHook: true` + `experimental.serverComponentsExternalPackages` + explicit webpack `config.externals` for OTEL packages in the `webpack(config, { isServer })` function.
- Deps: NO `sdk-node`, NO `auto-instrumentations-node`. YES `instrumentation`, `instrumentation-http`, `instrumentation-undici`, `resources`, `sdk-metrics`, `sdk-trace-node`, plus the two exporters.

Full working reference: `/Users/dnguyen/VSC/asset-portal/src/instrumentation.ts` + `next.config.js` + `package.json`. Also see the otel-log entry for the 8-failure fix chain that got there.

**Pin every OTEL dep to an exact version (no `^`, no `~`).** Two reasons:

1. OTEL's non-stable packages (`sdk-node`, `sdk-metrics`, `auto-instrumentations-node`, all exporters, all instrumentors) sit at `0.x.y` — under npm semver a caret expands `^0.52.0` to any `0.52.z`, so CI *will* pick up patch bumps silently. Some of those patches change transitive peer deps and force an OTEL 1.x → 2.x migration on a routine `npm install`.
2. A single instrumentor bug (see the pg leak below) can cascade into production. Deterministic lockfile alone is not enough — a lockfile-less clean install (some CI paths, ncu bumps, dependabot) reintroduces drift.

### Node OTEL line selection (2.x is canonical for new apps)

**Default for any new Node app: OTEL 2.x line + specific instrumentors (`HttpInstrumentation` + `UndiciInstrumentation`), NOT `auto-instrumentations-node`.** Reference implementation: `/Users/dnguyen/VSC/athena-ui/src/instrumentation.node.ts` + `package.json` (Next.js 15, shipped 2026-07-20). The 2.x line is what all new instrumentation should target; the 1.x line is now legacy (retained on csr-qbr-slide-generator and report-editor, do not migrate them without reason).

Canonical pinned block — **OTEL 2.x line (default)**:

```json
"@opentelemetry/api": "1.9.1",
"@opentelemetry/exporter-metrics-otlp-proto": "0.214.0",
"@opentelemetry/exporter-trace-otlp-proto": "0.214.0",
"@opentelemetry/instrumentation": "0.214.0",
"@opentelemetry/instrumentation-http": "0.214.0",
"@opentelemetry/instrumentation-undici": "0.24.0",
"@opentelemetry/resources": "2.8.0",
"@opentelemetry/sdk-metrics": "2.8.0",
"@opentelemetry/sdk-node": "0.214.0",
"@opentelemetry/sdk-trace-node": "2.8.0"
```

Notice what's absent: **no `@opentelemetry/auto-instrumentations-node`**. Register `HttpInstrumentation` + `UndiciInstrumentation` directly on the NodeSDK. HTTP covers Next.js SSR + Express + plain http servers; Undici covers Node's global fetch (Next server components, `fetch()` from anywhere). Add other instrumentors (`instrumentation-pg`, `instrumentation-ioredis`, etc.) explicitly if the app uses those libraries.

**Required env var on 2.x — set at the chart layer (already added to app-template's `helm/templates/deployment.yaml` in the app-bootstrap conditional):**

```
OTEL_SEMCONV_STABILITY_OPT_IN=http/dup
```

`@opentelemetry/instrumentation-http` 0.55+ emits `http.server.request.duration` (the stable name) ONLY when this env var is set. Without it, only legacy metric names fire and the modern name is silently missing from GMP — hours of "the metric isn't there" debugging for a one-line fix. `http/dup` emits both stable + legacy so downstream dashboards on the old name keep working. Harmless on the 1.x line and on Python (unrecognized env, no error).

Canonical pinned block — **OTEL 1.x line (legacy, kept for csr-qbr-slide-generator and report-editor)**:

```json
"@opentelemetry/api": "1.9.1",
"@opentelemetry/auto-instrumentations-node": "0.57.0",
"@opentelemetry/exporter-metrics-otlp-proto": "0.52.1",
"@opentelemetry/exporter-trace-otlp-proto": "0.52.1",
"@opentelemetry/sdk-metrics": "1.25.1",
"@opentelemetry/sdk-node": "0.52.1"
```

`0.57.0` is the LAST `auto-instrumentations-node` release that stays on the OTEL core 1.x peer range. `0.57.1` and later require `@opentelemetry/core@^2.0.0` and drag the whole SDK into a 2.x migration — do not bump the caret loose.

**Why the 2.x line drops `auto-instrumentations-node` — pnpm gotcha (asset-portal 2026-07-22):** under pnpm, `require('@opentelemetry/auto-instrumentations-node')` internally requires each of ~40 individual instrumentors (`@opentelemetry/instrumentation-amqplib`, `-kafka`, `-mongodb`, `-redis-4`, etc.). pnpm does NOT hoist those transitives to top-level `node_modules/@opentelemetry/` unless they're listed directly in `package.json`. Runtime `require()` fails with `Cannot find module '@opentelemetry/instrumentation-amqplib'`, and if the preload wraps setup in `try/catch`, the failure is silently swallowed → OTEL never runs. This is the actual reason for the "specific instrumentors" default above — it's not just cleaner, it's the only pattern that works reliably under pnpm. npm/yarn hoist differently and the auto bundle works there; still, use specific instrumentors even on npm apps for consistency.

**NEVER wrap OTEL setup in silent `try/catch`.** Any failure means "no OTEL running but you don't know it." Let it throw. If graceful degradation is truly required, log the failure LOUDLY (stderr with unique marker) so operators notice.

**Log-trace correlation for Node — canonical pattern:**

**WARNING for Next.js apps:** DO NOT globally wrap `console.*` for log correlation. asset-portal (Next 14) reverted 2026-07-22 after the console wrapper triggered "Invalid Auth Cookie" errors surfacing in production — React server components' error boundaries pass error objects to `console.error`, and re-serializing them via a wrapper (JSON.stringify) changes the shape Next.js sees and can cause error cascades. **For Next.js**, prefer: attach trace context as span attributes and let existing app logging alone, OR use a dedicated logger (`pino` with an OTEL processor) that owns its own emit path. Non-Next.js Node apps (Express, plain http servers) can use the console wrap safely.

Node apps typically use `console.log` / `console.error` directly (no `pino` / `winston` dep). Add a console wrapper in `instrumentation.node.ts` that:

1. Emits every log as JSON with `logging.googleapis.com/trace` and `logging.googleapis.com/spanId` fields — Cloud Logging + GKE fluent-bit auto-recognize these and correlate log entries to their trace.
2. Uses the **root span ID** (not the deepest active leaf span) so Cloud Trace's "View logs" button returns results when clicked on the top-level `GET /...` span. Without this, auto-instrumented nested spans (HTTP → GCS → fetch) cause `console.log` calls to inherit leaf spanIds, and clicking the root span in Cloud Trace returns zero logs.

Full block (append after `sdk.start()`):

```typescript
import { Context, Span, trace } from '@opentelemetry/api';
import { BatchSpanProcessor, SpanProcessor } from '@opentelemetry/sdk-trace-node';

// Root-span tracker: maps traceId → root spanId so log wrap can use root
// instead of leaf. Populated on span start (when parent context has no
// active span), cleaned up on root span end.
const rootSpanIdByTrace = new Map<string, string>();

const rootSpanTracker: SpanProcessor = {
  onStart(span: Span, parentContext: Context): void {
    if (!trace.getSpan(parentContext)) {
      const spanCtx = span.spanContext();
      rootSpanIdByTrace.set(spanCtx.traceId, spanCtx.spanId);
    }
  },
  onEnd(span): void {
    const spanCtx = span.spanContext();
    if (rootSpanIdByTrace.get(spanCtx.traceId) === spanCtx.spanId) {
      rootSpanIdByTrace.delete(spanCtx.traceId);
    }
  },
  async shutdown(): Promise<void> {},
  async forceFlush(): Promise<void> {},
};

// Register the tracker as a SpanProcessor. Because passing `spanProcessors`
// to NodeSDK overrides the default `traceExporter`, include a BatchSpanProcessor
// for the OTLP exporter in the same array:
//
//   const spanProcessors: SpanProcessor[] = [rootSpanTracker];
//   if (traceExporter) spanProcessors.push(new BatchSpanProcessor(traceExporter));
//   const sdk = new NodeSDK({ spanProcessors, metricReader, instrumentations: [...] });

// Console wrap — wraps global console.* to emit structured JSON with the
// root spanId. Zero touches to app code.
//
// GOOGLE_CLOUD_PROJECT MUST be set on the pod (the chart's env: block should
// include `- name: GOOGLE_CLOUD_PROJECT value: "{{ .Values.gcp.project_id }}"`).
// If unset, log entries emit WITHOUT the trace field — correlation silently
// won't work, but at least won't point at the WRONG project. Never hardcode
// a project ID here; a dev-guess default silently misroutes prod traces.
const LOG_PROJECT_ID = process.env.GOOGLE_CLOUD_PROJECT;
if (!LOG_PROJECT_ID) {
  // Use the original (unwrapped) console so this warning always surfaces,
  // even if the wrap fails.
  process.stderr.write(
    '[bootstrap] GOOGLE_CLOUD_PROJECT env var not set — log-trace correlation ' +
    'disabled. Cloud Trace "View logs" button will not find any logs for traces ' +
    "from this pod. Add GOOGLE_CLOUD_PROJECT to the deployment's env block " +
    '(sourced from .Values.gcp.project_id).\n',
  );
}

function formatArg(a: unknown): string {
  if (typeof a === 'string') return a;
  if (a instanceof Error) return a.stack || a.message;
  try { return JSON.stringify(a); } catch { return String(a); }
}

function wrapConsole(
  severity: 'INFO' | 'WARNING' | 'ERROR',
  original: (...args: unknown[]) => void,
): (...args: unknown[]) => void {
  return (...args: unknown[]): void => {
    const spanCtx = trace.getActiveSpan()?.spanContext();
    const entry: Record<string, unknown> = {
      severity,
      message: args.map(formatArg).join(' '),
      timestamp: new Date().toISOString(),
    };
    if (spanCtx?.traceId && LOG_PROJECT_ID) {
      const rootSpanId = rootSpanIdByTrace.get(spanCtx.traceId) || spanCtx.spanId;
      entry['logging.googleapis.com/trace'] = `projects/${LOG_PROJECT_ID}/traces/${spanCtx.traceId}`;
      entry['logging.googleapis.com/spanId'] = rootSpanId;
    }
    original(JSON.stringify(entry));
  };
}

const _origLog = console.log.bind(console);
const _origWarn = console.warn.bind(console);
const _origError = console.error.bind(console);
console.log = wrapConsole('INFO', _origLog);
console.info = wrapConsole('INFO', _origLog);
console.warn = wrapConsole('WARNING', _origWarn);
console.error = wrapConsole('ERROR', _origError);
```

### Node warning severity — downgrade Node runtime warnings

`process.emitWarning()` (used by `MaxListenersExceededWarning`, TLS reject, deprecation warnings, unhandled promise, etc.) routes through `console.error` internally. Without a check, all these tag as `severity=ERROR` in Cloud Logging — red-alarming on things that are actually informational. Detect the pattern and downgrade:

```typescript
const NODE_WARNING_RE = /^\(node:\d+\)\s+\w*Warning:/;

function wrapConsole(severity, original) {
  return (...args) => {
    const message = args.map(formatArg).join(' ');
    const actualSeverity =
      severity === 'ERROR' && NODE_WARNING_RE.test(message) ? 'WARNING' : severity;
    // ... use actualSeverity in the entry object instead of severity
  };
}
```

### Node.js PostgreSQL drivers — check which one before applying pg fix

Node has two competing PostgreSQL drivers, both widely used:

| npm package | Also known as | OTEL auto-instrumentor |
|---|---|---|
| `pg` | node-postgres | Yes — `@opentelemetry/instrumentation-pg` (in `getNodeAutoInstrumentations()`) |
| `postgres` | postgres.js | No auto-instrumentor in the standard bundle |

Framework choice (Next.js, Express, etc.) does not determine the driver — it's a separate library choice made when the app was scaffolded. `grep '"pg"\|"postgres"' package.json` to see which one an app uses.

### If the app uses `pg`: make sure the pinned auto-instrumentations-node includes the leak fix

Earlier versions of `@opentelemetry/instrumentation-pg` (`< 0.46.0`) attached EventEmitter listeners to `pg.Pool` on every query without cleaning them up. Over hours of real traffic, listener count grew unbounded — tripped `MaxListenersExceededWarning` (visible as a growing count in the message: `11 → 21 → 31 → ...`) and eventually ate real memory. Upstream fix: [instrumentation-pg PR #2484](https://github.com/open-telemetry/opentelemetry-js-contrib/pull/2484), released in `0.46.0`.

The canonical pinned block above (`auto-instrumentations-node@0.57.0`) transitively brings `instrumentation-pg@0.52.0` — well past the fix. No manual `enabled: false` override needed. Verify after `npm install`:

```
npm ls @opentelemetry/instrumentation-pg
# expect 0.46.0 or newer
```

If you inherit an older repo that DOES pin to a pre-fix version and you can't upgrade immediately, the interim workaround is to disable the instrumentor:

```typescript
instrumentations: [getNodeAutoInstrumentations({
  '@opentelemetry/instrumentation-pg': { enabled: false },
})],
```

Cost: no per-query pg spans in Cloud Trace until you upgrade. Prefer upgrading.

### If the app uses `postgres` (postgres.js): no auto-instrumentor exists

`postgres.js` has no official OTEL auto-instrumentor in the standard bundle — there are no per-query DB spans automatically. To get DB visibility, wrap queries manually at the repository/ORM layer with `tracer.startActiveSpan(...)`.

**Known trade-off (accept it):** clicking the root HTTP span in Cloud Trace returns all logs for the trace. Clicking a child auto-instrumented span (e.g., `storage.download`) returns zero logs, because every log's `spanId` = the root. Users learn to click the top-level span. Making per-span click work would require adding manual spans wrapping every log site (like Python's `with tracer.start_as_current_span(...)` pattern) — not worth it for typical Next.js apps.

### Operator-injected mode (escape hatch — do not use by default)

Available via `observability.mode: operator-injected` for legacy runtimes you can't add a bootstrap to. Two silent-failure gotchas make it unsuitable as a default:

**Python metrics silent-discard:** the operator's Python init container auto-configures a `MeterProvider` but does NOT attach a global `MetricReader` for custom code. Every `_meter.create_counter(...)` call succeeds, every `.add()` succeeds, but nothing is ever exported. Only detectable by querying the backend for the metric name after deploy and finding zero data. See the "OTEL Python Metrics Pipeline" reference for the mechanism.

**Python + Pub/Sub streaming pull:** the operator's auto-injected `opentelemetry-instrumentation-grpc` wraps bidi streaming calls in a generator. `google-cloud-pubsub`'s `SubscriberClient.streaming_pull` uses bidi gRPC and calls `.add_done_callback` on the result. Generators don't have that method — the subscriber thread dies on startup with `AttributeError: 'generator' object has no attribute 'add_done_callback'`. Pod stays Running (main thread is fine), no messages consumed. Under app-bootstrap this doesn't happen because you simply don't install `opentelemetry-instrumentation-grpc`.

**Node ESM / Next.js:** the init container's monkey-patching can't hook into ESM entrypoints cleanly — most of the app is un-instrumented.

If you must use operator-injected (rare):

```yaml
observability:
  enabled: true
  mode: operator-injected
  language: python
```

Precondition: `kubectl get instrumentation -n observability` must show `otel-<language>`. For Python + Pub/Sub subscribers, add `OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=grpc_client,grpc_server,grpc_aio_client,grpc_aio_server` and `OTEL_PYTHON_LOG_CORRELATION=true` on the pod. For custom metrics, do NOT expect them to work — you'll need to add explicit `MeterProvider` setup in the app anyway, at which point you might as well use app-bootstrap.

Do not run two competing OTEL bootstraps in the same process. In particular, do not mix modes — either the operator injects the SDK, or the app bootstraps it, never both.

## Span Design

Use stable, clear span names.

Examples:

- `app.api.generate`
- `app.api.review.submit`
- `app.ai.generate`
- `app.ai.tool_call`
- `app.workflow.review_build`
- `app.db.review_save`

Add useful attributes such as:

- `app.endpoint`
- `app.user.id`
- `app.session.id`
- `app.request.id`
- `app.workflow.name`
- `app.tool.name`
- `gen_ai.system`
- `gen_ai.operation.name`
- `gen_ai.request.model`

### PII in span attributes — hard rule

Span attributes land in Cloud Trace, are searchable, and are retained for weeks. Treat them like log lines that get indexed. **Never put user-identifying values or message payloads in span attributes.**

**Allowed on spans:**

- opaque internal IDs (`app.lookup_key`, `app.request.id`, `app.job.id`) — treat these as safe only when they don't embed user info
- counts and sizes (`app.recipient_count`, `app.batch.size`, `app.retry.count`, `app.payload.bytes`)
- loop indexes (`app.recipient_index = 0..N-1`) — use this INSTEAD of putting the recipient's address on a per-item span
- states, kinds, booleans (`app.final_state = "completed"`, `app.channel = "email"`, `app.db.is_new = true`)
- non-user infrastructure identifiers (`messaging.destination.name = "notification-service-requested"`, `app.gcs.uri` when the URI is a server-owned path, not user input)

**Forbidden on spans (even "just for debugging"):**

- email addresses, phone numbers, physical addresses, names
- Slack user IDs, Slack channel IDs (channel IDs can be DMs), Slack workspace IDs
- OAuth tokens, refresh tokens, API keys, session IDs, cookies
- request or response bodies, message payloads, rendered template output
- fields under a `pii_payload` / `pii` / `personal` key — the name is a warning label; do not read from it into attributes
- resolved values derived from any of the above (e.g. a Slack channel ID resolved from a user's email is still PII)

**Correct pattern for per-recipient / per-item loops:** name the span, index it, count it. Log the identifier if you need it for troubleshooting — logs have retention policies; span attributes don't in the same way.

```python
for i, recipient in enumerate(recipients):
    with tracer.start_as_current_span("app.email.send") as span:
        span.set_attribute("app.recipient_index", i)  # NOT the address
        # ... send ...
        if failed:
            logger.error(f"send failed to {recipient.address}: {err}")  # address in log, not span
```

If a project has a documented, security-reviewed exception (e.g. attributes are stripped by a collector processor before export), follow that. Otherwise this rule is unconditional.

Minimal manual span pattern:

```ts
const span = tracer.startSpan("app.api.generate");
try {
  span.setAttribute("app.endpoint", "/api/generate");
  // work
  span.setStatus({ code: SpanStatusCode.OK });
} catch (error) {
  span.recordException(error);
  span.setStatus({
    code: SpanStatusCode.ERROR,
    message: error instanceof Error ? error.message : String(error),
  });
  throw error;
} finally {
  span.end();
}
```

## Log-trace correlation

Without this, Cloud Trace shows spans correctly but the "View logs" link on each span opens Log Explorer with a filter that matches zero entries — every trace investigation forces you to hand-search Cloud Logging. Wire this on every instrumented app; it is not optional.

**Two things must be true for correlation to work:**

1. The trace ID and span ID must be injected into each log entry at emit time (the app's logging framework has to know which trace is active).
2. The log entry that reaches Cloud Logging must expose the trace ID in the field name Cloud Logging recognizes: `logging.googleapis.com/trace` = `projects/<project>/traces/<trace_id>` and `logging.googleapis.com/spanId` = `<span_id>`. GKE's fluent-bit auto-parses JSON stdout logs and forwards these fields, which is what makes the "View logs" button work.

**Python wiring (app-bootstrap mode):**

Both parts of log-trace correlation are done in `bootstrap.py` — no separate env vars or main.py setup. The canonical `bootstrap.py` in the "Python app-bootstrap: canonical bootstrap.py" section already includes:

- `LoggingInstrumentor().instrument(set_logging_format=False)` — injects `otelTraceID`, `otelSpanID`, `otelServiceName`, `otelTraceSampled` onto every `LogRecord`.
- `_CloudTraceJSONFormatter` — a `jsonlogger.JsonFormatter` subclass that maps `otelTraceID` → `logging.googleapis.com/trace` and `otelSpanID` → `logging.googleapis.com/spanId` on the emitted JSON entry.
- A `StreamHandler` with that formatter installed as the root handler.

Any `main.py` that does `import bootstrap  # noqa: F401` as its first import gets full log-trace correlation for free — no code changes in the app body beyond that import line.

Do NOT flip `OTEL_LOGS_EXPORTER=otlp`. Logs stay stdout → fluent-bit → Cloud Logging; correlation works because the JSON entry carries `logging.googleapis.com/trace`. OTLP logs adds an extra hop with no benefit for this outcome.

**Node.js / Next.js:** handled by the console-wrap + root-span-tracker in `instrumentation.node.ts` — see "Node.js app-bootstrap" section for the full canonical block. Wraps global `console.*` methods to emit JSON with `logging.googleapis.com/trace` and `logging.googleapis.com/spanId` (root span ID, not leaf). No new logger dep, no touches to existing `console.log` call sites.

**Verification:** after deploying, trigger a real request, open the trace in Cloud Trace, click "View logs" on the top-level HTTP span (Python: the root FastAPI span; Node: the root `GET /...` span). The Log Explorer filter should return the log lines emitted during that request. If zero results, either (a) the specific span had no log calls in its execution — try a code path known to log, or (b) the JSON entries aren't reaching Cloud Logging with the trace field — `kubectl exec <pod> -- ls /app` and check pod logs for JSON output with `logging.googleapis.com/trace`.

Reminder on the button's design: Cloud Trace's "View logs" button filters by BOTH `trace=` AND `spanId=`. Clicking on a leaf/child span only returns logs emitted while THAT specific span was active. To see all logs for a whole trace regardless of which span was active, either click the root span (works with the Node root-span-tracker pattern above), or open Log Explorer directly with `trace="projects/<project>/traces/<trace_id>"` and no spanId filter.

## Error Handling

For important spans:

- record exceptions
- mark span status as error
- always end spans in `finally`

## Environment And Helm

If the app uses Helm:

- wire OTEL env vars through Helm values
- keep dev/prod differences in values or deployment env
- do not bake environment-specific endpoints into app code

This should work in dev or prod GKE as long as the cluster has the shared OTEL platform and the app reads endpoint config from env/Helm.

For local development:

- prefer env overrides instead of code changes
- if no collector is available locally, use a console exporter only for local debugging
- do not leave local-only exporters enabled in committed production code

## Verification

If the pre-flight landed on State C, verification is: report the classification and stop. Do not "verify by pushing to dev" — the user already verified. Do not describe next steps that redo work.

If you made changes (State A or B):

1. `helm template ./helm` diff shows only the changes you intended
2. push to dev, watch pipeline
3. `kubectl -n <ns> get pod -l app=<app> -o yaml | grep -A2 initContainers` — init container present (operator-injected mode)
4. `kubectl -n <ns> exec deploy/<app> -- env | grep OTEL_` — CR env vars present (operator-injected mode) or app-bootstrap env block present
5. trigger a real app flow
6. confirm a trace appears in Google Trace Explorer under the app's `service.name`
7. confirm frontend-to-backend continuity if the app has both
8. confirm important manual spans exist
9. confirm no duplicate tracer providers or duplicate spans were introduced

## Deliverable Expectations

When applying this prompt to a project, the agent should:

- run the pre-flight classification and report the result before making any change
- **"no changes needed" is a valid outcome** when the pre-flight lands on State C — report and stop, do not manufacture cosmetic edits to justify running the prompt
- for State A/B, implement only what the classification identified as missing
- for State A specifically, the deliverable MUST include chart wiring, dependency addition, manual spans on high-value boundaries, AND async-queue `traceparent` propagation — in the same session. A chart-only diff is not a valid State A deliverable; see Implementation Pattern step 4.
- update Helm/env wiring only when the rendered YAML must change
- run `helm template` before/after any chart edit and diff; revert any change that produces byte-identical rendered output
- verify the result on the running pod, not just describe next steps
- before declaring done, grep every span attribute you added and confirm none carry PII (email addresses, phone numbers, Slack IDs, tokens, payloads, or any field under a `pii_*` key). Per-item loops MUST use `app.<thing>_index`, not the identifier. See "PII in span attributes" in Span Design.
