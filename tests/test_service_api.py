import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_jev import response_for

from jev_trader.api import create_app
from jev_trader.export import export_analysis
from jev_trader.jev import JevClient
from jev_trader.models import AnalysisError


def enable_model(engine):
    calls = []
    engine.settings.jev_api_key = SecretStr("test-only-secret")

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json=response_for(body["questions"]))

    engine.client = JevClient(engine.settings, httpx.MockTransport(handler))
    return calls


def test_missing_key_preserves_real_technical_state(engine):
    result = engine.analyze("000001")
    assert result.status == "needs_key" and result.action is None and result.horizon is None
    assert len(result.metrics) >= 85 and result.evidence and result.bars
    assert any(notice["code"] == "benchmark_missing" for notice in result.notices)
    assert all(item.side == "context" for item in result.evidence)


def test_client_initialization_failure_returns_technical_analysis(engine, monkeypatch):
    engine.settings.jev_api_key = SecretStr("test-only")
    with TestClient(create_app(engine.directory, engine)) as client:
        def broken_client(**kwargs):
            raise ImportError("Missing SOCKS dependency")

        monkeypatch.setattr(httpx, "Client", broken_client)
        response = client.post("/api/analyze", json={"symbol": "000001"})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "model_configuration" and result["action"] is None
    assert result["horizon"] is None and result["metrics"] and result["bars"]
    assert result["notices"][-1]["code"] == "model_configuration"


def test_ready_cache_and_configuration_change(engine):
    calls = enable_model(engine)
    first = engine.analyze("000001")
    second = engine.analyze("000001")
    assert first.status == "ready" and first.action == "buy"
    assert len(calls) == 1 and second.cached
    technical = engine.analyze("000001", technical_only=True)
    assert technical.action is None and technical.id != first.id
    assert engine.store.analysis(first.id)["status"] == "ready"
    engine.settings.buy_threshold = .8
    third = engine.analyze("000001")
    assert len(calls) == 2 and third.action == "hold"
    assert "symbol" not in calls[0]["state"]


@pytest.mark.parametrize("case,code", [("stale", "stale_or_suspended"), ("history", "insufficient_history"), ("suspended", "suspended")])
def test_invalid_input_never_reaches_model(engine, case, code):
    calls = enable_model(engine)
    if case == "stale":
        engine.provider.frame = engine.provider.frame.iloc[:-1]
    elif case == "history":
        engine.provider.frame = engine.provider.frame.tail(20)
    else:
        engine.provider.frame.loc[519, "volume"] = 0
    with pytest.raises(AnalysisError) as exc:
        engine.analyze("000001")
    assert exc.value.code == code and calls == []


def test_api_shared_history_watchlist_and_credentials(engine):
    enable_model(engine)
    with TestClient(create_app(engine.directory, engine)) as client:
        settings = client.get("/api/settings").json()
        assert settings["jev_configured"] and "jev_api_key" not in settings
        assert client.post("/api/watchlist", json={"symbol": "000001"}).json()[0]["symbol"] == "000001.SZ"
        response = client.post("/api/analyze", json={"symbol": "000001"})
        assert response.status_code == 200, response.text
        analysis = response.json()
        assert analysis["status"] == "ready"
        history = client.get("/api/analyses").json()
        assert history[0]["id"] == analysis["id"] and "bars" not in history[0]
        english = client.get(f"/api/analyses/{analysis['id']}/export?format=json&lang=en").json()
        assert english["action"] == "Buy"
        assert not {"entry_price", "target_price", "stop_loss", "api_key"} & set(english)
        assert "test-only-secret" not in json.dumps(english)
        assert client.delete("/api/watchlist/000001").json() == []


def test_local_write_guard_and_error_localization(engine):
    with TestClient(create_app(engine.directory, engine)) as client:
        assert client.post("/api/analyze", json={"symbol": "000001"}, headers={"Origin": "https://example.com"}).status_code == 403
        assert client.post("/api/analyze", content="symbol=000001", headers={"Content-Type": "application/x-www-form-urlencoded"}).status_code == 415
        assert client.get("/api/health", headers={"Host": "attacker.example"}).status_code == 400
        error = client.post("/api/analyze?lang=en", json={"symbol": "invalid"})
        assert error.status_code == 422 and "six-digit" in error.json()["message"]
        assert client.post("/api/jobs", json={"scope": "market"}).json()["code"] == "needs_key"


def test_export_escaping_and_bilingual_evidence(engine):
    result = engine.analyze("000001", technical_only=True)
    result.name = "<script>alert(1)</script>"
    html = export_analysis(result, "html", "en")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "No decision" in html and "MA20" in html
    result.name = "=1+1"
    assert "'=1+1" in export_analysis(result, "csv", "zh")
    chinese = json.loads(export_analysis(result, "json", "zh"))
    assert chinese["action"] == "未形成判断"


def test_provider_switch_is_immediate_and_preserves_keys(engine, monkeypatch):
    from jev_trader.config import load_settings
    from jev_trader.providers.akshare import AKShareProvider
    from jev_trader.providers.tushare import TushareProvider

    engine.settings.jev_api_key = SecretStr("jev-test-only")
    closed = []
    monkeypatch.setattr(engine.provider, "close", lambda: closed.append(True))
    with TestClient(create_app(engine.directory, engine)) as client:
        response = client.put("/api/settings", json={"provider": "tushare", "tushare_token": "tushare-test-only"})
        assert response.status_code == 200 and response.json()["tushare_configured"]
        assert "tushare-test-only" not in response.text and "jev-test-only" not in response.text
        assert isinstance(engine.provider, TushareProvider) and closed == [True]
        assert engine.settings.jev_api_key.get_secret_value() == "jev-test-only"
        assert client.get("/api/health").json()["provider"] == "tushare"
        assert client.put("/api/settings", json={"provider": "akshare", "tushare_token": ""}).status_code == 200
        assert isinstance(engine.provider, AKShareProvider)
        assert load_settings(engine.directory).tushare_token.get_secret_value() == "tushare-test-only"
        assert client.put("/api/settings", json={"provider": "tushare"}).status_code == 200
        assert isinstance(engine.provider, TushareProvider)


def test_invalid_provider_settings_leave_current_provider_unchanged(engine):
    previous = engine.provider
    with TestClient(create_app(engine.directory, engine)) as client:
        missing = client.put("/api/settings?lang=en", json={"provider": "tushare"})
        assert missing.status_code == 422 and missing.json()["code"] == "needs_tushare_token"
        assert engine.settings.provider == "akshare" and engine.provider is previous
        invalid = client.put("/api/settings", json={"provider": "unsupported", "tushare_token": "private-test-value"})
        assert invalid.status_code == 422 and "private-test-value" not in invalid.text
        oversize = client.put("/api/settings", json={"tushare_token": "private-test-value" * 100})
        assert oversize.status_code == 422 and "private-test-value" not in oversize.text


def test_provider_switch_blocked_during_scan(engine, monkeypatch):
    app = create_app(engine.directory, engine)
    monkeypatch.setattr(app.state.jobs, "is_running", lambda: True)
    with TestClient(app) as client:
        response = client.put("/api/settings", json={"provider": "tushare", "tushare_token": "test-only"})
        assert response.json()["code"] == "job_active"
        assert engine.settings.provider == "akshare"


def test_switch_save_failure_keeps_existing_provider(engine, monkeypatch):
    replacement = type("Replacement", (), {"close": lambda self: setattr(self, "closed", True)})()
    monkeypatch.setattr("jev_trader.api.create_provider", lambda *args: replacement)
    def fail_save(*args):
        raise OSError("disk failure")
    monkeypatch.setattr("jev_trader.api.save_settings", fail_save)
    old = engine.provider
    with TestClient(create_app(engine.directory, engine), raise_server_exceptions=False) as client:
        assert client.put("/api/settings", json={"provider": "tushare", "tushare_token": "test-only"}).status_code == 500
    assert engine.provider is old and engine.settings.provider == "akshare" and replacement.closed
