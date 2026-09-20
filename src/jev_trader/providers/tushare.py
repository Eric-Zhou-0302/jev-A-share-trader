from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timedelta

import httpx
import numpy as np
import pandas as pd

from jev_trader.calendar import SHANGHAI
from jev_trader.models import AnalysisError, Stock, normalize_symbol

from .akshare import PRICE_COLUMNS, records, validate_bars

API_URL = "https://api.tushare.pro"


def data_error() -> AnalysisError:
    return AnalysisError("invalid_data", "Tushare 返回的数据格式或数值异常。", "Tushare returned invalid data or values.")


def normalize_daily(daily: pd.DataFrame, factors: pd.DataFrame, basic: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """以前复权截止日的因子为基准；成交量、成交额不做价格复权。"""
    try:
        daily, factors, basic = (frame.copy() for frame in (daily, factors, basic))
        cutoff = as_of.strftime("%Y%m%d")
        daily = daily.loc[daily.trade_date <= cutoff, ["trade_date", *PRICE_COLUMNS, "vol", "amount"]]
        factors = factors.loc[factors.trade_date <= cutoff]
        if daily.empty:
            raise AnalysisError("empty_data", "Tushare 未返回截止日之前的日线。", "Tushare returned no daily bars before the cutoff.")
        for frame in (daily, factors, basic):
            if frame.trade_date.duplicated().any():
                raise data_error()
        merged = daily.merge(factors[["trade_date", "adj_factor"]], on="trade_date", how="left", validate="one_to_one").sort_values("trade_date")
        factor = pd.to_numeric(merged.adj_factor, errors="raise")
        if not np.isfinite(factor).all() or (factor <= 0).any():
            raise AnalysisError("adjustment_missing", "复权因子缺失或无效，停止分析；请检查 adj_factor 权限和数据。", "Missing or invalid adjustment factors; analysis stopped. Check adj_factor access and data.")
        merged[PRICE_COLUMNS] = merged[PRICE_COLUMNS].apply(pd.to_numeric, errors="raise").mul(factor / factor.iloc[-1], axis=0)
        merged["date"] = pd.to_datetime(merged.trade_date, format="%Y%m%d", errors="raise").dt.strftime("%Y-%m-%d")
        merged["volume"] = pd.to_numeric(merged.vol, errors="raise") * 100
        merged["amount"] = pd.to_numeric(merged.amount, errors="raise") * 1000
        merged = merged.merge(basic[["trade_date", "turnover_rate"]], on="trade_date", how="left", validate="one_to_one")
        merged["turnover"] = merged.turnover_rate
        return validate_bars(merged, as_of)
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise data_error() from exc


class TushareProvider:
    name = "tushare"

    def __init__(self, settings, store, transport=None):
        self.settings, self.store, self.transport = settings, store, transport
        self.lock = threading.RLock()
        self.client = None
        self.last_call = 0.0

    def close(self):
        with self.lock:
            if self.client:
                self.client.close()
                self.client = None

    def _token(self):
        token = self.settings.tushare_token.get_secret_value().strip()
        if not token:
            raise AnalysisError("needs_tushare_token", "请先在设置中配置 Tushare Token，或选择 AKShare。", "Configure a Tushare token in Settings, or select AKShare.")
        return token

    def _api_error(self, api: str, code, message: str):
        # 只使用消息判别错误类型，不回传可能包含凭据的上游原文。
        message = message.lower()
        if "token" in message or code == 40101:
            return AnalysisError("tushare_auth", "Tushare Token 无效或已失效，请检查配置。", "The Tushare token is invalid or expired. Check configuration.")
        if any(word in message for word in ("频", "每分钟", "每小时", "每天", "rate", "limit")):
            return AnalysisError("tushare_rate_limit", f"Tushare {api} 已达到调用频次或额度限制，请稍后重试。", f"Tushare {api} reached its rate or quota limit. Retry later.")
        if code == 2002 or any(word in message for word in ("权限", "积分", "permission", "access")):
            return AnalysisError("tushare_permission", f"Tushare {api} 权限不足，请检查账户积分及接口权限。", f"Insufficient access to Tushare {api}. Check account points and API permissions.")
        return AnalysisError("data_unavailable", f"Tushare {api} 暂不可用，请稍后重试。", f"Tushare {api} is unavailable. Retry later.")

    def _query(self, api: str, fields: str, **params) -> pd.DataFrame:
        token = self._token()
        with self.lock:
            if self.client is None:
                try:
                    self.client = httpx.Client(timeout=self.settings.request_timeout, transport=self.transport)
                except (ImportError, ValueError, OSError) as exc:
                    raise AnalysisError("data_configuration", "Tushare 网络初始化失败，请检查依赖、代理和证书配置。", "Tushare network initialization failed. Check dependencies, proxy and certificates.") from exc
            for attempt in range(3):
                time.sleep(max(0, self.settings.request_interval - (time.monotonic() - self.last_call)))
                self.last_call = time.monotonic()
                try:
                    response = self.client.post(API_URL, json={"api_name": api, "token": token, "params": params, "fields": fields})
                except httpx.RequestError as exc:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    raise AnalysisError("data_unavailable", f"Tushare {api} 连接失败，请检查网络或稍后重试。", f"Tushare {api} connection failed. Check the network or retry later.") from exc
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    raise self._api_error(api, None, "rate limit" if response.status_code == 429 else "")
                if response.status_code in (401, 403):
                    raise self._api_error(api, 40101 if response.status_code == 401 else 2002, "")
                if response.status_code != 200:
                    raise self._api_error(api, None, "")
                try:
                    body = response.json()
                    if not isinstance(body, dict) or "code" not in body:
                        raise ValueError("invalid envelope")
                    if body["code"] != 0:
                        raise self._api_error(api, body["code"], str(body.get("msg", "")))
                    data = body["data"]
                    columns, rows = data["fields"], data["items"]
                    if (not isinstance(columns, list) or not all(isinstance(column, str) for column in columns)
                            or len(set(columns)) != len(columns) or not set(fields.split(",")).issubset(columns)
                            or not isinstance(rows, list) or any(not isinstance(row, list) or len(row) != len(columns) for row in rows)):
                        raise ValueError("invalid table")
                    return pd.DataFrame(rows, columns=columns)
                except (KeyError, TypeError, ValueError) as exc:
                    raise data_error() from exc
        raise data_error()

    def _history(self, api: str, fields: str, start: date, end: date, **params) -> pd.DataFrame:
        frames = []
        # 每段最多三个自然年，低于单证券日线和日历接口的行数上限。
        while start <= end:
            stop = min(end, start + timedelta(days=1094))
            part = self._query(api, fields, start_date=start.strftime("%Y%m%d"), end_date=stop.strftime("%Y%m%d"), **params)
            date_column = "cal_date" if api == "trade_cal" else "trade_date"
            try:
                dates = pd.to_datetime(part[date_column], format="%Y%m%d", errors="raise")
                if not dates.between(pd.Timestamp(start), pd.Timestamp(stop)).all():
                    raise data_error()
                part[date_column] = dates.dt.strftime("%Y%m%d")
            except (KeyError, TypeError, ValueError) as exc:
                raise data_error() from exc
            frames.append(part)
            start = stop + timedelta(days=1)
        frame = pd.concat(frames, ignore_index=True)
        date_column = "cal_date" if api == "trade_cal" else "trade_date"
        try:
            dates = pd.to_datetime(frame[date_column], format="%Y%m%d", errors="raise")
            if dates.isna().any() or dates.duplicated().any():
                raise ValueError("invalid dates")
            if "ts_code" in params and not frame.ts_code.eq(params["ts_code"]).all():
                raise ValueError("wrong symbol")
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            raise data_error() from exc
        return frame

    def universe(self) -> list[Stock]:
        self._token()
        key = "universe:tushare:v1"
        cached = self.store.get(key, max_age=86400)
        if cached:
            return [Stock.model_validate(row) for row in cached]
        stocks = []
        for exchange in ("SSE", "SZSE", "BSE"):
            frame = self._query("stock_basic", "ts_code,name,market,list_date", exchange=exchange, list_status="L")
            if len(frame) >= 6000:
                raise AnalysisError("universe_truncated", "Tushare 股票名单达到单次行数上限，停止使用不完整名单。", "Tushare stock list reached its row cap; refusing an incomplete universe.")
            for row in frame.to_dict("records"):
                try:
                    symbol = normalize_symbol(row["ts_code"])
                except AnalysisError:
                    continue
                name = str(row["name"])
                board = {"科创板": "star", "创业板": "chinext", "北交所": "beijing"}.get(row["market"], "main")
                stocks.append(Stock(symbol=symbol, name=name, market=symbol[-2:], board=board, listed=row["list_date"], special="ST" in name.upper() or "退" in name))
        if not stocks or len({stock.symbol for stock in stocks}) != len(stocks):
            raise data_error()
        self.store.put(key, [stock.model_dump() for stock in stocks])
        return stocks

    def calendar(self) -> list[date]:
        self._token()
        today = datetime.now(SHANGHAI).date()
        key = f"calendar:tushare:{today.year}:{self.settings.history_years}"
        cached = self.store.get(key, max_age=86400)
        if not cached:
            frame = self._history("trade_cal", "cal_date,is_open", date(today.year - self.settings.history_years - 2, 1, 1), date(today.year + 1, 12, 31), exchange="SSE")
            if not frame.is_open.astype(str).isin(["0", "1"]).all():
                raise data_error()
            cached = sorted(pd.to_datetime(frame.loc[frame.is_open.astype(str) == "1", "cal_date"], format="%Y%m%d").dt.strftime("%Y-%m-%d").tolist())
            if not cached:
                raise data_error()
            self.store.put(key, cached)
        return [date.fromisoformat(day) for day in cached]

    def bars(self, symbol: str, as_of: date) -> tuple[pd.DataFrame, str]:
        self._token()
        key = f"bars:tushare:qfq:v1:{symbol}:{as_of}:{self.settings.history_years}"
        cached = self.store.get(key)
        if cached:
            frame = validate_bars(pd.DataFrame(cached["bars"]), as_of)
            frame.attrs["notices"] = cached["notices"]
            return frame, "Tushare Pro / daily + adj_factor"
        start = as_of - timedelta(days=365 * self.settings.history_years + 3)
        daily = self._history("daily", "ts_code,trade_date,open,high,low,close,vol,amount", start, as_of, ts_code=symbol)
        factors = self._history("adj_factor", "ts_code,trade_date,adj_factor", start, as_of, ts_code=symbol)
        notices = []
        try:
            basic = self._history("daily_basic", "ts_code,trade_date,turnover_rate", start, as_of, ts_code=symbol)
        except AnalysisError as exc:
            basic = pd.DataFrame(columns=["trade_date", "turnover_rate"])
            notices.append({"code": exc.code, "zh": exc.zh, "en": exc.en})
        frame = normalize_daily(daily, factors, basic, as_of)
        frame.attrs["notices"] = notices
        # 只缓存完整、无可选接口失败的快照，避免权限恢复后仍命中失败结果。
        if frame.date.iloc[-1] == as_of.isoformat() and not notices and frame.turnover.notna().all():
            self.store.put(key, {"bars": records(frame), "notices": notices})
        return frame, "Tushare Pro / daily + adj_factor"

    def metadata(self, stock: Stock) -> Stock:
        self._token()
        key = f"metadata:tushare:sw2021:{stock.symbol}"
        cached = self.store.get(key, max_age=86400)
        if cached:
            return stock.model_copy(update=cached)
        # stock_basic.industry 与申万指数口径不同，必须取申万成分接口的代码。
        frame = self._query("index_member_all", "ts_code,l1_code,l1_name,in_date", ts_code=stock.symbol, is_new="Y")
        if frame.empty:
            return stock.model_copy(update={"industry": None})
        if not frame.ts_code.eq(stock.symbol).all():
            raise data_error()
        codes = frame.l1_code.dropna().unique()
        if len(codes) != 1 or not re.fullmatch(r"\d{6}\.SI", str(codes[0])):
            raise data_error()
        metadata = {"industry": str(codes[0])}
        self.store.put(key, metadata)
        return stock.model_copy(update=metadata)

    def _index(self, api: str, symbol: str, as_of: date) -> pd.DataFrame:
        self._token()
        key = f"index:tushare:{api}:v1:{symbol}:{as_of}:{self.settings.history_years}"
        cached = self.store.get(key)
        if cached:
            return validate_bars(pd.DataFrame(cached), as_of)
        frame = self._history(api, "ts_code,trade_date,open,high,low,close,vol,amount", as_of - timedelta(days=365 * self.settings.history_years + 3), as_of, ts_code=symbol)
        try:
            frame["date"] = pd.to_datetime(frame.trade_date, format="%Y%m%d", errors="raise").dt.strftime("%Y-%m-%d")
            frame["volume"] = pd.to_numeric(frame.vol, errors="raise") * (10000 if api == "sw_daily" else 100)
            frame["amount"] = pd.to_numeric(frame.amount, errors="raise") * (10000 if api == "sw_daily" else 1000)
        except (AttributeError, TypeError, ValueError) as exc:
            raise data_error() from exc
        frame = validate_bars(frame, as_of)
        if frame.date.iloc[-1] == as_of.isoformat():
            self.store.put(key, records(frame))
        return frame

    def benchmark(self, as_of: date) -> pd.DataFrame:
        return self._index("index_daily", "000300.SH", as_of)

    def industry(self, name: str, as_of: date) -> pd.DataFrame:
        if not re.fullmatch(r"\d{6}\.SI", name):
            raise data_error()
        return self._index("sw_daily", name, as_of)
