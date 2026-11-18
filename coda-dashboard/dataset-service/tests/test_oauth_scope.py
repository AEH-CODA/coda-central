"""
Tests for the datasets:read scope path used by Connected Apps (e.g. Biomni).

Covers: require_scope() accepting session tokens unchanged, accepting/rejecting
oauth_access tokens by scope and by auth-service's revocation check, the
existing verify_token/extract_user_role/extract_user_info dependencies now
rejecting oauth_access tokens outright, and the CSV export endpoint end to end.

Route functions are called directly against sqlite, matching the pattern in
test_datasets_routes.py (production runs on Postgres via psycopg2, which
isn't affected by the sqlite/threadpool caveat noted there).
"""
import asyncio
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from config import JWT_SECRET, JWT_ALGORITHM
from db import Base, engine, SessionLocal
from models import DatasetSaveRequest
import routes.datasets as datasets_routes
from routes.datasets import (
    export_dataset_csv,
    extract_user_info,
    extract_user_role,
    get_dataset_detail,
    list_datasets,
    require_scope,
    save_dataset,
    verify_token,
)
from services.dataset_service import DatasetService


@pytest.fixture(scope="module", autouse=True)
def _tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def make_session_token(role="user", user_id=None):
    payload = {
        "sub": str(user_id or uuid4()),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def make_oauth_token(user_id, scope="datasets:read", expired=False):
    delta = timedelta(minutes=-5) if expired else timedelta(days=30)
    payload = {
        "sub": str(user_id),
        "token_type": "oauth_access",
        "client_id": "biomni",
        "scope": scope,
        "jti": "test-jti",
        "exp": datetime.utcnow() + delta,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def bearer(token_str):
    return f"Bearer {token_str}"


class TestRequireScopeAcceptsSessionTokens:
    def test_any_role_session_token_is_accepted_unchanged(self):
        user_id = uuid4()
        dep = require_scope("datasets:read")
        result = dep(authorization=bearer(make_session_token(role="user", user_id=user_id)))
        assert result == user_id

    def test_garbage_non_jwt_token_is_a_clean_401_not_a_crash(self):
        """Regression test: python-jose's jwt module has no
        InvalidSignatureError/DecodeError attributes (those are PyJWT names).
        A malformed bearer token used to hit AttributeError while Python
        evaluated those except clauses, surfacing as an unhandled 500
        instead of 401 — see routes/datasets.py's require_scope/verify_token/
        extract_user_role/extract_user_info."""
        dep = require_scope("datasets:read")
        with pytest.raises(HTTPException) as exc_info:
            dep(authorization=bearer("not-a-real-jwt"))
        assert exc_info.value.status_code == 401

    def test_verify_token_garbage_token_is_a_clean_401(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token(authorization=bearer("not-a-real-jwt"))
        assert exc_info.value.status_code == 401


class TestRequireScopeWithOAuthTokens:
    def test_matching_scope_and_active_grant_is_accepted(self, monkeypatch):
        monkeypatch.setattr(datasets_routes, "introspect_is_active", lambda token: True)
        user_id = uuid4()
        dep = require_scope("datasets:read")
        result = dep(authorization=bearer(make_oauth_token(user_id)))
        assert result == user_id

    def test_missing_required_scope_is_rejected(self, monkeypatch):
        monkeypatch.setattr(datasets_routes, "introspect_is_active", lambda token: True)
        dep = require_scope("datasets:read")
        with pytest.raises(HTTPException) as exc_info:
            dep(authorization=bearer(make_oauth_token(uuid4(), scope="other:scope")))
        assert exc_info.value.status_code == 403

    def test_revoked_grant_is_rejected(self, monkeypatch):
        monkeypatch.setattr(datasets_routes, "introspect_is_active", lambda token: False)
        dep = require_scope("datasets:read")
        with pytest.raises(HTTPException) as exc_info:
            dep(authorization=bearer(make_oauth_token(uuid4())))
        assert exc_info.value.status_code == 401

    def test_expired_oauth_token_is_rejected(self):
        dep = require_scope("datasets:read")
        with pytest.raises(HTTPException) as exc_info:
            dep(authorization=bearer(make_oauth_token(uuid4(), expired=True)))
        assert exc_info.value.status_code == 401


class TestWriteAndOtherDependenciesRejectOAuthTokens:
    """An oauth_access token must never reach save/update/delete/preview/access-request paths."""

    def test_verify_token_rejects_oauth_access_token(self):
        with pytest.raises(HTTPException) as exc_info:
            verify_token(authorization=bearer(make_oauth_token(uuid4())))
        assert exc_info.value.status_code == 403

    def test_extract_user_role_rejects_oauth_access_token(self):
        with pytest.raises(HTTPException) as exc_info:
            extract_user_role(authorization=bearer(make_oauth_token(uuid4())))
        assert exc_info.value.status_code == 403

    def test_extract_user_info_rejects_oauth_access_token(self):
        with pytest.raises(HTTPException) as exc_info:
            extract_user_info(authorization=bearer(make_oauth_token(uuid4())))
        assert exc_info.value.status_code == 403

    def test_verify_token_still_accepts_session_token(self):
        user_id = uuid4()
        assert verify_token(authorization=bearer(make_session_token(user_id=user_id))) == user_id


def _sparql_results():
    return {
        "head": {"vars": ["patientId", "age"]},
        "results": {"bindings": [
            {"patientId": {"value": "P1"}, "age": {"value": "42"}},
            {"patientId": {"value": "P2"}, "age": {"value": "57"}},
        ]},
    }


class TestConnectedAppReadFlow:
    """End-to-end: a user saves a dataset via the normal UI session token, then
    a Biomni-style oauth_access token lists it, fetches it, and exports it as CSV."""

    def test_full_flow(self, db, monkeypatch):
        monkeypatch.setattr(datasets_routes, "introspect_is_active", lambda token: True)

        user_id = uuid4()
        save_dataset(
            req=DatasetSaveRequest(
                nl_query="show patients", sparql_query="SELECT ...",
                results=_sparql_results(), name="My Cohort", description=None,
            ),
            user_id=user_id,
            db=db,
        )

        oauth_token = make_oauth_token(user_id)

        listed = list_datasets(
            user_id=require_scope("datasets:read")(authorization=bearer(oauth_token)),
            skip=0, limit=10, db=db,
        )
        assert listed["total"] == 1
        dataset_id = str(listed["datasets"][0].id)

        detail = get_dataset_detail(
            dataset_id=dataset_id,
            user_id=require_scope("datasets:read")(authorization=bearer(oauth_token)),
            db=db,
        )
        assert detail.results == _sparql_results()

        csv_response = export_dataset_csv(
            dataset_id=dataset_id,
            format="csv",
            user_id=require_scope("datasets:read")(authorization=bearer(oauth_token)),
            db=db,
        )
        async def _drain():
            return "".join([chunk async for chunk in csv_response.body_iterator])

        content = asyncio.run(_drain())
        assert "patientId,age" in content
        assert "P1,42" in content
        assert csv_response.headers["content-type"].startswith("text/csv")

    def test_export_rejects_unsupported_format(self, db, monkeypatch):
        monkeypatch.setattr(datasets_routes, "introspect_is_active", lambda token: True)
        user_id = uuid4()
        dataset = DatasetService.save_dataset(
            db=db, user_id=user_id, nl_query="q", sparql_query="s",
            results=_sparql_results(), name="X", description=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            export_dataset_csv(
                dataset_id=str(dataset.id), format="xlsx",
                user_id=require_scope("datasets:read")(authorization=bearer(make_oauth_token(user_id))),
                db=db,
            )
        assert exc_info.value.status_code == 400

    def test_export_404_for_missing_dataset(self, db, monkeypatch):
        monkeypatch.setattr(datasets_routes, "introspect_is_active", lambda token: True)
        user_id = uuid4()
        with pytest.raises(HTTPException) as exc_info:
            export_dataset_csv(
                dataset_id=str(uuid4()), format="csv",
                user_id=require_scope("datasets:read")(authorization=bearer(make_oauth_token(user_id))),
                db=db,
            )
        assert exc_info.value.status_code == 404

    def test_oauth_token_cannot_see_another_users_dataset(self, db, monkeypatch):
        monkeypatch.setattr(datasets_routes, "introspect_is_active", lambda token: True)
        owner_id = uuid4()
        other_id = uuid4()
        dataset = DatasetService.save_dataset(
            db=db, user_id=owner_id, nl_query="q", sparql_query="s",
            results=_sparql_results(), name="Owner only", description=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            get_dataset_detail(
                dataset_id=str(dataset.id),
                user_id=require_scope("datasets:read")(authorization=bearer(make_oauth_token(other_id))),
                db=db,
            )
        assert exc_info.value.status_code == 404
