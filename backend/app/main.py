"""Точка входа FastAPI-приложения FinTrack."""
from fastapi import FastAPI

app = FastAPI(
    title="FinTrack API",
    version="0.1.0",
    description="Self-hosted веб-приложение для учёта личных финансов.",
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    """Health check: возвращает {'status': 'ok'}, если backend запущен."""
    return {"status": "ok"}
