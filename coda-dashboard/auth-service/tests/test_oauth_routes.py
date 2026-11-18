"""Tests for the OAuth2 provider routes (Connected Apps, e.g. Biomni).

Like test_users_routes.py, the service functions talk to Postgres via raw
psycopg2 with no ORM/sqlite double and no Postgres available here, so
services.oauth_service is monkeypatched. This exercises require_session_user's
JWT gate (including rejecting oauth_access tokens) and the route-level
validation/error mapping.
"""
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from config import JWT_SECRET, JWT_ALGORITHM
import routes.oauth as oauth_routes
from routes.oauth import (
    AuthorizeRequest,
    IntrospectRequest,
    TokenRequest,
    authorize,
    delete_grant,
    get_grants,
    introspect,
    require_session_user,
    token,
)


def make_session_token(user_id="11111111-1111-1111-1111-111111111111", role="user", expired=False):
    delta = timedelta(minutes=-5) if expired else timedelta(minutes=30)
    payload = {"sub": user_id, "role": role, "exp": datetime.utcnow() + delta}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def make_oauth_access_token(user_id="11111111-1111-1111-1111-111111111111"):
    payload = {
        "sub": user_id,
        "token_type": "oauth_access",
        "client_id": "biomni",
        "scope": "datasets:read",
        "jti": "some-jti",
        "exp": datetime.utcnow() + timedelta(days=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def bearer(token_str):
    return f"Bearer {token_str}"


class TestRequireSessionUser:
    def test_valid_session_token_is_accepted(self):
        user_id = require_session_user(authorization=bearer(make_session_token()))
        assert user_id == "11111111-1111-1111-1111-111111111111"

    def test_oauth_access_token_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            require_session_user(authorization=bearer(make_oauth_access_token()))
        assert exc_info.value.status_code == 403

    def test_missing_bearer_prefix_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            require_session_user(authorization="not-a-bearer-token")
        assert exc_info.value.status_code == 401

    def test_expired_token_is_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            require_session_user(authorization=bearer(make_session_token(expired=True)))
        assert exc_info.value.status_code == 401


class TestAuthorize:
    def test_unknown_client_is_rejected(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "get_client", lambda client_id: None)
        req = AuthorizeRequest(client_id="ghost", redirect_uri="http://x", scope="datasets:read", state="s")
        with pytest.raises(HTTPException) as exc_info:
            authorize(req, user_id="u1")
        assert exc_info.value.status_code == 400

    def test_unregistered_redirect_uri_is_rejected(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "get_client", lambda client_id: {
            "redirect_uris": ["http://127.0.0.1:7860/oauth/callback"],
            "allowed_scopes": ["datasets:read"],
        })
        req = AuthorizeRequest(client_id="biomni", redirect_uri="http://evil.example/cb", scope="datasets:read", state="s")
        with pytest.raises(HTTPException) as exc_info:
            authorize(req, user_id="u1")
        assert exc_info.value.status_code == 400

    def test_scope_outside_allowed_is_rejected(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "get_client", lambda client_id: {
            "redirect_uris": ["http://127.0.0.1:7860/oauth/callback"],
            "allowed_scopes": ["datasets:read"],
        })
        req = AuthorizeRequest(
            client_id="biomni", redirect_uri="http://127.0.0.1:7860/oauth/callback",
            scope="datasets:read datasets:write", state="s",
        )
        with pytest.raises(HTTPException) as exc_info:
            authorize(req, user_id="u1")
        assert exc_info.value.status_code == 400

    def test_valid_request_returns_redirect_with_code_and_state(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "get_client", lambda client_id: {
            "redirect_uris": ["http://127.0.0.1:7860/oauth/callback"],
            "allowed_scopes": ["datasets:read"],
        })
        monkeypatch.setattr(oauth_routes, "create_authorization_code", lambda **kw: "the-code")
        req = AuthorizeRequest(
            client_id="biomni", redirect_uri="http://127.0.0.1:7860/oauth/callback",
            scope="datasets:read", state="xyz",
        )
        result = authorize(req, user_id="u1")
        assert result == {"redirect_url": "http://127.0.0.1:7860/oauth/callback?code=the-code&state=xyz"}


class TestToken:
    def test_rejects_unsupported_grant_type(self):
        req = TokenRequest(grant_type="password", code="c", client_id="biomni", client_secret="s", redirect_uri="r")
        with pytest.raises(HTTPException) as exc_info:
            token(req)
        assert exc_info.value.status_code == 400

    def test_maps_service_valueerror_to_400(self, monkeypatch):
        def fake_exchange(**kw):
            raise ValueError("Invalid client credentials")
        monkeypatch.setattr(oauth_routes, "exchange_code_for_token", fake_exchange)
        req = TokenRequest(grant_type="authorization_code", code="c", client_id="biomni", client_secret="wrong", redirect_uri="r")
        with pytest.raises(HTTPException) as exc_info:
            token(req)
        assert exc_info.value.status_code == 400

    def test_valid_exchange_returns_bearer_token(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "exchange_code_for_token", lambda **kw: ("the-access-token", "datasets:read", 2591999))
        req = TokenRequest(grant_type="authorization_code", code="c", client_id="biomni", client_secret="s", redirect_uri="r")
        result = token(req)
        assert result == {
            "access_token": "the-access-token",
            "token_type": "bearer",
            "expires_in": 2591999,
            "scope": "datasets:read",
        }


class TestIntrospect:
    def test_garbage_token_is_inactive(self):
        assert introspect(IntrospectRequest(token="not-a-jwt")) == {"active": False}

    def test_session_token_is_inactive(self):
        result = introspect(IntrospectRequest(token=make_session_token()))
        assert result == {"active": False}

    def test_revoked_grant_is_inactive(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "is_grant_revoked", lambda jti: True)
        result = introspect(IntrospectRequest(token=make_oauth_access_token()))
        assert result == {"active": False}

    def test_active_grant_returns_claims(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "is_grant_revoked", lambda jti: False)
        result = introspect(IntrospectRequest(token=make_oauth_access_token()))
        assert result == {
            "active": True,
            "sub": "11111111-1111-1111-1111-111111111111",
            "scope": "datasets:read",
            "client_id": "biomni",
        }


class TestGrants:
    def test_get_grants_delegates_to_service(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "list_grants", lambda user_id: [{"id": "g1", "client_id": "biomni"}])
        assert get_grants(user_id="u1") == {"grants": [{"id": "g1", "client_id": "biomni"}]}

    def test_delete_grant_404_when_not_found(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "revoke_grant", lambda grant_id, user_id: False)
        with pytest.raises(HTTPException) as exc_info:
            delete_grant("missing-id", user_id="u1")
        assert exc_info.value.status_code == 404

    def test_delete_grant_success(self, monkeypatch):
        monkeypatch.setattr(oauth_routes, "revoke_grant", lambda grant_id, user_id: True)
        assert delete_grant("g1", user_id="u1") == {"status": "revoked"}
