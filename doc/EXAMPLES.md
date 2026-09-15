# Language-Specific Examples

This guide provides complete Dockerfile and application examples for different programming languages.

## Requirements for All Languages

Your application MUST:
1. **Listen on port 8080** (standardized across all languages - simplifies deployment)
2. **Have a `/health` endpoint** that returns HTTP 200 for Kubernetes health checks
3. **Run as non-root user** for security
4. **Use multi-stage builds** to keep image size small (when applicable)
5. **Use `docker-io.art.code.pan.run` for Docker Hub images** (avoids rate limits)

> **Why port 8080?** It's the industry standard for containerized HTTP applications. Using the same port across all languages eliminates configuration errors and simplifies the template.

> **Why `docker-io.art.code.pan.run`?** This is Palo Alto Networks' internal Artifactory proxy for Docker Hub. It caches images locally and prevents "Too Many Requests" (HTTP 429) rate limit errors from Docker Hub. Always use `docker-io.art.code.pan.run/library/<image>` instead of `docker.io/<image>` or just `<image>`.

---

## Node.js / Express

### Application: `server.js`
```javascript
const express = require('express');
const app = express();
const PORT = process.env.PORT || 8080;

app.use(express.json());

// Required: Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({ status: 'healthy' });
});

app.get('/', (req, res) => {
  res.json({ message: 'Hello World' });
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
```

### Dependencies: `package.json`
```json
{
  "name": "my-app",
  "version": "1.0.0",
  "main": "server.js",
  "scripts": {
    "start": "node server.js"
  },
  "dependencies": {
    "express": "^4.18.2"
  }
}
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
# Use npm ci (installs all dependencies including devDependencies)
# If your app has NO build step and NO TypeScript, you could use --only=production
# But it's safer to just use npm ci
RUN npm ci
COPY . .

FROM docker-io.art.code.pan.run/library/node:20-alpine
RUN addgroup -g 1001 -S nodejs && adduser -S nodejs -u 1001
WORKDIR /app
COPY --from=builder --chown=nodejs:nodejs /app .
USER nodejs
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1
CMD ["node", "server.js"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

---

## Python / Flask

### Application: `app.py`
```python
from flask import Flask, jsonify
import os

app = Flask(__name__)
PORT = int(os.getenv('PORT', 8080))

# Required: Health check endpoint
@app.route('/health')
def health():
    return jsonify({'status': 'healthy'}), 200

@app.route('/')
def hello():
    return jsonify({'message': 'Hello World'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT)
```

### Dependencies: `requirements.txt`
```
Flask==3.0.0
gunicorn==21.2.0
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

FROM docker-io.art.code.pan.run/library/python:3.11-slim
RUN useradd -m -u 1001 appuser
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:app"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

---

## Python / FastAPI

### Application: `main.py`
```python
from fastapi import FastAPI
import os

app = FastAPI()
PORT = int(os.getenv('PORT', 8080))

# Required: Health check endpoint
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/")
async def root():
    return {"message": "Hello World"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
```

### Dependencies: `requirements.txt`
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/python:3.11-slim
RUN useradd -m -u 1001 appuser
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

---

## Go

### Application: `main.go`
```go
package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "os"
)

func main() {
    port := os.Getenv("PORT")
    if port == "" {
        port = "8080"
    }

    // Required: Health check endpoint
    http.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{"status": "healthy"})
    })

    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(map[string]string{"message": "Hello World"})
    })

    fmt.Printf("Server running on port %s\n", port)
    log.Fatal(http.ListenAndServe(":"+port, nil))
}
```

### Dependencies: `go.mod`
```go
module myapp

go 1.21
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o server

FROM docker-io.art.code.pan.run/library/alpine:latest
RUN addgroup -g 1001 -S appuser && adduser -S appuser -u 1001
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/server .
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1
CMD ["./server"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

---

## Python / Django

### Application: `myproject/settings.py`
Add to settings:
```python
ALLOWED_HOSTS = ['*']  # Configure properly for production
```

### Health Check: `myapp/views.py`
```python
from django.http import JsonResponse

def health(request):
    return JsonResponse({'status': 'healthy'})
```

### URLs: `myproject/urls.py`
```python
from django.urls import path
from myapp.views import health

urlpatterns = [
    path('health', health),
    # ... other URLs
]
```

### Dependencies: `requirements.txt`
```
Django==4.2.7
gunicorn==21.2.0
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/python:3.11-slim
RUN useradd -m -u 1001 appuser
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "myproject.wsgi:application"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

---

## React / Static Frontend (with nginx)

### Build Setup: `package.json`
```json
{
  "name": "my-react-app",
  "scripts": {
    "build": "react-scripts build"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }
}
```

### nginx config: `nginx.conf`
```nginx
server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # Health check endpoint
    location /health {
        access_log off;
        return 200 '{"status":"healthy"}';
        add_header Content-Type application/json;
    }

    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM docker-io.art.code.pan.run/library/nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget --no-verbose --tries=1 --spider http://localhost/health || exit 1
CMD ["nginx", "-g", "daemon off;"]
```

### Helm Configuration
```yaml
# helm/values.yaml
# Note: nginx listens on port 80 by default, so we override here
k8s:
  app_targetPort: 80
  app_containerPort: 80
```

---

## Next.js (with Google Fonts and TypeScript)

**Important:** Next.js apps that download external resources (Google Fonts, external APIs, etc.) during build **must use the EP-provided Node image** with PANW CA certificates. This allows the build container to trust the corporate SSL proxy.

### Application: `src/app/page.tsx`
```typescript
export default function Home() {
  return (
    <main>
      <h1>Hello from Next.js</h1>
      <p>Running on port 8080</p>
    </main>
  );
}
```

### Health Check: `src/app/api/health/route.ts`
```typescript
import { NextResponse } from 'next/server';

export async function GET() {
  return NextResponse.json(
    {
      status: 'healthy',
      timestamp: new Date().toISOString()
    },
    { status: 200 }
  );
}
```

### Layout with Google Fonts: `src/app/layout.tsx`
```typescript
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
```

### Dependencies: `package.json`
```json
{
  "name": "my-nextjs-app",
  "version": "1.0.0",
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "next": "^14.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.2.0",
    "typescript": "^5.0.0"
  }
}
```

### Dockerfile
```dockerfile
# Use EP-provided image with PANW CA certificates
# This allows downloading Google Fonts and other external resources during build
FROM docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9

# EP images run as non-root user (nodeuser) by default
# Switch to root to install system packages
USER root

WORKDIR /app

# Optional: Install Chromium for Puppeteer (if needed for PDF generation, etc.)
# RUN apt-get update && apt-get install -y \
#     chromium \
#     fonts-liberation \
#     --no-install-recommends \
#     && rm -rf /var/lib/apt/lists/*
#
# ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
#     PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Copy package files and install ALL dependencies
# DO NOT use --only=production - Next.js needs devDependencies for build!
COPY package*.json ./
RUN npm ci

# Copy source code
COPY . .

# Build Next.js app
# Google Fonts will download successfully because PANW CA certs are trusted
ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production
RUN npm run build

# Set ownership and switch back to non-root user
RUN chown -R nodeuser:nodeuser /app
USER nodeuser

# Configure runtime
ENV PORT=8080 \
    HOSTNAME="0.0.0.0"

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s \
  CMD node -e "require('http').get('http://localhost:8080/api/health', (r) => {process.exit(r.statusCode === 200 ? 0 : 1)})"

CMD ["npm", "start"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

### Key Points for Next.js:

1. **Use EP-provided image**: `docker.art.code.pan.run/build-tools--image-node:20-bullseye.ep9`
   - Has PANW CA certificates pre-installed
   - Allows downloading Google Fonts, external APIs, etc.
   - Pre-configured for corporate SSL proxy

2. **USER root pattern**: EP images run as non-root by default
   - Switch to `USER root` before `apt-get install`
   - Switch back to `USER nodeuser` after setup

3. **npm ci (not --only=production)**: Next.js needs devDependencies
   - TypeScript compiler
   - Tailwind CSS
   - PostCSS plugins
   - Other build tools

4. **Health endpoint**: Create `/api/health/route.ts` for Kubernetes probes

---

## Ruby / Rails

### Health Check: `config/routes.rb`
```ruby
Rails.application.routes.draw do
  get '/health', to: 'health#index'
  # ... other routes
end
```

### Controller: `app/controllers/health_controller.rb`
```ruby
class HealthController < ApplicationController
  def index
    render json: { status: 'healthy' }
  end
end
```

### Dependencies: `Gemfile`
```ruby
source 'https://rubygems.org'
gem 'rails', '~> 7.0'
gem 'puma', '~> 6.0'
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/ruby:3.2-slim AS builder
WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN bundle install
COPY . .

FROM docker-io.art.code.pan.run/library/ruby:3.2-slim
RUN useradd -m -u 1001 appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /usr/local/bundle /usr/local/bundle
COPY --chown=appuser:appuser . .
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8080/health || exit 1
CMD ["rails", "server", "-b", "0.0.0.0", "-p", "8080"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

---

## Java / Spring Boot

### Health Check (Built-in)
Spring Boot Actuator provides `/health` automatically:

### Dependencies: `pom.xml`
```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

### Application properties: `application.properties`
```properties
server.port=8080
management.endpoints.web.exposure.include=health
```

### Dockerfile
```dockerfile
FROM docker-io.art.code.pan.run/library/maven:3.9-eclipse-temurin-17 AS builder
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn package -DskipTests

FROM docker-io.art.code.pan.run/library/eclipse-temurin:17-jre-alpine
RUN addgroup -g 1001 -S appuser && adduser -S appuser -u 1001
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app/target/*.jar app.jar
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1
CMD ["java", "-jar", "app.jar"]
```

### Helm Configuration
```yaml
# helm/values.yaml (already configured correctly - no changes needed!)
k8s:
  app_targetPort: 8080
  app_containerPort: 8080
```

---

## Common Patterns

### Health Check Implementations

**Simple status check:**
```
GET /health
200 OK
{"status": "healthy"}
```

**With dependencies check:**
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Multi-stage Build Benefits
- **Smaller images**: Build dependencies not included in final image
- **Faster deploys**: Less data to transfer
- **More secure**: Fewer attack surfaces

### Security Best Practices
- Always run as non-root user
- Don't include secrets in image
- Use specific base image versions (not `latest`)
- Scan images for vulnerabilities

---

## Choosing Your Stack

When selecting a language/framework, consider:
- **Team expertise** - Use what your team knows
- **Performance requirements** - Go/Java for high performance, Python/Node.js for rapid development
- **Ecosystem** - Libraries and tools available
- **Deployment speed** - Image size affects deployment time

All examples above work with this template's CI/CD pipeline!
