# DNS Setup

How DNS is wired for apps deployed via this template, and how to add your app's domain.

> **Most apps should use the automated onboarding pipeline instead of following this manually.** See [ONBOARDING-AUTOMATION.md](ONBOARDING-AUTOMATION.md). This doc is the reference for the underlying mechanics and the fallback when automation breaks.

## Overview

Every app deployed with this template gets two URLs:

- **Dev:** `https://your-app-name.tsdev.paloaltonetworks.com`
- **Prod:** `https://your-app-name.ts.paloaltonetworks.com`

Both are derived automatically from `app_name` in `helm/values.yaml`. The DNS records themselves are managed by Terraform in separate deployment repos — one for dev, one for prod.

**⚠️ Internal-only DNS:**
- These hostnames only resolve on the PANW corporate network (in-office or on VPN).
- External services can't reach your app over HTTP. For Slack apps, use Socket Mode (outbound WebSocket from your pod) instead of HTTP event subscriptions.

## Where DNS Lives

DNS lives in two repos, each owning a different piece:

### 1. The Cloud DNS managed zones ([`gcp-wwss-as-trust-module`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-module) → `dns.tf`)

Defines:
- The private DNS zones `tsdev.paloaltonetworks.com.` (dev) and `ts.paloaltonetworks.com.` (prod)
- The forwarding zone for `paloaltonetworks.com.` (so apps can resolve internal PANW hostnames via the bastion)
- The static IPs for ingress (internal and external)

**You don't normally edit `dns.tf`.** It's done at cluster setup time, not per-app.

### 2. The per-app domain list (the deployment repos)

This is what you edit when adding a new app:

- **Dev:** [`gcp-wwss-as-trust-dev-deployment`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment) → `main.tf` → `ingress_app_domain_names`
- **Prod:** [`gcp-wwss-as-trust-prod-deployment`](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-prod-deployment) → `main.tf` → `ingress_app_domain_names`

Adding your app's domain to the array causes Terraform to:
1. Create a Cloud DNS A record pointing to the ingress-nginx static IP
2. Add the hostname to the ingress controller's accepted host list
3. Provision a TLS certificate for the hostname

## How to Add a New Domain (Dev)

### Step 1: Clone the dev deployment repo

Repo: [gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment)

```bash
git clone https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-dev-deployment.git
cd gcp-wwss-as-trust-dev-deployment
```

### Step 2: Create a feature branch

```bash
git checkout -b feature/add-my-app-dns
```

**⚠️ The `feature/...` prefix is required** — only branches matching that pattern get the protected CI/CD variables (GCP credentials) needed for the pipeline.

### Step 3: Add your domain to `main.tf`

Edit `main.tf` and add your domain to `ingress_app_domain_names`:

```terraform
ingress_app_domain_names = [
  # ... existing domains ...
  "my-app.tsdev.paloaltonetworks.com.",
]
```

**⚠️ The trailing dot is required.** `my-app.tsdev.paloaltonetworks.com` (no dot) will fail apply.

### Step 4: Commit, push, open MR

```bash
git add main.tf
git commit -m "Add my-app DNS"
git push -u origin feature/add-my-app-dns
```

Open an MR and request a reviewer.

### Step 5: Run `terraform apply`

After merge, `terraform apply` does NOT run automatically. Someone with access has to run it manually:

```bash
cd gcp-wwss-as-trust-dev-deployment
git checkout main
git pull
terraform init
terraform apply
```

Ping `#engineering-productivity` or your team lead if you don't have apply access.

## How to Add a New Domain (Prod)

Repeat the same five steps against the prod deployment repo: [gitlab.com/panw-gse/ts/gcp-wwss-as-trust-prod-deployment](https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-prod-deployment)

```bash
git clone https://gitlab.com/panw-gse/ts/gcp-wwss-as-trust-prod-deployment.git
```

Use the prod hostname format (`.ts.paloaltonetworks.com.`, no `tsdev`):

```terraform
ingress_app_domain_names = [
  # ... existing domains ...
  "my-app.ts.paloaltonetworks.com.",
]
```

Only do this once you've verified the app works in dev.

## Verification

### Verify DNS resolves (on PANW network)

```bash
nslookup my-app.tsdev.paloaltonetworks.com
```

Should resolve to the ingress-nginx static IP.

### Verify the app responds

After your app is deployed:

```bash
curl -I https://my-app.tsdev.paloaltonetworks.com
```

Should return `HTTP/2 200` (or `HTTP/2 302` redirecting to the SSO login flow if SSO is enabled).

## Troubleshooting

### Domain doesn't resolve

- **Are you on PANW network or VPN?** Internal-only DNS won't resolve elsewhere.
- **Did `terraform apply` run after merge?** Check the deployment repo's commit history vs. when the operator last ran apply.
- **Is the trailing dot in the domain string?** `my-app.tsdev.paloaltonetworks.com.` — missing it breaks apply.

### Domain resolves but you get a TLS certificate error

- Certificate provisioning takes a few minutes after `terraform apply`. Wait 5-10 minutes and retry.
- If it persists, check cert-manager events:
  ```bash
  kubectl describe certificate -n applications | grep -A5 "my-app"
  ```

### Domain resolves but app returns 404

- DNS is fine. The issue is in your app's ingress or pod.
- Check ingress hostname matches `dev.yaml`/`prod.yaml`:
  ```bash
  kubectl get ingress -n applications
  ```
- Check pod is running:
  ```bash
  kubectl get pods -n applications -l app=my-app
  ```

### Pipeline fails with `ACCESS_TOKEN_SCOPE_INSUFFICIENT`

- Your branch isn't named `feature/...` so protected variables (GCP credentials) aren't exposed. Rename the branch.

## Related Docs

- [SERVICE-ACCOUNT-SETUP.md](SERVICE-ACCOUNT-SETUP.md)
- [GETTING-STARTED.md](GETTING-STARTED.md)
- [SSO-AUTHENTICATION.md](SSO-AUTHENTICATION.md)
