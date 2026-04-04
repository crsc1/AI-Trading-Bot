"""
Risk Manager - Enforces all risk limits and position sizing rules.

This is the "safety net" of the trading bot. It answers questions like:
- Can we open a new position?
- How many contracts should we buy?
- Did we lose too much today?
- Are we a PDT (Pattern Day Trader)?

Think of it like a seatbelt in a car:
- Even if the bot wants to trade, the risk manager says "are you sure?"
- It prevents overleverage, excessive losses, and PDT violations
- It stops you from blowing up your account

Golden rule: The risk manager's decision is FINAL. No exceptions.
"""

from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict, Any
from datetime import datetime, timedelta
from strategies.base import Signal
from config.settings import settings


@dataclass
class Trade:
    """A single executed trade (for tracking PDT and daily P&L)"""

    entry_time: datetime
    """When we entered the trade"""

    exit_time: Optional[datetime] = None
    """When we exited (if closed)"""

    symbol: str = "SPY"
    """Which symbol"""

    action: str = ""
    """BUY CALL, BUY PUT, etc."""

    entry_price: float = 0.0
    """Entry price"""

    exit_price: Optional[float] = None
    """Exit price (if closed)"""

    pnl: float = 0.0
    """Profit/loss on this trade"""

    is_day_trade: bool = False
    """Did we enter and exit on same day?"""


class RiskManager:
    """
    Enforces all risk management rules before allowing trades.

    Responsibilities:
    1. Check daily loss limits
    2. Check position count limits
    3. Track PDT (Pattern Day Trader) rules
    4. Calculate safe position sizing
    5. Enforce stop losses
    6. Track daily P&L
    """

    def __init__(self, account_balance: float = None):
        """
        Initialize the risk manager.

        Args:
            account_balance: Starting account balance in dollars.
                           If None, uses settings.starting_capital
        """
        self.account_balance = account_balance or settings.starting_capital
        self.starting_balance = self.account_balance

        # Track open positions (for position count limit)
        self.open_positions: List[Dict[str, Any]] = []

        # Track all trades (for P&L and PDT calculation)
        self.trade_history: List[Trade] = []

        # Track day trades in rolling window
        self.day_trades_today: int = 0
        self.last_day_trade_date: Optional[datetime] = None

    def check_trade_allowed(self, signal: Signal) -> Tuple[bool, str]:
        """
        Can we execute this trade? Check all risk limits.

        Args:
            signal: The Signal we want to trade

        Returns:
            Tuple of (allowed: bool, reason: str)
            Example: (False, "Daily loss limit exceeded: $1000 lost today")
        """

        # Check 1: Daily loss limit (0 = disabled)
        daily_pnl = self.get_daily_pnl()
        max_daily_loss_amt = self.get_max_daily_loss_amount()

        if max_daily_loss_amt > 0 and daily_pnl <= -max_daily_loss_amt:
            return (False, f"Daily loss limit exceeded. Daily P&L: ${daily_pnl:.2f}")

        # Check 2: Maximum number of open positions
        if len(self.open_positions) >= settings.max_total_open_positions:
            return (
                False,
                f"Max positions ({settings.max_total_open_positions}) already open"
            )

        # Check 3: PDT (Pattern Day Trader) rule
        if self.is_pdt_restricted():
            return (
                False,
                f"PDT restriction active. Day trades: {self.day_trades_today}/"
                f"{settings.max_day_trades} in last {settings.day_trade_window_days} days"
            )

        # Check 4: Position size limit
        # Calculate how much capital this trade would use
        position_capital = self.calculate_position_size(signal, self.account_balance)
        max_position_capital = self.account_balance * settings.max_position_size

        if position_capital > max_position_capital:
            return (
                False,
                f"Position size ${position_capital:.2f} exceeds max "
                f"${max_position_capital:.2f}"
            )

        # All checks passed!
        return (True, "Trade allowed")

    def calculate_position_size(
        self,
        signal: Signal,
        account_balance: float
    ) -> float:
        """
        Calculate how many contracts to buy using Half-Kelly Criterion.

        Half-Kelly is a safer version of the Kelly Criterion:
        f = (p * b - q) / b / 2
        where:
        - f = fraction of capital to risk
        - p = probability of win (from signal.metadata or 50% default)
        - b = reward/risk ratio (from signal.risk_reward)
        - q = 1 - p (probability of loss)

        Example:
        - Win probability: 60%
        - Risk $100 to make $200
        - Kelly suggests risking 11% of capital
        - Half-Kelly suggests risking 5.5% (safer)

        Args:
            signal: The Signal to size for
            account_balance: Current account balance

        Returns:
            Number of contracts to trade
        """

        # Get win probability (from signal metadata or default 50%)
        p = signal.metadata.get('win_probability', 0.50)
        p = max(0.01, min(0.99, p))  # Cap between 1% and 99%

        # Get reward/risk ratio
        b = signal.risk_reward if signal.risk_reward and signal.risk_reward > 0 else 1.0

        # Probability of loss
        q = 1 - p

        # Half-Kelly formula (divide by 2 for safety)
        if b <= 0:
            kelly_fraction = 0
        else:
            kelly_fraction = (p * b - q) / b / 2

        # Cap at 2% of capital max
        kelly_fraction = min(kelly_fraction, 0.02)

        # Can't be negative
        kelly_fraction = max(0, kelly_fraction)

        # Convert to dollar amount
        risk_amount = account_balance * kelly_fraction

        # Convert to number of contracts
        # 1 SPY contract = 100 shares
        # Cost = price_per_share * 100 * number_of_contracts
        # For options, cost per contract varies; simplification:
        # Assume each contract costs approximately strike price / 10
        # (options are usually 1-20% of underlying price)

        if signal.entry_price <= 0:
            return 1  # Default to 1 contract

        # Rough estimate: cost per contract ≈ entry_price / 10
        cost_per_contract = max(signal.entry_price / 10, 10)  # Min $10 per contract
        num_contracts = int(risk_amount / cost_per_contract)

        # Always trade at least 1 contract if allowed
        if num_contracts < 1 and risk_amount > cost_per_contract:
            num_contracts = 1

        return max(0, num_contracts)

    def track_day_trade(self, trade: Trade) -> None:
        """
        Track a day trade for PDT rule compliance.

        Args:
            trade: The Trade object to track
        """
        if trade.is_day_trade:
            self.day_trades_today += 1
            self.last_day_trade_date = datetime.now()

        self.trade_history.append(trade)

    def get_daily_pnl(self) -> float:
        """
        Get current daily profit/loss.

        Returns today's realized P&L from closed positions.

        Returns:
            P&L in dollars (negative = loss, positive = profit)
        """
        today = datetime.now().date()
        daily_pnl = 0.0

        for trade in self.trade_history:
            # Only count trades closed today
            if trade.exit_time and trade.exit_time.date() == today:
                daily_pnl += trade.pnl

        return daily_pnl

    def is_pdt_restricted(self) -> bool:
        """
        Are we currently PDT restricted?

        PDT rule: max 3 day trades in rolling 5 days
        (Only applies to margin accounts under $25k)

        Returns:
            True if we can't day trade right now
        """

        # If account is >= $25k, PDT rule doesn't apply
        if self.account_balance >= 25000:
            return False

        # Count day trades in rolling window
        cutoff_date = datetime.now() - timedelta(
            days=settings.day_trade_window_days
        )

        recent_day_trades = 0
        for trade in self.trade_history:
            if trade.is_day_trade and trade.entry_time >= cutoff_date:
                recent_day_trades += 1

        return recent_day_trades >= settings.max_day_trades

    def get_max_risk_amount(self, account_balance: float) -> float:
        """
        Get the maximum dollar amount we can risk on a single trade.

        Formula: account_balance * max_risk_per_trade

        Example:
        - Account: $5,000
        - Max risk per trade: 2% = 0.02
        - Max risk amount: $100

        Args:
            account_balance: Current balance in dollars

        Returns:
            Max risk in dollars
        """
        return account_balance * settings.max_risk_per_trade

    def get_max_daily_loss_amount(self) -> float:
        """
        Get the maximum loss allowed for the entire day.

        Formula: account_balance * max_daily_loss

        Example:
        - Account: $5,000
        - Max daily loss: 5% = 0.05
        - Max daily loss: $250

        Returns:
            Max daily loss in dollars (positive number)
        """
        return self.account_balance * settings.max_daily_loss

    def enforce_stop_loss(self, position: Dict[str, Any]) -> bool:
        """
        Check if a position should be closed due to stop loss.

        Args:
            position: Position dict with 'current_price', 'entry_price', 'stop_loss'

        Returns:
            True if position should be closed (stop hit)
        """
        if 'stop_loss' not in position or 'current_price' not in position:
            return False

        # If current price <= stop loss, close the position
        return position['current_price'] <= position['stop_loss']

    def update_account_balance(self, pnl: float) -> None:
        """
        Update account balance after a trade P&L.

        Args:
            pnl: Profit/loss from the trade
        """
        self.account_balance += pnl

    def reset_daily_trades(self) -> None:
        """Reset daily trade counter (call at market open)"""
        self.day_trades_today = 0

    def add_open_position(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        stop_loss: float,
        profit_target: float,
        num_contracts: int = 1
    ) -> None:
        """
        Add a new open position to track.

        Args:
            symbol: SPY or SPX
            action: BUY CALL, BUY PUT, etc.
            entry_price: Entry price
            stop_loss: Stop loss price
            profit_target: Profit target price
            num_contracts: Number of contracts
        """
        position = {
            'symbol': symbol,
            'action': action,
            'entry_price': entry_price,
            'current_price': entry_price,
            'stop_loss': stop_loss,
            'profit_target': profit_target,
            'num_contracts': num_contracts,
            'entry_time': datetime.now()
        }
        self.open_positions.append(position)

    def close_position(self, position_index: int, exit_price: float) -> Trade:
        """
        Close an open position and return the Trade record.

        Args:
            position_index: Index in open_positions list
            exit_price: Price at which we exited

        Returns:
            Trade object with P&L calculated
        """
        position = self.open_positions.pop(position_index)

        # Calculate P&L
        entry = position['entry_price']
        pnl = (exit_price - entry) * position['num_contracts'] * 100

        # Determine if it's a day trade
        entry_time = position['entry_time']
        exit_time = datetime.now()
        is_day_trade = entry_time.date() == exit_time.date()

        trade = Trade(
            entry_time=entry_time,
            exit_time=exit_time,
            symbol=position['symbol'],
            action=position['action'],
            entry_price=entry,
            exit_price=exit_price,
            pnl=pnl,
            is_day_trade=is_day_trade
        )

        self.trade_history.append(trade)

        # Update account balance
        self.update_account_balance(pnl)

        return trade

    def get_position_count(self) -> int:
        """Get number of currently open positions"""
        return len(self.open_positions)

    def get_account_summary(self) -> Dict[str, Any]:
        """
        Get a complete summary of account status.

        Returns:
            Dict with current account info
        """
        return {
            'account_balance': self.account_balance,
            'starting_balance': self.starting_balance,
            'unrealized_pnl': sum(
                (p['current_price'] - p['entry_price']) * p['num_contracts'] * 100
                for p in self.open_positions
            ),
            'daily_pnl': self.get_daily_pnl(),
            'total_pnl': self.account_balance - self.starting_balance,
            'open_positions': len(self.open_positions),
            'max_positions': settings.max_total_open_positions,
            'day_trades_today': self.day_trades_today,
            'max_day_trades': settings.max_day_trades,
            'pdt_restricted': self.is_pdt_restricted(),
            'max_risk_per_trade': self.get_max_risk_amount(self.account_balance),
            'max_daily_loss': self.get_max_daily_loss_amount(),
        }
