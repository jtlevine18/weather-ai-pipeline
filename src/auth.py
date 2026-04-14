"""JWT authentication for the weather pipeline API.

Provides password hashing, token creation/validation, and FastAPI dependencies
for route-level access control.

Roles:
  - operator: full access (create users, trigger pipeline)
  - viewer: read-only data access
"""

from __future__ import annotations
import os
import warnings
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel


def _resolve_secret_key() -> str:
    """Resolve JWT secret, refusing to start in production without one.

    Production is detected via ENV=production (case-insensitive). In any
    non-production environment an explicit dev fallback is used and a
    warning is emitted, so local development still works without setup.
    """
    secret = os.getenv("JWT_SECRET_KEY", "")
    env = os.getenv("ENV", "").lower()
    if secret:
        return secret
    if env == "production":
        raise RuntimeError(
            "JWT_SECRET_KEY must be set when ENV=production. "
            "Refusing to start with an insecure default."
        )
    warnings.warn(
        "JWT_SECRET_KEY not set — using insecure default. "
        "Set JWT_SECRET_KEY in .env for production.",
        stacklevel=2,
    )
    return "dev-secret-DO-NOT-USE-IN-PRODUCTION"


SECRET_KEY = _resolve_secret_key()
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


class User(BaseModel):
    username: str
    role: str = "viewer"


class TokenData(BaseModel):
    username: str
    role: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(username: str, role: str = "viewer") -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "role": role, "exp": expire},
        SECRET_KEY, algorithm=ALGORITHM,
    )


def decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenData(username=payload["sub"], role=payload.get("role", "viewer"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """FastAPI dependency — extracts user from Bearer token."""
    data = decode_token(creds.credentials)
    return User(username=data.username, role=data.role)


def require_operator(user: User = Depends(get_current_user)) -> User:
    """FastAPI dependency — requires operator role."""
    if user.role != "operator":
        raise HTTPException(status_code=403, detail="Operator role required")
    return user
