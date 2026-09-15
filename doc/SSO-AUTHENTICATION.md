# SSO Authentication (nginx + goggles + Vouch + Okta)

This template includes SSO (Single Sign-On) authentication by default. Users must authenticate via corporate SSO (Okta) before accessing your application.

## How It Works

**Architecture:**
```
User → Ingress (TLS) → nginx + goggles (auth check) → Vouch → Okta (IdP)
                              ↓ (if authenticated)
                           Your App
```

**Components:**
- **nginx**: Reverse proxy that handles authentication checks
- **goggles**: SSO validation service (validates Vouch JWT tokens)
- **Vouch**: SSO proxy that connects to Okta, creates JWT tokens (managed centrally)
- **Okta**: Corporate identity provider (handles actual user authentication)

**Authentication Flow:**
1. User visits your app URL
2. nginx + goggles check for valid Vouch JWT token
3. If authenticated → request proxies to your app
4. If not authenticated → redirects to Vouch → Vouch redirects to Okta login
5. User logs in via Okta
6. Okta returns to Vouch → Vouch creates JWT → redirects back to your app
7. goggles validates JWT → nginx proxies request to your app

**User information headers:**
Your app receives authenticated user information via HTTP headers:
- `X-Username`: User's email (e.g., "jdoe@paloaltonetworks.com")
- `X-First-Name`: User's first name
- `X-Last-Name`: User's last name
- `X-Groups`: User's group memberships (comma-separated)

## Okta SSO Configuration (Vouch is Centralized)

**Important:** Apps using this template **do NOT need individual Okta SSO apps**. Vouch is a centralized SSO proxy already configured in Okta.

**What this means:**
- ✅ You don't request a new Okta SSO app for your template-based app
- ✅ Vouch handles authentication for all apps behind it
- ✅ Your app simply receives authenticated user info via headers
- ✅ Users access your app via Imanami group membership

**How Vouch is configured in Okta:**
- **Group Assignments:** Determines WHO can access Vouch (and thus any app behind it)
- **Groups Claim:** Vouch receives all user groups from Okta and passes them to apps
- **Return Groups:** Configured to return user's groups in the authentication token

**You don't see individual apps in Okta - you see Vouch.** All template-based apps share the same Vouch authentication.

### Reference: How Okta SSO Apps Work (You Don't Need This)

This section is for understanding only. **Template-based apps don't need individual Okta apps.**

When creating a new Okta SSO app (SAML or OIDC), admins configure:

1. **Group Assignments** - Which AD group controls access to the app
   - A group is automatically created and assigned to the app
   - Users gain access by being added to this group via Imanami
   - The app owner can modify the group via Imanami

2. **Groups Claim** - What groups Okta returns to the app
   - **All groups** - Returns all groups the user belongs to
   - **Apply a filter** - Returns only groups matching a pattern
   - **No groups** - Returns no group information
   
   The "Group Assignments" controls access TO the app.
   The "Groups Claim" controls what groups are sent IN the token (for authorization within the app).

**For Vouch:** The Okta admin configured Vouch to receive and pass all user groups.

## Group Management with Imanami and Active Directory

**Where groups come from:**

User groups in the `X-Groups` header originate from **Active Directory (AD)** and are managed via **Imanami**.

**The complete flow:**
1. **Imanami** - Front-end tool for managing AD groups
   - App owners add/remove users from their assigned AD groups
   - Can add individuals or distribution lists (DLs)
   - Can perform bulk imports via CSV
   - Access via Okta dashboard → Search "Imanami"

2. **Active Directory (AD)** - Source of truth for groups
   - Groups are stored here (e.g., `sg-<APP_NAME>-sso-users`)
   - When Okta SSO apps are created, an AD security group is automatically created
   - Naming convention: `sg-<APP_NAME>-sso-users`
   - **Sync time:** 1-2 hours from Imanami changes to AD to Okta

3. **Okta** - Syncs groups FROM Active Directory via LDAP
   - Automatically pulls group membership from AD
   - Includes groups in authentication responses
   - You do NOT manage groups directly in Okta

4. **Vouch** - Receives groups from Okta and creates JWT with groups in `CustomClaims`

5. **goggles** - Validates JWT and extracts groups from `CustomClaims`

6. **Your app** - Receives groups via `X-Groups` header

**Example `X-Groups` header value:**
```
X-Groups: ENGINEERING,DATA-SCIENCE-TEAM,ALL-EMPLOYEES
```

### How to Add Users to Groups

**To give someone access to your app, you add them to your app's AD group via Imanami:**

**Steps:**

1. **Access Imanami:**
   - Go to Okta dashboard
   - Search for "Imanami" and open the app
   - This is the web UI for managing Active Directory groups

2. **Find your app's group:**
   - Navigate to "My Groups"
   - Find your app's group (typically named `sg-<app-name>-sso-users`)
   - Example: `sg-myapp-sso-users`

3. **Add users:**
   - Click the "Members" tab
   - Add users by:
     - **Individuals** - Search and add specific users
     - **Distribution lists** - Add entire DLs
     - **Bulk import** - Upload CSV file with multiple users

4. **Wait for sync (1-2 hours):**
   - Changes made in Imanami sync to Active Directory
   - Active Directory syncs to Okta via LDAP
   - After sync completes, users can access your app

**That's it!** Users will authenticate via Vouch and Okta automatically once they're in the group.

**Example scenario:**
- Your app requires users to be in "DATA-SCIENCE-TEAM" group for admin features
- User authenticates → Gets all their groups from AD via Okta → Vouch passes to app → App receives via `X-Groups` header
- If "DATA-SCIENCE-TEAM" is in the header → Allow admin access
- If not → Return 403 Forbidden for admin routes

**Important Notes:**
- **Basic authentication:** Handled by Vouch (all authenticated users can access the app)
- **Authorization within app:** Use `X-Groups` header to control features/routes
- **Group naming:** AD groups typically follow `sg-<APP_NAME>-sso-users` convention
- **Sync delay:** Allow 1-2 hours after adding users in Imanami before they can access the app

### Using Groups for Authorization

**In your application code, use groups to control access:**

**Node.js example:**
```javascript
app.get('/admin', (req, res) => {
  const groups = req.headers['x-groups']?.split(',') || [];
  
  if (!groups.includes('ADMIN-GROUP')) {
    return res.status(403).send('Forbidden: Admin access required');
  }
  
  // Admin-only functionality
  res.render('admin-dashboard');
});
```

**Python example:**
```python
from fastapi import Request, HTTPException

@app.get("/admin")
async def admin_page(request: Request):
    groups = request.headers.get("x-groups", "").split(",")
    
    if "ADMIN-GROUP" not in groups:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return {"page": "admin-dashboard"}
```

**Go example:**
```go
func adminHandler(w http.ResponseWriter, r *http.Request) {
    groupsHeader := r.Header.Get("X-Groups")
    groups := strings.Split(groupsHeader, ",")
    
    hasAdminAccess := false
    for _, group := range groups {
        if group == "ADMIN-GROUP" {
            hasAdminAccess = true
            break
        }
    }
    
    if !hasAdminAccess {
        http.Error(w, "Admin access required", http.StatusForbidden)
        return
    }
    
    // Admin functionality
}
```

### Using Groups with goggles Rules

You can also enforce group-based access at the **goggles level** (before requests reach your app).

**Edit `helm/templates/sso.yaml` - goggles ConfigMap:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Values.k8s.app_name }}-goggles-config-map
data:
  goggles.yaml: |
    pk_url: {{ .Values.auth_public_key_url }}
    
    # Require users to be in specific groups
    default_action: deny
    rules:
      - name: Allow engineering team
        match_any:
          groups:
            - ENGINEERING
            - DATA-SCIENCE-TEAM
        action: permit
    
    # Allow unauthenticated access to health check
    unauthenticated_paths:
      - /health
      - /api/health
```

**Path-based group rules:**

```yaml
# Different groups for different paths
paths:
  - path: /admin/*
    rules:
      - match_any:
          groups:
            - ADMIN-GROUP
        action: permit
  
  - path: /api/*
    rules:
      - match_any:
          groups:
            - ENGINEERING
            - DATA-SCIENCE-TEAM
        action: permit
  
  - path: /*
    action: permit  # Everyone can access other paths
```

**See [goggles documentation](https://gitlab.com/panw-gse/ts/goggles) for more examples.**

### How to Add Users to Groups

**If you need to grant access to your app:**
1. **Contact IT or Identity Management team**
2. **Request:** "Add user X to group Y in Imanami"
3. **Wait for sync** - Imanami → Okta sync happens automatically (may take a few minutes to hours)
4. **User logs out and back in** - Groups are included in new JWT token

**Important:** Group changes require the user to **re-authenticate** (logout/login) to get a new JWT with updated groups.

### Troubleshooting Groups

**User says "I was added to the group but still can't access":**

1. **Have them logout and login again** - Groups are in the JWT, which is cached
2. **Check they were added to the correct group name** - Case-sensitive, spelling matters
3. **Verify group appears in header:**
   ```javascript
   // Add temporary logging
   console.log('User groups:', req.headers['x-groups']);
   ```
4. **Check Imanami → Okta sync completed** - May take time to propagate

**Group not appearing in `X-Groups` header:**

1. **Check Okta configuration** - Ensure Okta is syncing groups from Imanami
2. **Check Vouch configuration** - Ensure Vouch is including groups in JWT
3. **Check goggles logs** - See what groups goggles extracted from JWT:
   ```bash
   kubectl logs -n applications <goggles-pod> | grep "groups:"
   ```

## When to Keep SSO Enabled

**Most applications need SSO:**
- Internal corporate tools
- Apps handling sensitive data
- Admin dashboards
- Customer data access
- Compliance-required applications

**Default: SSO is ENABLED**

## When to Disable SSO

Consider disabling SSO only if your app falls into one of these categories:

### 1. Public APIs
- REST APIs intended for public consumption
- Webhooks receiving external calls
- Public-facing services with their own auth

### 2. Apps with Built-in Authentication
- Applications that implement their own authentication (OAuth, JWT, etc.)
- Apps that need custom authentication logic
- Multi-tenant apps with their own user management

### 3. Internal Tools Without Sensitive Data
- Development utilities
- Build status dashboards
- Public documentation sites
- Health check endpoints

### 4. Development/Testing Apps
- Temporary testing environments
- Load testing targets
- CI/CD test deployments

**⚠️ Important:** If you disable SSO, your app **MUST** implement its own authentication, or accept that it's publicly accessible within the corporate network.

## How to Disable SSO

### Option 1: Disable in values.yaml (applies to all environments)

Edit `helm/values.yaml`:
```yaml
# SSO Configuration
disable_sso: true  # ← Change from false to true
```

### Option 2: Disable per environment

Edit `helm/dev.yaml` or `helm/prod.yaml`:
```yaml
# Disable SSO in dev only
disable_sso: true
```

This allows you to use SSO in production but bypass it in development.

### What Happens When Disabled

When `disable_sso: true`:
- ✅ nginx + goggles pods are NOT created
- ✅ Ingress routes directly to your app service
- ✅ No authentication checks
- ❌ No user information headers
- ❌ Anyone with network access can reach your app

## Customizing SSO Configuration

### Unauthenticated Paths

Some paths (like health checks) should bypass authentication. Edit `helm/templates/sso.yaml`:

```yaml
data:
  goggles.yaml: |
    pk_url: {{ .Values.auth_public_key_url }}
    default_action: permit
    unauthenticated_paths:
      - /health           # Health check endpoint
      - /api/health       # Alternative health check
      - /metrics          # Prometheus metrics (if needed)
      - /api/public       # Public API endpoints
```

### Timeout Configuration

Adjust nginx timeouts in `helm/templates/sso.yaml`:

```nginx
proxy_read_timeout 600s;  # ← Increase for long-running requests
proxy_send_timeout 600s;
```

### Client Body Size

For file uploads, increase client body size:

```nginx
client_max_body_size 10m;  # ← Increase for larger uploads
```

## Troubleshooting

### Redirect Loop (keeps going to login page)

**Cause:** Vouch URL or public key URL is incorrect

**Fix:** Check `helm/dev.yaml` or `helm/prod.yaml`:
```yaml
vouch_url: https://auth.tsdev.paloaltonetworks.com
auth_public_key_url: https://auth.tsdev.paloaltonetworks.com/public-key
```

### 401 Unauthorized on all requests

**Cause:** goggles can't reach Vouch or public key is invalid

**Fix:** 
1. Check goggles pod logs: `kubectl logs -n <namespace> <app>-nginx-deployment-xxx -c <app>-goggles`
2. Verify Vouch URL is accessible from the cluster
3. Check auth_public_key_url returns a valid public key

### nginx pod fails to start

**Cause:** ConfigMap syntax error

**Fix:** Check `helm/templates/sso.yaml` for YAML syntax errors

### User headers not reaching app

**Cause:** nginx config not passing headers

**Fix:** Verify in `helm/templates/sso.yaml`:
```nginx
location / {
    proxy_set_header X-Username $auth_username;
    proxy_set_header X-First-Name $auth_first_name;
    proxy_set_header X-Last-Name $auth_last_name;
    proxy_set_header X-Groups $auth_groups;
}
```

## Verifying SSO is Working

### 1. Check deployments
```bash
kubectl get deployments -n <namespace>
```

Should see:
- `<app>-deployment` (your app)
- `<app>-nginx-deployment` (SSO proxy) ← Should exist if SSO enabled

### 2. Check services
```bash
kubectl get svc -n <namespace>
```

Should see:
- `<app>-svc` (your app service)
- `<app>-nginx-svc` (SSO proxy service) ← Should exist if SSO enabled

### 3. Test authentication
```bash
# Visit your app URL in browser
# Should redirect to: https://auth.tsdev.paloaltonetworks.com/login?...
```

### 4. Check user headers (from within your app)
```javascript
// Node.js example
app.get('/whoami', (req, res) => {
  res.json({
    username: req.headers['x-username'],
    firstName: req.headers['x-first-name'],
    lastName: req.headers['x-last-name'],
    groups: req.headers['x-groups']
  });
});
```

Visit `/whoami` after logging in to see the user information.

## Security Best Practices

### ✅ DO:
- Keep SSO enabled for apps with sensitive data
- Use user headers for authorization (roles, groups)
- Log authentication events
- Monitor for authentication failures

### ❌ DON'T:
- Disable SSO without implementing alternative auth
- Trust client-side authentication tokens without verification
- Store sensitive data in apps without authentication
- Bypass SSO for convenience without security review

## Migration from Non-SSO Setup

If you have an existing app without SSO and want to add it:

1. **Update helm templates:**
   - Ensure `helm/templates/sso.yaml` exists (copy from this template)
   - Update `helm/templates/ingress.yaml` to route to nginx-svc

2. **Update values:**
   - Add SSO configuration to `helm/values.yaml`
   - Add vouch URLs to `helm/dev.yaml` and `helm/prod.yaml`

3. **Deploy:**
   ```bash
   helm upgrade --install <app> ./helm -n <namespace> -f helm/dev.yaml
   ```

4. **Verify:**
   - Check nginx deployment exists
   - Test authentication flow
   - Verify user headers in your app

## Tracking User Activity & Login/Logout

### What You Can Track

**Every authenticated request includes user information:**
- `X-Username`: User's email
- `X-First-Name`, `X-Last-Name`: User's name
- `X-Groups`: User's group memberships

Your app receives these headers on **every request**, allowing you to track:
- ✅ Which users accessed your app
- ✅ When they accessed it (timestamp)
- ✅ What pages/endpoints they used
- ✅ User activity patterns
- ✅ Active vs inactive users

### Okta Analytics Limitation

**Important:** Vouch is registered as a single application in Okta. This means:
- Okta logs show: "User logged into Vouch"
- Okta **cannot** distinguish which specific app the user accessed
- **No per-app metrics** in Okta dashboard

If you need per-app usage metrics, you must track them at the application level (see below).

### Login Tracking

**There is no explicit "login" event** because authentication happens at Vouch/Okta (outside your app).

**Recommended approach:** Track "session start" = first authenticated request from a user.

**Example implementation:**

```javascript
// Node.js example
const userSessions = new Map(); // Or use Redis/database

app.use((req, res, next) => {
  const username = req.headers['x-username'];
  
  if (username) {
    const lastSeen = userSessions.get(username);
    const now = Date.now();
    
    // Track as new session if no activity in last 30 minutes
    if (!lastSeen || (now - lastSeen) > 30 * 60 * 1000) {
      logMetric('user_session_start', {
        username: username,
        app: 'my-app',
        timestamp: new Date()
      });
    }
    
    // Update last seen
    userSessions.set(username, now);
  }
  
  next();
});
```

**Python example:**

```python
from datetime import datetime, timedelta

last_seen = {}  # Or use Redis

@app.middleware("http")
async def track_sessions(request, call_next):
    username = request.headers.get("x-username")
    
    if username:
        now = datetime.now()
        last = last_seen.get(username)
        
        # Track as new session if no activity in last 30 minutes
        if not last or (now - last) > timedelta(minutes=30):
            log_metric("user_session_start", {
                "username": username,
                "app": "my-app",
                "timestamp": now
            })
        
        last_seen[username] = now
    
    response = await call_next(request)
    return response
```

### Logout Tracking

**Universal web app problem:** Most users don't explicitly logout - they just close the browser.

**No web app can perfectly track logout** because:
- Users close browsers (most common)
- Browser crashes
- Network disconnects
- Mobile OS kills apps
- Users have multiple tabs open

**Industry standard approach:** Infer logout from inactivity.

**Example:**

```javascript
// Track activity on every request
app.use((req, res, next) => {
  const username = req.headers['x-username'];
  if (username) {
    updateActivity(username, {
      timestamp: Date.now(),
      path: req.path,
      method: req.method
    });
  }
  next();
});

// Periodic job to detect inactive sessions
setInterval(() => {
  const inactiveThreshold = 30 * 60 * 1000; // 30 minutes
  const now = Date.now();
  
  for (const [username, lastActivity] of userSessions) {
    if (now - lastActivity > inactiveThreshold) {
      logMetric('user_session_end', {
        username: username,
        app: 'my-app',
        last_activity: new Date(lastActivity)
      });
      userSessions.delete(username);
    }
  }
}, 5 * 60 * 1000); // Check every 5 minutes
```

**Optional: Explicit logout endpoint** (captures ~30% of logouts):

```javascript
app.post('/logout', (req, res) => {
  const username = req.headers['x-username'];
  
  logMetric('user_explicit_logout', {
    username: username,
    app: 'my-app',
    timestamp: new Date()
  });
  
  // Clear the Vouch cookie
  res.clearCookie('VouchCookie');
  res.redirect('/');
});
```

### Centralized Logging & Metrics

**Send metrics to a centralized system for dashboards:**

**Option 1: BigQuery (recommended if already using it)**

```javascript
const { BigQuery } = require('@google-cloud/bigquery');
const bigquery = new BigQuery();

function logMetric(event, data) {
  bigquery.dataset('app_metrics').table('user_activity').insert({
    event_type: event,
    app_name: process.env.APP_NAME,
    ...data,
    timestamp: new Date()
  });
}
```

**Option 2: CloudWatch Logs**

```javascript
const AWS = require('aws-sdk');
const cloudwatch = new AWS.CloudWatchLogs();

function logMetric(event, data) {
  cloudwatch.putLogEvents({
    logGroupName: '/apps/user-activity',
    logStreamName: process.env.APP_NAME,
    logEvents: [{
      timestamp: Date.now(),
      message: JSON.stringify({ event, ...data })
    }]
  });
}
```

**Option 3: Application Logs (simplest)**

```javascript
function logMetric(event, data) {
  console.log(JSON.stringify({
    event_type: event,
    app_name: process.env.APP_NAME,
    ...data,
    timestamp: new Date().toISOString()
  }));
}
```

Then use log aggregation tools (Splunk, CloudWatch Insights, etc.) to build dashboards.

### Recommended Metrics to Track

**User engagement:**
- Daily Active Users (DAU) - users with activity today
- Weekly Active Users (WAU)
- Monthly Active Users (MAU)
- New vs returning users
- Session duration (time between first and last request)

**Application usage:**
- Most accessed pages/endpoints
- Peak usage times
- User retention (% of users who return)
- Feature adoption (which endpoints are used)

**Example query (BigQuery):**

```sql
-- Daily Active Users
SELECT 
  DATE(timestamp) as date,
  COUNT(DISTINCT username) as active_users
FROM app_metrics.user_activity
WHERE app_name = 'my-app'
GROUP BY date
ORDER BY date DESC;

-- Average session duration
SELECT 
  username,
  DATE(timestamp) as date,
  MAX(timestamp) - MIN(timestamp) as session_duration_ms
FROM app_metrics.user_activity
WHERE app_name = 'my-app'
  AND DATE(timestamp) = CURRENT_DATE()
GROUP BY username, date;
```

### Why This is Better Than Direct Okta Integration

**With application-level tracking you get:**
- ✅ More detailed metrics (pages viewed, features used, not just login)
- ✅ Per-app dashboards and analytics
- ✅ Custom metrics specific to your app's needs
- ✅ Real user activity data, not just authentication events

**Direct Okta integration would give:**
- ✅ Explicit OAuth callback event (login timestamp)
- ❌ Still no logout tracking (same problem)
- ❌ Only authentication events (not activity data)
- ❌ Each app must implement OAuth (more code, less consistent)

**Recommendation:** Keep Vouch + goggles architecture and add application-level activity tracking.

## Questions?

- **Security questions:** Contact #infosec
- **SSO/auth infrastructure issues:** Check documentation or team that manages auth infrastructure
