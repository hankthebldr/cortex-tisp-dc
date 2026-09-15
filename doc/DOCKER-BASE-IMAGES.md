# Docker Base Images Guide

## Quick Decision Tree by Language

The PANW proxy MITMs all outbound HTTPS during `docker build`, so any package fetch (`pip install`, `npm ci`, `apt-get`, etc.) fails with `CERTIFICATE_VERIFY_FAILED` on a standard base image. The fix differs by language — pick the pattern that's been verified to work, don't guess.

| Language | Build touches network? | Pattern |
|---|---|---|
| **Python** | Yes (pip install) | Plain proxy image + `pip --trusted-host` — see below |
| **Node** | Yes (npm ci, Next.js, etc.) | EP image (`build-tools--image-node`) |
| **Node** | No (precompiled, COPY-only) | Plain proxy image |
| **Go** | Usually no in final stage | Plain proxy image; put `go mod download` in a builder stage |

> ⚠️ **Do NOT use `docker.art.code.pan.run/build-tools--image-python:*.ep*`** — these tags do not exist in Artifactory (verified 2026-07-01: kaniko returns `MANIFEST_UNKNOWN`). Only Node EP images are currently maintained.

---

## Python — Plain Image + `pip --trusted-host` (Verified Working)

Used by `ask-experts` and `py-observability-smoketest`.

```dockerfile
FROM docker-io.art.code.pan.run/library/python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir \
      --trusted-host pypi.org \
      --trusted-host files.pythonhosted.org \
      -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Why it works:** `--trusted-host` tells pip to skip cert verification for pypi.org and files.pythonhosted.org. The PANW proxy still MITMs the connection, but pip stops checking whose cert is on the other end.

**Do NOT** try `docker.art.code.pan.run/build-tools--image-python:3.11-slim.ep9` or any `.ep*` variant — the tag doesn't exist and kaniko will fail with `MANIFEST_UNKNOWN`. If a Python EP image gets published in the future, this doc should be updated.

---

## Node — EP-Provided Images (With PANW CA Certificates)

**When to use:**
- Next.js apps with Google Fonts
- Apps that fetch external data during build
- Any Node app running `npm ci` from `registry.npmjs.org` during build

**Available images:**
```dockerfile
FROM docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9
FROM docker.art.code.pan.run/build-tools--image-node:20-alpine.ep9
FROM docker.art.code.pan.run/build-tools--image-node:18-alpine.ep7
```

**Why these images?**
- PANW firewall intercepts and decrypts all HTTPS traffic (SSL inspection)
- Standard base images don't trust the PANW Enterprise CA G2 certificate
- EP images have PANW CA pre-installed in the certificate store
- Allows successful HTTPS connections through corporate proxy

**Important notes:**
- These images run as **non-root user** by default (`nodeuser` for Node, `pythonuser` for Python)
- Switch to `USER root` before `apt-get install`
- Switch back to `USER nodeuser` after setup

**Example:**
```dockerfile
FROM docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9

# EP images run as non-root, switch to root for system packages
USER root

RUN apt-get update && apt-get install -y chromium && rm -rf /var/lib/apt/lists/*

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Switch back to non-root user
RUN chown -R nodeuser:nodeuser /app
USER nodeuser

CMD ["npm", "start"]
```

---

## Artifactory Proxy Images (No PANW Certs)

**When to use:**
- Simple Node.js/Express apps (no build step)
- Go apps
- Ruby apps
- Any app that doesn't make external HTTPS requests during build

**Available images:**
```dockerfile
# Node.js
FROM docker-io.art.code.pan.run/library/node:20-alpine
FROM docker-io.art.code.pan.run/library/node:18-alpine

# Python
FROM docker-io.art.code.pan.run/library/python:3.11-slim
FROM docker-io.art.code.pan.run/library/python:3.10-slim

# Go
FROM docker-io.art.code.pan.run/library/golang:1.21-alpine

# Ruby
FROM docker-io.art.code.pan.run/library/ruby:3.2-slim

# Nginx
FROM docker-io.art.code.pan.run/library/nginx:alpine

# Alpine
FROM docker-io.art.code.pan.run/library/alpine:latest
```

**Why these images?**
- Proxied through Artifactory, avoiding Docker Hub rate limits
- Lighter weight than EP images
- No extra certificates, simpler setup

**Example:**
```dockerfile
FROM docker-io.art.code.pan.run/library/node:20-alpine

RUN addgroup -g 1001 -S nodejs && adduser -S nodejs -u 1001

WORKDIR /app
COPY package*.json ./
RUN npm ci

COPY . .
RUN chown -R nodejs:nodejs /app

USER nodejs
CMD ["node", "server.js"]
```

---

## Common Patterns

### Pattern 1: Next.js with Google Fonts
```dockerfile
FROM docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9
USER root
WORKDIR /app
COPY package*.json ./
RUN npm ci  # Needs devDependencies for build!
COPY . .
RUN npm run build
RUN chown -R nodeuser:nodeuser /app
USER nodeuser
CMD ["npm", "start"]
```

### Pattern 2: Simple Express App
```dockerfile
FROM docker-io.art.code.pan.run/library/node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci  # Safer to include devDependencies
COPY . .
CMD ["node", "server.js"]
```

### Pattern 3: Go Binary
```dockerfile
FROM docker-io.art.code.pan.run/library/golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o server

FROM docker-io.art.code.pan.run/library/alpine:latest
COPY --from=builder /app/server .
CMD ["./server"]
```

---

## FAQ

### Why can't I just use `node:20-alpine` directly?

You can, but it will pull from Docker Hub with rate limits (429 errors). Always use `docker-io.art.code.pan.run/library/node:20-alpine` instead.

### When should I use `npm ci --only=production`?

**Almost never.** If your app has ANY build step (TypeScript, Next.js, React, Tailwind), you need devDependencies. Just use `npm ci`.

### Why do EP images run as non-root?

Security best practice. But you need to switch to root temporarily for `apt-get install`, then switch back.

### How do I find available EP images?

Browse Artifactory: https://art.code.pan.run/ui/repos/tree/General/docker/build-tools--image-node

Or ask EP team for the full list.

### What if my build fails with SSL/certificate errors?

You're using a standard image when you need an EP image. Switch to the EP variant for your language.

**Exact error text you'll see (Python `pip install`):**
```
WARNING: Retrying (...) after connection broken by 'SSLError(SSLCertVerificationError(1,
'[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate
in certificate chain (_ssl.c:1016)'))': /simple/<package>/
ERROR: Could not find a version that satisfies the requirement <package>
```

**Exact error text you'll see (Node `npm ci`):**
```
npm ERR! code SELF_SIGNED_CERT_IN_CHAIN
npm ERR! request to https://registry.npmjs.org/... failed, reason: self-signed
certificate in certificate chain
```

**Fix — by language:**

**Python** — keep the plain image, add `--trusted-host` to pip. Verified working in `ask-experts` and `py-observability-smoketest`:

```dockerfile
FROM docker-io.art.code.pan.run/library/python:3.11-slim
RUN pip install --no-cache-dir \
      --trusted-host pypi.org \
      --trusted-host files.pythonhosted.org \
      -r requirements.txt
```

(Do NOT try `docker.art.code.pan.run/build-tools--image-python:*.ep*` — those tags return `MANIFEST_UNKNOWN` from Artifactory as of 2026-07-01.)

**Node** — switch to the EP image:

| Replace this | With this |
|---|---|
| `docker-io.art.code.pan.run/library/node:20-alpine` | `docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9` |

Remember Node EP images run as non-root — add `USER root` before `npm ci` / `apt-get`.

---

## Resources

- **Artifactory Docker Registry**: https://art.code.pan.run
- **EP Documentation**: https://confluence-dc.paloaltonetworks.com/display/EP/
- **Traffic Decryption Guide**: https://confluence-dc.paloaltonetworks.com/display/EP/Updating+your+jobs+for+traffic+decryption
- **Open EP Jira Ticket**: Request new images or proxies

---

**Last Updated**: 2026-07-01
