"""
Signal Validator — Pre-trade checks before entering any position.

Validates that a signal meets all safety and quality criteria before
the paper trader (or simulation engine) is allowed to execute.

Checks:
  1. Spread check — bid/ask spread < 5% of mid price
  2. Liquidity  — option volume > 100 contracts (or OI > 500)
  3. Risk budget — position cost within per-trade and daily limits
  4. Correlation — no duplicate/correlated open position
  5. Daily loss  — daily drawdown < 2% of account (hard stop)
  6. Cooldown    — minimum 5 min between same-direction entries
  7. Time guard  — no entries past 3:00 PM ET (0DTE hard stop)
  8. IV guard    — reject if IV Rank > 90 (options too expensive)

All checks are independent; any single failure vetoes the trade.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timedelta, timezone
import logging

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    ET = timezone(timedelta(hours=-4))

from .confluence import (
    ACCOUNT_BALANCE,
    ZERO_DTE_HARD_STOP,
    MIN_TRADE_CONFIDENCE,
)

logger = logging.getLogger(__name__)


# ── Thresholds ──
MAX_SPREAD_PCT = 0.05          # 5% of mid price
MIN_VOLUME = 100               # Minimum daily option volume
MIN_OI = 500                   # Minimum open interest (alt liquidity)
MAX_DAILY_LOSS_PCT = 0.02      # 2% of account → stop trading
COOLDOWN_MINUTES = 5           # Minutes between same-direction entries
MAX_IV_RANK = 90               # Reject if IV Rank exceeds this
MAX_OPEN_POSITIONS = 3         # Maximum concurrent AI-managed positions
MAX_POSITION_RISK_PCT = 0.03   # 3% of account per single position


@dataclass
class ValidationResult:
    """Outcome of pre-trade validation."""
    passed: bool
    checks: List[Dict]           # Individual check results
    reject_reason: Optional[str] = None  # First failure reason

    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "reject_reason": self.reject_reason,
            "checks": self.checks,
        }


def validate_signal(
    signal: Dict,
    account_balance: float = ACCOUNT_BALANCE,
    open_trades: Optional[List[Dict]] = None,
    daily_pnl: float = 0.0,
) -> ValidationResult:
    """
    Run all pre-trade validation checks on a signal.

    Args:
        signal: Full signal dict from SignalEngine.analyze()
        account_balance: Current account balance
        open_trades: Currently open trades (from signal_db.get_open_trades)
        daily_pnl: Today's realized P&L so far

    Returns:
        ValidationResult with pass/fail and individual check details
    """
    if open_trades is None:
        open_trades = []

    checks = []
    first_failure = None

    # ── 1. Confidence threshold ──
    confidence = signal.get("confidence", 0)
    tier = signal.get("tier", "DEVELOPING")
    passed = confidence >= MIN_TRADE_CONFIDENCE and tier != "DEVELOPING"
    checks.append({
        "name": "confidence",
        "passed": passed,
        "detail": f"Confidence {confidence:.3f} (tier: {tier}), min: {MIN_TRADE_CONFIDENCE}",
    })
    if not passed and not first_failure:
        first_failure = f"Confidence too low: {confidence:.3f} ({tier})"

    # ── 2. Spread check ──
    bid = signal.get("bid", 0) or 0
    ask = signal.get("ask", 0) or 0
    entry_price = signal.get("entry_price", 0) or 0

    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / mid if mid > 0 else 1.0
        passed = spread_pct <= MAX_SPREAD_PCT
        checks.append({
            "name": "spread",
            "passed": passed,
            "detail": f"Spread {spread_pct:.2%} (max {MAX_SPREAD_PCT:.0%}), bid={bid:.2f} ask={ask:.2f}",
        })
        if not passed and not first_failure:
            first_failure = f"Spread too wide: {spread_pct:.2%}"
    else:
        # No bid/ask data — pass with warning (simulation mode can still run)
        checks.append({
            "name": "spread",
            "passed": True,
            "detail": "No bid/ask data — skipped (simulation mode)",
        })

    # ── 3. Liquidity check ──
    # Check from options_analytics if available
    analytics = signal.get("options_analytics") or {}
    call_vol = analytics.get("total_call_volume", 0)
    put_vol = analytics.get("total_put_volume", 0)
    total_vol = call_vol + put_vol

    if total_vol > 0:
        passed = total_vol >= MIN_VOLUME
        checks.append({
            "name": "liquidity",
            "passed": passed,
            "detail": f"Chain volume {total_vol} (min {MIN_VOLUME})",
        })
        if not passed and not first_failure:
            first_failure = f"Insufficient liquidity: {total_vol} contracts"
    else:
        # Check OI as fallback
        call_oi = analytics.get("total_call_oi", 0)
        put_oi = analytics.get("total_put_oi", 0)
        total_oi = call_oi + put_oi
        if total_oi > 0:
            passed = total_oi >= MIN_OI
            checks.append({
                "name": "liquidity",
                "passed": passed,
                "detail": f"Chain OI {total_oi} (min {MIN_OI})",
            })
            if not passed and not first_failure:
                first_failure = f"Insufficient OI: {total_oi}"
        else:
            checks.append({
                "name": "liquidity",
                "passed": True,
                "detail": "No volume/OI data — skipped",
            })

    # ── 4. Risk budget ──
    risk_mgmt = signal.get("risk_management", {})
    max_contracts = signal.get("max_contracts", 0) or risk_mgmt.get("max_contracts", 0)

    if entry_price > 0 and max_contracts > 0:
        position_cost = entry_price * max_contracts * 100  # options = 100x multiplier
        position_risk_pct = position_cost / account_balance if account_balance > 0 else 1.0
        passed = position_risk_pct <= MAX_POSITION_RISK_PCT
        checks.append({
            "name": "risk_budget",
            "passed": passed,
            "detail": f"Position risk {position_risk_pct:.2%} of ${account_balance:.0f} (max {MAX_POSITION_RISK_PCT:.0%})",
        })
        if not passed and not first_failure:
            first_failure = f"Position risk too high: {position_risk_pct:.2%}"
    else:
        checks.append({
            "name": "risk_budget",
            "passed": True,
            "detail": "No entry price/contracts — skipped",
        })

    # ── 5. Correlation / duplicate check ──
    direction = signal.get("signal", "NO_TRADE")
    symbol = signal.get("symbol", "SPY")
    same_direction_open = [
        t for t in open_trades
        if t.get("symbol") == symbol
        and t.get("option_type") == ("call" if direction == "BUY_CALL" else "put")
    ]
    passed = len(same_direction_open) == 0
    checks.append({
        "name": "correlation",
        "passed": passed,
        "detail": f"{len(same_direction_open)} same-direction open positions on {symbol}",
    })
    if not passed and not first_failure:
        first_failure = f"Already have {len(same_direction_open)} open {symbol} {'call' if direction == 'BUY_CALL' else 'put'} position(s)"

    # ── 6. Max open positions ──
    passed = len(open_trades) < MAX_OPEN_POSITIONS
    checks.append({
        "name": "max_positions",
        "passed": passed,
        "detail": f"{len(open_trades)} open (max {MAX_OPEN_POSITIONS})",
    })
    if not passed and not first_failure:
        first_failure = f"Max positions reached: {len(open_trades)}/{MAX_OPEN_POSITIONS}"

    # ── 7. Daily loss limit ──
    daily_loss_pct = abs(daily_pnl) / account_balance if account_balance > 0 and daily_pnl < 0 else 0
    passed = daily_loss_pct < MAX_DAILY_LOSS_PCT
    checks.append({
        "name": "daily_loss",
        "passed": passed,
        "detail": f"Daily P&L ${daily_pnl:.2f} ({daily_loss_pct:.2%} loss, max {MAX_DAILY_LOSS_PCT:.0%})",
    })
    if not passed and not first_failure:
        first_failure = f"Daily loss limit hit: ${daily_pnl:.2f} ({daily_loss_pct:.2%})"

    # ── 8. Cooldown check ──
    if open_trades:
        now = datetime.now(timezone.utc)
        recent_same = [
            t for t in open_trades
            if t.get("symbol") == symbol
        ]
        too_recent = False
        for t in recent_same:
            try:
                entry_time = datetime.fromisoformat(t.get("entry_time", ""))
                if (now - entry_time).total_seconds() < COOLDOWN_MINUTES * 60:
                    too_recent = True
                    break
            except (ValueError, TypeError):
                pass

        passed = not too_recent
        checks.append({
            "name": "cooldown",
            "passed": passed,
            "detail": f"{'Within' if too_recent else 'Past'} {COOLDOWN_MINUTES}min cooldown on {symbol}",
        })
        if not passed and not first_failure:
            first_failure = f"Cooldown active: last {symbol} entry < {COOLDOWN_MINUTES}min ago"
    else:
        checks.append({
            "name": "cooldown",
            "passed": True,
            "detail": "No open trades — cooldown N/A",
        })

    # ── 9. Time guard (0DTE hard stop) ──
    try:
        now_et = datetime.now(ET)
        current_time = now_et.time()
        passed = current_time < ZERO_DTE_HARD_STOP
        checks.append({
            "name": "time_guard",
            "passed": passed,
            "detail": f"Current time {current_time.strftime('%H:%M')} ET, hard stop {ZERO_DTE_HARD_STOP.strftime('%H:%M')} ET",
        })
        if not passed and not first_failure:
            first_failure = f"Past 0DTE hard stop ({ZERO_DTE_HARD_STOP.strftime('%I:%M %p')} ET)"
    except Exception:
        checks.append({
            "name": "time_guard",
            "passed": True,
            "detail": "Could not determine time — skipped",
        })

    # ── 10. IV guard ──
    iv_rank = analytics.get("iv_rank")
    if iv_rank is not None:
        passed = iv_rank <= MAX_IV_RANK
        checks.append({
            "name": "iv_guard",
            "passed": passed,
            "detail": f"IV Rank {iv_rank:.0f}% (max {MAX_IV_RANK}%)",
        })
        if not passed and not first_failure:
            first_failure = f"IV Rank too high: {iv_rank:.0f}% (options overpriced)"
    else:
        checks.append({
            "name": "iv_guard",
            "passed": True,
            "detail": "IV Rank unavailable — skipped",
        })

    # ── Final verdict ──
    all_passed = all(c["passed"] for c in checks)

    return ValidationResult(
        passed=all_passed,
        checks=checks,
        reject_reason=first_failure if not all_passed else None,
    )
