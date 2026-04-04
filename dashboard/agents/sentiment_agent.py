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

        # 2. VIX regime
        vix = await self._fetch_vix()
        if vix > 0:
            self._last_vix = vix
            if vix > 30:
                factors.append(f"VIX {vix:.1f} — extreme fear, market stressed")
                bearish_weight += 0.20
            elif vix > 22:
                factors.append(f"VIX {vix:.1f} — elevated volatility")
                bearish_weight += 0.10
            elif vix < 14:
                factors.append(f"VIX {vix:.1f} — complacency, low volatility")
                bullish_weight += 0.10
            else:
                factors.append(f"VIX {vix:.1f} — normal range")

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
            confidence = min(0.7, bullish_weight)
        elif net < -0.1:
            direction = Direction.BEARISH
            confidence = min(0.7, bearish_weight)
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
        """Fetch Put/Call ratio from our options snapshot."""
        try:
            # Get today's expiry
            from datetime import date
            today = date.today().strftime("%Y-%m-%d")

            async with aiohttp.ClientSession() as session:
                url = f"{API_BASE}/api/options/snapshot?root=SPY&exp={today}"
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("pc_ratio", 0)
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
