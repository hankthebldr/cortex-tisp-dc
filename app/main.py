from fastapi import FastAPI

from app import __version__

app = FastAPI(title="TISP Evolution", version=__version__)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/")
async def root() -> dict[str, str]:
    return {"app": "tisp-evolution", "version": __version__}
