"""
Flow-Based Strategy Module - Follow the Smart Money

This strategy monitors unusual options activity and follows what the "smart money"
(institutions, large traders) is doing.

For beginners: Imagine a secret poker game where you can see what the best players
are betting on. If you see them betting big on something, you want to follow their bets.
Options flow analysis is like that - we see when big money is buying calls or puts.

Key concepts:
- Sweep: Aggressive buying that takes out ask price immediately
  (The buyer wants in NOW, doesn't care about the price)
- Block: Institutional-sized order, often negotiated
- Golden Sweep: An ATM or ITM sweep with high premium (very bullish conviction)
- Repeated Hits: Same strike getting bought multiple times (strong conviction)
- Net Flow: Are more call buyers or put buyers winning today?

Flow characteristics:
- Sweeps > $1M = high conviction trade
- Golden Sweeps = extremely bullish (hard to ignore)
- Multiple flow signals in same direction = strong confirmation
"""

from datetime import datetime
from typing import Optional, Dict, Any
from strategies.base import BaseStrategy, Signal


class FlowBasedStrategy(BaseStrategy):
    """
    Smart Money Options Flow Analysis Strategy.

    This strategy detects unusual options activity and follows the smart money.

    Logic:
    1. Monitor options flow data (sweeps, blocks, golden sweeps)
    2. Detect aggressive buying patterns (size, frequency, types)
    3. Calculate net flow direction (calls vs puts)
    4. Score the flow based on conviction signals
    5. BUY CALL when bullish flow dominates
    6. BUY PUT when bearish flow dominates

    Flow signals:
    - Large sweep ($1M+) = immediate demand, high conviction
    - Multiple sweeps in same direction = consistent betting
    - Golden sweep (ATM/ITM, large) = extremely strong bullish
    - Blocks = institutional money, patient buying
    - Repeated hits on same strike = someone really wants that strike
    """

    def __init__(self, name: str = "FlowBasedStrategy", weight: float = 1.0):
        """
        Initialize the Flow-Based Strategy.

        Args:
            name: Strategy name for logging
            weight: How much this strategy influences final decision
        """
        super().__init__(name=name, weight=weight)

        # Store for confidence calculation
        self.last_score = 0.0
        self.last_confidence = 0.0
        self.last_reasoning = ""

        # Flow signal thresholds
        self.large_flow_threshold = 1_000_000  # $1M = large/smart money
        self.very_large_flow_threshold = 5_000_000  # $5M = extremely large

        # Golden sweep: ATM or ITM with high premium
        self.golden_sweep_min_size = 500_000  # Minimum $500k

        # Flow scoring weights
        self.sweep_score = 20  # Sweep = aggressive = high conviction
        self.block_score = 15  # Block = institutional patience
        self.golden_sweep_score = 30  # Golden sweep = extremely bullish

    async def analyze(self,
                     market_data: Dict[str, Any],
                     options_data: Dict[str, Any],
                     context: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze options flow and generate trading signals based on smart money activity.

        Args:
            market_data: Current price
            options_data: Options flow data (sweeps, blocks, net flow)
            context: Market regime, time of day

        Returns:
            Signal if smart money flow is detected, None otherwise
        """

        symbol = "SPY"

        # STEP 1: Extract flow data
        try:
            current_price = market_data.get(symbol, {}).get('current_price')

            # Options flow data from Unusual Whales or similar
            flow_data = options_data.get(symbol, {}).get('flow_data', {})

            # Extract flow components
            call_sweeps = flow_data.get('call_sweeps', [])  # List of sweep orders
            put_sweeps = flow_data.get('put_sweeps', [])

            call_blocks = flow_data.get('call_blocks', [])
            put_blocks = flow_data.get('put_blocks', [])

            golden_sweeps = flow_data.get('golden_sweeps', [])  # Very bullish indicator

            # Net flow: aggregate call vs put buying
            _net_flow = options_data.get(symbol, {}).get('options_flow')  # 'bullish', 'bearish', 'neutral'
            call_put_ratio = options_data.get(symbol, {}).get('call_put_ratio')  # Ratio of calls to puts

            # Context
            vix = context.get('vix', 20)

            # Validate minimum data
            if current_price is None:
                return None

        except (KeyError, TypeError, AttributeError):
            return None

        # STEP 2: Score individual flow events
        score = 0.0
        signal_details = []
        flow_signal_count = 0

        # CALL FLOW ANALYSIS
        call_flow_total = 0
        call_large_count = 0

        if call_sweeps:
            for sweep in call_sweeps:
                size = sweep.get('size', 0)
                strike = sweep.get('strike')
                call_flow_total += size

                # Score based on size
                if size >= self.very_large_flow_threshold:
                    score += 25  # Very large sweep = very bullish
                    call_large_count += 1
                    signal_details.append(f"Large call sweep ${size/1e6:.1f}M at ${strike:.2f} strike")
                elif size >= self.large_flow_threshold:
                    score += 15  # Large sweep = bullish
                    call_large_count += 1
                    signal_details.append(f"Call sweep ${size/1e6:.1f}M at ${strike:.2f} strike")
                else:
                    score += 5  # Normal sweep

                flow_signal_count += 1

        # PUT FLOW ANALYSIS
        put_flow_total = 0
        put_large_count = 0

        if put_sweeps:
            for sweep in put_sweeps:
                size = sweep.get('size', 0)
                strike = sweep.get('strike')
                put_flow_total += size

                # Score based on size (negative = bearish)
                if size >= self.very_large_flow_threshold:
                    score -= 25  # Very large sweep = very bearish
                    put_large_count += 1
                    signal_details.append(f"Large put sweep ${size/1e6:.1f}M at ${strike:.2f} strike")
                elif size >= self.large_flow_threshold:
                    score -= 15  # Large sweep = bearish
                    put_large_count += 1
                    signal_details.append(f"Put sweep ${size/1e6:.1f}M at ${strike:.2f} strike")
                else:
                    score -= 5  # Normal sweep

                flow_signal_count += 1

        # GOLDEN SWEEP ANALYSIS (Extremely bullish)
        if golden_sweeps:
            for golden in golden_sweeps:
                size = golden.get('size', 0)
                strike = golden.get('strike')
                sentiment = golden.get('sentiment', 'bullish')  # golden sweeps are usually bullish

                if size >= self.golden_sweep_min_size:
                    if sentiment == 'bullish':
                        score += 30
                        signal_details.insert(0, f"GOLDEN SWEEP ${size/1e6:.1f}M - EXTREMELY BULLISH")
                    else:
                        score -= 30
                        signal_details.insert(0, f"GOLDEN SWEEP ${size/1e6:.1f}M - EXTREMELY BEARISH")

                    flow_signal_count += 1

        # BLOCK FLOW ANALYSIS (Institutional money)
        if call_blocks:
            total_call_blocks = sum(b.get('size', 0) for b in call_blocks)
            score += 10
            signal_details.append(f"Call blocks (institutional): ${total_call_blocks/1e6:.1f}M total")
            flow_signal_count += 1

        if put_blocks:
            total_put_blocks = sum(b.get('size', 0) for b in put_blocks)
            score -= 10
            signal_details.append(f"Put blocks (institutional): ${total_put_blocks/1e6:.1f}M total")
            flow_signal_count += 1

        # STEP 3: Check net flow direction
        # If not enough flow data, check call/put ratio
        if not signal_details or flow_signal_count == 0:
            # No specific flow data, use aggregate flow
            if call_put_ratio is not None:
                if call_put_ratio > 1.3:
                    # More calls than puts = bullish
                    score += 20
                    signal_details.append(f"Call/Put ratio {call_put_ratio:.2f} - more bullish calls")
                    flow_signal_count += 1
                elif call_put_ratio < 0.7:
                    # More puts than calls = bearish
                    score -= 20
                    signal_details.append(f"Call/Put ratio {call_put_ratio:.2f} - more bearish puts")
                    flow_signal_count += 1
                else:
                    # Balanced = no clear signal
                    return None
            else:
                # No flow data at all
                return None

        # STEP 4: Validate we have enough flow signals to trade
        if flow_signal_count < 1:
            # Not enough flow signals to make a decision
            return None

        # Normalize score
        score = max(-100, min(100, score))

        # STEP 5: Determine direction
        if score > 10:
            direction = "CALL"
            action = "BUY CALL"
        elif score < -10:
            direction = "PUT"
            action = "BUY PUT"
        else:
            # Flow signals are balanced = no trade
            return None

        # STEP 6: Calculate confidence
        # Confidence based on:
        # 1. Number of confirming flow signals
        # 2. Size of the signals (bigger = more confident)
        # 3. Multiple signal types agreeing (sweep + block + golden = very confident)

        base_confidence = 0.50

        # Signal count boost
        if flow_signal_count >= 3:
            base_confidence += 0.20
        elif flow_signal_count >= 2:
            base_confidence += 0.10
        else:
            base_confidence += 0.05

        # Score magnitude boost
        base_confidence += (abs(score) / 100.0) * 0.20

        # Multiple signal type check
        has_sweeps = bool(call_sweeps or put_sweeps)
        has_blocks = bool(call_blocks or put_blocks)
        has_golden = bool(golden_sweeps)

        signal_type_count = sum([has_sweeps, has_blocks, has_golden])
        if signal_type_count >= 2:
            # Multiple types of flow signals = higher confidence
            base_confidence += 0.15

        base_confidence = min(0.85, base_confidence)

        # VIX adjustment: high VIX during heavy flow = strong conviction
        if vix > 25:
            # Flow during elevated VIX = extra conviction
            vix_boost = 1.0 + ((vix - 25) / 50.0 * 0.1)
            base_confidence *= vix_boost

        self.last_score = score
        self.last_confidence = base_confidence

        # Don't trade if confidence is too low
        if base_confidence < 0.55:
            return None

        # STEP 7: Select strike and expiration
        # Flow-based trades: follow momentum
        # Strike: ATM or 1 strike OTM
        # Expiry: depends on confidence (higher = longer DTE)

        strike = round(current_price * 2) / 2  # ATM

        if base_confidence > 0.75:
            dte = 7
            expiry_str = "7DTE"
        elif base_confidence > 0.65:
            dte = 5
            expiry_str = "5DTE"
        else:
            dte = 3
            expiry_str = "3DTE"

        # STEP 8: Calculate entry, stops, and targets
        iv = options_data.get(symbol, {}).get('iv', 20)

        # Estimate option premium
        estimated_premium = max(0.10, (iv / 100.0) * current_price * 0.03 * (dte / 7.0))
        entry_price = estimated_premium

        # Stop loss: 20-30% loss
        stop_loss = entry_price * 0.70

        # Profit target: 50-100% gain based on flow strength
        if base_confidence > 0.75:
            profit_target = entry_price * 2.0  # 100% gain
        else:
            profit_target = entry_price * 1.5  # 50% gain

        # Risk/reward
        potential_profit = profit_target - entry_price
        potential_loss = entry_price - stop_loss

        if potential_loss > 0:
            risk_reward = potential_profit / potential_loss
        else:
            risk_reward = 0

        # STEP 9: Create reasoning
        reasoning = f"""
        Smart Money Options Flow Analysis:

        Flow Signals Detected: {flow_signal_count}
        {chr(10).join(signal_details)}

        Net Direction: {'BULLISH' if score > 0 else 'BEARISH'}
        Flow Score: {score:.0f}/100
        Confidence: {base_confidence*100:.1f}%

        Trade Setup:
        Action: {action}
        Strike: ${strike:.2f}
        Expiration: {dte} days ({expiry_str})
        Entry Price: ${entry_price:.2f}
        Stop Loss: ${stop_loss:.2f}
        Profit Target: ${profit_target:.2f}
        Risk/Reward: {risk_reward:.2f}:1

        Flow Details:
        Call Sweep Total: ${call_flow_total/1e6:.1f}M
        Put Sweep Total: ${put_flow_total/1e6:.1f}M
        Call/Put Ratio: {(call_flow_total/(put_flow_total+0.001)):.2f}:1

        Strategy Notes:
        - Following smart money = higher probability
        - Golden sweeps are extremely high conviction
        - Multiple flow signals = stronger setup
        - Large size = more conviction
        - Exit with profit or stop loss hit
        """.strip()

        self.last_reasoning = reasoning

        # STEP 10: Create and return Signal
        signal = Signal(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            strategy="FlowBasedStrategy",
            score=score,
            confidence=base_confidence,
            recommended_action=action,
            strike=strike,
            expiry=expiry_str,
            entry_price=entry_price,
            stop_loss=stop_loss,
            profit_target=profit_target,
            risk_reward=risk_reward,
            reasoning=reasoning,
            metadata={
                "flow_signal_count": flow_signal_count,
                "call_flow_total": call_flow_total,
                "put_flow_total": put_flow_total,
                "has_golden_sweeps": bool(golden_sweeps),
                "has_blocks": bool(call_blocks or put_blocks),
                "vix": vix,
                "iv": iv,
            }
        )

        if self.validate_signal(signal):
            return signal
        else:
            return None

    def calculate_confidence(self) -> float:
        """
        Return the confidence of this strategy's latest signal.

        Returns:
            Float from 0.0 to 1.0
        """
        return self.last_confidence
