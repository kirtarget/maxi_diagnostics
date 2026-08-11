"""Protected diagnostic administration mounted into the API application."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .router import router as admin_router


_ROOT = Path(__file__).resolve().parent


def install_admin(app: FastAPI) -> None:
    """Mount secret-free assets and the fully authenticated admin router."""
    app.mount(
        "/admin/static",
        StaticFiles(directory=_ROOT / "static"),
        name="diagnostic-admin-static",
    )
    app.include_router(admin_router)


__all__ = ["install_admin"]
