# Getting Started with App Template

Quick guide to get your new application up and running.

> **💡 Language Examples:** See [EXAMPLES.md](EXAMPLES.md) for complete examples in Node.js, Python, Go, Java, Ruby, React, and more!
>
> **📝 Already have an existing app?** See [MIGRATION-GUIDE.md](MIGRATION-GUIDE.md) for instructions on adding CI/CD to your existing repository.

## Prerequisites

- **Git** - Version control
- **Your language runtime** - Node.js, Python, Go, Java, etc.
- **Docker** (optional but recommended) - For local container testing
- **kubectl** (optional) - For debugging deployments
- **GitLab account** - With access to code.pan.run

## Step 1: Create Your Project from Template

Choose one of these methods to create your new app from this template:

### Method 1: Fork the Template (Recommended - Easiest)

**This keeps the template connection and is the fastest way to start:**

1. Go to https://code.pan.run/reference-architectures/app-template
2. Click **Fork** (top right)
3. Choose your group/namespace
4. **Rename** the project to your app name (e.g., `my-app`)
5. Click **Fork project**
6. Clone your new fork:
   ```bash
   git clone https://code.pan.run/your-group/my-app.git
   cd my-app
   
   # Create dev branch
   git checkout -b dev
   git push -u origin dev
   ```

**Advantages:**
- ✅ Fastest method (one click)
- ✅ Can pull template updates later if needed
- ✅ Fork relationship shows where it came from

**Disadvantage:**
- Includes all template's git history

---

### Method 2: Clone and Fresh Start (Clean History)

**Use this if you want a fresh git history without the template's commits:**

1. Clone the template locally:
   ```bash
   git clone https://code.pan.run/reference-architectures/app-template.git my-app
   cd my-app
   ```

2. Remove template's git history and start fresh:
   ```bash
   rm -rf .git
   git init
   git add .
   git commit -m "Initial commit from app-template"
   ```

3. Create a new project in GitLab:
   - Go to https://code.pan.run/your-group
   - Click **New project** → **Create blank project**
   - Name it `my-app`
   - **Uncheck** "Initialize repository with a README"
   - Click **Create project**

4. Push your code to the new project:
   ```bash
   git remote add origin https://code.pan.run/your-group/my-app.git
   git push -u origin main
   
   # Create dev branch
   git checkout -b dev
   git push -u origin dev
   ```

**Advantages:**
- ✅ Clean git history (no template commits)
- ✅ Full control over initial commit

**Disadvantage:**
- More manual steps

## Step 2: Configure Branch Protection (REQUIRED)

**Important:** The CI/CD pipeline uses protected group-level variables for Artifactory credentials. These variables only work on protected branches.

**Protect your branches:**

1. Go to your project in GitLab: `https://code.pan.run/your-group/my-app`
2. Navigate to **Settings → Repository**
3. Expand **Protected branches**
4. Protect the `main` branch (if not already protected):
   - Branch: `main`
   - Allowed to merge: **Maintainers**
   - Allowed to push: **Maintainers**
   - Click **Protect**
5. Protect the `dev` branch:
   - Branch: `dev`
   - Allowed to merge: **Developers + Maintainers** (or **Maintainers** only)
   - Allowed to push: **Developers + Maintainers** (or **Maintainers** only)
   - Click **Protect**

**Why is this required?**
- The `ARTIFACTORY_API_USERNAME` and `ARTIFACTORY_API_PASSWORD` variables are marked as "Protected" at the group level
- Protected variables are only available to protected branches
- Without this, the `kaniko upload artifactory` job will fail with authentication errors

## Step 3: Customize Configuration

**Update `helm/values.yaml` with your app name:**

```yaml
k8s:
  app_name: "your-app-name"  # ← CHANGE THIS (everything else is auto-configured)
```

**That's it!** The following are automatically configured from `app_name`:
- Docker image: `docker-ra.art.code.pan.run/{app_name}`
- Dev URL: `{app_name}.tsdev.paloaltonetworks.com`
- Prod URL: `{app_name}.ts.paloaltonetworks.com`
- Kubernetes service account: `{app_name}-sa`
- GCP service account: `{app_name}@{project}.iam.gserviceaccount.com`

## Step 4: Set Up External Infrastructure (DNS + GCP Service Account)

**Required before your app can serve traffic or access GCP services.**

**Recommended: the automated onboarding pipeline.**
1. Fill in the `onboarding:` block in `helm/values.yaml` (IAM roles, optionally `iam_target_project`).
2. Push your first commit to `dev`.
3. CI/CD → Pipelines → **Run pipeline** → Branch: `dev`, Variable: `RUN_ONBOARD=true` → Run.
4. Pipeline commits SA terraform + tags the module + opens an MR in the dev deployment repo. Reviewer merges; applier clicks Apply.
5. When you're ready for prod: merge `dev` → `main`, then **Run pipeline** on `main` with `RUN_ONBOARD=true` → opens a prod deployment MR.

**📖 See [ONBOARDING-AUTOMATION.md](ONBOARDING-AUTOMATION.md)** for the full developer flow, role allowlist, and troubleshooting.

**Manual fallback** (if automation is broken or you need to inspect the generated terraform):
- DNS: [DNS-SETUP.md](DNS-SETUP.md) — repo: [gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment)
- Service account: [SERVICE-ACCOUNT-SETUP.md](SERVICE-ACCOUNT-SETUP.md) — repo: [gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module)

You can do this in parallel with Step 5 (building your app), but both must be complete before Step 6 (deploy).

## Step 5: Build Your Application & Dockerfile

**Your app needs:**
- Listen on **port 8080**
- `/health` endpoint that returns HTTP 200 (for Kubernetes health checks)
- A `Dockerfile` to containerize it

**See [EXAMPLES.md](EXAMPLES.md) for complete working examples** in Node.js, Python, Go, Java, Ruby, and more.

> **Note:** While health checks are optional initially, they're recommended for production. Without `/health`, your app will still deploy, but Kubernetes won't be able to detect issues or perform graceful restarts.

Copy the example for your language and customize, or create your own if you already know Docker.

**Test locally:**
```bash
docker build -t my-app:test .
docker run -p 8080:8080 my-app:test
curl http://localhost:8080/health  # Should return 200 OK
```

## Step 6: Deploy to Dev

> **Branch → cluster mapping:**
> - Pushing to the **`dev`** branch deploys to the **`us-gke-trust-dev`** cluster (automatic).
> - Merging to the **`main`** branch deploys to the **`us-gke-trust-prod`** cluster (manual trigger required — see Step 7).

```bash
# Commit your changes
git add .
git commit -m "feat: initial app setup"
git push origin dev
```

**What happens next:**
1. GitLab CI/CD pipeline starts automatically
2. **Security scan** runs (trufflehog)
3. **Build stage** - Kaniko builds Docker image
4. **Publish stage** - Image pushed to Artifactory
5. **Deploy stage** - Helm deploys to the **`us-gke-trust-dev`** cluster (namespace: `applications`)

**Monitor the deployment:**
1. Go to https://code.pan.run/your-group/your-app-name/-/pipelines
2. Click on the latest pipeline
3. Watch the `deploy_to_dev` job complete

**Once deployed:**
- Visit: `https://your-app-name.tsdev.paloaltonetworks.com`
- Your app should be live!

## Step 7: Deploy to Production

Merging to `main` triggers a build, but the deploy to the **`us-gke-trust-prod`** cluster requires a manual click in GitLab.

```bash
# Merge dev to main
git checkout main
git pull origin main
git merge dev
git push origin main
```

**Production requires manual approval:**
1. Go to https://code.pan.run/your-group/your-app-name/-/pipelines
2. Find the main branch pipeline
3. Click **Play** button (▶️) on `deploy_to_prod` job (deploys to **`us-gke-trust-prod`**, namespace: `applications`)
4. Wait for deployment to complete

**Once deployed:**
- Visit: `https://your-app-name.ts.paloaltonetworks.com`

## Troubleshooting

### Pipeline stuck - no runner online
**Problem:** Job shows "This job is stuck because the project doesn't have any runners online"

**Solution:**
- Go to **Build → Runners** in GitLab
- Verify runner with tag `us-gke-trust-dev` is online

### Build fails
**Check:**
- Dockerfile syntax
- All COPY commands reference existing files
- Build logs in GitLab for specific error

### Deploy succeeds but app not accessible
```bash
# Check pods
kubectl config use-context us-gke-trust-dev
kubectl get pods -n applications

# Check pod logs
kubectl logs -n applications <pod-name>

# Check ingress
kubectl get ingress -n applications
```

### Health check fails
- Ensure `/health` endpoint returns 200 OK
- Check app is listening on port 8080
- Check app listens on 0.0.0.0:8080, not localhost:8080
- Verify health check path in Dockerfile matches your app

## Next Steps

**Now that your app is deployed, continue with:**

1. **[README.md](../README.md)** - Read the full documentation for:
   - Complete architecture overview
   - All configuration options
   - Customization guide
   - Advanced troubleshooting

2. **Then read based on your needs:**
   - **[ONBOARDING-AUTOMATION.md](ONBOARDING-AUTOMATION.md)** - One-click DNS + GCP service account setup
   - **[DNS-SETUP.md](DNS-SETUP.md)** - DNS reference (mechanics + manual fallback)
   - **[SERVICE-ACCOUNT-SETUP.md](SERVICE-ACCOUNT-SETUP.md)** - GCP service account reference (mechanics + manual fallback)
   - **[BIGQUERY-SETUP.md](BIGQUERY-SETUP.md)** - If your app needs BigQuery
   - **[DATABASE-SETUP.md](DATABASE-SETUP.md)** - If your app needs PostgreSQL
   - **[SSO-AUTHENTICATION.md](SSO-AUTHENTICATION.md)** - To customize or disable SSO
   - **[EXAMPLES.md](EXAMPLES.md)** - More language-specific examples
   - **[CLAUDE.md](../CLAUDE.md)** - If using Claude Code for development

## Common Tasks

### View deployed pods
```bash
kubectl config use-context us-gke-trust-dev
kubectl get pods -n applications -l app=your-app-name
```

### View pod logs
```bash
kubectl logs -n applications <pod-name> -f
```

### Restart deployment
```bash
kubectl rollout restart deployment/your-app-name-deployment -n applications
```

### Check Helm release
```bash
helm list -n applications
helm status your-app-name -n applications
```

## Support

- **GitLab Issues:** Report bugs or request features
- **#engineering-productivity:** Infrastructure issues (Artifactory access, registry problems)
- **Team chat:** General questions

---

Happy coding! 🚀
