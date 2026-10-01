"""The server enforces retention itself (legal review M4): before 2026-09-26 the purge ran only
when someone remembered the CLI. Startup purges; `QORGAN_REPORT_PURGE_INTERVAL_HOURS=0` hands
the job to cron."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from qorgan.api import app
from qorgan.reports.store import REPORTS_FILENAME, append_report, load_reports
from support.numbers import stored_report


@pytest.fixture()
def reports(tmp_path, monkeypatch):
    monkeypatch.setenv("QORGAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("QORGAN_REPORT_RETENTION_DAYS", "180")
    path = tmp_path / "processed" / REPORTS_FILENAME
    now = datetime.now(UTC)
    expired = stored_report(number=None, timestamp=now - timedelta(days=200))
    fresh = stored_report(number=None, timestamp=now - timedelta(days=2))
    append_report(expired, path)
    append_report(fresh, path)
    return path, expired, fresh


def test_server_startup_purges_reports_past_retention(reports, monkeypatch):
    path, _, fresh = reports
    monkeypatch.setenv("QORGAN_REPORT_PURGE_INTERVAL_HOURS", "24")
    with TestClient(app):
        assert load_reports(path) == [fresh]


def test_interval_zero_leaves_retention_to_cron(reports, monkeypatch):
    path, expired, fresh = reports
    monkeypatch.setenv("QORGAN_REPORT_PURGE_INTERVAL_HOURS", "0")
    with TestClient(app):
        assert load_reports(path) == [expired, fresh]


def test_the_purge_run_is_logged_at_info(reports, monkeypatch, caplog):
    import logging

    monkeypatch.setenv("QORGAN_REPORT_PURGE_INTERVAL_HOURS", "24")
    with caplog.at_level(logging.INFO, logger="qorgan"), TestClient(app):
        pass
    assert any("past retention forgotten" in r.getMessage() for r in caplog.records)


def test_server_logging_gets_one_handler_only_when_the_host_configured_none(monkeypatch):
    # Under uvicorn nothing handles `qorgan.*` records, so INFO lines (a purge run) vanished.
    import logging

    from qorgan.api import _configure_logging

    root, logger = logging.getLogger(), logging.getLogger("qorgan")
    monkeypatch.setattr(root, "handlers", [])
    monkeypatch.setattr(logger, "handlers", [])
    _configure_logging("INFO")
    _configure_logging("INFO")
    assert len(logger.handlers) == 1 and logger.level == logging.INFO

    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(root, "handlers", [logging.NullHandler()])  # the host already logs
    _configure_logging("INFO")
    assert logger.handlers == []
