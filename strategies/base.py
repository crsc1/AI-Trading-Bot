"""
Base Strategy Module - Foundation for all trading strategies

This module defines the abstract base class and data structures that ALL strategies
must inherit from. Think of this as the "template" that every strategy follows.

Key Concepts:
- BaseStrategy: Abstract class that all real strategies inherit from
- Signal: The output/recommendation that a strategy produces
- Every strategy analyzes market data and produces a Signal
"""

from dataclasses import dataclass, field
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any


@dataclass
class Signal:
    """
    A Signal is what a strategy outputs. It's the recommendation to BUY, SELL, or DO NOTHING.

    Think of it like a doctor's diagnosis:
    - timestamp: When the diagnosis was made
    - symbol: Which stock (SPY or SPX)
    - direction: CALL (bullish) or PUT (bearish)
    - score: How strong is the signal? -100 = strong put, +100 = strong call
    - recommended_action: What to actually DO? "BUY CALL", "SELL PUT SPREAD", etc.
    """

    # BASIC INFO - WHEN AND WHAT
    timestamp: datetime
    """The exact time this signal was generated"""

    symbol: str
    """Which index? 'SPY' or 'SPX' (SPX is more expensive but better for larger accounts)"""

    direction: str
    """'CALL' (bullish), 'PUT' (bearish), or 'NEUTRAL' (no clear trade)"""

    strategy: str
    """Which strategy generated this? e.g., 'OpeningRange', 'Directional', 'MeanReversion'"""

    # CONFIDENCE AND SCORING - HOW STRONG IS THIS?
    score: float
    """
    Score from -100 to +100.
    -100 = extremely bearish (strong put signal)
    0 = neutral (no trade)
    +100 = extremely bullish (strong call signal)
    Use this to compare signals from different strategies.
    """

    confidence: float
    """
    How confident are we? 0.0 to 1.0
    0.5 = moderate confidence
    0.8+ = very confident (good entry point)
    0.3 and below = weak signal (maybe skip this trade)
    """

    # WHAT TO DO - THE ACTION
    recommended_action: str
    """
    What should the trader actually DO?
    Examples:
    - "BUY CALL" (buy a call option - bullish bet)
    - "BUY PUT" (buy a put option - bearish bet)
    - "SELL CALL SPREAD" (collect premium, capped upside)
    - "SELL PUT SPREAD" (collect premium, capped downside)
    - "IRON CONDOR" (sell both sides for premium)
    - "HOLD" (don't trade right now)
    """

    # OPTION DETAILS - WHERE TO TRADE
    strike: float
    """
    Which strike price to trade?
    ATM = At The Money (same price as current stock)
    ITM = In The Money (intrinsic value)
    OTM = Out of The Money (only time value)

    Usually we pick ATM or 1-2 strikes OTM for better risk/reward.
    """

    expiry: str
    """
    When should this option expire?
    Examples: '2025-01-17', '1DTE' (tomorrow), '0DTE' (today only)
    Shorter expirations = faster profit, but riskier
    Longer expirations = more time, less theta decay
    """

    # ENTRY AND EXIT PRICES - THE LEVELS
    entry_price: float
    """
    The suggested price to ENTER this trade.
    This is what we'd pay for a call or what we'd receive for selling.
    Market price changes every second, so use this as a guide.
    """

    stop_loss: float
    """
    The MAXIMUM LOSS price.
    If the market moves to this price, automatically exit to prevent bigger losses.
    Golden rule: ALWAYS set a stop loss before entering ANY trade.
    Example: If you buy a call at $100, stop loss might be $85 (max loss = $15)
    """

    profit_target: float
    """
    The TAKE PROFIT price.
    If the trade reaches this price, sell to lock in profits.
    Example: If you buy at $100, profit target might be $130 (profit = $30)
    """

    risk_reward: float
    """
    The ratio of potential profit to potential loss.
    risk_reward = (profit_target - entry_price) / (entry_price - stop_loss)
    Example: risk_reward = 2.0 means you make $2 for every $1 you risk
    Generally look for ratios >= 2.0 for good trades
    """

    # EXPLANATION - THE REASONING
    reasoning: str
    """
    WHY are we making this trade? This is the "story" behind the signal.
    This should be written in plain English so any trader can understand it.

    Example:
    "RSI at 25 (oversold), bouncing off support with volume increase.
    Next resistance at $450. Risk/reward is 3:1. Best entry is at $445 call."
    """

    # EXTRA DATA - STRATEGY-SPECIFIC DETAILS
    metadata: Dict[str, Any] = field(default_factory=dict)
    """
    Extra information that might be useful for this specific strategy.
    Examples:
    {
        'rsi': 28,  # RSI value
        'macd_histogram': 0.045,  # MACD histogram value
        'vix': 18.5,  # VIX level
        'iv_percentile': 65,  # IV rank (how high is IV compared to 1 year?)
        'support_level': 445.50,
        'resistance_level': 450.00,
    }
    """


class BaseStrategy(ABC):
    """
    Abstract base class that ALL strategies must inherit from.

    This enforces that every strategy:
    1. Has a name (for logging and tracking)
    2. Has a weight (how much this strategy contributes to the final decision)
    3. Can analyze market data and produce signals
    4. Can calculate its own confidence

    Think of this like a contract: "All strategies MUST implement these methods."
    If you create a new strategy, you MUST inherit from BaseStrategy and override
    the abstract methods (marked with @abstractmethod).
    """

    def __init__(self, name: str, weight: float = 1.0):
        """
        Initialize a strategy.

        Args:
            name: Name of this strategy (e.g., "OpeningRangeBreakout")
            weight: How much this strategy contributes to final decision
                   Default is 1.0 (equal weight)
                   Higher weight = more influence on final signal
                   Example: momentum strategy with weight 2.0 has 2x the influence
        """
        self.name = name
        self.weight = weight

        # Validate weight is positive
        if weight <= 0:
            raise ValueError(f"Strategy weight must be positive, got {weight}")

    @abstractmethod
    async def analyze(self,
                     market_data: Dict[str, Any],
                     options_data: Dict[str, Any],
                     context: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze current market conditions and generate a trading signal.

        This is the CORE method of any strategy. Every strategy must implement this.
        It receives market data and outputs a trading Signal (if conditions are met).

        Args:
            market_data: Current price data, candles, volume
                        {
                            'SPY': {
                                'current_price': 450.25,
                                'high': 451.00,
                                'low': 449.50,
                                'volume': 45000000,
                                'vwap': 450.10,
                            }
                        }

            options_data: Options chain info
                         {
                            'SPY': {
                                'call_volume': 1000,
                                'put_volume': 800,
                                'iv': 18.5,
                                'iv_percentile': 65,
                            }
                        }

            context: Market regime info (trending? VIX high? etc)
                    {
                        'vix': 18.5,
                        'market_regime': 'trending',  # or 'range_bound'
                        'is_0dte_window': True,
                        'gex_level': 'positive',
                    }

        Returns:
            Signal object if trade condition is met, None otherwise

        Why async? Because we might be fetching real-time data or doing
        complex calculations that could take time. Async lets the program
        do other things while we wait.
        """
        pass

    @abstractmethod
    def calculate_confidence(self) -> float:
        """
        Calculate how confident this strategy is in its latest signal.

        This is used by the signal aggregator to weight different strategies.
        A strategy that always wins should have high confidence.
        A strategy that's uncertain should have lower confidence.

        Returns:
            Float from 0.0 to 1.0
            0.0 = no confidence (don't trade)
            0.5 = moderate confidence
            1.0 = very high confidence

        Why is this separate? Because confidence depends on many factors:
        - How many confirming indicators?
        - How strong are they?
        - What's the market regime?

        This allows each strategy to calculate confidence its own way.
        """
        pass

    def validate_signal(self, signal: Signal) -> bool:
        """
        Validate that a signal is properly formed before returning it.

        This is a sanity check to prevent bad signals from being sent to traders.
        All strategies use this validation.

        Args:
            signal: The Signal to validate

        Returns:
            True if signal is valid, False otherwise
        """
        # Check required fields
        if signal.symbol not in ['SPY', 'SPX']:
            print(f"Invalid symbol: {signal.symbol}")
            return False

        if signal.direction not in ['CALL', 'PUT', 'NEUTRAL']:
            print(f"Invalid direction: {signal.direction}")
            return False

        if not -100 <= signal.score <= 100:
            print(f"Score out of range: {signal.score}")
            return False

        if not 0 <= signal.confidence <= 1.0:
            print(f"Confidence out of range: {signal.confidence}")
            return False

        # Check that entry price is reasonable
        if signal.entry_price <= 0:
            print(f"Entry price must be positive: {signal.entry_price}")
            return False

        # Check that stop loss and profit target make sense
        if signal.stop_loss >= signal.entry_price:
            print(f"Stop loss ({signal.stop_loss}) must be below entry ({signal.entry_price})")
            return False

        if signal.profit_target <= signal.entry_price:
            print(f"Profit target ({signal.profit_target}) must be above entry ({signal.entry_price})")
            return False

        # Check risk/reward is positive
        if signal.risk_reward <= 0:
            print(f"Risk/reward must be positive: {signal.risk_reward}")
            return False

        return True

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"{self.__class__.__name__}(name='{self.name}', weight={self.weight})"
