from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from jev_trader.calendar import SHANGHAI, complete_periods, latest_completed
from jev_trader.config import Settings
from jev_trader.models import AnalysisError, normalize_symbol
from jev_trader.providers.akshare import AKShareProvider, merge_history, normalize_frame, validate_bars
from jev_trader.storage import Store


@pytest.mark.parametrize("instant,expected", [("2026-09-21T14:59:59", "2026-09-18"), ("2026-09-21T15:00:00", "2026-09-21"), ("2026-09-20T16:00:00", "2026-09-18"), ("2026-09-22T10:00:00", "2026-09-21")])
def test_completed_session(sessions, instant, expected):
    assert latest_completed(sessions, datetime.fromisoformat(instant).replace(tzinfo=SHANGHAI)).isoformat() == expected


def test_holiday_and_timezone():
    sessions = [date(2026, 9, 30), date(2026, 10, 9)]
    assert latest_completed(sessions, datetime.fromisoformat("2026-10-08T23:59:00+08:00")) == date(2026, 9, 30)
    assert latest_completed(sessions, datetime.fromisoformat("2026-10-09T06:00:00+00:00")) == date(2026, 9, 30)
    with pytest.raises(AnalysisError, match="stale"):
        latest_completed([date(2025, 1, 1)], datetime(2026, 9, 21, tzinfo=SHANGHAI))


def test_closed_periods_only(bars, sessions):
    as_of = date(2026, 9, 16)
    weekly = complete_periods(bars, sessions, as_of, "weekly")
    monthly = complete_periods(bars, sessions, as_of, "monthly")
    assert weekly.date.iloc[-1] == "2026-09-11"
    assert monthly.date.iloc[-1] == "2026-08-31"
    last_week = bars[(bars.date >= "2026-09-07") & (bars.date <= "2026-09-11")]
    assert weekly.volume.iloc[-1] == last_week.volume.sum()
    assert weekly.high.iloc[-1] == last_week.high.max()


def test_short_holiday_week_is_closed(bars):
    calendar = [date(2026, 9, day) for day in (14, 15, 16, 21, 22, 23, 24, 25)]
    weekly = complete_periods(bars, calendar, date(2026, 9, 16), "weekly")
    assert weekly.date.iloc[-1] == "2026-09-16"


def test_cutoff_removes_future_invalid_bar(bars):
    future = bars.iloc[[-1]].copy()
    future["date"], future["close"] = "2026-09-21", np.nan
    output = validate_bars(pd.concat([bars, future]), date(2026, 9, 18))
    assert len(output) == len(bars)


@pytest.mark.parametrize("mutation", ["duplicate", "nan", "negative_volume", "invalid_ohlc", "missing_date", "infinite_amount"])
def test_bad_data_stops_analysis(bars, mutation):
    if mutation == "duplicate":
        bars = pd.concat([bars, bars.tail(1)])
    elif mutation == "nan":
        bars.loc[519, "close"] = np.nan
    elif mutation == "negative_volume":
        bars.loc[519, "volume"] = -1
    elif mutation == "missing_date":
        bars.loc[519, "date"] = None
    elif mutation == "infinite_amount":
        bars.loc[519, "amount"] = float("inf")
    else:
        bars.loc[519, "high"] = 1
    with pytest.raises(AnalysisError):
        validate_bars(bars, date(2026, 9, 18))


def test_units_and_missing_optional_values(bars):
    frame = bars.tail(1).drop(columns=["amount", "turnover"])
    assert normalize_frame(frame, "eastmoney", date(2026, 9, 18)).volume.iloc[0] == frame.volume.iloc[0] * 100
    tx = normalize_frame(bars.tail(1).assign(turnover=.012), "tencent", date(2026, 9, 18))
    assert tx.volume.iloc[0] == bars.volume.iloc[-1]
    assert tx.turnover.iloc[0] == pytest.approx(1.2)
    assert validate_bars(frame, date(2026, 9, 18)).amount.isna().all()


def test_adjustment_change_invalidates_whole_history(bars):
    old, fresh = bars.iloc[:-5].copy(), bars.iloc[-20:].copy()
    assert len(merge_history(old, fresh)) == len(bars)
    fresh[["open", "high", "low", "close"]] *= .8
    assert merge_history(old, fresh) is None


def test_stale_primary_tries_backup(tmp_path, bars, monkeypatch):
    provider = AKShareProvider(Settings(), Store(tmp_path))
    calls = []

    def fetch(symbol, start, as_of, source):
        calls.append(source)
        return bars.iloc[:-1].copy() if source == "eastmoney" else bars.copy()

    monkeypatch.setattr(provider, "_fetch", fetch)
    frame, source = provider.bars("000001.SZ", date(2026, 9, 18))
    assert frame.date.iloc[-1] == "2026-09-18" and source.endswith("tencent")
    assert calls == ["eastmoney", "tencent"]


@pytest.mark.parametrize("raw,expected", [("000001", "000001.SZ"), ("sh600000", "600000.SH"), ("920001.BJ", "920001.BJ")])
def test_symbols(raw, expected):
    assert normalize_symbol(raw) == expected


@pytest.mark.parametrize("raw", ["600000.SZ", "SH000001", "123456", "000001; rm -rf /"])
def test_invalid_symbols(raw):
    with pytest.raises(AnalysisError):
        normalize_symbol(raw)


@pytest.mark.parametrize("backup", ["sina", "tencent"])
def test_benchmark_fallback_and_independent_cache(tmp_path, bars, monkeypatch, backup):
    provider = AKShareProvider(Settings(), Store(tmp_path))
    calls = []
    def call(function, **kwargs):
        calls.append(function)
        if function.endswith("_em") or (backup == "tencent" and function == "stock_zh_index_daily"):
            raise AnalysisError("data_unavailable", "不可用", "Unavailable")
        if backup == "tencent":
            return bars.drop(columns=["volume", "turnover"]).assign(amount=100)
        return bars
    monkeypatch.setattr(provider.worker, "call", call)
    result = provider.benchmark(date(2026, 9, 18))
    assert result.date.iloc[-1] == "2026-09-18"
    if backup == "tencent":
        assert result.volume.iloc[-1] == 10000 and result.amount.isna().all()
    before = len(calls)
    assert provider.benchmark(date(2026, 9, 18)).close.iloc[-1] == pytest.approx(result.close.iloc[-1])
    assert len(calls) == before


def test_stale_benchmark_tries_next_source(tmp_path, bars, monkeypatch):
    provider = AKShareProvider(Settings(), Store(tmp_path))
    monkeypatch.setattr(provider.worker, "call", lambda function, **kw: bars.iloc[:-1] if function.endswith("_em") else bars)
    assert provider.benchmark(date(2026, 9, 18)).date.iloc[-1] == "2026-09-18"
