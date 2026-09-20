from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from .models import AnalysisError

SHANGHAI = ZoneInfo("Asia/Shanghai")


def latest_completed(sessions: list[date], now: datetime | None = None) -> date:
    now = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    if not sessions or max(sessions) < now.date() - timedelta(days=14):
        raise AnalysisError("calendar_stale", "交易日历不可用或已过期。", "Trading calendar is unavailable or stale.")
    # 收盘只决定可用日期上限；当日是否齐备仍需校验实际行情。
    eligible = [day for day in sessions if day < now.date() or (day == now.date() and now.time() >= time(15, 0))]
    if not eligible:
        raise AnalysisError("calendar_empty", "没有已完成的交易日。", "No completed trading session is available.")
    return max(eligible)


def complete_periods(frame: pd.DataFrame, sessions: list[date], as_of: date, frequency: str) -> pd.DataFrame:
    source = frame.copy().set_index(pd.to_datetime(frame["date"]))
    source = source.loc[source.index.date <= as_of]
    period_code = "W-FRI" if frequency == "weekly" else "M"
    groups = source.index.to_period(period_code)
    calendar_periods: dict = {}
    for session in sessions:
        period = pd.Timestamp(session).to_period(period_code)
        calendar_periods[period] = max(calendar_periods.get(period, session), session)
    rows = []
    for period, block in source.groupby(groups):
        # 只使用确认闭合的周期；本周／本月未完成时不把局部数据当整根 K 线。
        period_end = calendar_periods.get(period)
        if not period_end or period_end > as_of:
            continue
        if period.end_time.date() > max(sessions):
            continue
        rows.append({"date": block["date"].iloc[-1], "open": block.open.iloc[0], "high": block.high.max(), "low": block.low.min(), "close": block.close.iloc[-1], "volume": block.volume.sum(), "amount": block.amount.sum()})
    return pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume", "amount"])
