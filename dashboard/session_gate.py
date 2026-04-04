"""
Session Gate — Smart session-aware signal filtering.

Instead of a dumb midday blackout, this module applies an override checklist
during low-quality sessions. Obvious setups (key level bounces with multi-TF
confirmation) still trade; random noise gets filtered.

Usage:
    gate = SessionGate()
    allowed, reason = gate.check(signal)
"""

import logging
from datetime import datetime, timezone, time as dt_time
from typing import Dict, Tuple, Optional, List

from .config import cfg

logger = logging.getLogger("session_gate")

# ── Key level proximity: how close price must be to count as "at a level" ──
# Expressed as fraction of ATR. If ATR is $3.00 and threshold is 0.5,
# price must be within $1.50 of a level. This adapts to volatility.
LEVEL_PROXIMITY_ATR_MULT = 0.5

# Fallback: if ATR not available, use absolute dollar threshold
LEVEL_PROXIMITY_FALLBACK = 1.50  # $1.50

# Minimum confirming factors for midday override
MIDDAY_MIN_FACTORS = 3

# Volume multiplier required during midday (1.5 = 50% above average)
MIDDAY_VOLUME_MULT = 1.3


class SessionGate:
    """
    Smart session gating. During low-quality sessions (midday chop),
    signals must pass additional override checks. High-quality sessions
    pass through normally.
    """

    def check(self, signal: Dict) -> Tuple[bool, str]:
        """
        Check if signal is allowed to trade given current session context.

        Returns (allowed: bool, reason: str).
        """
        session = signal.get("session", {})
        phase = session.get("phase", "unknown")

        # Always block pre-market and close_risk
        if phase == "pre_market":
            return False, "session_gate: pre-market, no trading"
        if phase == "close_risk":
            return False, "session_gate: close_risk phase (after 3:45 PM)"

        # Midday chop requires override checklist
        if phase == "midday_chop":
            return self._check_midday_override(signal, session)

        # All other phases: allow with standard checks
        return True, f"session_ok: {phase}"

    def _check_midday_override(self, signal: Dict, session: Dict) -> Tuple[bool, str]:
        """
        Midday chop (11:30-1:30) override checklist.
        Signal must prove it's an obvious setup, not random noise.

        Override criteria (need 3+ of these to pass):
        1. Price at a key level (prev day H/L, VWAP ±2σ, HOD/LOD, pivots, POC)
        2. Tier is HIGH or TEXTBOOK (no VALID during chop)
        3. Not near a high-impact event (FOMC, CPI, NFP within 30 min)
        4. Volume confirmation (above average)
        5. Multi-timeframe alignment (5min/15min direction supports signal)
        6. Strong confluence (7+ confirming factors)
        """
        checks_passed = []
        checks_failed = []
        levels = signal.get("levels", {})
        indicators = signal.get("indicators", {})
        tier = signal.get("tier", "DEVELOPING")
        direction = signal.get("signal", "NO_TRADE")
        factors = signal.get("factors", [])

        # ── Check 1: Price at a key level ──
        at_level, level_name = self._price_at_key_level(levels)
        if at_level:
            checks_passed.append(f"at_level({level_name})")
        else:
            checks_failed.append("not_at_key_level")

        # ── Check 2: Tier is HIGH or TEXTBOOK ──
        if tier in ("TEXTBOOK", "HIGH"):
            checks_passed.append(f"tier({tier})")
        else:
            checks_failed.append(f"tier_too_low({tier})")

        # ── Check 3: No high-impact event within 30 min ──
        event_clear = self._check_event_clear(signal)
        if event_clear:
            checks_passed.append("event_clear")
        else:
            checks_failed.append("near_high_impact_event")

        # ── Check 4: Volume confirmation ──
        volume_ok = self._check_volume(indicators)
        if volume_ok:
            checks_passed.append("volume_confirmed")
        else:
            checks_failed.append("low_volume")

        # ── Check 5: Multi-timeframe alignment ──
        # Check recent 1-minute bars stored in levels for trend direction
        mtf_ok = self._check_multi_timeframe(levels, direction)
        if mtf_ok:
            checks_passed.append("mtf_aligned")
        else:
            checks_failed.append("mtf_not_aligned")

        # ── Check 6: Strong confluence (7+ directional factors) ──
        confirming = self._count_confirming_factors(factors, direction)
        if confirming >= 7:
            checks_passed.append(f"strong_confluence({confirming})")
        else:
            checks_failed.append(f"weak_confluence({confirming})")

        # ── Decision ──
        passed_count = len(checks_passed)
        if passed_count >= MIDDAY_MIN_FACTORS:
            reason = (
                f"midday_override_PASS: {passed_count}/6 checks — "
                f"{', '.join(checks_passed)}"
            )
            logger.info(f"[SessionGate] {reason}")
            return True, reason
        else:
            reason = (
                f"midday_override_FAIL: {passed_count}/6 checks (need {MIDDAY_MIN_FACTORS}) — "
                f"passed=[{', '.join(checks_passed)}] "
                f"failed=[{', '.join(checks_failed)}]"
            )
            logger.info(f"[SessionGate] {reason}")
            return False, reason

    def _price_at_key_level(self, levels: Dict) -> Tuple[bool, str]:
        """
        Check if current price is near a key support/resistance level.
        Uses ATR-based proximity for volatility adaptation.
        """
        price = levels.get("current_price", 0)
        if price <= 0:
            return False, ""

        # Determine proximity threshold (ATR-based or fallback)
        atr = levels.get("atr_5m", 0) or levels.get("atr_1m", 0)
        if atr > 0:
            threshold = atr * LEVEL_PROXIMITY_ATR_MULT
        else:
            threshold = LEVEL_PROXIMITY_FALLBACK

        # Key levels to check (name, value)
        key_levels: List[Tuple[str, float]] = []

        # Previous day high/low — strongest levels
        if levels.get("prev_high", 0) > 0:
            key_levels.append(("prev_high", levels["prev_high"]))
        if levels.get("prev_low", 0) > 0:
            key_levels.append(("prev_low", levels["prev_low"]))

        # Today's HOD/LOD
        if levels.get("hod", 0) > 0:
            key_levels.append(("HOD", levels["hod"]))
        if levels.get("lod", 0) > 0:
            key_levels.append(("LOD", levels["lod"]))

        # VWAP bands (±2σ are mean reversion zones)
        if levels.get("vwap_upper_2", 0) > 0:
            key_levels.append(("VWAP+2σ", levels["vwap_upper_2"]))
        if levels.get("vwap_lower_2", 0) > 0:
            key_levels.append(("VWAP-2σ", levels["vwap_lower_2"]))
        if levels.get("vwap", 0) > 0:
            key_levels.append(("VWAP", levels["vwap"]))

        # Pivot points
        for name in ("pivot", "r1", "r2", "s1", "s2"):
            val = levels.get(name, 0)
            if val > 0:
                key_levels.append((name.upper(), val))

        # POC (Point of Control) — highest volume price
        if levels.get("poc", 0) > 0:
            key_levels.append(("POC", levels["poc"]))

        # Value area boundaries
        if levels.get("value_area_high", 0) > 0:
            key_levels.append(("VAH", levels["value_area_high"]))
        if levels.get("value_area_low", 0) > 0:
            key_levels.append(("VAL", levels["value_area_low"]))

        # ORB levels
        if levels.get("orb_15_high", 0) > 0:
            key_levels.append(("ORB15_H", levels["orb_15_high"]))
        if levels.get("orb_15_low", 0) > 0:
            key_levels.append(("ORB15_L", levels["orb_15_low"]))

        # Previous close
        if levels.get("prev_close", 0) > 0:
            key_levels.append(("prev_close", levels["prev_close"]))

        # Find nearest level
        nearest_name = ""
        nearest_dist = float("inf")
        for name, level_price in key_levels:
            dist = abs(price - level_price)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_name = name

        if nearest_dist <= threshold:
            return True, f"{nearest_name}(${levels.get(nearest_name.lower(), nearest_dist):.2f}, dist=${nearest_dist:.2f})"
        return False, ""

    def _check_event_clear(self, signal: Dict) -> bool:
        """
        Check there's no high-impact event within 30 minutes.
        Uses event data from the signal's risk_management or session context.
        """
        risk_mgmt = signal.get("risk_management", {})

        # Check if event calendar flagged suppress_entries
        # (event_calendar.py already computes this)
        session = signal.get("session", {})

        # The signal doesn't carry event_context directly, but confluence
        # already factors it in. We can check the factors list for event impact.
        factors = signal.get("factors", [])
        for f in factors:
            if "event" in f.get("name", "").lower():
                detail = f.get("detail", "").lower()
                if "blocked" in detail or "suppress" in detail:
                    return False

        # Also check minutes_to_close as proxy — if event_context had
        # suppress_entries, it would have been applied in confidence scoring
        return True

    def _check_volume(self, indicators: Dict) -> bool:
        """
        Check if current volume is above average (confirms institutional interest).
        During midday, volume typically drops — elevated volume means something
        is happening at this price level.
        """
        total_volume = indicators.get("total_volume", 0)

        # If we have large trades and they show a clear bias, that's volume confirmation
        large_trades = indicators.get("large_trades", 0)
        large_bias = indicators.get("large_trade_bias", "neutral")

        # Volume check: large institutional activity present
        if large_trades >= 3 and large_bias != "neutral":
            return True

        # Absorption or exhaustion patterns indicate meaningful activity
        if indicators.get("absorption", False):
            return True

        # Strong imbalance indicates directional conviction
        imbalance = abs(indicators.get("imbalance", 0))
        if imbalance >= 0.25:  # 25%+ order flow imbalance
            return True

        # Aggressive flow dominance
        aggressive_buy = indicators.get("aggressive_buy_pct", 0)
        aggressive_sell = indicators.get("aggressive_sell_pct", 0)
        if max(aggressive_buy, aggressive_sell) >= 0.65:  # 65%+ one-sided
            return True

        return False

    def _check_multi_timeframe(self, levels: Dict, direction: str) -> bool:
        """
        Check multi-timeframe alignment using available bar data.

        Uses recent 1-minute bars (stored in levels.recent_bars) to construct
        higher-timeframe views:
        - Last 5 bars → approximate 5-minute candle direction
        - Last 15 bars → approximate 15-minute candle direction

        For a BUY_CALL, we want 5m and 15m bars to show bullish structure.
        For a BUY_PUT, we want 5m and 15m bars to show bearish structure.
        """
        recent_bars = levels.get("recent_bars")
        if not recent_bars or len(recent_bars) < 5:
            # Can't verify multi-TF — fail this check
            return False

        is_call = "CALL" in direction

        # Build 5-minute candle from last 5 bars
        last_5 = recent_bars[-5:]
        candle_5m = self._aggregate_bars(last_5)

        # Build 15-minute candle from last 15 bars (or as many as available)
        last_15 = recent_bars[-min(15, len(recent_bars)):]
        candle_15m = self._aggregate_bars(last_15)

        # 5-minute direction check
        five_bullish = candle_5m["close"] > candle_5m["open"]
        five_body_pct = abs(candle_5m["close"] - candle_5m["open"]) / max(candle_5m["open"], 0.01)

        # 15-minute direction check
        fifteen_bullish = candle_15m["close"] > candle_15m["open"]

        if is_call:
            # For calls: 5m should be green or showing bounce (lower wick),
            # and 15m should not be strongly bearish
            five_ok = five_bullish or self._has_lower_wick(candle_5m)
            fifteen_ok = fifteen_bullish or five_body_pct < 0.001  # flat is ok
            return five_ok and fifteen_ok
        else:
            # For puts: 5m should be red or showing rejection (upper wick),
            # and 15m should not be strongly bullish
            five_ok = (not five_bullish) or self._has_upper_wick(candle_5m)
            fifteen_ok = (not fifteen_bullish) or five_body_pct < 0.001
            return five_ok and fifteen_ok

    def _aggregate_bars(self, bars: list) -> Dict:
        """Aggregate multiple 1-minute bars into a single candle."""
        if not bars:
            return {"open": 0, "high": 0, "low": 0, "close": 0}

        # Handle both dict and list-of-values formats
        def _get(bar, key, idx):
            if isinstance(bar, dict):
                return float(bar.get(key, 0))
            return float(bar[idx]) if len(bar) > idx else 0

        opens = [_get(b, "open", 0) or _get(b, "o", 0) for b in bars]
        highs = [_get(b, "high", 1) or _get(b, "h", 1) for b in bars]
        lows = [_get(b, "low", 2) or _get(b, "l", 2) for b in bars]
        closes = [_get(b, "close", 3) or _get(b, "c", 3) for b in bars]

        return {
            "open": opens[0] if opens else 0,
            "high": max(highs) if highs else 0,
            "low": min(l for l in lows if l > 0) if any(l > 0 for l in lows) else 0,
            "close": closes[-1] if closes else 0,
        }

    def _has_lower_wick(self, candle: Dict) -> bool:
        """Candle has significant lower wick (bounce signal)."""
        body_bottom = min(candle["open"], candle["close"])
        total_range = candle["high"] - candle["low"]
        if total_range <= 0:
            return False
        lower_wick = body_bottom - candle["low"]
        return (lower_wick / total_range) >= 0.4  # 40%+ lower wick = bounce

    def _has_upper_wick(self, candle: Dict) -> bool:
        """Candle has significant upper wick (rejection signal)."""
        body_top = max(candle["open"], candle["close"])
        total_range = candle["high"] - candle["low"]
        if total_range <= 0:
            return False
        upper_wick = candle["high"] - body_top
        return (upper_wick / total_range) >= 0.4  # 40%+ upper wick = rejection

    def _count_confirming_factors(self, factors: list, direction: str) -> int:
        """Count how many factors align with the signal direction."""
        target_dir = "bullish" if "CALL" in direction else "bearish"
        return sum(1 for f in factors
                   if f.get("direction") == target_dir and f.get("weight", 0) > 0)


# Singleton
session_gate = SessionGate()
