from datetime import date

import numpy as np
import pandas as pd
import pytest

from jev_trader.models import AnalysisError, Stock


@pytest.fixture(autouse=True)
def isolated_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)


@pytest.fixture
def bars():
    dates = pd.bdate_range(end="2026-09-18", periods=520)
    x = np.arange(len(dates), dtype=float)
    close = 20 + x * .025 + np.sin(x / 9) * .7
    volume = 100_000 + (x % 7) * 10_000
    return pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "open": close - .12,
                         "high": close + .35, "low": close - .4, "close": close,
                         "volume": volume, "amount": close * volume, "turnover": 1.2})


@pytest.fixture
def sessions():
    # 测试日历，不是实际交易所日历；节假日边界另有专门用例。
    return [stamp.date() for stamp in pd.bdate_range("2024-01-01", "2026-12-31")]


class FakeProvider:
    def __init__(self, frame, calendar):
        self.frame, self.sessions = frame, calendar
        self.calls = 0

    def close(self):
        pass

    def calendar(self):
        return self.sessions

    def universe(self):
        return [Stock(symbol="000001.SZ", name="测试股票", market="SZ"),
                Stock(symbol="600000.SH", name="测试股票二", market="SH"),
                Stock(symbol="600001.SH", name="ST测试", market="SH", special=True)]

    def bars(self, symbol, as_of):
        self.calls += 1
        return self.frame.copy(), "test fixture"

    def metadata(self, stock):
        return stock

    def benchmark(self, as_of):
        raise AnalysisError("benchmark_missing", "测试指数缺失", "Test benchmark missing")

    def industry(self, name, as_of):
        raise AssertionError("No industry is configured")


@pytest.fixture
def engine(tmp_path, bars, sessions):
    from jev_trader.service import Engine
    result = Engine(tmp_path, provider=FakeProvider(bars, sessions))
    result.context = lambda: (sessions, date(2026, 9, 18))
    return result
