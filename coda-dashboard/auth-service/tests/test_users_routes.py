"""Tests for the admin-only Role Management routes.

The service functions (list_users/update_user_role/list_role_changes) talk to
Postgres via raw psycopg2 — no ORM to swap in a sqlite double for, and no
Postgres available in this test environment — so they're monkeypatched here.
This still fully exercises what actually needs coverage: require_admin's JWT
"is this caller an admin?" gate, and the route-level validation (role must be
valid, can't change your own role, 404 on unknown user).
"""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from config import JWT_SECRET, JWT_ALGORITHM
import routes.users as users_routes
from routes.users import RoleUpdateRequest, get_role_changes, get_users, put_user_role, require_admin


def make_token(role, user_id="11111111-1111-1111-1111-111111111111", name="Test Admin", expired=False):
    delta = timedelta(minutes=-5) if expired else timedelta(minutes=30)
    payload = {"sub": user_id, "role": role, "name": name, "exp": datetime.utcnow() + delta}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def bearer(role, **kwargs):
    return f"Bearer {make_token(role, **kwargs)}"


class TestRequireAdmin:
    def test_admin_token_is_accepted(self):
        user_id, role = require_admin(authorization=bearer("admin"))
        assert role == "admin"

    @pytest.mark.parametrize("role", ["user", "doctor", "data-manager"])
    def test_non_admin_roles_are_rejected(self, role):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(authorization=bearer(role))
        assert exc_info.value.status_code == 403

    def test_missing_bearer_prefix_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(authorization="not-a-bearer-token")
        assert exc_info.value.status_code == 401

    def test_expired_token_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            require_admin(authorization=bearer("admin", expired=True))
        assert exc_info.value.status_code == 401


class TestGetUsers:
    def test_returns_list_from_service(self, monkeypatch):
        monkeypatch.setattr(users_routes, "list_users", lambda: [{"id": "u1", "role": "user"}])
        result = get_users(admin=("admin-id", "admin"))
        assert result == {"users": [{"id": "u1", "role": "user"}]}


class TestPutUserRole:
    def test_rejects_invalid_role(self):
        with pytest.raises(HTTPException) as exc_info:
            put_user_role("target-id", RoleUpdateRequest(role="superuser"), admin=("admin-id", "admin"))
        assert exc_info.value.status_code == 400

    def test_rejects_changing_own_role(self):
        with pytest.raises(HTTPException) as exc_info:
            put_user_role("admin-id", RoleUpdateRequest(role="doctor"), admin=("admin-id", "admin"))
        assert exc_info.value.status_code == 400

    def test_404_when_target_user_not_found(self, monkeypatch):
        monkeypatch.setattr(users_routes, "update_user_role", lambda *a, **kw: None)
        with pytest.raises(HTTPException) as exc_info:
            put_user_role("missing-id", RoleUpdateRequest(role="doctor"), admin=("admin-id", "admin"))
        assert exc_info.value.status_code == 404

    def test_valid_change_delegates_to_service(self, monkeypatch):
        captured = {}

        def fake_update(user_id, new_role, changed_by_id):
            captured["args"] = (user_id, new_role, changed_by_id)
            return {"user_id": user_id, "old_role": "user", "new_role": new_role}

        monkeypatch.setattr(users_routes, "update_user_role", fake_update)

        result = put_user_role("target-id", RoleUpdateRequest(role="doctor"), admin=("admin-id", "admin"))

        assert result == {"user_id": "target-id", "old_role": "user", "new_role": "doctor"}
        assert captured["args"] == ("target-id", "doctor", "admin-id")


class TestGetRoleChanges:
    def test_returns_list_from_service(self, monkeypatch):
        monkeypatch.setattr(users_routes, "list_role_changes", lambda skip, limit: [{"old_role": "user", "new_role": "doctor"}])
        result = get_role_changes(skip=0, limit=50, admin=("admin-id", "admin"))
        assert result == {"changes": [{"old_role": "user", "new_role": "doctor"}]}
