"""
Position Tracker — Real-time P&L monitoring with Greeks decomposition.

Watches open trades and provides:
  - Live unrealized P&L (mark-to-market)
  - MFE / MAE tracking (max favorable/adverse excursion)
  - Greeks P&L decomposition (how much came from delta, gamma, theta, vega)
  - Auto-exit on stop-loss, profit-target, or time-stop triggers
  - Portfolio-level risk metrics

Data sources:
  - Simulation mode: Black-Scholes repricing via utils/greeks.py
  - Alpaca mode: Live position data from Alpaca paper account

Does NOT interfere with Alpaca or execute any trades directly.
Exit decisions are returned to the caller (paper_trader) for execution.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .signal_db import get_open_trades

logger = logging.getLogger(__name__)


class PositionTracker:
    """
    Tracks open positions and computes real-time P&L metrics.

    Uses REAL chain mid-prices (bid+ask)/2 when available.
    Falls back to Black-Scholes only when no live chain data exists.

    Usage:
        tracker = PositionTracker()
        tracker.update_chain_prices(chain_data)  # Feed live chain
        positions = tracker.get_live_positions(current_price, current_iv)
    """

    def __init__(self):
        import time
        self._price_cache: Dict[str, float] = {}   # trade_id -> last known price
        self._chain_cache: Dict[str, Any] = {}      # "calls"/"puts" -> list of chain entries
        self._chain_update_time: float = time.time()  # Init to now so first lookup doesn't reject as stale

    def update_chain_prices(self, chain: Dict):
        """
        Feed live options chain data for real mid-price lookups.

        Args:
            chain: Dict with "calls" and "puts" lists, each entry having
                   at minimum: strike, bid, ask, last, delta, gamma, theta, vega, iv
        """
        if chain:
            self._chain_cache = chain
            import time
            self._chain_update_time = time.time()

    def _lookup_chain_price(self, strike: float, option_type: str) -> Optional[Dict]:
        """
        Look up a specific option in the live chain cache.

        Returns dict with mid, bid, ask, last, delta, gamma, theta, vega, iv
        or None if not found.
        """
        import time
        # Chain data older than 60 seconds is stale (ThetaData snapshots refresh every 15s)
        if time.time() - self._chain_update_time > 60:
            return None

        side = "calls" if option_type.lower() in ("call", "c") else "puts"
        options = self._chain_cache.get(side, [])

        if not options:
            return None

        # Find matching strike (within $0.01 tolerance)
        for opt in options:
            opt_strike = opt.get("strike", 0)
            if abs(opt_strike - strike) < 0.01:
                bid = opt.get("bid", 0) or 0
                ask = opt.get("ask", 0) or 0
                last = opt.get("last", 0) or 0

                # Compute mid price
                if bid > 0 and ask > 0:
                    mid = (bid + ask) / 2
                elif last > 0:
                    mid = last
                else:
                    return None

                return {
                    "mid": mid,
                    "bid": bid,
                    "ask": ask,
                    "last": last,
                    "delta": opt.get("delta"),
                    "gamma": opt.get("gamma"),
                    "theta": opt.get("theta"),
                    "vega": opt.get("vega"),
                    "iv": opt.get("iv"),
                    "volume": opt.get("volume", 0),
                    "open_interest": opt.get("open_interest", 0),
                }

        return None

    def get_live_positions(
        self,
        current_price: float = 0.0,
        current_iv: float = 0.0,
    ) -> List[Dict]:
        """
        Get all open positions with live P&L calculations.

        Uses real chain mid-prices when available, falls back to Black-Scholes.

        Args:
            current_price: Current underlying price (SPY)
            current_iv: Current ATM implied volatility

        Returns:
            List of position dicts with P&L metrics
        """
        open_trades = get_open_trades()
        positions = []

        for trade in open_trades:
            pos = self._compute_position(trade, current_price, current_iv)
            positions.append(pos)

        return positions

    def _compute_position(
        self,
        trade: Dict,
        underlying_price: float,
        current_iv: float = 0.0,
    ) -> Dict:
        """Compute live P&L for a single position using real chain prices first."""

        entry_price = trade.get("entry_price", 0) or 0
        quantity = trade.get("quantity", 1) or 1
        strike = trade.get("strike", 0) or 0
        option_type = trade.get("option_type", "call")
        mode = trade.get("mode", "simulation")

        # PRIORITY 1: Real chain mid-price (most accurate)
        chain_data = self._lookup_chain_price(strike, option_type)
        price_source = "unknown"

        if chain_data and chain_data["mid"] > 0:
            current_option_price = chain_data["mid"]
            price_source = "chain_mid"
            # Cache it for autotrader exit checks
            self._price_cache[trade.get("id", "")] = current_option_price
        # PRIORITY 2: Black-Scholes theoretical (simulation fallback)
        elif underlying_price > 0 and strike > 0:
            current_option_price = self._reprice_option(
                underlying_price=underlying_price,
                strike=strike,
                option_type=option_type,
                entry_time=trade.get("entry_time"),
                iv=current_iv or 0.20,
            )
            price_source = "black_scholes"
        else:
            # PRIORITY 3: Cached price or entry price
            current_option_price = self._price_cache.get(
                trade.get("id", ""), entry_price
            )
            price_source = "cached"

        # P&L calculations
        pnl_per_contract = (current_option_price - entry_price) * 100
        total_pnl = pnl_per_contract * quantity
        pnl_pct = ((current_option_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        # MFE / MAE tracking
        max_favorable = trade.get("max_favorable", 0) or 0
        max_adverse = trade.get("max_adverse", 0) or 0

        if total_pnl > max_favorable:
            max_favorable = total_pnl
        if total_pnl < 0 and abs(total_pnl) > max_adverse:
            max_adverse = abs(total_pnl)

        # Hold time
        hold_minutes = 0
        try:
            entry_dt = datetime.fromisoformat(trade.get("entry_time", ""))
            hold_minutes = (datetime.now(timezone.utc) - entry_dt).total_seconds() / 60
        except (ValueError, TypeError):
            pass

        # Greeks decomposition (if we have entry greeks)
        greeks_pnl = self._decompose_greeks_pnl(
            trade, underlying_price, current_option_price, hold_minutes
        )

        # Live greeks from chain (if available)
        live_greeks = {}
        if chain_data:
            live_greeks = {
                "delta": chain_data.get("delta"),
                "gamma": chain_data.get("gamma"),
                "theta": chain_data.get("theta"),
                "vega": chain_data.get("vega"),
                "iv": chain_data.get("iv"),
            }

        return {
            "trade_id": trade.get("id"),
            "signal_id": trade.get("signal_id"),
            "mode": mode,
            "symbol": trade.get("symbol", "SPY"),
            "strike": strike,
            "expiry": trade.get("expiry"),
            "option_type": option_type,
            "quantity": quantity,
            "entry_price": entry_price,
            "current_price": round(current_option_price, 4),
            "underlying_price": underlying_price,

            # P&L
            "unrealized_pnl": round(total_pnl, 2),
            "unrealized_pnl_pct": round(pnl_pct, 2),
            "pnl_per_contract": round(pnl_per_contract, 2),

            # Excursions
            "max_favorable": round(max_favorable, 2),
            "max_adverse": round(max_adverse, 2),

            # Time
            "entry_time": trade.get("entry_time"),
            "hold_minutes": round(hold_minutes, 1),

            # Greeks P&L
            "greeks_pnl": greeks_pnl,

            # Live greeks from chain
            "live_greeks": live_greeks,

            # Pricing source: "chain_mid", "black_scholes", "cached"
            "price_source": price_source,

            # Bid/ask spread info for transparency
            "bid": chain_data.get("bid") if chain_data else None,
            "ask": chain_data.get("ask") if chain_data else None,

            # Risk levels from signal
            "target_price": trade.get("target_price"),
            "stop_price": trade.get("stop_price"),
        }

    def update_mfe_mae(self, trade_id: str, current_pnl: float):
        """
        Update MFE/MAE in the database for a specific trade.
        Called periodically during position monitoring.
        """
        from .signal_db import _get_conn

        conn = _get_conn()
        row = conn.execute(
            "SELECT max_favorable, max_adverse FROM trades WHERE id = ?",
            (trade_id,)
        ).fetchone()

        if not row:
            conn.close()
            return

        mfe = max(row["max_favorable"] or 0, current_pnl if current_pnl > 0 else 0)
        mae = max(row["max_adverse"] or 0, abs(current_pnl) if current_pnl < 0 else 0)

        conn.execute(
            "UPDATE trades SET max_favorable = ?, max_adverse = ? WHERE id = ?",
            (round(mfe, 2), round(mae, 2), trade_id),
        )
        conn.commit()
        conn.close()

    def check_exit_triggers(
        self,
        positions: List[Dict],
    ) -> List[Dict]:
        """
        Check all open positions for exit triggers.

        Returns list of trades that should be closed, with exit reason.
        The caller (paper_trader) handles actual execution.
        """
        exits = []

        for pos in positions:
            exit_reason = self._should_exit(pos)
            if exit_reason:
                exits.append({
                    "trade_id": pos["trade_id"],
                    "trade": pos,
                    "exit_price": pos["current_price"],
                    "exit_reason": exit_reason,
                })

        return exits

    def _should_exit(self, pos: Dict) -> Optional[str]:
        """
        Determine if a position should be exited.

        Exit conditions (checked in priority order):
          1. Stop-loss hit
          2. Profit target hit
          3. Time stop (0DTE hard stop at 3:00 PM ET)
          4. Max hold time exceeded (60 min for 0DTE)
          5. Theta decay threshold (option lost >50% of entry value)
        """
        current_price = pos.get("current_price", 0)
        entry_price = pos.get("entry_price", 0)

        if not current_price or not entry_price:
            return None

        # ── 1. Stop-loss ──
        stop_price = pos.get("stop_price")
        if stop_price and current_price <= stop_price:
            return "stop_loss"

        # ── 2. Profit target ──
        target_price = pos.get("target_price")
        if target_price and current_price >= target_price:
            return "profit_target"

        # ── 3. Time stop (0DTE hard stop) ──
        from datetime import timedelta
        try:
            from zoneinfo import ZoneInfo
            ET = ZoneInfo("America/New_York")
        except ImportError:
            ET = timezone(timedelta(hours=-4))

        try:
            now_et = datetime.now(ET)
            from .confluence import ZERO_DTE_HARD_STOP
            if now_et.time() >= ZERO_DTE_HARD_STOP:
                return "time_stop_0dte"
        except Exception:
            pass

        # ── 4. Max hold time (60 min for aggressive 0DTE management) ──
        hold_minutes = pos.get("hold_minutes", 0)
        if hold_minutes > 60:
            return "max_hold_time"

        # ── 5. Theta decay threshold ──
        pnl_pct = pos.get("unrealized_pnl_pct", 0)
        if pnl_pct < -50:  # Lost more than 50% of entry value
            return "theta_decay"

        return None

    def _reprice_option(
        self,
        underlying_price: float,
        strike: float,
        option_type: str,
        entry_time: Optional[str] = None,
        iv: float = 0.20,
    ) -> float:
        """
        Reprice an option using Black-Scholes.

        Uses utils/greeks.py's calculate_theoretical_price for consistent pricing.
        """
        try:
            from utils.greeks import calculate_theoretical_price

            # Time to expiration in years (0DTE = remainder of today)
            now = datetime.now(timezone.utc)
            # For 0DTE: assume market closes at 4 PM ET = 20:00 UTC
            market_close_utc = now.replace(hour=20, minute=0, second=0, microsecond=0)
            if now >= market_close_utc:
                t_years = 1 / (365 * 24 * 60)  # ~1 minute minimum
            else:
                remaining_seconds = (market_close_utc - now).total_seconds()
                t_years = max(remaining_seconds / (365.25 * 24 * 3600), 1e-6)

            opt_type = "C" if option_type.lower() in ("call", "c") else "P"
            r = 0.05  # Risk-free rate approximation

            price = calculate_theoretical_price(
                S=underlying_price,
                K=strike,
                T=t_years,
                r=r,
                sigma=iv,
                option_type=opt_type,
            )
            return max(price, 0.01)  # Floor at 1 cent

        except Exception as e:
            logger.debug(f"Repricing fallback: {e}")
            # Intrinsic value fallback
            if option_type.lower() in ("call", "c"):
                return max(underlying_price - strike, 0.01)
            else:
                return max(strike - underlying_price, 0.01)

    def _decompose_greeks_pnl(
        self,
        trade: Dict,
        current_underlying: float,
        current_option_price: float,
        hold_minutes: float,
    ) -> Dict:
        """
        Decompose P&L into Greeks components.

        This is approximate — shows how much of the P&L came from:
          - Delta: price movement
          - Gamma: convexity (acceleration)
          - Theta: time decay
          - Vega: IV change
        """
        import json

        greeks_raw = trade.get("greeks_at_entry", "{}")
        if isinstance(greeks_raw, str):
            try:
                greeks = json.loads(greeks_raw)
            except (json.JSONDecodeError, TypeError):
                greeks = {}
        else:
            greeks = greeks_raw or {}
        # Guard: json.loads("somestring") returns a str, not a dict
        if not isinstance(greeks, dict):
            greeks = {}

        delta = greeks.get("delta") or 0
        greeks.get("gamma") or 0
        theta = greeks.get("theta") or 0
        greeks.get("vega") or 0

        entry_price = trade.get("entry_price", 0)
        strike = trade.get("strike", 0)
        quantity = trade.get("quantity", 1)

        # Price change in underlying (approximation)
        # We don't know the exact underlying at entry, so estimate from strike + delta
        total_pnl = (current_option_price - entry_price) * 100 * quantity

        result = {
            "total_pnl": round(total_pnl, 2),
            "delta_pnl": None,
            "gamma_pnl": None,
            "theta_pnl": None,
            "vega_pnl": None,
        }

        if not delta:
            return result

        # Delta P&L approximation (requires knowing underlying move)
        # We'll estimate based on option price change and delta
        if current_underlying > 0 and strike > 0:
            # Rough underlying move since entry
            # This is an approximation since we don't store entry underlying price
            days_held = hold_minutes / (60 * 6.5)  # Trading hours per day

            result["theta_pnl"] = round(theta * days_held * 100 * quantity, 2) if theta else None

        return result

    def get_portfolio_summary(
        self,
        positions: List[Dict],
    ) -> Dict:
        """
        Compute portfolio-level metrics across all open positions.
        """
        if not positions:
            return {
                "open_count": 0,
                "total_unrealized_pnl": 0,
                "total_cost_basis": 0,
                "calls_count": 0,
                "puts_count": 0,
                "avg_hold_minutes": 0,
                "worst_position": None,
                "best_position": None,
            }

        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)
        total_cost = sum(
            (p.get("entry_price", 0) * p.get("quantity", 1) * 100)
            for p in positions
        )
        calls = [p for p in positions if p.get("option_type") == "call"]
        puts = [p for p in positions if p.get("option_type") == "put"]
        hold_times = [p.get("hold_minutes", 0) for p in positions]

        sorted_by_pnl = sorted(positions, key=lambda p: p.get("unrealized_pnl", 0))
        worst = sorted_by_pnl[0] if sorted_by_pnl else None
        best = sorted_by_pnl[-1] if sorted_by_pnl else None

        return {
            "open_count": len(positions),
            "total_unrealized_pnl": round(total_pnl, 2),
            "total_cost_basis": round(total_cost, 2),
            "calls_count": len(calls),
            "puts_count": len(puts),
            "avg_hold_minutes": round(sum(hold_times) / len(hold_times), 1) if hold_times else 0,
            "worst_position": {
                "trade_id": worst["trade_id"],
                "pnl": worst["unrealized_pnl"],
            } if worst else None,
            "best_position": {
                "trade_id": best["trade_id"],
                "pnl": best["unrealized_pnl"],
            } if best else None,
        }
