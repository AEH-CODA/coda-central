"""User/role management routes — admin only."""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel
from jose import jwt, JWTError

from config import JWT_SECRET, JWT_ALGORITHM
from services.user_service import list_users, update_user_role, list_role_changes

router = APIRouter()

VALID_ROLES = {"user", "doctor", "data-manager", "admin"}


def require_admin(authorization: str = Header(...)) -> tuple:
    """
    Verify the JWT and require the caller to have the admin role.

    Returns:
        Tuple of (user_id, role) for the calling admin
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Invalid token format",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.split(" ")[1]

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    role = payload.get("role", "user")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing sub claim")

    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can manage user roles")

    return user_id, role


class RoleUpdateRequest(BaseModel):
    role: str


@router.get("/users")
def get_users(admin=Depends(require_admin)):
    """List all users so an admin can assign roles. Admin only."""
    try:
        return {"users": list_users()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list users: {str(e)}")


@router.put("/users/{user_id}/role")
def put_user_role(user_id: str, req: RoleUpdateRequest, admin=Depends(require_admin)):
    """Change a user's role and record it in the role_changes audit trail. Admin only."""
    if req.role not in VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}"
        )

    admin_id, _ = admin

    if user_id == admin_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    try:
        result = update_user_role(user_id, req.role, admin_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update role: {str(e)}")

    if result is None:
        raise HTTPException(status_code=404, detail="User not found")

    return result


@router.get("/role-changes")
def get_role_changes(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin=Depends(require_admin)
):
    """List the role-change audit trail, most recent first. Admin only."""
    try:
        return {"changes": list_role_changes(skip, limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list role changes: {str(e)}")
