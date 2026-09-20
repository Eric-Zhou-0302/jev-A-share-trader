from datetime import date

import numpy as np
import pytest

from jev_trader.indicators import compute, kdj, pivots, supertrend


def test_indicator_values_against_manual_calculation(bars, sessions):
    result = compute(bars, sessions, date(2026, 9, 18))
    metrics = {item.key: item.value for item in result.metrics}
    close = bars.close.tail(20)
    assert metrics["sma_20"] == pytest.approx(close.mean(), abs=1e-6)
    assert metrics["wma_20"] == pytest.approx(np.dot(close, np.arange(1, 21)) / 210, abs=1e-6)
    assert metrics["bb_upper"] == pytest.approx(close.mean() + 2 * close.std(ddof=0), abs=1e-6)
    assert metrics["relative_volume_20"] == pytest.approx(bars.volume.iloc[-1] / bars.volume.iloc[-21:-1].mean(), abs=1e-6)
    assert metrics["vwma_20"] == pytest.approx((close * bars.volume.tail(20)).sum() / bars.volume.tail(20).sum(), abs=1e-6)
    assert metrics["realized_vol_20"] == pytest.approx(np.log(bars.close / bars.close.shift()).tail(20).std(ddof=1) * np.sqrt(252) * 100, abs=1e-6)
    assert metrics["macd_hist"] == pytest.approx(metrics["macd"] - metrics["macd_signal"], abs=2e-6)
    assert len(metrics) >= 85


def test_future_values_do_not_change_any_fact(bars, sessions):
    cutoff = date(2026, 9, 10)
    original = compute(bars[bars.date <= cutoff.isoformat()], sessions, cutoff)
    future = bars.copy()
    future.loc[future.date > cutoff.isoformat(), ["open", "high", "low", "close", "volume"]] *= 100
    actual = compute(future, sessions, cutoff)
    assert original.metrics == actual.metrics
    assert original.evidence == actual.evidence
    assert original.charts == actual.charts


def test_kdj_seed_and_flat_denominator():
    high, low, close = np.full(12, 12.), np.full(12, 8.), np.full(12, 11.)
    k, d, j = kdj(high, low, close)
    assert np.isnan(k[7])
    assert k[8] == pytest.approx(50 * 2 / 3 + 75 / 3)
    assert d[8] == pytest.approx(50 * 2 / 3 + k[8] / 3)
    assert j[8] == pytest.approx(3 * k[8] - 2 * d[8])
    flat = np.full(12, 10.)
    assert kdj(flat, flat, flat)[0][-1] == 50


def test_pivots_require_two_subsequent_candles():
    values = np.array([1, 2, 5, 2, 1, 3, 8.])
    assert pivots(values, "high") == [2]
    assert pivots(np.append(values, [3, 2]), "high") == [2, 6]


def test_supertrend_crosses_only_when_band_breaks():
    close = np.r_[np.arange(20., 55.), np.arange(54., 15., -1)]
    line, direction = supertrend(close + 1, close - 1, close)
    assert np.isnan(line[:10]).all()
    assert direction[30] == 1 and line[30] < close[30]
    assert direction[-1] == -1 and line[-1] > close[-1]


def test_breakout_excludes_current_bar(bars, sessions):
    bars.loc[519, "close"] = bars.high.iloc[-61:-1].max() + 2
    bars.loc[519, "high"] = bars.close.iloc[-1] + .3
    result = compute(bars, sessions, date(2026, 9, 18))
    assert next(item for item in result.evidence if item.id == "range_position").polarity == 1


def test_reference_requires_matching_dates(bars, sessions):
    result = compute(bars, sessions, date(2026, 9, 18), bars.iloc[:-1])
    assert not any(item.key.startswith("relative_benchmark") for item in result.metrics)
    reference = bars.copy()
    reference["close"] = 10.
    result = compute(bars, sessions, date(2026, 9, 18), reference)
    metric = next(item for item in result.metrics if item.key == "relative_benchmark_20")
    assert metric.value == pytest.approx((bars.close.iloc[-1] / bars.close.iloc[-21] - 1) * 100, abs=1e-6)


def test_breadth_requires_cutoff_and_coverage(bars, sessions):
    for breadth in ({"as_of": "2026-09-17", "coverage": 1, "above_ma20_pct": 70}, {"as_of": "2026-09-18", "coverage": .79, "above_ma20_pct": 70}):
        result = compute(bars, sessions, date(2026, 9, 18), breadth=breadth)
        assert not any(item.id == "market_breadth" for item in result.evidence)


def test_flat_series_remains_serializable(bars, sessions):
    bars[["open", "high", "low", "close"]] = 10.
    result = compute(bars, sessions, date(2026, 9, 18))
    assert all(item.value is None or np.isfinite(item.value) for item in result.metrics)
    assert all("nan" not in item.en for item in result.evidence)
