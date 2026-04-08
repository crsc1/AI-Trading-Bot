"""
Options Flow Scanner — Multi-symbol unusual activity detection.

Subscribes to ATM options for the top liquid symbols via ThetaData WS.
Detects sweeps, whale trades, unusual volume, and premium spikes.
Broadcasts alerts to the frontend in real-time.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Top liquid option symbols to scan
SCANNER_SYMBOLS = [
    "SPY", "QQQ", "AAPL", "TSLA", "NVDA",
    "AMZN", "META", "MSFT", "GOOGL", "AMD",
]

# How many strikes around ATM per symbol (±N)
STRIKES_AROUND_ATM = 5

# Alert thresholds
MIN_SWEEP_SIZE = 50          # Contracts for sweep alert
MIN_WHALE_PREMIUM = 50_000   # $50K premium for whale alert
MIN_BLOCK_SIZE = 100         # 100+ contracts single print
UNUSUAL_VOLUME_MULT = 3.0    # 3x normal volume = unusual


@dataclass
class FlowAlert:
    """A single unusual flow event detected by the scanner."""
    id: str = ""
    timestamp: str = ""
    symbol: str = ""
    alert_type: str = ""      # 'sweep', 'whale', 'block', 'unusual_volume'
    direction: str = ""       # 'bullish', 'bearish'
    strike: float = 0
    right: str = ""           # 'C' or 'P'
    expiration: int = 0
    size: int = 0
    premium: float = 0
    price: float = 0
    side: str = ""            # 'buy', 'sell', 'mid'
    detail: str = ""          # Human-readable description

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FlowScanner:
    """
    Scans multiple symbols for unusual options activity.
    Subscribes to ThetaData WS for real-time trades.
    """

    def __init__(self):
        self._alerts: deque = deque(maxlen=500)
        self._symbol_prices: Dict[str, float] = {}  # symbol → last known price
        self._symbol_volumes: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # symbol → {strike_right → cumulative volume} for unusual volume detection
        self._sweep_buffer: Dict[str, List[Dict]] = defaultdict(list)
        # symbol → recent trades for sweep detection (same strike+right within 500ms)
        self._subscribed_symbols: Set[str] = set()
        self._running = False
        self._broadcast_fn = None

    def set_broadcast(self, fn):
        """Set the broadcast function for sending alerts to frontend."""
        self._broadcast_fn = fn

    def update_price(self, symbol: str, price: float):
        """Update underlying price for a symbol (for ATM strike calculation)."""
        if price > 0:
            self._symbol_prices[symbol] = price

    async def subscribe_symbol(self, theta_stream, symbol: str, expiration: int):
        """Subscribe to ATM ± STRIKES_AROUND_ATM for a symbol."""
        price = self._symbol_prices.get(symbol, 0)
        if price <= 0:
            logger.warning(f"[Scanner] No price for {symbol}, skipping subscription")
            return

        # Calculate ATM strikes
        atm = round(price)
        # Determine strike spacing (SPY/QQQ = $1, others vary)
        spacing = 1 if symbol in ("SPY", "QQQ", "IWM") else 2.5 if price > 200 else 1
        strikes = [int(atm + i * spacing) for i in range(-STRIKES_AROUND_ATM, STRIKES_AROUND_ATM + 1)]

        await theta_stream.subscribe_trades_per_contract(
            root=symbol,
            expiration=expiration,
            strikes=strikes,
            rights=["C", "P"],
        )

        self._subscribed_symbols.add(symbol)
        logger.info(
            f"[Scanner] Subscribed {symbol} @ ${price:.2f}: "
            f"{len(strikes)} strikes × 2 rights = {len(strikes) * 2} contracts"
        )

    async def subscribe_all(self, theta_stream):
        """Subscribe to all scanner symbols. Call after prices are known."""
        from datetime import date
        today = int(date.today().strftime("%Y%m%d"))

        for symbol in SCANNER_SYMBOLS:
            if symbol in self._subscribed_symbols:
                continue
            try:
                await self.subscribe_symbol(theta_stream, symbol, today)
            except Exception as e:
                logger.warning(f"[Scanner] Failed to subscribe {symbol}: {e}")

        total = sum(1 for _ in self._subscribed_symbols)
        logger.info(f"[Scanner] Subscribed to {total} symbols")

    def on_trade(self, event: dict):
        """
        Process a theta_trade event from the WS stream.
        Detect sweeps, whales, blocks, unusual volume.
        """
        root = event.get("root", "")
        if root not in self._subscribed_symbols and root != "SPY":
            return  # SPY always processed (even before scanner subscribes)

        strike = event.get("strike", 0)
        right = event.get("right", "")
        size = event.get("size", 0)
        price = event.get("price", 0)
        side = event.get("side", "mid")
        premium = price * size * 100

        if size <= 0 or price <= 0:
            return

        # Direction inference
        if right == "C":
            direction = "bullish" if side == "buy" else "bearish" if side == "sell" else "neutral"
        else:
            direction = "bearish" if side == "buy" else "bullish" if side == "sell" else "neutral"

        now = time.time()
        now_str = datetime.now(_ET).strftime("%H:%M:%S")

        # Track cumulative volume per strike
        vol_key = f"{strike}{right}"
        self._symbol_volumes[root][vol_key] += size

        # ── Whale detection: single trade with $50K+ premium ──
        if premium >= MIN_WHALE_PREMIUM:
            alert = FlowAlert(
                id=f"whale-{root}-{now_str}-{strike}{right}",
                timestamp=datetime.now(_ET).isoformat(),
                symbol=root,
                alert_type="whale",
                direction=direction,
                strike=strike,
                right=right,
                expiration=event.get("expiration", 0),
                size=size,
                premium=premium,
                price=price,
                side=side,
                detail=f"${premium/1000:.0f}K {side.upper()} {size}x {root} ${strike}{right} @ ${price:.2f}",
            )
            self._emit_alert(alert)

        # ── Block detection: 100+ contract single print ──
        elif size >= MIN_BLOCK_SIZE:
            alert = FlowAlert(
                id=f"block-{root}-{now_str}-{strike}{right}",
                timestamp=datetime.now(_ET).isoformat(),
                symbol=root,
                alert_type="block",
                direction=direction,
                strike=strike,
                right=right,
                expiration=event.get("expiration", 0),
                size=size,
                premium=premium,
                price=price,
                side=side,
                detail=f"{size}x {root} ${strike}{right} {side.upper()} @ ${price:.2f} (${premium/1000:.0f}K)",
            )
            self._emit_alert(alert)

        # ── Sweep detection: multiple fills same strike within 500ms ──
        sweep_key = f"{root}-{strike}-{right}-{side}"
        buf = self._sweep_buffer[sweep_key]
        buf.append({"ts": now, "size": size, "premium": premium, "price": price})
        # Clean old entries
        buf[:] = [t for t in buf if now - t["ts"] < 0.5]

        if len(buf) >= 3:  # 3+ fills in 500ms = sweep
            total_size = sum(t["size"] for t in buf)
            total_premium = sum(t["premium"] for t in buf)
            if total_size >= MIN_SWEEP_SIZE:
                alert = FlowAlert(
                    id=f"sweep-{root}-{now_str}-{strike}{right}",
                    timestamp=datetime.now(_ET).isoformat(),
                    symbol=root,
                    alert_type="sweep",
                    direction=direction,
                    strike=strike,
                    right=right,
                    expiration=event.get("expiration", 0),
                    size=total_size,
                    premium=total_premium,
                    price=price,
                    side=side,
                    detail=f"SWEEP {total_size}x {root} ${strike}{right} {side.upper()} ({len(buf)} fills, ${total_premium/1000:.0f}K)",
                )
                self._emit_alert(alert)
                buf.clear()  # Reset after alert

    def _emit_alert(self, alert: FlowAlert):
        """Store alert and broadcast to frontend."""
        self._alerts.append(alert)
        logger.info(f"[Scanner] {alert.alert_type.upper()}: {alert.detail}")

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
        """Return recent alerts for REST API."""
        return [a.to_dict() for a in reversed(list(self._alerts))][:limit]

    def get_stats(self) -> Dict:
        return {
            "subscribed_symbols": sorted(self._subscribed_symbols),
            "total_alerts": len(self._alerts),
            "symbol_prices": {k: round(v, 2) for k, v in self._symbol_prices.items()},
        }


# Singleton
flow_scanner = FlowScanner()
