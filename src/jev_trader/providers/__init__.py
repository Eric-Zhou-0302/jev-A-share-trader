from __future__ import annotations

from datetime import date
from importlib.metadata import entry_points
from typing import Protocol

import pandas as pd

from jev_trader.models import Stock


class MarketProvider(Protocol):
    """扩展提供方统一返回日期及股／元单位；价格为同口径前复权序列。"""

    name: str

    def universe(self) -> list[Stock]: ...
    def calendar(self) -> list[date]: ...
    def bars(self, symbol: str, as_of: date) -> tuple[pd.DataFrame, str]: ...
    def metadata(self, stock: Stock) -> Stock: ...
    def benchmark(self, as_of: date) -> pd.DataFrame: ...
    def industry(self, name: str, as_of: date) -> pd.DataFrame: ...
    def close(self) -> None: ...


REGISTRY: dict[str, type] = {}


def register_provider(name: str, provider: type) -> None:
    REGISTRY[name] = provider


def create_provider(settings, store) -> MarketProvider:
    from .akshare import AKShareProvider

    if settings.provider == "akshare":
        return AKShareProvider(settings, store)
    if settings.provider == "tushare":
        from .tushare import TushareProvider
        return TushareProvider(settings, store)
    if settings.provider not in REGISTRY:
        plugins = entry_points(group="jev_trader.providers", name=settings.provider)
        for plugin in plugins:
            register_provider(settings.provider, plugin.load())
    if settings.provider not in REGISTRY:
        from jev_trader.models import AnalysisError
        raise AnalysisError("unknown_provider", "该数据提供方尚未注册。", "The data provider is not registered.")
    return REGISTRY[settings.provider](settings, store)
