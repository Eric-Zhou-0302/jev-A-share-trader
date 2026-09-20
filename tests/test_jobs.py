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


def test_pause_during_preparation_stops_before_fetching_universe(engine, monkeypatch):
    calls = enable_model(engine)
    entered, release = threading.Event(), threading.Event()
    original_context = engine.context
    universes = []
    original_universe = engine.provider.universe

    def context():
        entered.set()
        assert release.wait(timeout=10)
        return original_context()

    def universe():
        universes.append(True)
        return original_universe()

    monkeypatch.setattr(engine, "context", context)
    monkeypatch.setattr(engine.provider, "universe", universe)
    manager = JobManager(engine)
    job = manager.start(["000001.SZ"])
    try:
        assert entered.wait(timeout=5)
        assert manager.pause(job["id"])["status"] == "pausing"
    finally:
        release.set()
    finish(manager)
    paused = manager.get(job["id"])
    assert paused["status"] == "paused" and paused["total"] == 0
    assert universes == calls == []
    manager.resume(job["id"])
    finish(manager)
    assert manager.get(job["id"])["completed"] == 1 and len(calls) == 1


@pytest.mark.parametrize("symbols", [["000001.SZ"], ["000001.SZ", "600000.SH"]])
def test_pause_during_model_call_finishes_only_current_stock(engine, monkeypatch, symbols):
    calls = enable_model(engine)
    entered, release = threading.Event(), threading.Event()
    original = engine.client.evaluate

    def evaluate(*args):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args)

    monkeypatch.setattr(engine.client, "evaluate", evaluate)
    first = JobManager(engine)
    job = first.start(symbols)
    second = JobManager(engine)
    try:
        assert entered.wait(timeout=5)
        assert second.pause(job["id"])["status"] == "pausing"
    finally:
        release.set()
    finish(first)
    paused = second.get(job["id"])
    assert paused["status"] == "paused"
    assert paused["completed"] == 1 and paused["remaining"] == len(symbols) - 1
    assert len(calls) == 1
    first_analysis = paused["items"][0]["analysis_id"]
    second.resume(job["id"])
    finish(second)
    completed = second.get(job["id"])
    assert completed["status"] == "completed" and completed["completed"] == len(symbols)
    assert completed["items"][0]["analysis_id"] == first_analysis
    assert len(calls) == len(symbols)


@pytest.mark.parametrize("stage", ["preparing", "data", "analysis"])
def test_stop_running_job_across_managers_stops_after_current_stock(engine, monkeypatch, stage):
    calls = enable_model(engine)
    entered, release = threading.Event(), threading.Event()
    target, method = {"preparing": (engine, "context"), "data": (engine.provider, "bars"), "analysis": (engine.client, "evaluate")}[stage]
    original = getattr(target, method)

    def blocking(*args):
        entered.set()
        assert release.wait(timeout=10)
        return original(*args)

    monkeypatch.setattr(target, method, blocking)
    first = JobManager(engine)
    job = first.start(["000001.SZ", "600000.SH"])
    second = JobManager(engine)
    try:
        assert entered.wait(timeout=5)
        assert second.stop(job["id"])["status"] == "stopping"
        assert second.is_running()
        with pytest.raises(AnalysisError) as exc:
            second.start()
        assert exc.value.code == "job_active"
    finally:
        release.set()
    finish(first)
    result = second.get(job["id"])
    assert result["status"] == "stopped" and not second.is_running()
    assert result["completed"] == (1 if stage == "analysis" else 0)
    assert len(calls) == (1 if stage == "analysis" else 0)
    if stage == "preparing":
        assert result["total"] == 0 and engine.provider.calls == 0
    elif stage == "data":
        assert result["downloaded"] == 1 and engine.provider.calls == 1
    else:
        analysis_id = result["items"][0]["analysis_id"]
        assert engine.store.analysis(analysis_id)["status"] == "ready"
    for retry in (False, True):
        with pytest.raises(AnalysisError) as exc:
            second.resume(job["id"], retry_failed=retry)
        assert exc.value.code == "job_stopped"
    fresh = second.start(["600000.SH"])
    finish(second)
    assert fresh["id"] != job["id"] and second.get(fresh["id"])["completed"] == 1
    assert second.get(job["id"])["items"] == result["items"]


def test_stop_completed_job_is_a_noop_and_preserves_history_and_cache(engine):
    calls = enable_model(engine)
    manager = JobManager(engine)
    job = manager.start(["000001.SZ"])
    finish(manager)
    before = manager.get(job["id"])
    engine.store.put("test-cache-preserved", {"value": 1})
    assert manager.stop(job["id"]) == {key: value for key, value in before.items() if key != "items"}
    assert not engine.store.get(f"stop:{job['id']}")
    restarted = JobManager(engine)
    after = restarted.get(job["id"])
    assert after == before
    assert engine.store.get("test-cache-preserved") == {"value": 1}
    assert engine.store.analysis(after["items"][0]["analysis_id"])["status"] == "ready"
    fresh = restarted.start(["000001.SZ"])
    finish(restarted)
    assert restarted.get(fresh["id"])["completed"] == 1 and len(calls) == 1


@pytest.mark.parametrize("flag", ["stop", "reset"])
def test_stop_pending_at_process_exit_is_recovered_as_stopped(engine, flag):
    enable_model(engine)
    manager = JobManager(engine)
    job = manager.start(["000001.SZ"])
    finish(manager)
    stored = engine.store.job(job["id"])
    stored["status"] = "running"
    engine.store.save_job(stored)
    engine.store.put(f"{flag}:{job['id']}", True)
    restarted = JobManager(engine)
    assert restarted.get(job["id"])["status"] == "stopped"
    assert not restarted.is_running()


@pytest.mark.parametrize("operation", ["stop", "reset"])
def test_stop_route_preserves_paused_job_and_blocks_resume(engine, operation):
    from fastapi.testclient import TestClient

    from jev_trader.api import create_app

    enable_model(engine)
    app = create_app(engine.directory, engine)
    with TestClient(app) as client:
        job = app.state.jobs.start(["000001.SZ"])
        finish(app.state.jobs)
        saved = engine.store.job(job["id"])
        saved["status"] = "paused"
        engine.store.save_job(saved)
        engine.store.put(f"pause:{job['id']}", True)
        response = client.post(f"/api/jobs/{job['id']}/{operation}", json={})
        assert response.status_code == 200 and response.json()["status"] == "stopped"
        detail = client.get(f"/api/jobs/{job['id']}").json()
        assert detail["completed"] == 1 and detail["items"][0]["analysis_id"]
        assert client.get("/api/jobs").json()[0]["status"] == "stopped"
        assert client.post(f"/api/jobs/{job['id']}/resume", json={}).json()["code"] == "job_stopped"
        assert client.post(f"/api/jobs/{job['id']}/retry", json={}).json()["code"] == "job_stopped"
        assert client.post(f"/api/jobs/{job['id']}/stop", json={}).json()["status"] == "stopped"
        assert client.post("/api/jobs/missing/stop", json={}).json()["code"] == "job_missing"


@pytest.mark.parametrize("status", ["reset", "stopped"])
def test_stopped_history_without_control_flag_remains_terminal(engine, status):
    manager = JobManager(engine)
    engine.store.save_job({"id": "old-stopped", "created": 1, "status": status, "scope": "market", "items": []})
    assert manager.get("old-stopped")["status"] == "stopped"
    assert manager.search(status="stopped")["total"] == 1
    assert manager.search(status="reset")["items"][0]["status"] == "stopped"
    assert manager.stop("old-stopped")["status"] == "stopped"
    with pytest.raises(AnalysisError) as exc:
        manager.resume("old-stopped")
    assert exc.value.code == "job_stopped"
