"""
Market Structure Levels — VWAP, Pivots, ORB, POC, ATR.

Computes all key price levels from bar data:
- VWAP with standard deviation bands
- HOD/LOD from intraday bars
- Pivot points (classic)
- Opening Range (5-min, 15-min)
- Point of Control (POC) from volume profile
- ATR (Average True Range)
- Realized volatility
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
import math
import statistics


@dataclass
class MarketLevels:
    """Key price levels for market structure analysis."""
    # Price
    current_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0
    prev_close: float = 0.0

    # Day range
    hod: float = 0.0
    lod: float = 0.0

    # Previous day
    prev_high: float = 0.0
    prev_low: float = 0.0

    # VWAP
    vwap: float = 0.0
    vwap_upper_1: float = 0.0  # +1σ
    vwap_lower_1: float = 0.0  # -1σ
    vwap_upper_2: float = 0.0  # +2σ
    vwap_lower_2: float = 0.0  # -2σ
    vwap_upper_3: float = 0.0  # +3σ
    vwap_lower_3: float = 0.0  # -3σ

    # Opening Range (first 5 min, 15 min, and 30 min)
    orb_5_high: float = 0.0
    orb_5_low: float = 0.0
    orb_15_high: float = 0.0
    orb_15_low: float = 0.0
    orb_30_high: float = 0.0
    orb_30_low: float = 0.0
    orb_30_width: float = 0.0  # Range width — narrow = explosive breakout potential

    # Pivot points (classic)
    pivot: float = 0.0
    r1: float = 0.0
    r2: float = 0.0
    r3: float = 0.0
    s1: float = 0.0
    s2: float = 0.0
    s3: float = 0.0

    # Volume profile
    poc: float = 0.0  # Point of Control (highest volume price)
    value_area_high: float = 0.0
    value_area_low: float = 0.0

    # Volatility
    atr_1m: float = 0.0   # 1-minute ATR
    atr_5m: float = 0.0   # 5-minute ATR
    realized_vol: float = 0.0  # Intraday realized volatility

    # v7: Chart indicators (computed from bars, fed into confluence factors)
    ema_9: float = 0.0      # 9-period EMA
    ema_21: float = 0.0     # 21-period EMA
    sma_50: float = 0.0     # 50-period SMA
    bb_upper: float = 0.0   # Bollinger upper band (20, 2σ)
    bb_lower: float = 0.0   # Bollinger lower band
    bb_mid: float = 0.0     # Bollinger middle (SMA20)
    avg_bb_width_pct: float = 0.0  # Average BB width as % of mid
    recent_bars: Optional[list] = field(default=None, repr=False)  # Last N 1-minute bars

    # Multi-day reference levels (computed from daily bars)
    weekly_high: float = 0.0     # 5-day high
    weekly_low: float = 0.0      # 5-day low
    monthly_high: float = 0.0    # 20-day high
    monthly_low: float = 0.0     # 20-day low
    yearly_high: float = 0.0     # Max available daily bars high
    yearly_low: float = 0.0      # Max available daily bars low
    prev_day_vwap: float = 0.0   # Previous day's typical price (magnet level)

    def to_dict(self) -> Dict[str, float]:
        return {k: round(v, 4) if isinstance(v, float) else v
                for k, v in self.__dict__.items()}

    def nearby_levels(self, price: float, threshold: float = 0.15) -> List[Tuple[str, float]]:
        """Find all key levels within threshold dollars of price."""
        nearby = []
        level_names = {
            "VWAP": self.vwap, "VWAP+1σ": self.vwap_upper_1,
            "VWAP-1σ": self.vwap_lower_1, "VWAP+2σ": self.vwap_upper_2,
            "VWAP-2σ": self.vwap_lower_2,
            "HOD": self.hod, "LOD": self.lod,
            "Prev Close": self.prev_close,
            "Prev High": self.prev_high, "Prev Low": self.prev_low,
            "ORB 5m High": self.orb_5_high, "ORB 5m Low": self.orb_5_low,
            "ORB 15m High": self.orb_15_high, "ORB 15m Low": self.orb_15_low,
            "ORB 30m High": self.orb_30_high, "ORB 30m Low": self.orb_30_low,
            "Pivot": self.pivot, "R1": self.r1, "R2": self.r2,
            "S1": self.s1, "S2": self.s2,
            "POC": self.poc,
            "VA High": self.value_area_high, "VA Low": self.value_area_low,
            "Week High": self.weekly_high, "Week Low": self.weekly_low,
            "Month High": self.monthly_high, "Month Low": self.monthly_low,
            "Year High": self.yearly_high, "Year Low": self.yearly_low,
            "Prev VWAP": self.prev_day_vwap,
        }
        for name, level in level_names.items():
            if level > 0 and abs(price - level) <= threshold:
                nearby.append((name, level))
        return sorted(nearby, key=lambda x: abs(price - x[1]))


def compute_market_levels(
    bars_1m: List[Dict],
    bars_daily: List[Dict],
    quote: Dict,
) -> MarketLevels:
    """
    Compute all market structure levels from available bar data.

    Args:
        bars_1m: Today's 1-minute bars [{time, open, high, low, close, volume, vwap}, ...]
        bars_daily: Recent daily bars (need at least 2 for prev day)
        quote: Current quote {bid, ask, last, prev_close}
    """
    levels = MarketLevels()

    # Current price from quote
    levels.current_price = quote.get("last", 0) or quote.get("price", 0)
    levels.bid = quote.get("bid", 0)
    levels.ask = quote.get("ask", 0)
    levels.spread = round(levels.ask - levels.bid, 4) if levels.bid and levels.ask else 0
    levels.prev_close = quote.get("prev_close", 0)

    # ── Previous day levels from daily bars ──
    if bars_daily and len(bars_daily) >= 2:
        prev_day = bars_daily[-2]  # Second-to-last is previous completed day
        levels.prev_high = prev_day.get("high", 0)
        levels.prev_low = prev_day.get("low", 0)
        if not levels.prev_close:
            levels.prev_close = prev_day.get("close", 0)

    # ── Classic pivot points from prev day ──
    if levels.prev_high and levels.prev_low and levels.prev_close:
        high, low, close = levels.prev_high, levels.prev_low, levels.prev_close
        levels.pivot = round((high + low + close) / 3, 2)
        levels.r1 = round(2 * levels.pivot - low, 2)
        levels.s1 = round(2 * levels.pivot - high, 2)
        levels.r2 = round(levels.pivot + (high - low), 2)
        levels.s2 = round(levels.pivot - (high - low), 2)
        levels.r3 = round(high + 2 * (levels.pivot - low), 2)
        levels.s3 = round(low - 2 * (high - levels.pivot), 2)

    # ── Multi-day reference levels ──
    if bars_daily:
        daily_highs = [b.get("high", 0) for b in bars_daily if b.get("high", 0) > 0]
        daily_lows = [b.get("low", 0) for b in bars_daily if b.get("low", 0) > 0]

        if len(daily_highs) >= 5:
            levels.weekly_high = max(daily_highs[-5:])
            levels.weekly_low = min(daily_lows[-5:])

        if len(daily_highs) >= 20:
            levels.monthly_high = max(daily_highs[-20:])
            levels.monthly_low = min(daily_lows[-20:])

        if len(daily_highs) >= 50:
            levels.yearly_high = max(daily_highs)
            levels.yearly_low = min(daily_lows)

        # Previous day's typical price as VWAP proxy (magnet level)
        if len(bars_daily) >= 2:
            pd = bars_daily[-2]
            h, l, c = pd.get("high", 0), pd.get("low", 0), pd.get("close", 0)
            if h > 0 and l > 0 and c > 0:
                levels.prev_day_vwap = round((h + l + c) / 3, 4)

    if not bars_1m:
        return levels

    # ── HOD / LOD from intraday bars ──
    highs = [b.get("high", 0) for b in bars_1m if b.get("high", 0) > 0]
    lows = [b.get("low", 0) for b in bars_1m if b.get("low", 0) > 0]
    if highs:
        levels.hod = max(highs)
    if lows:
        levels.lod = min(lows)

    # ── VWAP with standard deviation bands ──
    cum_vol = 0
    cum_tp_vol = 0.0
    cum_tp2_vol = 0.0
    for bar in bars_1m:
        v = bar.get("volume", 0)
        if v <= 0:
            continue
        # Typical price = (H + L + C) / 3
        tp = (bar.get("high", 0) + bar.get("low", 0) + bar.get("close", 0)) / 3
        cum_vol += v
        cum_tp_vol += tp * v
        cum_tp2_vol += (tp ** 2) * v

    if cum_vol > 0:
        levels.vwap = round(cum_tp_vol / cum_vol, 4)
        # Standard deviation of VWAP
        variance = (cum_tp2_vol / cum_vol) - (levels.vwap ** 2)
        std = math.sqrt(max(0, variance))
        levels.vwap_upper_1 = round(levels.vwap + std, 4)
        levels.vwap_lower_1 = round(levels.vwap - std, 4)
        levels.vwap_upper_2 = round(levels.vwap + 2 * std, 4)
        levels.vwap_lower_2 = round(levels.vwap - 2 * std, 4)
        levels.vwap_upper_3 = round(levels.vwap + 3 * std, 4)
        levels.vwap_lower_3 = round(levels.vwap - 3 * std, 4)

    # ── Opening Range (5-min and 15-min) ──
    # First 5 bars = first 5 minutes, first 15 bars = first 15 minutes
    if len(bars_1m) >= 5:
        orb5 = bars_1m[:5]
        levels.orb_5_high = max(b.get("high", 0) for b in orb5)
        levels.orb_5_low = min(b.get("low", 999999) for b in orb5)
    if len(bars_1m) >= 15:
        orb15 = bars_1m[:15]
        levels.orb_15_high = max(b.get("high", 0) for b in orb15)
        levels.orb_15_low = min(b.get("low", 999999) for b in orb15)
    if len(bars_1m) >= 30:
        orb30 = bars_1m[:30]
        levels.orb_30_high = max(b.get("high", 0) for b in orb30)
        levels.orb_30_low = min(b.get("low", 999999) for b in orb30)
        levels.orb_30_width = levels.orb_30_high - levels.orb_30_low

    # ── Volume Profile — POC and Value Area ──
    price_vol: Dict[float, int] = {}
    total_vol = 0
    for bar in bars_1m:
        v = bar.get("volume", 0)
        if v <= 0:
            continue
        # Use VWAP or close as representative price, rounded to $0.25
        price_key = round(bar.get("vwap", bar.get("close", 0)) * 4) / 4
        price_vol[price_key] = price_vol.get(price_key, 0) + v
        total_vol += v

    if price_vol:
        # POC = price level with highest volume
        levels.poc = max(price_vol, key=price_vol.get)

        # Value Area = 70% of volume centered on POC
        sorted_levels = sorted(price_vol.items(), key=lambda x: -x[1])
        va_target = total_vol * 0.70
        va_vol = 0
        va_prices = []
        for price, vol in sorted_levels:
            va_vol += vol
            va_prices.append(price)
            if va_vol >= va_target:
                break
        if va_prices:
            levels.value_area_high = max(va_prices)
            levels.value_area_low = min(va_prices)

    # ── ATR (Average True Range) ──
    if len(bars_1m) >= 14:
        trs = []
        for i in range(1, len(bars_1m)):
            high = bars_1m[i].get("high", 0)
            low = bars_1m[i].get("low", 0)
            pc = bars_1m[i - 1].get("close", 0)
            tr = max(high - low, abs(high - pc), abs(low - pc))
            trs.append(tr)
        if trs:
            levels.atr_1m = round(statistics.mean(trs[-14:]), 4)
            # Estimate 5m ATR as ~2.2× 1m ATR (sqrt(5) scaling)
            levels.atr_5m = round(levels.atr_1m * 2.236, 4)

    # ── Realized volatility (annualized from 1m returns) ──
    if len(bars_1m) >= 20:
        returns = []
        for i in range(1, len(bars_1m)):
            c1 = bars_1m[i - 1].get("close", 0)
            c2 = bars_1m[i].get("close", 0)
            if c1 > 0 and c2 > 0:
                returns.append(math.log(c2 / c1))
        if len(returns) >= 10:
            std_ret = statistics.stdev(returns)
            levels.realized_vol = round(std_ret * math.sqrt(98280) * 100, 2)

    # ── v7: Chart indicators — EMA, SMA, Bollinger Bands ──
    closes = [b.get("close", 0) for b in bars_1m if b.get("close", 0) > 0]

    if len(closes) >= 9:
        levels.ema_9 = round(_compute_ema(closes, 9), 4)
    if len(closes) >= 21:
        levels.ema_21 = round(_compute_ema(closes, 21), 4)
    if len(closes) >= 50:
        levels.sma_50 = round(statistics.mean(closes[-50:]), 4)

    # Bollinger Bands (20-period SMA ± 2σ)
    if len(closes) >= 20:
        bb_window = closes[-20:]
        levels.bb_mid = round(statistics.mean(bb_window), 4)
        bb_std = statistics.stdev(bb_window)
        levels.bb_upper = round(levels.bb_mid + 2 * bb_std, 4)
        levels.bb_lower = round(levels.bb_mid - 2 * bb_std, 4)

        # Average BB width over last 50 bars (or as many as available)
        if len(closes) >= 40:
            widths = []
            for i in range(20, min(len(closes), 70)):
                w = closes[i - 20:i]
                m = statistics.mean(w)
                s = statistics.stdev(w)
                if m > 0:
                    widths.append(((4 * s) / m) * 100)
            if widths:
                levels.avg_bb_width_pct = round(statistics.mean(widths), 4)

    # Store last 10 bars for candle pattern analysis
    if len(bars_1m) >= 5:
        levels.recent_bars = bars_1m[-10:]

    return levels


def _compute_ema(data: List[float], period: int) -> float:
    """Compute Exponential Moving Average."""
    if len(data) < period:
        return 0.0
    multiplier = 2.0 / (period + 1)
    ema = statistics.mean(data[:period])  # Seed with SMA
    for val in data[period:]:
        ema = (val - ema) * multiplier + ema
    return ema
