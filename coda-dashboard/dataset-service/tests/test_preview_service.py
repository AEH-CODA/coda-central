"""Tests for role-driven sample-row behavior in PreviewService.

Users get a 5-row preview and must submit an access request for the rest;
doctors (and admins/data managers) get every fetched row via the `full_sample` flag,
since they aren't subject to that request-access workflow.
"""
from services.preview_service import PreviewService


def _sparql_results(n_rows):
    bindings = [{"patientId": {"value": f"P{i}"}, "age": {"value": str(20 + i)}} for i in range(n_rows)]
    return {"head": {"vars": ["patientId", "age"]}, "results": {"bindings": bindings}}


def _aggregate_results(n_rows):
    bindings = [{"count": {"value": str(i)}} for i in range(n_rows)]
    return {"head": {"vars": ["count"]}, "results": {"bindings": bindings}}


def test_compute_metadata_default_caps_sample_rows_at_five():
    metadata = PreviewService.compute_metadata(_sparql_results(20))
    assert len(metadata["sample_rows"]) == 5
    assert metadata["dataset_summary"]["row_count"] == 20


def test_compute_metadata_full_sample_returns_every_row():
    metadata = PreviewService.compute_metadata(_sparql_results(20), full_sample=True)
    assert len(metadata["sample_rows"]) == 20
    assert metadata["dataset_summary"]["row_count"] == 20


def test_compute_metadata_full_sample_with_fewer_than_five_rows():
    metadata = PreviewService.compute_metadata(_sparql_results(3), full_sample=True)
    assert len(metadata["sample_rows"]) == 3


def test_aggregate_metadata_default_caps_sample_rows_at_five():
    metadata = PreviewService._compute_aggregate_metadata(_aggregate_results(10))
    assert len(metadata["sample_rows"]) == 5


def test_aggregate_metadata_full_sample_returns_every_row():
    metadata = PreviewService._compute_aggregate_metadata(_aggregate_results(10), full_sample=True)
    assert len(metadata["sample_rows"]) == 10


def test_generate_preview_threads_full_sample_flag_through(monkeypatch):
    monkeypatch.setattr(
        PreviewService, "execute_sparql_query", staticmethod(lambda query, timeout: _sparql_results(20))
    )

    capped = PreviewService.generate_preview("SELECT * WHERE { ?s ?p ?o }", full_sample=False)
    full = PreviewService.generate_preview("SELECT * WHERE { ?s ?p ?o }", full_sample=True)

    assert len(capped["sample_rows"]) == 5
    assert len(full["sample_rows"]) == 20
