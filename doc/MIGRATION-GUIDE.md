# Migration Guide - Existing Apps to Template

Guide for adding CI/CD and deployment infrastructure to an existing application repository.

> **💡 Language Examples:** See [EXAMPLES.md](EXAMPLES.md) for complete Dockerfile and app examples in Node.js, Python, Go, Java, Ruby, React, and more!

## Overview

If you already have an application repository and want to add the GitLab CI/CD pipeline and Helm deployment, follow this guide instead of starting from the template.

**What you'll add:**
- GitLab CI/CD pipeline (`.gitlab-ci.yml`)
- Helm deployment charts (`helm/` directory)
- Dockerfile (if you don't have one)
- Documentation

**What you'll keep:**
- Your application source code
- Existing dependencies and configs
- Git history

## Prerequisites

- [ ] Existing application repository in code.pan.run
- [ ] Application runs locally and works
- [ ] You know what port your app listens on
- [ ] Access to the app-template repository

## Migration Steps

### Step 1: Backup and Switch to Dev Branch

```bash
# Backup your current state
cd /path/to/your-app
git checkout main
git checkout -b backup-before-migration
git push origin backup-before-migration

# Switch to dev branch (create if it doesn't exist)
git checkout dev || git checkout -b dev
git push origin dev
```

**Why dev first?** Test the migration in dev environment before deploying to production.

### Step 2: Copy Template Files

**Clone the template repo alongside your app:**
```bash
cd /path/to/projects
git clone https://code.pan.run/reference-architectures/app-template.git
```

**Copy these files to your app repo:**
```bash
cd /path/to/your-app

# Copy CI/CD pipeline
cp ../app-template/.gitlab-ci.yml .

# Copy Helm charts (entire directory)
cp -r ../app-template/helm .

# Copy .gitignore (merge with existing if you have one)
cp ../app-template/.gitignore .

# Optional: Copy documentation templates
cp ../app-template/CLAUDE.md .
cp ../app-template/GETTING-STARTED.md .
```

**If you don't have a Dockerfile:**
```bash
cp ../app-template/Dockerfile .
# Then customize it for your language/framework (see Step 4)
```

### Step 3: Configure Branch Protection (REQUIRED)

**Important:** The CI/CD pipeline uses protected group-level variables for Artifactory credentials. These variables only work on protected branches.

**Protect your branches:**

1. Go to your project in GitLab: `https://code.pan.run/your-group/my-existing-app`
2. Navigate to **Settings → Repository**
3. Expand **Protected branches**
4. Protect the `main` branch (if not already protected):
   - Branch: `main`
   - Allowed to merge: **Maintainers**
   - Allowed to push: **Maintainers**
   - Click **Protect**
5. Create and protect the `dev` branch:
   ```bash
   git checkout -b dev
   git push -u origin dev
   ```
   Then in GitLab:
   - Branch: `dev`
   - Allowed to merge: **Developers + Maintainers** (or **Maintainers** only)
   - Allowed to push: **Developers + Maintainers** (or **Maintainers** only)
   - Click **Protect**

**Why is this required?**
- The `ARTIFACTORY_API_USERNAME` and `ARTIFACTORY_API_PASSWORD` variables are marked as "Protected" at the group level
- Protected variables are only available to protected branches
- Without this, the `kaniko upload artifactory` job will fail with authentication errors

### Step 4: Customize Dockerfile for Your App

**See EXAMPLES.md for complete Dockerfile examples for your language:**
- Node.js / Express
- Python / Flask or FastAPI
- Python / Django
- Go
- Java / Spring Boot
- Ruby / Rails
- React / Static (with nginx)

**Quick reference in `Dockerfile.example`** for common patterns.

**Required elements in your Dockerfile:**
- Multi-stage build (keeps image small)
- Non-root user (security)
- EXPOSE statement (your app's port)
- HEALTHCHECK (for Kubernetes)

**Test your Dockerfile locally:**
```bash
docker build -t my-app-test .
docker run -p 8080:8080 my-app-test
curl http://localhost:8080/health     # Test health endpoint
```

If the build fails, check:
- All files referenced in COPY exist
- Dependency files are correct (package.json, requirements.txt, etc.)
- Port number matches your app

### Step 5: Update Helm Configuration

**Edit `helm/values.yaml` - Change ONLY the app name:**
```yaml
k8s:
  app_name: "my-existing-app"  # ← CHANGE THIS (everything else auto-configures!)
```

**That's it!** The following are automatically configured from `app_name`:
- Docker image: `docker-ra.art.code.pan.run/my-existing-app`
- Dev URL: `my-existing-app.tsdev.paloaltonetworks.com`
- Prod URL: `my-existing-app.ts.paloaltonetworks.com`
- Service accounts: K8s `my-existing-app-sa`, GCP `my-existing-app@{project}.iam.gserviceaccount.com`

**Note:** Port 8080 is already configured. Just make sure your app listens on port 8080!

**If your app needs environment variables:**

Edit `helm/templates/deployment.yaml` and add them:
```yaml
env:
  - name: GOOGLE_CLOUD_PROJECT
    value: "{{ .Values.gcp.project_id }}"
  # Add your app's env vars here:
  - name: DATABASE_URL
    value: "postgres://..."
  - name: API_KEY
    valueFrom:
      secretKeyRef:
        name: my-app-secrets
        key: api-key
```

### Step 6: Add Health Check Endpoint

**Your app MUST have a `/health` endpoint** for Kubernetes health probes.

**See EXAMPLES.md for health check implementation in your language:**
- Complete working examples for Node.js, Python, Go, Java, Ruby, etc.
- Shows exactly where to add the endpoint in each framework

**Requirements:**
- Path: `/health`
- Method: GET
- Response: HTTP 200 with JSON like `{"status":"healthy"}`

**Test it:**
```bash
# Start your app locally
# (use your language's run command)

# Test health endpoint
curl http://localhost:8080/health
# Should return: {"status":"healthy"}
```

**Common mistake:** Health endpoint returns 404 - make sure you added the route!

### Step 7: Update .gitlab-ci.yml (If Needed)

The template `.gitlab-ci.yml` should work as-is, but check these:

**If your project name != image name:**
```yaml
variables:
  IMAGE_NAME_TEMPLATE: 'my-custom-image-name'  # Override project name
```

**If you need build arguments:**
```yaml
variables:
  KANIKO_EXTRA_ARGS: '--build-arg NODE_ENV=production --build-arg VERSION=1.0.0'
```

**If your app needs special build resources:**
```yaml
kaniko build artifactory:
  variables:
    KUBERNETES_MEMORY_REQUEST: "16Gi"  # Increase if needed
    KUBERNETES_MEMORY_LIMIT: "16Gi"
```

### Step 8: Test the Migration in Dev

**1. Commit changes to dev:**
```bash
# You should already be on dev branch from Step 1
git add .
git commit -m "feat: add CI/CD pipeline and Helm deployment"
git push origin dev
```

**2. Watch the pipeline:**
- Go to GitLab → CI/CD → Pipelines
- Pipeline automatically starts on push to dev
- Watch for errors in:
  - Security scan
  - Docker build (kaniko)
  - Publish
  - Deploy to dev (runs automatically)

**3. Verify deployment in dev:**
```bash
# Wait for deploy_to_dev job to complete
# Visit: https://my-app.tsdev.paloaltonetworks.com
```

**4. Verify deployment:**
```bash
kubectl config use-context us-gke-trust-dev
kubectl get pods -n applications -l app=my-existing-app
kubectl logs -n applications <pod-name>
kubectl get ingress -n applications
```

### Step 9: Deploy to Production

**Once dev is working successfully:**
```bash
# Merge dev to main
git checkout main
git merge dev
git push origin main

# In GitLab, manually trigger deploy_to_prod job
# CI/CD → Pipelines → Click latest pipeline → deploy_to_prod → Click "Play" button

# Visit: https://my-app.ts.paloaltonetworks.com
```

**Clean up (optional):**
```bash
# Delete backup branch if everything is working
git push origin --delete backup-before-migration
```

## Migration Checklist

Use this checklist to ensure you've completed all steps:

### Files Added
- [ ] `.gitlab-ci.yml` - CI/CD pipeline
- [ ] `helm/Chart.yaml` - Helm chart metadata
- [ ] `helm/values.yaml` - Default configuration
- [ ] `helm/dev.yaml` - Dev environment config
- [ ] `helm/prod.yaml` - Prod environment config
- [ ] `helm/templates/deployment.yaml` - Kubernetes deployment
- [ ] `helm/templates/service.yaml` - Kubernetes service
- [ ] `helm/templates/ingress.yaml` - HTTPS ingress
- [ ] `helm/templates/sa.yaml` - Service account
- [ ] `Dockerfile` - Container image build (if you didn't have one)
- [ ] `.gitignore` - Updated with Helm/Docker ignores
- [ ] `CLAUDE.md` - Claude Code guidance (optional)

### Configuration Updated
- [ ] `helm/values.yaml` → `app_name` matches your app
- [ ] `helm/values.yaml` → `app_targetPort` matches your app's port
- [ ] `helm/values.yaml` → `image.repo` uses your app name
- [ ] `helm/dev.yaml` → `hostnames` set to your dev URL
- [ ] `helm/prod.yaml` → `hostnames` set to your prod URL
- [ ] `Dockerfile` → Customized for your language/framework
- [ ] `Dockerfile` → Port matches your app (`EXPOSE 8080`)
- [ ] App has `/health` endpoint implemented

### Testing Completed
- [ ] Docker build works locally: `docker build -t test .`
- [ ] Docker container runs: `docker run -p 8080:8080 test`
- [ ] Health check works: `curl http://localhost:8080/health`
- [ ] GitLab pipeline runs successfully
- [ ] Image pushed to Artifactory
- [ ] Deployed to dev cluster successfully
- [ ] App accessible via dev URL
- [ ] Logs show no errors: `kubectl logs -n applications <pod>`

### Deployment Verified
- [ ] Pods running: `kubectl get pods -n applications`
- [ ] Service exists: `kubectl get svc -n applications`
- [ ] Ingress configured: `kubectl get ingress -n applications`
- [ ] App responds: `curl https://my-app.tsdev.paloaltonetworks.com`
- [ ] Health endpoint works: `curl https://my-app.tsdev.paloaltonetworks.com/health`

## Common Migration Issues

### Issue: Docker build fails with "COPY failed"
**Cause:** Files referenced in Dockerfile don't exist

**Solution:**
```bash
# Check what files you're trying to COPY
cat Dockerfile | grep COPY

# Ensure those files exist
ls -la package.json  # or requirements.txt, go.mod, etc.

# Update Dockerfile to match your actual files
```

### Issue: App crashes in container (CrashLoopBackOff)
**Cause:** App can't start in containerized environment

**Solution:**
```bash
# Check pod logs
kubectl logs -n applications <pod-name>

# Common fixes:
# 1. App not listening on 8080 - Check your app configuration
# 2. Wrong port binding - App must listen on 0.0.0.0:8080, not localhost
# 3. Missing environment variables - Add to deployment.yaml
# 4. Missing dependencies - Check Dockerfile installs everything
# 5. Wrong command - Check CMD in Dockerfile
```

### Issue: Health check fails
**Cause:** `/health` endpoint not implemented or wrong path

**Solution:**
```bash
# Test health endpoint locally first
curl http://localhost:8080/health

# If it doesn't exist, add it to your app
# If it's a different path, update deployment.yaml health probes
```

### Issue: "No runner online" error
**Cause:** Job uses wrong tags or runner is offline

**Solution:**
```bash
# Check runners are online
# GitLab → Build → Runners
# Should see: us-gke-trust-dev (green)

# Check job tags match in .gitlab-ci.yml:
tags:
  - us-gke-trust-dev  # For dev
  - us-gke-trust-prod # For prod
```

### Issue: App not accessible via URL
**Cause:** Ingress misconfigured or DNS not updated

**Solution:**
```bash
# Check ingress exists
kubectl get ingress -n applications

# Check hostname matches
kubectl get ingress -n applications -o yaml | grep host

# Verify it matches helm/dev.yaml or helm/prod.yaml

# Check pods are running
kubectl get pods -n applications
```

### Issue: Image pull error (ImagePullBackOff)
**Cause:** Image doesn't exist in Artifactory

**Solution:**
```bash
# Check image was pushed by pipeline
# GitLab → CI/CD → Pipelines → kaniko upload artifactory job

# Check image exists in Artifactory
# Login to https://art.code.pan.run
# Search for your app name

# Check image tag matches
# helm/dev.yaml should have correct tag (set by CI/CD)
```

## Differences from Starting with Template

**Advantages of migrating:**
- ✅ Keep your git history
- ✅ Keep your existing code structure
- ✅ Keep your existing dependencies

**Disadvantages:**
- ❌ More manual configuration
- ❌ Need to adapt Dockerfile to your app
- ❌ Need to ensure health endpoint exists
- ❌ May have conflicts with existing files

**Starting fresh with template:**
- ✅ Everything pre-configured
- ✅ Example app to reference
- ✅ Less chance of misconfiguration
- ❌ Lose git history (unless you migrate history too)

## Getting Help

**If you get stuck during migration:**

1. **Check the logs:**
   - GitLab pipeline logs for build errors
   - `kubectl logs` for runtime errors

2. **Compare with template:**
   - Look at working example in app-template repo
   - Check what's different in your config

3. **Test incrementally:**
   - First: Docker build locally
   - Then: Push and test CI/CD build
   - Finally: Test deployment

4. **Ask for help:**
   - Create issue in app-template repo
   - Share specific error messages
   - Include what you've tried

## Next Steps After Migration

1. **Update documentation:**
   - Update your README.md with deployment info
   - Document any custom configuration
   - Add CLAUDE.md if using AI-assisted development

2. **Set up production:**
   - Test deployment to prod
   - Configure production secrets
   - Set up monitoring/alerts

3. **Train your team:**
   - Show them how to deploy
   - Document common operations
   - Create runbook for troubleshooting

## Migration Timeline Estimate

- **Simple app (Node.js/Python):** 1-2 hours
- **Complex app (with database, external services):** 3-5 hours
- **App needing major Dockerfile changes:** 4-6 hours

Add 1-2 hours for testing and troubleshooting in each case.

---

**Need help?** Create an issue in the app-template repository with:
- Your app's language/framework
- Error messages you're seeing
- What you've tried so far
