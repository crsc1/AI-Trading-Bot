"""
Agent 2: News Agent (LLM-Powered via Alpaca + Finnhub + Stocktwits)

Monitors real-time market news for SPY-moving events:
  - Alpaca News API (included with Algo Trader Plus) — primary
  - Finnhub news + sentiment (60 req/min free) — secondary
  - Stocktwits trending (free, no auth) — social sentiment
  - FRED economic calendar — macro events

The agent fetches headlines, then uses Claude API (when configured)
or a rule-based keyword classifier to determine market impact.

Features:
  - URGENCY classification: BREAKING / HIGH / NORMAL
  - Breaking news circuit breaker — signals auto-trader to exit/pause
  - Expanded keyword library for modern market movers (tariffs, sanctions, etc.)

Polling: Every 10 seconds (fast enough to catch breaking news)
"""

import aiohttp
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Tuple
from .base import BaseAgent, AgentVerdict, Direction
from ..config import cfg

logger = logging.getLogger(__name__)

ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_HEADERS = cfg.ALPACA_HEADERS

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── EXPANDED KEYWORD DATABASE ──
# Organized by urgency level and direction

BULLISH_KEYWORDS = [
    # Rate / monetary policy
    "rate cut", "fed cut", "dovish", "stimulus", "quantitative easing", "qe",
    "pause rate", "hold rates", "accommodative", "inject liquidity",
    # Earnings / economic
    "beat expectations", "strong earnings", "earnings beat", "revenue beat",
    "jobs added", "gdp growth", "gdp beat", "gdp above", "jobs surge",
    "retail sales beat", "consumer confidence rises",
    # Trade / geopolitics
    "trade deal", "deal reached", "ceasefire", "peace talks", "peace deal",
    "sanctions lifted", "tariff removed", "tariff delay", "tariff paused",
    "tariff exemption", "trade agreement",
    # Market sentiment
    "bull market", "record high", "all-time high", "rally", "surge", "soar",
    "breakout", "green across", "risk-on",
    # Inflation
    "inflation falls", "inflation drops", "inflation eases", "cpi lower",
    "cpi below", "pce lower", "disinflation",
    # General positive
    "optimism", "buy the dip", "recovery", "expansion", "upside surprise",
    "better than expected", "above consensus", "soft landing",
]

BEARISH_KEYWORDS = [
    # Rate / monetary policy
    "rate hike", "hawkish", "tightening", "higher for longer",
    "quantitative tightening", "qt", "restrictive",
    # Tariffs & trade war (CRITICAL for Trump-era moves)
    "tariff", "tariffs", "new tariff", "tariff increase", "tariff war",
    "trade war", "retaliatory tariff", "import tax", "export ban",
    "sanctions", "new sanctions", "sanction", "embargo",
    "china tariff", "china trade", "china ban",
    # Geopolitical crisis
    "war", "invasion", "attack", "missile", "military strike",
    "conflict escalat", "geopolitical", "nuclear", "threat",
    "middle east", "taiwan", "troops deployed",
    # Economic weakness
    "recession", "contraction", "gdp miss", "gdp below",
    "layoffs", "mass layoffs", "jobs lost", "unemployment rises",
    "job cuts", "hiring freeze", "weak earnings", "earnings miss",
    "revenue miss", "guidance cut", "guidance lower",
    "consumer confidence falls", "retail sales miss",
    # Market panic
    "crash", "bear market", "sell off", "selloff", "plunge", "tank",
    "circuit breaker", "flash crash", "capitulation", "margin call",
    "risk-off", "flight to safety", "panic",
    # Inflation shock
    "inflation rises", "inflation surge", "inflation hot",
    "cpi higher", "cpi above", "cpi beat", "pce higher",
    "stagflation",
    # Political / fiscal crisis
    "default", "shutdown", "government shutdown", "debt ceiling",
    "downgrade", "credit downgrade", "impeach",
    "miss expectations", "below consensus",
]

# Keywords that mark news as POTENTIALLY BREAKING (instant market movers)
BREAKING_KEYWORDS = [
    # People whose words move markets instantly
    "trump", "president", "white house", "oval office",
    "powell", "fed chair", "yellen", "treasury secretary",
    "xi jinping", "china president",
    # Events that move markets in seconds
    "breaking", "just in", "alert", "flash",
    "emergency", "surprise", "unexpected", "shock",
    "executive order", "signed order",
    # Extreme market events
    "circuit breaker", "halt", "trading halt", "flash crash",
    "limit down", "limit up",
]

HIGH_IMPACT_KEYWORDS = [
    "fed", "fomc", "powell", "cpi", "ppi", "nonfarm", "jobs report",
    "gdp", "unemployment", "retail sales", "interest rate",
    "treasury", "yield", "debt ceiling", "default", "tariff",
    "trump", "white house", "executive order", "sanctions",
    "china", "russia", "war", "invasion", "opec", "oil",
]

# ── NEWS URGENCY LEVELS ──
URGENCY_BREAKING = "BREAKING"   # Exit positions immediately, pause new entries
URGENCY_HIGH = "HIGH"           # Factor heavily into next signal, tighten stops
URGENCY_NORMAL = "NORMAL"       # Standard news flow

# ── CIRCUIT BREAKER (shared state for autonomous trader) ──
# When breaking news hits, this flag tells the auto-trader to react
_news_circuit_breaker = {
    "active": False,
    "triggered_at": None,
    "headline": None,
    "direction": None,       # Which way the news pushes
    "urgency": URGENCY_NORMAL,
    "auto_clear_seconds": 300,  # 5 minutes then auto-clear
}


def get_news_circuit_breaker() -> Dict:
    """Check if news circuit breaker is active. Called by autonomous_trader."""
    cb = _news_circuit_breaker
    if cb["active"] and cb["triggered_at"]:
        age = (datetime.now(timezone.utc) - cb["triggered_at"]).total_seconds()
        if age > cb["auto_clear_seconds"]:
            cb["active"] = False
            cb["urgency"] = URGENCY_NORMAL
            logger.info("News circuit breaker auto-cleared after timeout")
    return dict(cb)


def clear_news_circuit_breaker():
    """Manually clear the circuit breaker."""
    _news_circuit_breaker["active"] = False
    _news_circuit_breaker["urgency"] = URGENCY_NORMAL
    logger.info("News circuit breaker manually cleared")


class NewsAgent(BaseAgent):
    name = "News"
    poll_interval = 10       # Fast polling — breaking news moves markets in seconds
    stale_seconds = 90       # News stays relevant for 90 seconds

    def __init__(self):
        super().__init__()
        self._seen_ids: set = set()
        self._last_headlines: List[Dict] = []
        self._last_urgency: str = URGENCY_NORMAL

    async def analyze(self) -> AgentVerdict:
        """Fetch news from multiple sources and determine market impact."""
        headlines = []

        # 1. Alpaca News (primary — real-time, included with subscription)
        alpaca_news = await self._fetch_alpaca_news()
        headlines.extend(alpaca_news)

        # 2. Finnhub news (secondary — has sentiment scores)
        if FINNHUB_KEY:
            finnhub_news = await self._fetch_finnhub_news()
            headlines.extend(finnhub_news)

        # 3. Stocktwits trending (free, no auth — social sentiment)
        stocktwits_news = await self._fetch_stocktwits()
        headlines.extend(stocktwits_news)

        if not headlines:
            return self._neutral("No recent news")

        # Filter to new headlines only
        new_headlines = []
        for h in headlines:
            hid = h.get("id", h.get("headline", ""))
            if hid not in self._seen_ids:
                self._seen_ids.add(hid)
                new_headlines.append(h)

        # Keep seen_ids from growing forever
        if len(self._seen_ids) > 500:
            self._seen_ids = set(list(self._seen_ids)[-200:])

        self._last_headlines = headlines[:10]

        # Analyze all recent headlines (not just new ones)
        return await self._analyze_headlines(headlines[:20])

    async def _fetch_alpaca_news(self) -> List[Dict]:
        """Fetch recent news from Alpaca News API."""
        if not ALPACA_KEY:
            return []

        try:
            # Alpaca News API v1beta1
            _since = (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            url = f"{ALPACA_DATA_URL}/v1beta1/news"
            params = {
                "symbols": "SPY,SPX,QQQ",
                "start": _since,
                "limit": 20,
                "sort": "desc",
            }

            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        logger.debug(f"Alpaca news {resp.status}")
                        return []
                    data = await resp.json()

            news_items = data.get("news", [])
            return [
                {
                    "id": n.get("id", ""),
                    "headline": n.get("headline", ""),
                    "summary": n.get("summary", ""),
                    "source": n.get("source", "alpaca"),
                    "created_at": n.get("created_at", ""),
                    "symbols": n.get("symbols", []),
                    "sentiment": None,  # Alpaca doesn't provide sentiment
                }
                for n in news_items
            ]
        except Exception as e:
            logger.debug(f"Alpaca news error: {e}")
            return []

    async def _fetch_stocktwits(self) -> List[Dict]:
        """Fetch trending messages from Stocktwits (free, no auth required)."""
        try:
            # Stocktwits trending for SPY
            url = "https://api.stocktwits.com/api/2/streams/symbol/SPY.json"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        logger.debug(f"Stocktwits {resp.status}")
                        return []
                    data = await resp.json()

            messages = data.get("messages", [])
            results = []
            for msg in messages[:10]:
                body = msg.get("body", "")
                sentiment = msg.get("entities", {}).get("sentiment", {})
                sent_val = None
                if sentiment:
                    basic = sentiment.get("basic")
                    if basic == "Bullish":
                        sent_val = 0.5
                    elif basic == "Bearish":
                        sent_val = -0.5

                results.append({
                    "id": f"st_{msg.get('id', '')}",
                    "headline": body[:200],
                    "summary": "",
                    "source": "stocktwits",
                    "created_at": msg.get("created_at", ""),
                    "sentiment": sent_val,
                })
            return results
        except Exception as e:
            logger.debug(f"Stocktwits error: {e}")
            return []

    async def _fetch_finnhub_news(self) -> List[Dict]:
        """Fetch news with sentiment from Finnhub."""
        try:
            url = "https://finnhub.io/api/v1/news"
            params = {
                "category": "general",
                "minId": 0,
                "token": FINNHUB_KEY,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()

            return [
                {
                    "id": str(n.get("id", "")),
                    "headline": n.get("headline", ""),
                    "summary": n.get("summary", ""),
                    "source": n.get("source", "finnhub"),
                    "created_at": datetime.fromtimestamp(
                        n.get("datetime", 0), tz=timezone.utc
                    ).isoformat() if n.get("datetime") else "",
                    "sentiment": n.get("sentiment"),
                }
                for n in data[:10]
            ]
        except Exception as e:
            logger.debug(f"Finnhub news error: {e}")
            return []

    async def _analyze_headlines(self, headlines: List[Dict]) -> AgentVerdict:
        """
        Analyze headlines for market impact.
        Uses LLM if ANTHROPIC_API_KEY is set, otherwise rule-based keywords.
        Also classifies urgency and triggers circuit breaker on BREAKING news.
        """
        # Try LLM analysis first
        if ANTHROPIC_KEY and headlines:
            llm_result = await self._llm_analyze(headlines)
            if llm_result:
                return llm_result

        # Fallback: keyword-based analysis
        return self._keyword_analyze(headlines)

    def _classify_urgency(self, headlines: List[Dict]) -> Tuple[str, Optional[str]]:
        """
        Classify the urgency level of current headlines.
        Returns (urgency_level, triggering_headline_or_None).
        """
        for h in headlines:
            text = (h.get("headline", "") + " " + h.get("summary", "")).lower()

            # Check for BREAKING keywords
            breaking_count = sum(1 for kw in BREAKING_KEYWORDS if kw in text)
            if breaking_count >= 2:
                return URGENCY_BREAKING, h.get("headline", "")

            # Single breaking keyword + high-impact = BREAKING
            if breaking_count >= 1 and any(kw in text for kw in HIGH_IMPACT_KEYWORDS):
                return URGENCY_BREAKING, h.get("headline", "")

        # Check for HIGH urgency
        for h in headlines:
            text = (h.get("headline", "") + " " + h.get("summary", "")).lower()
            high_count = sum(1 for kw in HIGH_IMPACT_KEYWORDS if kw in text)
            if high_count >= 2:
                return URGENCY_HIGH, h.get("headline", "")

        return URGENCY_NORMAL, None

    def _trigger_circuit_breaker(self, headline: str, direction: Direction, urgency: str):
        """Activate the news circuit breaker for breaking news events."""
        global _news_circuit_breaker
        _news_circuit_breaker["active"] = True
        _news_circuit_breaker["triggered_at"] = datetime.now(timezone.utc)
        _news_circuit_breaker["headline"] = headline
        _news_circuit_breaker["direction"] = direction.value
        _news_circuit_breaker["urgency"] = urgency
        logger.warning(
            f"NEWS CIRCUIT BREAKER TRIGGERED: [{urgency}] {direction.value} — {headline[:100]}"
        )

    async def _llm_analyze(self, headlines: List[Dict]) -> Optional[AgentVerdict]:
        """Use Claude API to interpret news impact on SPY."""
        try:
            headline_text = "\n".join(
                f"- {h['headline']}" + (f" ({h['source']})" if h.get('source') else "")
                for h in headlines[:10]
            )

            prompt = f"""You are a professional SPY/SPX options day trader. Analyze these market news headlines and determine their IMMEDIATE impact on SPY price direction for the next 1-2 hours.

Headlines:
{headline_text}

Classify urgency:
- BREAKING: Instant market movers (Fed decisions, presidential executive orders, war/invasion, trading halts). Requires immediate action.
- HIGH: Major economic data, tariff announcements, earnings of megacaps. Significant but not instant.
- NORMAL: Standard market news flow.

Respond in EXACTLY this JSON format (no other text):
{{"direction": "bullish" or "bearish" or "neutral", "confidence": 0.0-1.0, "urgency": "BREAKING" or "HIGH" or "NORMAL", "reasoning": "one sentence"}}"""

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 150,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        logger.debug(f"Claude API {resp.status}")
                        return None
                    result = await resp.json()

            text = result.get("content", [{}])[0].get("text", "")

            # Parse JSON from response
            import json
            # Find JSON in response
            json_match = re.search(r'\{[^}]+\}', text)
            if not json_match:
                return None
            parsed = json.loads(json_match.group())

            direction_map = {
                "bullish": Direction.BULLISH,
                "bearish": Direction.BEARISH,
                "neutral": Direction.NEUTRAL,
            }

            direction = direction_map.get(parsed.get("direction", "neutral"), Direction.NEUTRAL)
            urgency = parsed.get("urgency", URGENCY_NORMAL)
            if urgency not in (URGENCY_BREAKING, URGENCY_HIGH, URGENCY_NORMAL):
                urgency = URGENCY_NORMAL
            self._last_urgency = urgency

            # Trigger circuit breaker on BREAKING news
            if urgency == URGENCY_BREAKING and direction != Direction.NEUTRAL:
                self._trigger_circuit_breaker(
                    headlines[0]["headline"] if headlines else "LLM breaking",
                    direction,
                    urgency,
                )

            # Boost confidence for high urgency
            confidence = min(1.0, float(parsed.get("confidence", 0)))
            if urgency == URGENCY_BREAKING:
                confidence = min(1.0, confidence * 1.5)
            elif urgency == URGENCY_HIGH:
                confidence = min(1.0, confidence * 1.2)

            return AgentVerdict(
                agent_name=self.name,
                direction=direction,
                confidence=confidence,
                reasoning=f"[{urgency}] " + parsed.get("reasoning", "LLM analysis"),
                factors=[h["headline"] for h in headlines[:5]],
                data={
                    "headlines": len(headlines),
                    "source": "llm",
                    "urgency": urgency,
                },
                stale_after_seconds=self.stale_seconds,
            )

        except Exception as e:
            logger.debug(f"LLM analysis failed: {e}")
            return None

    def _keyword_analyze(self, headlines: List[Dict]) -> AgentVerdict:
        """Rule-based keyword analysis when LLM is unavailable."""
        bullish_score = 0.0
        bearish_score = 0.0
        factors = []
        high_impact = False

        for h in headlines:
            text = (h.get("headline", "") + " " + h.get("summary", "")).lower()

            # Check for high impact
            for kw in HIGH_IMPACT_KEYWORDS:
                if kw in text:
                    high_impact = True
                    break

            # Score bullish keywords
            for kw in BULLISH_KEYWORDS:
                if kw in text:
                    weight = 0.15 if any(hk in text for hk in HIGH_IMPACT_KEYWORDS) else 0.08
                    bullish_score += weight
                    factors.append(f"Bullish: '{kw}' in \"{h['headline'][:60]}\"")

            # Score bearish keywords
            for kw in BEARISH_KEYWORDS:
                if kw in text:
                    weight = 0.15 if any(hk in text for hk in HIGH_IMPACT_KEYWORDS) else 0.08
                    bearish_score += weight
                    factors.append(f"Bearish: '{kw}' in \"{h['headline'][:60]}\"")

            # Use Finnhub / Stocktwits sentiment if available
            if h.get("sentiment") is not None:
                sent = h["sentiment"]
                if sent > 0.3:
                    bullish_score += 0.10
                elif sent < -0.3:
                    bearish_score += 0.10

        # ── Urgency classification ──
        urgency, trigger_headline = self._classify_urgency(headlines)
        self._last_urgency = urgency

        # Determine direction
        net = bullish_score - bearish_score
        if net > 0.1:
            direction = Direction.BULLISH
            confidence = min(0.8, bullish_score)
        elif net < -0.1:
            direction = Direction.BEARISH
            confidence = min(0.8, bearish_score)
        else:
            direction = Direction.NEUTRAL
            confidence = 0.0

        # Boost confidence for high-impact / urgent news
        if high_impact and confidence > 0:
            confidence = min(1.0, confidence * 1.3)
        if urgency == URGENCY_BREAKING and confidence > 0:
            confidence = min(1.0, confidence * 1.5)
        elif urgency == URGENCY_HIGH and confidence > 0:
            confidence = min(1.0, confidence * 1.2)

        # ── Trigger circuit breaker on BREAKING ──
        if urgency == URGENCY_BREAKING and direction != Direction.NEUTRAL:
            self._trigger_circuit_breaker(
                trigger_headline or (headlines[0].get("headline", "") if headlines else ""),
                direction,
                urgency,
            )

        reasoning = f"[{urgency}] {len(headlines)} headlines analyzed"
        if factors:
            reasoning += " — " + factors[0]

        return AgentVerdict(
            agent_name=self.name,
            direction=direction,
            confidence=confidence,
            reasoning=reasoning,
            factors=factors[:5],
            data={
                "headlines": len(headlines),
                "bullish_score": round(bullish_score, 2),
                "bearish_score": round(bearish_score, 2),
                "high_impact": high_impact,
                "urgency": urgency,
                "source": "keywords",
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
