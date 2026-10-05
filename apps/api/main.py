"""Minimal HTTP API: uvicorn apps.api.main:app --host 0.0.0.0 --port 8000"""
from __future__ import annotations

from fastapi import FastAPI

from .routes import health

API_PREFIX = "/api/v1"

app = FastAPI(title="Discord Chess API", version="0.1.0")
app.include_router(health.router, prefix=API_PREFIX)


if __name__ == "__main__":
    import uvicorn
    from config.settings import load_settings

    settings = load_settings()
    uvicorn.run("apps.api.main:app", host=settings.api_host, port=settings.api_port, reload=False)
