"""
Agent 1: Price & Order Flow Agent (Rule-Based)

Analyzes real-time order flow from Alpaca SIP ticks:
  - Cumulative Volume Delta (CVD) trend and divergence
  - Aggressive vs passive order flow
  - Large block trade detection
  - Volume exhaustion / absorption at key levels
  - Bid/ask imbalance

Polling: Every 10 seconds (fastest agent — price is king)
Data source: Alpaca SIP trades via /api/orderflow/trades/recent
"""

import aiohttp
import logging
from .base import BaseAgent, AgentVerdict, Direction
from ..config import cfg

logger = logging.getLogger(__name__)
API_BASE = cfg.DASHBOARD_BASE_URL


class PriceFlowAgent(BaseAgent):
    name = "PriceFlow"
    poll_interval = 10
    stale_seconds = 30

    def __init__(self):
        super().__init__()
        self._prev_cvd = 0.0
        self._prev_price = 0.0

    async def analyze(self) -> AgentVerdict:
        """Fetch recent trades and analyze order flow patterns."""
        async with aiohttp.ClientSession() as session:
            # Fetch recent trades (last 5 min)
            resp = await session.get(
                f"{API_BASE}/api/orderflow/trades/recent?symbol=SPY&limit=500&minutes=5",
                timeout=aiohttp.ClientTimeout(total=5),
            )
            if resp.status != 200:
                return self._neutral("Failed to fetch trade data")
            data = await resp.json()

        trades = data.get("trades", [])
        if len(trades) < 20:
            return self._neutral("Insufficient trade data")

        # ── CVD analysis ──
        cvd = 0
        buy_vol = sell_vol = 0
        aggressive_buy = aggressive_sell = 0
        large_buy = large_sell = 0
        large_count = 0

        for t in trades:
            size = t.get("s", 0)
            side = t.get("side", "neutral")

            if side == "buy":
                cvd += size
                buy_vol += size
                aggressive_buy += size  # All buys lift the ask
            elif side == "sell":
                cvd -= size
                sell_vol += size
                aggressive_sell += size

            # Large trades (5000+ shares for SPY)
            if size >= 5000:
                large_count += 1
                if side == "buy":
                    large_buy += size
                else:
                    large_sell += size

        total_vol = buy_vol + sell_vol
        if total_vol == 0:
            return self._neutral("No volume")

        imbalance = buy_vol / total_vol  # 0-1

        # ── CVD trend (compare to previous cycle) ──
        cvd_delta = cvd - self._prev_cvd
        self._prev_cvd = cvd

        # ── Price trend ──
        prices = [t.get("p", 0) for t in trades if t.get("p", 0) > 0]
        current_price = prices[-1] if prices else 0
        price_change = current_price - self._prev_price if self._prev_price > 0 else 0
        self._prev_price = current_price

        # ── Volume exhaustion ──
        half = len(trades) // 2
        first_vol = sum(t.get("s", 0) for t in trades[:half])
        second_vol = sum(t.get("s", 0) for t in trades[half:])
        vol_ratio = second_vol / first_vol if first_vol > 0 else 1.0
        exhausted = vol_ratio < 0.6

        # ── Build verdict ──
        factors = []
        direction = Direction.NEUTRAL
        confidence = 0.0

        # CVD signal
        if cvd_delta > total_vol * 0.1:
            factors.append(f"CVD rising strongly (+{cvd_delta:,.0f})")
            direction = Direction.BULLISH
            confidence += 0.25
        elif cvd_delta < -total_vol * 0.1:
            factors.append(f"CVD falling strongly ({cvd_delta:,.0f})")
            direction = Direction.BEARISH
            confidence += 0.25

        # Price-CVD divergence
        if price_change < -0.02 and cvd_delta > 0:
            factors.append(f"Bullish divergence: price down ${price_change:.2f} but CVD rising")
            direction = Direction.BULLISH
            confidence += 0.20
        elif price_change > 0.02 and cvd_delta < 0:
            factors.append(f"Bearish divergence: price up ${price_change:.2f} but CVD falling")
            direction = Direction.BEARISH
            confidence += 0.20

        # Imbalance
        if imbalance > 0.65:
            factors.append(f"Buy imbalance {imbalance:.0%}")
            if direction == Direction.NEUTRAL:
                direction = Direction.BULLISH
            confidence += 0.15
        elif imbalance < 0.35:
            factors.append(f"Sell imbalance {imbalance:.0%}")
            if direction == Direction.NEUTRAL:
                direction = Direction.BEARISH
            confidence += 0.15

        # Large trades
        if large_count >= 2:
            if large_buy > large_sell * 1.5:
                factors.append(f"{large_count} large blocks ({large_buy:,.0f} shares) — buy bias")
                if direction == Direction.NEUTRAL:
                    direction = Direction.BULLISH
                confidence += 0.15
            elif large_sell > large_buy * 1.5:
                factors.append(f"{large_count} large blocks ({large_sell:,.0f} shares) — sell bias")
                if direction == Direction.NEUTRAL:
                    direction = Direction.BEARISH
                confidence += 0.15

        # Exhaustion
        if exhausted:
            factors.append(f"Volume exhaustion (ratio {vol_ratio:.2f})")
            confidence += 0.10

        confidence = min(1.0, confidence)

        reasoning = " | ".join(factors) if factors else "No strong order flow pattern"

        return AgentVerdict(
            agent_name=self.name,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            factors=factors,
            data={
                "cvd": cvd, "cvd_delta": cvd_delta,
                "imbalance": round(imbalance, 3),
                "total_volume": total_vol,
                "large_trades": large_count,
                "current_price": current_price,
                "exhausted": exhausted,
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
