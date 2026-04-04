"""
Agent 4: Market Structure Agent (Rule-Based)

Analyzes price structure and key levels:
  - VWAP position and band interactions
  - HOD/LOD proximity and breakout/rejection
  - Opening Range status
  - Pivot point support/resistance
  - Session timing and quality
  - Trend identification from multi-timeframe bars

Uses the signal engine's compute_market_levels() for calculations.

Polling: Every 15 seconds
Data source: /api/signals/levels (server-side computed)
"""

import aiohttp
import logging
from .base import BaseAgent, AgentVerdict, Direction
from ..config import cfg

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    from datetime import timezone, timedelta
    ET = timezone(timedelta(hours=-4))

logger = logging.getLogger(__name__)
API_BASE = cfg.DASHBOARD_BASE_URL


class MarketStructureAgent(BaseAgent):
    name = "Structure"
    poll_interval = 15
    stale_seconds = 45

    def __init__(self):
        super().__init__()
        self._prev_price = 0.0
        self._trend_prices: list = []  # Rolling price window for trend

    async def analyze(self) -> AgentVerdict:
        """Analyze market structure levels and determine bias."""
        # Fetch computed levels from signal engine
        async with aiohttp.ClientSession() as session:
            resp = await session.get(
                f"{API_BASE}/api/signals/levels",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            if resp.status != 200:
                return self._neutral("Failed to fetch market levels")
            data = await resp.json()

        levels = data.get("levels", {})
        session_data = data.get("session", {})

        price = levels.get("current_price", 0)
        if price <= 0:
            return self._neutral("No price data")

        # Track rolling prices for trend detection
        self._trend_prices.append(price)
        if len(self._trend_prices) > 30:
            self._trend_prices = self._trend_prices[-30:]

        factors = []
        bullish_weight = 0.0
        bearish_weight = 0.0

        # ── 1. VWAP Position ──
        vwap = levels.get("vwap", 0)
        vwap_u1 = levels.get("vwap_upper_1", 0)
        vwap_l1 = levels.get("vwap_lower_1", 0)
        vwap_u2 = levels.get("vwap_upper_2", 0)
        vwap_l2 = levels.get("vwap_lower_2", 0)

        if vwap > 0:
            if price > vwap_u1 and vwap_u1 > 0:
                factors.append(f"Price above VWAP+1σ (${vwap_u1:.2f}) — strong bullish")
                bullish_weight += 0.20
            elif price > vwap:
                factors.append(f"Price above VWAP (${vwap:.2f}) — bullish bias")
                bullish_weight += 0.10
            elif price < vwap_l1 and vwap_l1 > 0:
                factors.append(f"Price below VWAP-1σ (${vwap_l1:.2f}) — strong bearish")
                bearish_weight += 0.20
            elif price < vwap:
                factors.append(f"Price below VWAP (${vwap:.2f}) — bearish bias")
                bearish_weight += 0.10

            # VWAP band extremes (mean reversion zones)
            if vwap_u2 > 0 and price >= vwap_u2:
                factors.append(f"At VWAP+2σ (${vwap_u2:.2f}) — overextended, potential reversal")
                bearish_weight += 0.15
            elif vwap_l2 > 0 and price <= vwap_l2:
                factors.append(f"At VWAP-2σ (${vwap_l2:.2f}) — overextended, potential bounce")
                bullish_weight += 0.15

        # ── 2. HOD/LOD Position ──
        hod = levels.get("hod", 0)
        lod = levels.get("lod", 0)
        atr = levels.get("atr_1m", 0.05)

        if hod > 0 and lod > 0:
            day_range = hod - lod
            position_in_range = (price - lod) / day_range if day_range > 0 else 0.5

            if position_in_range > 0.85:
                factors.append(f"Near HOD (${hod:.2f}) — {position_in_range:.0%} of range")
                # Could be breakout or rejection — depends on momentum
                if len(self._trend_prices) >= 5 and self._trend_prices[-1] > self._trend_prices[-5]:
                    bullish_weight += 0.15  # Momentum toward HOD = bullish
                else:
                    bearish_weight += 0.10  # Stalling at HOD = bearish
            elif position_in_range < 0.15:
                factors.append(f"Near LOD (${lod:.2f}) — {position_in_range:.0%} of range")
                if len(self._trend_prices) >= 5 and self._trend_prices[-1] < self._trend_prices[-5]:
                    bearish_weight += 0.15
                else:
                    bullish_weight += 0.10

        # ── 3. Opening Range ──
        orb_high = levels.get("orb_5_high", 0)
        orb_low = levels.get("orb_5_low", 0)
        phase = session_data.get("phase", "")

        if orb_high > 0 and orb_low > 0:
            if price > orb_high and phase in ("opening_drive", "morning_trend"):
                factors.append(f"Above ORB high (${orb_high:.2f}) — bullish breakout")
                bullish_weight += 0.15
            elif price < orb_low and phase in ("opening_drive", "morning_trend"):
                factors.append(f"Below ORB low (${orb_low:.2f}) — bearish breakout")
                bearish_weight += 0.15

        # ── 4. Pivot Points ──
        pivot = levels.get("pivot", 0)
        r1 = levels.get("r1", 0)
        s1 = levels.get("s1", 0)

        if pivot > 0:
            if price > r1 and r1 > 0:
                factors.append(f"Above R1 (${r1:.2f}) — strong bullish")
                bullish_weight += 0.10
            elif price > pivot:
                factors.append(f"Above Pivot (${pivot:.2f})")
                bullish_weight += 0.05
            elif price < s1 and s1 > 0:
                factors.append(f"Below S1 (${s1:.2f}) — strong bearish")
                bearish_weight += 0.10
            elif price < pivot:
                factors.append(f"Below Pivot (${pivot:.2f})")
                bearish_weight += 0.05

        # ── 5. Trend detection from rolling prices ──
        if len(self._trend_prices) >= 10:
            first_avg = sum(self._trend_prices[:5]) / 5
            last_avg = sum(self._trend_prices[-5:]) / 5
            trend_change = last_avg - first_avg

            if trend_change > atr * 2:
                factors.append(f"Strong uptrend (+${trend_change:.2f} over {len(self._trend_prices)} samples)")
                bullish_weight += 0.15
            elif trend_change < -atr * 2:
                factors.append(f"Strong downtrend (${trend_change:.2f} over {len(self._trend_prices)} samples)")
                bearish_weight += 0.15

        # ── 6. Previous day close ──
        prev_close = levels.get("prev_close", 0)
        if prev_close > 0 and price > 0:
            gap = price - prev_close
            gap_pct = (gap / prev_close) * 100
            if abs(gap_pct) > 0.3:
                if gap > 0:
                    factors.append(f"Gap up +{gap_pct:.2f}% from prev close ${prev_close:.2f}")
                else:
                    factors.append(f"Gap down {gap_pct:.2f}% from prev close ${prev_close:.2f}")

        # ── 7. Session quality ──
        quality = session_data.get("session_quality", 0.5)
        if quality < 0.3:
            factors.append(f"Low-quality session ({phase.replace('_', ' ')}) — reduce sizing")
        past_hard_stop = session_data.get("past_hard_stop", False)
        if past_hard_stop:
            factors.append("Past 3:00 PM ET — 0DTE hard stop active")
            bearish_weight = 0
            bullish_weight = 0

        # ── Aggregate ──
        if not factors:
            return self._neutral("No clear structure signal")

        net = bullish_weight - bearish_weight
        if net > 0.1:
            direction = Direction.BULLISH
            confidence = min(0.85, bullish_weight)
        elif net < -0.1:
            direction = Direction.BEARISH
            confidence = min(0.85, bearish_weight)
        else:
            direction = Direction.NEUTRAL
            confidence = 0.0

        # Scale by session quality
        confidence *= (0.5 + quality * 0.5)

        return AgentVerdict(
            agent_name=self.name,
            direction=direction,
            confidence=min(1.0, confidence),
            reasoning=" | ".join(factors[:4]),
            factors=factors,
            data={
                "price": price,
                "vwap": vwap,
                "hod": hod,
                "lod": lod,
                "phase": phase,
                "quality": quality,
                "levels": levels,
            },
            stale_after_seconds=self.stale_seconds,
        )

    def _neutral(self, reason: str) -> AgentVerdict:
        return AgentVerdict(
            agent_name=self.name,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            reasoning=reason,
            stale_after_seconds=self.stale_seconds,
        )
