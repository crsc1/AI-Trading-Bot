"""
Momentum Strategy Module - Ride the Trend

This strategy identifies strong trends and trades in the direction of the trend.

For beginners: A trend is like a river current. If the current is moving downstream (uptrend),
we want to swim downstream (buy calls). If the current is moving upstream (downtrend), we want
to swim upstream (buy puts). Fighting the trend usually loses money.

Key indicators:
- EMA (Exponential Moving Average): smooth out price noise to see the true direction
- ADX (Average Directional Index): measures how STRONG the trend is (ADX > 25 = strong)
- Volume: confirms the trend is real (high volume = real buyers/sellers)
- Pullbacks to 9 EMA: often good entry points to add to existing position

Why this works:
- Trends tend to continue (momentum)
- Entering WITH the trend = higher probability
- Waiting for pullbacks reduces risk
- Higher DTE (7-14 days) = lets theta decay work slower, gives trend time to develop
"""

from datetime import datetime
from typing import Optional, Dict, Any
from strategies.base import BaseStrategy, Signal


class MomentumStrategy(BaseStrategy):
    """
    Trend-Following Momentum Strategy using EMA Crossovers.

    This strategy identifies strong trends using:
    - EMA 9/21 crossover (short-term vs intermediate-term trend)
    - ADX > 25 (confirms trend is strong, not choppy)
    - Volume confirmation (trend is real)

    BUY CALL in uptrend, BUY PUT in downtrend.
    Look for pullbacks to 9 EMA for entry points.
    Use higher DTE (7-14 days) for trend trades.

    EMA explanation:
    - EMA 9: Very responsive, shows SHORT-TERM direction
    - EMA 21: Smoother, shows INTERMEDIATE-TERM direction
    - When EMA 9 > EMA 21: Uptrend in progress
    - When EMA 9 < EMA 21: Downtrend in progress
    """

    def __init__(self, name: str = "MomentumStrategy", weight: float = 1.0):
        """
        Initialize the Momentum Strategy.

        Args:
            name: Strategy name for logging
            weight: How much this strategy influences final decision
        """
        super().__init__(name=name, weight=weight)

        # Store for confidence calculation
        self.last_score = 0.0
        self.last_confidence = 0.0
        self.last_reasoning = ""

        # EMA parameters
        self.ema_short = 9    # Fast moving average = short-term trend
        self.ema_long = 21    # Slow moving average = intermediate trend

        # ADX threshold for "strong trend"
        self.adx_strong_threshold = 25  # ADX > 25 = strong trend, not choppy
        self.adx_very_strong_threshold = 40  # ADX > 40 = extremely strong trend

        # Volume confirmation
        self.volume_surge_multiplier = 1.3  # 30% above average is confirmation

        # Risk management
        self.max_distance_from_ema = 0.02  # Max 2% away from EMA to count as "pullback"

    async def analyze(self,
                     market_data: Dict[str, Any],
                     options_data: Dict[str, Any],
                     context: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze trend strength and generate momentum signals.

        Args:
            market_data: Price, EMAs, ADX, volume
            options_data: Options data
            context: Market regime, VIX

        Returns:
            Signal if strong trend is detected, None otherwise
        """

        symbol = "SPY"

        # STEP 1: Extract all data
        try:
            current_price = market_data.get(symbol, {}).get('current_price')
            volume = market_data.get(symbol, {}).get('volume')
            avg_volume = market_data.get(symbol, {}).get('avg_volume')

            # EMA values (should be pre-calculated)
            ema_9 = market_data.get(symbol, {}).get('ema_9')
            ema_21 = market_data.get(symbol, {}).get('ema_21')

            # ADX measures trend strength (not direction)
            adx = market_data.get(symbol, {}).get('adx')

            # ATR for stop loss calculation
            atr = market_data.get(symbol, {}).get('atr')

            # Options data
            iv = options_data.get(symbol, {}).get('iv')

            # Context
            vix = context.get('vix', 20)

            # Validate required data
            if not all([current_price, ema_9, ema_21, adx, atr]):
                return None

        except (KeyError, TypeError, AttributeError):
            return None

        # STEP 2: Determine trend direction based on EMA crossover
        # EMA 9 > EMA 21 = uptrend (buy calls)
        # EMA 9 < EMA 21 = downtrend (buy puts)

        is_uptrend = ema_9 > ema_21
        is_downtrend = ema_9 < ema_21

        if not (is_uptrend or is_downtrend):
            # EMAs are equal = choppy/transitional = don't trade
            return None

        # STEP 3: Check if trend is STRONG enough (ADX > 25)
        # ADX < 25 = weak/choppy market (not good for trend trading)
        # ADX 25-40 = strong trend (good for trading)
        # ADX > 40 = extremely strong trend (best for trading)

        if adx < self.adx_strong_threshold:
            # Trend is too weak, don't trade
            return None

        score = 0.0
        signal_details = []

        # STEP 4: Score the trend strength
        if is_uptrend:
            direction = "CALL"
            action = "BUY CALL"
            signal_details.append(f"EMA 9 ({ema_9:.2f}) > EMA 21 ({ema_21:.2f}) = UPTREND")

            if adx > self.adx_very_strong_threshold:
                score += 30
                signal_details.append(f"ADX {adx:.1f} - EXTREMELY STRONG uptrend (+30 pts)")
            elif adx > self.adx_strong_threshold:
                score += 20
                signal_details.append(f"ADX {adx:.1f} - Strong uptrend (+20 pts)")

            # Check if price is near 9 EMA (good entry point)
            distance_to_ema = (current_price - ema_9) / ema_9
            if -self.max_distance_from_ema < distance_to_ema < 0:
                # Price has pulled back to 9 EMA = good entry
                score += 15
                signal_details.append("Price pulled back to 9 EMA - good entry point (+15 pts)")
            elif distance_to_ema > 0:
                # Price is above 9 EMA (normal in uptrend)
                score += 5
                signal_details.append("Price above 9 EMA - confirms uptrend (+5 pts)")

        else:  # Downtrend
            direction = "PUT"
            action = "BUY PUT"
            signal_details.append(f"EMA 9 ({ema_9:.2f}) < EMA 21 ({ema_21:.2f}) = DOWNTREND")

            if adx > self.adx_very_strong_threshold:
                score -= 30
                signal_details.append(f"ADX {adx:.1f} - EXTREMELY STRONG downtrend (-30 pts)")
            elif adx > self.adx_strong_threshold:
                score -= 20
                signal_details.append(f"ADX {adx:.1f} - Strong downtrend (-20 pts)")

            # Check if price is near 9 EMA (good entry point)
            distance_to_ema = (current_price - ema_9) / ema_9
            if 0 < distance_to_ema < self.max_distance_from_ema:
                # Price bounced back to 9 EMA = good entry for short
                score -= 15
                signal_details.append("Price bounced to 9 EMA - good entry point (-15 pts)")
            elif distance_to_ema < 0:
                # Price is below 9 EMA (normal in downtrend)
                score -= 5
                signal_details.append("Price below 9 EMA - confirms downtrend (-5 pts)")

        # STEP 5: Confirm with volume
        if volume is not None and avg_volume is not None and avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio > self.volume_surge_multiplier:
                score += 10 if is_uptrend else -10
                signal_details.append(f"Volume surge {volume_ratio:.1f}x - trend is confirmed (+/- 10 pts)")

        # Normalize score
        score = max(-100, min(100, score))

        # STEP 6: Calculate confidence
        # Confidence based on ADX (stronger = more confident) and score
        base_confidence = 0.40  # Base confidence

        # ADX boost: higher ADX = more confident
        adx_confidence = min(0.50, (adx - self.adx_strong_threshold) / 30.0)
        base_confidence += adx_confidence

        # Score boost: more confirming signals = higher confidence
        base_confidence += (abs(score) / 100.0) * 0.25

        base_confidence = min(0.90, base_confidence)

        # VIX adjustment
        if vix > 30:
            vix_reduction = 1.0 - ((vix - 30) / 50.0 * 0.15)
            base_confidence *= vix_reduction

        self.last_score = score
        self.last_confidence = base_confidence

        # Don't trade if confidence is too low
        if base_confidence < 0.55:
            return None

        # STEP 7: Select strike and expiration
        # Momentum trades need more time = longer DTE (7-14 days)
        # Strike: ATM is standard for trend following

        strike = round(current_price * 2) / 2  # Round to nearest $0.50

        # DTE selection based on ADX (stronger trend = can hold longer)
        if adx > 40:
            dte = 14  # Very strong trend, can hold 2 weeks
        elif adx > 30:
            dte = 10  # Strong trend, 10 days
        else:
            dte = 7   # Standard momentum DTE

        expiry_str = f"{dte}DTE"

        # STEP 8: Calculate entry, stops, and targets
        # Estimate option premium
        estimated_premium = max(0.10, (iv / 100.0) * current_price * 0.04 * (dte / 7.0))
        entry_price = estimated_premium

        # Stop loss: below 21 EMA (if trend breaks, exit)
        # But for options, we use a percentage-based stop
        stop_loss = entry_price * 0.70  # 30% loss max

        # Profit target: trailing stop at 2x ATR
        # ATR (Average True Range) measures volatility
        # Trailing stop follows the trend but exits if trend reverses
        if atr is not None and atr > 0:
            atr_option_value = (atr / current_price) * entry_price
            profit_target = entry_price + (atr_option_value * 2.0)
        else:
            profit_target = entry_price * 3.0  # Default to 3x return

        # Risk/reward
        potential_profit = profit_target - entry_price
        potential_loss = entry_price - stop_loss

        if potential_loss > 0:
            risk_reward = potential_profit / potential_loss
        else:
            risk_reward = 0

        # STEP 9: Create reasoning
        reasoning = f"""
        Momentum Trend Analysis:

        Trend Direction: {'UPTREND' if is_uptrend else 'DOWNTREND'}
        EMA 9: {ema_9:.2f}
        EMA 21: {ema_21:.2f}
        ADX (Trend Strength): {adx:.1f}

        Trading Signals:
        {chr(10).join(signal_details)}

        Trade Setup:
        Action: {action}
        Strike: ${strike:.2f}
        Expiration: {dte} days ({expiry_str})
        Entry Price: ${entry_price:.2f}
        Stop Loss: ${stop_loss:.2f}
        Profit Target: ${profit_target:.2f}
        Risk/Reward: {risk_reward:.2f}:1
        Confidence: {base_confidence*100:.1f}%

        Strategy Notes:
        - ADX > 25 confirms trend is strong enough
        - EMA 9 acting as dynamic support/resistance
        - Look to add on pullbacks to 9 EMA
        - Ride the trend until ADX drops below 25 (trend weakening)
        """.strip()

        self.last_reasoning = reasoning

        # STEP 10: Create and return Signal
        signal = Signal(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            strategy="MomentumStrategy",
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
                "ema_9": ema_9,
                "ema_21": ema_21,
                "adx": adx,
                "atr": atr,
                "vix": vix,
                "iv": iv,
                "trend_type": "uptrend" if is_uptrend else "downtrend",
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
