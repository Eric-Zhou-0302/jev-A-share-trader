from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import talib as ta

from .calendar import complete_periods
from .models import Evidence, Metric

VERSION = "indicators-2"


def finite(value) -> float | None:
    return round(float(value), 6) if value is not None and np.isfinite(value) else None


def divide(a, b):
    return np.divide(a, b, out=np.full_like(np.asarray(a, dtype=float), np.nan), where=np.asarray(b) != 0)


def supertrend(high, low, close, period=10, multiplier=3.0):
    atr = ta.ATR(high, low, close, timeperiod=period)
    upper, lower = (high + low) / 2 + multiplier * atr, (high + low) / 2 - multiplier * atr
    direction = np.full(len(close), np.nan)
    line = np.full(len(close), np.nan)
    for i in range(period, len(close)):
        if i == period:
            direction[i], line[i] = 1, lower[i]
            continue
        if upper[i] >= upper[i - 1] and close[i - 1] <= upper[i - 1]:
            upper[i] = upper[i - 1]
        if lower[i] <= lower[i - 1] and close[i - 1] >= lower[i - 1]:
            lower[i] = lower[i - 1]
        direction[i] = (1 if close[i] > upper[i] else -1) if direction[i - 1] == -1 else (-1 if close[i] < lower[i] else 1)
        line[i] = lower[i] if direction[i] == 1 else upper[i]
    return line, direction


def kdj(high, low, close, period=9):
    upper, lower = ta.MAX(high, timeperiod=period), ta.MIN(low, timeperiod=period)
    rsv = divide(close - lower, upper - lower) * 100
    k, d = np.full(len(close), np.nan), np.full(len(close), np.nan)
    previous_k = previous_d = 50.0
    for i in range(period - 1, len(close)):
        value = rsv[i] if np.isfinite(rsv[i]) else 50.0
        previous_k = previous_k * 2 / 3 + value / 3
        previous_d = previous_d * 2 / 3 + previous_k / 3
        k[i], d[i] = previous_k, previous_d
    return k, d, 3 * k - 2 * d


def pivots(values: np.ndarray, kind: str, radius: int = 2) -> list[int]:
    result = []
    for i in range(radius, len(values) - radius):
        window = values[i - radius:i + radius + 1]
        extreme = np.max(window) if kind == "high" else np.min(window)
        if values[i] == extreme and np.sum(window == extreme) == 1:
            result.append(i)
    return result


@dataclass
class TechnicalState:
    metrics: list[Metric]
    evidence: list[Evidence]
    series: dict[str, np.ndarray]
    charts: dict[str, list[dict]]
    groups_available: list[str]


def compute(frame: pd.DataFrame, sessions: list[date], as_of: date, benchmark: pd.DataFrame | None = None, industry: pd.DataFrame | None = None, breadth: dict | None = None) -> TechnicalState:
    frame = frame.loc[frame.date <= as_of.isoformat()].copy().reset_index(drop=True)
    o, h, low, c, v = (frame[key].to_numpy(dtype=float) for key in ("open", "high", "low", "close", "volume"))
    dates = frame.date.tolist()
    current_date = dates[-1]
    series: dict[str, np.ndarray] = {}
    metrics, evidence = [], []

    def add(key, group, values, label=None, unit=""):
        values = np.asarray(values, dtype=float)
        series[key] = values
        metrics.append(Metric(key=key, group=group, label=label or key.upper(), value=finite(values[-1]), unit=unit))
        return values

    def fact(key, group, polarity, zh, en, values=None, when=None, strength=1.0):
        evidence.append(Evidence(id=key, group=group, polarity=polarity, zh=zh, en=en, date=when or current_date, metrics=values or {}, strength=strength))

    for period in (5, 10, 20, 60, 120, 250):
        add(f"sma_{period}", "trend", ta.SMA(c, timeperiod=period))
        add(f"ema_{period}", "trend", ta.EMA(c, timeperiod=period))
    add("wma_20", "trend", ta.WMA(c, timeperiod=20))
    add("hma_20", "trend", ta.WMA(2 * ta.WMA(c, timeperiod=10) - ta.WMA(c, timeperiod=20), timeperiod=4))
    add("kama_30", "trend", ta.KAMA(c, timeperiod=30))
    add("adx_14", "trend", ta.ADX(h, low, c, timeperiod=14))
    add("plus_di_14", "trend", ta.PLUS_DI(h, low, c, timeperiod=14))
    add("minus_di_14", "trend", ta.MINUS_DI(h, low, c, timeperiod=14))
    down, up = ta.AROON(h, low, timeperiod=25)
    add("aroon_up", "trend", up)
    add("aroon_down", "trend", down)
    add("sar", "trend", ta.SAR(h, low, acceleration=.02, maximum=.2))
    st, direction = supertrend(h, low, c)
    add("supertrend", "trend", st)
    add("supertrend_direction", "trend", direction)
    add("slope_20_pct", "trend", divide(ta.LINEARREG_SLOPE(c, timeperiod=20), c) * 100, unit="%")
    for period in (20, 60):
        ma = series[f"sma_{period}"]
        position = (c[-1] / ma[-1] - 1) * 100
        rising = ma[-1] > ma[-6]
        polarity = 1 if position > 0 and rising else -1 if position < 0 and not rising else 0
        fact(f"ma_position_{period}", "trend", polarity,
             f"收盘价较 MA{period} {'高' if position >= 0 else '低'} {abs(position):.2f}%，均线近五日{'上行' if rising else '走平或下行'}。",
             f"Close is {abs(position):.2f}% {'above' if position >= 0 else 'below'} MA{period}; the average is {'rising' if rising else 'flat or falling'} over five sessions.",
             {"distance_pct": finite(position), "rising": str(rising)})
    aligned_up = series["sma_5"][-1] > series["sma_10"][-1] > series["sma_20"][-1] > series["sma_60"][-1]
    aligned_down = series["sma_5"][-1] < series["sma_10"][-1] < series["sma_20"][-1] < series["sma_60"][-1]
    fact("ma_alignment", "trend", 1 if aligned_up else -1 if aligned_down else 0,
         "MA5/10/20/60 呈" + ("多头排列。" if aligned_up else "空头排列。" if aligned_down else "交错排列。"),
         "MA5/10/20/60 show " + ("bullish alignment." if aligned_up else "bearish alignment." if aligned_down else "mixed alignment."))
    adx = series["adx_14"][-1]
    di_sign = 1 if series["plus_di_14"][-1] > series["minus_di_14"][-1] else -1
    fact("directional_strength", "trend", di_sign if adx >= 25 else 0, f"ADX 为 {adx:.1f}，DMI 方向{'向上' if di_sign > 0 else '向下'}。", f"ADX is {adx:.1f}; DMI direction is {'upward' if di_sign > 0 else 'downward'}.", {"adx": finite(adx)})

    macd, signal, hist = ta.MACD(c, fastperiod=12, slowperiod=26, signalperiod=9)
    for key, arr in (("macd", macd), ("macd_signal", signal), ("macd_hist", hist)):
        add(key, "momentum", arr)
    for period in (6, 14, 24):
        add(f"rsi_{period}", "momentum", ta.RSI(c, timeperiod=period))
    k, d, j = kdj(h, low, c)
    for key, arr in (("kdj_k", k), ("kdj_d", d), ("kdj_j", j)):
        add(key, "momentum", arr)
    sk, sd = ta.STOCH(h, low, c, fastk_period=9, slowk_period=3, slowd_period=3)
    add("stoch_k", "momentum", sk)
    add("stoch_d", "momentum", sd)
    add("cci_20", "momentum", ta.CCI(h, low, c, timeperiod=20))
    add("willr_14", "momentum", ta.WILLR(h, low, c, timeperiod=14))
    add("roc_10", "momentum", ta.ROC(c, timeperiod=10), unit="%")
    add("mom_10", "momentum", ta.MOM(c, timeperiod=10))
    add("trix_15", "momentum", ta.TRIX(c, timeperiod=15), unit="%")
    change = pd.Series(c).diff()
    smooth_change = change.ewm(span=25, adjust=False, min_periods=25).mean().ewm(span=13, adjust=False, min_periods=13).mean()
    smooth_abs = change.abs().ewm(span=25, adjust=False, min_periods=25).mean().ewm(span=13, adjust=False, min_periods=13).mean()
    add("tsi", "momentum", divide(smooth_change, smooth_abs) * 100)
    rsi = series["rsi_14"][-1]
    fact("rsi_state", "momentum", 1 if 50 < rsi < 70 else -1 if rsi < 40 or rsi >= 75 else 0,
         f"RSI14 为 {rsi:.1f}，" + ("处于超买区。" if rsi >= 70 else "处于超卖区。" if rsi <= 30 else "位于常规区间。"),
         f"RSI14 is {rsi:.1f}, " + ("in overbought territory." if rsi >= 70 else "in oversold territory." if rsi <= 30 else "within its normal range."), {"rsi": finite(rsi)})
    fact("macd_state", "momentum", 1 if macd[-1] > signal[-1] and macd[-1] > 0 else -1 if macd[-1] < signal[-1] and macd[-1] < 0 else 0,
         f"MACD 位于零轴{'上' if macd[-1] >= 0 else '下'}方，柱体近三日{'增加' if hist[-1] > hist[-4] else '减小或走平'}。",
         f"MACD is {'above' if macd[-1] >= 0 else 'below'} zero; its histogram has {'increased' if hist[-1] > hist[-4] else 'fallen or flattened'} over three sessions.", {"macd": finite(macd[-1]), "signal": finite(signal[-1]), "hist": finite(hist[-1])})
    for key, left, right, group in (("macd_cross", macd, signal, "momentum"), ("kdj_cross", k, d, "momentum"), ("ma_cross", series["sma_5"], series["sma_20"], "trend")):
        diff = left - right
        for i in range(len(c) - 1, max(1, len(c) - 6), -1):
            if diff[i] * diff[i - 1] < 0:
                sign = 1 if diff[i] > 0 else -1
                fact(key, group, sign, f"{key.split('_')[0].upper()} 最近出现{'向上' if sign > 0 else '向下'}交叉。", f"A recent {'bullish' if sign > 0 else 'bearish'} {key.split('_')[0].upper()} crossover was detected.", when=dates[i], strength=.8)
                break

    for period in (5, 20, 60):
        add(f"volume_ma_{period}", "volume", ta.SMA(v, timeperiod=period), unit="shares")
    previous_mean = pd.Series(v).shift(1).rolling(20).mean().to_numpy()
    ratio = add("relative_volume_20", "volume", divide(v, previous_mean), unit="x")
    add("obv", "volume", ta.OBV(c, v), unit="shares")
    add("mfi_14", "volume", ta.MFI(h, low, c, v, timeperiod=14))
    add("ad", "volume", ta.AD(h, low, c, v))
    add("adosc", "volume", ta.ADOSC(h, low, c, v, fastperiod=3, slowperiod=10))
    multiplier = np.nan_to_num(divide(2 * c - h - low, h - low))
    add("cmf_20", "volume", divide(pd.Series(multiplier * v).rolling(20).sum(), pd.Series(v).rolling(20).sum()))
    pvt = pd.Series(c).pct_change().fillna(0).to_numpy() * v
    add("pvt", "volume", np.cumsum(pvt))
    add("vwma_20", "volume", divide(pd.Series(c * v).rolling(20).sum(), pd.Series(v).rolling(20).sum()))
    add("turnover", "volume", frame.turnover.to_numpy(dtype=float), unit="%")
    price_change = (c[-1] / c[-2] - 1) * 100
    vol_ratio = ratio[-1]
    if np.isfinite(vol_ratio):
        fact("volume_confirmation", "volume", (1 if price_change > 0 else -1) if vol_ratio >= 1.3 and price_change != 0 else 0,
             f"日成交量为此前 20 日均量的 {vol_ratio:.2f} 倍，当日涨跌幅 {price_change:+.2f}%。",
             f"Daily volume is {vol_ratio:.2f}× the previous 20-session average; the close changed {price_change:+.2f}%.", {"volume_ratio": finite(vol_ratio), "return_pct": finite(price_change)})
    obv_direction = np.sign(series["obv"][-1] - series["obv"][-21])
    price_direction = np.sign(c[-1] - c[-21])
    confirmation = int(price_direction) if price_direction == obv_direction else 0
    fact("obv_confirmation", "volume", confirmation,
         "近 20 日价格与 OBV " + ("同向上行。" if confirmation > 0 else "同向下行。" if confirmation < 0 else "缺乏同向变化确认。"),
         "Price and OBV over 20 sessions " + ("both increased." if confirmation > 0 else "both decreased." if confirmation < 0 else "lack confirmation from aligned changes."))

    atr = add("atr_14", "volatility", ta.ATR(h, low, c, timeperiod=14))
    natr = add("natr_14", "volatility", ta.NATR(h, low, c, timeperiod=14), unit="%")
    upper, middle, lower = ta.BBANDS(c, timeperiod=20, nbdevup=2, nbdevdn=2)
    for key, arr in (("bb_upper", upper), ("bb_middle", middle), ("bb_lower", lower)):
        add(key, "volatility", arr)
    width = add("bb_width_pct", "volatility", divide(upper - lower, middle) * 100, unit="%")
    add("bb_percent_b", "volatility", divide(c - lower, upper - lower))
    kc_mid = ta.EMA(c, timeperiod=20)
    add("kc_upper", "volatility", kc_mid + 2 * atr)
    add("kc_lower", "volatility", kc_mid - 2 * atr)
    add("donchian_high_20", "volatility", ta.MAX(h, timeperiod=20))
    add("donchian_low_20", "volatility", ta.MIN(low, timeperiod=20))
    log_returns = np.log(pd.Series(c) / pd.Series(c).shift(1))
    add("realized_vol_20", "volatility", log_returns.rolling(20).std(ddof=1) * np.sqrt(252) * 100, unit="%")
    squeeze = upper[-1] < series["kc_upper"][-1] and lower[-1] > series["kc_lower"][-1]
    fact("volatility_state", "volatility", 0, f"ATR14 占收盘价 {natr[-1]:.2f}%，布林带宽 {width[-1]:.2f}%。", f"ATR14 is {natr[-1]:.2f}% of close; Bollinger bandwidth is {width[-1]:.2f}%.", {"natr": finite(natr[-1]), "bandwidth": finite(width[-1])})
    fact("squeeze", "volatility", 0, "布林带" + ("处于 Keltner 通道内，波动收缩。" if squeeze else "未形成 Keltner 挤压。"), "Bollinger bands " + ("are inside the Keltner channel: volatility is compressed." if squeeze else "are not inside the Keltner channel."), {"squeeze": str(squeeze)})

    prev_high = pd.Series(h).shift(1).rolling(60).max().to_numpy()
    prev_low = pd.Series(low).shift(1).rolling(60).min().to_numpy()
    add("distance_high_60_pct", "structure", (divide(c, prev_high) - 1) * 100, unit="%")
    add("distance_low_60_pct", "structure", (divide(c, prev_low) - 1) * 100, unit="%")
    breakout = 1 if c[-1] > prev_high[-1] else -1 if c[-1] < prev_low[-1] else 0
    fact("range_position", "structure", breakout,
         "收盘价" + ("突破此前 60 日高点。" if breakout > 0 else "跌破此前 60 日低点。" if breakout < 0 else f"位于此前 60 日区间内，距上沿 {(prev_high[-1] / c[-1] - 1) * 100:.2f}%。"),
         "Close " + ("broke above the previous 60-session high." if breakout > 0 else "broke below the previous 60-session low." if breakout < 0 else f"is within the previous 60-session range, {(prev_high[-1] / c[-1] - 1) * 100:.2f}% below its upper boundary."))
    for direction_name, arr, kind in (("support", low, "low"), ("resistance", h, "high")):
        points = pivots(arr[-120:], kind)
        if len(points) >= 2:
            a, b = points[-2:]
            line_slope = (arr[-120:][b] - arr[-120:][a]) / (b - a)
            line = arr[-120:][b] + line_slope * (119 - b)
            relative = (c[-1] / line - 1) * 100 if line else 0
            fact(f"trendline_{direction_name}", "structure", 1 if line_slope > 0 and relative > 0 else -1 if line_slope < 0 and relative < 0 else 0,
                 f"最近两个已确认{'低' if kind == 'low' else '高'}点形成的结构线{'上倾' if line_slope > 0 else '下倾或走平'}。",
                 f"The structural line through the last two confirmed {'lows' if kind == 'low' else 'highs'} is {'rising' if line_slope > 0 else 'falling or flat'}.", {"distance_pct": finite(relative)}, strength=.7)
    for i in range(len(c) - 1, max(60, len(c) - 15), -1):
        boundary = prev_high[i]
        if c[i] > boundary and c[i - 1] <= prev_high[i - 1] and i < len(c) - 1:
            held = c[-1] >= boundary
            fact("breakout_retest", "structure", 1 if held else -1,
                 "近期突破后，收盘价" + ("仍维持在原区间上沿之上。" if held else "已退回原区间，突破未能维持。"),
                 "After a recent breakout, close " + ("remains above the former range." if held else "has returned inside the former range; the breakout did not hold."), when=dates[i])
            break
    for i in range(len(c) - 1, max(1, len(c) - 20), -1):
        if low[i] > h[i - 1] and low[i:].min() > h[i - 1]:
            fact("open_gap", "structure", 1, "近 20 日存在尚未完全回补的向上缺口。", "An upside gap in the last 20 sessions remains unfilled.", when=dates[i], strength=.6)
            break
        if h[i] < low[i - 1] and h[i:].max() < low[i - 1]:
            fact("open_gap", "structure", -1, "近 20 日存在尚未完全回补的向下缺口。", "A downside gap in the last 20 sessions remains unfilled.", when=dates[i], strength=.6)
            break

    candle_names = {"CDLDOJI": ("十字星", "Doji"), "CDLHAMMER": ("锤头", "Hammer"), "CDLINVERTEDHAMMER": ("倒锤头", "Inverted hammer"), "CDLENGULFING": ("吞没", "Engulfing"), "CDLMORNINGSTAR": ("早晨之星", "Morning star"), "CDLEVENINGSTAR": ("黄昏之星", "Evening star"), "CDL3WHITESOLDIERS": ("三白兵", "Three white soldiers"), "CDL3BLACKCROWS": ("三只乌鸦", "Three black crows"), "CDLHARAMI": ("孕线", "Harami"), "CDLSHOOTINGSTAR": ("流星", "Shooting star"), "CDLDARKCLOUDCOVER": ("乌云盖顶", "Dark cloud cover"), "CDLPIERCING": ("刺透", "Piercing"), "CDLHANGINGMAN": ("上吊线", "Hanging man"), "CDLSPINNINGTOP": ("纺锤线", "Spinning top")}
    for key, (zh, en) in candle_names.items():
        pattern = add(key.lower(), "candles", getattr(ta, key)(o, h, low, c), label=f"{zh} / {en}")
        hits = np.where(pattern[-3:] != 0)[0]
        if len(hits):
            index = len(c) - 3 + hits[-1]
            polarity = 0 if key in ("CDLDOJI", "CDLSPINNINGTOP") else int(np.sign(pattern[index]))
            fact(key.lower(), "candles", polarity, f"识别到{zh}形态，需结合趋势与量价背景。", f"A {en.lower()} pattern was detected; interpret it in trend and volume context.", when=dates[index], strength=.6)
    body = add("body_pct", "candles", divide(c - o, o) * 100, unit="%")
    add("upper_shadow_pct", "candles", divide(h - np.maximum(o, c), c) * 100, unit="%")
    add("lower_shadow_pct", "candles", divide(np.minimum(o, c) - low, c) * 100, unit="%")
    fact("candle_body", "candles", int(np.sign(body[-1])) if abs(body[-1]) > 1 else 0,
         f"最新日 K 线实体涨跌 {body[-1]:+.2f}%，上影 {series['upper_shadow_pct'][-1]:.2f}%，下影 {series['lower_shadow_pct'][-1]:.2f}%。",
         f"The latest candle body is {body[-1]:+.2f}%, with an upper shadow of {series['upper_shadow_pct'][-1]:.2f}% and a lower shadow of {series['lower_shadow_pct'][-1]:.2f}%.", {"body_pct": finite(body[-1])})

    for label, arr in (("RSI", series["rsi_14"]), ("MACD", macd), ("OBV", series["obv"])):
        for kind in ("high", "low"):
            points = [i for i in pivots(c, kind) if i >= len(c) - 60]
            if len(points) < 2 or points[-1] < len(c) - 20:
                continue
            a, b = points[-2:]
            divergent = (c[b] > c[a] and arr[b] < arr[a]) if kind == "high" else (c[b] < c[a] and arr[b] > arr[a])
            if divergent:
                sign = -1 if kind == "high" else 1
                fact(f"divergence_{label}_{kind}", "volume" if label == "OBV" else "momentum", sign,
                     f"已确认的价格拐点与 {label} 形成{'顶' if kind == 'high' else '底'}背离候选。",
                     f"Confirmed price pivots and {label} show a candidate {'bearish' if kind == 'high' else 'bullish'} divergence.", when=dates[b], strength=.7)

    charts = {}
    for frequency, ma_periods, prefix in (("weekly", (10, 20), "周"), ("monthly", (6, 12), "月")):
        aggregate = complete_periods(frame, sessions, as_of, frequency)
        charts[frequency] = aggregate.to_dict("records")
        if len(aggregate) < max(ma_periods) + 1:
            continue
        prices = aggregate.close.to_numpy(dtype=float)
        fast, slow = (ta.SMA(prices, timeperiod=period)[-1] for period in ma_periods)
        sign = 1 if prices[-1] > fast > slow else -1 if prices[-1] < fast < slow else 0
        metrics.extend([Metric(key=f"{frequency}_sma_{period}", group="multitimeframe", label=f"{prefix}线 SMA{period} / {frequency.title()} SMA{period}", value=finite(value)) for period, value in zip(ma_periods, (fast, slow), strict=True)])
        fact(f"{frequency}_trend", "multitimeframe", sign,
             f"已完成{prefix}线的收盘与 MA{ma_periods[0]}/{ma_periods[1]} 呈" + ("多头排列。" if sign > 0 else "空头排列。" if sign < 0 else "交错状态。"),
             f"Completed {frequency} close and MA{ma_periods[0]}/{ma_periods[1]} show " + ("bullish alignment." if sign > 0 else "bearish alignment." if sign < 0 else "mixed alignment."), when=str(aggregate.date.iloc[-1]))
    for label, reference in (("benchmark", benchmark), ("industry", industry)):
        if reference is None or reference.empty:
            continue
        joined = frame[["date", "close"]].merge(reference[["date", "close"]], on="date", how="left", suffixes=("", "_reference"))
        if joined.close_reference.tail(61).isna().any():
            continue
        for period in (5, 20, 60):
            own = c[-1] / c[-period - 1] - 1
            ref = joined.close_reference.iloc[-1] / joined.close_reference.iloc[-period - 1] - 1
            excess = (own - ref) * 100
            metrics.append(Metric(key=f"relative_{label}_{period}", group="relative", label=f"RS {label.upper()} {period}D", value=finite(excess), unit="pp"))
            if period == 20:
                fact(f"relative_{label}", "relative", 1 if excess > 1 else -1 if excess < -1 else 0,
                     f"近 20 个交易日较{'沪深300' if label == 'benchmark' else '所属行业指数'}{'多涨' if excess >= 0 else '少涨'} {abs(excess):.2f} 个百分点。",
                     f"Over 20 sessions, the stock {'outperformed' if excess >= 0 else 'underperformed'} {'CSI 300' if label == 'benchmark' else 'its industry index'} by {abs(excess):.2f} percentage points.", {"excess_pp": finite(excess)})
        returns = joined[["close", "close_reference"]].pct_change().tail(60)
        correlation = returns.corr().iloc[0, 1]
        metrics.append(Metric(key=f"correlation_{label}_60", group="relative", label=f"CORREL {label.upper()} 60D", value=finite(correlation)))
        ref_prices = joined.close_reference.to_numpy(dtype=float)
        ma20, ma60 = ref_prices[-20:].mean(), ref_prices[-60:].mean()
        sign = 1 if ref_prices[-1] > ma20 > ma60 else -1 if ref_prices[-1] < ma20 < ma60 else 0
        fact(f"{label}_trend", "relative", sign,
             f"{'沪深300' if label == 'benchmark' else '行业指数'}收盘与 MA20/60 呈" + ("多头排列。" if sign > 0 else "空头排列。" if sign < 0 else "交错状态。"),
             f"{'CSI 300' if label == 'benchmark' else 'The industry index'} close and MA20/60 show " + ("bullish alignment." if sign > 0 else "bearish alignment." if sign < 0 else "mixed alignment."))
    if breadth and breadth.get("as_of") == current_date and breadth.get("coverage", 0) >= .8:
        share = breadth["above_ma20_pct"]
        fact("market_breadth", "relative", 1 if share >= 60 else -1 if share <= 40 else 0,
             f"已取得日线的市场样本中，{share:.1f}% 位于 MA20 上方，覆盖率 {breadth['coverage']:.1%}。",
             f"{share:.1f}% of the available market sample is above MA20; universe coverage is {breadth['coverage']:.1%}.", {"above_ma20_pct": share, "coverage": breadth["coverage"]})

    for key, arr in series.items():
        charts[key] = [{"time": day, "value": finite(value)} for day, value in zip(dates[-300:], arr[-300:], strict=True) if finite(value) is not None]
    return TechnicalState(metrics=metrics, evidence=evidence, series=series, charts=charts, groups_available=sorted({item.group for item in evidence}))
