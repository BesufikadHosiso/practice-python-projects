"""FastAPI application factory + static SPA hosting."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from . import config, database as db
from . import database
from .routers import activity, authors, auth, groups, jobs, posts, rules, stats


def _assert_storage_is_usable() -> None:
    """Fail loudly and helpfully when storage cannot work.

    On a serverless host (Vercel and friends) the deployment directory is
    read-only and there is no persistent disk, so the bundled SQLite file
    cannot be used at all. Without this guard the app dies later with a bare
    PermissionError; here we say exactly what to do instead.
    """
    if database.DRIVER == "postgres":
        return
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        probe = config.DATA_DIR / ".write-probe"
        probe.write_text("ok")
        probe.unlink()
    except OSError as error:
        raise RuntimeError(
            f"Cannot use the bundled SQLite database at {config.DB_PATH} ({error}). "
            "This usually means the filesystem is read-only, as it is on Vercel. "
            "Set DATABASE_URL to a PostgreSQL connection string "
            "(postgresql://user:pass@host/db?sslmode=require) and redeploy."
        ) from error


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{config.APP_NAME} API",
        version="1.0.0",
        description=(
            "Moderation console for Facebook group owners and admins: review the pending "
            "queue, bulk-delete posted content, purge reported posts and automate the "
            "boring parts with cleanup rules."
        ),
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r".*",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _assert_storage_is_usable()

    db.init_db()

    # Self-healing: if the database is empty (fresh clone, or `data/` was
    # wiped), build the demo workspace so the app is never served broken.
    if not (db.scalar("SELECT COUNT(*) FROM users") or 0):
        from .seed import seed

        seed(fresh=False, verbose=False)
    for module in (auth, groups, posts, rules, authors, jobs, activity, stats):
        app.include_router(module.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {
            "status": "ok",
            "app": config.APP_NAME,
            "database": str(config.DB_PATH),
            "users": db.scalar("SELECT COUNT(*) FROM users") or 0,
            "posts": db.scalar("SELECT COUNT(*) FROM posts") or 0,
        }

    if config.STATIC_DIR.exists():
        app.mount("/assets", StaticFiles(directory=config.STATIC_DIR), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str, request: Request):
            """Serve the single-page app; unknown API paths still 404 as JSON."""
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = config.STATIC_DIR / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            index = config.STATIC_DIR / "index.html"
            if not index.exists():
                raise HTTPException(status_code=404, detail="Frontend not built")
            return FileResponse(index)

    @app.exception_handler(404)
    async def not_found(request: Request, exc: Exception) -> JSONResponse:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        index = config.STATIC_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": "Not found"}, status_code=404)

    return app


app = create_app()
