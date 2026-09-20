import threading
from datetime import date

import pytest
from test_service_api import enable_model

from jev_trader.jobs import JobManager
from jev_trader.models import AnalysisError


def finish(manager):
    manager.thread.join(timeout=10)
    assert not manager.thread.is_alive()


def test_full_scan_filters_only_foundation_and_evaluates_every_eligible_stock(engine):
    calls = enable_model(engine)
    manager = JobManager(engine)
    job = manager.start()
    finish(manager)
    result = manager.get(job["id"])
    assert result["status"] == "completed"
    assert (result["total"], result["completed"], result["skipped"]) == (3, 2, 1)
    assert len(calls) == 2
    assert engine.store.get(engine.breadth_key(date(2026, 9, 18)))["coverage"] == 1


def test_breadth_cache_is_scoped_to_universe(engine):
    original = engine.breadth_key(date(2026, 9, 18))
    engine.settings.markets = ["SZ"]
    assert engine.breadth_key(date(2026, 9, 18)) != original


def test_cross_manager_lock_and_pause_resume(engine, monkeypatch):
    calls = enable_model(engine)
    entered, release = threading.Event(), threading.Event()
    original = engine.provider.bars

    def blocking(*args):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args)

    monkeypatch.setattr(engine.provider, "bars", blocking)
    first = JobManager(engine)
    job = first.start(["000001.SZ", "600000.SH"])
    assert entered.wait(timeout=5)
    second = JobManager(engine)
    assert second.get(job["id"])["status"] == "running"
    assert second.is_running()
    with pytest.raises(AnalysisError) as exc:
        second.start()
    assert exc.value.code == "job_active"
    second.pause(job["id"])
    release.set()
    finish(first)
    assert second.get(job["id"])["status"] == "paused"
    assert calls == []
    second.resume(job["id"])
    finish(second)
    assert second.get(job["id"])["completed"] == 2
    assert len(calls) == 2


def test_changed_rules_and_dates_cannot_mix_with_scan(engine):
    enable_model(engine)
    manager = JobManager(engine)
    job = manager.start(["000001.SZ"])
    finish(manager)
    engine.settings.buy_threshold = .5
    with pytest.raises(AnalysisError) as exc:
        manager.resume(job["id"])
    assert exc.value.code == "job_config_changed"


def test_model_failure_pauses_and_retry_recovers(engine, monkeypatch):
    calls = enable_model(engine)
    real_evaluate = engine.client.evaluate

    def failure(*args):
        raise AnalysisError("model_auth", "无效测试密钥", "Invalid test key")

    monkeypatch.setattr(engine.client, "evaluate", failure)
    manager = JobManager(engine)
    job = manager.start(["000001.SZ", "600000.SH"])
    finish(manager)
    result = manager.get(job["id"])
    assert result["status"] == "paused" and result["failed"] == 1 and result["remaining"] == 1
    monkeypatch.setattr(engine.client, "evaluate", real_evaluate)
    manager.resume(job["id"], retry_failed=True)
    finish(manager)
    assert manager.get(job["id"])["completed"] == 2 and len(calls) == 2
