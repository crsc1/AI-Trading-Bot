"""
Mean Reversion Strategy Module - Catch Oversold/Overbought Bounces

This strategy identifies when price has moved too far too fast and is likely to bounce back.

For beginners: Imagine you're on a swing. You swing out to the left, then the gravity
pulls you back to the center. The market works the same way. When RSI is at 25 (oversold),
it usually bounces back up. When RSI is at 75 (overbought), it usually comes back down.

Key indicators:
- RSI (Relative Strength Index): measures momentum extremes
  - RSI < 25 = extremely oversold, likely to bounce up (BUY CALL)
  - RSI > 75 = extremely overbought, likely to bounce down (BUY PUT)
- Bollinger Bands: shows price extremes
  - Price touching upper band = overbought
  - Price touching lower band = oversold
- Support/Resistance: price bounces at key levels
  - Round numbers like 440, 450, 460 are strong support/resistance
- 20-period SMA: the "mean" - price tends to revert back to this average

Why this works:
- Extremes don't last long
- Quickly profitable when they bounce
- Lower DTE (3-7 days) = fast reversion trades
"""

from datetime import datetime
from typing import Optional, Dict, Any
from strategies.base import BaseStrategy, Signal


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy using RSI extremes and Bollinger Bands.

    This strategy identifies oversold/overbought conditions and trades the bounce back
    to the mean (20-period SMA).

    Logic:
    1. Detect RSI extremes (<25 oversold, >75 overbought)
    2. Confirm with Bollinger Band touches
    3. Check for support/resistance at key levels
    4. BUY CALL when oversold + at support
    5. BUY PUT when overbought + at resistance
    6. Profit target: return to 20-period SMA (the mean)
    """

    def __init__(self, name: str = "MeanReversionStrategy", weight: float = 1.0):
        """
        Initialize the Mean Reversion Strategy.

        Args:
            name: Strategy name for logging
            weight: How much this strategy influences final decision
        """
        super().__init__(name=name, weight=weight)

        # Store for confidence calculation
        self.last_score = 0.0
        self.last_confidence = 0.0
        self.last_reasoning = ""

        # RSI thresholds for extreme conditions
        self.rsi_oversold_extreme = 25  # Very oversold (likely bounce up)
        self.rsi_overbought_extreme = 75  # Very overbought (likely bounce down)

        # Bollinger Band parameters
        self.bb_std_dev = 2.0  # 2 standard deviations = extreme bands

        # Support/resistance detection
        # Key levels: round numbers like 440, 450, 460, etc.
        self.key_level_tolerance = 0.5  # Within $0.50 counts as "at a key level"

        # Volume confirmation
        self.volume_surge_multiplier = 1.2  # 20% above average

    async def analyze(self,
                     market_data: Dict[str, Any],
                     options_data: Dict[str, Any],
                     context: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze RSI and Bollinger Bands for mean reversion signals.

        Args:
            market_data: Price, RSI, Bollinger Bands, SMA
            options_data: Options data
            context: Market regime

        Returns:
            Signal if mean reversion setup is detected, None otherwise
        """

        symbol = "SPY"

        # STEP 1: Extract all required data
        try:
            current_price = market_data.get(symbol, {}).get('current_price')
            volume = market_data.get(symbol, {}).get('volume')
            avg_volume = market_data.get(symbol, {}).get('avg_volume')

            # RSI (Relative Strength Index)
            rsi = market_data.get(symbol, {}).get('rsi')

            # Bollinger Bands (upper, middle, lower)
            bb_upper = market_data.get(symbol, {}).get('bb_upper')
            bb_middle = market_data.get(symbol, {}).get('bb_middle')
            bb_lower = market_data.get(symbol, {}).get('bb_lower')

            # 20-period SMA (the "mean" to revert to)
            sma_20 = market_data.get(symbol, {}).get('sma_20')

            # Options and context data
            iv = options_data.get(symbol, {}).get('iv')
            vix = context.get('vix', 20)

            # Validate required data
            if not all([current_price, rsi, bb_upper, bb_lower, sma_20]):
                return None

        except (KeyError, TypeError, AttributeError):
            return None

        # STEP 2: Detect RSI extreme conditions
        is_oversold = rsi < self.rsi_oversold_extreme  # < 25 = very oversold
        is_overbought = rsi > self.rsi_overbought_extreme  # > 75 = very overbought

        if not (is_oversold or is_overbought):
            # RSI not at extremes = no mean reversion setup
            return None

        score = 0.0
        signal_details = []

        # STEP 3: Check for Bollinger Band touches
        # Price at or beyond 2 std dev = extreme condition
        is_at_lower_band = current_price <= bb_lower
        is_at_upper_band = current_price >= bb_upper

        # STEP 4: Determine direction (oversold bounce up vs overbought bounce down)
        if is_oversold and is_at_lower_band:
            direction = "CALL"
            action = "BUY CALL"
            signal_details.append(f"RSI {rsi:.1f} = OVERSOLD (<25)")
            signal_details.append(f"Price at Bollinger Band lower ({bb_lower:.2f})")
            score += 25  # Strong oversold confirmation

        elif is_overbought and is_at_upper_band:
            direction = "PUT"
            action = "BUY PUT"
            signal_details.append(f"RSI {rsi:.1f} = OVERBOUGHT (>75)")
            signal_details.append(f"Price at Bollinger Band upper ({bb_upper:.2f})")
            score -= 25  # Strong overbought confirmation

        elif is_oversold:
            # Oversold but not at BB = weaker signal
            direction = "CALL"
            action = "BUY CALL"
            signal_details.append(f"RSI {rsi:.1f} = OVERSOLD (<25)")
            signal_details.append("Below Bollinger Band upper")
            score += 15

        elif is_overbought:
            # Overbought but not at BB = weaker signal
            direction = "PUT"
            action = "BUY PUT"
            signal_details.append(f"RSI {rsi:.1f} = OVERBOUGHT (>75)")
            signal_details.append("Above Bollinger Band lower")
            score -= 15

        else:
            return None

        # STEP 5: Check for support/resistance at round numbers
        # Key levels: 440, 450, 460, etc. (round numbers traders watch)
        # Price bouncing off a key level = stronger signal
        key_levels = [int(round(current_price / 10)) * 10 - 5,
                     int(round(current_price / 10)) * 10,
                     int(round(current_price / 10)) * 10 + 5]

        near_key_level = any(abs(current_price - level) < self.key_level_tolerance
                            for level in key_levels)

        if near_key_level:
            score += 10 if score > 0 else -10
            signal_details.append("Price near key support/resistance level")

        # STEP 6: Check if price is at the SMA (mean)
        distance_to_mean = abs(current_price - sma_20) / sma_20

        if distance_to_mean > 0.03:  # Price > 3% away from mean
            # Good setup: oversold/overbought AND far from mean = room to bounce back
            score += 10 if score > 0 else -10
            signal_details.append(f"Price {abs(distance_to_mean)*100:.1f}% away from mean ({sma_20:.2f})")
            signal_details.append("Room for reversion to the mean")

        # STEP 7: Volume confirmation
        if volume is not None and avg_volume is not None and avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio > self.volume_surge_multiplier:
                # High volume at extreme = reversal is likely
                score += 10 if score > 0 else -10
                signal_details.append(f"Volume surge {volume_ratio:.1f}x - reversal strength confirmed")

        # Normalize score
        score = max(-100, min(100, score))

        # STEP 8: Calculate confidence
        # Mean reversion is most profitable when:
        # 1. RSI is very extreme (not just moderately)
        # 2. At Bollinger Band
        # 3. Near support/resistance
        # 4. Volume is confirming

        # Base confidence from RSI extreme
        if is_oversold or is_overbought:
            base_confidence = 0.50
        else:
            base_confidence = 0.30

        # Boost from Bollinger Band
        if is_at_lower_band or is_at_upper_band:
            base_confidence += 0.20
        else:
            base_confidence += 0.10

        # Boost from support/resistance
        if near_key_level:
            base_confidence += 0.10

        # Boost from score strength
        base_confidence += (abs(score) / 100.0) * 0.15

        base_confidence = min(0.85, base_confidence)

        # VIX adjustment: high VIX = choppy = less confident in reversions
        if vix > 30:
            vix_reduction = 1.0 - ((vix - 30) / 50.0 * 0.2)
            base_confidence *= vix_reduction

        self.last_score = score
        self.last_confidence = base_confidence

        # Don't trade if confidence is too low
        if base_confidence < 0.50:
            return None

        # STEP 9: Select strike and expiration
        # Mean reversion is fast = lower DTE (3-7 days)
        # Strike: ATM is standard

        strike = round(current_price * 2) / 2  # Round to nearest $0.50

        # DTE: shorter for quick reversions
        if base_confidence > 0.70:
            dte = 3  # Very confident = fast trade
        elif base_confidence > 0.60:
            dte = 5
        else:
            dte = 7

        expiry_str = f"{dte}DTE"

        # STEP 10: Calculate entry, stops, and targets
        # Estimate option premium
        estimated_premium = max(0.10, (iv / 100.0) * current_price * 0.03 * (dte / 7.0))
        entry_price = estimated_premium

        # Stop loss: beyond the Bollinger Band (if BB is broken, trade is wrong)
        # For options: percentage-based stop
        stop_loss = entry_price * 0.60  # 40% loss max

        # Profit target: revert to 20-period SMA (the mean)
        # Calculate how much the price needs to move
        if direction == "CALL":
            # For call, target is SMA
            distance_to_target = (sma_20 - current_price) / current_price
        else:  # PUT
            # For put, target is SMA
            distance_to_target = (current_price - sma_20) / current_price

        # Convert price distance to option profit
        # Rough estimate: option profits 3-4x if price reaches target
        profit_target = entry_price * (2.5 + abs(distance_to_target) * 20)

        # Risk/reward
        potential_profit = profit_target - entry_price
        potential_loss = entry_price - stop_loss

        if potential_loss > 0:
            risk_reward = potential_profit / potential_loss
        else:
            risk_reward = 0

        # STEP 11: Create reasoning
        reasoning = f"""
        Mean Reversion Analysis:

        RSI: {rsi:.1f} ({'OVERSOLD' if is_oversold else 'OVERBOUGHT'})
        Bollinger Bands: [{bb_lower:.2f}, {bb_middle:.2f}, {bb_upper:.2f}]
        Current Price: {current_price:.2f}
        20-SMA (Mean): {sma_20:.2f}

        Signals Detected:
        {chr(10).join(signal_details)}

        Trade Setup:
        Direction: {'BOUNCE UP (Call)' if direction == 'CALL' else 'BOUNCE DOWN (Put)'}
        Strike: ${strike:.2f}
        Expiration: {dte} days ({expiry_str})
        Entry Price: ${entry_price:.2f}
        Stop Loss: ${stop_loss:.2f}
        Profit Target: ${profit_target:.2f}
        Risk/Reward: {risk_reward:.2f}:1
        Confidence: {base_confidence*100:.1f}%

        Strategy Notes:
        - Mean reversion trades are fast (3-7 DTE)
        - Extremes don't last - market naturally reverts to the mean
        - Target is the 20-SMA at ${sma_20:.2f}
        - Stop loss is at opposite Bollinger Band
        """.strip()

        self.last_reasoning = reasoning

        # STEP 12: Create and return Signal
        signal = Signal(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            strategy="MeanReversionStrategy",
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
                "rsi": rsi,
                "bb_upper": bb_upper,
                "bb_lower": bb_lower,
                "sma_20": sma_20,
                "vix": vix,
                "iv": iv,
                "extreme_type": "oversold" if is_oversold else "overbought",
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
