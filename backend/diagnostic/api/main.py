"""Factory for the production Mini App ASGI application."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from diagnostic.admin import install_admin
from diagnostic.catalog import DiagnosticCatalog, load_catalog
from diagnostic.db.core import close_db, database_ready, init_db
from diagnostic.db.attempts import store_report_asset_bundle
from diagnostic.school import SchoolConfig, load_school
from diagnostic.settings import Settings

from .sessions import create_router, prepare_report_asset_bundles
from .league import create_league_router
from .offer_events import create_offer_events_router
from .trainer import create_trainer_router


def create_app(
    settings: Settings,
    school: SchoolConfig,
    catalog: DiagnosticCatalog,
    *,
    lifespan=None,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.school = school
    app.state.catalog = catalog
    app.state.report_asset_bundles = prepare_report_asset_bundles(school, catalog)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.miniapp_origin],
        allow_credentials=False,
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(RequestValidationError)
    async def bounded_request_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        if any("answers_too_large" in str(error.get("msg", "")) for error in errors):
            return JSONResponse(status_code=413, content={"detail": "answers_too_large"})
        safe_errors = [
            {
                "location": ".".join(str(part) for part in error.get("loc", ()))[:256],
                "code": str(error.get("type", "invalid"))[:64],
            }
            for error in errors[:10]
        ]
        return JSONResponse(
            status_code=422,
            content={"detail": "request_invalid", "errors": safe_errors},
        )

    @app.get("/healthz")
    async def healthz():
        if not await database_ready():
            return JSONResponse(status_code=503, content={"ok": False})
        return {"ok": True}

    app.include_router(create_router(catalog))
    app.include_router(create_league_router())
    app.include_router(create_offer_events_router())
    app.include_router(create_trainer_router(catalog))
    install_admin(app)
    return app


def create_default_app() -> FastAPI:
    settings = Settings.from_env()
    school = load_school()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            await init_db(settings.database_url, school)
            stored_bundle_ids: set[str] = set()
            for bundle_id, payload in app.state.report_asset_bundles.values():
                if bundle_id in stored_bundle_ids:
                    continue
                await store_report_asset_bundle(bundle_id, payload)
                stored_bundle_ids.add(bundle_id)
            yield
        finally:
            await close_db()

    return create_app(settings, school, load_catalog(school), lifespan=lifespan)
