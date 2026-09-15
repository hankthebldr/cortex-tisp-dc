# App Template

A template repository for building and deploying applications to GKE clusters with GitLab CI/CD.

**Features:**
- ✅ **SSO Authentication** - Built-in corporate SSO (can be disabled if needed)
- ✅ **GitLab CI/CD** - Automated Docker builds and Helm deployments  
- ✅ **Multi-environment** - Separate dev and prod configurations
- ✅ **GKE Ready** - Kubernetes manifests via Helm charts
- ✅ **Language Agnostic** - Examples for Node.js, Python, Go, Java, Ruby, and more

## Quick Start

**Get your app deployed in 6 steps:**

1. **Create project** - Fork this template or clone with fresh git history
2. **Protect branches** - Protect `main` and `dev` branches in GitLab (required for Artifactory credentials)
3. **Update config** - Change `app_name` in `helm/values.yaml` to match your GitLab project name (everything else auto-configures)
4. **Build app** - Create your app + Dockerfile (listen on port 8080, add `/health` endpoint)
5. **Deploy to dev** - `git push origin dev` (auto-deploys)
6. **Deploy to prod** - Merge to `main`, manually trigger deploy job in GitLab

**Done!** Your app is live at:
- Dev: `https://your-app.tsdev.paloaltonetworks.com`
- Prod: `https://your-app.ts.paloaltonetworks.com`

**Need details?** See [GETTING-STARTED.md](doc/GETTING-STARTED.md) for step-by-step instructions.

**Migrating existing app?** See [MIGRATION-GUIDE.md](doc/MIGRATION-GUIDE.md)

## Manual Setup Required

The template automates a lot, but you'll still need to handle these steps manually:

### Required for Every App

- [ ] **GitLab project name** - Must match `app_name` in `helm/values.yaml`
- [ ] **Update `app_name`** in `helm/values.yaml`
- [ ] **DNS + GCP service account** - Both handled by the automated onboarding pipeline (one click) - see [ONBOARDING-AUTOMATION.md](doc/ONBOARDING-AUTOMATION.md). Manual fallback: [DNS-SETUP.md](doc/DNS-SETUP.md) + [SERVICE-ACCOUNT-SETUP.md](doc/SERVICE-ACCOUNT-SETUP.md).
- [ ] **Add telemetry/instrumentation** - See [Running the instrumentation prompt](#running-the-instrumentation-prompt) below, plus [TELEMETRY-SETUP.md](doc/TELEMETRY-SETUP.md) for the runtime picture.

### Required If Using PostgreSQL

- [ ] Create database in Cloud SQL
- [ ] Create database user
- [ ] Add password to `gitlabvars` GitLab CI/CD variables
- [ ] Update Helm with DB connection info
- [ ] Choose migration strategy (manual, on startup, init container) - see [DATABASE-SETUP.md](doc/DATABASE-SETUP.md)

### Required If Using BigQuery

- [ ] Add BigQuery IAM permissions to your Terraform module file
- [ ] Identify which BigQuery project/dataset to access
- [ ] See [BIGQUERY-SETUP.md](doc/BIGQUERY-SETUP.md) for details

### Required If Using Secrets/API Keys

- [ ] Add secrets to GitLab CI/CD variables (creates `gitlabvars` secret automatically)
- [ ] Reference in Helm via `envFrom: secretRef: gitlabvars`

### Optional but Recommended

- [ ] **Health endpoint** - Add `/health` route in your app for Kubernetes probes

## Running the Instrumentation Prompt

Instrumentation (OpenTelemetry traces and manual spans around business-critical operations) is applied by an AI-assisted prompt, not by hand. This keeps the pattern consistent across every app in the fleet.

**Precondition** — verify the OTEL Operator + Instrumentation CRs exist in your target cluster:

```
kubectl get instrumentation -n observability
```

Expect at least `otel-python` and/or `otel-nodejs`. If missing, the operator-injected pattern won't work and you'll need to fall back to `mode: app-bootstrap` (the prompt covers this).

**How to run** — open Claude Code (or Gemini) inside your app's repo and paste:

```
Read /path/to/app-template/doc/Instrumentation_prompt.md and apply
it to this repo.

Follow the prompt's own workflow — it tells you what to do:

- Start with the Pre-flight section. Classify this app as State A /
  B / C before touching anything, and report the classification. If
  State C, STOP and report — no-op is a valid outcome.

- Then run the "Detect chart shape first" step in Concrete
  implementation examples. Shape A (values-driven), Shape B (hand-
  authored single workload), or Shape C (hand-authored multi-
  workload) determines HOW you wire the annotation. Don't try to
  convert Shape B/C to Shape A by swapping in the app-template's
  chart — that collapses the deployment topology.

- Pick mode: operator-injected (default for Python, Java, Go) or
  app-bootstrap (Next.js, ESM entrypoints, other framework edge
  cases). The prompt explains both — pick based on the runtime, not
  by copying from another repo.

- Before declaring done, run `helm template ./helm` and diff against
  the pre-change output. Byte-identical rendered output means you
  produced churn, not instrumentation — revert.
```

Swap `/path/to/app-template/` for your actual clone path.

**What the prompt does** — reads your app, classifies state (already-wired vs partial vs missing), then either reports "no changes needed" or wires only the missing pieces: `trace.get_tracer(__name__)`, manual spans around business-critical boundaries (DB transactions, message publishes, external API calls, fan-out loops), W3C `traceparent` propagation across queues (Pub/Sub, SQS, etc.).

**What the prompt does NOT do** — flip `observability.enabled` from `false` to `true` in a way that fires alerts (separate deliberate step after you've verified traces in Cloud Trace); rewrite chart templates when the rendered YAML wouldn't change; "align" hand-edited files with the canonical template just for consistency.

## Architecture

**Stack:**
- **Language:** Your choice! (Node.js, Python, Go, Java, Ruby, etc.)
- **Container Registry:** Artifactory (`docker-ra.art.code.pan.run`)
- **Deployment:** Kubernetes via Helm
- **CI/CD:** GitLab CI with custom runners

**See [EXAMPLES.md](doc/EXAMPLES.md)** for complete setup examples in different languages.

**Deployment Flow:**
1. Push code to `dev` or `main` branch
2. GitLab CI builds Docker image with Kaniko
3. Image pushed to Artifactory with tag = commit SHA
4. Deploy job runs Helm upgrade to install/update the app
5. Kubernetes pulls image from Artifactory and deploys

## SSO Authentication

**By default, this template includes SSO authentication.** Users must authenticate via corporate SSO (Okta) before accessing your app.

**User → Ingress → nginx + goggles → Vouch → Okta → Your App**

- **nginx + goggles**: Validates authentication tokens
- **Vouch**: SSO proxy that connects to Okta
- **Okta**: Corporate identity provider

Your app receives authenticated user information via HTTP headers:
- `X-Username`: User's email
- `X-First-Name`, `X-Last-Name`: User's name
- `X-Groups`: User's groups (comma-separated)

**When to disable SSO:**
- Public APIs
- Apps with their own built-in authentication
- Development/testing apps without sensitive data

**To disable SSO:**
Edit `helm/values.yaml`:
```yaml
disable_sso: true
```

**📖 See [SSO-AUTHENTICATION.md](doc/SSO-AUTHENTICATION.md) for complete documentation, troubleshooting, and customization.**

## Google Cloud Access

**This template is pre-configured for Google Cloud access via Workload Identity** - no credentials or keys needed.

**How it works:**
1. Your Kubernetes pod runs with a Kubernetes service account (`{app-name}-sa`)
2. GKE automatically maps it to a GCP service account (`{app-name}@{project}.iam.gserviceaccount.com`) via Workload Identity
3. **Credentials are provided automatically** - no keys or secrets needed
4. Your app code uses Application Default Credentials - authentication just works
5. The `GOOGLE_CLOUD_PROJECT` environment variable tells the SDK which project to use

**What you can access:**
- BigQuery (data warehouse and analytics)
- Cloud Storage (file storage)
- Pub/Sub (messaging)
- Secret Manager (secure credentials)
- Any other GCP service your service account has permissions for

**Setup required:**
1. Add your app to the [`gcp-wwss-as-trust-module`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module) Terraform module
2. This creates the GCP service account, workload identity binding, and IAM permissions
3. Your app automatically gets access - no credentials needed

**⚠️ Important:** All apps **MUST** be added to the Terraform infrastructure module for GCP access to work.

**See [BIGQUERY-SETUP.md](doc/BIGQUERY-SETUP.md)** for complete setup instructions including Terraform module requirements.

## PostgreSQL

Shared Cloud SQL instances run in dev and prod; each app gets its own database and user on the shared instance.

**What you need to do:**
1. Create the database and a database user in Cloud SQL (manual via GCP Console or `gcloud sql`)
2. Add the password as a secret — see [Secrets / API Keys](#secrets--api-keys) below
3. Wire connection info (host, port, db name, user) into your Helm `env` block in `helm/templates/deployment.yaml`
4. Pick a migration strategy — manual, on startup, or init container — the template does NOT run migrations automatically

**See [DATABASE-SETUP.md](doc/DATABASE-SETUP.md)** for the complete setup, migration patterns, and connection examples.

## BigQuery

BigQuery uses your app's GCP service account via Workload Identity — no credentials or key files needed.

**What you need to do:**
1. Make sure your app has a GCP service account set up — see [SERVICE-ACCOUNT-SETUP.md](doc/SERVICE-ACCOUNT-SETUP.md)
2. Add the BigQuery IAM permissions (`roles/bigquery.dataViewer`, `roles/bigquery.jobUser`) to your app's `.tf` file in the Terraform module — the IAM grant goes on the project that owns the BigQuery data (often `wwss-appsheet`), not your app's project
3. Use the BigQuery client library in your app — code examples by language in [BIGQUERY-SETUP.md](doc/BIGQUERY-SETUP.md)

## Secrets / API Keys

Secrets (database passwords, Slack tokens, API keys, OAuth client secrets) are loaded into pods via a **centralized Kubernetes secret called `gitlabvars`**, managed in a separate repo — **not** in this app repo and **not** in your app's own GitLab CI/CD variables.

**Repos:**
- Dev: [`us-gke-trust-dev-argocd-apps`](https://gitlab.com/panw-gse/ts/us-gke-trust-dev-argocd-apps)
- Prod: [`us-gke-trust-prod-argocd-apps`](https://gitlab.com/panw-gse/ts/us-gke-trust-prod-argocd-apps)

**File to edit:** `manifests/secrets/secrets.tmpl` (in either repo).

**⚠️ Common pitfall:** Adding a CI/CD variable to your own app's GitLab project does **NOT** make it available to the pod. The pod reads from the cluster's `gitlabvars` secret, which is built from variables in the secrets repo above.

**How the template consumes secrets:** `helm/templates/deployment.yaml` already includes:

```yaml
envFrom:
  - secretRef:
      name: gitlabvars
```

So every key in the `gitlabvars` secret becomes an env var in your pod automatically. Reference them in your code as normal env vars (`process.env.SLACK_BOT_TOKEN`, `os.environ["MY_API_KEY"]`, etc.).

**How to add a new secret:**

1. Edit `manifests/secrets/secrets.tmpl` in the secrets repo. Add a line like:
   ```yaml
   MY_API_KEY: ${MY_API_KEY}
   ```
2. Add the actual value as a **Protected + Masked** CI/CD variable in the **secrets repo's** GitLab project (Settings → CI/CD → Variables), with the same name (`MY_API_KEY`).
3. Open an MR against the secrets repo and merge it.
4. The pipeline runs `envsubst` over `secrets.tmpl` and applies the updated `gitlabvars` secret to the cluster.
5. Restart your app's pods so they pick up the new env var:
   ```bash
   kubectl rollout restart deploy/your-app-deployment -n applications
   ```

**Verify the secret is loaded:**

```bash
kubectl exec -n applications deploy/your-app-deployment -- env | grep MY_API_KEY
```

## Development Commands

```bash
# Local development (language-specific)
# Node.js: npm run dev
# Python: python app.py
# Go: go run main.go
# See doc/EXAMPLES.md for your language

# Docker testing
docker build -t my-app .
docker run -p 8080:8080 my-app

# Test health endpoint
curl http://localhost:8080/health
```

## Deployment Architecture

### Environments

| Environment | Branch | Cluster | Namespace | URL |
|-------------|--------|---------|-----------|-----|
| Dev | `dev` | us-gke-trust-dev | `applications` | your-app.tsdev.paloaltonetworks.com |
| Prod | `main` | us-gke-trust-prod | `applications` | your-app.ts.paloaltonetworks.com |

### GitLab Runners

**Dev Runner:**
- Tag: `us-gke-trust-dev`
- Cluster: us-gke-trust-dev
- Auto-deploys on `dev` branch push

**Prod Runner:**
- Tag: `us-gke-trust-prod`
- Cluster: us-gke-trust-prod
- Manual deploy on `main` branch

## Helm Configuration

The `helm/` directory contains Kubernetes manifests:

- `Chart.yaml` - Chart metadata
- `values.yaml` - Default values (base configuration)
- `dev.yaml` - Dev environment overrides
- `prod.yaml` - Prod environment overrides
- `templates/` - Kubernetes resource templates

**Key configuration:**
```yaml
k8s:
  app_name: "myapp"  # IMPORTANT: Should match your GitLab project name
  app_port: 80
  app_targetPort: 8080       # Your app's port (standard is 8080)
  replicas: 1

image:
  registry: docker-ra.art.code.pan.run
  # Image auto-constructed as: registry/app_name:tag
  # Override only if GitLab project name differs from app_name:
  # repo: docker-ra.art.code.pan.run/different-project-name
  tag: latest
```

**Auto-configured from `app_name`:**
- Docker image: `registry/{app_name}:{tag}`
- URLs: `{app_name}.tsdev.paloaltonetworks.com` (dev), `{app_name}.ts.paloaltonetworks.com` (prod)
- Service accounts: K8s `{app_name}-sa`, GCP `{app_name}@{project}.iam.gserviceaccount.com`

**⚠️ Important:** Your GitLab project name should match `app_name`. If they differ, the image won't be found during deployment.

## Customization Guide

### Using a Different Port (Not Recommended)

**Standard is port 8080.** If you absolutely must use a different port:

1. Update your app to listen on your port
2. Update `Dockerfile` - EXPOSE your port
3. Update `helm/values.yaml`:
   ```yaml
   k8s:
     app_targetPort: 9000  # Your custom port
     app_containerPort: 9000
   ```

**Note:** Using 8080 is simpler and avoids configuration errors.

### Add Environment Variables

Edit `helm/templates/deployment.yaml`:
```yaml
env:
  - name: MY_ENV_VAR
    value: "my-value"
  - name: SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: my-app-secrets
        key: secret-key
```

### Add Database or Redis

See `helm/templates/deployment.yaml` for examples of adding service containers.

### Change Base Path

For apps served under a path (e.g., `/my-app/`):
1. Update `.gitlab-ci.yml` - Set `BASE_PATH` variable
2. Update your app to handle the base path

## Troubleshooting

### Pipeline Fails at Build Step
- Check Dockerfile syntax
- Verify all files referenced in Dockerfile exist
- Check Kaniko build logs in GitLab

### Pipeline Fails at Deploy Step
- Check runner is online: GitLab → Build → Runners
- Verify tags match: job uses `us-gke-trust-dev`, runner has same tag
- Check Helm chart syntax: `helm lint ./helm`

### App Not Accessible After Deploy
```bash
# Check pods are running
kubectl get pods -n applications

# Check pod logs
kubectl logs -n applications <pod-name>

# Check ingress
kubectl get ingress -n applications
```

### Image Pull Errors
- Verify image exists in Artifactory
- Check image tag matches what was built
- GKE nodes should have automatic access (no imagePullSecrets needed)

## Removing an App

If you need to shut down and remove an app deployed with this template:

### 1. Delete from Kubernetes

**Delete from dev:**
```bash
kubectl config use-context us-gke-trust-dev
helm uninstall your-app-name -n applications
```

**Delete from prod:**
```bash
kubectl config use-context us-gke-trust-prod
helm uninstall your-app-name -n applications
```

**Verify deletion:**
```bash
# Check pods are gone
kubectl get pods -n applications -l app=your-app-name

# Check all resources removed
kubectl get all -n applications -l app=your-app-name
```

### 2. Delete GCP Service Account (Optional)

If your app had a GCP service account for BigQuery/Cloud Storage access:

```bash
# List to find your service account
gcloud iam service-accounts list --project=wwss-as-trust-dev

# Delete the service account
gcloud iam service-accounts delete \
  your-app-name@wwss-as-trust-dev.iam.gserviceaccount.com \
  --project=wwss-as-trust-dev
```

**For prod environment:**
```bash
gcloud iam service-accounts delete \
  your-app-name@wwss-as-trust-prod.iam.gserviceaccount.com \
  --project=wwss-as-trust-prod
```

### 3. Delete GitLab Project (Optional)

If you want to completely remove the GitLab repository:

1. Go to your project in GitLab
2. Settings → General
3. Scroll to **Advanced** section
4. Click **Expand**
5. Click **Delete project**
6. Type the project name to confirm
7. Click **Yes, delete project**

**Warning:** This is permanent and cannot be undone.

### 4. Clean Up Artifactory Images (Optional)

Images in Artifactory don't need to be deleted unless storage is a concern. They're automatically tagged by commit SHA and won't interfere with other apps.

**If you want to clean them up:**
1. Login to https://art.code.pan.run
2. Search for your app name
3. Select images to delete
4. Click Delete

## Support

- **GitLab CI/CD:** See `.gitlab-ci.yml` comments
- **Helm Charts:** See `helm/` directory
- **Claude Code:** See [CLAUDE.md](CLAUDE.md) for AI-assisted development guidance
- **Infrastructure issues:** Contact #engineering-productivity (Artifactory access, registry problems)

## Full Documentation

All documentation is in the [`doc/`](doc/) folder:

**Getting Started:**
- [GETTING-STARTED.md](doc/GETTING-STARTED.md) - Step-by-step setup guide
- [MIGRATION-GUIDE.md](doc/MIGRATION-GUIDE.md) - Migrating an existing app
- [EXAMPLES.md](doc/EXAMPLES.md) - Language-specific examples

**Setup Guides:**
- [ONBOARDING-AUTOMATION.md](doc/ONBOARDING-AUTOMATION.md) - Automated onboarding pipeline (DNS + GCP service account in one click)
- [DNS-SETUP.md](doc/DNS-SETUP.md) - DNS setup (manual fallback / mechanics reference)
- [SERVICE-ACCOUNT-SETUP.md](doc/SERVICE-ACCOUNT-SETUP.md) - GCP service account + Workload Identity (manual fallback / mechanics reference)
- [SSO-AUTHENTICATION.md](doc/SSO-AUTHENTICATION.md) - SSO authentication setup
- [BIGQUERY-SETUP.md](doc/BIGQUERY-SETUP.md) - BigQuery (after the SA is set up)
- [DATABASE-SETUP.md](doc/DATABASE-SETUP.md) - PostgreSQL setup
- [DOCKER-BASE-IMAGES.md](doc/DOCKER-BASE-IMAGES.md) - Choosing base images for your Dockerfile

**Architecture & Visualization:**
- [DIAGRAMS.md](doc/DIAGRAMS.md) - Architecture diagrams (system, CI/CD, SSO flow, etc.)

**Observability:**
- [TELEMETRY-SETUP.md](doc/TELEMETRY-SETUP.md) - OpenTelemetry tracing setup
- [Instrumentation_prompt.md](doc/Instrumentation_prompt.md) - AI prompt for adding instrumentation


## Next Steps After Template

1. ✅ Update app name in all configs
2. ✅ Implement your application logic
3. ✅ Test Docker build locally
4. ✅ Push to `dev` branch and deploy
5. ✅ Verify dev deployment works
6. ✅ Merge to `main` and deploy to prod
7. ✅ Set up monitoring/alerts (if needed)

---

**Built with GitLab CI/CD + Kubernetes + Helm**
