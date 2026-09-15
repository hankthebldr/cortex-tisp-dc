# Alerting Prompt

Use this prompt when adding alerts to an app that is **already emitting metrics** via [Metrics_prompt.md](./Metrics_prompt.md). Alerts query existing metrics; they do not stand alone.

Write the code. Do not stop at recommendations.

Keep the alert set small, signal-heavy, and re-validatable end-to-end.

## Goal

Convert a metric the app already emits into a **PromQL alert policy** in Google Cloud Monitoring, routed to **Slack** via a notification channel. The full path is:

```
OTEL SDK push → otel-agent → gateway → googlemanagedprometheus exporter
  → GMP storage → PromQL evaluation → Cloud Monitoring alert policy
  → notification channel → Slack
```

Current backend assumptions:

- metrics live in **Google Managed Prometheus (GMP)** (see Metrics_prompt.md)
- alerts are **Cloud Monitoring `alert_policy` resources** using `condition_prometheus_query_language`
- alerts deliver to **Slack** via the cluster-wide `cluster_alerts` notification channel (see "Notification Channel Pattern" below)
- alert policies live in **Terraform** in `gcp-wwss-as-trust-module/<service>.tf` or `<service>_alerts.tf`, NOT in the app repo
- no app should emit alerts directly to a vendor backend or define them in code

## Core Rules

1. Require metrics to already be in place (Metrics_prompt.md applied first). An alert without a working metric is dead config.
2. **First ask whether a new metric is needed.** Most alerts reuse an existing instrument. Only add a new metric when no existing series can carry the signal.
3. Define alert policies as Terraform in the deployment module — same file as the app's GCP service account, OR a sibling `<app>_alerts.tf` when the infra file is already crowded. One file per app keeps blast radius scoped.
4. Reference the Slack notification channel by `display_name` via a `data` source. Never embed channel IDs.
5. Use `condition_prometheus_query_language`, not the legacy `condition_threshold`. PromQL is the lingua franca of GMP.
6. Every alert policy includes a `documentation` block with: what's wrong, how to validate on demand, and pre-filtered links to Logs Explorer / Cloud Trace / Metrics Explorer for this specific service.
7. Set `auto_close` so stale incidents don't pile up. 1800s (30min) is a reasonable default.
8. Validate **every** new alert end-to-end with a triggering action and a recovery, before marking the work done. PromQL that looks right can still be wrong (label drift, rate vs gauge mistakes, evaluation window mismatch).

## Decision: Do I Need A New Metric?

| Situation | New metric? | What to do |
|---|---|---|
| Alert on errors of an operation already covered by RED instruments | No | Reuse `<service>_<op>_failures_total` |
| Alert on latency of an operation already covered by RED instruments | No | Reuse `<service>_<op>_duration_<unit>_bucket` with `histogram_quantile` |
| Alert on absence ("is the pipeline alive?") | Yes, usually | Add a **heartbeat counter** incremented on a timer (see "Heartbeat pattern" below). Reusing a user-traffic-driven metric will fire as soon as the app is idle. |
| Alert on saturation ("queue depth", "in-flight count") | Yes, usually | Add a gauge / UpDownCounter (no existing instrument carries point-in-time state) |
| Alert on resource utilization (CPU, memory) | No | Use the auto-emitted process/runtime metrics or GKE container metrics |

The default answer is "reuse." Only add new code when no existing series can carry the signal.

### Heartbeat pattern (for absence alerts)

A heartbeat is a counter incremented on a timer **solely** to produce a continuous OTLP export. Its existence is the signal — absence means the SDK → collector → GMP path is broken, regardless of what the app is doing.

Python (in `bootstrap.py` after the MeterProvider is set):

```python
import threading

_heartbeat = metrics.get_meter("<service>").create_counter(
    "<service>.heartbeat",
    description="Liveness signal incremented on a timer, for absence alerting.",
)

def _pulse():
    _heartbeat.add(1)
    t = threading.Timer(30.0, _pulse)
    t.daemon = True
    t.start()

_pulse()
```

Node/TypeScript (in `instrumentation.mjs`):

```js
const heartbeat = meter.createCounter('<service>.heartbeat', {
  description: 'Liveness signal incremented on a timer, for absence alerting.',
});
const heartbeatInterval = setInterval(() => heartbeat.add(1), 30_000);
heartbeatInterval.unref();
```

- Increment every 30s. The default OTLP push interval is 60s, so each export carries at least one fresh increment.
- Timer runs in the background — `daemon=True` (Python) / `unref()` (Node) so it doesn't block graceful shutdown.
- Ship **two** alerts on the heartbeat, not one:
  1. `absent_over_time(<service>_heartbeat_total[5m])` — fires when GMP receives no samples at all
  2. `rate(<service>_heartbeat_total[5m]) == 0` with `for 5m` — fires when GMP receives samples but the counter isn't climbing (reset, flat-line, multi-writer corruption)
- The two catch different failures. See "Pair every heartbeat with a rate=0 alert" below.

Why not reuse an existing metric? OTLP cumulative counters only export data points after their first measurement. A request counter with no traffic has no series at all — `absent_over_time` would fire constantly. The heartbeat sidesteps this by guaranteeing traffic to itself.

### Fork-safe heartbeat (Python only)

If the app uses **any fork-based scale model** (celery `--concurrency=N`, gunicorn `--workers=N`, uwsgi processes), gate the increment on the master PID. Otherwise every forked child inherits the counter, all children write to the same GMP series identifier (OTLP resource labels are pod-scoped — nothing distinguishes PIDs), and the cumulative value flaps between the master's real value and children's near-zero values. Observed on doc-generator-worker: 3139 → 1 → 3229 without any pod restart, invisible to `absent_over_time`.

```python
_INIT_PID = os.getpid()  # captured at import in the master, before fork

def _pulse():
    if os.getpid() == _INIT_PID:
        _heartbeat.add(1)
    t = threading.Timer(30.0, _pulse)
    t.daemon = True
    t.start()
```

Node's cluster module has the same issue — same gate on `cluster.isPrimary` if you're using it.

### Pair every heartbeat with a rate=0 alert

`absent_over_time` and `rate == 0` catch **different** failure modes:

| Failure | `absent_over_time` fires? | `rate == 0` fires? |
|---|---|---|
| Pod dead / OTLP pipeline broken | ✅ | ✅ (eventually — no samples at all) |
| Counter reset to 0, exporter healthy | ❌ (samples exist at value 0) | ✅ |
| Multi-writer corruption (fork bug) alternating high/low writes | ❌ | ✅ (rate over window collapses) |
| Exporter stuck sending same cumulative value forever | ❌ | ✅ |

Absence-only alerting is a common blind spot — it only checks "is data flowing" and misses "is the data meaningful." Always ship both. They cost nothing extra and cover complementary failures.

## Default Strategy

**Minimum per user-facing operation:** error ratio + p95 latency. If the app has quiet periods (background workers, cron jobs, low-traffic APIs), also add absence — which requires the heartbeat pattern above.

Beyond the minimum, layer additional alerts only when you have evidence a real failure needed them. Alert count is app-specific — a public API might warrant saturation + downstream-latency splits; an internal batch job may only need error + absence.

**Prefer ratio thresholds over absolute rate.** `rate(failures[5m]) > 0.1` fires wildly differently at different traffic volumes — at 1 req/s that's 10% errors, at 100 req/s it's 0.1%. Ratio normalizes: at 1% error rate the alert fires regardless of scale. Use absolute only when the operation is critical enough that any occurrence warrants attention (DLQ arrival, security-relevant failures).

| Alert type | Reuses metric? | PromQL idiom | Example |
|---|---|---|---|
| **Error ratio** (minimum, preferred) | Reuse `<op>_requests_total{outcome}` | `sum(rate({outcome="error"}[5m])) / sum(rate([5m])) > 0.01` | 1% for HTTP APIs; 5-10% for consumers hitting flaky external APIs |
| **Error rate (absolute)** | Reuse `<op>_failures_total` | `rate(...[5m]) > N` | Reserve for "any failure = investigate" (DLQ arrival, security) |
| **Latency p95** (minimum) | Reuse `<op>_duration_<unit>_bucket` | `histogram_quantile(0.95, sum by (le) (rate(..._bucket[5m]))) > N` | p95 latency > 2s |
| **Absence** (minimum if app has quiet periods) | New heartbeat counter | `absent_over_time(...[5m])` | `absent_over_time(heartbeat_total[5m])` |
| **Counter-reset / no-progress** (ship alongside every absence alert) | Reuse heartbeat counter | `rate(...[5m]) == 0` `for 5m` | `rate(heartbeat_total[5m]) == 0` — catches resets, flat-lines, fork corruption that `absent_over_time` misses |
| **Saturation** (added when you have a capacity limit) | New gauge / UpDownCounter | `metric > N` | `inflight_work > 100` |
| **GCP-native metric** (Pub/Sub backlog, DLQ, etc.) | GCP-emitted, no app code | `condition_threshold` with filter on `pubsub.googleapis.com/...` | See "GCP-native metrics" section below |

## Where Alerts Live

Alert policies are infra, not app code. They live in the deployment Terraform module:

```
gcp-wwss-as-trust-module/
  <service>.tf              ← SA + WI binding + alert policies (small apps)
  <service>_alerts.tf       ← alerts only, when infra already lives in a separate file
```

One file per service. This keeps:
- Alert blast radius scoped — a bad apply only affects one service
- App repo focused on app code, not infra
- Alerts under the same review/approval flow as service-account changes

The app repo's `doc/` can describe what alerts exist, but the source of truth is the `.tf` file.

## Notification Channel Pattern

Route all app alerts to the cluster-wide Slack channel via `notification_channels.tf`:

```hcl
data "google_monitoring_notification_channel" "cluster_alerts" {
  display_name = "${var.cluster_name}-alerts"
}
```

Reference from every alert policy in the module. All services in the cluster share the channel — filter/mute per-service in Slack via the alert's `display_name` prefix or `user_labels.service`.

Historical note: earlier apps used per-service channels (`<service>-alerts`). That pattern is deprecated; new alerts should use `cluster_alerts`. The Slack channel is created **once** out-of-band via Slack OAuth in the GCP Console. Terraform never creates it — always reference by `display_name`.

## Implementation Pattern

For each new alert:

1. **Pick the metric.** Walk the decision table above. If you need a new instrument (heartbeat, gauge), add it via Metrics_prompt.md first and confirm samples reach GMP before writing the alert. **For on-error-only counters** (`<op>_failures_total`), add an eager zero-increment at instrument creation (`counter.add(0)`) so the series exists in GMP even when the app is healthy — otherwise `terraform apply` fails with `PromQL metric(s) are invalid` because the counter has never fired.
2. **Write the PromQL in GMP first.** Cloud Monitoring → Metrics Explorer → PromQL editor. Confirm the query returns the expected series under normal and triggering conditions before locking it into an alert policy.
3. **Add the `google_monitoring_alert_policy` resource** to `gcp-wwss-as-trust-module/<service>.tf` (or `<service>_alerts.tf`). Required fields: `display_name`, `documentation`, `conditions.condition_prometheus_query_language`, `alert_strategy.auto_close`, `notification_channels`, `combiner = "OR"`, `severity`, `enabled`.
4. **Set `duration` to filter flaps.** 60s is the default; tune longer for noisier signals.
5. **Apply via the module's release process** — push to module repo main, tag a new version, `git push --follow-tags`, then bump the deployment repo's `main.tf` to that version on a `feature/...` branch, MR + apply.
6. **Validate end-to-end.** Trigger the condition, wait for Slack, then recover and wait for auto-close.

### Alert policy template

```hcl
resource "google_monitoring_alert_policy" "<service>_<short_name>" {
  project      = var.gcp_project
  display_name = "<service>: <what's wrong in plain language>"

  documentation {
    content   = <<-EOT
      **What:** <One sentence on what failed. Name the metric.>

      **Look here first** (pre-filtered for this service):
      - [Logs Explorer — errors from this pod](https://console.cloud.google.com/logs/query;query=resource.labels.container_name%3D%22<service>%22%20AND%20severity%3E%3DERROR?project=${var.gcp_project})
      - [Cloud Trace — recent traces](https://console.cloud.google.com/traces/list?project=${var.gcp_project}) — filter by service.name=<service>
      - [Metrics Explorer](https://console.cloud.google.com/monitoring/metrics-explorer?project=${var.gcp_project}) — PromQL: `<the query from below>`

      **Next action:** <one sentence pointing at the most likely root cause and the fastest way to confirm it>
    EOT
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "<short condition description>"
    condition_prometheus_query_language {
      query               = "<promql>"
      duration            = "60s"
      evaluation_interval = "60s"
      alert_rule          = "<CamelCaseRuleName>"
      rule_group          = "<ServiceCamelCase>"
    }
  }

  alert_strategy {
    auto_close = "1800s"
  }

  notification_channels = [data.google_monitoring_notification_channel.cluster_alerts.name]
  combiner              = "OR"

  user_labels = {
    service = "<service>"
    app     = "<parent-app-if-multi-workload>"
  }

  severity = "WARNING"
  enabled  = true
}
```

## GCP-native metrics (Pub/Sub backlog, DLQ, etc.)

Some signals are emitted by GCP directly to Cloud Monitoring, NOT by the app via OTEL. Common examples for our workloads:

| Signal | Metric | Notes |
|---|---|---|
| Pub/Sub subscription backlog | `pubsub.googleapis.com/subscription/num_undelivered_messages` | Gauge; alert with `ALIGN_MAX` and a threshold |
| Dead-letter forwarding | `pubsub.googleapis.com/subscription/dead_letter_message_count` | Cumulative counter on the parent subscription; alert with `ALIGN_DELTA` + `REDUCE_SUM` |
| Oldest un-ack'd message age | `pubsub.googleapis.com/subscription/oldest_unacked_message_age` | Gauge in seconds |
| GKE container restarts | `kubernetes.io/container/restart_count` | Cumulative; cluster-scoped alert usually |

These use `condition_threshold`, NOT `condition_prometheus_query_language`, because the metric is native to Cloud Monitoring rather than translated through GMP. Template:

```hcl
conditions {
  display_name = "backlog > 100 for 5m"
  condition_threshold {
    filter          = "metric.type=\"pubsub.googleapis.com/subscription/num_undelivered_messages\" AND resource.type=\"pubsub_subscription\" AND resource.label.subscription_id=\"<subscription-name>\""
    duration        = "300s"
    comparison      = "COMPARISON_GT"
    threshold_value = 100

    aggregations {
      alignment_period   = "60s"
      per_series_aligner = "ALIGN_MAX"
    }

    trigger {
      count = 1
    }
  }
}
```

Aggregation cheat sheet:

- **Gauges** (backlog, age): `per_series_aligner = ALIGN_MAX` (or `ALIGN_MEAN`); no reducer needed if you filter to a single series.
- **Cumulative counters** (DLQ arrivals, restart_count): `per_series_aligner = ALIGN_DELTA` (per-window increment) + `cross_series_reducer = REDUCE_SUM` (across subscriptions/pods).

For DLQ arrivals specifically, alert `> 0` — DLQ almost always means a permanent failure (bad payload, code bug) that no retry will fix.

## PromQL Cheat Sheet

For OTEL → GMP metric names: dots become underscores, counters get `_total` suffix, histograms get `_bucket`/`_sum`/`_count`. So `coach.generate.requests` (counter) → `coach_generate_requests_total` in PromQL.

| Pattern | Query | When the alert fires |
|---|---|---|
| Error rate > 0 | `rate(coach_generate_failures_total[5m]) > 0` | Any failure in the last 5 min |
| Error rate > N/min | `rate(coach_generate_failures_total[5m]) * 60 > 5` | More than 5 failures per minute |
| Error ratio > 1% | `sum(rate(coach_generate_failures_total[5m])) / sum(rate(coach_generate_requests_total[5m])) > 0.01` | Error ratio over 1% |
| Absence | `absent_over_time(coach_heartbeat_total[5m])` | No data points in last 5 min |
| No-progress (pair with absence) | `rate(coach_heartbeat_total[5m]) == 0` | Samples present but counter not climbing (reset, flat-line, fork corruption) |
| Latency p95 > 2s | `histogram_quantile(0.95, sum by (le) (rate(coach_generate_duration_milliseconds_bucket[5m]))) > 2000` | 95th percentile latency above 2s |
| Saturation | `coach_inflight_work > 100` | Gauge value above threshold |

`sum by (le)` is mandatory in `histogram_quantile` — without it, percentiles are computed per-series and mostly wrong.

## Validation

Every new alert is validated by:

1. **Confirm the metric is in GMP.** Metrics Explorer → search for `prometheus.googleapis.com/<metric_name>`. If it's not there, the alert can't fire.
2. **Run the PromQL in Metrics Explorer.** Switch to PromQL mode. Confirm it returns expected data under normal load. Trigger the condition (curl, scale, etc.) and confirm the query crosses the threshold.
3. **Trigger the alert end-to-end.** Run the validation command / test script. Expected Slack delivery: ~ `evaluation_interval + duration + Cloud Monitoring poll lag` ≈ 2-3 min.
4. **Verify auto-close.** Stop triggering. Confirm Cloud Monitoring → Alerting shows the incident closes within the `auto_close` window.
5. **Check the Slack message.** Title, description from `documentation.content`, and link back to the incident must all render. Broken markdown in the doc block silently degrades the message.

Skip none of these steps. PromQL syntax is forgiving in ways that produce silent zeroes.

## Anti-patterns

- **Alerting on a metric that doesn't exist yet.** Cloud Monitoring rejects `terraform apply` with `"PromQL metric(s) are invalid: <name>"` — the alert policy never gets created. Always confirm the metric in Metrics Explorer first. This bites hardest on **on-error-only counters** like `<op>_failures_total`: they only emit when an error occurs, so a healthy app has no series in GMP for that name and the alert can't bind. Fix by eagerly zero-incrementing at instrument creation time — see Metrics_prompt.md "Custom failure counter" section. Same trap applies to heartbeat counters if the pod hasn't rolled to the new image before you try to apply the alert.
- **Alerting on `<metric>` instead of `rate(<metric>[5m])`.** Cumulative counters only ever go up — a threshold on the raw value fires once and stays firing.
- **`histogram_quantile` without `sum by (le)`.** Returns nonsense most of the time. Always aggregate to `(le)` before the quantile.
- **Reusing a user-traffic metric for absence detection.** Silent during idle hours. Use a heartbeat.
- **Shipping only `absent_over_time` on the heartbeat.** Blind to counter resets and multi-writer corruption (the series is present, just wrong). Always pair with `rate(...[5m]) == 0`.
- **Duration too short.** Fires on every transient blip. Start at 60s, tune up for noisier signals.
- **No `auto_close`.** Stale incidents accumulate until the channel becomes background noise.
- **Channel ID hardcoded** instead of `data.google_monitoring_notification_channel` by display_name. Re-creating the channel breaks every reference.
- **Defining alerts in the app repo** instead of the deployment module. The app repo doesn't have the GCP credentials or apply pipeline; the alert never gets created.
- **Per-service Slack channels for new apps.** Deprecated pattern; use `cluster_alerts`.

## Deliverable Expectations

When applying this prompt to a project, the agent should:

- confirm metrics are already in place (Metrics_prompt.md applied)
- walk the "Do I Need A New Metric?" table for each requested alert and surface the answer before writing code
- if a new instrument is needed (typically only heartbeat for absence, or a gauge for saturation), add it via Metrics_prompt.md, verify it lands in GMP, THEN write the alert
- write the alert policy in `gcp-wwss-as-trust-module/<service>.tf` (or `<service>_alerts.tf`), following the template
- validate end-to-end (trigger + recover) before marking work done
