import re
from uuid import UUID

import jwt
from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import get_settings
from app.core.rate_limit import enforce_rate_limit
from app.core.security import decode_access_token, decode_document_upload_token


class BodyTooLarge(Exception):
    pass


class SecurityMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        started = False

        async def secure_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Content-Type-Options"] = "nosniff"
                response_headers["Cache-Control"] = "private, no-store"
                response_headers["Referrer-Policy"] = "no-referrer"
                response_headers["X-Frame-Options"] = "DENY"
                response_headers["Content-Security-Policy"] = (
                    "default-src 'none'; frame-ancestors 'none'; sandbox"
                )
                response_headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        settings = get_settings()
        path = scope["path"]
        multipart = headers.get("content-type", "").lower().startswith("multipart/form-data")
        limit = (settings.max_document_size_mb + 1) * 1024 * 1024 if multipart else 1024 * 1024
        length = headers.get("content-length")
        if length and (not length.isdecimal() or int(length) > limit):
            await JSONResponse({"detail": "Request body too large"}, 413)(
                scope, receive, secure_send
            )
            return
        try:
            peer = scope.get("client")
            address = peer[0] if peer else "unknown"
            if scope["method"] == "POST" and path in {
                f"{settings.api_prefix}/auth/token",
                f"{settings.api_prefix}/auth/register",
            }:
                await enforce_rate_limit("auth-ip", address, 120, 60)
            if multipart:
                # Verify signature before Starlette can spool an unauthenticated upload to disk.
                match = re.fullmatch(
                    re.escape(settings.api_prefix)
                    + r"/projects/([0-9a-fA-F-]+)/documents(/direct-upload)?",
                    path,
                )
                token = headers.get("authorization", "")
                if not match or not token.lower().startswith("bearer "):
                    raise HTTPException(status_code=401, detail="Not authenticated")
                try:
                    if match[2]:
                        identity = decode_document_upload_token(token[7:], UUID(match[1]))
                    else:
                        identity = decode_access_token(token[7:])
                except (jwt.InvalidTokenError, ValueError):
                    raise HTTPException(
                        status_code=401, detail="Invalid upload authorization"
                    ) from None
                await enforce_rate_limit("upload-user", str(identity), 20, 300)
        except HTTPException as error:
            await JSONResponse({"detail": error.detail}, error.status_code, headers=error.headers)(
                scope, receive, secure_send
            )
            return

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    raise BodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, secure_send)
        except BodyTooLarge:
            if not started:
                await JSONResponse({"detail": "Request body too large"}, 413)(
                    scope, receive, secure_send
                )
