"""Fail-closed API-key authentication for knowledge-base HTTP routes."""

import os
import secrets
from typing import Annotated

from fastapi import HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    request: Request,
    provided: Annotated[str | None, Security(api_key_header)],
) -> None:
    """Reject unconfigured servers and missing, ambiguous or incorrect keys.

    Read process configuration only; never load credential files or log keys.
    API keys are restricted to ASCII so HTTP header decoding remains unambiguous.
    """
    expected = os.environ.get("KB_API_KEY", "")
    if not expected.strip() or expected != expected.strip() or not expected.isascii():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Knowledge-base authentication is not configured",
        )
    if (
        provided is None
        or len(request.headers.getlist("x-api-key")) != 1
        or not secrets.compare_digest(
            provided.encode("utf-8"), expected.encode("utf-8")
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "APIKey"},
        )
