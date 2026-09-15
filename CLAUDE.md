# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this application template.

## Project Overview

This is a template for building and deploying containerized applications to GKE clusters using GitLab CI/CD and Helm.

**Key Components:**
- **Application Code:** Your main application (customize the language/framework)
- **Dockerfile:** Containerizes the application
- **GitLab CI:** Builds Docker images and deploys via Helm
- **Helm Charts:** Kubernetes deployment manifests

## CRITICAL: Base image selection (read before writing any Dockerfile)

The PANW corporate proxy does SSL inspection on all outbound HTTPS. Standard base images do NOT trust the PANW Enterprise CA G2 cert. Any HTTPS request during `docker build` — `pip install`, `npm ci`, `apt-get update`, `go mod download` — will fail with:

```
SSL: CERTIFICATE_VERIFY_FAILED: self-signed certificate in certificate chain
```

**Fix by language — use the proven pattern, not a guess:**

**Python** — plain proxy image + `pip --trusted-host`. Verified working in `ask-experts` and `py-observability-smoketest`:

```dockerfile
FROM docker-io.art.code.pan.run/library/python:3.11-slim
COPY requirements.txt .
RUN pip install --no-cache-dir \
      --trusted-host pypi.org \
      --trusted-host files.pythonhosted.org \
      -r requirements.txt
```

Do NOT try `docker.art.code.pan.run/build-tools--image-python:*.ep*` — those tags do not exist in Artifactory (verified 2026-07-01 via kaniko `MANIFEST_UNKNOWN`).

**Node** — EP image required for Next.js / anything with a build step that fetches from the internet:

```dockerfile
FROM docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9
USER root   # EP images default to non-root; switch for npm ci / apt-get
```

Simple Node apps without external HTTPS during build can use `docker-io.art.code.pan.run/library/node:20-alpine`.

**Any language** — plain proxy image (`docker-io.art.code.pan.run/library/*`) is fine for stages that don't touch the network (COPY-only final stages, precompiled Go binaries).

See `doc/DOCKER-BASE-IMAGES.md` for full details and the FAQ entry on the certificate error.

## Development Workflow

### Local Development

```bash
# Start the application locally (update based on your language)
# Node.js: npm run dev
# Python: python app.py
# Go: go run main.go
# See EXAMPLES.md for complete language-specific examples

# Test Docker build locally
docker build -t my-app-test .
docker run -p 8080:8080 my-app-test
curl http://localhost:8080/health    # Test health endpoint
```

### Deployment Workflow

1. **Develop locally** - Build features using Claude Code
2. **Commit to `dev` branch** - Triggers CI/CD pipeline
3. **GitLab CI builds image** - Kaniko builds and pushes to Artifactory
4. **Deploy job runs** - Helm deploys to dev cluster
5. **Test in dev** - Verify at `https://your-app.tsdev.paloaltonetworks.com`
6. **Merge to `main`** - Deploy to production

## File Structure

```
.
├── README.md                 # Developer documentation (root level)
├── CLAUDE.md                 # This file - Claude Code guidance (root level)
├── .gitlab-ci.yml            # CI/CD pipeline configuration
├── Dockerfile                # Container image definition
├── .gitignore                # Git ignore patterns
├── doc/                      # All other documentation
│   ├── GETTING-STARTED.md    # Step-by-step setup guide
│   ├── EXAMPLES.md           # Language-specific examples
│   ├── BIGQUERY-SETUP.md     # BigQuery setup
│   ├── DATABASE-SETUP.md     # PostgreSQL setup
│   ├── SSO-AUTHENTICATION.md # SSO setup
│   ├── DIAGRAMS.md           # Architecture diagrams
│   └── ...                   # Other docs
├── helm/                     # Kubernetes deployment configs
│   ├── Chart.yaml            # Helm chart metadata
│   ├── values.yaml           # Default configuration values
│   ├── dev.yaml              # Dev environment overrides
│   ├── prod.yaml             # Prod environment overrides
│   └── templates/            # Kubernetes resource templates
│       ├── deployment.yaml   # Main app deployment
│       ├── service.yaml      # Kubernetes service
│       ├── ingress.yaml      # External access configuration
│       └── sa.yaml           # Service account (for GCP access)
└── [your app files]          # Application source code
```

## Important Configuration Files

### .gitlab-ci.yml

**Purpose:** Defines the CI/CD pipeline (build and deploy)

**Key sections:**
- `variables:` - Configure Docker registry, image name, build args
- `kaniko build artifactory:` - Builds Docker image
- `deploy_to_dev:` - Deploys to dev cluster via Helm (automatic)
- `deploy_to_prod:` - Deploys to prod cluster via Helm (manual trigger)

**When to modify:**
- Changing app name
- Adding build arguments
- Adjusting deployment triggers

### Dockerfile

**Purpose:** Defines how to build the Docker image

**Current setup:** Template - customize for your language (see EXAMPLES.md)

**Important:** 
- All apps must listen on **port 8080** (standardized)
- **Choose the right base image:**
  - **Apps that download external resources during build** (Next.js with Google Fonts, TypeScript, etc.):
    - Use `docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9`
    - Has PANW Enterprise CA certificates pre-installed
    - Allows downloads from internet during build (fonts, APIs, etc.)
  - **Simple apps with no external downloads**:
    - Use `docker-io.art.code.pan.run/library/node:20-alpine`
    - Lighter weight, no extra certificates needed
- **npm ci pattern:**
  - Use `npm ci` (installs all dependencies including devDependencies)
  - DO NOT use `npm ci --only=production` if your app has a build step
  - Apps with TypeScript, Next.js, React, etc. need devDependencies to build
- **EP images run as non-root by default:**
  - Switch to `USER root` before `apt-get install`
  - Switch back to `USER nodeuser` after setup

**When to modify:**
- Changing language/framework
- Adding dependencies
- Optimizing build performance
- Adding build arguments

### helm/values.yaml

**Purpose:** Default configuration for all environments

**Key settings:**
```yaml
k8s:
  app_name: "myapp"              # IMPORTANT: Must match GitLab project name!
  app_port: 80                   # Service port (external - keep at 80)
  app_targetPort: 8080           # Container port (standardized at 8080)
  replicas: 1                    # Number of pod replicas

image:
  registry: docker-ra.art.code.pan.run  # Registry (image is auto-constructed as registry/app_name:tag)
  # Optional override if GitLab project name differs:
  # repo: docker-ra.art.code.pan.run/different-project-name
  tag: latest

gcp:
  project_id: wwss-as-trust-dev  # GCP project
  # Service account name is auto-set to app_name
```

**Auto-configured from `app_name`:**
- Docker image: `registry/{app_name}:{tag}`
- URLs: `{app_name}.tsdev.paloaltonetworks.com` (dev), `{app_name}.ts.paloaltonetworks.com` (prod)
- Service accounts: K8s `{app_name}-sa`, GCP `{app_name}@{project}.iam.gserviceaccount.com`
- Standard K8s labels on Deployment + Service:
  - `app: {app_name}`
  - `app.kubernetes.io/name: {app_name}`
  - `app.kubernetes.io/instance: {app_name}`
  - `app.kubernetes.io/managed-by: Helm`

**⚠️ Critical:** `app_name` must match the GitLab project name. GitLab CI builds the Docker image using the project name, and Helm deploys using `app_name`. If they don't match, deployment will fail with `ImagePullBackOff`. This convention is ALSO what lets triage-bot's `app.kubernetes.io/instance` lookup find your source repo without fallback tiers.

**When to modify:**
- Initial setup (change `app_name` to match GitLab project name)
- Changing resource requirements
- Adding environment variables
- Edge case: Set `image.repo` if project name must differ from app name

### helm/dev.yaml & helm/prod.yaml

**Purpose:** Environment-specific overrides

**Key settings:**
```yaml
hostnames:
  - your-app.tsdev.paloaltonetworks.com  # Dev URL
  # - your-app.ts.paloaltonetworks.com      # Prod URL

image:
  tag: "abc1234"  # Updated automatically by CI/CD

gcp:
  project_id: wwss-as-trust-dev  # or wwss-as-trust-prod
```

**When to modify:**
- Changing hostname/domain
- Environment-specific configurations
- Different resource limits per environment

## CI/CD Pipeline Details

### Build Stage (Kaniko)

**What it does:**
1. Reads `Dockerfile`
2. Builds multi-stage Docker image
3. Pushes to `docker-ra.art.code.pan.run/your-app:${CI_COMMIT_SHORT_SHA}`

**Image tags:**
- Each commit gets a unique tag (first 8 chars of commit SHA)
- Example: `abc12345`

**Registry:** Artifactory at `docker-ra.art.code.pan.run`

### Deploy Stage (Helm)

**What it does:**
1. Clones the repo to get Helm charts
2. Runs `helm upgrade --install` with the new image tag
3. Kubernetes pulls the image and updates the deployment

**Runners used:**
- Dev: Tag `us-gke-trust-dev` → us-gke-trust-dev cluster
- Prod: Tag `us-gke-trust-prod` → us-gke-trust-prod cluster

**No imagePullSecrets needed** - GKE nodes have automatic access to Artifactory via node service accounts.

## Making Code Changes

### Adding New Features

1. **Write code** using Claude Code's vibe coding
2. **Test locally** - Run the app and verify it works
3. **Update Dockerfile if needed** - If adding new dependencies
4. **Commit and push to `dev`**:
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin dev
   ```
5. **Monitor pipeline** in GitLab CI/CD → Pipelines (deploys automatically to dev)
6. **Verify in dev environment** at `https://your-app.tsdev.paloaltonetworks.com`

### Modifying Kubernetes Configuration

**Add environment variables:**
Edit `helm/templates/deployment.yaml`:
```yaml
env:
  - name: DATABASE_URL
    value: "postgres://..."
  - name: API_KEY
    valueFrom:
      secretKeyRef:
        name: app-secrets
        key: api-key
```

**Change resource limits:**
Edit `helm/templates/deployment.yaml`:
```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "100m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

**Add health checks:**
Edit `helm/templates/deployment.yaml`:
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10
```

### Debugging Deployments

**Check pipeline logs:**
1. Go to GitLab → CI/CD → Pipelines
2. Click on the failed job
3. Read the logs to identify the issue

**Check Kubernetes pods:**
```bash
kubectl config use-context us-gke-trust-dev
kubectl get pods -n applications
kubectl logs -n applications <pod-name>
kubectl describe pod -n applications <pod-name>
```

**Common issues:**
- **Image not found** - Check image was pushed to Artifactory, verify tag matches
- **CrashLoopBackOff** - App is crashing, check pod logs
- **ImagePullBackOff** - Can't pull image (rare - should work with node credentials)
- **Pending** - Resource constraints or scheduling issues

## Best Practices

### Code Organization
- Keep application code separate from infrastructure code
- Use environment variables for configuration
- Don't hardcode secrets (use Kubernetes secrets)

### Docker Images
- **Choose the right base image:**
  - Apps downloading external resources → `docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9` (has PANW CA certs)
  - Simple apps → `docker-io.art.code.pan.run/library/node:20-alpine` (lighter, no extra certs)
- **Use `npm ci` not `npm ci --only=production`** - Apps with build steps (TypeScript, Next.js, React) need devDependencies
- Use multi-stage builds to keep images small
- Don't include unnecessary files (.git, node_modules, etc.)
- Layer dependencies efficiently (install deps before copying code)
- **EP images run as non-root** - Switch to `USER root` for `apt-get`, then back to `USER nodeuser`

### Helm Charts
- Use values files for environment-specific config
- Keep templates generic and reusable
- Document custom values in comments

### Git Workflow
- **`dev` branch** - Development and testing
- **`main` branch** - Production releases
- Use descriptive commit messages
- Test in dev before merging to main

### Security
- **Never commit secrets** to Git
- Use Kubernetes secrets for sensitive data
- Use GCP Workload Identity for cloud access (already configured)
- Keep base images updated

## Database Migrations

**The template does NOT include automatic migrations.** This is intentional to keep it flexible.

**Why not included:**
- Not all apps use databases
- Migration tools vary by language and framework
- Some teams prefer manual migrations or init containers
- Can cause race conditions with multiple replicas

**If your app needs migrations:**
- See `DATABASE-SETUP.md` for patterns (manual, automatic on startup, init containers)
- Add migration logic based on your specific needs
- Consider using init containers for production deployments with multiple replicas

## Customization Checklist

When creating a new app from this template:

- [ ] Update `helm/values.yaml` → `k8s.app_name` (everything else auto-configures from this!)
- [ ] Update `.gitlab-ci.yml` → `IMAGE_NAME_TEMPLATE` (only if different from project name)
- [ ] Update `Dockerfile` for your language/framework
- [ ] **Pick the correct base image** — if the build runs `pip install` / `npm ci` / `apt-get` / any HTTPS fetch, use an EP image (`docker.art.code.pan.run/build-tools--image-*`). See `doc/DOCKER-BASE-IMAGES.md`. Wrong choice = `CERTIFICATE_VERIFY_FAILED` on build.
- [ ] Update `README.md` with app-specific documentation
- [ ] Update this `CLAUDE.md` with app-specific guidance
- [ ] Create GCP service account if app needs GCP access
- [ ] Add database migrations if needed (see DATABASE-SETUP.md)
- [ ] Test Docker build locally: `docker build -t test .`
- [ ] Push to `dev` branch and verify deployment

## Troubleshooting Guide

### Build Failures

**Error:** `Dockerfile not found`
- Ensure Dockerfile is in repo root
- Check .gitignore isn't excluding it

**Error:** `COPY failed: no source files were specified`
- Files referenced in Dockerfile don't exist
- Check paths are correct

**Error:** `Exit code 137` (OOM Killed)
- Build ran out of memory
- Optimize Dockerfile (multi-stage builds, smaller base images)
- Request more memory for build job

### Deploy Failures

**Error:** `Job stuck: no runner online`
- Runner with tag `us-gke-trust-dev` is offline
- Check: GitLab → Build → Runners

**Error:** `Helm upgrade failed`
- Check Helm chart syntax: `helm lint ./helm`
- Review deploy job logs for specific error

**Error:** `Error: INSTALLATION FAILED: timed out waiting`
- Deployment took too long
- Check pod status: `kubectl get pods -n applications`
- Check pod logs for startup errors

### Runtime Issues

**App not accessible via URL:**
1. Check ingress: `kubectl get ingress -n applications`
2. Verify hostname matches what's in `dev.yaml`/`prod.yaml`
3. Check DNS resolution
4. Check pod is running: `kubectl get pods -n applications`

**App returns 502/503 errors:**
1. Check pod logs: `kubectl logs -n applications <pod-name>`
2. Verify app is listening on correct port
3. Check service configuration: `kubectl get svc -n applications`

## Additional Resources

- **Helm Documentation:** https://helm.sh/docs/
- **Kubernetes Docs:** https://kubernetes.io/docs/
- **GitLab CI/CD:** https://docs.gitlab.com/ee/ci/
- **Docker Best Practices:** https://docs.docker.com/develop/dev-best-practices/

## Template Maintenance

This template should be updated periodically:
- Update base images in Dockerfile
- Update Helm chart version
- Update GitLab CI syntax/features
- Add new best practices as they emerge
