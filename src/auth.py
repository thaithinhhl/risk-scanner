"""
Authentication module for FastAPI backend.
Validates JWT tokens issued by Next.js Auth.js.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError, ExpiredSignatureError

from src.config import _env

# Shared secret with Next.js Auth.js
AUTH_SECRET = _env("BACKEND_AUTH_SECRET", _env("AUTH_SECRET", ""))

security = HTTPBearer()


class CurrentUser:
    """Represents an authenticated user."""
    def __init__(self, id: str, email: str, role: str = "free"):
        self.id = id
        self.email = email
        self.role = role

    @property
    def is_free(self) -> bool:
        return self.role == "free"

    @property
    def is_premium(self) -> bool:
        return self.role in ("premium", "admin")

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token."""
    if not AUTH_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AUTH_SECRET not configured"
        )
    try:
        payload = jwt.decode(token, AUTH_SECRET, algorithms=["HS256"])
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTError as e:
        print(f"JWT Decode failed! Error: {e}, Secret length: {len(AUTH_SECRET)}, Token starts with: {token[:15]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """FastAPI dependency to get the current authenticated user from JWT."""
    payload = decode_token(credentials.credentials)

    user_id = payload.get("sub")
    email = payload.get("email", "")
    role = payload.get("role", "free")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    return CurrentUser(id=str(user_id), email=email, role=role)


def require_role(minimum_role: str = "free"):
    """
    Factory that returns a dependency requiring a minimum role level.

    Usage:
        @router.post("/premium-feature", dependencies=[Depends(require_role("premium"))])
        async def premium_endpoint(user: CurrentUser = Depends(get_current_user)):
            ...
    """
    role_hierarchy = {"free": 0, "premium": 1, "admin": 2}
    min_level = role_hierarchy.get(minimum_role, 0)

    def role_checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        user_level = role_hierarchy.get(user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum_role} role or higher. Current role: {user.role}",
            )
        return user

    return role_checker


# Usage counters helper (for rate limiting)
class UsageLimits:
    """Usage limits by role."""
    FREE_CONTRACTS_PER_MONTH = 5
    FREE_QA_PER_DAY = 10
    FREE_API_CALLS_PER_HOUR = 100
    FREE_MAX_UPLOAD_SIZE_MB = 5

    PREMIUM_CONTRACTS_PER_MONTH = float("inf")
    PREMIUM_QA_PER_DAY = float("inf")
    PREMIUM_API_CALLS_PER_HOUR = 1000
    PREMIUM_MAX_UPLOAD_SIZE_MB = 25

    @classmethod
    def get_limits(cls, role: str) -> dict:
        if role == "free":
            return {
                "contracts_per_month": cls.FREE_CONTRACTS_PER_MONTH,
                "qa_per_day": cls.FREE_QA_PER_DAY,
                "api_calls_per_hour": cls.FREE_API_CALLS_PER_HOUR,
                "max_upload_size_mb": cls.FREE_MAX_UPLOAD_SIZE_MB,
            }
        return {
            "contracts_per_month": cls.PREMIUM_CONTRACTS_PER_MONTH,
            "qa_per_day": cls.PREMIUM_QA_PER_DAY,
            "api_calls_per_hour": cls.PREMIUM_API_CALLS_PER_HOUR,
            "max_upload_size_mb": cls.PREMIUM_MAX_UPLOAD_SIZE_MB,
        }
