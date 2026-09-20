from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np
import pandas as pd

from jev_trader.models import AnalysisError, Stock, normalize_symbol

from .worker import AKWorker

RENAME = {"日期": "date", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount", "换手率": "turnover"}
PRICE_COLUMNS = ["open", "high", "low", "close"]


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=12))


def validate_bars(frame: pd.DataFrame, as_of: date) -> pd.DataFrame:
    required = {"date", *PRICE_COLUMNS, "volume"}
    if frame.empty or not required.issubset(frame.columns):
        raise AnalysisError("empty_data", "行情为空或缺少必要字段。", "Market data is empty or missing required fields.")
    frame = frame.copy()
    try:
        parsed_dates = pd.to_datetime(frame["date"], errors="raise")
        if parsed_dates.isna().any():
            raise ValueError("missing date")
        frame["date"] = parsed_dates.dt.strftime("%Y-%m-%d")
        frame = frame.loc[frame.date <= as_of.isoformat()].sort_values("date").reset_index(drop=True)
        frame[PRICE_COLUMNS + ["volume"]] = frame[PRICE_COLUMNS + ["volume"]].apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as exc:
        raise AnalysisError("invalid_data", "行情包含无效日期或数值。", "Market data contains invalid dates or values.") from exc
    if frame.empty:
        raise AnalysisError("empty_data", "截止日期之前没有完整日线。", "No completed daily bars exist before the cutoff.")
    values = frame[PRICE_COLUMNS + ["volume"]].to_numpy(dtype=float)
    if frame.date.duplicated().any() or not np.isfinite(values).all() or (frame[PRICE_COLUMNS] <= 0).any().any() or (frame.volume < 0).any():
        raise AnalysisError("invalid_data", "行情有重复日期、无效价格或成交量。", "Market data has duplicate dates, invalid prices, or invalid volume.")
    tolerance = frame.close.abs() * .00001 + .011
    invalid = (frame.high + tolerance < frame[["open", "close", "low"]].max(axis=1)) | (frame.low - tolerance > frame[["open", "close", "high"]].min(axis=1))
    if invalid.any():
        raise AnalysisError("invalid_ohlc", "开高低收之间不一致，停止分析。", "Inconsistent OHLC values; analysis stopped.")
    for key in ["amount", "turnover"]:
        if key not in frame:
            frame[key] = np.nan
        frame[key] = pd.to_numeric(frame[key], errors="coerce")
        if (frame[key].dropna() < 0).any() or not np.isfinite(frame[key].dropna()).all():
            raise AnalysisError("invalid_data", "成交额或换手率为负值或无效值。", "Negative or non-finite amount or turnover values.")
    return frame[["date", *PRICE_COLUMNS, "volume", "amount", "turnover"]]


def normalize_frame(frame: pd.DataFrame, source: str, as_of: date) -> pd.DataFrame:
    frame = frame.rename(columns=RENAME).copy()
    if source == "eastmoney":
        # 东财成交量为手、换手率为百分数；内部统一为股、百分数。
        if "volume" in frame:
            frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce") * 100
    elif source == "tencent":
        # AKShare 1.18.96 腾讯接口已经统一成交量为股，换手率仍为小数。
        if "turnover" in frame:
            frame["turnover"] = pd.to_numeric(frame["turnover"], errors="coerce") * 100
    return validate_bars(frame, as_of)


def merge_history(cached: pd.DataFrame, fresh: pd.DataFrame) -> pd.DataFrame | None:
    shared = cached.merge(fresh, on="date", suffixes=("_old", "_new"))
    if shared.empty:
        return None
    # 重叠窗口复权值变化意味着整段历史需要重建，不能用旧基准直接追加。
    for column in PRICE_COLUMNS:
        if not np.allclose(shared[f"{column}_old"], shared[f"{column}_new"], rtol=1e-6, atol=.005):
            return None
    return pd.concat([cached, fresh]).drop_duplicates("date", keep="last").sort_values("date").reset_index(drop=True)


class AKShareProvider:
    name = "akshare"

    def __init__(self, settings, store):
        self.settings, self.store = settings, store
        self.worker = AKWorker(settings.request_timeout, settings.request_interval)

    def close(self):
        self.worker.close()

    def universe(self) -> list[Stock]:
        cached = self.store.get("universe:akshare", max_age=86400)
        if cached:
            return [Stock.model_validate(stock) for stock in cached]
        frame = self.worker.call("stock_info_a_code_name")
        stocks = []
        for row in frame.to_dict("records"):
            code, name = str(row["code"]).zfill(6), str(row["name"])
            try:
                symbol = normalize_symbol(code)
            except AnalysisError:
                continue
            market = symbol[-2:]
            board = "star" if code.startswith("688") else "chinext" if code.startswith(("300", "301")) else "beijing" if market == "BJ" else "main"
            stocks.append(Stock(symbol=symbol, name=name, market=market, board=board, special="ST" in name.upper() or "退" in name))
        if not stocks:
            raise AnalysisError("universe_empty", "未取得 A 股股票列表。", "No A-share universe was returned.")
        self.store.put("universe:akshare", [stock.model_dump() for stock in stocks])
        return stocks

    def calendar(self) -> list[date]:
        cached = self.store.get("calendar:akshare", max_age=86400)
        if not cached:
            frame = self.worker.call("tool_trade_date_hist_sina")
            cached = sorted({str(value)[:10] for value in frame["trade_date"]})
            self.store.put("calendar:akshare", cached)
        return [date.fromisoformat(value) for value in cached]

    def _fetch(self, symbol: str, start: date, as_of: date, source: str) -> pd.DataFrame:
        arguments = {"start_date": start.strftime("%Y%m%d"), "end_date": as_of.strftime("%Y%m%d"), "adjust": "qfq"}
        if source == "eastmoney":
            frame = self.worker.call("stock_zh_a_hist", symbol=symbol[:6], period="daily", **arguments)
        elif source == "tencent":
            frame = self.worker.call("stock_zh_a_hist_tx", symbol=symbol[-2:].lower() + symbol[:6], timeout=self.settings.request_timeout, **arguments)
        else:
            raise AnalysisError("unknown_source", "不支持的 AKShare 上游。", "Unsupported AKShare upstream source.")
        return normalize_frame(frame, source, as_of)

    def bars(self, symbol: str, as_of: date) -> tuple[pd.DataFrame, str]:
        full_start = as_of - timedelta(days=365 * self.settings.history_years + 3)
        last_error = None
        for source in self.settings.source_order:
            key = f"bars:akshare:{source}:qfq:{symbol}"
            saved = self.store.get(key)
            try:
                cached = validate_bars(pd.DataFrame(saved), as_of) if saved else None
            except AnalysisError:
                cached = None
            # 历史记录可能覆盖更晚日期，不向较早截止日的模型输入泄露未来数据。
            if cached is not None and cached.date.iloc[-1] == as_of.isoformat():
                return cached, f"AKShare / {source}"
            start = max(full_start, date.fromisoformat(cached.date.iloc[-1]) - timedelta(days=40)) if cached is not None else full_start
            try:
                fresh = self._fetch(symbol, start, as_of, source)
                merged = merge_history(cached, fresh) if cached is not None else fresh
                if merged is None:
                    merged = self._fetch(symbol, full_start, as_of, source)
                self.store.put(key, records(merged))
                if merged.date.iloc[-1] != as_of.isoformat():
                    continue
                return merged, f"AKShare / {source}"
            except AnalysisError as exc:
                last_error = exc
        # 失败时保留旧行情，但明确截止时间；服务层禁止把它视作最新模型输入。
        for source in self.settings.source_order:
            saved = self.store.get(f"bars:akshare:{source}:qfq:{symbol}")
            if saved:
                try:
                    return validate_bars(pd.DataFrame(saved), as_of), f"AKShare / {source} (cache)"
                except AnalysisError as exc:
                    last_error = exc
        raise last_error or AnalysisError("data_unavailable", "无法取得行情。", "No market data is available.")

    def metadata(self, stock: Stock) -> Stock:
        key = f"metadata:akshare:{stock.symbol}"
        cached = self.store.get(key, max_age=86400 * 7)
        if cached:
            return stock.model_copy(update=cached)
        frame = self.worker.call("stock_individual_info_em", symbol=stock.symbol[:6], timeout=self.settings.request_timeout)
        values = dict(zip(frame["item"], frame["value"], strict=False))
        # 不使用该接口的实时价格、成交量等字段。
        metadata = {"industry": str(values["行业"]) if values.get("行业") else None, "listed": str(values["上市时间"]) if values.get("上市时间") else None}
        self.store.put(key, metadata)
        return stock.model_copy(update=metadata)

    def benchmark(self, as_of: date) -> pd.DataFrame:
        sources = ("eastmoney", "sina", "tencent")
        keys = {source: f"benchmark:akshare:{source}:000300:{as_of}" for source in sources}
        for source in sources:
            cached = self.store.get(keys[source])
            if cached:
                frame = validate_bars(pd.DataFrame(cached), as_of)
                if frame.date.iloc[-1] == as_of.isoformat():
                    return frame
        last_error = None
        for source in sources:
            try:
                if source == "sina":
                    frame = self.worker.call("stock_zh_index_daily", symbol="sh000300")
                else:
                    endpoint = "stock_zh_index_daily_em" if source == "eastmoney" else "stock_zh_index_daily_tx"
                    frame = self.worker.call(endpoint, symbol="sh000300", start_date=(as_of - timedelta(days=3650)).strftime("%Y%m%d"), end_date=as_of.strftime("%Y%m%d"))
                    if source == "tencent":
                        # 腾讯指数的 amount 实际为成交手数，不是成交金额。
                        frame = frame.rename(columns={"amount": "volume"})
                        frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce") * 100
                frame = validate_bars(frame, as_of)
                if frame.date.iloc[-1] != as_of.isoformat():
                    raise AnalysisError("benchmark_stale", "大盘指数尚未更新，相对大盘维度不可用。", "Benchmark data is stale; benchmark-relative evidence is unavailable.")
                self.store.put(keys[source], records(frame))
                return frame
            except AnalysisError as exc:
                last_error = exc
            except (KeyError, TypeError, ValueError):
                last_error = AnalysisError("invalid_data", "指数接口返回了无效字段。", "The index source returned invalid fields.")
        raise last_error

    def industry(self, name: str, as_of: date) -> pd.DataFrame:
        key = f"industry:akshare:{name}:{as_of}"
        cached = self.store.get(key)
        if cached:
            return pd.DataFrame(cached)
        frame = self.worker.call("stock_board_industry_hist_em", symbol=name, period="日k", start_date=(as_of - timedelta(days=3650)).strftime("%Y%m%d"), end_date=as_of.strftime("%Y%m%d"), adjust="")
        frame = validate_bars(frame.rename(columns=RENAME), as_of)
        self.store.put(key, records(frame))
        return frame
