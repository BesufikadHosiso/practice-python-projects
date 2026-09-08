"""FastAPI application factory + static SPA hosting."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from . import config, database as db
from .routers import activity, authors, auth, groups, jobs, posts, rules, stats


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

    db.init_db()

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
