"""
Options Flow Scanner — Institutional flow detection across multiple symbols.

NOT a raw trade dump. This scanner:
1. Aggregates fragmented orders (same strike+right+side within 1s = one order)
2. Filters ask-side only (aggressive buying = conviction)
3. Requires $100K+ premium minimum (kills retail noise)
4. Tracks repeat accumulation (same contract hit 5+ times = strong conviction)
5. Scores each alert by premium + sweep + aggression + repeat count
6. Targets 5-15 high-quality alerts per day, not 500 raw fills
"""

import asyncio
import logging
import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Top liquid option symbols to scan
SCANNER_SYMBOLS = [
    "SPY", "QQQ", "AAPL", "TSLA", "NVDA",
    "AMZN", "META", "MSFT", "GOOGL", "AMD",
]

STRIKES_AROUND_ATM = 5

# ── Filter thresholds ────────────────────────────────────────────────────────
MIN_ALERT_PREMIUM = 100_000     # $100K minimum for any alert
MIN_SWEEP_FILLS = 3             # 3+ fills across exchanges = sweep
SWEEP_WINDOW_SEC = 1.0          # Time window for sweep aggregation
REPEAT_THRESHOLD = 5            # 5+ hits on same contract = repeat accumulation
REPEAT_WINDOW_SEC = 300         # 5-minute window for repeat detection
COOLDOWN_SEC = 30               # Min 30s between alerts for same contract


@dataclass
class FlowAlert:
    """A scored, aggregated unusual flow event."""
    id: str = ""
    timestamp: str = ""
    symbol: str = ""
    alert_type: str = ""        # 'sweep', 'block', 'whale', 'repeat'
    direction: str = ""         # 'bullish', 'bearish'
    strike: float = 0
    right: str = ""
    expiration: int = 0
    size: int = 0               # Total aggregated contracts
    premium: float = 0          # Total aggregated premium
    avg_price: float = 0        # Volume-weighted avg fill price
    fills: int = 0              # Number of fills aggregated
    side: str = ""              # 'buy' (ask-side only in filtered mode)
    score: int = 0              # 0-100 quality score
    repeat_count: int = 0       # How many times this contract was hit today
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FlowScanner:
    """Smart options flow scanner with aggregation, filtering, and scoring."""

    def __init__(self):
        self._alerts: deque = deque(maxlen=200)
        self._symbol_prices: Dict[str, float] = {}
        self._subscribed_symbols: Set[str] = set()
        self._broadcast_fn = None

        # Order aggregation: key = "SYM-STRIKE-RIGHT-SIDE" → list of fills within 1s
        self._agg_buffer: Dict[str, List[Dict]] = defaultdict(list)

        # Repeat accumulation: key = "SYM-STRIKE-RIGHT" → list of (timestamp, size, premium)
        self._repeat_tracker: Dict[str, List[Tuple[float, int, float]]] = defaultdict(list)

        # Cooldown: key = "SYM-STRIKE-RIGHT" → last alert timestamp
        self._last_alert_ts: Dict[str, float] = {}

        # Daily stats
        self._total_trades_seen = 0
        self._total_premium_seen = 0.0
        self._alerts_today = 0

    def set_broadcast(self, fn):
        self._broadcast_fn = fn

    def update_price(self, symbol: str, price: float):
        if price > 0:
            self._symbol_prices[symbol] = price

    async def subscribe_symbol(self, theta_stream, symbol: str, expiration: int):
        price = self._symbol_prices.get(symbol, 0)
        if price <= 0:
            logger.warning(f"[Scanner] No price for {symbol}, skipping")
            return

        atm = round(price)
        spacing = 1 if symbol in ("SPY", "QQQ", "IWM") else 2.5 if price > 200 else 1
        strikes = [int(atm + i * spacing) for i in range(-STRIKES_AROUND_ATM, STRIKES_AROUND_ATM + 1)]

        await theta_stream.subscribe_trades_per_contract(
            root=symbol, expiration=expiration, strikes=strikes, rights=["C", "P"],
        )
        self._subscribed_symbols.add(symbol)
        logger.info(f"[Scanner] Subscribed {symbol} @ ${price:.2f}: {len(strikes)*2} contracts")

    async def subscribe_all(self, theta_stream):
        from datetime import date
        today = int(date.today().strftime("%Y%m%d"))
        for symbol in SCANNER_SYMBOLS:
            if symbol in self._subscribed_symbols:
                continue
            try:
                await self.subscribe_symbol(theta_stream, symbol, today)
            except Exception as e:
                logger.warning(f"[Scanner] Failed to subscribe {symbol}: {e}")
        logger.info(f"[Scanner] Subscribed to {len(self._subscribed_symbols)} symbols")

    def on_trade(self, event: dict):
        """Process a theta_trade event. Aggregates before alerting."""
        root = event.get("root", "")
        if root not in self._subscribed_symbols and root != "SPY":
            return

        strike = event.get("strike", 0)
        right = event.get("right", "")
        size = event.get("size", 0)
        price = event.get("price", 0)
        side = event.get("side", "mid")
        premium = price * size * 100

        if size <= 0 or price <= 0:
            return

        self._total_trades_seen += 1
        self._total_premium_seen += premium

        # FILTER 1: Ask-side only (aggressive buying = conviction)
        # Include 'buy' (at ask) and 'sell' (at bid, could be put buying which is bearish)
        # Skip 'mid' — ambiguous, often market maker hedging
        if side == "mid":
            return

        now = time.time()

        # Aggregate fills: same contract + same side within 1 second
        agg_key = f"{root}-{strike}-{right}-{side}"
        buf = self._agg_buffer[agg_key]

        # Flush old entries
        buf[:] = [f for f in buf if now - f["ts"] < SWEEP_WINDOW_SEC]
        buf.append({"ts": now, "size": size, "premium": premium, "price": price})

        # Track repeat accumulation (broader: any side, 5-min window)
        repeat_key = f"{root}-{strike}-{right}"
        repeats = self._repeat_tracker[repeat_key]
        repeats[:] = [(t, s, p) for t, s, p in repeats if now - t < REPEAT_WINDOW_SEC]
        repeats.append((now, size, premium))

        # Check if aggregated order crosses alert threshold
        total_premium = sum(f["premium"] for f in buf)
        total_size = sum(f["size"] for f in buf)

        # FILTER 2: Min $100K premium (aggregated)
        if total_premium < MIN_ALERT_PREMIUM:
            return

        # FILTER 3: Cooldown — no repeat alerts for same contract within 30s
        last_alert = self._last_alert_ts.get(agg_key, 0)
        if now - last_alert < COOLDOWN_SEC:
            return

        # Determine alert type
        num_fills = len(buf)
        is_sweep = num_fills >= MIN_SWEEP_FILLS
        is_block = num_fills == 1 and total_size >= 100
        repeat_count = len(repeats)
        is_repeat = repeat_count >= REPEAT_THRESHOLD

        if is_sweep:
            alert_type = "sweep"
        elif is_block:
            alert_type = "block"
        elif is_repeat:
            alert_type = "repeat"
        else:
            alert_type = "whale"  # Large premium, few fills

        # Direction inference
        if right == "C":
            direction = "bullish" if side == "buy" else "bearish"
        else:
            direction = "bearish" if side == "buy" else "bullish"

        # Score the alert (0-100)
        score = self._score_alert(
            premium=total_premium,
            is_sweep=is_sweep,
            side=side,
            repeat_count=repeat_count,
            strike=strike,
            symbol=root,
            right=right,
        )

        # Compute avg fill price
        total_value = sum(f["price"] * f["size"] for f in buf)
        avg_price = total_value / total_size if total_size > 0 else price

        # Build detail string
        premium_str = f"${total_premium/1000:.0f}K" if total_premium < 1_000_000 else f"${total_premium/1_000_000:.1f}M"
        repeat_str = f" | {repeat_count}x repeat" if repeat_count >= 3 else ""
        type_str = "SWEEP" if is_sweep else "BLOCK" if is_block else "REPEAT" if is_repeat else "LARGE"

        detail = (
            f"{type_str} {premium_str} {side.upper()} {total_size}x "
            f"{root} ${strike}{right} @ ${avg_price:.2f}"
            f" ({num_fills} fills){repeat_str}"
        )

        now_str = datetime.now(_ET).strftime("%H%M%S")
        alert = FlowAlert(
            id=f"{alert_type}-{root}-{now_str}-{strike}{right}",
            timestamp=datetime.now(_ET).isoformat(),
            symbol=root,
            alert_type=alert_type,
            direction=direction,
            strike=strike,
            right=right,
            expiration=event.get("expiration", 0),
            size=total_size,
            premium=total_premium,
            avg_price=round(avg_price, 2),
            fills=num_fills,
            side=side,
            score=score,
            repeat_count=repeat_count,
            detail=detail,
        )

        self._emit_alert(alert)
        self._last_alert_ts[agg_key] = now
        buf.clear()  # Reset aggregation after alert

    def _score_alert(
        self, premium: float, is_sweep: bool, side: str, repeat_count: int,
        strike: float, symbol: str, right: str,
    ) -> int:
        """
        Score 0-100 based on multiple factors:
        - Premium size (0-30): log-scaled, $100K=10, $500K=20, $1M+=30
        - Sweep (0-20): multi-exchange routing = urgency
        - Aggression (0-15): ask-side buy = maximum conviction
        - Repeat accumulation (0-25): 5x=10, 10x=20, 15x+=25
        - OTM distance (0-10): further OTM = more directional conviction
        """
        score = 0

        # Premium size (log-scaled, 0-30)
        if premium > 0:
            score += min(30, int(math.log10(premium / 10_000) * 10))

        # Sweep bonus (0-20)
        if is_sweep:
            score += 20

        # Aggression (0-15)
        if side == "buy":
            score += 15  # At ask
        elif side == "sell":
            score += 10  # At bid (still aggressive)

        # Repeat accumulation (0-25)
        if repeat_count >= 15:
            score += 25
        elif repeat_count >= 10:
            score += 20
        elif repeat_count >= 5:
            score += 10
        elif repeat_count >= 3:
            score += 5

        # OTM distance bonus (0-10)
        underlying = self._symbol_prices.get(symbol, 0)
        if underlying > 0 and strike > 0:
            if right == "C":
                otm_pct = (strike - underlying) / underlying * 100
            else:
                otm_pct = (underlying - strike) / underlying * 100
            if otm_pct > 5:
                score += 10  # Deep OTM = conviction
            elif otm_pct > 2:
                score += 5
            elif otm_pct > 0:
                score += 2

        return min(100, max(0, score))

    def _emit_alert(self, alert: FlowAlert):
        self._alerts.append(alert)
        self._alerts_today += 1
        logger.info(f"[Scanner] [{alert.score}] {alert.detail}")

        if self._broadcast_fn:
            try:
                asyncio.get_event_loop().create_task(
                    self._broadcast_fn({
                        "type": "flow_alert",
                        "alert": alert.to_dict(),
                    })
                )
            except Exception:
                pass

    def get_recent_alerts(self, limit: int = 50) -> List[Dict]:
        # Return sorted by score (highest first)
        alerts = [a.to_dict() for a in self._alerts]
        alerts.sort(key=lambda x: x.get("score", 0), reverse=True)
        return alerts[:limit]

    def get_stats(self) -> Dict:
        return {
            "subscribed_symbols": sorted(self._subscribed_symbols),
            "total_alerts": self._alerts_today,
            "total_trades_seen": self._total_trades_seen,
            "total_premium_seen": round(self._total_premium_seen),
            "symbol_prices": {k: round(v, 2) for k, v in self._symbol_prices.items()},
        }


# Singleton
flow_scanner = FlowScanner()
