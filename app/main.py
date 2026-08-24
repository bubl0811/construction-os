from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_settings()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if settings.environment != "production" else None,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
