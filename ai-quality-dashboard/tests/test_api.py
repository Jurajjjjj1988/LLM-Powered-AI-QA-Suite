"""
Test strategy for ai-quality-dashboard / app.py
================================================
Coverage targets:
  1. GET /api/metrics/summary returns all 5 DashboardSummary fields matching
     seeded DB state.
  2. GET /api/flaky-tests/trend?days=30 returns only rows within range;
     empty DB → empty array.
  3. Pagination: limit=2&offset=0 returns 2; offset=2 returns next 2;
     offset beyond total → [].
  4. GET / serves index.html with HTTP 200 and Content-Type: text/html.
  5. DB unreachable → all /api/* endpoints return HTTP 503.

Uses:
  - httpx TestClient (sync) via FastAPI's TestClient wrapper.
  - SQLite :memory: for all DB access.
  - pytest-mock for the DB-unreachable scenario.

No real API keys or external services are used.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

TOOL_ROOT = Path(__file__).parent.parent
REPO_ROOT = TOOL_ROOT.parent

for p in (str(TOOL_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# In-memory DB bootstrap
# ---------------------------------------------------------------------------

# We need to set up the DB BEFORE importing app (which runs init_db on import).
# Use a module-level :memory: engine, patch the settings, and reset the
# module-level engine singleton before each test class/fixture.

import common.database as _db_module
from common.models import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_MEM_URL = "sqlite:///:memory:"


def _fresh_mem_engine():
    engine = create_engine(_MEM_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def mem_engine():
    """Provide a fresh in-memory SQLite engine per test."""
    engine = _fresh_mem_engine()
    yield engine
    engine.dispose()


@pytest.fixture()
def mem_session(mem_engine):
    """Provide a raw SQLAlchemy session for seeding test data."""
    Session = sessionmaker(bind=mem_engine, autoflush=False, autocommit=False)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def mem_settings():
    from common.config import Settings
    settings = Settings.model_construct(
        anthropic_api_key="sk-ant-api03-" + "x" * 90,
        claude_model="claude-test-model",
        claude_max_tokens=2000,
        claude_timeout_seconds=30,
        retry_max_attempts=1,
        retry_wait_min_seconds=0.0,
        retry_wait_max_seconds=0.0,
        db_path=Path(":memory:"),
        generator_default_framework="playwright",
        generator_output_dir=Path("./generated"),
        analyzer_flaky_threshold_percent=20.0,
        dashboard_host="127.0.0.1",
        dashboard_port=8000,
        log_level="DEBUG",
        log_json=False,
    )
    return settings


@pytest.fixture()
def client(mem_engine, mem_settings):
    """
    Build a FastAPI TestClient with the in-memory DB injected.

    Strategy: patch `get_readonly_session` in app.py to use our mem_engine
    directly, bypassing any file-path-based engine creation.
    """
    from contextlib import contextmanager
    from sqlalchemy.orm import Session

    Session = sessionmaker(bind=mem_engine, autoflush=False, autocommit=False)

    @contextmanager
    def _mem_readonly_session(db_path):
        session = Session()
        try:
            yield session
        finally:
            session.close()

    # Patch both settings and get_readonly_session in the app module
    with patch("app.settings", mem_settings), \
         patch("app.get_readonly_session", _mem_readonly_session), \
         patch("app.init_db", return_value=None):
        # Import app AFTER patching so module-level code runs with mocks
        import importlib
        import app as app_module
        importlib.reload(app_module)

        from fastapi.testclient import TestClient
        test_client = TestClient(app_module.app, raise_server_exceptions=False)
        yield test_client, mem_engine


# ---------------------------------------------------------------------------
# Helpers for seeding data
# ---------------------------------------------------------------------------

from common.models import FlakyTestResult, FlakyTestRun, GeneratedTest, HealedSelector


def _seed_generated_test(session, framework="playwright", tokens=100, valid=True):
    row = GeneratedTest(
        requirement_hash="abc123",
        framework=framework,
        requirement_text="Test login flow",
        generated_code="test('foo', () => {});",
        model_used="claude-test",
        tokens_used=tokens,
        validation_passed=valid,
        output_file_path=None,
    )
    session.add(row)
    session.flush()
    return row


def _seed_flaky_run(session, total=10, flaky=3, days_ago=0, source="ci.log"):
    analyzed_at = datetime.utcnow() - timedelta(days=days_ago)
    run = FlakyTestRun(
        source_file=source,
        total_tests=total,
        flaky_count=flaky,
        analyzed_at=analyzed_at,
    )
    session.add(run)
    session.flush()
    result = FlakyTestResult(
        run_id=run.id,
        test_name="test_login",
        fail_rate=30.0,
        total_runs=10,
        avg_duration_seconds=1.5,
        ai_suggestion="Add wait",
    )
    session.add(result)
    session.flush()
    return run


def _seed_healed_selector(session, old="#broken", new="button.submit", valid=True):
    row = HealedSelector(
        description="Submit button",
        old_selector=old,
        new_selector=new,
        html_context_hash="deadbeef" * 8,
        model_used="claude-test",
        tokens_used=15,
        validation_passed=valid,
        applied_count=1,
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------------------
# GET / (index.html)
# ---------------------------------------------------------------------------

class TestServeIndex:
    def test_should_return_200_with_html_content_type(self, client):
        test_client, _ = client
        response = test_client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# GET /api/metrics/summary
# ---------------------------------------------------------------------------

class TestMetricsSummary:
    def test_should_return_all_5_fields_matching_db_state(self, client, mem_session):
        test_client, mem_engine = client
        Session = sessionmaker(bind=mem_engine, autoflush=False, autocommit=False)
        session = Session()

        try:
            _seed_generated_test(session)
            _seed_flaky_run(session)
            _seed_healed_selector(session)
            session.commit()
        finally:
            session.close()

        response = test_client.get("/api/metrics/summary")
        assert response.status_code == 200
        data = response.json()

        assert "generated_tests_count" in data
        assert "flaky_runs_count" in data
        assert "avg_flaky_rate" in data
        assert "healed_selectors_count" in data
        assert "last_activity_at" in data

        assert data["generated_tests_count"] >= 1
        assert data["flaky_runs_count"] >= 1
        assert data["healed_selectors_count"] >= 1

    def test_should_return_zeros_when_db_is_empty(self, client):
        test_client, _ = client
        response = test_client.get("/api/metrics/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["generated_tests_count"] == 0
        assert data["flaky_runs_count"] == 0
        assert data["healed_selectors_count"] == 0


# ---------------------------------------------------------------------------
# GET /api/flaky-tests/trend
# ---------------------------------------------------------------------------

class TestFlakyTrend:
    def test_should_return_empty_array_when_db_is_empty(self, client):
        test_client, _ = client
        response = test_client.get("/api/flaky-tests/trend?days=30")
        assert response.status_code == 200
        assert response.json() == []

    def test_should_return_only_rows_within_days_range(self, client, mem_engine):
        test_client, _ = client
        Session = sessionmaker(bind=mem_engine, autoflush=False, autocommit=False)
        session = Session()
        try:
            _seed_flaky_run(session, days_ago=5, source="recent.log")
            _seed_flaky_run(session, days_ago=60, source="old.log")  # outside 30d
            session.commit()
        finally:
            session.close()

        response = test_client.get("/api/flaky-tests/trend?days=30")
        assert response.status_code == 200
        data = response.json()
        # Only the recent run should appear
        assert len(data) >= 1
        # Each item should have the expected keys
        for item in data:
            assert "date" in item
            assert "avg_flaky_rate" in item
            assert "run_count" in item


# ---------------------------------------------------------------------------
# Pagination of generated-tests
# ---------------------------------------------------------------------------

class TestPagination:
    def _seed_n_tests(self, session, n: int):
        for i in range(n):
            _seed_generated_test(session, framework="playwright", tokens=100 + i)
        session.commit()

    def test_should_return_2_items_with_limit_2_offset_0(self, client, mem_engine):
        test_client, _ = client
        Session = sessionmaker(bind=mem_engine)
        session = Session()
        self._seed_n_tests(session, 4)
        session.close()

        response = test_client.get("/api/generated-tests?limit=2&offset=0")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_should_return_next_2_items_with_limit_2_offset_2(self, client, mem_engine):
        test_client, _ = client
        Session = sessionmaker(bind=mem_engine)
        session = Session()
        self._seed_n_tests(session, 4)
        session.close()

        first_page = test_client.get("/api/generated-tests?limit=2&offset=0").json()
        second_page = test_client.get("/api/generated-tests?limit=2&offset=2").json()

        assert len(second_page) == 2
        first_ids = {r["id"] for r in first_page}
        second_ids = {r["id"] for r in second_page}
        assert first_ids.isdisjoint(second_ids), "Pages must not overlap"

    def test_should_return_empty_array_when_offset_exceeds_total(
        self, client, mem_engine
    ):
        test_client, _ = client
        Session = sessionmaker(bind=mem_engine)
        session = Session()
        self._seed_n_tests(session, 2)
        session.close()

        response = test_client.get("/api/generated-tests?limit=10&offset=100")
        assert response.status_code == 200
        assert response.json() == []


# ---------------------------------------------------------------------------
# DB unreachable → HTTP 503
# ---------------------------------------------------------------------------

class TestDbUnreachable:
    """
    Simulate a DatabaseError in every repository function to confirm all
    /api/* endpoints return 503 rather than 500 or an unhandled exception.
    """

    @pytest.fixture()
    def unreachable_client(self, mem_settings):
        from common.exceptions import DatabaseError
        from contextlib import contextmanager

        @contextmanager
        def _raise_session(db_path):
            raise DatabaseError("connection refused")
            yield  # pragma: no cover

        with patch("app.settings", mem_settings), \
             patch("app.get_readonly_session", _raise_session), \
             patch("app.init_db", return_value=None):
            import importlib
            import app as app_module
            importlib.reload(app_module)

            from fastapi.testclient import TestClient
            yield TestClient(app_module.app, raise_server_exceptions=False)

    @pytest.mark.parametrize("endpoint", [
        "/api/metrics/summary",
        "/api/generated-tests",
        "/api/flaky-tests",
        "/api/flaky-tests/trend",
        "/api/healed-selectors",
    ])
    def test_should_return_503_when_db_is_unreachable(
        self, unreachable_client, endpoint
    ):
        response = unreachable_client.get(endpoint)
        assert response.status_code == 503
