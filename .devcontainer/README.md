# Dev Container

Rapid local-iteration environment for TISP Evolution.

## Two ways to use it

### A. VS Code / Cursor devcontainer (recommended)

1. Install the "Dev Containers" extension.
2. `Cmd+Shift+P` → "Dev Containers: Reopen in Container".
3. Container builds, deps install, pytest runs. Terminal lands you at `/workspace`.
4. Start the dev server: `uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload`
5. Open http://localhost:8080 — hot-reload is on, edits trigger a reload.

### B. Plain docker compose (no VS Code required)

```bash
cd .devcontainer
docker compose up -d --build
docker compose exec app bash
# inside the container:
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Tear down: `docker compose down`.

## Why a devcontainer and not just .venv?

- Matches the production image base (`docker-io.art.code.pan.run/library/python:3.11-slim`) so "works on my laptop" and "works in GKE" stay aligned.
- Pre-wires the PANW Artifactory proxy flags for `pip install` so new dependencies pick up without `CERTIFICATE_VERIFY_FAILED`.
- Mounts the source tree read-write; code changes land immediately via `--reload`.
- `pip` cache lives in a named volume so container rebuilds are fast.
- Opens on port 8080 — same as the production container.

## Env vars

Copy `.env.example` → `.env` at the repo root. `docker-compose.yml` auto-loads it.
