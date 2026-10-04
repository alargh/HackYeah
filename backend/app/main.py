"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.container import Container, build_container
from app.core.db import init_db
from app.core.logging import configure_logging, fields, get_logger
from app.workers.jobs import recover_interrupted

log = get_logger("tutorly")


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    settings.media_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db(settings.sqlalchemy_url)
        recovered = recover_interrupted()
        app.state.container = container or build_container(settings)
        c: Container = app.state.container
        log.info(
            "Tutorly backend started",
            extra=fields(
                model=settings.gemini_model,
                gemini_configured=c.pipeline is not None,
                recovered_lessons=recovered,
                prompt_versions=c.prompts.versions(),
            ),
        )
        yield
        c.jobs.shutdown()

    app = FastAPI(title="Tutorly API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.mount("/media", StaticFiles(directory=settings.media_dir), name="media")
    return app


app = create_app()
