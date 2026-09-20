from typing import Any

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """The shape of every non-2xx response (see app/core/errors.py)."""

    error: ErrorDetail


# the type FastAPI expects for a route's `responses=` argument
Responses = dict[int | str, dict[str, Any]]
