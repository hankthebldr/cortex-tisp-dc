# Telemetry Setup - OpenTelemetry Tracing and Metrics

This guide explains how to add observability — **tracing** and **metrics** — to your app using OpenTelemetry.

## What is This About?

You want to know what's happening inside your app in production. Two complementary signals get you there:

- **Tracing** answers *"what happened in this one specific request?"* — useful when a user reports a bug or a slow page.
- **Metrics** answer *"how is the app doing in aggregate right now?"* — useful for dashboards, alerts, and capacity planning.

**Analogy:**
- A **trace** is the UPS tracking page for one specific package: every stop, every handoff, exactly what happened.
- A **metric** is the UPS daily delivery report: how many packages went out, how many got delayed, what the average delivery time was.

You want both. Tracing finds the needle; metrics tell you the haystack is on fire.

## Key Terms

### Shared

**OpenTelemetry (OTEL)**
- Open source standard for emitting both traces and metrics
- Works with any language, sends to any backend (Google, AWS, Datadog, etc.)

**OTLP (OpenTelemetry Protocol)**
- The wire format used to ship telemetry over the network
- Standard protocol — same shape for traces and metrics

**OTEL Collector**
- A separate service running in the GKE cluster (not your app)
- Receives traces AND metrics from every app
- Translates and forwards each signal to the right Google Cloud backend
- Your app pushes to it; it handles vendor authentication

**instrumentation.mjs (Node.js) / equivalent bootstrap**
- File that sets up OTEL when your app starts
- Configures where to send traces and metrics (from env vars)
- Loaded *before* your app code runs

### Tracing-specific

**Trace** — the complete journey of one request through your code.

**Span** — one step in that journey (e.g. "AI API call", "database query"). A trace is a tree of spans.

**Auto-Instrumentation** — OTEL automatically tracks common things (HTTP requests, database queries, outbound API calls). Zero code from you.

**Manual Spans** — custom spans YOU add for important business logic (e.g. "AI generation took 2.3s").

**Google Cloud Trace** — backend storage for trace data. View at `console.cloud.google.com/traces`.

### Metrics-specific

**Meter** — the object you use to create instruments. One meter per app, named after the service.

**Counter** — a number that only goes up. Used for things like "number of requests", "number of errors", "bytes processed".

**Histogram** — a distribution of values, not a single number. Used for latency, payload sizes — anything where the *spread* matters (p50, p95, p99). Always has a unit (`ms`, `s`, `By`).

**Gauge** — a "current value" measurement. Rare — usually a counter or histogram is the right choice.

**Attribute (a.k.a. label/dimension)** — a key/value tag on a measurement. Lets you slice the same metric by, e.g., `outcome=success` vs `outcome=error`. **Keep these low-cardinality** — every unique attribute combination is a separate stored time series.

**RED Method** — Rate, Errors, Duration. The three core instruments every request-handling endpoint should emit:
- **R**equests counter
- **E**rrors counter
- **D**uration histogram

**Google Managed Prometheus (GMP)** — backend storage for metrics. Fully-managed Prometheus that auto-scrapes (or, in our case, receives OTLP-translated metrics from the collector). View at `console.cloud.google.com/monitoring`.

**Cloud Monitoring** — Google's UI for querying GMP metrics, building dashboards, and configuring alerts. Same UI that shows GKE/GCE built-in metrics.

## How It All Connects

```
1. Your app starts up
   → instrumentation.mjs runs first
   → Sets up OTEL traces + metrics with config from Helm env vars

2. User makes a request
   → OTEL auto-instrumentation tracks HTTP, DB calls (spans)
   → Your manual spans track AI calls, business logic
   → Your metric instruments record: request count, duration, errors

3. App sends OTLP to the OTEL Collector
   → Collector is shared in the cluster (no GCP auth from your app)
   → Collector receives both traces and metrics on the same endpoint

4. Collector splits and forwards
   → Traces → Google Cloud Trace
   → Metrics → Google Managed Prometheus (GMP)
   → Collector handles vendor authentication centrally

5. You investigate
   → Cloud Monitoring → dashboards / alerts (the "how is it doing" view)
   → If you see an issue, drill into Cloud Trace for one specific failing request
```

**For the visual architecture diagram, see [DIAGRAMS.md - Section 7](DIAGRAMS.md#7-observability---opentelemetry-tracing).**

## Real Example: Trace + Metrics Together

A user clicks "Generate Report":

**Cloud Monitoring (metrics)** shows:
```
myapp.generate.requests       — 1,847 today (outcome: success=1,801, error=46)
myapp.generate.duration p95   — 3.4s (was 1.2s yesterday — alert fires)
myapp.generate.failures       — 46 today (was 5 yesterday — alert fires)
```

Now you know "generate is slow and failing more." That's the aggregate signal. To find out *why*, you pivot to Cloud Trace.

**Cloud Trace (one failing request)** shows:
```
[Trace: req-12345]                                       Total: 8.2s
│
├─ POST /api/generate                                    [auto]   8.2s
│  ├─ app.ai.generate                                    [manual] 7.8s
│  │  └─ OpenAI API call                                  [auto]   7.7s   ← slow!
│  └─ Response sent to user (status 500)
```

Now you know the AI provider is slow and timing out. Fix: add a timeout, or switch to a faster model.

**Without metrics:** you wouldn't notice the regression until users complained.
**Without traces:** you'd know something is slow but not where in the code.

## Why You Want This

- **Alerts that fire before users notice** — error-rate or p95-latency thresholds
- **Dashboards for "how is the app doing right now"** — without manually checking logs
- **Debug specific failures** — pivot from a metric anomaly to the exact request that broke
- **Capacity planning** — see real traffic patterns over time
- **Performance tuning** — find bottlenecks with real distribution data, not assumptions

## Do I Need Workload Identity (WIF)?

**No** — your app does NOT need WIF for either traces or metrics.

- Your app sends to the in-cluster OTEL Collector via an internal cluster URL (no auth)
- The Collector handles GCP authentication for both Cloud Trace and GMP
- You only need WIF if your app uses *other* GCP services (BigQuery, Cloud Storage, etc.)

## How to Add Telemetry to Your App

Two prompts in the `doc/` folder do the actual scaffolding. Give them to Claude (or follow them by hand) **in order**:

### Step 1 — Add tracing

Use [`Instrumentation_prompt.md`](./Instrumentation_prompt.md).

This wires:
- The OTEL SDK bootstrap (`instrumentation.mjs` for Node.js, equivalent for other languages)
- Auto-instrumentation for inbound HTTP and outbound calls
- Manual spans for important business logic (AI calls, DB writes, workflow steps)
- Frontend → backend trace propagation (W3C `tracecontext,baggage`)
- Helm env vars for the OTLP endpoint
- Verification: real trace appears in Google Trace Explorer

After this step, you can answer *"what happened in this one specific request?"*

### Step 2 — Add metrics

Use [`Metrics_prompt.md`](./Metrics_prompt.md).

This builds on the tracing bootstrap and adds:
- `PeriodicExportingMetricReader` + `OTLPMetricExporter` registered on the existing NodeSDK
- One meter per app, named after the service
- For each user-facing operation: **RED instruments** (`<service>.<op>.requests` counter, `<op>.duration` histogram in `ms`, `<op>.failures` counter)
- Standard semantic-convention `http.server.request.duration` so Google Cloud Application Monitoring auto-recognizes it
- One `record<Op>Metrics(outcome, ...attrs)` helper per operation, called from every success and error exit
- Cardinality discipline (safe attributes vs. dangerous attributes)
- Helm env vars (`OTEL_METRICS_EXPORTER`, etc.)
- Verification: metrics appear in Cloud Monitoring under GMP-converted names

After this step, you can answer *"how is the app doing in aggregate right now?"* and set up alerts on it.

### Step 3 — Alerting

Once metrics are flowing, apply [`Alerting_prompt.md`](./Alerting_prompt.md) to convert them into Cloud Monitoring `alert_policy` resources. Minimum per user-facing operation: error rate + p95 latency; add absence (via heartbeat counter) if the app has quiet periods. Alerts live in Terraform in `gcp-wwss-as-trust-module/<service>.tf`, not in the app repo.

## Common Gotchas

**Metric names look different in Cloud Monitoring than in your code.**
- Dots become underscores: `myapp.generate.requests` → `myapp_generate_requests`
- Counters get a `_total` suffix: `myapp_generate_requests_total`
- Histograms get `_bucket`, `_count`, `_sum` suffixes plus a unit suffix: `myapp_generate_duration_milliseconds_bucket`
- Search prefix in Metrics Explorer: `prometheus.googleapis.com/...`

**"Metrics not showing up" almost always means one of:**
- `OTEL_METRICS_EXPORTER` is set to `none` (the default in instrumentation.mjs — must flip to `otlp`)
- The OTLP endpoint isn't reachable from the pod (check `OTEL_EXPORTER_OTLP_ENDPOINT`)
- You added the instruments but never called `.add()` or `.record()` on them
- It's been less than ~1 minute since the first emit (collector flushes periodically)
- **Your PromQL filter is wrong.** In GMP the `job` label is `<namespace>/<OTEL_SERVICE_NAME>` — NOT `<namespace>/<deployment-name>`. If the deployment is `foo-deployment` and `OTEL_SERVICE_NAME=foo`, the filter is `{job="applications/foo"}`. Empty result looks identical to "metric not emitting" and derails debugging. Always query with no filter first, read the actual `job` value off a returned row.
- **(Node OTEL 2.x only) `http.server.request.duration` missing but custom metrics present** — you're missing `OTEL_SEMCONV_STABILITY_OPT_IN=http/dup`. `@opentelemetry/instrumentation-http` 0.55+ emits the stable HTTP metric name only when this env is set. The app-template chart sets it automatically in `app-bootstrap` mode; if you're on a hand-authored chart, add it to your deployment env.

**High-cardinality attributes will cost you money.** Never tag a metric with `user.id`, `session.id`, `request.id`, or anything else with an unbounded value set. Use traces for that.
