"""
Probability Engine - Calculates win probability, expected value, and risk/reward scoring.

This module answers: "Is this a mathematically good trade?"

Think of it like poker:
- You have a 60% chance to win the hand
- If you win, you make $200
- If you lose, you lose $100
- Expected value = (0.60 * 200) - (0.40 * 100) = $80

A trade with positive expected value is worth taking (in the long run).
This engine calculates EV for each options trade.

Note: For beginners, "expected value" means the average profit/loss over many trades.
Positive EV = long-term profit. Negative EV = long-term loss.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
import statistics
from strategies.base import Signal


class ProbabilityEngine:
    """
    Calculates probabilities and expected values for trading decisions.

    Responsibilities:
    1. Calculate win probability based on strategy history and market conditions
    2. Calculate expected value of a trade
    3. Score risk/reward ratios
    4. Perform quick backtest to verify strategy works
    """

    def __init__(self):
        """Initialize probability engine with empty trade history"""
        # Store historical trades for backtesting
        # Format: {strategy_name: [{'win': True/False, 'return': 0.05, ...}, ...]}
        self.trade_history: Dict[str, List[Dict[str, Any]]] = {}

    def calculate_win_probability(self, signal: Signal) -> float:
        """
        Calculate the probability that this trade will be profitable.

        Uses three factors:
        1. Historical win rate of this strategy
        2. Current market conditions (IV, regime)
        3. Signal strength

        Args:
            signal: The Signal to analyze

        Returns:
            Probability from 0.0 to 1.0
        """

        # Start with base rate (50% - neutral)
        base_probability = 0.50

        # Factor 1: Historical win rate of this strategy
        strategy_win_rate = self._get_strategy_win_rate(signal.strategy)
        if strategy_win_rate is not None:
            # Weight historical rate 40%
            base_probability = base_probability * 0.6 + strategy_win_rate * 0.4

        # Factor 2: Signal confidence (higher confidence = higher win probability)
        # Signal confidence is 0-1, map to +/- 0.15
        confidence_adjustment = (signal.confidence - 0.5) * 0.3
        base_probability += confidence_adjustment

        # Factor 3: Market conditions (from signal metadata)
        # IV percentile: high IV = more expensive, lower win rate for shorts
        iv_percentile = signal.metadata.get('iv_percentile', 50) / 100.0
        # If IV very high (95%), reduce win probability by 10%
        iv_adjustment = -(iv_percentile - 0.5) * 0.1
        base_probability += iv_adjustment

        # Cap between 0.01 and 0.99
        return max(0.01, min(0.99, base_probability))

    def calculate_expected_value(self, signal: Signal) -> float:
        """
        Calculate the expected value (EV) of this trade.

        Formula:
        EV = (Probability of Win * Profit) - (Probability of Loss * Loss)

        Example:
        - P(win) = 60%, profit if win = $100
        - P(loss) = 40%, loss if loss = $50
        - EV = (0.6 * 100) - (0.4 * 50) = 60 - 20 = $40

        Positive EV = good trade (profit on average)
        Negative EV = bad trade (loss on average)

        Args:
            signal: The Signal to analyze

        Returns:
            Expected value in dollars (positive = good, negative = bad)
        """

        # Calculate win probability
        p_win = self.calculate_win_probability(signal)
        p_loss = 1 - p_win

        # Calculate profit and loss amounts
        if signal.entry_price <= 0 or signal.stop_loss <= 0:
            return 0  # Can't calculate without valid prices

        profit_per_contract = signal.profit_target - signal.entry_price
        loss_per_contract = signal.entry_price - signal.stop_loss

        # Assume 1 contract for simplicity (could be parameterized)
        profit = profit_per_contract
        loss = loss_per_contract

        # Calculate EV
        ev = (p_win * profit) - (p_loss * loss)

        return ev

    def score_risk_reward(self, signal: Signal) -> float:
        """
        Score the risk/reward ratio to see if it makes mathematical sense.

        A 2:1 risk/reward is decent.
        A 3:1 risk/reward is good.
        A 1:1 risk/reward is acceptable only with high win probability.

        Scoring:
        - 3:1 or better = 90 points
        - 2:1 = 70 points
        - 1.5:1 = 50 points
        - 1:1 = 30 points
        - Below 1:1 = 0 points (bad)

        Args:
            signal: The Signal to score

        Returns:
            Score from 0 to 100
        """

        rr = signal.risk_reward

        if rr is None or rr <= 0:
            return 0

        # Score based on risk/reward ratio
        if rr >= 3.0:
            base_score = 90
        elif rr >= 2.0:
            base_score = 70
        elif rr >= 1.5:
            base_score = 50
        elif rr >= 1.0:
            base_score = 30
        else:
            return 0  # Risk/reward below 1:1 is bad

        # Adjust based on win probability
        # If win probability is very high, lower R:R is acceptable
        p_win = self.calculate_win_probability(signal)

        # Minimum win probability needed for this R:R
        # Formula: p_min = 1 / (1 + rr)
        # Example: for 2:1 R:R, need p_min = 1/3 = 33%
        p_min = 1.0 / (1.0 + rr)

        if p_win >= p_min:
            # We have sufficient win probability for this R:R
            # Add bonus for strong probability
            probability_bonus = (p_win - p_min) * 20
            base_score = min(100, base_score + probability_bonus)

        else:
            # Win probability is too low for this R:R
            # Penalize the score
            probability_penalty = (p_min - p_win) * 50
            base_score = max(0, base_score - probability_penalty)

        return max(0, min(100, base_score))

    def backtest_quick(
        self,
        strategy_name: str,
        lookback_days: int = 30
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Quick backtest: did this strategy work in the past?

        This checks historical trades from this strategy to see:
        - Win rate: % of trades that were profitable
        - Average return: average % gain per trade

        Args:
            strategy_name: Name of the strategy to test
            lookback_days: How many days back to look

        Returns:
            Tuple of (win_rate, avg_return) or (None, None) if no history

        Example:
            win_rate, avg_return = engine.backtest_quick('Technical', lookback_days=30)
            if win_rate:
                print(f"Technical strategy: {win_rate*100:.1f}% win rate")
        """

        if strategy_name not in self.trade_history:
            return (None, None)

        # Get all trades for this strategy
        all_trades = self.trade_history[strategy_name]

        if not all_trades:
            return (None, None)

        # Filter to lookback period
        cutoff = datetime.now() - timedelta(days=lookback_days)
        recent_trades = [
            t for t in all_trades
            if t.get('timestamp', datetime.now()) >= cutoff
        ]

        if not recent_trades:
            return (None, None)

        # Calculate win rate
        wins = sum(1 for t in recent_trades if t.get('win', False))
        win_rate = wins / len(recent_trades)

        # Calculate average return
        returns = [t.get('return', 0) for t in recent_trades]
        avg_return = statistics.mean(returns) if returns else 0

        return (win_rate, avg_return)

    def record_trade(
        self,
        strategy_name: str,
        won: bool,
        return_percent: float,
        entry_price: float,
        exit_price: float
    ) -> None:
        """
        Record a historical trade for backtesting.

        Args:
            strategy_name: Name of strategy that generated this trade
            won: True if trade was profitable
            return_percent: Return as decimal (0.05 = 5% return)
            entry_price: Entry price
            exit_price: Exit price
        """

        if strategy_name not in self.trade_history:
            self.trade_history[strategy_name] = []

        trade = {
            'timestamp': datetime.now(),
            'win': won,
            'return': return_percent,
            'entry_price': entry_price,
            'exit_price': exit_price,
        }

        self.trade_history[strategy_name].append(trade)

    def _get_strategy_win_rate(self, strategy_name: str) -> Optional[float]:
        """
        Get historical win rate for a strategy.

        Returns:
            Win rate from 0-1, or None if no history
        """

        if strategy_name not in self.trade_history:
            return None

        trades = self.trade_history[strategy_name]
        if not trades:
            return None

        wins = sum(1 for t in trades if t.get('win', False))
        return wins / len(trades)

    def get_strategy_stats(self, strategy_name: str) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a strategy.

        Args:
            strategy_name: Name of the strategy

        Returns:
            Dict with statistics or empty dict if no history
        """

        if strategy_name not in self.trade_history:
            return {}

        trades = self.trade_history[strategy_name]
        if not trades:
            return {}

        # Calculate statistics
        wins = sum(1 for t in trades if t.get('win', False))
        losses = len(trades) - wins
        win_rate = wins / len(trades)

        returns = [t.get('return', 0) for t in trades]
        avg_return = statistics.mean(returns)
        std_dev = statistics.stdev(returns) if len(returns) > 1 else 0

        # Profit factor (average win / average loss)
        winning_trades = [t.get('return', 0) for t in trades if t.get('win', False)]
        losing_trades = [abs(t.get('return', 0)) for t in trades if not t.get('win', False)]

        avg_win = statistics.mean(winning_trades) if winning_trades else 0
        avg_loss = statistics.mean(losing_trades) if losing_trades else 0

        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

        return {
            'total_trades': len(trades),
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate,
            'average_return': avg_return,
            'std_deviation': std_dev,
            'profit_factor': profit_factor,
            'avg_winning_trade': avg_win,
            'avg_losing_trade': avg_loss,
        }

    def is_mathematically_sound(self, signal: Signal) -> bool:
        """
        Quick check: Is this trade mathematically sound?

        A trade is mathematically sound if:
        1. Expected value is positive
        2. Risk/reward ratio >= 1.5:1
        3. Win probability >= minimum required for that R:R

        Args:
            signal: The Signal to check

        Returns:
            True if trade meets all criteria
        """

        # Check EV
        ev = self.calculate_expected_value(signal)
        if ev <= 0:
            return False

        # Check R:R
        rr_score = self.score_risk_reward(signal)
        if rr_score < 40:  # Below 1.5:1 threshold
            return False

        # Check win probability
        p_win = self.calculate_win_probability(signal)
        if p_win < 0.30:  # Less than 30% win probability
            return False

        return True
