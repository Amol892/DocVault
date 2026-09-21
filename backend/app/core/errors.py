"""One error shape for the whole API: {"error": {"code": "...", "message": "..."}}.

`code` is stable and machine-readable; `message` is safe to show to a user. Messages never echo
request values (a validation error must not repeat a password back).
"""

import logging
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_STATUS_CODES = {
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def unauthorized() -> ApiError:
    # One message for every reason (missing, malformed, expired, revoked, deactivated) so a caller
    # learns nothing about why.
    return ApiError(401, "UNAUTHORIZED", "Not authenticated.", {"WWW-Authenticate": "Bearer"})


def forbidden(message: str = "You don't have permission to do that.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def not_found(message: str = "Not found.") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


async def _api_error_handler(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(ApiError, exc)
    return JSONResponse(
        error_body(exc.code, exc.message), status_code=exc.status_code, headers=exc.headers
    )


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    code = _STATUS_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    first: dict[str, Any] = exc.errors()[0] if exc.errors() else {}
    location = ".".join(str(part) for part in first.get("loc", ()) if part not in ("body", "query"))
    problem = str(first.get("msg", "Invalid request."))
    message = f"{location}: {problem}" if location else problem
    return JSONResponse(error_body("VALIDATION_ERROR", message), status_code=422)


async def _unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(
        error_body("INTERNAL_ERROR", "Something went wrong on our side."), status_code=500
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
