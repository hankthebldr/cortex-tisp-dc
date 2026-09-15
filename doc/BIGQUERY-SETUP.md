# BigQuery Setup Guide

This guide explains how to set up BigQuery access for your application using Google Cloud Workload Identity.

## Overview

**BigQuery with Workload Identity:**
- No credentials or passwords to manage
- Service accounts are automatically mapped between Kubernetes and GCP
- IAM permissions control what your app can access
- Same service account name in dev and prod, different GCP projects

## Prerequisites: Terraform Module (REQUIRED)

**⚠️ Important:** All apps deployed with this template **MUST** be added to the Terraform infrastructure module for GCP service account creation and workload identity binding.

### What You Need to Do

Your app must be added to the `gcp-wwss-as-trust-module` Terraform module. This creates:
1. GCP service account (in dev and prod projects)
2. Workload identity binding (links Kubernetes SA to GCP SA)
3. IAM permissions (BigQuery, Storage, etc.)

### How to Request This

**Option A: Create the Terraform file yourself (if you have access)**

1. Clone the module repository:
   ```bash
   git clone https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module.git
   ```

2. Create `my-app.tf` in the repository root:
   ```terraform
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

   resource "google_project_iam_member" "my_app_bq_data_viewer" {
     project = var.gcp_project  # the app's own project (wwss-as-trust-dev / -prod)
     role    = "roles/bigquery.dataViewer"
     member  = "serviceAccount:${google_service_account.my_app.email}"
   }

   resource "google_project_iam_member" "my_app_bq_job_user" {
     project = var.gcp_project
     role    = "roles/bigquery.jobUser"
     member  = "serviceAccount:${google_service_account.my_app.email}"
   }
   ```

3. Update `gcp-wwss-as-trust-dev-deployment/main.tf` to add your domain:
   ```terraform
   ingress_app_domain_names = [
     # ... existing domains ...
     "my-app.tsdev.paloaltonetworks.com."
   ]
   ```

4. Create MR and get it reviewed/merged

5. Terraform apply runs automatically via GitLab CI/CD

**Option B: Request via ticket/Slack (if you don't have access)**

Contact the infrastructure team with:
- App name: `my-app`
- Kubernetes namespace: `applications`
- Kubernetes SA name: `my-app-sa` (follows naming convention)
- GCP permissions needed:
  - BigQuery: `roles/bigquery.dataViewer`, `roles/bigquery.jobUser`
  - Project: `wwss-as-trust-dev` / `wwss-as-trust-prod` (the app's own project, where its BigQuery dataset lives)
- Domains: `my-app.tsdev.paloaltonetworks.com`, `my-app.ts.paloaltonetworks.com`

### What the Terraform Module Creates

For **each environment** (dev and prod):

1. **GCP Service Account:**
   - Dev: `my-app@wwss-as-trust-dev.iam.gserviceaccount.com`
   - Prod: `my-app@wwss-as-trust-prod.iam.gserviceaccount.com`

2. **Workload Identity Binding:**
   - Links Kubernetes SA `applications/my-app-sa` to GCP SA
   - Allows pods to automatically use GCP credentials

3. **IAM Permissions:**
   - Grants BigQuery access to specified projects
   - Can include Cloud Storage, Pub/Sub, etc.

### Verify Terraform Applied Successfully

After Terraform runs:

```bash
# Check GCP service account exists
gcloud iam service-accounts list --project=wwss-as-trust-dev --filter="email:my-app@"

# Check workload identity binding
gcloud iam service-accounts get-iam-policy \
  my-app@wwss-as-trust-dev.iam.gserviceaccount.com \
  --project=wwss-as-trust-dev
```

You should see `roles/iam.workloadIdentityUser` binding.

## Using BigQuery in Your App (After Terraform Setup)

Once the Terraform module is applied and your GCP service account exists:

### 1. Verify Your App Name Matches

Make sure `helm/values.yaml` uses the same app name you used in Terraform:

```yaml
k8s:
  app_name: "my-app"  # Must match Terraform service account name
```

### 2. No Helm Configuration Needed

The template automatically:
- Creates Kubernetes service account: `my-app-sa`
- Annotates it with workload identity: `iam.gke.io/gcp-service-account: my-app@{project}.iam.gserviceaccount.com`

**The Terraform module already created the GCP service account and workload identity binding** - the Helm chart just references it.

### 3. Add BigQuery Client to Your App

Now skip to the [code examples below](#add-bigquery-client-code) to use BigQuery in your application.

---

## Manual Setup (Alternative - Not Recommended)

**Use this only if you can't use the Terraform module for some reason.**

The manual approach requires you to create service accounts and bindings yourself.

### 1. Create GCP Service Account Manually

You need to create a service account in both dev and prod GCP projects.

**Service account name:** Use your app name (e.g., `my-app`)

**Dev project:** `wwss-as-trust-dev`
**Prod project:** `wwss-as-trust-prod`

**Option A: Using gcloud CLI**

```bash
# Create service account in dev
gcloud iam service-accounts create my-app \
  --project=wwss-as-trust-dev \
  --display-name="My App Service Account"

# Create service account in prod
gcloud iam service-accounts create my-app \
  --project=wwss-as-trust-prod \
  --display-name="My App Service Account"
```

**Option B: Using GCP Console**

1. Go to https://console.cloud.google.com/iam-admin/serviceaccounts
2. Select project `wwss-as-trust-dev`
3. Click **Create Service Account**
4. Name: `my-app`
5. Click **Create and Continue**
6. Skip roles for now (we'll add them in next step)
7. Click **Done**
8. Repeat for `wwss-as-trust-prod`

### 2. Grant BigQuery Permissions

Grant your service account permissions to access BigQuery datasets.

**Common permissions:**
- `roles/bigquery.dataViewer` - Read data from tables
- `roles/bigquery.dataEditor` - Read and write data
- `roles/bigquery.jobUser` - Run queries

**Using gcloud:**

```bash
# Grant permissions in dev (grant on the app's own project)
gcloud projects add-iam-policy-binding wwss-as-trust-dev \
  --member="serviceAccount:my-app@wwss-as-trust-dev.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding wwss-as-trust-dev \
  --member="serviceAccount:my-app@wwss-as-trust-dev.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Grant permissions in prod
gcloud projects add-iam-policy-binding wwss-as-trust-prod \
  --member="serviceAccount:my-app@wwss-as-trust-prod.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding wwss-as-trust-prod \
  --member="serviceAccount:my-app@wwss-as-trust-prod.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```

**Note:** If your app's BigQuery data lives in a different project, replace the target project accordingly. The standard pattern is to grant on the app's own project.

**Using GCP Console:**

1. Go to the BigQuery project (e.g., `wwss-as-trust-dev`)
2. Navigate to **IAM & Admin → IAM**
3. Click **Grant Access**
4. Add principal: `my-app@wwss-as-trust-dev.iam.gserviceaccount.com`
5. Select roles: `BigQuery Data Viewer` and `BigQuery Job User`
6. Click **Save**
7. Repeat for prod service account

### 3. Enable Workload Identity Binding

This allows your Kubernetes service account to impersonate the GCP service account.

```bash
# Bind Kubernetes SA to GCP SA in dev
gcloud iam service-accounts add-iam-policy-binding \
  my-app@wwss-as-trust-dev.iam.gserviceaccount.com \
  --project=wwss-as-trust-dev \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:wwss-as-trust-dev.svc.id.goog[applications/my-app-sa]"

# Bind Kubernetes SA to GCP SA in prod
gcloud iam service-accounts add-iam-policy-binding \
  my-app@wwss-as-trust-prod.iam.gserviceaccount.com \
  --project=wwss-as-trust-prod \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:wwss-as-trust-prod.svc.id.goog[applications/my-app-sa]"
```

**Note:** The Kubernetes service account name is `{app-name}-sa` in the `applications` namespace (e.g., `my-app-sa`).

### 4. Configure Helm Values

The template automatically creates the service account based on your app name.

**No additional configuration needed.** The service account name is automatically set to `k8s.app_name` from `helm/values.yaml`.

The service account template (`helm/templates/sa.yaml`) automatically:
- Creates Kubernetes service account: `{app-name}-sa`
- Adds workload identity annotation linking to GCP service account: `{app-name}@{project}.iam.gserviceaccount.com`

### 5. Add BigQuery Client Code

<a name="add-bigquery-client-code"></a>

**Node.js / JavaScript:**

```bash
npm install @google-cloud/bigquery
```

```javascript
import { BigQuery } from '@google-cloud/bigquery';

// Initialize BigQuery client (uses Application Default Credentials)
const bigquery = new BigQuery({
  projectId: 'wwss-as-trust-dev',  // Your BigQuery project
});

// Environment-specific table names
const tableName = process.env.NODE_ENV === 'production'
  ? 'wwss-as-trust-dev.appsheet_prod.my_table'
  : 'wwss-as-trust-dev.appsheet_prod.my_table_dev';

// Query example
async function queryData() {
  const query = `SELECT * FROM \`${tableName}\` LIMIT 10`;
  const [rows] = await bigquery.query(query);
  return rows;
}
```

**Python:**

```bash
pip install google-cloud-bigquery
```

```python
from google.cloud import bigquery
import os

# Initialize BigQuery client (uses Application Default Credentials)
client = bigquery.Client(project='wwss-as-trust-dev')

# Environment-specific table name
table_name = 'wwss-as-trust-dev.appsheet_prod.my_table'
if os.getenv('NODE_ENV') != 'production':
    table_name = 'wwss-as-trust-dev.appsheet_prod.my_table_dev'

# Query example
def query_data():
    query = f"SELECT * FROM `{table_name}` LIMIT 10"
    results = client.query(query)
    return [dict(row) for row in results]
```

**Go:**

```bash
go get cloud.google.com/go/bigquery
```

```go
package main

import (
    "context"
    "cloud.google.com/go/bigquery"
)

func main() {
    ctx := context.Background()
    
    // Initialize BigQuery client (uses Application Default Credentials)
    client, err := bigquery.NewClient(ctx, "wwss-as-trust-dev")
    if err != nil {
        log.Fatal(err)
    }
    defer client.Close()
    
    // Query example
    query := client.Query("SELECT * FROM `wwss-as-trust-dev.appsheet_prod.my_table` LIMIT 10")
    // ... execute query
}
```

## Best Practices

### Use Environment-Specific Tables

Don't mix dev and prod data. Use different tables:

```javascript
const tableName = process.env.NODE_ENV === 'production'
  ? 'project.dataset.table'
  : 'project.dataset.table_dev';
```

### Connection Pooling

BigQuery clients handle connection management automatically. Just create one client instance and reuse it:

```javascript
// Good: Single client instance
const bigquery = new BigQuery({ projectId: 'wwss-as-trust-dev' });

// Bad: Creating new clients for each query
function queryData() {
  const bigquery = new BigQuery({ projectId: 'wwss-as-trust-dev' });  // Don't do this
  // ...
}
```

### Query Optimization

- Use `LIMIT` for testing queries
- Avoid `SELECT *` - specify only needed columns
- Use partitioned tables for large datasets
- Cache results when possible

### Error Handling

```javascript
try {
  const [rows] = await bigquery.query(query);
  return rows;
} catch (error) {
  console.error('BigQuery error:', error);
  throw error;
}
```

## Local Development

**Option A: Use Application Default Credentials**

1. Install gcloud CLI
2. Run `gcloud auth application-default login`
3. Your app will use your personal credentials locally

**Option B: Use Service Account Key (Not Recommended for Production)**

1. Download service account key from GCP Console
2. Set environment variable:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/keyfile.json"
   ```
3. **Important:** Never commit key files to git

## Troubleshooting

### Error: "User does not have permission to access dataset"

**Solution:**
- Check service account has BigQuery permissions
- Verify permissions are on the correct project (where BigQuery data lives)
- Make sure you granted both `dataViewer` and `jobUser` roles

```bash
# Check current permissions
gcloud projects get-iam-policy wwss-as-trust-dev \
  --flatten="bindings[].members" \
  --filter="bindings.members:my-app@wwss-as-trust-dev.iam.gserviceaccount.com"
```

### Error: "Could not find workload identity pool"

**Solution:**
- Check workload identity binding was created correctly
- Verify Kubernetes service account name matches (should be `{app-name}-sa`)

```bash
# Check binding
gcloud iam service-accounts get-iam-policy \
  my-app@wwss-as-trust-dev.iam.gserviceaccount.com \
  --project=wwss-as-trust-dev
```

### Error: "Application Default Credentials not found"

**In Kubernetes:**
- Verify deployment uses the correct service account in `helm/templates/deployment.yaml`
- Check service account has workload identity annotation

**Locally:**
- Run `gcloud auth application-default login`
- Or set `GOOGLE_APPLICATION_CREDENTIALS` to key file path

### Query returns empty results

**Check:**
- Table name is correct (including project and dataset)
- Environment-specific table exists (dev vs prod)
- Service account has access to the dataset
- Table actually contains data

```bash
# List tables in dataset
bq ls wwss-as-trust-dev:appsheet_prod

# Check table schema and preview
bq show wwss-as-trust-dev:appsheet_prod.my_table
bq head -n 10 wwss-as-trust-dev:appsheet_prod.my_table
```

## Getting Help

- **BigQuery permissions:** Check with data owner or team lead
- **GCP service accounts:** Contact team lead or DevOps
- **Infrastructure issues:** Contact #engineering-productivity (GCP access, IAM issues)

## Checklist

Before deploying:
- [ ] GCP service account created in dev and prod
- [ ] BigQuery permissions granted (dataViewer, jobUser)
- [ ] Workload identity binding configured
- [ ] `helm/values.yaml` updated with service account name
- [ ] BigQuery client installed in app
- [ ] Tested locally with `gcloud auth application-default login`
- [ ] Environment-specific table names configured
- [ ] Deployed to dev and verified queries work

---

**For PostgreSQL setup instead, see [DATABASE-SETUP.md](DATABASE-SETUP.md)**
