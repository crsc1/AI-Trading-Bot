"""
Paper Trader — Dual-mode execution engine.

Modes:
  1. Simulation: Uses Black-Scholes repricing from utils/greeks.py.
     No broker interaction. Pure mathematical P&L tracking.
     Perfect for backtesting / when market is closed.

  2. Alpaca Paper: Places real orders on Alpaca paper account.
     Uses the existing trading_api.py infrastructure.
     Real fills, real slippage, real order book.

Both modes:
  - Record every trade in signal_db (signals + trades tables)
  - Track MFE (max favorable excursion) and MAE (max adverse excursion)
  - Apply risk management rules from the signal
  - Monitor for stop-loss and profit-target exits

Does NOT interfere with Alpaca live trading or modify any existing
Alpaca positions/orders not created by this module.
"""

import logging
import aiohttp
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .signal_db import store_signal, mark_signal_traded, mark_signal_rejected, store_trade, close_trade
from .signal_validator import validate_signal
from .confluence import ACCOUNT_BALANCE
from .config import cfg

logger = logging.getLogger(__name__)

# ── Alpaca credentials (same as trading_api.py) ──
ALPACA_TRADING_URL = cfg.ALPACA_BASE_URL
ALPACA_KEY = cfg.ALPACA_API_KEY
ALPACA_SECRET = cfg.ALPACA_SECRET_KEY
ALPACA_HEADERS = cfg.ALPACA_HEADERS

# Tag prefix so we can identify our orders in Alpaca
AI_ORDER_TAG = "ai_signal_"


class PaperTrader:
    """
    Manages trade execution and lifecycle for AI-generated signals.

    Usage:
        trader = PaperTrader(mode="simulation")
        result = await trader.process_signal(signal)
    """

    def __init__(
        self,
        mode: str = "simulation",
        account_balance: float = ACCOUNT_BALANCE,
    ):
        """
        Args:
            mode: "simulation" (Black-Scholes) or "alpaca_paper" (real paper orders)
            account_balance: Starting balance for risk calculations
        """
        if mode not in ("simulation", "alpaca_paper"):
            raise ValueError(f"Invalid mode: {mode}. Use 'simulation' or 'alpaca_paper'.")
        self.mode = mode
        self.account_balance = account_balance

    async def process_signal(
        self,
        signal: Dict,
        open_trades: Optional[List[Dict]] = None,
        daily_pnl: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Full signal processing pipeline:
          1. Store signal in DB
          2. Skip if NO_TRADE
          3. Validate pre-trade checks
          4. Execute entry (simulation or Alpaca)
          5. Return result with trade_id or rejection reason

        Args:
            signal: Full signal dict from SignalEngine
            open_trades: Current open trades for validation
            daily_pnl: Today's realized P&L

        Returns:
            Dict with action taken, trade_id (if entered), validation details
        """
        result = {
            "action": "none",
            "signal_id": None,
            "trade_id": None,
            "validation": None,
            "error": None,
        }

        try:
            # ── 1. Store the signal regardless ──
            sig_id = store_signal(signal)
            result["signal_id"] = sig_id

            # ── 2. Skip NO_TRADE signals ──
            if signal.get("signal") == "NO_TRADE":
                result["action"] = "no_trade"
                return result

            # ── 3. Validate ──
            validation = validate_signal(
                signal=signal,
                account_balance=self.account_balance,
                open_trades=open_trades or [],
                daily_pnl=daily_pnl,
            )
            result["validation"] = validation.to_dict()

            if not validation.passed:
                mark_signal_rejected(sig_id, validation.reject_reason or "Validation failed")
                result["action"] = "rejected"
                return result

            # ── 4. Execute entry ──
            if self.mode == "simulation":
                trade_id = self._enter_simulation(signal, sig_id)
            else:
                trade_id = await self._enter_alpaca(signal, sig_id)

            if trade_id:
                mark_signal_traded(sig_id)
                result["action"] = "entered"
                result["trade_id"] = trade_id
            else:
                mark_signal_rejected(sig_id, "Execution failed")
                result["action"] = "execution_failed"

        except Exception as e:
            logger.error(f"PaperTrader error: {e}", exc_info=True)
            result["error"] = str(e)
            result["action"] = "error"

        return result

    def _enter_simulation(self, signal: Dict, sig_id: str) -> Optional[str]:
        """
        Enter a simulated trade. No broker interaction.
        Uses the signal's entry price directly.
        """
        entry_price = signal.get("entry_price", 0)
        if not entry_price or entry_price <= 0:
            logger.warning("Simulation entry skipped: no entry price")
            return None

        direction = signal.get("signal", "")
        max_contracts = signal.get("max_contracts", 1) or 1

        trade = {
            "signal_id": sig_id,
            "mode": "simulation",
            "entry_time": datetime.now(timezone.utc).isoformat(),
            "entry_price": entry_price,
            "quantity": max_contracts,
            "strike": signal.get("strike"),
            "expiry": signal.get("expiry"),
            "option_type": "call" if direction == "BUY_CALL" else "put",
            "symbol": signal.get("symbol", "SPY"),
            "greeks_at_entry": {
                "delta": signal.get("option_delta"),
                "iv": signal.get("option_iv"),
            },
        }

        trade_id = store_trade(trade)
        logger.info(
            f"SIM ENTRY: {direction} {max_contracts}x "
            f"${signal.get('strike')} {trade['option_type']} @ ${entry_price:.2f} "
            f"[trade_id={trade_id}]"
        )
        return trade_id

    async def _enter_alpaca(self, signal: Dict, sig_id: str) -> Optional[str]:
        """
        Place a real order on Alpaca paper account.

        Uses limit order at the signal's entry price with day TIF.
        Builds the OCC symbol from signal strike/expiry/direction.

        IMPORTANT: Only creates new orders — never modifies existing
        Alpaca positions that weren't created by this module.
        """
        if not ALPACA_KEY:
            logger.error("Alpaca API key not configured — falling back to simulation")
            return self._enter_simulation(signal, sig_id)

        direction = signal.get("signal", "")
        strike = signal.get("strike")
        expiry = signal.get("expiry")
        entry_price = signal.get("entry_price", 0)
        max_contracts = signal.get("max_contracts", 1) or 1

        if not all([strike, expiry, entry_price]):
            logger.warning("Alpaca entry skipped: missing strike/expiry/entry_price")
            return None

        # Build OCC symbol: SPY250326C00570000
        option_type = "C" if direction == "BUY_CALL" else "P"
        occ_symbol = _build_occ_symbol(
            root=signal.get("symbol", "SPY"),
            expiry=expiry,
            option_type=option_type,
            strike=strike,
        )

        if not occ_symbol:
            logger.error("Could not build OCC symbol")
            return None

        # Place limit order
        order_payload = {
            "symbol": occ_symbol,
            "qty": str(max_contracts),
            "side": "buy",
            "type": "limit",
            "time_in_force": "day",
            "limit_price": str(round(entry_price, 2)),
            "client_order_id": f"{AI_ORDER_TAG}{sig_id}",
        }

        try:
            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                url = f"{ALPACA_TRADING_URL}/orders"
                async with session.post(
                    url,
                    json=order_payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        alpaca_order_id = data.get("id", "")

                        # Store in our DB with Alpaca order reference
                        trade = {
                            "signal_id": sig_id,
                            "mode": "alpaca_paper",
                            "entry_time": datetime.now(timezone.utc).isoformat(),
                            "entry_price": entry_price,
                            "quantity": max_contracts,
                            "strike": strike,
                            "expiry": expiry,
                            "option_type": "call" if direction == "BUY_CALL" else "put",
                            "symbol": signal.get("symbol", "SPY"),
                            "greeks_at_entry": {
                                "delta": signal.get("option_delta"),
                                "iv": signal.get("option_iv"),
                                "alpaca_order_id": alpaca_order_id,
                            },
                        }
                        trade_id = store_trade(trade)

                        logger.info(
                            f"ALPACA ENTRY: {direction} {max_contracts}x {occ_symbol} "
                            f"@ ${entry_price:.2f} limit [order={alpaca_order_id[:8]}]"
                        )
                        return trade_id
                    else:
                        text = await resp.text()
                        logger.error(f"Alpaca order failed ({resp.status}): {text[:300]}")
                        return None

        except Exception as e:
            logger.error(f"Alpaca order error: {e}")
            return None

    async def exit_trade(
        self,
        trade: Dict,
        exit_price: float,
        exit_reason: str = "manual",
        greeks_at_exit: Optional[Dict] = None,
    ) -> bool:
        """
        Close an open trade (simulation or Alpaca).

        Args:
            trade: Trade dict from signal_db
            exit_price: Price to exit at
            exit_reason: Why we're exiting (target, stop, manual, time_stop, expiry)
            greeks_at_exit: Current greeks at exit time

        Returns:
            True if exit was successful
        """
        trade_id = trade.get("id")
        if not trade_id:
            return False

        entry_price = trade.get("entry_price", 0)
        quantity = trade.get("quantity", 1)

        # Calculate P&L
        pnl_per_contract = (exit_price - entry_price) * 100  # options multiplier
        total_pnl = pnl_per_contract * quantity
        pnl_pct = ((exit_price - entry_price) / entry_price * 100) if entry_price > 0 else 0

        exit_data = {
            "exit_time": datetime.now(timezone.utc).isoformat(),
            "exit_price": exit_price,
            "pnl": round(total_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "max_favorable": trade.get("max_favorable", 0),
            "max_adverse": trade.get("max_adverse", 0),
            "exit_reason": exit_reason,
            "greeks_at_exit": greeks_at_exit or {},
        }

        # If Alpaca mode, close the position too
        if trade.get("mode") == "alpaca_paper":
            await self._exit_alpaca(trade)

        close_trade(trade_id, exit_data)

        logger.info(
            f"EXIT: trade={trade_id} @ ${exit_price:.2f} "
            f"P&L=${total_pnl:.2f} ({pnl_pct:+.1f}%) reason={exit_reason}"
        )
        return True

    async def _exit_alpaca(self, trade: Dict) -> bool:
        """Close an Alpaca paper position by selling to close."""
        if not ALPACA_KEY:
            return False

        greeks_entry = trade.get("greeks_at_entry")
        if isinstance(greeks_entry, str):
            import json
            try:
                greeks_entry = json.loads(greeks_entry)
            except (json.JSONDecodeError, TypeError):
                greeks_entry = {}

        alpaca_order_id = (greeks_entry or {}).get("alpaca_order_id")
        if not alpaca_order_id:
            logger.warning("No Alpaca order ID found for trade — skipping broker exit")
            return False

        # Build OCC symbol for sell-to-close
        option_type = "C" if trade.get("option_type") == "call" else "P"
        occ_symbol = _build_occ_symbol(
            root=trade.get("symbol", "SPY"),
            expiry=trade.get("expiry", ""),
            option_type=option_type,
            strike=trade.get("strike", 0),
        )

        if not occ_symbol:
            return False

        try:
            order_payload = {
                "symbol": occ_symbol,
                "qty": str(trade.get("quantity", 1)),
                "side": "sell",
                "type": "market",
                "time_in_force": "day",
            }

            async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
                url = f"{ALPACA_TRADING_URL}/orders"
                async with session.post(
                    url,
                    json=order_payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201):
                        logger.info(f"Alpaca sell-to-close placed for {occ_symbol}")
                        return True
                    else:
                        text = await resp.text()
                        logger.error(f"Alpaca exit failed ({resp.status}): {text[:300]}")
                        return False
        except Exception as e:
            logger.error(f"Alpaca exit error: {e}")
            return False


def _build_occ_symbol(
    root: str,
    expiry: str,
    option_type: str,
    strike: float,
) -> Optional[str]:
    """
    Build OCC option symbol: SPY250326C00570000

    Format: ROOT + YYMMDD + C/P + 8-digit strike (strike × 1000, zero-padded)
    """
    try:
        # Parse expiry date
        if "-" in str(expiry):
            parts = str(expiry).split("-")
            yy = parts[0][-2:]  # Last 2 digits of year
            mm = parts[1].zfill(2)
            dd = parts[2].zfill(2)
        else:
            # Already YYMMDD or similar
            exp_str = str(expiry)
            if len(exp_str) == 6:
                yy, mm, dd = exp_str[:2], exp_str[2:4], exp_str[4:6]
            else:
                return None

        # Strike to 8 digits: 570.00 → 00570000
        strike_int = int(round(strike * 1000))
        strike_str = str(strike_int).zfill(8)

        return f"{root.upper()}{yy}{mm}{dd}{option_type}{strike_str}"

    except Exception as e:
        logger.error(f"OCC symbol build error: {e}")
        return None
