"""
Research Agent — Background agent for continuous improvement.

Runs every 30 minutes during market hours + after-hours batch.
Scrapes Reddit, analyzes trade history, detects patterns, suggests parameter changes.

Sources:
    - Reddit (r/wallstreetbets, r/options, r/SPY) via Reddit JSON API
    - Trade history from signal_db — win/loss patterns by setup, time of day, regime
    - Daily performance from trade_grader
    - Market regime shifts from regime_detector historical data

Findings stored in SQLite, surfaced via REST API + frontend ResearchFeed.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_FINDINGS = 100
RESEARCH_INTERVAL = 30 * 60  # 30 minutes
REDDIT_SUBREDDITS = ["wallstreetbets", "options", "SPY"]
REDDIT_USER_AGENT = "AI-Trading-Bot-Research/1.0"


@dataclass
class ResearchFinding:
    """One finding from the research agent."""
    id: str = ""
    type: str = ""          # sentiment, pattern, suggestion
    title: str = ""
    content: str = ""
    source: str = ""        # reddit, trade_history, performance
    confidence: float = 0.0
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ── Singleton state ───────────────────────────────────────────────────────────
_findings: deque = deque(maxlen=MAX_FINDINGS)
_stats = {
    "total_runs": 0,
    "reddit_posts_analyzed": 0,
    "patterns_found": 0,
    "suggestions_made": 0,
    "errors": 0,
    "last_run": None,
}
_running = False
_task: Optional[asyncio.Task] = None


def get_findings(limit: int = 20) -> List[Dict]:
    """Return recent findings, newest first."""
    return [f.to_dict() for f in reversed(list(_findings))][:limit]


def get_research_stats() -> Dict:
    return {**_stats}


# ── Reddit Scraping ───────────────────────────────────────────────────────────

async def _fetch_reddit_posts(subreddit: str, limit: int = 25) -> List[Dict]:
    """Fetch recent posts from a subreddit using Reddit's JSON API (no auth needed)."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers={"User-Agent": REDDIT_USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"[Research] Reddit r/{subreddit} returned {resp.status}")
                    return []
                data = await resp.json()
                posts = []
                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    posts.append({
                        "title": post.get("title", ""),
                        "selftext": (post.get("selftext", "") or "")[:500],
                        "score": post.get("score", 0),
                        "num_comments": post.get("num_comments", 0),
                        "created_utc": post.get("created_utc", 0),
                        "subreddit": subreddit,
                        "url": post.get("url", ""),
                    })
                return posts
    except Exception as e:
        logger.debug(f"[Research] Reddit fetch error for r/{subreddit}: {e}")
        return []


async def _analyze_reddit_sentiment() -> Optional[ResearchFinding]:
    """Analyze Reddit sentiment across SPY-related subreddits."""
    all_posts = []
    for sub in REDDIT_SUBREDDITS:
        posts = await _fetch_reddit_posts(sub, limit=15)
        all_posts.extend(posts)
        await asyncio.sleep(1)  # Rate limit

    if not all_posts:
        return None

    _stats["reddit_posts_analyzed"] += len(all_posts)

    # Simple keyword sentiment analysis (no LLM needed for basic classification)
    bullish_keywords = ["calls", "bull", "moon", "rip", "buy", "long", "breakout", "gap up", "higher"]
    bearish_keywords = ["puts", "bear", "crash", "dump", "short", "sell", "breakdown", "gap down", "lower"]
    spy_keywords = ["spy", "spx", "0dte", "0DTE", "options"]

    spy_posts = [p for p in all_posts if any(k in (p["title"] + " " + p["selftext"]).lower() for k in spy_keywords)]

    if not spy_posts:
        return None

    bull_score = 0
    bear_score = 0
    for post in spy_posts:
        text = (post["title"] + " " + post["selftext"]).lower()
        weight = 1 + min(post["score"], 100) / 100  # Upvotes boost weight
        for kw in bullish_keywords:
            if kw in text:
                bull_score += weight
        for kw in bearish_keywords:
            if kw in text:
                bear_score += weight

    total = bull_score + bear_score
    if total == 0:
        return None

    bull_pct = bull_score / total * 100
    bear_pct = bear_score / total * 100
    sentiment = "bullish" if bull_pct > 60 else "bearish" if bear_pct > 60 else "mixed"

    # Top trending posts
    top_posts = sorted(spy_posts, key=lambda p: p["score"], reverse=True)[:3]
    top_titles = [p["title"][:80] for p in top_posts]

    return ResearchFinding(
        id=str(uuid.uuid4())[:8],
        type="sentiment",
        title=f"Reddit Sentiment: {sentiment.upper()} ({len(spy_posts)} SPY posts)",
        content=(
            f"Bull/Bear ratio: {bull_pct:.0f}% / {bear_pct:.0f}% across {len(spy_posts)} SPY-related posts.\n"
            f"Top posts:\n" + "\n".join(f"  - {t}" for t in top_titles)
        ),
        source="reddit",
        confidence=min(0.9, len(spy_posts) / 20),  # More posts = higher confidence
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={
            "bull_pct": round(bull_pct, 1),
            "bear_pct": round(bear_pct, 1),
            "post_count": len(spy_posts),
            "subreddits": REDDIT_SUBREDDITS,
        },
    )


# ── Trade History Analysis ────────────────────────────────────────────────────

async def _analyze_trade_history() -> List[ResearchFinding]:
    """Analyze trade history for patterns."""
    findings = []

    try:
        from .signal_db import get_recent_signals
        signals = get_recent_signals(limit=100)
        if not signals or len(signals) < 10:
            return findings

        # Analyze by setup type
        setup_stats: Dict[str, Dict] = {}
        for sig in signals:
            setup = sig.get("setup_name", "unknown")
            if setup not in setup_stats:
                setup_stats[setup] = {"wins": 0, "losses": 0, "total_pnl": 0}
            pnl = sig.get("pnl", 0) or 0
            if pnl > 0:
                setup_stats[setup]["wins"] += 1
            elif pnl < 0:
                setup_stats[setup]["losses"] += 1
            setup_stats[setup]["total_pnl"] += pnl

        for setup, stats in setup_stats.items():
            total = stats["wins"] + stats["losses"]
            if total < 3:
                continue
            win_rate = stats["wins"] / total if total > 0 else 0

            if win_rate < 0.35 and total >= 5:
                findings.append(ResearchFinding(
                    id=str(uuid.uuid4())[:8],
                    type="pattern",
                    title=f"Low win rate: {setup} ({win_rate:.0%})",
                    content=(
                        f"{setup} has a {win_rate:.0%} win rate over {total} trades "
                        f"(P&L: ${stats['total_pnl']:.2f}). "
                        f"Consider raising the quality threshold or disabling this setup."
                    ),
                    source="trade_history",
                    confidence=min(0.9, total / 20),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metadata={"setup": setup, "win_rate": win_rate, "trades": total},
                ))
                _stats["patterns_found"] += 1

            elif win_rate > 0.70 and total >= 5:
                findings.append(ResearchFinding(
                    id=str(uuid.uuid4())[:8],
                    type="pattern",
                    title=f"Strong setup: {setup} ({win_rate:.0%})",
                    content=(
                        f"{setup} has a {win_rate:.0%} win rate over {total} trades "
                        f"(P&L: ${stats['total_pnl']:.2f}). "
                        f"This is a reliable setup — consider increasing position size."
                    ),
                    source="trade_history",
                    confidence=min(0.9, total / 20),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metadata={"setup": setup, "win_rate": win_rate, "trades": total},
                ))
                _stats["patterns_found"] += 1

        # Analyze by time of day
        hour_stats: Dict[int, Dict] = {}
        for sig in signals:
            ts = sig.get("timestamp", "")
            try:
                hour = datetime.fromisoformat(ts).hour
            except (ValueError, TypeError):
                continue
            if hour not in hour_stats:
                hour_stats[hour] = {"wins": 0, "losses": 0, "total_pnl": 0}
            pnl = sig.get("pnl", 0) or 0
            if pnl > 0:
                hour_stats[hour]["wins"] += 1
            elif pnl < 0:
                hour_stats[hour]["losses"] += 1
            hour_stats[hour]["total_pnl"] += pnl

        for hour, stats in hour_stats.items():
            total = stats["wins"] + stats["losses"]
            if total < 3:
                continue
            win_rate = stats["wins"] / total if total > 0 else 0

            if win_rate < 0.30 and total >= 5 and stats["total_pnl"] < -20:
                findings.append(ResearchFinding(
                    id=str(uuid.uuid4())[:8],
                    type="suggestion",
                    title=f"Avoid trading at {hour}:00 ({win_rate:.0%} win rate)",
                    content=(
                        f"Trades placed between {hour}:00-{hour}:59 have a {win_rate:.0%} win rate "
                        f"over {total} trades (P&L: ${stats['total_pnl']:.2f}). "
                        f"Consider raising the confidence threshold during this hour."
                    ),
                    source="trade_history",
                    confidence=min(0.8, total / 15),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    metadata={"hour": hour, "win_rate": win_rate, "trades": total},
                ))
                _stats["suggestions_made"] += 1

    except Exception as e:
        logger.debug(f"[Research] Trade history analysis error: {e}")

    return findings


# ── Research Cycle ────────────────────────────────────────────────────────────

async def _run_research_cycle():
    """Run one research cycle: scrape + analyze + store findings."""
    _stats["total_runs"] += 1
    _stats["last_run"] = datetime.now(timezone.utc).isoformat()
    logger.info("[Research] Starting research cycle")

    try:
        # Reddit sentiment
        sentiment = await _analyze_reddit_sentiment()
        if sentiment:
            _findings.append(sentiment)
            logger.info(f"[Research] Reddit: {sentiment.title}")

        # Trade history patterns
        patterns = await _analyze_trade_history()
        for p in patterns:
            _findings.append(p)
            logger.info(f"[Research] Pattern: {p.title}")

        logger.info(
            f"[Research] Cycle complete: "
            f"{1 if sentiment else 0} sentiment, {len(patterns)} patterns"
        )

    except Exception as e:
        _stats["errors"] += 1
        logger.error(f"[Research] Cycle error: {e}", exc_info=True)


async def _research_loop():
    """Background loop running research every 30 minutes."""
    logger.info(f"[Research] Starting research loop (every {RESEARCH_INTERVAL}s)")
    await asyncio.sleep(30)  # Wait for server to start

    while _running:
        try:
            await _run_research_cycle()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Research] Loop error: {e}")
        await asyncio.sleep(RESEARCH_INTERVAL)


def start_research_agent():
    """Start the background research loop."""
    global _running, _task
    if _running:
        return
    _running = True
    try:
        loop = asyncio.get_running_loop()
        _task = loop.create_task(_research_loop())
    except RuntimeError:
        _task = asyncio.get_event_loop().create_task(_research_loop())
    logger.info("[Research] Agent started")


def stop_research_agent():
    """Stop the background research loop."""
    global _running, _task
    _running = False
    if _task and not _task.done():
        _task.cancel()
    _task = None
    logger.info("[Research] Agent stopped")


# ── FastAPI Routes ────────────────────────────────────────────────────────────

from fastapi import APIRouter

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/findings")
async def get_research_findings(limit: int = 20):
    """Get recent research findings."""
    return {"findings": get_findings(limit)}


@router.get("/stats")
async def get_stats():
    """Get research agent stats."""
    return get_research_stats()


@router.post("/run")
async def trigger_research():
    """Manually trigger a research cycle."""
    await _run_research_cycle()
    return {"status": "completed", "findings_count": len(_findings)}
