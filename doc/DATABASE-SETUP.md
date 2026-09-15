# Database Setup Guide

Most applications need a database. 

**Note:** Teams commonly use **BigQuery** or **PostgreSQL**. 

- **For BigQuery setup:** See [BIGQUERY-SETUP.md](BIGQUERY-SETUP.md)
- **For PostgreSQL setup:** Continue reading below

## Infrastructure Overview

**We use a shared PostgreSQL instance:**
- **Dev:** `postgres.tsdev.paloaltonetworks.com`
- **Prod:** `postgres.ts.paloaltonetworks.com`

Each application gets:
- Its own database with the same name in dev and prod (e.g., `my_app`)
- Its own user with the same name in dev and prod (e.g., `my_app`)
- Its own password (stored in Kubernetes secrets, different for dev and prod)

**Why shared?** Cost-effective, easier to manage, sufficient for most internal tools. Separate instances are only needed for high-traffic apps or compliance requirements.

## Setup Steps

### 1. Create Database and User

You need to create:
- Database: `{app_name}` (same name in both dev and prod)
- User: `{app_name}` (same name in both dev and prod)
- Password: Generate a DIFFERENT secure password for dev and prod

**Why same name?** Since dev and prod use different PostgreSQL instances, using the same database/user name simplifies configuration.

**Option A: Manual (via Cloud SQL Console or psql)**

```sql
-- Connect to DEV PostgreSQL instance (postgres.tsdev.paloaltonetworks.com)
-- Then run these commands (replace {app_name} and {dev_password}):

CREATE DATABASE {app_name};
CREATE USER {app_name} WITH ENCRYPTED PASSWORD '{dev_password}';
GRANT ALL PRIVILEGES ON DATABASE {app_name} TO {app_name};

-- Later, connect to PROD PostgreSQL instance (postgres.ts.paloaltonetworks.com)
-- Then run these commands (replace {app_name} and {prod_password}):

CREATE DATABASE {app_name};
CREATE USER {app_name} WITH ENCRYPTED PASSWORD '{prod_password}';
GRANT ALL PRIVILEGES ON DATABASE {app_name} TO {app_name};
```

**Note:** Use DIFFERENT passwords for dev and prod for security.

**Option B: Terraform (Recommended for teams)**

Add to `gcp-wwss-as-trust-dev-deployment` repo:

```hcl
resource "google_sql_user" "my_app" {
  name     = "my_app"
  instance = google_sql_database_instance.postgres.name
  password = var.my_app_dev_password
}

resource "google_sql_database" "my_app" {
  name     = "my_app"
  instance = google_sql_database_instance.postgres.name
}
```

And add to `gcp-wwss-as-trust-prod-deployment` repo:

```hcl
resource "google_sql_user" "my_app" {
  name     = "my_app"
  instance = google_sql_database_instance.postgres.name
  password = var.my_app_prod_password  # Different password!
}

resource "google_sql_database" "my_app" {
  name     = "my_app"
  instance = google_sql_database_instance.postgres.name
}
```

### 2. Store Passwords in Kubernetes Secrets

**For apps in `applications` namespace:**

```bash
kubectl create secret generic my-app-secrets -n applications \
  --from-literal=db-password='YOUR_DEV_DB_PASSWORD'
```

**For apps in `firebot` namespace:**

```bash
kubectl create secret generic my-app-secrets -n firebot \
  --from-literal=db-password='YOUR_DEV_DB_PASSWORD'
```

**For production:**

```bash
kubectl create secret generic my-app-secrets -n applications \
  --from-literal=db-password='YOUR_PROD_DB_PASSWORD' \
  --context=prod-cluster  # or whatever your prod context is
```

### 3. Configure Helm Values

**Edit `helm/values.yaml` (base config for both environments):**

```yaml
env:
  - name: NODE_ENV
    value: "production"
  - name: DB_USER
    value: "my_app"  # ← Your app name (same for dev and prod)
  - name: DB_NAME
    value: "my_app"  # ← Your app name (same for dev and prod)
  - name: DB_PORT
    value: "5432"
```

**Edit `helm/dev.yaml` (only hostname and secrets differ):**

```yaml
env:
  - name: DB_HOST
    value: "postgres.tsdev.paloaltonetworks.com"
  - name: DB_PASS
    valueFrom:
      secretKeyRef:
        name: my-app-secrets
        key: db-password
```

**Edit `helm/prod.yaml` (only hostname and secrets differ):**

```yaml
env:
  - name: DB_HOST
    value: "postgres.ts.paloaltonetworks.com"  # ← Note: ts not tsdev
  - name: DB_PASS
    valueFrom:
      secretKeyRef:
        name: my-app-secrets
        key: db-password
```

**Benefits of this approach:**
- DB_USER, DB_NAME, DB_PORT are in values.yaml (shared)
- Only DB_HOST differs between dev and prod
- Less duplication, cleaner configuration

### 4. Update Deployment Template

The template is already configured to construct `DATABASE_URL` from individual components:

```yaml
# helm/templates/deployment.yaml already has:
- name: DATABASE_URL
  value: "postgres://$(DB_USER):$(DB_PASS)@$(DB_HOST):$(DB_PORT)/$(DB_NAME)"
```

This automatically builds the connection string from the env vars above.

### 5. Deploy

```bash
git add helm/dev.yaml helm/prod.yaml
git commit -m "feat: configure database connection"
git push origin dev
```

The pipeline will deploy, and your app will connect to the database.

## Using the Database in Your App

### Node.js / TypeScript

**With Drizzle ORM (recommended):**

```typescript
import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error('DATABASE_URL environment variable is not defined');
}

const client = postgres(connectionString, { prepare: false });
const db = drizzle(client);
```

**With pg library:**

```javascript
const { Pool } = require('pg');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});
```

### Python

**With psycopg2:**

```python
import psycopg2
import os

conn = psycopg2.connect(os.environ['DATABASE_URL'])
```

**With SQLAlchemy:**

```python
from sqlalchemy import create_engine
import os

engine = create_engine(os.environ['DATABASE_URL'])
```

### Go

```go
import (
    "database/sql"
    "os"
    _ "github.com/lib/pq"
)

db, err := sql.Open("postgres", os.Getenv("DATABASE_URL"))
```

## Common Issues

### Connection Refused

**Problem:** App can't reach postgres.tsdev.paloaltonetworks.com

**Solution:**
- Verify DNS resolves: `nslookup postgres.tsdev.paloaltonetworks.com`
- Check network policies allow traffic
- Verify you're using the correct hostname (tsdev vs ts)

### Authentication Failed

**Problem:** `FATAL: password authentication failed for user "my_app_dev"`

**Possible causes:**
1. Wrong password in secret
2. User doesn't exist
3. Wrong username

**Fix:**
```bash
# Check what's in the secret
kubectl get secret my-app-secrets -n applications -o jsonpath='{.data.db-password}' | base64 -d

# Verify user exists in PostgreSQL
# Connect to postgres and run: \du
```

### Database Does Not Exist

**Problem:** `FATAL: database "my_app_dev" does not exist`

**Solution:**
```sql
-- Connect to PostgreSQL instance and run:
CREATE DATABASE my_app_dev;
GRANT ALL PRIVILEGES ON DATABASE my_app_dev TO my_app_dev;
```

### SSL/TLS Issues

**Problem:** `SSL connection required`

**Solution:**
Add SSL mode to connection string (the template already handles this via individual env vars, but if constructing manually):

```
postgres://user:pass@host:5432/dbname?sslmode=require
```

## Database Migrations

**Important:** The app-template does **NOT** include automatic migrations. You must add migration logic based on your needs.

### Option 1: Manual Migrations (Recommended for Most Apps)

Run migrations manually before deploying:

**Drizzle Kit (Node.js):**
```bash
npm install drizzle-kit -D
npx drizzle-kit push:pg
```

**Alembic (Python):**
```bash
pip install alembic
alembic upgrade head
```

**migrate (Go):**
```bash
go get -u github.com/golang-migrate/migrate
migrate -database $DATABASE_URL -path ./migrations up
```

### Option 2: Automatic Migrations on Startup (Advanced)

**⚠️ Use with caution:** Can cause race conditions with multiple replicas or long-running migrations.

**When to use:**
- Single replica deployments
- Fast migrations (< 10 seconds)
- Dev environments

**When NOT to use:**
- Multiple replicas (race conditions)
- Long-running migrations (blocks app startup)
- Production with high availability requirements

**Implementation example (Node.js with Drizzle):**

1. **Add migration script** (`src/db/migrate.ts`):
```typescript
import { migrate } from 'drizzle-orm/postgres-js/migrator';
import { db, client } from './index';

async function main() {
  console.log('Running migrations...');
  await migrate(db, { migrationsFolder: './drizzle' });
  console.log('Migrations complete!');
  await client.end();
}

main().catch((err) => {
  console.error('Migration failed!', err);
  process.exit(1);
});
```

2. **Add npm script** (`package.json`):
```json
{
  "scripts": {
    "migrate": "tsx src/db/migrate.ts",
    "start": "node server.js"
  }
}
```

3. **Update Dockerfile CMD**:
```dockerfile
# Run migrations then start app
CMD sh -c "npm run migrate && npm start"
```

**Alternative: Init Container (Kubernetes)**

For production with multiple replicas, use an init container to run migrations once:

```yaml
# helm/templates/deployment.yaml
spec:
  template:
    spec:
      initContainers:
        - name: migrations
          image: {{ .Values.image.registry }}/{{ .Values.k8s.app_name }}:{{ .Values.image.tag }}
          command: ['npm', 'run', 'migrate']
          env:
            # Same env vars as main container
            - name: DATABASE_URL
              value: "postgres://$(DB_USER):$(DB_PASS)@$(DB_HOST):$(DB_PORT)/$(DB_NAME)"
      containers:
        - name: {{ .Values.k8s.app_name }}
          # ... main container config
```

**Pros of init containers:**
- Runs once before pods start
- Prevents race conditions
- Blocks deployment if migrations fail

**Cons:**
- More complex
- Requires same image for migrations and app

## Security Best Practices

### ✅ DO:
- Use separate users for dev and prod
- Use strong, randomly generated passwords
- Store passwords in Kubernetes secrets (never in code or Helm values)
- Grant only necessary privileges
- Rotate passwords periodically
- Use SSL/TLS connections

### ❌ DON'T:
- Commit passwords to git
- Share database users between apps
- Use the same password for dev and prod
- Grant superuser privileges to app users
- Store passwords in environment variables in Helm values files

## Advanced: Connection Pooling

For high-traffic apps, use connection pooling:

**PgBouncer (recommended):**
Deploy a PgBouncer sidecar or shared instance to pool connections.

**App-level pooling:**
Most database libraries support pooling:
- Node.js: `postgres` library has built-in pooling
- Python: SQLAlchemy has connection pooling
- Go: `database/sql` has connection pooling

## Getting Help

- **Database doesn't exist:** Contact team lead or DevOps to create it
- **Connection issues:** Check your app configuration, credentials, network settings
- **Performance issues:** Review query patterns, add indexes
- **Need separate instance:** Discuss with team lead (usually not needed)

## Checklist

Before deploying:
- [ ] Database created in PostgreSQL
- [ ] User created with password
- [ ] Kubernetes secret created with password
- [ ] `helm/dev.yaml` configured with correct DB_USER, DB_NAME, DB_HOST
- [ ] `helm/prod.yaml` configured with correct DB_USER, DB_NAME, DB_HOST
- [ ] Secret name matches in Helm values
- [ ] App code uses `DATABASE_URL` environment variable
- [ ] Deployed and tested connection

---

**For BigQuery setup instead, see [BIGQUERY-SETUP.md](BIGQUERY-SETUP.md)**

**Next:** See [EXAMPLES.md](EXAMPLES.md) for complete application examples with database integration.
