from __future__ import annotations

import hashlib
import json
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .calendar import SHANGHAI, latest_completed
from .config import load_settings
from .indicators import VERSION, compute, finite
from .jev import PROMPT_VERSION, JevClient, aggregate
from .models import Analysis, AnalysisError, Stock, normalize_symbol
from .providers import create_provider
from .providers.akshare import records, validate_bars
from .storage import Store


def notice(code: str, zh: str, en: str) -> dict:
    return {"code": code, "zh": zh, "en": en}


class Engine:
    def __init__(self, directory: Path, provider=None, client=None):
        self.directory, self.store = directory, Store(directory)
        self.analysis_lock = threading.RLock()
        self.settings = load_settings(directory)
        self.provider = provider or create_provider(self.settings, self.store)
        self.client = client or JevClient(self.settings)

    def close(self):
        self.provider.close()

    def context(self) -> tuple[list[date], date]:
        sessions = self.provider.calendar()
        return sessions, latest_completed(sessions)

    def breadth_key(self, as_of: date) -> str:
        scope = self.settings.model_dump(include={"provider", "markets", "exclude_special", "min_bars", "min_amount"})
        scope["markets"] = sorted(scope["markets"])
        digest = hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest()[:16]
        return f"breadth:{as_of}:{digest}"

    def get_stock(self, symbol: str) -> Stock:
        symbol = normalize_symbol(symbol)
        for stock in self.provider.universe():
            if stock.symbol == symbol:
                return stock
        raise AnalysisError("unknown_stock", "股票不在当前 A 股名单中。", "The stock is not in the current A-share universe.")

    def filter_stock(self, stock: Stock) -> None:
        if stock.market not in self.settings.markets:
            raise AnalysisError("market_filtered", "该交易所未纳入当前扫描范围。", "This exchange is outside the configured universe.")
        if self.settings.exclude_special and stock.special:
            raise AnalysisError("special_filtered", "当前默认过滤 ST／退市整理股票。", "ST / delisting stocks are excluded by the current filter.")

    def check_frame(self, frame: pd.DataFrame, as_of: date) -> None:
        if frame.empty:
            raise AnalysisError("empty_data", "未取得已完成的日线。", "No completed daily bars were returned.")
        if frame.date.iloc[-1] != as_of.isoformat():
            raise AnalysisError("stale_or_suspended", f"最新完整日线为 {frame.date.iloc[-1]}，尚未取得 {as_of} 数据；可能停牌或上游未更新。", f"Latest completed bar is {frame.date.iloc[-1]}; {as_of} is missing. The stock may be suspended or the upstream has not updated.")
        if frame.volume.iloc[-1] <= 0:
            raise AnalysisError("suspended", "最新交易日无成交，暂不形成判断。", "No trading volume on the latest session; no decision is produced.")
        if len(frame) < self.settings.min_bars:
            raise AnalysisError("insufficient_history", f"需要至少 {self.settings.min_bars} 根完整日线，当前仅 {len(frame)} 根。", f"At least {self.settings.min_bars} completed daily bars are required; only {len(frame)} are available.")
        if self.settings.min_amount and (frame.amount.tail(20).isna().any() or frame.amount.tail(20).mean() < self.settings.min_amount):
            raise AnalysisError("liquidity_filtered", "成交额不足或缺失，未通过流动性过滤。", "Insufficient or missing turnover amount; liquidity filter failed.")

    def analyze(self, symbol: str, technical_only=False, pinned_context=None, stock: Stock | None = None, market_data=None) -> Analysis:
        # 配置修改和单次分析互斥，防止签名、模型与聚合规则来自不同快照。
        with self.analysis_lock:
            return self._analyze(symbol, technical_only, pinned_context, stock, market_data)

    def _analyze(self, symbol: str, technical_only=False, pinned_context=None, stock: Stock | None = None, market_data=None) -> Analysis:
        stock = stock or self.get_stock(symbol)
        self.filter_stock(stock)
        sessions, requested = pinned_context or self.context()
        # 批量任务复用当前股票刚取得的行情，仍执行完整校验。
        frame, source = market_data if market_data is not None else self.provider.bars(stock.symbol, requested)
        notices = list(frame.attrs.get("notices", []))
        frame = validate_bars(frame, requested)
        self.check_frame(frame, requested)
        reference = industry = None
        try:
            reference = self.provider.benchmark(requested)
            if reference.date.iloc[-1] != requested.isoformat():
                reference = None
                raise AnalysisError("benchmark_stale", "大盘指数尚未更新，相对大盘维度不可用。", "Benchmark data is stale; benchmark-relative evidence is unavailable.")
        except AnalysisError as exc:
            notices.append(notice(exc.code, exc.zh, exc.en))
        try:
            stock = self.provider.metadata(stock)
            if stock.industry:
                industry = self.provider.industry(stock.industry, requested)
                if industry.date.iloc[-1] != requested.isoformat():
                    industry = None
                    raise AnalysisError("industry_stale", "行业指数尚未更新，行业维度不可用。", "Industry data is stale; industry-relative evidence is unavailable.")
            else:
                notices.append(notice("industry_missing", "该股票的行业归属不可用。", "Industry classification is unavailable for this stock."))
        except AnalysisError as exc:
            notices.append(notice(exc.code, exc.zh, exc.en))
        breadth = self.store.get(self.breadth_key(requested))
        if not breadth:
            notices.append(notice("breadth_missing", "缺少同日全市场宽度数据；本次未使用，也不会用股票列表估算。", "Same-day market breadth is unavailable and is not used or estimated from the stock list."))
        technical = compute(frame, sessions, requested, reference, industry, breadth)
        if len(technical.charts["monthly"]) < 13:
            notices.append(notice("monthly_history", "完整月线不足 13 根，未使用月线趋势证据。", "Fewer than 13 completed monthly bars; monthly trend evidence is unavailable."))
        if frame.turnover.isna().any():
            notices.append(notice("turnover_partial", "部分换手率缺失，未补造数值。", "Some turnover-rate values are missing and have not been imputed."))
        state = {
            "as_of": requested.isoformat(), "market": "China A shares", "adjustment": "forward adjusted (qfq)",
            "evidence": [item.model_dump(exclude={"zh", "side"}) for item in technical.evidence],
            "metrics": [metric.model_dump() for metric in technical.metrics if metric.value is not None],
            "data_quality": {"rows": len(frame), "groups_available": technical.groups_available, "missing": [item["en"] for item in notices]},
            "volatility_context": {"natr_14_latest": finite(technical.series["natr_14"][-1]), "natr_14_median_120": finite(np.nanmedian(technical.series["natr_14"][-120:])), "bandwidth_latest": finite(technical.series["bb_width_pct"][-1]), "bandwidth_median_120": finite(np.nanmedian(technical.series["bb_width_pct"][-120:]))},
        }
        signature = {"symbol": stock.symbol, "state": state, "model": self.settings.model, "weights": self.settings.weights, "buy": self.settings.buy_threshold, "sell": self.settings.sell_threshold, "risk": self.settings.risk_damping, "indicators": VERSION, "prompt": PROMPT_VERSION, "source": source}
        digest = hashlib.sha256(json.dumps(signature, sort_keys=True, allow_nan=False).encode()).hexdigest()
        if not technical_only and self.settings.jev_api_key.get_secret_value():
            saved = self.store.get(f"decision:{digest}", max_age=86400)
            if saved and self.store.analysis(saved["id"]):
                return Analysis.model_validate(saved).model_copy(update={"cached": True})
        # 缓存命中可复用原报告；实际重新计算时创建独立快照，不能覆盖历史报告。
        result = Analysis(id=uuid.uuid4().hex, symbol=stock.symbol, name=stock.name, market=stock.market,
            as_of=requested.isoformat(), requested_as_of=requested.isoformat(), created_at=datetime.now(SHANGHAI).isoformat(),
            status="technical_only", source=source, rows=len(frame), evidence=technical.evidence, metrics=technical.metrics,
            bars=records(frame.tail(300)), charts=technical.charts, notices=notices, groups_available=technical.groups_available)
        if not technical_only:
            try:
                answers, metadata = self.client.evaluate(state, technical.groups_available)
                action, horizon, evidence, details = aggregate(answers, technical.evidence, self.settings)
                result.action, result.horizon, result.evidence = action, horizon, evidence
                result.status, result.model = "ready", metadata["model"]
                self.store.put(f"audit:{result.id}", {"signature": signature, "model_response": metadata, "aggregation": details})
                self.store.put(f"decision:{digest}", result.model_dump(mode="json"))
            except AnalysisError as exc:
                result.status = exc.code
                result.notices.append(notice(exc.code, exc.zh, exc.en))
        self.store.save_analysis(result.model_dump(mode="json"))
        return result
