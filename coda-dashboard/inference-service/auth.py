"""JWT validation (defence in depth: the gateway also verifies). Same secret and claims as auth-service tokens."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException
from jose import JWTError, jwt

from config import ADMIN_ROLES, JWT_ALGORITHM, JWT_SECRET


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role in ADMIN_ROLES


def current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Token validation failed")

    # Connected-app tokens (e.g. Biomni, scope datasets:read) are not granted OCT inference.
    if payload.get("token_type") == "oauth_access":
        raise HTTPException(status_code=403, detail="This connected app is not authorized for this action")
    try:
        user_id = UUID(str(payload.get("sub")))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")
    return CurrentUser(id=user_id, role=payload.get("role", "user"))
