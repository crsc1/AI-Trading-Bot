"""
Agent 3: Sentiment Agent (Hybrid — Social + Market Indicators)

Monitors market-wide sentiment from multiple free sources:
  - Fear & Greed Index (alternative.me — free, no auth)
  - VIX level and regime (via Alpaca bars)
  - Put/Call ratio from options snapshot
  - Reddit r/wallstreetbets sentiment (via keyword scraping)

Polling: Every 60 seconds (sentiment changes slowly)
"""

import aiohttp
import logging
from .base import BaseAgent, AgentVerdict, Direction
from ..config import cfg

logger = logging.getLogger(__name__)
API_BASE = cfg.DASHBOARD_BASE_URL


class SentimentAgent(BaseAgent):
    name = "Sentiment"
    poll_interval = 60
    stale_seconds = 180  # Sentiment valid for 3 minutes

    def __init__(self):
        super().__init__()
        self._last_vix = 0.0

    async def analyze(self) -> AgentVerdict:
        """Aggregate sentiment from multiple sources."""
        factors = []
        bullish_weight = 0.0
        bearish_weight = 0.0

        # 1. Fear & Greed Index
        fg = await self._fetch_fear_greed()
        if fg is not None:
            if fg >= 75:
                factors.append(f"Extreme Greed ({fg}) — contrarian bearish signal")
                bearish_weight += 0.15
            elif fg >= 55:
                factors.append(f"Greed ({fg}) — bullish sentiment")
                bullish_weight += 0.10
            elif fg <= 25:
                factors.append(f"Extreme Fear ({fg}) — contrarian bullish signal")
                bullish_weight += 0.15
            elif fg <= 45:
                factors.append(f"Fear ({fg}) — bearish sentiment")
                bearish_weight += 0.10

        # 2. IV Rank (replaces VIX proxy — uses actual option IV history)
        try:
            from dashboard.api_routes import get_iv_percentile
            iv_data = await get_iv_percentile("SPY", 0.20)  # current_iv placeholder; function fetches live
            iv_rank = iv_data.get("iv_rank", 0)
            iv_pct = iv_data.get("iv_percentile", 0)
            if iv_rank > 0.80:
                factors.append(f"IV Rank {iv_rank:.0%} — options expensive, contrarian bullish")
                bullish_weight += 0.15
            elif iv_rank > 0.60:
                factors.append(f"IV Rank {iv_rank:.0%} — elevated volatility")
                bearish_weight += 0.10
            elif iv_rank < 0.20:
                factors.append(f"IV Rank {iv_rank:.0%} — low vol, complacency")
                bullish_weight += 0.10
            else:
                factors.append(f"IV Rank {iv_rank:.0%} — normal range")
        except Exception:
            # Fallback to VIXY proxy if ThetaData unavailable
            vix = await self._fetch_vix()
            if vix > 0:
                if vix > 30:
                    factors.append(f"VIX proxy {vix:.1f} — extreme fear")
                    bearish_weight += 0.20
                elif vix < 14:
                    factors.append(f"VIX proxy {vix:.1f} — low vol")
                    bullish_weight += 0.10

        # 3. Put/Call ratio from our options data
        pcr = await self._fetch_pcr()
        if pcr > 0:
            if pcr > 1.2:
                factors.append(f"P/C ratio {pcr:.2f} — heavy put buying (bearish)")
                bearish_weight += 0.15
            elif pcr > 0.9:
                factors.append(f"P/C ratio {pcr:.2f} — slightly bearish")
                bearish_weight += 0.05
            elif pcr < 0.6:
                factors.append(f"P/C ratio {pcr:.2f} — heavy call buying (bullish)")
                bullish_weight += 0.15
            elif pcr < 0.8:
                factors.append(f"P/C ratio {pcr:.2f} — slightly bullish")
                bullish_weight += 0.05

        if not factors:
            return self._neutral("No sentiment data available")

        # Determine direction
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

        reasoning = " | ".join(factors)

        return AgentVerdict(
            agent_name=self.name,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            factors=factors,
            data={
                "fear_greed": fg,
                "vix": vix,
                "pcr": pcr,
                "bullish_weight": round(bullish_weight, 2),
                "bearish_weight": round(bearish_weight, 2),
            },
            stale_after_seconds=self.stale_seconds,
        )

    async def _fetch_fear_greed(self) -> int | None:
        """Fetch CNN Fear & Greed index from alternative.me (free, no auth)."""
        try:
            url = "https://api.alternative.me/fng/?limit=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    items = data.get("data", [])
                    if items:
                        return int(items[0].get("value", 0))
        except Exception as e:
            logger.debug(f"Fear & Greed error: {e}")
        return None

    async def _fetch_vix(self) -> float:
        """Fetch VIX from our internal bars endpoint (Alpaca data)."""
        try:
            async with aiohttp.ClientSession() as session:
                # Try to get VIX via Alpaca — VIX is an index, may need special handling
                # Use Yahoo finance fallback through a simple quote
                url = f"{API_BASE}/api/market?symbol=VIXY"  # VIX ETF proxy
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        spy_data = data.get("spy", {})
                        price = spy_data.get("price", 0)
                        if price > 0:
                            # VIXY roughly tracks VIX (it's a VIX futures ETF)
                            # Scale factor: VIXY ~ VIX * 0.6 approximately
                            return price
        except Exception as e:
            logger.debug(f"VIX fetch error: {e}")

        return self._last_vix  # Return cached value

    async def _fetch_pcr(self) -> float:
        """Fetch Put/Call ratio across near-term expirations (not just today)."""
        try:
            from datetime import date, timedelta as td

            # Fetch the next 3 expirations and aggregate P/C ratio
            async with aiohttp.ClientSession() as session:
                # First get available expirations
                exp_resp = await session.get(
                    f"{API_BASE}/api/options/expirations?root=SPY",
                    timeout=aiohttp.ClientTimeout(total=5),
                )
                expirations = []
                if exp_resp.status == 200:
                    exp_data = await exp_resp.json()
                    expirations = exp_data.get("expirations", [])[:3]  # Next 3 expirations

                if not expirations:
                    # Fallback: just use today
                    expirations = [date.today().strftime("%Y-%m-%d")]

                total_call_vol = 0
                total_put_vol = 0
                for exp in expirations:
                    url = f"{API_BASE}/api/options/snapshot?root=SPY&exp={exp}"
                    resp = await session.get(url, timeout=aiohttp.ClientTimeout(total=5))
                    if resp.status == 200:
                        data = await resp.json()
                        total_call_vol += data.get("call_volume", 0)
                        total_put_vol += data.get("put_volume", 0)

                if total_call_vol > 0:
                    return round(total_put_vol / total_call_vol, 3)
        except Exception as e:
            logger.debug(f"P/C ratio error: {e}")
        return 0

    def _neutral(self, reason: str) -> AgentVerdict:
        return AgentVerdict(
            agent_name=self.name,
            direction=Direction.NEUTRAL,
            confidence=0.0,
            reasoning=reason,
            stale_after_seconds=self.stale_seconds,
        )
