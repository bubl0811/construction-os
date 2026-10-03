import asyncio
import os
import tempfile
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.core import rate_limit
from app.core.config import get_settings
from app.modules.auth.dependencies import SessionDep

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


@router.get("", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()


def storage_ready() -> None:
    root = get_settings().document_storage_path
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=root, prefix=".readiness-") as handle:
        handle.write(b"readiness")
        handle.flush()
        os.fsync(handle.fileno())
        handle.seek(0)
        if handle.read() != b"readiness":
            raise OSError("Storage verification failed")


@router.get("/ready")
async def readiness(session: SessionDep) -> JSONResponse:
    checks: dict[str, str] = {}
    tasks: list[tuple[str, Callable[[], Awaitable[Any]]]] = [
        ("database", lambda: session.execute(text("SELECT 1"))),
        ("redis", lambda: rate_limit.rate_limit_store().ping()),
        ("storage", lambda: asyncio.to_thread(storage_ready)),
    ]
    for name, task in tasks:
        try:
            await asyncio.wait_for(task(), timeout=3)
            checks[name] = "ok"
        except Exception:
            # Public health responses never reveal connection strings or paths.
            checks[name] = "unavailable"
    ready = all(value == "ok" for value in checks.values())
    return JSONResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status_code=200 if ready else 503,
    )
