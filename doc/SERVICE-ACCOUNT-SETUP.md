# Service Account Setup

How to set up a GCP service account for your app so it can access GCP services (BigQuery, Cloud Storage, Firestore, Pub/Sub, Vertex AI, etc.).

> **Most apps should use the automated onboarding pipeline instead of following this manually.** See [ONBOARDING-AUTOMATION.md](ONBOARDING-AUTOMATION.md). This doc is the reference for the underlying mechanics and the fallback when automation breaks.

For BigQuery-specific permissions and code examples, see [BIGQUERY-SETUP.md](BIGQUERY-SETUP.md).

## Overview

Every app that needs to call GCP APIs needs a GCP service account. This template uses **Workload Identity** so your pod authenticates as that service account automatically — no key files to manage.

### The three pieces (all required)

1. **GCP service account** — `my-app@wwss-as-trust-dev.iam.gserviceaccount.com` (created in the Terraform module)
2. **Kubernetes service account with annotation** — links the K8s SA to the GCP SA (the template handles this automatically via `helm/templates/sa.yaml`)
3. **Workload Identity binding** — grants the K8s SA permission to impersonate the GCP SA (created in the Terraform module)

If any one is missing, your pod will get `403 PERMISSION_DENIED` when calling GCP APIs.

### Naming convention

All three derive from `app_name` in `helm/values.yaml`:

| Resource | Value |
|---|---|
| `app_name` (Helm) | `my-app` |
| K8s service account | `my-app-sa` |
| GCP service account email | `my-app@wwss-as-trust-dev.iam.gserviceaccount.com` |
| Workload Identity member | `serviceAccount:wwss-as-trust-dev.svc.id.goog[applications/my-app-sa]` |

## The Two Setup Paths

**Path A — Terraform module (recommended).** Add a `.tf` file for your app to [`gcp-wwss-as-trust-module`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module). Creates the GCP SA, the Workload Identity binding, and any IAM permissions.

**Path B — Manual via gcloud.** Use only if you can't get access to the Terraform module repo. Resources won't be managed by Terraform — a future `terraform apply` could overwrite them.

## Path A: Terraform Module (Recommended)

### Step 1: Clone the module repo

Repo: [gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module)

```bash
git clone https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module.git
cd gcp-wwss-as-trust-module
```

The module repo is NOT branch-protected — you push directly to `main`.

### Step 2: Create `<your-app>.tf`

Create a new file in the repo root. Replace `my-app` with your app name everywhere (must match `app_name` in `helm/values.yaml`):

```terraform
# my-app.tf

resource "google_service_account" "my_app" {
  account_id   = "my-app"
  display_name = "My App Service Account"
  description  = "My App Service Account"
  project      = var.gcp_project
}

resource "google_service_account_iam_binding" "my_app_wiu_binding" {
  service_account_id = google_service_account.my_app.name
  role               = "roles/iam.workloadIdentityUser"
  members = [
    "serviceAccount:${var.gcp_project}.svc.id.goog[applications/my-app-sa]"
  ]
}

# Add IAM permissions for whatever GCP services your app needs.
# Example: BigQuery read + run queries (granted on the app's own project)
resource "google_project_iam_member" "my_app_bq_data_viewer" {
  project = var.gcp_project  # resolves to wwss-as-trust-dev / wwss-as-trust-prod
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.my_app.email}"
}

resource "google_project_iam_member" "my_app_bq_job_user" {
  project = var.gcp_project
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.my_app.email}"
}
```

**⚠️ IAM safety rules — read before adding more roles:**

- ✅ Use `google_project_iam_member` for granting your SA project-level roles. Additive, safe.
- ✅ Use `google_service_account_iam_binding` only on SAs you own (like the Workload Identity binding above).
- ❌ **NEVER use `google_project_iam_binding` for project roles** — it's authoritative and would wipe every other app's access to that role.

### Step 3: Commit and tag a new module version

```bash
git add my-app.tf
git commit -m "Add my-app service account"

# Bump the patch version (check existing tags first with: git tag --sort=-v:refname | head -5)
git tag 0.3.75
git push --follow-tags
```

### Step 4: Bump the module version in the deployment repo

The module is consumed by the dev deployment repo: [gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment). Update the `version` field there:

```bash
git clone https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment.git
cd gcp-wwss-as-trust-dev-deployment
git checkout -b feature/bump-module-for-my-app
```

Edit `main.tf`:

```terraform
module "gcp-wwss-as-module" {
  source  = "gitlab.com/panw-gse/gcp-wwss-as-trust-module/google"
  version = "0.3.75"  # bumped from previous version
  # ... rest unchanged
}
```

**⚠️ The `feature/...` prefix is required** — only branches matching that pattern get the protected CI/CD variables needed for the pipeline.

Commit, push, open an MR, get it reviewed and merged.

### Step 5: Run `terraform apply`

After merge, someone with access has to run it manually:

```bash
cd gcp-wwss-as-trust-dev-deployment
git checkout main
git pull
terraform init -upgrade
terraform apply
```

Ping `#engineering-productivity` or your team lead if you don't have apply access.

### Step 6: Repeat for prod

The `.tf` file was already added to the module (step 2-3). For prod you only need to bump the module version in [`gcp-wwss-as-trust-prod-deployment`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-prod-deployment) → `main.tf` and run terraform apply against that repo. Only do this once you've verified the app works in dev.

## Path B: Manual via gcloud (Alternative)

### Step 1: Create the GCP service account

```bash
# Dev
gcloud iam service-accounts create my-app \
  --project=wwss-as-trust-dev \
  --display-name="My App Service Account"

# Prod
gcloud iam service-accounts create my-app \
  --project=wwss-as-trust-prod \
  --display-name="My App Service Account"
```

### Step 2: Bind the Kubernetes SA to the GCP SA (Workload Identity)

```bash
# Dev
gcloud iam service-accounts add-iam-policy-binding \
  my-app@wwss-as-trust-dev.iam.gserviceaccount.com \
  --project=wwss-as-trust-dev \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:wwss-as-trust-dev.svc.id.goog[applications/my-app-sa]"

# Prod
gcloud iam service-accounts add-iam-policy-binding \
  my-app@wwss-as-trust-prod.iam.gserviceaccount.com \
  --project=wwss-as-trust-prod \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:wwss-as-trust-prod.svc.id.goog[applications/my-app-sa]"
```

### Step 3: Grant IAM roles for whatever your app needs

Example for BigQuery (grant on the app's own project):

```bash
gcloud projects add-iam-policy-binding wwss-as-trust-dev \
  --member="serviceAccount:my-app@wwss-as-trust-dev.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"
```

## Common Roles by GCP Service

| Service | Common roles |
|---|---|
| BigQuery | `roles/bigquery.dataViewer`, `roles/bigquery.jobUser`, `roles/bigquery.dataEditor` |
| Cloud Storage | `roles/storage.objectViewer`, `roles/storage.objectAdmin` |
| Firestore / Datastore | `roles/datastore.user` |
| Pub/Sub | `roles/pubsub.publisher`, `roles/pubsub.subscriber` |
| Secret Manager | `roles/secretmanager.secretAccessor` |
| Vertex AI | `roles/aiplatform.user` |
| Cloud SQL (client) | `roles/cloudsql.client` |
| Cloud Memorystore | `roles/redis.editor` |

For a complete list see [the IAM roles reference](https://cloud.google.com/iam/docs/understanding-roles).

## Verification

After setup, verify all three pieces.

### 1. GCP service account exists

```bash
gcloud iam service-accounts describe \
  my-app@wwss-as-trust-dev.iam.gserviceaccount.com \
  --project=wwss-as-trust-dev
```

### 2. Workload Identity binding is correct

```bash
gcloud iam service-accounts get-iam-policy \
  my-app@wwss-as-trust-dev.iam.gserviceaccount.com \
  --project=wwss-as-trust-dev
```

Expected output includes:

```yaml
bindings:
- members:
  - serviceAccount:wwss-as-trust-dev.svc.id.goog[applications/my-app-sa]
  role: roles/iam.workloadIdentityUser
```

### 3. K8s service account has the annotation

After deploying your app:

```bash
kubectl get sa my-app-sa -n applications -o yaml
```

Expected annotation:

```yaml
metadata:
  annotations:
    iam.gke.io/gcp-service-account: my-app@wwss-as-trust-dev.iam.gserviceaccount.com
```

Set automatically by `helm/templates/sa.yaml`.

### 4. End-to-end test from inside the pod

```bash
kubectl exec -n applications -it deploy/my-app-deployment -- gcloud auth list
```

Should show the GCP SA email as the active account.

## Troubleshooting

### `403 PERMISSION_DENIED` calling a GCP API

One of the three pieces is missing or misconfigured.

- Check the GCP SA exists (verification step 1).
- Check the Workload Identity binding (verification step 2). The K8s SA name format is **literal**: `{project}.svc.id.goog[{namespace}/{sa-name}]`.
- Check the K8s SA annotation (verification step 3).
- Check the IAM role is actually granted on the right project:
  ```bash
  gcloud projects get-iam-policy wwss-as-trust-dev \
    --flatten="bindings[].members" \
    --filter="bindings.members:my-app@wwss-as-trust-dev.iam.gserviceaccount.com"
  ```

### `Could not find workload identity pool`

The namespace in the binding doesn't match where your pod actually runs. Apps in this template run in the `applications` namespace, so the binding must be:

```
serviceAccount:{project}.svc.id.goog[applications/my-app-sa]
```

Not `[default/my-app-sa]` or any other namespace.

### App works in dev but fails in prod (or vice versa)

- The SA only exists in one project. Repeat the setup for the other project (dev SAs live in `wwss-as-trust-dev`, prod SAs in `wwss-as-trust-prod`).
- The IAM role grant is on a different project than where the resource actually lives. The role must be granted on the project that owns the resource.

### Permission was granted but pod still fails

- GCP IAM changes can take 1-2 minutes to propagate.
- Restart the deployment:
  ```bash
  kubectl rollout restart deploy/my-app-deployment -n applications
  ```

## Related Docs

- [ONBOARDING-AUTOMATION.md](ONBOARDING-AUTOMATION.md)
- [BIGQUERY-SETUP.md](BIGQUERY-SETUP.md)
- [DNS-SETUP.md](DNS-SETUP.md)
- [GETTING-STARTED.md](GETTING-STARTED.md)
