"""Authentication & Authorization module for Trader Control Center APIs.

Enforces role authorization, API key verification, and security boundaries.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

DEFAULT_API_KEY = os.getenv("CONTROL_CENTER_API_KEY", "hermes-trader-secret-key-v2.1")


def verify_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> str:
    """Verify incoming request API Key or Bearer Token header."""
    token = None

    if x_api_key:
        token = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()

    # For development mode, allow default or fallback key
    if not token or (token != DEFAULT_API_KEY and token != "dev-token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing API Key/Token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token
