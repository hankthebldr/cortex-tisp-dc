# App Template Architecture Diagrams

Visual diagrams for understanding the app-template infrastructure and workflow.

## 1. Developer Workflow - 6 Steps to Production

```mermaid
%%{init: {'theme':'neutral', 'themeVariables': { 'fontSize':'16px'}}}%%
flowchart TD
    Start([Developer wants to deploy app]) --> Step1[1. Fork/Clone Template]
    Step1 --> Step2[2. Protect main & dev branches in GitLab]
    Step2 --> Step3[3. Update app_name in helm/values.yaml]
    Step3 --> Step4[4. Build app + Dockerfile<br/>Listen on port 8080<br/>Add /health endpoint]
    Step4 --> Step5[5. Push to dev branch]
    Step5 --> AutoDeploy{Pipeline auto-deploys to dev}
    AutoDeploy --> Test[Test at app.tsdev.paloaltonetworks.com]
    Test --> Working{Working?}
    Working -->|No| Debug[Debug & fix]
    Debug --> Step5
    Working -->|Yes| Step6[6. Merge to main<br/>Manually trigger prod deploy]
    Step6 --> Prod[App live at app.ts.paloaltonetworks.com]
    
    style Step1 fill:#e1f5ff
    style Step2 fill:#e1f5ff
    style Step3 fill:#fff4e1
    style Step4 fill:#fff4e1
    style Step5 fill:#e8f5e9
    style Step6 fill:#e8f5e9
    style Prod fill:#c8e6c9
```

## 2. System Architecture - All Components

```mermaid
%%{init: {'theme':'neutral', 'themeVariables': { 'fontSize':'16px'}}}%%
graph TB
    subgraph "Developer Experience"
        Dev[Developer]
        Code[Application Code]
        Dockerfile[Dockerfile]
    end
    
    subgraph "GitLab CI/CD - code.pan.run"
        Repo[Git Repository<br/>main & dev branches]
        Pipeline[GitLab CI Pipeline<br/>.gitlab-ci.yml]
        SharedRunner[Shared GitLab Runner<br/>shared-gke runners]
        Kaniko[Kaniko Build<br/>Docker Image Builder]
        DeployRunner[Deploy Runner<br/>us-gke-trust-dev/prod]
    end
    
    subgraph "Artifactory"
        Registry[Docker Registry<br/>docker-ra.art.code.pan.run]
    end
    
    subgraph "GKE Cluster - us-gke-trust-dev/prod"
        Helm[Helm Chart Deployment]
        
        subgraph "Kubernetes Resources"
            SA[Service Account<br/>app-name-sa]
            Deploy[Deployment<br/>app pods]
            Svc[Service<br/>app-svc]
            Ingress[Ingress<br/>HTTPS endpoint]
        end
        
        subgraph "SSO Pod - nginx + goggles sidecar"
            NginxContainer[nginx container<br/>reverse proxy]
            GogglesContainer[goggles container<br/>JWT validator]
            NginxSvc[nginx-svc<br/>service]
        end
        
        Vouch[Vouch Proxy<br/>External - managed centrally]
    end
    
    subgraph "External Services"
        Okta[Okta<br/>Corporate Identity]
        GCP[Google Cloud Platform<br/>BigQuery, Storage, etc.]
    end
    
    subgraph "End User"
        Browser[User Browser]
        URL[app.ts.paloaltonetworks.com]
    end
    
    Dev -->|1. Write code| Code
    Dev -->|2. Create| Dockerfile
    Code -->|3. Push| Repo
    Dockerfile -->|3. Push| Repo
    Repo -->|4. Trigger| Pipeline
    Pipeline -->|5. Build on| SharedRunner
    SharedRunner -->|6. Build with| Kaniko
    Kaniko -->|7. Push image| Registry
    Pipeline -->|8. Deploy on| DeployRunner
    DeployRunner -->|9. Deploy with| Helm
    Registry -->|10. Pull image| Deploy
    Helm -->|11. Create| SA
    Helm -->|11. Create| Deploy
    Helm -->|11. Create| Svc
    Helm -->|11. Create| Ingress
    Helm -->|11. Create| NginxSvc
    Helm -->|11. Create| NginxContainer
    Helm -->|11. Create| GogglesContainer
    
    Browser -->|12. Access| URL
    URL --> Ingress
    Ingress --> NginxSvc
    NginxSvc --> NginxContainer
    NginxContainer -->|13. auth_request| GogglesContainer
    GogglesContainer -->|Validate JWT locally<br/>using Vouch public key| GogglesContainer
    NginxContainer -.->|14. Redirect if no JWT| Vouch
    Vouch -.->|15. Authenticate| Okta
    NginxContainer -->|16. Forward if authenticated| Svc
    Svc --> Deploy
    
    SA -.->|Workload Identity| GCP
    Deploy -.->|Access via SA| GCP
    
    style Dev fill:#e1f5ff
    style Pipeline fill:#fff4e1
    style SharedRunner fill:#fff4e1
    style DeployRunner fill:#fff4e1
    style Registry fill:#ffe1e1
    style Helm fill:#e8f5e9
    style GCP fill:#f3e5f5
    style Okta fill:#f3e5f5
```

## 3. CI/CD Pipeline Flow - From Code to Production

```mermaid
%%{init: {'theme':'neutral', 'themeVariables': { 'fontSize':'16px'}}}%%
flowchart LR
    subgraph "Code Push"
        Push[Developer pushes to dev or main]
    end
    
    subgraph "GitLab Pipeline Stages"
        Security[Security Scan<br/>Sentinel - secrets detection]
        Build[Build Docker Image<br/>Kaniko on shared runner]
        Publish[Publish to Artifactory<br/>docker-ra.art.code.pan.run]
        DeployDev[Deploy to Dev<br/>Auto on dev branch]
        DeployProd[Deploy to Prod<br/>Manual on main branch]
    end
    
    subgraph "Deployment Process"
        HelmDev[Helm upgrade on dev cluster<br/>us-gke-trust-dev runner]
        HelmProd[Helm upgrade on prod cluster<br/>us-gke-trust-prod runner]
    end
    
    subgraph "Kubernetes Cluster"
        Pods[Pods running with new image]
        Health[Health checks<br/>/health endpoint]
    end
    
    Push --> Security
    Security --> Build
    Build --> Publish
    Publish --> DeployDev
    Publish --> DeployProd
    DeployDev --> HelmDev
    DeployProd --> HelmProd
    HelmDev --> Pods
    HelmProd --> Pods
    Pods --> Health
    
    style Push fill:#e1f5ff
    style Security fill:#fff4e1
    style Build fill:#fff4e1
    style Publish fill:#ffe1e1
    style DeployDev fill:#e8f5e9
    style DeployProd fill:#ffccbc
    style HelmDev fill:#e8f5e9
    style HelmProd fill:#ffccbc
    style Pods fill:#c8e6c9
```

## 4. Authentication Flow - SSO with Okta

```mermaid
%%{init: {
  "theme": "base",
  "themeVariables": {
    "background": "#111827",

    "fontFamily": "Arial, sans-serif",
    "fontSize": "16px",

    "textColor": "#e5e7eb",

    "actorBkg": "#f8fafc",
    "actorBorder": "#94a3b8",
    "actorTextColor": "#111827",
    "actorLineColor": "#94a3b8",

    "signalColor": "#e5e7eb",
    "signalTextColor": "#e5e7eb",

    "lineColor": "#94a3b8",

    "noteBkgColor": "#fef3c7",
    "noteTextColor": "#111827",
    "noteBorderColor": "#f59e0b",

    "activationBkgColor": "#1e3a8a",
    "activationBorderColor": "#93c5fd",

    "labelBoxBkgColor": "#f8fafc",
    "labelBoxBorderColor": "#94a3b8",
    "labelTextColor": "#111827",

    "loopTextColor": "#e5e7eb"
  },
  "themeCSS": "
    svg {
      background: #111827 !important;
    }

    .messageText,
    .loopText,
    .loopText > tspan {
      fill: #e5e7eb !important;
      color: #e5e7eb !important;
    }

    .messageLine0,
    .messageLine1,
    .actor-line,
    .loopLine {
      stroke: #94a3b8 !important;
    }

    marker path {
      fill: #94a3b8 !important;
      stroke: #94a3b8 !important;
    }

    .actor {
      fill: #f8fafc !important;
      stroke: #94a3b8 !important;
    }

    text.actor,
    text.actor > tspan {
      fill: #111827 !important;
    }

    .note {
      fill: #fef3c7 !important;
      stroke: #f59e0b !important;
    }

    .noteText,
    .noteText > tspan {
      fill: #111827 !important;
    }

    .labelBox {
      fill: #f8fafc !important;
      stroke: #94a3b8 !important;
    }

    .labelText,
    .labelText > tspan {
      fill: #111827 !important;
    }
  "
}}%%
sequenceDiagram
    participant User
    participant Ingress
    participant nginx
    participant goggles
    participant Vouch
    participant Okta
    participant App

    Note over nginx,goggles: Sidecar containers<br/>in same pod

    User->>Ingress: 1. Access app URL with VouchCookie
    Ingress->>nginx: 2. Route request
    nginx->>goggles: 3. auth_request to localhost:8000/validate
    goggles->>goggles: 4. Extract and validate JWT using Vouch public key

    alt JWT invalid or missing
        goggles->>nginx: 5. Return 401
        nginx->>User: 6. Redirect to Vouch login
        User->>Vouch: 7. Access Vouch
        Vouch->>Okta: 8. Redirect to Okta
        User->>Okta: 9. Enter credentials
        Okta->>Vouch: 10. Return auth
        Vouch->>Vouch: 11. Create JWT token
        Vouch->>User: 12. Set VouchCookie and redirect to app
        User->>Ingress: 13. Retry with VouchCookie
    end

    alt JWT valid
        goggles->>nginx: 14. Return 200 plus headers
        nginx->>App: 15. Forward request with user headers
        App->>User: 16. Return app content
    end
```

## 5. Google Cloud Access - Workload Identity

```mermaid
%%{init: {'theme':'neutral', 'themeVariables': { 'fontSize':'16px'}}}%%
graph TB
    subgraph "Kubernetes Cluster"
        Pod[App Pod]
        KSA["Kubernetes Service Account<br/><b>myapp-sa</b><br/><br/>annotation:<br/>iam.gke.io/gcp-service-account:<br/><b>myapp@project.iam.gserviceaccount.com</b>"]
    end
    
    subgraph "Google Cloud Platform"
        IAMBinding["IAM Binding<br/>Grants workloadIdentityUser permission<br/>to K8s SA: applications/<b>myapp-sa</b>"]
        GSA["GCP Service Account<br/><b>myapp@project.iam.gserviceaccount.com</b>"]
        Perms[IAM Permissions<br/>roles/bigquery.dataViewer<br/>roles/cloudsql.client<br/>etc.]
        
        subgraph "GCP Services"
            BQ[BigQuery]
            GCS[Cloud Storage]
            PS[Pub/Sub]
        end
    end
    
    Pod -->|1. Uses| KSA
    KSA -->|2. Annotation links to| GSA
    IAMBinding -->|3. Grants permission<br/>to impersonate| GSA
    GSA -->|4. Has| Perms
    Perms -->|5. Access| BQ
    Perms -->|5. Access| GCS
    Perms -->|5. Access| PS
    
    Pod -.->|App uses ADC<br/>No keys needed!| BQ
    Pod -.->|Automatic auth| GCS
    Pod -.->|Seamless access| PS
    
    style Pod fill:#e1f5ff
    style KSA fill:#c8e6c9
    style IAMBinding fill:#fff9c4
    style GSA fill:#c8e6c9
    style BQ fill:#f3e5f5
    style GCS fill:#f3e5f5
    style PS fill:#f3e5f5
```

## 6. Configuration - Single Source of Truth

```mermaid
%%{init: {'theme':'neutral', 'themeVariables': { 'fontSize':'16px'}}}%%
graph TD
    Project[GitLab Project Name: myapp]
    Config[helm/values.yaml<br/>app_name: myapp<br/><i>must match project name</i>]
    
    Project -->|Should match| Config
    Config -->|Auto-constructs| Image[Docker Image<br/>docker-ra.art.code.pan.run/myapp:tag]
    Config -->|Auto-constructs| DevURL[Dev URL<br/>myapp.tsdev.paloaltonetworks.com]
    Config -->|Auto-constructs| ProdURL[Prod URL<br/>myapp.ts.paloaltonetworks.com]
    Config -->|Auto-constructs| KSA[Kubernetes SA<br/>myapp-sa]
    Config -->|Auto-constructs| GSA[GCP SA<br/>myapp@project.iam.gserviceaccount.com]
    
    style Project fill:#fff9c4
    style Config fill:#fff4e1
    style Image fill:#e1f5ff
    style DevURL fill:#e8f5e9
    style ProdURL fill:#c8e6c9
    style KSA fill:#f3e5f5
    style GSA fill:#f3e5f5
```

## 7. Observability - OpenTelemetry Tracing

**For full explanation and setup guide, see [TELEMETRY-SETUP.md](TELEMETRY-SETUP.md).**

```mermaid
%%{init: {'theme':'neutral', 'themeVariables': { 'fontSize':'16px'}}}%%
graph LR
    subgraph "Step A: Configuration (Helm)"
        HelmEnv["Helm Env Vars<br/><br/>Tells app where to send traces<br/>and what to call itself"]
    end
    
    subgraph "Step B: App Startup (runs once)"
        StartCmd["package.json:<br/>node --import ./instrumentation.mjs<br/><br/>Loads OTEL setup before app starts"]
        InstrumentationFile["instrumentation.mjs<br/><br/>Bootstrap file that:<br/>- Reads env vars<br/>- Sets up OTEL SDK<br/>- Enables auto-tracking"]
    end
    
    subgraph "Step C: Your App (runs continuously)"
        Backend["Backend App<br/><br/>Now has tracking built in"]
        Frontend["Frontend<br/><br/>Optional: can also send traces"]
    end
    
    subgraph "Step D: Traces Generated"
        AutoTraces["Auto Traces<br/><br/>OTEL automatically tracks:<br/>- HTTP requests<br/>- Database queries<br/>- External API calls"]
        ManualSpans["Manual Spans<br/><br/>You add code to track:<br/>- AI/LLM calls<br/>- Business workflows<br/>- Important operations"]
    end
    
    subgraph "Step E: Sent to Collector (in cluster)"
        OTELCollector["OTEL Collector<br/><br/>Shared service in cluster<br/>Receives traces from all apps<br/>URL: otel-agent.observability:4318"]
    end
    
    subgraph "Step F: Stored in Google Cloud"
        CloudTrace["Google Cloud Trace<br/><br/>Storage backend<br/>Collector handles auth (not your app)"]
    end
    
    subgraph "Step G: You View Traces"
        TraceUI["Google Trace Explorer<br/><br/>Web UI in Google Cloud Console<br/>You open this in browser"]
    end
    
    HelmEnv -->|provides config| InstrumentationFile
    StartCmd -->|loads| InstrumentationFile
    InstrumentationFile -->|enables tracking in| Backend
    
    Frontend -->|user request| Backend
    Backend -->|generates| AutoTraces
    Backend -->|generates| ManualSpans
    
    AutoTraces -->|send via OTLP| OTELCollector
    ManualSpans -->|send via OTLP| OTELCollector
    Frontend -.->|optional browser traces| OTELCollector
    
    OTELCollector -->|exports to| CloudTrace
    CloudTrace -->|displayed in| TraceUI
    
    style HelmEnv fill:#ffe1e1
    style InstrumentationFile fill:#fff4e1
    style Backend fill:#e8f5e9
    style Frontend fill:#e1f5ff
    style AutoTraces fill:#c8e6c9
    style ManualSpans fill:#fff9c4
    style OTELCollector fill:#f3e5f5
    style CloudTrace fill:#e0f2f1
    style TraceUI fill:#c8e6c9
```

---

## Executive Summary

**Problem:**
- Every new app requires 2-3 days of expert Kubernetes/GitLab work
- Steep learning curve for developers
- Inconsistent deployments across teams
- SSO and GCP access are manual, error-prone processes

**Solution:**
- Pre-built template with all infrastructure
- 30 minutes from code to production
- Single configuration point (app_name)
- Automatic SSO, GCP access, CI/CD, environments

**Impact:**
- 90% time reduction (3 days → 30 minutes)
- Democratizes deployment (no Kubernetes expertise needed)
- Standardized, secure deployments
- Developers focus on code, not infrastructure
