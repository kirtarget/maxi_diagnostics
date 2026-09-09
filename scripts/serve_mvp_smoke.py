"""Local browser harness. Requires TEST_DATABASE_URL ending in _test.

Run the Mini App on 127.0.0.1:3000, then run this script with PYTHONPATH=backend.
Open http://127.0.0.1:3002/?smoke_user=8000000001. Each bounded synthetic user
has independent persisted state. This process never starts a bot or worker.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote, urlencode, urlsplit

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from diagnostic.api.main import create_app
from diagnostic.catalog import load_catalog
from diagnostic.db.attempts import store_report_asset_bundle
from diagnostic.db.core import close_db, init_db
from diagnostic.school import load_school
from diagnostic.settings import Settings


ORIGIN = "http://127.0.0.1:3002"
FRONTEND = "http://127.0.0.1:3000"
BOT_TOKEN = "9999999999:local-smoke-test-token-not-a-real-bot"
APPLICATION_SECRET = "local-smoke-only-stable-secret-12345678901234567890"
ROOT = Path(__file__).resolve().parents[1]


def test_database_url() -> str:
    value = os.environ.get("TEST_DATABASE_URL", "")
    parsed = urlsplit(value)
    database = unquote(parsed.path.removeprefix("/"))
    if (
        parsed.scheme not in {"postgresql", "postgres"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or not re.fullmatch(r"[A-Za-z0-9_]+_test", database)
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("Set TEST_DATABASE_URL to a localhost PostgreSQL database ending in _test")
    return value


def signed_init_data(user_id: int) -> str:
    pairs = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "first_name": "Smoke"}, separators=(",", ":")),
    }
    check = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def fixture_script(user_id: int) -> str:
    init_data = json.dumps(signed_init_data(user_id))
    return (
        "<script>window.Telegram={WebApp:{initData:" + init_data
        + ",platform:'tdesktop',version:'8.0',ready(){},expand(){},close(){},"
        "setHeaderColor(){},setBackgroundColor(){},"
        "BackButton:{show(){},hide(){},onClick(){},offClick(){}}}};</script>"
    )


def create_harness() -> FastAPI:
    database_url = test_database_url()
    os.environ.update({
        "DATABASE_URL": database_url,
        "BOT_TOKEN": BOT_TOKEN,
        "APPLICATION_SECRET": APPLICATION_SECRET,
        "MINIAPP_URL": ORIGIN,
        "MINIAPP_ORIGIN": ORIGIN,
        "ANALYTICS_WEBHOOK_URL": "",
        "BOT_POLLING_ENABLED": "false",
    })
    settings = Settings(
        database_url=database_url, bot_token=BOT_TOKEN,
        miniapp_url=ORIGIN, miniapp_origin=ORIGIN,
        admin_username="smoke-local", admin_password="smoke-local-not-production",
        analytics_webhook_url=None, application_secret=APPLICATION_SECRET,
        bot_polling_enabled=False,
    )
    school = load_school(ROOT / "school")
    backend = create_app(settings, school, load_catalog(school))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            await init_db(database_url, school)
            bundles = dict(backend.state.report_asset_bundles.values())
            for bundle_id, payload in bundles.items():
                await store_report_asset_bundle(bundle_id, payload)
            async with (
                httpx.AsyncClient(base_url=FRONTEND, trust_env=False, timeout=30) as frontend,
                httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=backend), base_url=ORIGIN,
                    trust_env=False, timeout=30,
                ) as api,
            ):
                app.state.frontend = frontend
                app.state.api = api
                yield
        finally:
            await close_db()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route("/{path:path}", methods=["GET", "POST"])
    async def proxy(path: str, request: Request):
        if request.headers.get("host") not in {"127.0.0.1:3002", "localhost:3002"}:
            raise HTTPException(400, "localhost_only")
        if path.startswith("api/diagnostics/") or path == "healthz":
            upstream = await app.state.api.request(
                request.method, "/" + path,
                content=await request.body(),
                headers={"content-type": "application/json", "origin": ORIGIN},
            )
            return Response(upstream.content, status_code=upstream.status_code,
                            media_type=upstream.headers.get("content-type"),
                            headers={"Cache-Control": "no-store"})
        if request.method != "GET" or not (path == "" or path.startswith(("_next/", "assets/", "fonts/")) or path == "favicon.ico"):
            raise HTTPException(404)
        upstream = await app.state.frontend.get("/" + path, headers={"accept-encoding": "identity"})
        content_type = upstream.headers.get("content-type", "application/octet-stream")
        content = upstream.content
        if "text/html" in content_type:
            try:
                user_id = int(request.query_params.get("smoke_user", "8000000001"))
            except ValueError as exc:
                raise HTTPException(400, "invalid_smoke_user") from exc
            if not 8_000_000_000 <= user_id <= 8_000_000_999:
                raise HTTPException(400, "smoke_user_out_of_range")
            html = re.sub(
                r'<script[^>]*src="https://telegram\.org/js/telegram-web-app\.js[^" ]*"[^>]*></script>',
                "", upstream.text,
            )
            content = html.replace("<head>", "<head>" + fixture_script(user_id), 1).encode("utf-8")
        return Response(content, status_code=upstream.status_code, media_type=content_type,
                        headers={"Cache-Control": "no-store"})

    return app


if __name__ == "__main__":
    uvicorn.run(create_harness(), host="127.0.0.1", port=3002, access_log=False)
