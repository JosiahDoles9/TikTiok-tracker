"""ASGI entrypoint shim so `uvicorn main:app --reload` works from repo root."""

from backend.main import app

__all__ = ["app"]
