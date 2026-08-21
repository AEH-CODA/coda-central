"""Role-based access tests for the dataset-service routes.

Covers FULL_ACCESS_ROLES ("doctor", "admin", "data-manager"): full (uncapped)
preview sample rows, and exclusion from the access-request workflow — they
see the whole dataset directly instead of a 5-row preview, so there's nothing
for them to request. Also covers the request-management endpoints (reviewing
*other* users' requests), which "admin" and "data-manager" both have access
to but "doctor" does not.

Route functions are called directly (bypassing the ASGI/TestClient threadpool)
since FastAPI dispatches sync route handlers to a worker thread, and the
sqlite driver used for these tests doesn't tolerate that safely — production
runs on Postgres via psycopg2, which isn't affected. Calling the route
functions directly still exercises the exact same role-check logic.
"""
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from config import JWT_SECRET, JWT_ALGORITHM
from db import Base, engine, SessionLocal
from models import PreviewRequest
from routes.datasets import (
    approve_access_request,
    create_access_request,
    get_pending_requests,
    preview_dataset,
)
from services.preview_service import PreviewService


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


def make_token(role, user_id=None, name="Test User"):
    payload = {
        "sub": str(user_id or uuid4()),
        "role": role,
        "name": name,
        "exp": datetime.utcnow() + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def bearer(role, **kwargs):
    return f"Bearer {make_token(role, **kwargs)}"


def _sparql_results(n_rows):
    bindings = [{"patientId": {"value": f"P{i}"}} for i in range(n_rows)]
    return {"head": {"vars": ["patientId"]}, "results": {"bindings": bindings}}


class TestPreviewSampleRowsByRole:
    def test_user_role_is_capped_at_five_rows(self, monkeypatch):
        monkeypatch.setattr(
            PreviewService, "execute_sparql_query", staticmethod(lambda query, timeout: _sparql_results(15))
        )
        response = preview_dataset(
            PreviewRequest(sparql_query="SELECT * WHERE { ?s ?p ?o }"),
            user_role=(uuid4(), "user"),
        )
        assert len(response.sample_rows) == 5

    def test_doctor_role_gets_every_row(self, monkeypatch):
        monkeypatch.setattr(
            PreviewService, "execute_sparql_query", staticmethod(lambda query, timeout: _sparql_results(15))
        )
        response = preview_dataset(
            PreviewRequest(sparql_query="SELECT * WHERE { ?s ?p ?o }"),
            user_role=(uuid4(), "doctor"),
        )
        assert len(response.sample_rows) == 15

    def test_admin_role_gets_every_row(self, monkeypatch):
        monkeypatch.setattr(
            PreviewService, "execute_sparql_query", staticmethod(lambda query, timeout: _sparql_results(15))
        )
        response = preview_dataset(
            PreviewRequest(sparql_query="SELECT * WHERE { ?s ?p ?o }"),
            user_role=(uuid4(), "admin"),
        )
        assert len(response.sample_rows) == 15

    def test_data_manager_role_gets_every_row(self, monkeypatch):
        monkeypatch.setattr(
            PreviewService, "execute_sparql_query", staticmethod(lambda query, timeout: _sparql_results(15))
        )
        response = preview_dataset(
            PreviewRequest(sparql_query="SELECT * WHERE { ?s ?p ?o }"),
            user_role=(uuid4(), "data-manager"),
        )
        assert len(response.sample_rows) == 15


class TestAccessRequestWorkflowExcludesFullAccessRoles:
    @pytest.mark.parametrize("role", ["doctor", "admin", "data-manager"])
    def test_full_access_role_cannot_create_access_request(self, db, role):
        with pytest.raises(HTTPException) as exc_info:
            create_access_request(
                project_name="Test Project",
                reason="Need this data for a legitimate research purpose",
                nl_query="show me patients",
                sparql_query="SELECT * WHERE { ?s ?p ?o }",
                data_preview=None,
                supporting_document=None,
                authorization=bearer(role),
                db=db,
            )
        assert exc_info.value.status_code == 403

    def test_user_can_still_create_access_request(self, db):
        result = create_access_request(
            project_name="Test Project",
            reason="Need this data for a legitimate research purpose",
            nl_query="show me patients",
            sparql_query="SELECT * WHERE { ?s ?p ?o }",
            data_preview=None,
            supporting_document=None,
            authorization=bearer("user"),
            db=db,
        )
        assert result["status"] == "pending"


class TestRequestManagementEndpointsExcludeDoctors:
    def test_doctor_cannot_view_pending_requests(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_pending_requests(skip=0, limit=20, authorization=bearer("doctor"), db=db)
        assert exc_info.value.status_code == 403

    def test_doctor_cannot_approve_requests(self, db):
        with pytest.raises(HTTPException) as exc_info:
            approve_access_request(
                request_id=str(uuid4()),
                authorization=bearer("doctor"),
                db=db,
            )
        assert exc_info.value.status_code == 403

    def test_admin_can_view_pending_requests(self, db):
        result = get_pending_requests(skip=0, limit=20, authorization=bearer("admin"), db=db)
        assert "requests" in result

    def test_data_manager_can_view_pending_requests(self, db):
        result = get_pending_requests(skip=0, limit=20, authorization=bearer("data-manager"), db=db)
        assert "requests" in result

    def test_regular_user_cannot_view_pending_requests(self, db):
        with pytest.raises(HTTPException) as exc_info:
            get_pending_requests(skip=0, limit=20, authorization=bearer("user"), db=db)
        assert exc_info.value.status_code == 403
