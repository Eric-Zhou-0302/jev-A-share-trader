import threading
from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_jobs import finish
from test_service_api import enable_model

from jev_trader.api import create_app
from jev_trader.jobs import JobManager
from jev_trader.models import AnalysisError, Stock, normalize_symbols


def test_symbols_normalize_deduplicate_and_keep_input_order():
    assert normalize_symbols("600000，sz000001\n600000.SH; BJ920001、000001.SZ") == ["600000.SH", "000001.SZ", "920001.BJ"]
    assert normalize_symbols(["000001,600000", "SH600000"]) == ["000001.SZ", "600000.SH"]
    assert len(normalize_symbols([f"600{i:03}" for i in range(50)] * 2)) == 50


@pytest.mark.parametrize("value,code", [(None, "empty_batch"), ([], "empty_batch"), (" ,；\n", "empty_batch"),
                                      ("000001 invalid", "invalid_symbol"), ("000001.SH", "invalid_symbol"),
                                      ([f"600{i:03}" for i in range(51)], "batch_too_large")])
def test_invalid_batches_do_not_create_jobs_or_call_providers(engine, monkeypatch, value, code):
    enable_model(engine)
    monkeypatch.setattr(engine.provider, "universe", lambda: pytest.fail("Invalid input must not request a universe"))
    manager = JobManager(engine)
    with pytest.raises(AnalysisError) as exc:
        manager.start(value)
    assert exc.value.code == code
    assert manager.list() == [] and manager.active is None and engine.provider.calls == 0


def test_first_result_is_saved_before_second_stock_download(engine, monkeypatch):
    calls = enable_model(engine)
    entered, release = threading.Event(), threading.Event()
    original = engine.provider.bars
    downloaded = []

    def bars(symbol, cutoff):
        downloaded.append(symbol)
        if symbol == "000001.SZ":
            entered.set()
            assert release.wait(timeout=10)
        return original(symbol, cutoff)

    monkeypatch.setattr(engine.provider, "bars", bars)
    manager = JobManager(engine)
    job = manager.start("600000, 000001, 600000.SH")
    try:
        assert entered.wait(timeout=5)
        current = manager.get(job["id"])
        assert current["completed"] == 1 and current["remaining"] == 1
        assert current["current_symbol"] == "000001.SZ"
        assert current["items"][0]["stock"]["symbol"] == "600000.SH"
        assert engine.store.analysis(current["items"][0]["analysis_id"])["status"] == "ready"
        assert len(calls) == 1
    finally:
        release.set()
    finish(manager)
    assert downloaded == ["600000.SH", "000001.SZ"]
    assert manager.get(job["id"])["current_symbol"] is None


def test_model_failure_does_not_prefetch_the_rest_of_the_batch(engine, monkeypatch):
    enable_model(engine)

    def fail(*args):
        raise AnalysisError("model_auth", "认证失败", "Authentication failed")

    monkeypatch.setattr(engine.client, "evaluate", fail)
    manager = JobManager(engine)
    job = manager.start(["000001", "600000"])
    finish(manager)
    result = manager.get(job["id"])
    assert result["status"] == "paused" and result["failed"] == 1 and result["remaining"] == 1
    assert engine.provider.calls == 1
    assert result["items"][1]["data_status"] == "pending"
    assert result["items"][0]["action"] is None


def test_repeated_data_failures_pause_and_retry_recovers(engine, monkeypatch):
    calls = enable_model(engine)
    stocks = [Stock(symbol=f"60000{i}.SH", name=f"测试{i}", market="SH") for i in range(4)]
    monkeypatch.setattr(engine.provider, "universe", lambda: stocks)
    original = engine.provider.bars
    downloads = []

    def failure(symbol, cutoff):
        downloads.append(symbol)
        raise AnalysisError("invalid_data", "行情无效", "Invalid data")

    monkeypatch.setattr(engine.provider, "bars", failure)
    manager = JobManager(engine)
    job = manager.start([stock.symbol for stock in stocks])
    finish(manager)
    result = manager.get(job["id"])
    assert (result["status"], result["failed"], result["remaining"]) == ("paused", 3, 1)
    assert result["error"]["code"] == "consecutive_data_failures"
    assert len(downloads) == 3 and calls == []
    monkeypatch.setattr(engine.provider, "bars", original)
    manager.resume(job["id"], retry_failed=True)
    finish(manager)
    assert manager.get(job["id"])["completed"] == 4 and len(calls) == 4


def test_unknown_stock_does_not_block_known_stocks_and_retry_rechecks_membership(engine, monkeypatch):
    calls = enable_model(engine)
    manager = JobManager(engine)
    job = manager.start(["600099", "000001"])
    finish(manager)
    result = manager.get(job["id"])
    assert (result["failed"], result["completed"]) == (1, 1)
    assert result["items"][0]["error"]["code"] == "unknown_stock"
    assert len(calls) == 1
    manager.resume(job["id"], retry_failed=True)
    finish(manager)
    assert manager.get(job["id"])["failed"] == 1 and len(calls) == 1
    stocks = engine.provider.universe() + [Stock(symbol="600099.SH", name="新股票", market="SH")]
    monkeypatch.setattr(engine.provider, "universe", lambda: stocks)
    manager.resume(job["id"], retry_failed=True)
    finish(manager)
    assert manager.get(job["id"])["completed"] == 2 and len(calls) == 2


def test_batch_api_validation_watchlist_snapshot_and_history(engine):
    enable_model(engine)
    app = create_app(engine.directory, engine)
    with TestClient(app) as client:
        for body in ({"scope": "market"}, {"scope": "batch"}, {"symbols": "bad"}, {"symbols": [f"600{i:03}" for i in range(51)]}, {"scope": "watchlist", "symbols": ["000001"]}):
            assert client.post("/api/jobs", json=body).status_code == 422
        assert engine.store.jobs() == []
        response = client.post("/api/jobs", json={"symbols": "600000\n000001，600000.SH"})
        assert response.status_code == 200
        finish(app.state.jobs)
        saved = client.get(f"/api/jobs/{response.json()['id']}").json()
        assert saved["scope"] == "batch" and saved["total"] == saved["completed"] == 2
        assert client.get("/api/jobs/search?scope=batch").json()["total"] == 1
        assert client.post("/api/jobs", json={"scope": "watchlist"}).json()["code"] == "empty_watchlist"
        engine.store.watch("000001.SZ", "测试股票")
        response = client.post("/api/jobs", json={"scope": "watchlist"})
        finish(app.state.jobs)
        engine.store.watch("600000.SH", "测试股票二")
        saved = client.get(f"/api/jobs/{response.json()['id']}").json()
        assert saved["scope"] == "watchlist" and saved["total"] == 1


def test_legacy_market_history_is_readable_but_cannot_resume(engine):
    calls = enable_model(engine)
    manager = JobManager(engine)
    original = {"id": "legacy-market", "created": 1, "scope": "market", "status": "paused", "symbols": None, "items": []}
    engine.store.save_job(original)
    for retry in (False, True):
        with pytest.raises(AnalysisError) as exc:
            manager.resume(original["id"], retry_failed=retry)
        assert exc.value.code == "market_scan_removed"
    assert manager.get(original["id"])["status"] == "paused"
    assert engine.store.job(original["id"]) == original and calls == []


def test_batch_resume_cannot_mix_trading_dates(engine):
    enable_model(engine)
    manager = JobManager(engine)
    job = manager.start(["000001"])
    finish(manager)
    engine.context = lambda: (engine.provider.sessions, date(2026, 9, 21))
    manager.resume(job["id"])
    finish(manager)
    assert manager.get(job["id"])["error"]["code"] == "job_expired"


def test_cli_batch_uses_the_same_input_contract(engine, monkeypatch, capsys):
    from jev_trader.cli import main

    calls = enable_model(engine)
    monkeypatch.setattr("jev_trader.cli.Engine", lambda directory: engine)
    monkeypatch.setattr("sys.argv", ["jev", "--data-dir", str(engine.directory), "scan", "--symbols", "600000,000001", "600000.SH"])
    main()
    saved = engine.store.jobs()[0]
    assert saved["scope"] == "batch" and saved["symbols"] == ["600000.SH", "000001.SZ"]
    assert saved["status"] == "completed" and len(calls) == 2
    assert "已完成" in capsys.readouterr().out
