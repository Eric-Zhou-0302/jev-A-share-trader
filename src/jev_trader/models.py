from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Language = Literal["zh", "en"]
Action = Literal["buy", "hold", "sell"]
GROUPS = ("trend", "momentum", "volume", "volatility", "structure", "candles", "multitimeframe", "relative")
GROUP_NAMES = {
    "trend": ("趋势", "Trend"), "momentum": ("动量", "Momentum"),
    "volume": ("量价", "Volume"), "volatility": ("波动", "Volatility"),
    "structure": ("价格结构", "Price structure"), "candles": ("K 线形态", "Candlesticks"),
    "multitimeframe": ("多周期", "Timeframes"), "relative": ("相对强弱", "Relative strength"),
}


class AnalysisError(Exception):
    def __init__(self, code: str, zh: str, en: str):
        super().__init__(en)
        self.code, self.zh, self.en = code, zh, en

    def message(self, lang: str = "zh") -> str:
        return self.en if lang == "en" else self.zh


def normalize_symbol(value: str) -> str:
    value = value.strip().upper()
    match = re.fullmatch(r"(?:(SH|SZ|BJ))?(\d{6})(?:\.(SH|SZ|BJ))?", value)
    if not match:
        raise AnalysisError("invalid_symbol", "请输入六位 A 股代码。", "Enter a six-digit A-share symbol.")
    prefix, code, suffix = match.groups()
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        market = "SH"
    elif code.startswith(("000", "001", "002", "003", "300", "301")):
        market = "SZ"
    elif code.startswith(("43", "83", "87", "88", "92")):
        market = "BJ"
    else:
        raise AnalysisError("invalid_symbol", "该代码不属于支持的 A 股股票范围。", "This code is outside the supported A-share stock universe.")
    if any(part and part != market for part in (prefix, suffix)):
        raise AnalysisError("invalid_symbol", "股票代码与交易所不匹配。", "The symbol and exchange do not match.")
    return f"{code}.{market}"


class Stock(BaseModel):
    symbol: str
    name: str
    market: str
    board: str = "main"
    industry: str | None = None
    listed: str | None = None
    special: bool = False


class Evidence(BaseModel):
    id: str
    group: str
    polarity: int = Field(ge=-1, le=1)
    zh: str
    en: str
    date: str
    strength: float = Field(default=1.0, ge=0, le=1)
    metrics: dict[str, float | str | None] = Field(default_factory=dict)
    side: Literal["support", "oppose", "context"] = "context"


class Metric(BaseModel):
    key: str
    group: str
    label: str
    value: float | None
    unit: str = ""


class Analysis(BaseModel):
    id: str
    symbol: str
    name: str
    market: str
    as_of: str
    requested_as_of: str
    created_at: str
    status: str
    action: Action | None = None
    horizon: str | None = None
    source: str
    adjustment: str = "qfq"
    rows: int
    evidence: list[Evidence] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    bars: list[dict] = Field(default_factory=list)
    charts: dict[str, list[dict]] = Field(default_factory=dict)
    notices: list[dict[str, str]] = Field(default_factory=list)
    model: str | None = None
    cached: bool = False
    groups_available: list[str] = Field(default_factory=list)


def iso(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)[:10]
