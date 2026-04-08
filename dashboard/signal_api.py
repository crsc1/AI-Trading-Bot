"""
Production-Grade AI Signal Engine for SPY 0DTE Options Trading.

Architecture:
  - Server-side data fetching: pulls bars, quotes, options chains internally
  - Market structure levels: VWAP (±1σ/2σ/3σ), HOD/LOD, prev day H/L/C,
    pre-market H/L, Opening Range (5m/15m), pivot points, POC
  - Order flow analysis: delta divergence, absorption, exhaustion, large blocks,
    aggressive vs passive, bid/ask imbalance at levels
  - Options integration: real chain data, delta-based strike selection,
    live bid/ask for entry pricing, GEX awareness
  - Time context: session phases, 0DTE decay curve, 3:00 PM hard stop
  - Confluence framework: Setup + Trigger, minimum 3+ confirming factors,
    tiered confidence (TEXTBOOK / HIGH / VALID / DEVELOPING)
  - Dynamic risk: sized by confidence × volatility (ATR + VIX proxy)

Signal Endpoints:
  - POST /api/signals/analyze  — real-time analysis from frontend tick data
  - GET  /api/signals/latest   — most recent signal
  - GET  /api/signals/history  — last 50 signals
  - GET  /api/signals/config   — current configuration
  - GET  /api/signals/levels   — current market structure levels
  - GET  /api/signals/gex      — GEX/DEX analysis

Phase 2 — Trading Endpoints:
  - POST /api/signals/trade     — process signal through paper trader
  - GET  /api/signals/positions — open positions with live P&L
  - GET  /api/signals/trades    — closed trade history
  - GET  /api/signals/scorecard — performance metrics + advanced stats
  - POST /api/signals/exit      — manually exit an open position

Phase 3B — Microstructure Edge Endpoints:
  - GET  /api/signals/sweeps    — institutional sweep detection
  - GET  /api/signals/vpin      — flow toxicity (VPIN) status
  - GET  /api/signals/sectors   — sector divergence + bond yield analysis
"""

from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime, timezone, time as dt_time
from datetime import timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
import logging
from collections import deque

from .config import cfg
from .signal_engine import SignalEngine, ACCOUNT_BALANCE, SYMBOL
from .market_levels import compute_market_levels
from .confluence import (
    get_session_context,
    SESSION_PHASES,
    ZERO_DTE_HARD_STOP,
    TIER_TEXTBOOK,
    TIER_HIGH,
    TIER_VALID,
    MIN_TRADE_CONFIDENCE,
    RISK_TABLE,
    ET,
    select_strike,
)
from .gex_engine import calculate_gex
from .options_analytics import analyze_options
from utils.greeks import calculate_greeks, calculate_iv
from .vanna_charm_engine import calculate_vanna_charm
from .regime_detector import detect_regime
from .event_calendar import get_event_context
from .sweep_detector import detect_sweeps
from .flow_toxicity import compute_vpin_from_trades
from .sector_monitor import analyze_sectors
from .market_internals import analyze_breadth
from .paper_trader import PaperTrader
from .position_tracker import PositionTracker
from .trade_grader import grade_and_store, compute_advanced_scorecard
from .autonomous_trader import AutonomousTrader, AutoTraderConfig, TrainingDataCollector
from .weight_learner import WeightLearner
from .confluence import (
    set_weight_learner, refresh_weights, get_active_weights,
    get_active_symbol, set_active_symbol, derive_spx_price,
    get_trade_mode, set_trade_mode, TRADE_MODE_PARAMS,
)
from .signal_db import (
    get_open_trades,
    get_trade_history,
    get_todays_trades,
    get_recent_signals,
    compute_scorecard,
    store_daily_scorecard,
    get_daily_scorecards,
)

import asyncio
import aiohttp
import uuid as _uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/signals", tags=["signals"])


def _inject_signal_id(signal: dict) -> dict:
    """Ensure every signal has a unique 'id' before entering signal_history.
    The PositionManager consumer loop uses this ID for deduplication."""
    if not signal.get("id"):
        signal["id"] = str(_uuid.uuid4())[:12]
    return signal


# ============================================================================
# CONFIGURATION
# ============================================================================

# Signal history
signal_history: deque = deque(maxlen=cfg.SIGNAL_HISTORY_MAX)

# Cached market structure (refreshed each analysis cycle)
_market_cache: Dict[str, Any] = {}

# Background analysis loop control
_analysis_task: Optional[asyncio.Task] = None
ANALYSIS_INTERVAL = cfg.SIGNAL_ANALYSIS_INTERVAL  # seconds between auto-analysis cycles

# ============================================================================
# PHANTOM P/L TRACKER — Real-time virtual P/L for every signal card
# ============================================================================

@dataclass
class PhantomEntry:
    """Tracks a signal's virtual P/L as if it were entered."""
    signal_id: str
    option_type: str       # "call" or "put"
    strike: float
    expiry: str
    entry_price: float     # Premium at signal generation
    target_price: float
    stop_price: float
    max_contracts: int
    created_at: float      # time.time()

    # Live tracking (updated on each poll)
    current_price: float = 0.0
    peak_price: float = 0.0      # Maximum favorable excursion
    trough_price: float = 0.0    # Maximum adverse excursion
    target_hit_at: Optional[float] = None   # timestamp when target first hit
    stop_hit_at: Optional[float] = None     # timestamp when stop first hit
    status: str = "LIVE"         # LIVE | TARGET_HIT | STOP_HIT | MISSED | EXPIRED
    was_traded: bool = False     # Whether PM actually entered this trade
    level_note: str = ""         # Level-aware exit note from risk calculation

import time as _time

# signal_id → PhantomEntry
_phantom_tracker: Dict[str, PhantomEntry] = {}

def _register_phantom(signal: Dict):
    """Register a new signal for phantom P/L tracking."""
    sig_id = signal.get("id")
    if not sig_id or sig_id in _phantom_tracker:
        return
    entry = signal.get("entry_price", 0)
    if not entry or entry <= 0:
        return

    action = signal.get("signal", "")
    opt_type = "put" if "PUT" in action else "call"

    risk_mgmt = signal.get("risk_management", {})
    _phantom_tracker[sig_id] = PhantomEntry(
        signal_id=sig_id,
        option_type=opt_type,
        strike=signal.get("strike", 0),
        expiry=signal.get("expiry", ""),
        entry_price=entry,
        target_price=signal.get("target_price", 0),
        stop_price=signal.get("stop_price", 0),
        max_contracts=signal.get("max_contracts", risk_mgmt.get("max_contracts", 1)),
        created_at=_time.time(),
        current_price=entry,
        peak_price=entry,
        trough_price=entry,
        level_note=risk_mgmt.get("level_note", ""),
    )

def _update_phantom_prices():
    """Update all phantom entries from the cached chain data."""
    if not _phantom_tracker:
        return

    # Get cached chain from engine
    chain = getattr(engine, '_chain_cache', None) or {}
    calls_chain = chain.get("calls", [])
    puts_chain = chain.get("puts", [])

    # Build strike→price lookup from chain
    call_prices = {}
    put_prices = {}
    for c in calls_chain:
        strike = c.get("strike", 0)
        bid = c.get("bid", 0) or 0
        ask = c.get("ask", 0) or 0
        mid = round((bid + ask) / 2, 2) if bid and ask else c.get("last", 0) or 0
        if strike > 0 and mid > 0:
            call_prices[strike] = {"bid": bid, "ask": ask, "mid": mid}
    for p in puts_chain:
        strike = p.get("strike", 0)
        bid = p.get("bid", 0) or 0
        ask = p.get("ask", 0) or 0
        mid = round((bid + ask) / 2, 2) if bid and ask else p.get("last", 0) or 0
        if strike > 0 and mid > 0:
            put_prices[strike] = {"bid": bid, "ask": ask, "mid": mid}

    now = _time.time()

    for sid, ph in list(_phantom_tracker.items()):
        # Skip already-closed entries
        if ph.status in ("EXPIRED",):
            continue

        # Auto-expire entries older than 8 hours (end of day cleanup)
        if now - ph.created_at > 8 * 3600:
            ph.status = "EXPIRED"
            continue

        # Look up current price from chain
        prices = call_prices if ph.option_type == "call" else put_prices
        contract = prices.get(ph.strike)
        if not contract:
            continue  # No chain data for this strike yet

        # Use bid for exit valuation (what you'd actually get if selling)
        current = contract["bid"] if contract["bid"] > 0 else contract["mid"]
        if current <= 0:
            continue

        ph.current_price = current

        # Track MFE / MAE
        if current > ph.peak_price:
            ph.peak_price = current
        if current < ph.trough_price:
            ph.trough_price = current

        # Status transitions
        if ph.target_price > 0 and current >= ph.target_price:
            if ph.target_hit_at is None:
                ph.target_hit_at = now
            ph.status = "TARGET_HIT"
        elif ph.stop_price > 0 and current <= ph.stop_price:
            if ph.stop_hit_at is None:
                ph.stop_hit_at = now
            ph.status = "STOP_HIT"
        elif ph.target_hit_at is not None and current < ph.target_price:
            # Was at target, now retreated → MISSED
            ph.status = "MISSED"
        else:
            ph.status = "LIVE"


# ============================================================================
# DATA MODELS
# ============================================================================

class AnalyzeRequest(BaseModel):
    trades: List[Dict[str, Any]]
    quote: Dict[str, Any]
    options_data: Optional[Dict[str, Any]] = None
    symbol: str = "SPY"


# ============================================================================
# GLOBAL ENGINE INSTANCE
# ============================================================================

engine = SignalEngine(SYMBOL)
paper_trader = PaperTrader(mode="alpaca_paper")  # Alpaca paper trading for real orders
position_tracker = PositionTracker()

# ── Autonomous Trading Infrastructure ──
weight_learner = WeightLearner()
training_collector = TrainingDataCollector()
auto_trader_config = AutoTraderConfig()

# ── After-Hours Learning Loop ──
from .afterhours_learner import AfterHoursLearner
afterhours_learner = AfterHoursLearner(
    weight_learner=weight_learner,
    training_collector=training_collector,
)


async def _on_trade_closed_callback(trade: Dict, pnl: float, exit_reason: str):
    """Bridge between autonomous trader and weight learner."""
    await weight_learner.on_trade_closed(trade, pnl, exit_reason)
    training_collector.record_outcome(trade.get("signal_id", ""), {
        **trade, "pnl": pnl, "exit_reason": exit_reason,
    })
    refresh_weights()  # Pull learned weights into confluence engine


auto_trader = AutonomousTrader(
    paper_trader=paper_trader,
    position_tracker=position_tracker,
    config=auto_trader_config,
    on_trade_closed=_on_trade_closed_callback,
)

# Register weight learner with confluence engine
set_weight_learner(weight_learner)


# ============================================================================
# BACKGROUND ANALYSIS LOOP — feeds live trades into the confluence engine
# ============================================================================
# This is the critical integration that was missing: the signal engine's
# POST /analyze endpoint was never called by anything. This background task
# fetches live trades from the REST API every 15s and runs full confluence
# analysis, populating signal_history so GET /latest returns real signals.

async def _fetch_live_trades(symbol: str = "SPY", limit: int = 500) -> List[Dict]:
    """Fetch recent trades from our own orderflow REST endpoint.
    Normalizes Alpaca compact format {t,p,s,side} → {timestamp,price,size,side}
    which is what the confluence engine expects."""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{cfg.DASHBOARD_BASE_URL}/api/orderflow/trades/recent?symbol={symbol}&limit={limit}&feed=sip"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    raw_trades = data.get("trades", [])
                    # Normalize: Alpaca uses {t, p, s} but confluence expects {timestamp, price, size}
                    normalized = []
                    for t in raw_trades:
                        normalized.append({
                            "timestamp": t.get("t", t.get("timestamp", "")),
                            "price": t.get("p", t.get("price", 0)),
                            "size": t.get("s", t.get("size", 0)),
                            "side": t.get("side", "unknown"),
                            "exchange": t.get("x", t.get("exchange", "")),
                        })
                    return normalized
    except Exception as e:
        logger.debug(f"[SignalLoop] Failed to fetch trades: {e}")
    return []


async def _fetch_live_quote(symbol: str = "SPY") -> Dict:
    """Fetch latest quote from our own API, or derive from recent trades."""
    result = {}

    # Try 1: Quote endpoint
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{cfg.DASHBOARD_BASE_URL}/api/quote?symbol={symbol}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Normalize: ensure 'last' exists
                    if not data.get("last") and data.get("price"):
                        data["last"] = data["price"]
                    if data.get("last") and data["last"] > 0:
                        return data
                    result = data  # Keep partial data for merging later
    except Exception as e:
        logger.debug(f"[SignalLoop] Quote endpoint failed: {e}")

    # Try 2: Market endpoint (has snapshot price)
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{cfg.DASHBOARD_BASE_URL}/api/market?symbol={symbol}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    spy = data.get("spy", {})
                    p = spy.get("price", 0) or spy.get("last", 0)
                    if p and p > 0:
                        result["last"] = p
                        result["price"] = p
                        result["prev_close"] = spy.get("prev_close", 0)
                        result["symbol"] = symbol
                        return result
    except Exception:
        pass

    # Try 3: Derive from most recent trade
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{cfg.DASHBOARD_BASE_URL}/api/orderflow/trades/recent?symbol={symbol}&limit=5&feed=sip"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    trades = data.get("trades", [])
                    if trades:
                        p = trades[-1].get("p", trades[-1].get("price", 0))
                        if p and p > 0:
                            result["last"] = p
                            result["price"] = p
                            result["symbol"] = symbol
                            return result
    except Exception:
        pass

    return result



def _is_market_hours() -> bool:
    """
    Return True only during regular trading hours (9:30 AM – 4:00 PM ET).
    0DTE options only exist and are tradeable during RTH — there is no valid
    signal to generate outside this window.
    """
    try:
        try:
            from zoneinfo import ZoneInfo
            now_et = datetime.now(ZoneInfo("America/New_York"))
        except ImportError:
            import pytz
            now_et = datetime.now(pytz.timezone("America/New_York"))
    except Exception:
        # Fallback: UTC-4 (EDT) — close enough
        now_et = datetime.now(timezone(timedelta(hours=-4)))

    t = now_et.time()
    # Monday–Friday 09:30–16:00 ET only
    if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return dt_time(9, 30) <= t < dt_time(16, 0)


# ── Signal smoothing + loss adaptation state ──
# Prevents flip-flopping by requiring sustained directional conviction.
_signal_history = []  # Last N signal directions for smoothing
_SMOOTHING_WINDOW = 3  # Must see same direction N times before acting
_consecutive_losses = 0  # Tracks consecutive stop-loss exits
_LOSS_CONFIDENCE_BOOST = 0.08  # Extra confidence required per consecutive loss


def _apply_signal_smoothing(signal: dict) -> dict:
    """
    Require same direction for N consecutive cycles before emitting a trade signal.
    Also raises confidence threshold after consecutive losses.
    """
    global _consecutive_losses

    action = signal.get("action", "NO_TRADE")
    confidence = signal.get("confidence", 0)

    # Track direction history
    _signal_history.append(action)
    if len(_signal_history) > _SMOOTHING_WINDOW * 2:
        _signal_history.pop(0)

    # If NO_TRADE, pass through as-is
    if action == "NO_TRADE":
        return signal

    # Check if last N signals agree on direction
    recent = _signal_history[-_SMOOTHING_WINDOW:]
    if len(recent) < _SMOOTHING_WINDOW or not all(s == action for s in recent):
        signal["action"] = "NO_TRADE"
        signal["reasoning"] = (
            f"Signal smoothing: {action} not sustained for {_SMOOTHING_WINDOW} cycles "
            f"(recent: {recent}). Original: {signal.get('reasoning', '')[:80]}"
        )
        return signal

    # Loss adaptation: raise confidence floor after consecutive losses
    if _consecutive_losses > 0:
        required = 0.60 + (_consecutive_losses * _LOSS_CONFIDENCE_BOOST)
        if confidence < required:
            signal["action"] = "NO_TRADE"
            signal["reasoning"] = (
                f"Loss adaptation: conf {confidence:.2f} < {required:.2f} required "
                f"after {_consecutive_losses} consecutive losses. "
                f"Original: {signal.get('reasoning', '')[:80]}"
            )
            return signal

    return signal


def record_trade_outcome(exit_reason: str):
    """Called when a trade exits. Tracks consecutive losses for adaptation."""
    global _consecutive_losses
    if exit_reason in ("stop_loss", "hard_stop", "trailing_stop"):
        _consecutive_losses += 1
        logger.info(f"[SignalSmoothing] Loss #{_consecutive_losses} — "
                     f"raising min confidence to {0.60 + _consecutive_losses * _LOSS_CONFIDENCE_BOOST:.2f}")
    else:
        if _consecutive_losses > 0:
            logger.info(f"[SignalSmoothing] Win/exit — resetting loss counter from {_consecutive_losses}")
        _consecutive_losses = 0


async def _trigger_brain_on_setup(signal: dict):
    """
    On-demand Brain: triggered only when the non-LLM engine finds a setup.
    Asks Opus to validate the setup with full market context.
    ~5-20 calls/day instead of ~780 from the 30s cycle.
    """
    try:
        from .market_brain import brain
        from .brain_chat import broadcast_decision, broadcast_brain_state
        from .market_moments import moments_db
        from .data_collector import collect_snapshot

        setup_name = signal.get("setup_name", signal.get("reasoning", "unknown")[:50])
        direction = signal.get("signal", "?")
        confidence = signal.get("confidence", 0)

        logger.info(f"[Brain] On-demand trigger: {setup_name} {direction} conf={confidence:.2f}")

        snapshot = await collect_snapshot(engine, signal_history)
        decision = await brain.analyze_cycle(engine, snapshot=snapshot, moments_db=moments_db)

        await broadcast_brain_state()

        # Record moment
        asyncio.create_task(asyncio.to_thread(
            moments_db.record_moment,
            trigger_type="setup",
            trigger_name=setup_name,
            trigger_detail=f"{direction} conf={confidence:.2f} — Brain says: {decision.action}",
            brain_action=decision.action,
            brain_confidence=decision.confidence,
            snapshot=snapshot,
        ))

        await broadcast_decision(decision.to_dict())

        logger.info(
            f"[Brain] On-demand result: {decision.action} conf={decision.confidence:.2f} "
            f"reason={decision.reasoning[:100]}"
        )

    except Exception as e:
        logger.error(f"[Brain] On-demand trigger error: {e}", exc_info=True)


async def _run_brain_cycle():
    """Market Brain analysis cycle: collect snapshot → LLM decision → record moment."""
    try:
        if not _is_market_hours():
            return

        from .market_brain import brain
        from .brain_chat import broadcast_decision, broadcast_brain_state
        from .market_moments import moments_db
        from .data_collector import collect_snapshot

        # 1. Collect snapshot for pattern recall
        snapshot = await collect_snapshot(engine, signal_history)

        # 2. Run Brain analysis (uses direct API or CLI based on config)
        decision = await brain.analyze_cycle(engine, snapshot=snapshot, moments_db=moments_db)

        # Broadcast state to WebSocket clients
        await broadcast_brain_state()

        # 3. Record market moment (async, non-blocking)
        setups = snapshot.setups if hasattr(snapshot, 'setups') else []
        trigger_name = setups[0].get("name") if setups else None
        asyncio.create_task(asyncio.to_thread(
            moments_db.record_moment,
            trigger_type="signal" if decision.action == "TRADE" else "cycle",
            trigger_name=trigger_name or decision.action,
            trigger_detail=decision.reasoning[:200] if decision.reasoning else None,
            brain_action=decision.action,
            brain_confidence=decision.confidence,
            snapshot=snapshot,
        ))

        if decision.action == "TRADE" and decision.direction and decision.confidence >= 0.45:
            # Convert Brain decision to signal format for position_manager
            signal = {
                "signal": decision.direction,
                "confidence": decision.confidence,
                "tier": decision.tier,
                "reasoning": decision.reasoning,
                "key_factors": decision.key_factors,
                "source": "market_brain",
                "brain_cycle": decision.cycle,
            }
            _inject_signal_id(signal)
            signal_history.append(signal)
            logger.info(
                f"[Brain] TRADE signal: {decision.direction} "
                f"conf={decision.confidence:.2f} tier={decision.tier}"
            )

        # Broadcast decision + pattern recall to chat clients
        await broadcast_decision(decision.to_dict())

        # Broadcast pattern recall for the frontend BrainFeed
        from .brain_chat import broadcast
        similar = moments_db.find_similar(snapshot=snapshot, limit=3, min_similarity=0.70)
        moments_stats = moments_db.get_stats()
        await broadcast({
            "type": "pattern_recall",
            "similar_moments": similar,
            "moments_stats": moments_stats,
        })

    except Exception as e:
        logger.error(f"[Brain] Cycle error: {e}", exc_info=True)


async def _run_analysis_cycle():
    """Single analysis cycle: fetch data → run confluence → store signal."""
    try:
        # ── Route to Market Brain if enabled ──
        if cfg.USE_MARKET_BRAIN:
            await _run_brain_cycle()
            return

        # ── Market hours guard — 0DTE signals are only valid during RTH ──
        if not _is_market_hours():
            return

        # ── Step 1: Get quote ──
        quote = await _fetch_live_quote("SPY")
        if not quote or not quote.get("last"):
            logger.info("[SignalLoop] Waiting — no valid quote yet")
            return
        underlying_price = quote.get("last", 0)

        # ── Step 2: Get REAL tick data from Rust flow engine ──
        # The Rust engine receives ThetaData WebSocket ticks, classifies them
        # using NBBO bid/ask aggression, and publishes structured events.
        # This is the ONLY trade data source. No synthetic fallbacks.
        # A bad signal from fake data is worse than no signal.
        trades = []
        _trades_source = "rust_engine"
        _flow_context = None
        try:
            from .flow_subscriber import flow_subscriber
            real_trades = flow_subscriber.get_real_trades(window_seconds=300)
            if real_trades and len(real_trades) >= 20:
                trades = real_trades
                buy_count = sum(1 for t in trades if t['side'] == 'buy')
                sell_count = sum(1 for t in trades if t['side'] == 'sell')
                logger.info(
                    f"[SignalLoop] Real flow: {len(trades)} ticks from Rust engine "
                    f"({buy_count}B / {sell_count}S)"
                )
            # Get structured flow context for setup detection
            try:
                _flow_context = flow_subscriber.get_flow_context()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"[SignalLoop] Rust engine trades unavailable: {e}")

        # ── Fallback: REST-polled Alpaca SIP trades ──
        if not trades or len(trades) < 20:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as _sess:
                    async with _sess.get(
                        f"{cfg.DASHBOARD_BASE_URL}/api/orderflow/trades/recent?symbol=SPY&limit=500&feed=sip",
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            rest_data = await resp.json()
                            rest_trades = rest_data.get("trades", [])
                            if rest_trades and len(rest_trades) >= 20:
                                # Normalize REST format to engine format
                                trades = [{
                                    "time": t.get("t", ""),
                                    "price": t.get("p", 0),
                                    "size": t.get("s", 0),
                                    "side": t.get("side", "unknown"),
                                    "exchange": t.get("x", ""),
                                } for t in rest_trades]
                                _trades_source = "alpaca_rest"
                                buy_count = sum(1 for t in trades if t["side"] == "buy")
                                sell_count = sum(1 for t in trades if t["side"] == "sell")
                                logger.info(
                                    f"[SignalLoop] REST fallback: {len(trades)} trades from Alpaca SIP "
                                    f"({buy_count}B / {sell_count}S)"
                                )
            except Exception as e:
                logger.debug(f"[SignalLoop] REST fallback failed: {e}")

        if not trades or len(trades) < 20:
            logger.info(
                "[SignalLoop] No tick data from Rust engine or REST fallback. "
                "Skipping cycle."
            )
            return

        # If trading SPX, derive SPX price from SPY
        active_sym = get_active_symbol()
        if active_sym == "SPX" and quote.get("last"):
            spy_price = quote["last"]
            spx_price = derive_spx_price(spy_price)
            quote["spy_price"] = spy_price
            quote["last"] = spx_price
            quote["price"] = spx_price
            quote["symbol"] = "SPX"

        # Fetch server-side market data (bars, options chain, etc.)
        market_data = await engine.fetch_market_data()

        # Merge quote data
        merged_quote = {**market_data.get("quote", {})}
        if quote:
            merged_quote.update({k: v for k, v in quote.items() if v})
        market = market_data.get("market", {})
        # Ensure 'last'/'price' exists — /api/quote returns bid/ask/midpoint but
        # engine.analyze() needs quote.get("last") or quote.get("price")
        if not merged_quote.get("last") and not merged_quote.get("price"):
            merged_quote["last"] = market.get("price", 0) or merged_quote.get("midpoint", 0)
        if not merged_quote.get("prev_close"):
            merged_quote["prev_close"] = market.get("prev_close", 0)

        # Fetch regime context
        try:
            chain = market_data.get("chain", {})
            current_iv = 0.0
            if chain:
                calls = chain.get("calls", [])
                puts = chain.get("puts", [])
                if calls or puts:
                    try:
                        from .options_analytics import analyze_options as _ao
                        _analytics = _ao(calls, puts, merged_quote.get("last", 0) or 0)
                        current_iv = _analytics.atm_iv
                    except Exception:
                        pass
            regime = await detect_regime(
                current_iv=current_iv,
                spy_bars_1m=market_data.get("bars_1m"),
            )
            engine._cached_regime = regime
        except Exception:
            pass

        # Fetch event context
        try:
            event_ctx = await get_event_context()
            engine._cached_event_context = event_ctx
        except Exception:
            pass

        # VPIN from trade data
        try:
            if len(trades) >= 10:
                vpin_state = compute_vpin_from_trades(trades)
                engine._cached_vpin = vpin_state
        except Exception:
            pass

        # Inject ThetaData options flow context into engine
        try:
            from .theta_stream import theta_stream
            opts_ctx = theta_stream.get_options_flow_context()
            if opts_ctx.get("connected") and opts_ctx.get("trades_received", 0) > 0:
                engine._cached_options_flow = opts_ctx
                # Override equity VPIN with options VPIN (more accurate for 0DTE)
                if opts_ctx.get("vpin") is not None:
                    from .flow_toxicity import VPINState
                    engine._cached_vpin = VPINState(
                        vpin=opts_ctx["vpin"],
                        toxicity_level=opts_ctx["vpin_level"],
                        buy_volume=opts_ctx["buy_volume"],
                        sell_volume=opts_ctx["sell_volume"],
                        total_volume=opts_ctx["buy_volume"] + opts_ctx["sell_volume"],
                        bucket_count=40,
                    )
                logger.debug(
                    f"[SignalLoop] Options flow: VPIN={opts_ctx.get('vpin', '?'):.2f} "
                    f"PCR={opts_ctx.get('pcr_premium', 0):.2f} "
                    f"SMS70+={opts_ctx.get('high_sms_count', 0)} "
                    f"sweeps={opts_ctx.get('sweep_count', 0)}"
                )
        except Exception as e:
            logger.debug(f"[SignalLoop] Options flow context unavailable: {e}")

        # Sweeps + sectors + breadth in parallel
        try:
            sweep_result, sector_result, breadth_result = await asyncio.gather(
                detect_sweeps(symbol="SPY"),
                analyze_sectors(),
                analyze_breadth(),
                return_exceptions=True,
            )
            engine._cached_sweeps = sweep_result if not isinstance(sweep_result, Exception) else None
            engine._cached_sectors = sector_result if not isinstance(sector_result, Exception) else None
            engine._cached_breadth = breadth_result if not isinstance(breadth_result, Exception) else None
        except Exception:
            pass

        # Fetch agent verdicts (v5: wire 5-agent system into confluence)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{cfg.DASHBOARD_BASE_URL}/api/agents/verdicts",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        verdicts = data.get("verdicts", {})
                        # Only pass through if we have at least one non-stale verdict
                        active = {k: v for k, v in verdicts.items()
                                  if not v.get("stale", True) and v.get("confidence", 0) > 0}
                        if active:
                            engine._cached_agent_verdicts = verdicts
                            logger.debug(f"[SignalLoop] Agent verdicts: {len(active)} active")
                        else:
                            engine._cached_agent_verdicts = None
                    else:
                        engine._cached_agent_verdicts = None
        except Exception as e:
            logger.debug(f"[SignalLoop] Agent verdicts fetch failed: {e}")
            engine._cached_agent_verdicts = None

        # Pass flow context for setup detection
        engine._cached_flow_context = _flow_context

        # Run full analysis (v15: uses setup detector instead of confluence)
        signal = engine.analyze(
            trades=trades,
            quote=merged_quote,
            options_data=market_data.get("options_snapshot", {}),
            bars_1m=market_data.get("bars_1m"),
            bars_daily=market_data.get("bars_daily"),
            chain=market_data.get("chain"),
            trades_source=_trades_source,
        )

        # v15: Skip signal smoothing for setup-based signals.
        # Setup detection has its own multi-cycle state tracking.
        # Only apply smoothing to legacy confluence signals (if any).
        if not signal.get("setup_based"):
            signal = _apply_signal_smoothing(signal)

        # Enrich with context
        if engine._cached_regime:
            signal["regime"] = engine._cached_regime.to_dict()
        if engine._cached_event_context:
            signal["event_context"] = engine._cached_event_context.to_dict()
        if engine._cached_sweeps:
            signal["sweeps"] = engine._cached_sweeps.to_dict()
        if engine._cached_vpin:
            signal["vpin"] = engine._cached_vpin.to_dict()
        if engine._cached_sectors:
            signal["sectors"] = engine._cached_sectors.to_dict()
        if getattr(engine, '_cached_breadth', None):
            signal["market_breadth"] = engine._cached_breadth.to_dict()
        if engine._cached_agent_verdicts:
            signal["agent_verdicts"] = engine._cached_agent_verdicts

        # Tag signal with the trade data source so UI can show data quality
        signal["trades_source"] = _trades_source
        signal["trade_count"] = len(trades)

        # Log analysis result (always, for diagnostics)
        sig_action = signal.get("signal", "NO_TRADE")
        sig_conf = signal.get("confidence", 0)
        sig_factors = signal.get("factors", [])
        active_count = sum(1 for f in sig_factors if abs(f.get("weight", 0)) > 0.05) if isinstance(sig_factors, list) else 0
        logger.info(
            f"[SignalLoop] {sig_action} conf={sig_conf:.2f} "
            f"factors={active_count} reason={signal.get('reasoning', '?')[:120]}"
        )

        # Broadcast every cycle to frontend (BrainFeed heartbeat)
        try:
            from .brain_chat import broadcast
            opts = getattr(engine, '_cached_options_flow', None) or {}
            await broadcast({
                "type": "cycle_update",
                "cycle": {
                    "action": sig_action,
                    "confidence": sig_conf,
                    "reasoning": signal.get("reasoning", "Scanning..."),
                    "trade_count": len(trades),
                    "trades_source": _trades_source,
                    "options_vpin": opts.get("vpin"),
                    "options_vpin_level": opts.get("vpin_level", ""),
                    "options_pcr": opts.get("pcr_premium", 0),
                    "high_sms": opts.get("high_sms_count", 0),
                    "timestamp": datetime.now().isoformat(),
                },
            })
        except Exception:
            pass

        # Tag the underlying SPY price so the outcome tracker can measure
        # direction accuracy without needing to call ThetaData historically.
        signal["spy_price"] = underlying_price

        # Store in history (inject ID so PositionManager can track/deduplicate)
        _inject_signal_id(signal)
        if signal.get("signal") != "NO_TRADE":
            signal_history.append(signal)
            _register_phantom(signal)  # Track phantom P/L
            logger.info(f"[SignalLoop] Signal generated: id={signal['id']} {signal.get('signal')} "
                        f"confidence={signal.get('confidence', 0):.0%} "
                        f"tier={signal.get('tier', '?')}")

            # Broadcast signal to frontend (BrainFeed + Dashboard)
            try:
                from .brain_chat import broadcast
                await broadcast({
                    "type": "signal_detected",
                    "signal": {
                        "id": signal.get("id"),
                        "action": signal.get("signal"),
                        "confidence": signal.get("confidence", 0),
                        "tier": signal.get("tier", "?"),
                        "reasoning": signal.get("reasoning", ""),
                        "setup_name": signal.get("setup_name", ""),
                        "timestamp": datetime.now().isoformat(),
                    },
                })
            except Exception:
                pass

            # On-demand Brain: only call Opus when the non-LLM engine finds a setup
            asyncio.create_task(_trigger_brain_on_setup(signal))
            # Record training data for every actionable signal
            try:
                training_collector.record_signal(signal, get_active_weights())
            except Exception:
                pass

            # Create an outcome stub so the tracker can record what SPY did next
            try:
                from .signal_db import create_outcome_stub, store_signal
                store_signal(signal)  # Persist to DB (includes spy_price column)
                create_outcome_stub(
                    signal_id=signal["id"],
                    direction=signal.get("signal", ""),
                    spy_price=underlying_price,
                )
            except Exception as e:
                logger.warning(f"[SignalLoop] Outcome stub failed for {signal.get('id')}: {e}")

        elif len(signal_history) == 0 or signal_history[-1].get("signal") != "NO_TRADE":
            signal_history.append(signal)
            logger.info(f"[SignalLoop] NO_TRADE — {signal.get('reasoning', 'scanning')[:150]}")

    except Exception as e:
        logger.error(f"[SignalLoop] Analysis cycle error: {e}", exc_info=True)


async def _signal_analysis_loop():
    """Background loop that continuously analyzes market data."""
    logger.info(f"[SignalLoop] Starting background signal analysis (every {ANALYSIS_INTERVAL}s)")
    # Wait for server to fully start up
    await asyncio.sleep(5)

    while True:
        try:
            await _run_analysis_cycle()
        except asyncio.CancelledError:
            logger.info("[SignalLoop] Background analysis stopped")
            break
        except Exception as e:
            logger.error(f"[SignalLoop] Unexpected error: {e}")
        await asyncio.sleep(ANALYSIS_INTERVAL)


def start_signal_loop():
    """Start the background signal analysis loop."""
    global _analysis_task
    if _analysis_task is None or _analysis_task.done():
        try:
            loop = asyncio.get_running_loop()
            _analysis_task = loop.create_task(_signal_analysis_loop())
        except RuntimeError:
            # Fallback for when no running loop (e.g., called outside async context)
            _analysis_task = asyncio.get_event_loop().create_task(_signal_analysis_loop())
        logger.info("[SignalLoop] Background analysis task created")


def stop_signal_loop():
    """Stop the background signal analysis loop."""
    global _analysis_task
    if _analysis_task and not _analysis_task.done():
        _analysis_task.cancel()
        logger.info("[SignalLoop] Background analysis task cancelled")


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/analyze")
async def analyze_order_flow_endpoint(req: AnalyzeRequest):
    """
    Analyze order flow and generate a production-grade trading signal.

    Accepts live tick data from the frontend and enriches with server-side
    market structure levels, real options chain data, and time context.
    """
    try:
        # Fetch server-side data to enrich the analysis
        market_data = await engine.fetch_market_data()

        # Merge frontend quote with server data
        merged_quote = {**market_data.get("quote", {})}
        if req.quote:
            merged_quote.update({k: v for k, v in req.quote.items() if v})

        # Ensure 'last'/'price' exists for engine.analyze()
        market = market_data.get("market", {})
        if not merged_quote.get("last") and not merged_quote.get("price"):
            merged_quote["last"] = market.get("price", 0) or merged_quote.get("midpoint", 0)
        if not merged_quote.get("prev_close"):
            merged_quote["prev_close"] = market.get("prev_close", 0)

        # Merge options data
        options_snap = market_data.get("options_snapshot", {})
        if req.options_data:
            options_snap.update(req.options_data)

        # v3: Fetch regime and event context (async, cached)
        try:
            chain = market_data.get("chain", {})
            current_iv = 0.0
            if chain:
                calls = chain.get("calls", [])
                puts = chain.get("puts", [])
                if calls or puts:
                    try:
                        _analytics = analyze_options(calls, puts, merged_quote.get("last", 0) or 0)
                        current_iv = _analytics.atm_iv
                    except Exception:
                        pass

            regime = await detect_regime(
                current_iv=current_iv,
                spy_bars_1m=market_data.get("bars_1m"),
            )
            engine._cached_regime = regime
        except Exception as e:
            logger.debug(f"Regime detection failed: {e}")
            engine._cached_regime = None

        try:
            event_ctx = await get_event_context()
            engine._cached_event_context = event_ctx
        except Exception as e:
            logger.debug(f"Event calendar failed: {e}")
            engine._cached_event_context = None

        # v4: Fetch Phase 3B data (sweeps, VPIN, sectors) in parallel
        import asyncio as _asyncio

        async def _fetch_sweeps():
            try:
                return await detect_sweeps(symbol="SPY")
            except Exception as e:
                logger.debug(f"Sweep detection failed: {e}")
                return None

        async def _fetch_sectors():
            try:
                return await analyze_sectors()
            except Exception as e:
                logger.debug(f"Sector analysis failed: {e}")
                return None

        async def _fetch_breadth():
            try:
                return await analyze_breadth()
            except Exception as e:
                logger.debug(f"Market breadth analysis failed: {e}")
                return None

        sweep_result, sector_result, breadth_result = await _asyncio.gather(
            _fetch_sweeps(), _fetch_sectors(), _fetch_breadth(),
        )
        engine._cached_sweeps = sweep_result
        engine._cached_sectors = sector_result
        engine._cached_breadth = breadth_result

        # VPIN: computed from trade data passed in the request
        try:
            if req.trades and len(req.trades) >= 10:
                vpin_state = compute_vpin_from_trades(req.trades)
                engine._cached_vpin = vpin_state
            else:
                engine._cached_vpin = None
        except Exception as e:
            logger.debug(f"VPIN calculation failed: {e}")
            engine._cached_vpin = None

        # Run full analysis
        signal = engine.analyze(
            trades=req.trades,
            quote=merged_quote,
            options_data=options_snap,
            bars_1m=market_data.get("bars_1m"),
            bars_daily=market_data.get("bars_daily"),
            chain=market_data.get("chain"),
        )

        # Enrich signal with regime, event, and Phase 3B context
        if engine._cached_regime:
            signal["regime"] = engine._cached_regime.to_dict()
        if engine._cached_event_context:
            signal["event_context"] = engine._cached_event_context.to_dict()
        if engine._cached_sweeps:
            signal["sweeps"] = engine._cached_sweeps.to_dict()
        if engine._cached_vpin:
            signal["vpin"] = engine._cached_vpin.to_dict()
        if engine._cached_sectors:
            signal["sectors"] = engine._cached_sectors.to_dict()
        if getattr(engine, '_cached_breadth', None):
            signal["market_breadth"] = engine._cached_breadth.to_dict()

        # Store in history (inject ID so PositionManager can track/deduplicate)
        _inject_signal_id(signal)
        if signal.get("signal") != "NO_TRADE":
            signal_history.append(signal)
            _register_phantom(signal)  # Track phantom P/L
        elif len(signal_history) == 0 or signal_history[-1].get("signal") != "NO_TRADE":
            # Store NO_TRADE too, but don't flood
            signal_history.append(signal)

        return signal

    except Exception as e:
        logger.error(f"Signal analysis error: {e}", exc_info=True)
        return engine._no_trade(f"Analysis error: {str(e)}")


@router.get("/latest")
async def get_latest_signal():
    """Get the most recent AI trading signal."""
    if not signal_history:
        return engine._no_trade("No signals generated yet — waiting for market data")
    return signal_history[-1]


@router.get("/phantom-pl")
async def get_phantom_pl():
    """
    Real-time phantom P/L for every tracked signal.
    Called every 2 seconds by the frontend for Robinhood-style live P/L.
    Reads from cached chain data so it's sub-5ms.
    """
    # Update prices from cached chain
    _update_phantom_prices()

    # Also mark which signals were actually traded by PM
    try:
        from .signal_db import get_open_trades, get_trade_history
        open_ids = {t.get("signal_id") for t in get_open_trades() if t.get("signal_id")}
        closed_ids = {t.get("signal_id") for t in get_trade_history(limit=100) if t.get("signal_id")}
        traded_ids = open_ids | closed_ids
        for sid, ph in _phantom_tracker.items():
            ph.was_traded = sid in traded_ids
    except Exception:
        pass

    now = _time.time()
    results = []
    for sid, ph in _phantom_tracker.items():
        if ph.status == "EXPIRED":
            continue

        pnl = (ph.current_price - ph.entry_price) * 100 * ph.max_contracts
        pnl_pct = ((ph.current_price - ph.entry_price) / ph.entry_price * 100) if ph.entry_price > 0 else 0
        peak_pnl = (ph.peak_price - ph.entry_price) * 100 * ph.max_contracts
        peak_pnl_pct = ((ph.peak_price - ph.entry_price) / ph.entry_price * 100) if ph.entry_price > 0 else 0

        # Distance to target/stop as percentage of the range
        target_dist = 0
        stop_dist = 0
        if ph.target_price > ph.entry_price:
            total_range = ph.target_price - ph.entry_price
            if total_range > 0:
                target_dist = min(100, max(0, (ph.current_price - ph.entry_price) / total_range * 100))
        if ph.entry_price > ph.stop_price:
            total_range = ph.entry_price - ph.stop_price
            if total_range > 0:
                stop_dist = min(100, max(0, (ph.entry_price - ph.current_price) / total_range * 100))

        results.append({
            "signal_id": sid,
            "option_type": ph.option_type,
            "strike": ph.strike,
            "entry_price": ph.entry_price,
            "current_price": round(ph.current_price, 2),
            "target_price": ph.target_price,
            "stop_price": ph.stop_price,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 1),
            "peak_pnl": round(peak_pnl, 2),
            "peak_pnl_pct": round(peak_pnl_pct, 1),
            "peak_price": round(ph.peak_price, 2),
            "trough_price": round(ph.trough_price, 2),
            "status": ph.status,
            "target_distance_pct": round(target_dist, 1),
            "stop_distance_pct": round(stop_dist, 1),
            "held_seconds": int(now - ph.created_at),
            "was_traded": ph.was_traded,
            "target_hit_at": ph.target_hit_at,
            "max_contracts": ph.max_contracts,
            "level_note": ph.level_note,
        })

    return {"entries": results, "count": len(results)}


@router.get("/diagnostics")
async def get_signal_diagnostics():
    """
    Get signal pipeline diagnostics — shows exactly which gate is blocking signals.
    Essential for debugging when 0 signals are being generated.
    """
    import aiohttp

    diag = engine.get_diagnostics()

    # Also check upstream data availability
    data_checks = {}
    try:
        async with aiohttp.ClientSession() as session:
            # Check trade data
            try:
                async with session.get(
                    f"{cfg.DASHBOARD_BASE_URL}/api/orderflow/trades/recent?symbol=SPY&limit=10&feed=sip",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        trades = data.get("trades", [])
                        data_checks["trades"] = {
                            "available": len(trades),
                            "sufficient": len(trades) >= 5,
                            "status": "OK" if len(trades) >= 5 else f"BLOCKED — need 5+, have {len(trades)}",
                        }
                    else:
                        data_checks["trades"] = {"available": 0, "sufficient": False, "status": f"API error {resp.status}"}
            except Exception as e:
                data_checks["trades"] = {"available": 0, "sufficient": False, "status": f"Unreachable: {e}"}

            # Check quote data
            try:
                async with session.get(
                    f"{cfg.DASHBOARD_BASE_URL}/api/quote?symbol=SPY",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = data.get("last", 0) or data.get("price", 0)
                        data_checks["quote"] = {
                            "price": price,
                            "valid": price > 0,
                            "status": "OK" if price > 0 else "BLOCKED — no valid price",
                        }
                    else:
                        data_checks["quote"] = {"price": 0, "valid": False, "status": f"API error {resp.status}"}
            except Exception as e:
                data_checks["quote"] = {"price": 0, "valid": False, "status": f"Unreachable: {e}"}

            # Check options chain
            try:
                from .confluence import _get_nearest_expiry
                expiry = _get_nearest_expiry()
                async with session.get(
                    f"{cfg.DASHBOARD_BASE_URL}/api/options/chain?root=SPY&exp={expiry}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        n_calls = len(data.get("calls", []))
                        n_puts = len(data.get("puts", []))
                        data_checks["chain"] = {
                            "calls": n_calls,
                            "puts": n_puts,
                            "expiry": expiry,
                            "available": n_calls > 0 or n_puts > 0,
                            "status": "OK" if (n_calls > 0 or n_puts > 0) else "BLOCKED — empty chain (ThetaData down?)",
                        }
                    else:
                        data_checks["chain"] = {"calls": 0, "puts": 0, "available": False, "status": f"API error {resp.status}"}
            except Exception as e:
                data_checks["chain"] = {"calls": 0, "puts": 0, "available": False, "status": f"Unreachable: {e}"}

            # Check ThetaData health
            try:
                async with session.get(
                    f"{cfg.DASHBOARD_BASE_URL}/api/data/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data_checks["connections"] = await resp.json()
            except Exception:
                data_checks["connections"] = {"error": "Health endpoint unreachable"}

    except Exception as e:
        data_checks["error"] = str(e)

    # Determine overall pipeline status
    pipeline_status = "UNKNOWN"
    blocking_gate = diag.get("last_gate_result", {}).get("blocked_at")

    if blocking_gate is None and diag.get("last_gate_result", {}).get("status") == "SIGNAL_GENERATED":
        pipeline_status = "FLOWING"
    elif blocking_gate:
        pipeline_status = f"BLOCKED at {blocking_gate}"
    elif not data_checks.get("trades", {}).get("sufficient"):
        pipeline_status = "BLOCKED — insufficient trade data"
    elif not data_checks.get("quote", {}).get("valid"):
        pipeline_status = "BLOCKED — no valid quote"
    elif not data_checks.get("chain", {}).get("available"):
        pipeline_status = "BLOCKED — no options chain (using estimated fallback)"
    else:
        pipeline_status = "READY — awaiting confluence"

    return {
        "pipeline_status": pipeline_status,
        "engine_diagnostics": diag,
        "data_availability": data_checks,
        "signal_count": len(signal_history),
        "last_signal_action": signal_history[-1].get("signal") if signal_history else None,
        "last_signal_time": signal_history[-1].get("timestamp") if signal_history else None,
    }


@router.get("/history")
async def get_signal_history(limit: int = Query(20, ge=1, le=100)):
    """Get recent signal history."""
    return list(signal_history)[-limit:]


@router.get("/config")
async def get_signal_config():
    """Get current signal engine configuration."""
    return {
        "account_balance": ACCOUNT_BALANCE,
        "symbol": SYMBOL,
        "min_trade_confidence": MIN_TRADE_CONFIDENCE,
        "confidence_tiers": {
            "TEXTBOOK": f">= {TIER_TEXTBOOK}",
            "HIGH": f">= {TIER_HIGH}",
            "VALID": f">= {TIER_VALID}",
            "DEVELOPING": f"< {TIER_VALID}",
        },
        "risk_table": RISK_TABLE,
        "session_phases": {k: f"{v[0].strftime('%H:%M')}-{v[1].strftime('%H:%M')}" for k, v in SESSION_PHASES.items()},
        "zero_dte_hard_stop": ZERO_DTE_HARD_STOP.strftime("%H:%M ET"),
        "signal_history_size": signal_history.maxlen,
        "current_signals_stored": len(signal_history),
    }


@router.get("/symbol")
async def get_trading_symbol():
    """Get the currently active trading symbol."""
    sym = get_active_symbol()
    return {
        "symbol": sym,
        "options_root": "SPXW" if sym == "SPX" else "SPY",
        "style": "european" if sym == "SPX" else "american",
        "settlement": "cash" if sym == "SPX" else "physical",
        "multiplier": 100,
        "description": "S&P 500 Index Options (0DTE)" if sym == "SPX" else "SPDR S&P 500 ETF Options (0DTE)",
    }


@router.post("/symbol")
async def set_trading_symbol(symbol: str = Query(...)):
    """
    Switch the active trading symbol between SPY and SPX.
    This affects signal generation, options chain lookups, and trade execution.
    """
    try:
        new_sym = set_active_symbol(symbol)
        logger.info(f"Active trading symbol changed to: {new_sym}")
        return {
            "symbol": new_sym,
            "options_root": "SPXW" if new_sym == "SPX" else "SPY",
            "message": f"Now trading {new_sym} options",
        }
    except ValueError as e:
        return {"error": str(e)}


@router.get("/trade-mode")
async def get_current_trade_mode():
    """Get the current trade mode (scalp/standard/swing) and its parameters."""
    mode = get_trade_mode()
    params = TRADE_MODE_PARAMS[mode]
    return {
        "mode": mode,
        "params": params,
        "available_modes": list(TRADE_MODE_PARAMS.keys()),
    }


@router.post("/trade-mode")
async def set_current_trade_mode(mode: str = Query(...)):
    """Switch trade mode. Affects exit targets, stops, and hold times."""
    try:
        new_mode = set_trade_mode(mode)
        params = TRADE_MODE_PARAMS[new_mode]
        logger.info(f"Trade mode changed to: {new_mode} — {params['description']}")
        return {"mode": new_mode, "params": params}
    except ValueError as e:
        return {"error": str(e)}


@router.get("/levels")
async def get_market_levels():
    """
    Get current market structure levels (VWAP, pivots, HOD/LOD, ORB, etc).
    Useful for the frontend to draw level lines on the chart.
    """
    try:
        market_data = await engine.fetch_market_data()

        quote = {**market_data.get("quote", {})}
        market = market_data.get("market", {})
        if not quote.get("prev_close"):
            quote["prev_close"] = market.get("prev_close", 0)
        if not quote.get("last"):
            quote["last"] = market.get("price", 0)

        levels = compute_market_levels(
            bars_1m=market_data.get("bars_1m", []),
            bars_daily=market_data.get("bars_daily", []),
            quote=quote,
        )

        return {
            "levels": levels.to_dict(),
            "session": get_session_context().to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/regime")
async def get_regime_status():
    """
    Get current market regime classification.

    Returns VIX term structure, SPY-TLT correlation, DXY direction,
    vol regime, and position sizing multiplier.
    """
    try:
        # Get current IV for vol regime analysis
        market_data = await engine.fetch_market_data()
        chain = market_data.get("chain", {})
        quote = market_data.get("quote", {})
        price = quote.get("last", 0) or quote.get("price", 0)

        current_iv = 0.0
        if chain:
            calls = chain.get("calls", [])
            puts = chain.get("puts", [])
            if calls or puts:
                try:
                    analytics = analyze_options(calls, puts, price)
                    current_iv = analytics.atm_iv
                except Exception:
                    pass

        regime = await detect_regime(
            current_iv=current_iv,
            spy_bars_1m=market_data.get("bars_1m"),
        )

        return {
            "regime": regime.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Regime detection error: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/events")
async def get_event_status():
    """
    Get current economic event awareness status.

    Returns today's events, current mode (pre-event/post-event/normal),
    and trading adjustments.
    """
    try:
        ctx = await get_event_context()
        return {
            "event_context": ctx.to_dict(),
            "events_today": [e.to_dict() for e in ctx.events_today],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Event calendar error: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/vanna-charm")
async def get_vanna_charm_analysis():
    """
    Get current Vanna & Charm dealer flow analysis.

    Returns vanna/charm exposure, regime classification,
    and scoring for the current options chain.
    """
    try:
        market_data = await engine.fetch_market_data()
        chain = market_data.get("chain", {})
        quote = market_data.get("quote", {})
        price = quote.get("last", 0) or quote.get("price", 0)

        calls = chain.get("calls", [])
        puts = chain.get("puts", [])

        if not calls and not puts:
            return {"error": "No options chain data", "vanna_charm": None}

        vc = calculate_vanna_charm(calls, puts, price)

        return {
            "vanna_charm": vc.to_dict(),
            "spot": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Vanna/Charm error: {e}", exc_info=True)
        return {"error": str(e), "vanna_charm": None}


def _enrich_greeks_locally(options: list, spot: float, r: float = 0.045):
    """
    Compute Greeks locally via Black-Scholes for options missing gamma/delta.
    Used as fallback when ThetaData first_order doesn't provide certain Greeks.
    Derives IV from bid/ask mid price, then computes delta and gamma.
    Modifies entries in-place. Returns count of enriched options.
    """
    enriched = 0
    now = datetime.now(timezone.utc)

    for opt in options:
        # Skip if Greeks already present (from ThetaData)
        if opt.get("gamma") is not None and opt.get("delta") is not None:
            continue

        strike = opt.get("strike", 0)
        right = opt.get("right", "C")
        bid = opt.get("bid", 0) or 0
        ask = opt.get("ask", 0) or 0
        mid = opt.get("mid") or ((bid + ask) / 2 if bid and ask else opt.get("last", 0))

        if not strike or strike <= 0 or not mid or mid <= 0 or not spot or spot <= 0:
            continue

        # Calculate time to expiry in years
        exp_str = opt.get("expiration", "")
        if exp_str:
            try:
                exp_date = datetime.strptime(exp_str[:10], "%Y-%m-%d").replace(
                    hour=16, minute=0, tzinfo=timezone.utc
                )
                T = max((exp_date - now).total_seconds() / (365.25 * 86400), 1 / (365.25 * 24))
            except (ValueError, TypeError):
                T = 1 / 365.25  # Default: ~1 day for 0DTE
        else:
            T = 1 / 365.25

        # Derive IV from mid price
        iv = calculate_iv(mid, spot, strike, T, r, right)
        if iv is None or iv <= 0.001:
            iv = 0.20  # Fallback: use 20% if IV solver fails

        # Compute Greeks
        greeks = calculate_greeks(spot, strike, T, r, iv, right)
        opt["gamma"] = greeks.get("gamma")
        opt["delta"] = greeks.get("delta")
        if opt.get("iv") is None:
            opt["iv"] = iv
        enriched += 1

    return enriched


@router.get("/gex")
async def get_gex_analysis():
    """
    Get current GEX/DEX analysis (Gamma & Delta Exposure).

    Fetches the options chain (ThetaData quotes/OI + local BS Greeks),
    computes GEX/DEX locally, and returns:
      - net_gex, call_gex, put_gex
      - call_wall, put_wall, gex_flip_level
      - regime (positive/negative/neutral)
      - per-strike GEX/DEX for visualization
      - options analytics (PCR, IV Rank, Max Pain)

    Greeks (delta/theta/vega/rho/IV) come from ThetaData first_order endpoint.
    Local Black-Scholes fallback only for gamma (which requires Pro greeks/all).
    """
    try:
        market_data = await engine.fetch_market_data()
        chain = market_data.get("chain", {})
        quote = market_data.get("quote", {})
        price = quote.get("last", 0) or quote.get("price", 0)

        calls = chain.get("calls", [])
        puts = chain.get("puts", [])

        if not calls and not puts:
            return {"error": "No options chain data available", "gex": None, "analytics": None}

        # Greeks source: ThetaData first_order provides delta/theta/vega/rho/IV.
        # Gamma requires Pro (greeks/all) — local BS fallback used for gamma only.
        chain.get("source", "unknown")
        greeks_source = "local_bs"  # default; overridden below if Greeks arrived pre-computed
        calls_missing = sum(1 for c in calls if c.get("gamma") is None)
        puts_missing = sum(1 for p in puts if p.get("gamma") is None)

        if calls_missing + puts_missing > 0 and price > 0:
            # Enrich with local Black-Scholes Greeks
            enriched_calls = _enrich_greeks_locally(calls, price)
            enriched_puts = _enrich_greeks_locally(puts, price)
            total_enriched = enriched_calls + enriched_puts
            if total_enriched > 0:
                greeks_source = "local_bs"
                logger.info(
                    f"GEX: enriched {total_enriched} options with local BS Greeks "
                    f"({calls_missing} calls + {puts_missing} puts were missing gamma)"
                )

        gex = calculate_gex(calls, puts, price)
        analytics = analyze_options(calls, puts, price)

        return {
            "gex": gex.to_dict(),
            "analytics": analytics.to_dict(),
            "spot": price,
            "chain_source": chain.get("source", "unknown"),
            "greeks_source": greeks_source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"GEX analysis error: {e}", exc_info=True)
        return {"error": str(e), "gex": None, "analytics": None}


# ============================================================================
# PHASE 3B — MICROSTRUCTURE EDGE ENDPOINTS
# ============================================================================

@router.get("/sweeps")
async def get_sweep_analysis():
    """
    Get current institutional sweep order detection.

    Scans recent 0DTE option trades for multi-exchange fills (sweeps).
    Returns bullish/bearish sweep counts, notional values, and conviction score.
    """
    try:
        analysis = await detect_sweeps(symbol="SPY")
        return {
            "sweeps": analysis.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Sweep detection error: {e}", exc_info=True)
        return {"error": str(e), "sweeps": None}


@router.get("/vpin")
async def get_vpin_status():
    """
    Get current VPIN (flow toxicity) status.

    VPIN measures informed trading probability from volume-bucketed
    trade classification. High VPIN = expect large directional move.
    """
    try:
        # Return cached VPIN if available (computed during analyze)
        cached = getattr(engine, '_cached_vpin', None)
        if cached:
            return {
                "vpin": cached.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return {
            "vpin": None,
            "message": "VPIN requires trade data — run /analyze first",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"VPIN error: {e}", exc_info=True)
        return {"error": str(e), "vpin": None}


@router.get("/sectors")
async def get_sector_analysis():
    """
    Get sector divergence and bond yield analysis.

    Compares XLK/XLF/XLE relative strength vs SPY and TLT bond signal.
    Divergences lead SPY moves by 15-30 minutes.
    """
    try:
        analysis = await analyze_sectors()
        return {
            "sectors": analysis.to_dict(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Sector analysis error: {e}", exc_info=True)
        return {"error": str(e), "sectors": None}


# ============================================================================
# PHASE 2 — TRADING ENDPOINTS
# ============================================================================

class TradeRequest(BaseModel):
    """Request to process a signal through the paper trader."""
    signal: Optional[Dict[str, Any]] = None  # If None, uses latest signal
    mode: Optional[str] = None  # Override: "simulation" or "alpaca_paper"


class ExitRequest(BaseModel):
    """Request to exit an open position."""
    trade_id: str
    exit_price: Optional[float] = None  # If None, uses current market price
    exit_reason: str = "manual"


@router.post("/trade")
async def process_trade(req: TradeRequest):
    """
    Process a signal through the paper trader pipeline.

    Steps: validate → enter (simulation or Alpaca paper) → store in DB.
    If no signal provided, uses the most recent generated signal.
    """
    try:
        # Use provided signal or latest
        signal = req.signal
        if not signal:
            if signal_history:
                signal = signal_history[-1]
            else:
                return {"error": "No signal available", "action": "none"}

        if signal.get("signal") == "NO_TRADE":
            return {"action": "no_trade", "reason": signal.get("reasoning")}

        # Override mode if requested
        trader = paper_trader
        if req.mode and req.mode != paper_trader.mode:
            trader = PaperTrader(mode=req.mode)

        # Get open trades for validation
        open_trades = get_open_trades()

        # Get today's P&L for daily loss check
        todays = get_todays_trades()
        daily_pnl = sum(t.get("pnl", 0) or 0 for t in todays if t.get("exit_time"))

        result = await trader.process_signal(
            signal=signal,
            open_trades=open_trades,
            daily_pnl=daily_pnl,
        )
        return result

    except Exception as e:
        logger.error(f"Trade processing error: {e}", exc_info=True)
        return {"error": str(e), "action": "error"}


@router.get("/positions")
async def get_live_positions():
    """
    Get all open AI-managed positions with REAL-TIME mid-price P&L.

    Uses live options chain bid/ask to compute accurate P&L.
    Falls back to Black-Scholes only when chain data is unavailable.

    Returns positions with unrealized P&L, MFE/MAE, hold time,
    live greeks, price source, and exit trigger status.
    """
    try:
        # Get current price for repricing
        market_data = await engine.fetch_market_data()
        quote = market_data.get("quote", {})
        price = quote.get("last", 0) or quote.get("price", 0)

        # Get live options chain for real mid-price P&L
        chain = market_data.get("chain", {})
        current_iv = 0.0
        if chain:
            calls = chain.get("calls", [])
            puts = chain.get("puts", [])

            # Feed chain to position tracker for real mid-price lookups
            position_tracker.update_chain_prices(chain)

            if calls or puts:
                try:
                    analytics = analyze_options(calls, puts, price)
                    current_iv = analytics.atm_iv
                except Exception:
                    pass

        positions = position_tracker.get_live_positions(
            current_price=price,
            current_iv=current_iv,
        )

        # Check exit triggers
        exit_triggers = position_tracker.check_exit_triggers(positions)

        # Update MFE/MAE for each position
        for pos in positions:
            position_tracker.update_mfe_mae(
                pos["trade_id"],
                pos["unrealized_pnl"],
            )

        summary = position_tracker.get_portfolio_summary(positions)

        return {
            "positions": positions,
            "summary": summary,
            "exit_triggers": [
                {"trade_id": e["trade_id"], "reason": e["exit_reason"]}
                for e in exit_triggers
            ],
            "spot": price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Positions error: {e}", exc_info=True)
        return {"error": str(e), "positions": [], "summary": {}}


@router.get("/trades")
async def get_closed_trades(limit: int = Query(50, ge=1, le=500)):
    """
    Get closed trade history with grades and P&L.
    """
    try:
        trades = get_trade_history(limit=limit)
        return {
            "trades": trades,
            "count": len(trades),
        }
    except Exception as e:
        return {"error": str(e), "trades": []}


@router.get("/scorecard")
async def get_scorecard(period: str = Query("today", description="today, week, month, all")):
    """
    Get performance scorecard with advanced metrics.

    Includes win rate, profit factor, expectancy, Sharpe, Sortino,
    max drawdown, grade distribution, and streak data.
    """
    try:
        if period == "today":
            trades = get_todays_trades()
            basic = compute_scorecard(trades)
            return {**basic, "period": "today"}
        else:
            # All periods use full history with advanced stats
            limit_map = {"week": 100, "month": 300, "all": 500}
            limit = limit_map.get(period, 500)
            advanced = compute_advanced_scorecard(
                trades=get_trade_history(limit=limit)
            )
            return {**advanced, "period": period}

    except Exception as e:
        logger.error(f"Scorecard error: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/beat-spy")
async def get_beat_spy_scorecard():
    """
    Beat SPY Scorecard — daily performance benchmark.

    Compares your day's P&L percentage against SPY's daily return.
    Returns spread, streak, and trade quality grades.
    """
    try:
        # 1. Get today's trades and compute P&L
        todays = get_todays_trades()
        basic = compute_scorecard(todays)

        total_pnl = basic.get("total_pnl", 0.0)
        trade_count = basic.get("total_trades", 0)
        win_rate = basic.get("win_rate", 0.0)

        # Calculate P&L percentage against account balance
        your_pct = (total_pnl / ACCOUNT_BALANCE) * 100 if ACCOUNT_BALANCE > 0 else 0.0

        # 2. Get SPY daily change from current quote vs previous close
        spy_pct = 0.0
        spy_prev_close = 0.0
        spy_current = 0.0
        try:
            market_data = await engine.fetch_market_data()
            quote = market_data.get("quote", {})
            spy_current = quote.get("last", 0) or quote.get("price", 0)
            # Get previous close from bars or from quote data
            bars = market_data.get("bars_1d") or market_data.get("bars_daily")
            if bars and len(bars) >= 2:
                spy_prev_close = bars[-2].get("c", 0) or bars[-2].get("close", 0)
            elif quote.get("prev_close"):
                spy_prev_close = quote["prev_close"]
            elif quote.get("prevClose"):
                spy_prev_close = quote["prevClose"]

            if spy_prev_close > 0 and spy_current > 0:
                spy_pct = ((spy_current - spy_prev_close) / spy_prev_close) * 100
        except Exception as e:
            logger.warning(f"Failed to get SPY daily change: {e}")

        # 3. Compute spread (you vs SPY)
        spread = your_pct - spy_pct
        beat_spy = spread > 0

        # 4. Grade distribution for today's trades
        grades = []
        for trade in todays:
            if trade.get("grade"):
                grades.append(trade["grade"])
            elif trade.get("exit_time"):
                # Try to grade if not already graded
                try:
                    from .trade_grader import grade_trade
                    result = grade_trade(trade)
                    grades.append(result.get("grade", "?"))
                except Exception:
                    grades.append("?")

        grade_dist = {}
        for g in grades:
            grade_dist[g] = grade_dist.get(g, 0) + 1

        # 5. Beat SPY streak (from stored daily scorecards)
        streak = 0
        try:
            scorecards = get_daily_scorecards(limit=30)
            for sc in scorecards:
                if sc.get("beat_spy"):
                    streak += 1
                else:
                    break
        except Exception:
            pass  # Table might not exist yet

        return {
            "your_pnl": round(total_pnl, 2),
            "your_pct": round(your_pct, 3),
            "spy_pct": round(spy_pct, 3),
            "spy_current": round(spy_current, 2),
            "spy_prev_close": round(spy_prev_close, 2),
            "spread": round(spread, 3),
            "beat_spy": beat_spy,
            "trade_count": trade_count,
            "win_rate": round(win_rate, 1),
            "grades": grade_dist,
            "grade_list": grades,
            "streak": streak,
            "account_balance": ACCOUNT_BALANCE,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Beat SPY scorecard error: {e}", exc_info=True)
        return {"error": str(e)}


@router.post("/exit")
async def exit_position(req: ExitRequest):
    """
    Manually exit an open position.

    If exit_price not provided, uses current market price estimate.
    After exit, the trade is graded automatically.
    """
    try:
        open_trades = get_open_trades()
        trade = next((t for t in open_trades if t.get("id") == req.trade_id), None)

        if not trade:
            return {"error": f"Trade {req.trade_id} not found or already closed"}

        # Get exit price
        exit_price = req.exit_price
        if not exit_price:
            # Estimate from current market data
            market_data = await engine.fetch_market_data()
            quote = market_data.get("quote", {})
            spot = quote.get("last", 0) or quote.get("price", 0)
            if spot > 0:
                exit_price = position_tracker._reprice_option(
                    underlying_price=spot,
                    strike=trade.get("strike", 0),
                    option_type=trade.get("option_type", "call"),
                    entry_time=trade.get("entry_time"),
                )
            else:
                exit_price = trade.get("entry_price", 0)  # Fallback to breakeven

        # Execute exit
        success = await paper_trader.exit_trade(
            trade=trade,
            exit_price=exit_price,
            exit_reason=req.exit_reason,
        )

        if not success:
            return {"error": "Exit execution failed"}

        # Grade the trade
        # Re-fetch the now-closed trade from DB
        from .signal_db import _get_conn
        conn = _get_conn()
        row = conn.execute("SELECT * FROM trades WHERE id = ?", (req.trade_id,)).fetchone()
        conn.close()

        grade_result = None
        if row:
            grade_result = grade_and_store(dict(row))

        # Track loss for signal adaptation
        record_trade_outcome(req.exit_reason)

        return {
            "success": True,
            "trade_id": req.trade_id,
            "exit_price": exit_price,
            "exit_reason": req.exit_reason,
            "grade": grade_result,
        }

    except Exception as e:
        logger.error(f"Exit error: {e}", exc_info=True)
        return {"error": str(e)}


@router.get("/signals/stored")
async def get_stored_signals(limit: int = Query(50, ge=1, le=200)):
    """Get signals stored in the database (persisted across restarts)."""
    try:
        signals = get_recent_signals(limit=limit)
        return {"signals": signals, "count": len(signals)}
    except Exception as e:
        return {"error": str(e), "signals": []}


@router.get("/replay")
async def get_signal_replay(
    date: str = Query(None, description="YYYY-MM-DD, defaults to most recent trading day"),
    direction: str = Query(None, description="BUY_CALL or BUY_PUT filter"),
    tier: str = Query(None, description="DEVELOPING, VALID, STRONG, EXCEPTIONAL"),
    min_confidence: float = Query(0, description="Minimum confidence threshold"),
    traded_only: bool = Query(False, description="Only show traded signals"),
):
    """
    Replay historical signals against actual price action.
    Joins signals + signal_outcomes + trades for a given date.
    """
    try:
        from .signal_db import _get_conn
        import json as _j

        conn = _get_conn()
        try:
            # Get available dates
            date_rows = conn.execute("""
                SELECT DISTINCT DATE(timestamp) as d FROM signals
                WHERE timestamp IS NOT NULL
                ORDER BY d DESC
            """).fetchall()
            available_dates = [r["d"] for r in date_rows if r["d"]]

            # Default to most recent date
            if not date and available_dates:
                date = available_dates[0]
            elif not date:
                return {"signals": [], "summary": {}, "price_range": {}, "available_dates": []}

            # Build query with filters
            where_clauses = ["DATE(s.timestamp) = ?"]
            params: list = [date]

            if direction:
                where_clauses.append("s.direction = ?")
                params.append(direction)
            if tier:
                where_clauses.append("s.tier = ?")
                params.append(tier)
            if min_confidence > 0:
                where_clauses.append("s.confidence >= ?")
                params.append(min_confidence)
            if traded_only:
                where_clauses.append("s.was_traded = 1")

            query = """
                SELECT
                    s.*,
                    o.spy_price_at_signal,
                    o.spy_price_15min,
                    o.spy_price_30min,
                    o.move_pct_15min,
                    o.move_pct_30min,
                    o.direction_correct_15,
                    o.direction_correct_30,
                    t.entry_time as trade_entry_time,
                    t.exit_time as trade_exit_time,
                    t.entry_price as trade_entry_price,
                    t.exit_price as trade_exit_price,
                    t.pnl as trade_pnl,
                    t.exit_reason as trade_exit_reason,
                    t.strike as trade_strike,
                    t.option_type as trade_option_type
                FROM signals s
                LEFT JOIN signal_outcomes o ON o.signal_id = s.id
                LEFT JOIN trades t ON t.signal_id = s.id
                WHERE """ + " AND ".join(where_clauses) + """
                ORDER BY s.timestamp ASC
            """
            rows = conn.execute(query, params).fetchall()

            signals = []
            spy_prices = []
            total = 0
            correct_15 = 0
            correct_30 = 0
            move_15_sum = 0.0
            move_30_sum = 0.0
            move_15_count = 0
            move_30_count = 0
            by_direction: Dict[str, Dict] = {}
            by_tier: Dict[str, Dict] = {}
            conf_sum = 0.0

            for r in rows:
                d = dict(r)
                total += 1

                # Parse factors JSON
                factors_raw = d.get("factors")
                try:
                    factors = _j.loads(factors_raw) if factors_raw else []
                except Exception:
                    factors = []
                # Extract top 3 factor names
                top_factors = []
                for f in factors[:3]:
                    if isinstance(f, dict):
                        top_factors.append(f.get("name") or f.get("factor") or str(f))
                    elif isinstance(f, str):
                        top_factors.append(f)
                d["top_factors"] = top_factors
                d["factors"] = factors

                # Track SPY prices for price range
                sp = d.get("spy_price") or d.get("spy_price_at_signal")
                if sp:
                    spy_prices.append(sp)

                # Accumulate summary stats
                conf = d.get("confidence") or 0
                conf_sum += conf

                dc15 = d.get("direction_correct_15")
                dc30 = d.get("direction_correct_30")
                if dc15 == 1:
                    correct_15 += 1
                if dc30 == 1:
                    correct_30 += 1

                m15 = d.get("move_pct_15min")
                m30 = d.get("move_pct_30min")
                if m15 is not None:
                    move_15_sum += m15
                    move_15_count += 1
                if m30 is not None:
                    move_30_sum += m30
                    move_30_count += 1

                # By direction
                dir_key = d.get("direction") or "UNKNOWN"
                if dir_key not in by_direction:
                    by_direction[dir_key] = {"total": 0, "correct_15": 0, "correct_30": 0}
                by_direction[dir_key]["total"] += 1
                if dc15 == 1:
                    by_direction[dir_key]["correct_15"] += 1
                if dc30 == 1:
                    by_direction[dir_key]["correct_30"] += 1

                # By tier
                tier_key = d.get("tier") or "UNKNOWN"
                if tier_key not in by_tier:
                    by_tier[tier_key] = {"total": 0, "correct_15": 0, "correct_30": 0}
                by_tier[tier_key]["total"] += 1
                if dc15 == 1:
                    by_tier[tier_key]["correct_15"] += 1
                if dc30 == 1:
                    by_tier[tier_key]["correct_30"] += 1

                signals.append(d)

            # Build summary
            summary = {
                "total": total,
                "correct_15": correct_15,
                "correct_30": correct_30,
                "accuracy_15": round(correct_15 / total * 100, 1) if total else 0,
                "accuracy_30": round(correct_30 / total * 100, 1) if total else 0,
                "by_direction": by_direction,
                "by_tier": by_tier,
                "avg_confidence": round(conf_sum / total, 1) if total else 0,
                "avg_move_15": round(move_15_sum / move_15_count, 3) if move_15_count else 0,
                "avg_move_30": round(move_30_sum / move_30_count, 3) if move_30_count else 0,
            }

            # Build price range
            price_range = {}
            if spy_prices:
                price_range = {
                    "high": round(max(spy_prices), 2),
                    "low": round(min(spy_prices), 2),
                    "open_price": round(spy_prices[0], 2),
                    "close_price": round(spy_prices[-1], 2),
                }

            return {
                "signals": signals,
                "summary": summary,
                "price_range": price_range,
                "available_dates": available_dates,
                "date": date,
            }
        finally:
            conn.close()

    except Exception as e:
        logger.error(f"Signal replay error: {e}", exc_info=True)
        return {"error": str(e), "signals": [], "summary": {}, "price_range": {}, "available_dates": []}


@router.post("/scorecard/snapshot")
async def snapshot_scorecard():
    """Save today's scorecard to the database for historical tracking."""
    try:
        store_daily_scorecard()
        return {"success": True, "message": "Daily scorecard saved"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/mode")
async def set_trading_mode(mode: str = Query(..., description="simulation or alpaca_paper")):
    """Switch between simulation and Alpaca paper trading mode."""
    global paper_trader
    if mode not in ("simulation", "alpaca_paper"):
        return {"error": f"Invalid mode: {mode}"}
    was_enabled = auto_trader.config.enabled
    auto_trader.config.enabled = False  # Pause during swap
    new_trader = PaperTrader(mode=mode)
    paper_trader = new_trader
    auto_trader.trader = new_trader
    auto_trader.config.enabled = was_enabled
    return {"mode": mode, "message": f"Trading mode set to {mode}"}


# ============================================================================
# VOLATILITY WINDOW ADVISOR (Volatility Framework)
# ============================================================================

# Volatility volatility windows — maps time-of-day to trading regime
VOL_WINDOWS = {
    "pre_market": {
        "label": "Pre-Market",
        "start": "04:00", "end": "09:29",
        "strike_type": "NONE",
        "description": "Check overnight movement, IV level, economic calendar. Mark key levels.",
        "risk_color": "gray",
        "checklist": [
            "Check SPY overnight movement",
            "Note IV level (low / normal / elevated)",
            "Review economic calendar for catalysts",
            "Mark key levels (premarket H/L, overnight H/L)",
            "Define max risk per idea (% of portfolio)",
        ],
    },
    "morning_volatility": {
        "label": "Morning Volatility",
        "start": "09:30", "end": "10:44",
        "strike_type": "OTM",
        "description": "High volatility window. OTM 1-3 strikes out preferred. IV expansion favors cheap options. Wait for structure after first 5-15 min.",
        "risk_color": "green",
        "checklist": [
            "Wait 5-15 min for structure to form",
            "OTM calls/puts aligned with emerging direction",
            "Small position sizes early — let market prove direction",
            "Watch for ISM PMI at 10:00 AM (sharp directional sweeps)",
        ],
    },
    "london_close": {
        "label": "London Close Transition",
        "start": "10:45", "end": "11:44",
        "strike_type": "ATM_ONLY",
        "description": "London markets close at 11:30 ET, causing a large volume regime change. Liquidity shifts, spreads may widen briefly. Transition from morning trends to midday. ATM only with verified structure.",
        "risk_color": "yellow",
        "checklist": [
            "London close at 11:30 — expect volume regime shift",
            "Morning trend may stall or reverse here",
            "ATM only with verified VWAP structure",
            "Reduce size — transitioning to low-vol midday",
            "Watch for false breakouts around 11:30",
        ],
    },
    "midday_theta": {
        "label": "Midday Theta Zone",
        "start": "11:45", "end": "13:29",
        "strike_type": "ATM_ONLY",
        "description": "Low volatility. Theta dominates. OTM rapidly loses value. Only ATM trades with verified structure (VWAP reclaim/breakdown, range break).",
        "risk_color": "yellow",
        "checklist": [
            "AVOID OTM positions (theta-heavy environment)",
            "Only trade ATM with verified structure",
            "Check lead vs SPY (maintain cushion)",
            "Reduce size — wait for afternoon window",
            "Confirm no major upcoming data releases",
        ],
    },
    "transition": {
        "label": "Transition Zone",
        "start": "13:30", "end": "13:59",
        "strike_type": "ATM_ONLY",
        "description": "Market transitioning to afternoon session. Charm acceleration begins. Reduce size, prepare for power window.",
        "risk_color": "yellow",
        "checklist": [
            "Theta steepening — adjust sizing down",
            "Prepare for 2PM+ convexity window",
            "Check if FOMC / Treasury Auction scheduled (1-2 PM)",
            "Look for VWAP reclaims/breakdowns for direction",
        ],
    },
    "power_hour": {
        "label": "Power Hour — Gamma Acceleration",
        "start": "14:00", "end": "15:44",
        "strike_type": "OTM",
        "description": "Gamma acceleration + charm pressure create explosive moves. OTM thrives when IV is elevated. Convexity trades shine. Best window for directional OTM if structure confirms.",
        "risk_color": "green",
        "checklist": [
            "Gamma accelerating — directional moves intensify",
            "OTM viable again if IV elevated and direction clear",
            "Look for VWAP reclaims/breakdowns for direction",
            "Avoid large directional bets without confirmation",
            "Protect your lead vs SPY",
        ],
    },
    "close_risk": {
        "label": "Close Risk — Exit Only",
        "start": "15:45", "end": "16:00",
        "strike_type": "NONE",
        "description": "Final 15 minutes. Close positions. 0DTE options expire worthless if not exited. No new entries.",
        "risk_color": "red",
        "checklist": [
            "Close all 0DTE positions NOW",
            "No new entries",
            "Review final P&L vs SPY",
            "Journal: IV behavior, timing, structure notes",
        ],
    },
}

# Risk tier mapping based on Volatility guide
RISK_TIER_LABELS = {
    "green":  {"label": "Low Risk", "grade": "A–High B", "behavior": "Neutral & focused. Market matches expectations. Clear structure."},
    "yellow": {"label": "Medium Risk", "grade": "Low B–High C", "behavior": "Conditions difficult. Reduce size. OTM only if IV high & direction clear."},
    "red":    {"label": "High Risk", "grade": "Low C", "behavior": "Behind SPY or choppy. Reduce size drastically. Structure-only trades. Stop if emotional."},
    "gray":   {"label": "Pre/Post Market", "grade": "N/A", "behavior": "Market closed. Prepare for next session."},
}


def _get_current_vol_window() -> Dict[str, Any]:
    """Determine the current Volatility volatility window based on ET time."""
    from datetime import time as dt_time
    now_et = datetime.now(ET)
    current_time = now_et.time()

    # Find current window
    current_window = None
    for key, window in VOL_WINDOWS.items():
        parts_start = window["start"].split(":")
        parts_end = window["end"].split(":")
        w_start = dt_time(int(parts_start[0]), int(parts_start[1]))
        w_end = dt_time(int(parts_end[0]), int(parts_end[1]))
        if w_start <= current_time <= w_end:
            current_window = (key, window)
            break

    if not current_window:
        # Outside all windows (after hours / overnight)
        return {
            "window_key": "closed",
            "label": "Market Closed",
            "strike_type": "NONE",
            "description": "Market is closed. Review today's trades and prepare for next session.",
            "risk_color": "gray",
            "checklist": ["Review today's P&L vs SPY", "Journal trades", "Reset for next session"],
            "time_remaining_min": 0,
            "current_time_et": now_et.strftime("%H:%M:%S"),
            "progress_pct": 100,
        }

    key, window = current_window
    parts_end = window["end"].split(":")
    w_end_dt = now_et.replace(hour=int(parts_end[0]), minute=int(parts_end[1]), second=0)
    remaining = max(0, int((w_end_dt - now_et).total_seconds() / 60))

    parts_start = window["start"].split(":")
    w_start_dt = now_et.replace(hour=int(parts_start[0]), minute=int(parts_start[1]), second=0)
    total_duration = max(1, int((w_end_dt - w_start_dt).total_seconds() / 60))
    elapsed = max(0, int((now_et - w_start_dt).total_seconds() / 60))
    progress = min(100, int(elapsed / total_duration * 100))

    return {
        "window_key": key,
        "label": window["label"],
        "strike_type": window["strike_type"],
        "description": window["description"],
        "risk_color": window["risk_color"],
        "checklist": window["checklist"],
        "time_remaining_min": remaining,
        "current_time_et": now_et.strftime("%H:%M:%S"),
        "progress_pct": progress,
    }


def _compute_fragility(regime_data: Dict, analytics_data: Optional[Any] = None) -> Dict:
    """
    Compute market fragility score (0-3 scale).

    Fragility measures how susceptible the market is to sudden, sharp moves.
    High fragility = reduce size, expect whipsaws.
    Low fragility = stable conditions, directional trades safer.

    Components:
      - IV component (0-1): elevated IV = more fragile
      - GEX component (0-1): low/negative GEX = more fragile (less dealer stabilization)
      - OI component (0-1): low OI density = thinner book, more fragile
    """
    iv_score = 0.0
    gex_score = 0.0
    oi_score = 0.0

    # IV component
    vol_regime = regime_data.get("vol_regime", "normal")
    if vol_regime == "elevated":
        iv_score = 0.9
    elif vol_regime == "compressed":
        iv_score = 0.2
    else:
        iv_score = 0.5

    # Also use IV rank if available
    iv_rank = regime_data.get("iv_percentile", 50)
    if iv_rank > 80:
        iv_score = min(1.0, iv_score + 0.1)

    # GEX component (from analytics if available)
    if analytics_data:
        net_gex = getattr(analytics_data, "net_gex", None)
        if net_gex is not None:
            # Negative GEX = high fragility (dealer hedging amplifies moves)
            if net_gex < 0:
                gex_score = 0.9
            elif net_gex < 1e9:  # < 1B = moderate
                gex_score = 0.6
            else:
                gex_score = 0.2
        else:
            gex_score = 0.5
    else:
        gex_score = 0.5

    # OI component
    if analytics_data:
        oi = getattr(analytics_data, "total_oi", None) or getattr(analytics_data, "open_interest", None)
        if oi is not None:
            # Low OI relative to typical = fragile
            if oi < 500000:
                oi_score = 0.8
            elif oi < 1000000:
                oi_score = 0.5
            else:
                oi_score = 0.2
        else:
            oi_score = 0.5
    else:
        oi_score = 0.5

    total = round(iv_score + gex_score + oi_score, 2)
    if total >= 2.2:
        level = "high"
    elif total >= 1.3:
        level = "elevated"
    elif total >= 0.7:
        level = "normal"
    else:
        level = "low"

    return {
        "score": total,
        "level": level,
        "iv_component": round(iv_score, 2),
        "gex_component": round(gex_score, 2),
        "oi_component": round(oi_score, 2),
    }


def _get_suggested_strikes(
    price: float, chain: Optional[Dict], strike_type: str
) -> Dict[str, Any]:
    """
    Get suggested call/put strikes based on current regime's strike type.

    Returns up to 3 calls and 3 puts for SPY, with delta and price info.
    """
    result = {"calls": [], "puts": [], "price": round(price, 2)}

    if not price or price <= 0 or strike_type == "NONE":
        return result

    # Determine target deltas based on regime
    if strike_type == "OTM":
        call_deltas = [0.30, 0.25, 0.20]  # 1-3 strikes OTM
        put_deltas = [0.30, 0.25, 0.20]
    elif strike_type == "ATM_ONLY":
        call_deltas = [0.50, 0.45, 0.40]  # ATM to slight OTM
        put_deltas = [0.50, 0.45, 0.40]
    else:
        return result

    for delta in call_deltas:
        try:
            s = select_strike("BUY_CALL", price, chain, target_delta=delta)
            if s.get("strike") and s["strike"] > 0:
                result["calls"].append({
                    "strike": s["strike"],
                    "delta": round(abs(s.get("delta") or delta), 2),
                    "bid": s.get("bid", 0),
                    "ask": s.get("ask", 0),
                    "mid": round((s.get("bid", 0) + s.get("ask", 0)) / 2, 2) if s.get("bid") and s.get("ask") else s.get("entry_price", 0),
                    "source": s.get("source", "estimated"),
                })
        except Exception:
            pass

    for delta in put_deltas:
        try:
            s = select_strike("BUY_PUT", price, chain, target_delta=delta)
            if s.get("strike") and s["strike"] > 0:
                result["puts"].append({
                    "strike": s["strike"],
                    "delta": round(abs(s.get("delta") or delta), 2),
                    "bid": s.get("bid", 0),
                    "ask": s.get("ask", 0),
                    "mid": round((s.get("bid", 0) + s.get("ask", 0)) / 2, 2) if s.get("bid") and s.get("ask") else s.get("entry_price", 0),
                    "source": s.get("source", "estimated"),
                })
        except Exception:
            pass

    # Deduplicate by strike price
    seen_c = set()
    result["calls"] = [c for c in result["calls"] if c["strike"] not in seen_c and not seen_c.add(c["strike"])]
    seen_p = set()
    result["puts"] = [p for p in result["puts"] if p["strike"] not in seen_p and not seen_p.add(p["strike"])]

    return result


@router.get("/volatility-advisor")
async def get_volatility_advisor():
    """
    Volatility Window Advisor.

    Returns current trading window, recommended strike type (ATM/OTM/None),
    risk tier color, active checklist, suggested strikes, fragility score,
    and real-time session context with regime and event awareness.
    """
    try:
        # 1. Current volatility window
        window = _get_current_vol_window()

        # 2. Session context from confluence engine
        session = get_session_context()
        session_dict = {
            "phase": session.phase,
            "phase_bias": session.phase_bias,
            "session_quality": session.session_quality,
            "minutes_to_close": session.minutes_to_close,
            "is_0dte": session.is_0dte,
            "past_hard_stop": session.past_hard_stop,
        }

        # 3. Regime data (IV level, vol regime) + market data for strikes
        regime_data = {}
        chain = {}
        price = 0.0
        analytics_obj = None
        try:
            market_data = await engine.fetch_market_data()
            chain = market_data.get("chain", {})
            quote = market_data.get("quote", {})
            price = quote.get("last", 0) or quote.get("price", 0)

            current_iv = 0.0
            if chain:
                calls = chain.get("calls", [])
                puts = chain.get("puts", [])
                if calls or puts:
                    try:
                        analytics_obj = analyze_options(calls, puts, price)
                        current_iv = analytics_obj.atm_iv
                    except Exception:
                        pass

            regime = await detect_regime(
                current_iv=current_iv,
                spy_bars_1m=market_data.get("bars_1m"),
            )
            regime_data = regime.to_dict()
        except Exception as e:
            logger.warning(f"Regime fetch in advisor failed: {e}")

        # 4. Event context
        event_data = {}
        try:
            evt_ctx = await get_event_context()
            next_name = evt_ctx.next_event.name if evt_ctx.next_event else None
            event_data = {
                "mode": evt_ctx.mode,
                "suppress_entries": evt_ctx.suppress_entries,
                "next_event": next_name,
                "next_event_minutes": evt_ctx.minutes_to_next if evt_ctx.minutes_to_next < 999 else None,
                "events_today_count": len(evt_ctx.events_today),
            }
            # Override risk color if pre-event suppression active
            if evt_ctx.suppress_entries:
                window["risk_color"] = "red"
                evt_label = next_name or "Event"
                mins_label = int(evt_ctx.minutes_to_next) if evt_ctx.minutes_to_next < 999 else "?"
                window["checklist"].insert(0, f"\u26a0 {evt_label} in {mins_label}min \u2014 entries suppressed")
        except Exception as e:
            logger.warning(f"Event fetch in advisor failed: {e}")

        # 5. Compute dynamic risk tier
        vol_regime = regime_data.get("vol_regime", "normal")
        risk_color = window["risk_color"]
        if vol_regime == "elevated" and window["window_key"] in ("midday_theta", "london_close"):
            risk_color = "red"
        elif vol_regime == "compressed" and window["window_key"] in ("morning_volatility", "power_hour"):
            window["strike_type"] = "ATM_ONLY"
            window["checklist"].insert(0, "IV compressed \u2014 ATM preferred over OTM")

        risk_tier = RISK_TIER_LABELS.get(risk_color, RISK_TIER_LABELS["gray"])

        # 6. Fragility score
        fragility = _compute_fragility(regime_data, analytics_obj)

        # Add fragility warning to checklist if high
        if fragility["level"] == "high":
            window["checklist"].insert(0, f"\u26a0 High fragility ({fragility['score']:.1f}/3) \u2014 reduce size, expect whipsaws")
        elif fragility["level"] == "elevated":
            window["checklist"].insert(0, f"Fragility elevated ({fragility['score']:.1f}/3) \u2014 tighter stops recommended")

        # 7. Suggested strikes based on current window's strike type
        suggested_strikes = _get_suggested_strikes(price, chain, window["strike_type"])

        return {
            "window": window,
            "risk_tier": {
                "color": risk_color,
                **risk_tier,
            },
            "fragility": fragility,
            "suggested_strikes": suggested_strikes,
            "session": session_dict,
            "regime": regime_data,
            "events": event_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Volatility advisor error: {e}", exc_info=True)
        return {"error": str(e)}


# ============================================================================
# HELPER EXPORTS
# ============================================================================

def get_latest_stored_signal() -> Optional[Dict]:
    """Get the most recent stored signal (for WebSocket broadcasts)."""
    return signal_history[-1] if signal_history else None


def get_signal_count() -> int:
    """Get total number of signals generated."""
    return len(signal_history)


# ============================================================================
# AUTONOMOUS TRADING ENDPOINTS
# ============================================================================

class AutoTradeConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    min_tier: Optional[str] = None
    min_confidence: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_trades_per_day: Optional[int] = None
    min_seconds_between_trades: Optional[int] = None
    max_hold_minutes: Optional[int] = None
    trailing_stop_pct: Optional[float] = None
    learn_from_trades: Optional[bool] = None


@router.post("/auto-trade/start")
async def start_auto_trading():
    """Enable autonomous trading. The background loop must already be running."""
    if auto_trader.is_enabled:
        return {"status": "already_enabled", "detail": "Autonomous trading is already active"}

    # Ensure the background loop is running (it should be from app startup)
    if not auto_trader.is_running:
        await auto_trader.start(signal_history)

    success = auto_trader.enable()
    if not success:
        return {"status": "error", "detail": "Failed to enable — background loop not running"}

    return {
        "status": "enabled",
        "config": auto_trader.config.to_dict(),
        "message": f"Autonomous trading enabled in {auto_trader.config.mode} mode",
    }


@router.post("/auto-trade/stop")
async def stop_auto_trading():
    """Disable autonomous trading. The background loop keeps running."""
    if not auto_trader.config.enabled:
        return {"status": "already_disabled"}

    auto_trader.disable()

    return {"status": "disabled", "message": "Autonomous trading disabled (loop still active)"}


@router.get("/auto-trade/status")
async def get_auto_trade_status():
    """Get the current status of the autonomous trader."""
    return {
        **auto_trader.status(),
        "weight_learner": weight_learner.status(),
        "training_data": training_collector.get_stats(),
        "afterhours_learner": afterhours_learner.status(),
    }


@router.post("/auto-trade/config")
async def update_auto_trade_config(req: AutoTradeConfigRequest):
    """Update autonomous trader configuration."""
    updates = req.dict(exclude_none=True)
    if not updates:
        return {"error": "No updates provided"}

    # Apply updates
    auto_trader.config.update(updates)

    # If mode changed, safely swap the paper trader (pause autotrader during swap)
    if "mode" in updates:
        global paper_trader
        was_enabled = auto_trader.config.enabled
        auto_trader.config.enabled = False  # Pause to prevent mid-trade corruption
        new_trader = PaperTrader(mode=updates["mode"])
        paper_trader = new_trader
        auto_trader.trader = new_trader
        auto_trader.config.enabled = was_enabled  # Restore previous state

    return {
        "status": "updated",
        "config": auto_trader.config.to_dict(),
    }


@router.get("/auto-trade/decisions")
async def get_auto_trade_decisions(limit: int = Query(50, ge=1, le=200)):
    """Get recent autonomous trading decisions for audit/review."""
    return {
        "decisions": auto_trader.decisions.recent(limit),
        "stats": auto_trader.decisions.stats(),
    }


# ============================================================================
# WEIGHT LEARNER ENDPOINTS
# ============================================================================

@router.get("/weights")
async def get_weights():
    """Get current factor weights (baseline vs learned)."""
    return weight_learner.status()


@router.get("/weights/importance")
async def get_factor_importance():
    """Get factor importance ranking based on trade outcomes."""
    return {
        "factors": weight_learner.get_factor_importance(),
        "version": weight_learner.get_version(),
        "trade_count": weight_learner._trade_count,
    }


@router.get("/weights/history")
async def get_weight_history(limit: int = Query(20, ge=1, le=100)):
    """Get the history of weight changes."""
    return {"history": weight_learner.get_weight_history(limit)}


@router.post("/weights/reset")
async def reset_weights():
    """Reset factor weights to baseline v5.0."""
    weight_learner.reset_to_baseline()
    refresh_weights()
    return {"status": "reset", "weights": weight_learner.get_current_weights()}


@router.post("/weights/learning-rate")
async def set_learning_rate(rate: float = Query(..., ge=0.001, le=0.20)):
    """Adjust the learning rate (0.01-0.10 recommended)."""
    weight_learner.set_learning_rate(rate)
    return {"status": "updated", "learning_rate": rate}


# ============================================================================
# TRAINING DATA ENDPOINTS
# ============================================================================

@router.get("/training-data/stats")
async def get_training_stats():
    """Get training data collection statistics."""
    return training_collector.get_stats()


@router.get("/training-data/samples")
async def get_training_samples(
    limit: int = Query(100, ge=1, le=1000),
    traded_only: bool = Query(True),
):
    """Get training data samples for analysis or ML pipeline."""
    return {
        "samples": training_collector.get_training_data(traded_only=traded_only, limit=limit),
        "stats": training_collector.get_stats(),
    }


# ============================================================================
# AFTER-HOURS LEARNING ENDPOINTS
# ============================================================================

@router.get("/learning/status")
async def get_learning_status():
    """Get the after-hours learner status and latest report."""
    return afterhours_learner.status()


@router.get("/learning/report")
async def get_latest_learning_report():
    """Get the most recent daily learning report."""
    report = afterhours_learner.get_latest_report()
    return {"report": report} if report else {"report": None, "message": "No analysis yet"}


@router.get("/learning/history")
async def get_learning_history(limit: int = Query(30, ge=1, le=365)):
    """Get historical daily learning reports for trend analysis."""
    return {"reports": afterhours_learner.get_report_history(limit)}


@router.get("/learning/factor-trend/{factor_name}")
async def get_factor_trend(factor_name: str, days: int = Query(30, ge=1, le=365)):
    """Get a specific factor's edge trend over recent days."""
    return {"factor": factor_name, "trend": afterhours_learner.get_factor_trend(factor_name, days)}


@router.get("/learning/insights")
async def get_learning_insights(days: int = Query(7, ge=1, le=90)):
    """Get human-readable learning insights from the last N days."""
    return {"insights": afterhours_learner.get_cumulative_insights(days)}


@router.post("/learning/run-now")
async def force_learning_analysis():
    """Manually trigger after-hours analysis for today (useful for testing)."""
    from datetime import date
    report = await afterhours_learner.run_daily_analysis(date.today().isoformat())
    if report:
        return {"status": "complete", "report": report.to_dict()}
    return {"status": "skipped", "reason": "Not enough trades for analysis"}


# ============================================================================
# STARTUP / SHUTDOWN HOOKS FOR AUTONOMOUS TRADER
# ============================================================================

async def start_auto_trader_loop():
    """Called from app.py startup to initialize the auto-trader and after-hours learner."""
    # Don't auto-enable — user must explicitly start via API or UI
    await auto_trader.start(signal_history)
    logger.info("Autonomous trader loop initialized (waiting for enable)")

    # Start after-hours learning loop (runs post-4PM ET automatically)
    await afterhours_learner.start()
    logger.info("After-hours learning loop initialized")


async def stop_auto_trader_loop():
    """Called from app.py shutdown to stop the auto-trader and after-hours learner."""
    await auto_trader.stop()
    await afterhours_learner.stop()
    logger.info("Autonomous trader loop and after-hours learner stopped")
