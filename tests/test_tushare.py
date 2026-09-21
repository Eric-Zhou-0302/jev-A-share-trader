import json
from datetime import date

import httpx
import numpy as np
import pandas as pd
import pytest
from pydantic import SecretStr

from jev_trader.config import Settings, load_settings, public_settings, save_settings
from jev_trader.models import AnalysisError, Stock
from jev_trader.providers import create_provider
from jev_trader.providers.tushare import TushareProvider, normalize_daily
from jev_trader.storage import Store


@pytest.fixture
def provider(tmp_path):
    provider = TushareProvider(Settings(provider="tushare", tushare_token=SecretStr("test-only")), Store(tmp_path))
    yield provider
    provider.close()


def raw_bars(bars):
    frame = bars.rename(columns={"volume": "vol", "turnover": "turnover_rate"}).copy()
    frame["ts_code"] = "000001.SZ"
    frame["trade_date"] = frame.date.str.replace("-", "")
    frame["vol"] /= 100
    frame["amount"] /= 1000
    return frame


def test_qfq_anchor_cutoff_and_units(bars):
    raw = raw_bars(bars.tail(3))
    factors = raw[["trade_date"]].assign(adj_factor=[1, 2, 4])
    # 即使上游夹带未来日期，也不能把未来复权因子用作当前价格基准。
    cutoff = date(2026, 9, 17)
    result = normalize_daily(raw, factors, raw, cutoff)
    assert result.date.tolist() == ["2026-09-16", "2026-09-17"]
    assert result.close.iloc[0] == pytest.approx(raw.close.iloc[0] / 2)
    assert result.close.iloc[-1] == raw.close.iloc[1]
    assert result.volume.iloc[0] == bars.volume.iloc[-3]
    assert result.amount.iloc[0] == bars.amount.iloc[-3]
    assert result.turnover.iloc[0] == 1.2


@pytest.mark.parametrize("bad", ["missing", "zero", "nan", "duplicate"])
def test_bad_adjustment_fails_closed(bars, bad):
    raw = raw_bars(bars.tail(3))
    factors = raw[["trade_date"]].assign(adj_factor=1.0).reset_index(drop=True)
    if bad == "missing":
        factors = factors.iloc[1:]
    elif bad == "duplicate":
        factors = pd.concat([factors, factors.tail(1)])
    else:
        factors.loc[0, "adj_factor"] = 0 if bad == "zero" else np.nan
    with pytest.raises(AnalysisError):
        normalize_daily(raw, factors, raw, date(2026, 9, 18))


def test_missing_token_makes_no_request(tmp_path):
    provider = create_provider(Settings(provider="tushare"), Store(tmp_path))
    with pytest.raises(AnalysisError) as exc:
        provider.universe()
    assert exc.value.code == "needs_tushare_token" and provider.client is None


def test_http_contract_and_no_redirects(provider):
    def handler(request):
        assert str(request.url) == "https://api.tushare.pro"
        assert json.loads(request.content) == {"api_name": "daily", "token": "test-only", "fields": "trade_date,close", "params": {"ts_code": "000001.SZ"}}
        return httpx.Response(200, json={"code": 0, "data": {"fields": ["trade_date", "close"], "items": [["20260918", 10]]}})
    provider.transport = httpx.MockTransport(handler)
    assert provider._query("daily", "trade_date,close", ts_code="000001.SZ").close.iloc[0] == 10


@pytest.mark.parametrize("code,message,expected", [(40101, "test-only", "tushare_auth"), (2002, "无权限 test-only", "tushare_permission"), (-2001, "每分钟最多访问 test-only", "tushare_rate_limit")])
def test_api_errors_are_specific_and_redacted(provider, code, message, expected):
    provider.transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"code": code, "msg": message}))
    with pytest.raises(AnalysisError) as exc:
        provider._query("daily", "close")
    assert exc.value.code == expected
    assert "test-only" not in exc.value.zh + exc.value.en


@pytest.mark.parametrize("payload", [{"code": 0, "data": {"fields": ["close"], "items": [[1, 2]]}}, {"code": 0, "data": None}, {"code": 0, "data": {"fields": ["wrong"], "items": []}}])
def test_invalid_response_is_not_silently_accepted(provider, payload):
    provider.transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(AnalysisError) as exc:
        provider._query("daily", "close")
    assert exc.value.code == "invalid_data"


def test_transient_failure_retries_without_exposing_secret(provider, monkeypatch):
    monkeypatch.setattr("jev_trader.providers.tushare.time.sleep", lambda _: None)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"code": 0, "data": {"fields": ["close"], "items": [[12]]}})
    provider.transport = httpx.MockTransport(handler)
    assert provider._query("daily", "close").close.iloc[0] == 12
    assert len(calls) == 3


def test_initialization_error_is_redacted(provider, monkeypatch):
    def broken(**kwargs):
        raise ValueError("proxy contains test-only")
    monkeypatch.setattr(httpx, "Client", broken)
    with pytest.raises(AnalysisError) as exc:
        provider._query("daily", "close")
    assert exc.value.code == "data_configuration" and "test-only" not in str(exc.value)


def test_history_windows_and_wrong_symbol(provider, monkeypatch):
    calls = []
    def query(api, fields, **params):
        calls.append(params)
        return pd.DataFrame({"trade_date": [params["start_date"]], "ts_code": [params["ts_code"]]})
    monkeypatch.setattr(provider, "_query", query)
    provider._history("daily", "trade_date,ts_code", date(2016, 1, 1), date(2026, 9, 18), ts_code="000001.SZ")
    assert len(calls) == 4
    for previous, current in zip(calls, calls[1:]):
        assert (pd.Timestamp(current["start_date"]) - pd.Timestamp(previous["end_date"])).days == 1
    monkeypatch.setattr(provider, "_query", lambda *args, **kwargs: pd.DataFrame({"trade_date": ["20260918"], "ts_code": ["600000.SH"]}))
    with pytest.raises(AnalysisError):
        provider._history("daily", "trade_date,ts_code", date(2026, 9, 18), date(2026, 9, 18), ts_code="000001.SZ")


def test_daily_basic_failure_preserves_bars_and_recovers(provider, bars, monkeypatch):
    raw = raw_bars(bars)
    blocked = [True]
    def history(api, *args, **kwargs):
        if api == "adj_factor":
            return raw[["trade_date"]].assign(adj_factor=1)
        if api == "daily_basic" and blocked[0]:
            raise AnalysisError("tushare_permission", "daily_basic 权限不足", "daily_basic access denied")
        return raw
    monkeypatch.setattr(provider, "_history", history)
    first, source = provider.bars("000001.SZ", date(2026, 9, 18))
    assert first.turnover.isna().all() and first.attrs["notices"][0]["code"] == "tushare_permission"
    assert source.startswith("Tushare")
    blocked[0] = False
    recovered, _ = provider.bars("000001.SZ", date(2026, 9, 18))
    assert recovered.turnover.notna().all() and recovered.attrs["notices"] == []
    monkeypatch.setattr(provider, "_history", lambda *a, **kw: pytest.fail("expected isolated Tushare cache"))
    assert len(provider.bars("000001.SZ", date(2026, 9, 18))[0]) == len(bars)


@pytest.mark.parametrize("api,symbol,multiplier", [("index_daily", "000300.SH", 100), ("sw_daily", "801050.SI", 10000)])
def test_index_units(provider, bars, monkeypatch, api, symbol, multiplier):
    raw = raw_bars(bars).assign(vol=2, amount=3, ts_code=symbol)
    monkeypatch.setattr(provider, "_history", lambda *a, **kw: raw)
    frame = provider._index(api, symbol, date(2026, 9, 18))
    assert frame.volume.iloc[-1] == 2 * multiplier
    assert frame.amount.iloc[-1] == 3 * (1000 if api == "index_daily" else 10000)


def test_industry_uses_matching_sw_classification(provider, monkeypatch):
    calls = []
    def query(api, fields, **params):
        calls.append((api, params))
        return pd.DataFrame({"ts_code": ["000001.SZ"], "l1_code": ["801780.SI"], "l1_name": ["银行"], "in_date": ["20210101"]})
    monkeypatch.setattr(provider, "_query", query)
    stock = provider.metadata(Stock(symbol="000001.SZ", name="平安银行", market="SZ", industry="different classification"))
    assert stock.industry == "801780.SI" and calls[0][0] == "index_member_all"
    with pytest.raises(AnalysisError):
        provider.industry("银行", date(2026, 9, 18))


def test_universe_exchange_coverage_and_cache(provider, monkeypatch):
    calls = []
    def query(api, fields, **params):
        calls.append(params["exchange"])
        symbol, name, market = {"SSE": ("688001.SH", "公司一", "科创板"), "SZSE": ("000001.SZ", "ST公司", "主板"), "BSE": ("920001.BJ", "公司三", "北交所")}[params["exchange"]]
        return pd.DataFrame([dict(ts_code=symbol, name=name, market=market, list_date="20200101")])
    monkeypatch.setattr(provider, "_query", query)
    stocks = provider.universe()
    assert [s.market for s in stocks] == ["SH", "SZ", "BJ"]
    assert stocks[0].board == "star" and stocks[1].special
    assert stocks[1].industry is None
    assert provider.universe() == stocks and len(calls) == 3


def test_calendar_holidays_and_open_flags(provider, monkeypatch):
    monkeypatch.setattr(provider, "_history", lambda *a, **kw: pd.DataFrame({"cal_date": ["20260918", "20260919", "20260921"], "is_open": [1, 0, 1]}))
    assert provider.calendar() == [date(2026, 9, 18), date(2026, 9, 21)]


def test_environment_and_saved_credentials_are_private(tmp_path, monkeypatch):
    settings = Settings(tushare_token=SecretStr("file-secret"))
    save_settings(tmp_path, settings)
    assert (tmp_path / "settings.json").stat().st_mode & 0o777 == 0o600
    assert load_settings(tmp_path).tushare_token.get_secret_value() == "file-secret"
    monkeypatch.setenv("TUSHARE_TOKEN", "environment-secret")
    loaded = load_settings(tmp_path)
    assert loaded.tushare_token.get_secret_value() == "environment-secret"
    public = public_settings(loaded)
    assert public["tushare_configured"] and "tushare_token" not in public
    assert "environment-secret" not in json.dumps(public)


def test_tushare_end_to_end_through_engine(engine, bars, monkeypatch):
    from test_service_api import enable_model
    monkeypatch.setattr("jev_trader.providers.tushare.time.sleep", lambda _: None)
    engine.settings.provider = "tushare"
    engine.settings.tushare_token = SecretStr("test-only")
    raw = raw_bars(bars).assign(adj_factor=1)
    endpoints = []
    def handler(request):
        body = json.loads(request.content)
        api, params, fields = body["api_name"], body["params"], body["fields"].split(",")
        endpoints.append(api)
        if api == "stock_basic":
            table = pd.DataFrame([{"ts_code": "000001.SZ", "name": "测试股票", "market": "主板", "list_date": "19900101"}] if params["exchange"] == "SZSE" else [], columns=fields)
        elif api == "index_member_all":
            table = pd.DataFrame([{"ts_code": "000001.SZ", "l1_code": "801780.SI", "l1_name": "银行", "in_date": "20210101"}])
        else:
            table = raw.loc[raw.trade_date.between(params["start_date"], params["end_date"])].assign(ts_code=params["ts_code"])
        return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": table[fields].values.tolist()}})
    engine.provider = TushareProvider(engine.settings, engine.store, httpx.MockTransport(handler))
    model_calls = enable_model(engine)
    result = engine.analyze("000001")
    engine.close()
    assert result.status == "ready" and result.source.startswith("Tushare")
    assert result.rows == 520 and "relative" in result.groups_available
    assert {"daily", "adj_factor", "daily_basic", "index_daily", "index_member_all", "sw_daily"}.issubset(endpoints)
    assert result.notices == [{"code": "breadth_missing", "zh": "缺少同日全市场宽度数据；本次未使用，也不会用股票列表估算。", "en": "Same-day market breadth is unavailable and is not used or estimated from the stock list."}]
    assert "test-only" not in json.dumps(result.model_dump()) + json.dumps(model_calls)


def test_cli_provider_configuration_uses_hidden_token(tmp_path, monkeypatch, capsys):
    import sys

    from jev_trader.cli import main
    monkeypatch.setattr(sys, "argv", ["jev", "--data-dir", str(tmp_path), "configure", "--provider", "tushare"])
    monkeypatch.setattr("getpass.getpass", lambda _: "cli-test-secret")
    main()
    public = json.loads(capsys.readouterr().out)
    assert public["provider"] == "tushare" and public["tushare_configured"]
    assert "cli-test-secret" not in json.dumps(public)
    assert load_settings(tmp_path).tushare_token.get_secret_value() == "cli-test-secret"


def test_token_rotation_preserves_scan_signature(engine):
    from jev_trader.jobs import JobManager
    manager = JobManager(engine)
    old = manager._configuration()
    engine.settings.tushare_token = SecretStr("changed-test-token")
    assert manager._configuration() == old
    engine.settings.provider = "tushare"
    assert manager._configuration() != old
