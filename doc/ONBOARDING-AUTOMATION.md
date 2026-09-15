# Onboarding Automation

Automates the two external-infra steps (DNS + GCP service account) by directly committing to the module repo and opening one MR per environment in the deployment repos.

For the manual fallback when automation fails or you need to inspect the generated terraform, see [DNS-SETUP.md](DNS-SETUP.md) and [SERVICE-ACCOUNT-SETUP.md](SERVICE-ACCOUNT-SETUP.md).

## What it does

Behavior depends on which branch you trigger the pipeline from:

### `RUN_ONBOARD=true` on `dev` branch
1. **Direct commit** to [`gcp-wwss-as-trust-module`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module): writes `<app>.tf` (SA + Workload Identity + IAM grants) and pushes to `main`
2. **Tags the module** at the next patch version (e.g., `0.3.75`); the module repo's existing CI publishes the new package to GitLab's Terraform Module Registry
3. **Opens an MR** in [`gcp-wwss-as-trust-dev-deployment`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment): bumps module version + appends `<app>.tsdev.paloaltonetworks.com.` to `ingress_app_domain_names`

### `RUN_ONBOARD=true` on `main` branch
1. Skips module work (already done from the dev run)
2. **Opens an MR** in [`gcp-wwss-as-trust-prod-deployment`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-prod-deployment): bumps module version + appends `<app>.ts.paloaltonetworks.com.`

Module repo writes are direct-to-`main` (no MR) because the module repo is not branch-protected and the generated `.tf` is mechanical — the meaningful review happens at the deployment-repo MR where apply actually runs.

## Source of truth: `helm/values.yaml`

**Your app's `helm/values.yaml` is the canonical source for what `<app>.tf` should contain.** The file in the module repo is a generated artifact — every pipeline run regenerates it from `helm/values.yaml` and replaces the existing one if there's any difference.

**Implication: do NOT hand-edit `<app>.tf` in the [`gcp-wwss-as-trust-module`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module) repo.** Any manual change there will be silently overwritten on the next onboarding pipeline run. To change the SA's IAM, edit `onboarding.iam_roles` in your app's `helm/values.yaml` and re-run the pipeline.

The mechanics: the script writes the freshly-generated content to a temp file (`<app>.tf.new`), compares it against the existing `<app>.tf`, and if they differ, `mv`s the temp file over the existing one. Same-filesystem `mv` is atomic — the file is either fully old or fully new on disk, never half-written.

If you need to add something to a generated `.tf` that the template doesn't support (e.g., a custom secret, a non-IAM resource), either extend the onboarding-ci template or accept that resource lives somewhere outside the module's per-app file.

## Developer flow

### 1. Declare what you need in `helm/values.yaml`

```yaml
k8s:
  app_name: "my-app"            # drives all derived names + URLs

onboarding:
  iam_roles:
    - roles/bigquery.dataViewer
    - roles/bigquery.jobUser
  iam_target_project: ""              # default: grants on app's own project (wwss-as-trust-dev / -prod)
  enable_alerts: false                # opt-in: generate the four standard alert policies for this app
```

If your app doesn't need any GCP access beyond the bare SA + Workload Identity binding, leave `iam_roles` empty or omit the whole `onboarding` block.

`enable_alerts` is opt-in because the underlying metrics must exist in GMP at apply time — see [Alert policies](#alert-policies) below.

### 2. Onboard dev

1. Push your changes to the `dev` branch (normal pipeline runs — onboard job stays hidden)
2. CI/CD → Pipelines → **Run pipeline** → Branch: `dev`, Variable: `RUN_ONBOARD` = `true`, click Run
3. Pipeline commits `<app>.tf` + tags the module + opens one MR in the dev deployment repo
4. Reviewer merges the dev deployment MR
5. Applier clicks Apply in the dev deployment repo's CI

### 3. Onboard prod (when ready)

1. Merge your `dev` branch to `main`
2. CI/CD → Pipelines → **Run pipeline** → Branch: `main`, Variable: `RUN_ONBOARD` = `true`, click Run
3. Pipeline opens one MR in the prod deployment repo (module work was already done)
4. Reviewer merges, applier clicks Apply

## Role allowlist

The pipeline refuses to grant any role not in `onboarding-ci/allowed_roles.txt`. Default allowlist:

- `roles/bigquery.dataViewer`, `roles/bigquery.dataEditor`, `roles/bigquery.jobUser`
- `roles/storage.objectViewer`, `roles/storage.objectAdmin`
- `roles/datastore.user`
- `roles/pubsub.publisher`, `roles/pubsub.subscriber`
- `roles/secretmanager.secretAccessor`
- `roles/aiplatform.user`
- `roles/cloudsql.client`
- `roles/redis.editor`
- `roles/monitoring.metricWriter`

To grant a role outside the allowlist (e.g., `roles/storage.admin` or anything matching `Admin` / `iam.*`), set `ALLOW_ELEVATED=true` as a pipeline variable in addition to `RUN_ONBOARD=true`. The deployment MR reviewer should treat this as a flag for extra scrutiny.

To add a role to the standard allowlist, edit [`onboarding-ci/allowed_roles.txt`](https://code.pan.run/reference-architectures/onboarding-ci/-/blob/main/allowed_roles.txt) and commit to `main`. Effective on the next pipeline run.

## Alert policies

Setting `onboarding.enable_alerts: true` appends four `google_monitoring_alert_policy` resources to `<app>.tf`:

- **tRPC error rate elevated** — `rate(<app>_trpc_request_duration_seconds_count{outcome="error"}[5m]) > 0.1`
- **heartbeat absent** — `absent_over_time(<app>_heartbeat_total[5m])`
- **tRPC p95 > 10s** — `histogram_quantile(0.95, ... <app>_trpc_request_duration_seconds_bucket ...)`
- **in-flight tRPC > 50** — `sum(<app>_trpc_inflight) > 50`

All four assume metrics named with the `<app_name_underscore>_*` prefix, emitted via the patterns in [Metrics_prompt.md](Metrics_prompt.md) and [Instrumentation_prompt.md](Instrumentation_prompt.md). They route to the cluster-wide notification channel defined in the module repo's `notification_channels.tf`.

**Why opt-in:** GCP Monitoring validates that the referenced metric exists in GMP at alert-create time. For a freshly onboarded app with no traffic, the three histogram-based alerts fail terraform apply with `Error 400: invalid PromQL metric`. Enable only after the app has been deployed AND has emitted at least one of each metric. (The heartbeat alert uses `absent_over_time` and creates cleanly from day one — but it's grouped with the others for an all-or-nothing toggle.)

If your app diverges from the standard `<app_name_underscore>_*` metric contract, leave `enable_alerts: false` and write your own alert policies outside the onboarding-managed `<app>.tf`.

## Idempotency

The pipeline is safe to re-run. Three scenarios:

### Identical re-run (same `app_name`, same `iam_roles`)
- Module: regenerates `<app>.tf` from current inputs, compares to existing content. If identical, skips commit + tag.
- Deployment repo: hcledit no-ops version bump (already at target); domain append is skipped (grep matches existing entry); MR creation is skipped because there's nothing to commit.
- Net effect: zero MRs opened, no infra changes. Safe.

### Add a new IAM role to an existing app
- User adds `roles/firestore.user` to `helm/values.yaml` and re-triggers.
- Module: regenerates the `.tf`, diff shows the new IAM block being added. Commits the update, tags new version (e.g., `0.3.76`).
- Deployment repo: version bump from `0.3.75` to `0.3.76`. Domain already present, no DNS change. MR is opened for the version bump.
- Net effect: 1 module commit + 1 tag + 1 deployment MR. The new role is provisioned on apply.

Same flow applies for flipping `enable_alerts` from `false` to `true` (or vice-versa) — the diff is the four alert resource blocks appearing or disappearing.

### Rename (`app_name` changed from `my-app1` to `my-app2`)
- The pipeline treats this as **a new app**, not a rename. It will create `my-app2.tf` and add `my-app2.tsdev...`, but **leaves `my-app1` infra in place**.
- To remove the old `my-app1` infra, run the offboarding pipeline (see below) with `OFFBOARD_APP_NAME=my-app1`.

### Re-running with an open MR
- The branch name is deterministic: `feature/onboard-<app>` (or `feature/offboard-<app>`). One name per app, reused across runs.
- If a prior MR is still open: the pipeline **force-pushes the branch and reuses the existing MR**. The MR's "Commits" tab updates to the new commit; the "Changes" tab shows the new diff. No duplicate MR is opened.
- Use case: developer edits `helm/values.yaml` (adds a role, changes target project), re-runs the pipeline, the same MR updates in place. Reviewer sees the latest state without juggling MRs.
- The force-push uses `--force-with-lease` tied to the remote branch's current SHA: if a reviewer pushed a fix-up commit between the pipeline's fetch and push, the lease fails and the push is rejected (no data loss). Re-run after pulling the reviewer's change locally.
- If the prior MR was merged: GitLab auto-deletes the branch (`remove_source_branch:true` in the MR payload), so the next run sees no remote branch and does a normal first push + opens a new MR.

## Troubleshooting

### Pipeline fails with "Role 'X' is not in allowed_roles.txt"
Either remove the role from `onboarding.iam_roles` in `helm/values.yaml`, or set `ALLOW_ELEVATED=true` on the pipeline run.

### Pipeline fails with "Onboarding must run on 'dev' or 'main' branch"
The Branch dropdown in the Run pipeline UI was set to a feature branch. Switch to `dev` or `main`.

### Pipeline fails with "Failed to push module tag after N attempts"
Two onboarding pipelines tagged the module concurrently. Re-run the pipeline — the next attempt will pick the next free version.

### Pipeline fails on prod run with "<app>.tf not found in module repo"
You triggered prod onboarding without doing dev first. Run on the `dev` branch first to do module setup.

### Pipeline fails on prod run with "Module is out of sync with current onboarding inputs"
You changed `iam_roles` or `iam_target_project` in `helm/values.yaml` but haven't re-run dev onboarding to update the module. The job log shows the diff (what the module currently has vs. what your inputs now ask for). Re-run on `dev` branch first to push the updated module + new tag, then re-run on `main`.

### Manual fallback
If the pipeline is broken, the original manual flow still works — see [DNS-SETUP.md](DNS-SETUP.md) and [SERVICE-ACCOUNT-SETUP.md](SERVICE-ACCOUNT-SETUP.md).

## Offboarding (removing an app)

Inverse of onboard. Deletes the SA + IAM from the module and removes the DNS entry from the deployment repo. After apply, terraform destroys the SA, all IAM bindings referencing it, and the DNS A record.

### Trigger

CI/CD → Pipelines → **Run pipeline** → Branch: `dev` (or `main` for prod), Variable: `RUN_OFFBOARD=true` → Run.

App name defaults to `k8s.app_name` from `helm/values.yaml`. To offboard a *different* name (typically after a rename — helm now has the new name, but you want to clean up the old name's infra), also set `OFFBOARD_APP_NAME=old-name`.

### Behavior

- **Dev branch:** removes `<app>.tf` from module repo (direct commit + tag bump), opens MR in dev deployment repo to bump module version + remove DNS entry.
- **Main branch:** opens MR in prod deployment repo (module work was already done in the dev offboard).
- Idempotent: if the module `.tf` is already gone, skips module step. If the domain is already absent, skips DNS removal. If both are no-ops, no MR is opened.

### Warnings

The MR description warns that applying will destroy the SA + IAM + DNS. **If the app is still deployed, applying will break it** (the pod loses GCP access immediately, the URL stops resolving). Decommission the app first (helm uninstall, gitlab project removal) before merging the offboard MR.

## Architecture

```
code.pan.run/reference-architectures/
  app-template/             ← this repo, includes the onboard pipeline
    .gitlab-ci.yml          ← include: project: onboarding-ci file: onboard.gitlab-ci.yml
    helm/values.yaml        ← onboarding: block declares what's needed

  onboarding-ci/            ← shared CI template, owns the automation logic
    onboard.gitlab-ci.yml
    onboard.sh
    templates/sa.tf.tmpl
    templates/iam_member.tf.tmpl
    templates/alerts.tf.tmpl
    allowed_roles.txt

gitlab.com/panw-gse/ts/
  gcp-wwss-as-trust-module/             ← direct commit + tag (dev runs only)
  gcp-wwss-as-trust-dev-deployment/     ← MR on dev runs (version bump + DNS)
  gcp-wwss-as-trust-prod-deployment/    ← MR on main runs (version bump + DNS)
```

The pipeline runs in the **app's** CI context (its runner, its variables) but the **logic** lives in `onboarding-ci`. The infra repos live on a different GitLab instance (`gitlab.com`) than the app repos (`code.pan.run`); the pipeline uses Project Access Tokens (stored as group CI/CD variables on code.pan.run) to clone, push, and tag.

## Required group-level CI/CD variables

Set on the parent group `reference-architectures` on code.pan.run, all Protected + Masked:

| Variable | Source |
|---|---|
| `ONBOARD_TOKEN_MODULE` | Project Access Token on `gcp-wwss-as-trust-module`, role `Developer`, scopes `api,write_repository` |
| `ONBOARD_TOKEN_DEV_DEPLOY` | Same on `gcp-wwss-as-trust-dev-deployment` |
| `ONBOARD_TOKEN_PROD_DEPLOY` | Same on `gcp-wwss-as-trust-prod-deployment` |

Tokens expire (GitLab requires it, max 1 year). Rotation = create new token in the same project, replace the variable value, delete the old token. No app-side changes needed.

### `ONBOARDING_CI_REF` (NOT Protected, NOT Masked)

Also required at the group level, but with different settings:

| Variable | Value | Settings |
|---|---|---|
| `ONBOARDING_CI_REF` | `main` | Protect: **NO** · Mask: **NO** · Type: Variable |

What it does: both the `include:` in your app's `.gitlab-ci.yml` AND the runtime `git clone` inside the onboarding job reference `$ONBOARDING_CI_REF` to decide which branch of `onboarding-ci` to pull. Having it at the group level means every app inherits the same default (`main`) automatically — no per-project setup, no scaffolded-app regression.

To test against an unreleased `onboarding-ci` branch (e.g., during development of the pipeline itself), manually trigger a pipeline via **CI/CD → Pipelines → Run pipeline** and add `ONBOARDING_CI_REF=dev` as a pipeline variable. The UI value wins over the group default for that one pipeline.

**Why NOT Protected:** Protected variables are only injected on Protected branches. QA pipelines (which override `ONBOARDING_CI_REF` to test new pipeline code) often run on unprotected branches, where the value would arrive as an empty string and the include would fail with `reference '' does not exist!`.

**Why NOT Masked:** masking is for secrets. This is just a branch name.

**Why the variable must be group/project-level, NOT in the app's own `.gitlab-ci.yml`:** GitLab CI/CD variables live in two timelines — *parse time* (when GitLab merges YAML and resolves `include:`) vs *job runtime* (when shell scripts execute). The file's own `variables:` block is available only at runtime, so it can't drive `include: ref:`. Only project-level, group-level, instance-level, and "Run pipeline" UI variables exist at parse time. So a file-level default would silently fail on push-triggered pipelines while appearing to work on manual ones.
