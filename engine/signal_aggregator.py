"""
Signal Aggregator - Combines signals from multiple strategies into one final decision.

Think of this like a panel of expert traders:
- Each strategy (expert) gives their opinion on whether to buy/sell
- The aggregator weighs each expert's opinion based on their track record (weight)
- If most experts agree, we execute the trade (consensus)
- If they disagree, we reduce confidence or skip the trade

This prevents us from trading on a single strategy's noise.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
import statistics
from strategies.base import Signal
from config.settings import settings


@dataclass
class AggregatedSignal:
    """
    Final trading recommendation after combining all strategy signals.

    This is what the actual trader sees. It tells them:
    - What to do (action)
    - How confident we are (confidence)
    - Why we're doing it (reasoning)
    """

    timestamp: datetime
    """When this decision was made"""

    symbol: str
    """Which symbol (SPY or SPX)"""

    action: str
    """
    Final trading action. Examples:
    - "BUY CALL"
    - "BUY PUT"
    - "SELL CALL SPREAD"
    - "SELL PUT SPREAD"
    - "IRON CONDOR"
    - "NO TRADE"
    """

    aggregated_score: float
    """
    Score from -100 to +100 after weighting all strategies.
    -100 = extremely bearish
    0 = neutral
    +100 = extremely bullish
    """

    confidence: float
    """
    Confidence from 0 to 100%. This is reduced if:
    - Strategies disagree (conflict)
    - Few strategies agree (weak consensus)
    - Signals below our minimum confidence threshold
    """

    contributing_signals: List[str]
    """
    Which strategies contributed to this decision?
    Example: ['TechnicalAnalysis', 'FlowAnalysis']
    """

    strike: Optional[float] = None
    """Best strike price from the contributing signals"""

    expiry: Optional[str] = None
    """Best expiration from the contributing signals"""

    entry_price: Optional[float] = None
    """Suggested entry price (average from contributing signals)"""

    stop_loss: Optional[float] = None
    """Suggested stop loss (tightest from contributing signals)"""

    profit_target: Optional[float] = None
    """Suggested profit target (best from contributing signals)"""

    risk_reward: Optional[float] = None
    """Risk/reward ratio from the contributing signals"""

    reasoning: str = ""
    """
    Plain English explanation of why we're making this trade.
    Combines reasoning from all contributing strategies.
    """

    all_signals: List[Signal] = field(default_factory=list)
    """All input signals that were aggregated (for debugging)"""


class SignalAggregator:
    """
    Takes signals from multiple strategies and produces a final recommendation.

    Key responsibility: Ensure we don't trade on single-strategy noise.
    Instead, we look for CONSENSUS across multiple independent strategies.

    Think of it like medical diagnosis:
    - One doctor suggests surgery (one strategy says BUY)
    - But two other doctors suggest rest (other strategies say HOLD)
    - The patient should probably rest, not have surgery

    That's what consensus checking does.
    """

    def __init__(self):
        """Initialize the signal aggregator with empty history"""
        self.last_aggregated_signal: Optional[AggregatedSignal] = None
        self.signal_history: List[AggregatedSignal] = []

    def aggregate(self, signals: List[Signal]) -> AggregatedSignal:
        """
        Combine multiple strategy signals into one final recommendation.

        Algorithm:
        1. Filter out low-confidence signals
        2. Check consensus (do at least 2 strategies agree on direction?)
        3. Calculate weighted score
        4. Reduce confidence if strategies disagree
        5. Select best parameters from contributing signals
        6. Format reasoning

        Args:
            signals: List of Signal objects from different strategies

        Returns:
            AggregatedSignal with final recommendation
        """

        if not signals:
            return self._create_no_trade_signal()

        # Step 1: Filter by minimum confidence from settings
        # Only use signals we're confident about
        filtered_signals = [
            s for s in signals
            if s.confidence >= (settings.min_signal_confidence / 100.0)
        ]

        if not filtered_signals:
            return self._create_no_trade_signal()

        # Step 2: Separate bullish (CALL) and bearish (PUT) signals
        bullish_signals = [s for s in filtered_signals if s.direction == 'CALL']
        bearish_signals = [s for s in filtered_signals if s.direction == 'PUT']
        _neutral_signals = [s for s in filtered_signals if s.direction == 'NEUTRAL']

        # Check consensus: do we have at least 2 strategies agreeing on direction?
        bullish_count = len(bullish_signals)
        bearish_count = len(bearish_signals)

        has_bullish_consensus = bullish_count >= 2
        has_bearish_consensus = bearish_count >= 2

        # If no consensus, don't trade
        if not has_bullish_consensus and not has_bearish_consensus:
            return self._create_no_trade_signal()

        # Step 3: Decide which direction to go
        # If both have consensus, pick the one with stronger agreement
        if has_bullish_consensus and has_bearish_consensus:
            bullish_strength = self._calculate_weighted_score(bullish_signals)
            bearish_strength = self._calculate_weighted_score(bearish_signals)

            if bullish_strength > bearish_strength:
                contributing_signals = bullish_signals
                direction = 'CALL'
            else:
                contributing_signals = bearish_signals
                direction = 'PUT'
        elif has_bullish_consensus:
            contributing_signals = bullish_signals
            direction = 'CALL'
        else:
            contributing_signals = bearish_signals
            direction = 'PUT'

        # Step 4: Calculate weighted score (-100 to +100)
        # Weight = strategy.weight * signal.score
        weighted_score = self._calculate_weighted_score(contributing_signals)

        # Step 5: Calculate confidence
        # Start with average confidence of contributing signals
        base_confidence = statistics.mean([s.confidence for s in contributing_signals])

        # Reduce confidence if strategies disagree
        # (High variance in scores means less agreement)
        scores = [s.score for s in contributing_signals]
        if len(scores) > 1:
            variance = statistics.variance(scores)
            # Normalize variance to 0-1 range and subtract from confidence
            # Higher variance = lower confidence
            disagreement_penalty = min(variance / 100.0, 0.2)  # Max 20% penalty
            base_confidence -= disagreement_penalty

        # Bonus confidence if many strategies agree
        if len(contributing_signals) >= 3:
            base_confidence += 0.05  # 5% bonus for 3+ signals

        # Convert to 0-100 range and cap
        confidence = max(0, min(100, base_confidence * 100))

        # Step 6: Determine action based on direction
        action = self._determine_action(direction, confidence)

        # Step 7: Select best parameters from contributing signals
        strike = self._select_best_strike(contributing_signals)
        expiry = self._select_best_expiry(contributing_signals)
        entry_price = self._select_best_entry(contributing_signals)
        stop_loss = self._select_best_stop_loss(contributing_signals)
        profit_target = self._select_best_profit_target(contributing_signals)

        # Calculate risk/reward from selected parameters
        if entry_price and stop_loss and profit_target:
            risk = entry_price - stop_loss
            reward = profit_target - entry_price
            risk_reward = reward / risk if risk > 0 else 0
        else:
            risk_reward = None

        # Step 8: Format reasoning (combine from all strategies)
        reasoning = self._combine_reasoning(contributing_signals, direction)

        # Create the aggregated signal
        aggregated = AggregatedSignal(
            timestamp=datetime.now(),
            symbol=contributing_signals[0].symbol,
            action=action,
            aggregated_score=weighted_score,
            confidence=confidence,
            contributing_signals=[s.strategy for s in contributing_signals],
            strike=strike,
            expiry=expiry,
            entry_price=entry_price,
            stop_loss=stop_loss,
            profit_target=profit_target,
            risk_reward=risk_reward,
            reasoning=reasoning,
            all_signals=contributing_signals
        )

        # Store in history
        self.last_aggregated_signal = aggregated
        self.signal_history.append(aggregated)

        return aggregated

    def _create_no_trade_signal(self) -> AggregatedSignal:
        """Create a NO TRADE signal when consensus isn't met"""
        return AggregatedSignal(
            timestamp=datetime.now(),
            symbol="SPY",  # Default
            action="NO TRADE",
            aggregated_score=0,
            confidence=0,
            contributing_signals=[],
            reasoning="No consensus among strategies or insufficient confidence"
        )

    def _calculate_weighted_score(self, signals: List[Signal]) -> float:
        """
        Calculate the weighted average score of signals.

        Formula: sum(score * weight) / sum(weight)

        Example:
        - Strategy A: score=80, weight=2.0
        - Strategy B: score=60, weight=1.0
        - Weighted score = (80*2 + 60*1) / (2+1) = 73.3

        Args:
            signals: List of Signal objects

        Returns:
            Weighted score from -100 to +100
        """
        if not signals:
            return 0

        total_weighted_score = 0
        total_weight = 0

        for signal in signals:
            # Access the strategy's weight from the strategy object
            # Note: Signal doesn't have weight, so we'll use confidence as proxy
            # In production, you'd store strategy weight in Signal metadata
            weight = signal.confidence if signal.confidence > 0 else 1.0

            total_weighted_score += signal.score * weight
            total_weight += weight

        if total_weight == 0:
            return 0

        return total_weighted_score / total_weight

    def _determine_action(self, direction: str, confidence: float) -> str:
        """
        Determine the specific action based on direction and confidence.

        Args:
            direction: 'CALL' or 'PUT'
            confidence: Confidence from 0-100

        Returns:
            Action string like "BUY CALL", "SELL PUT SPREAD", etc.
        """
        if confidence < settings.min_signal_confidence:
            return "NO TRADE"

        # For now, simple logic: BUY options if bullish/bearish
        # More complex logic could use IV, Greeks, etc.
        if direction == 'CALL':
            return "BUY CALL"
        else:
            return "BUY PUT"

    def _select_best_strike(self, signals: List[Signal]) -> Optional[float]:
        """
        Select the best strike from contributing signals.

        Strategy: Use the median strike (most common level)
        This prevents outliers from skewing our choice.
        """
        if not signals:
            return None

        strikes = [s.strike for s in signals if s.strike > 0]
        if not strikes:
            return None

        return statistics.median(strikes)

    def _select_best_expiry(self, signals: List[Signal]) -> Optional[str]:
        """
        Select the best expiration from contributing signals.

        Strategy: Prefer shorter DTE (faster theta decay) if signals agree
        """
        if not signals:
            return None

        # Use the first signal's expiry for now
        # In production, parse expiry dates and pick median
        return signals[0].expiry if signals[0].expiry else None

    def _select_best_entry(self, signals: List[Signal]) -> Optional[float]:
        """
        Select the best entry price from contributing signals.

        Strategy: Use average of entry prices for a balanced approach
        """
        if not signals:
            return None

        entries = [s.entry_price for s in signals if s.entry_price > 0]
        if not entries:
            return None

        return statistics.mean(entries)

    def _select_best_stop_loss(self, signals: List[Signal]) -> Optional[float]:
        """
        Select the best stop loss from contributing signals.

        Strategy: Use the HIGHEST stop loss (tightest, most protective)
        We want the strictest risk management.
        """
        if not signals:
            return None

        stops = [s.stop_loss for s in signals if s.stop_loss > 0]
        if not stops:
            return None

        return max(stops)  # Tightest stop loss

    def _select_best_profit_target(self, signals: List[Signal]) -> Optional[float]:
        """
        Select the best profit target from contributing signals.

        Strategy: Use the HIGHEST profit target (most ambitious)
        Let winners run!
        """
        if not signals:
            return None

        targets = [s.profit_target for s in signals if s.profit_target > 0]
        if not targets:
            return None

        return max(targets)

    def _combine_reasoning(self, signals: List[Signal], direction: str) -> str:
        """
        Combine reasoning from all contributing signals into one narrative.

        Args:
            signals: List of Signal objects
            direction: 'CALL' or 'PUT'

        Returns:
            Combined reasoning string
        """
        if not signals:
            return "No signal reasoning available"

        # Build a summary from all contributing strategies
        reasoning_parts = []

        for signal in signals:
            reasoning_parts.append(f"• {signal.strategy}: {signal.reasoning}")

        # Add consensus info
        action = "Bullish (CALL)" if direction == 'CALL' else "Bearish (PUT)"

        combined = f"Consensus {action} based on {len(signals)} strategies:\n\n"
        combined += "\n".join(reasoning_parts)

        return combined

    def get_last_signal(self) -> Optional[AggregatedSignal]:
        """Get the most recent aggregated signal"""
        return self.last_aggregated_signal

    def get_signal_count(self) -> int:
        """Get total number of aggregated signals generated"""
        return len(self.signal_history)
