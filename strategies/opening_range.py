"""
Opening Range Breakout Strategy Module

This is a simple but powerful strategy for 0DTE (same-day expiration) options trading.

For beginners: Imagine the market opens at 9:30 AM and trades in a range for the first
30 minutes (say 449.50 to 450.50). Then at 10:00 AM, price breaks above 450.50 on high
volume. This is a breakout signal. We buy a CALL option betting the price will keep going up.

Opening Range:
- The opening range is the high and low of the first 15-30 minutes of trading
- We watch for price to break above the high (bullish) or below the low (bearish)
- Breakouts are strongest when volume is high (confirms demand)
- Time window: Best signals are 9:45 AM to 10:30 AM ET

Why this works:
- Early momentum often continues throughout the day
- Large volume confirms the breakout is real
- 0DTE options = fast profits (theta decay works with us)
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from strategies.base import BaseStrategy, Signal


class OpeningRangeBreakout(BaseStrategy):
    """
    Opening Range Breakout Strategy for 0DTE and 1DTE options.

    This strategy identifies the opening range (first 15-30 minutes) and trades
    breakouts from that range. Perfect for day traders and 0DTE gamma scalping.

    Logic:
    1. Calculate the HIGH and LOW of the first 15-30 minutes
    2. Watch for price to break above HIGH or below LOW
    3. Confirm with volume surge and VWAP alignment
    4. Generate BUY CALL on upside breakout, BUY PUT on downside
    5. Use opening range width as profit target and opposite side as stop loss
    """

    def __init__(self, name: str = "OpeningRangeBreakout", weight: float = 1.0):
        """
        Initialize the Opening Range Breakout strategy.

        Args:
            name: Strategy name for logging
            weight: How much this strategy influences final decision
        """
        super().__init__(name=name, weight=weight)

        # Store data for confidence calculation
        self.last_score = 0.0
        self.last_confidence = 0.0
        self.last_reasoning = ""

        # Opening range parameters
        self.opening_window_minutes = 30  # First 30 minutes = opening range

        # Volume confirmation: volume must be this many times the average
        self.volume_surge_multiplier = 1.5  # 50% above average confirms breakout

        # Time window: only trade from 9:45 AM to 10:30 AM ET
        # (gives 15-30 min for range to form, then watch for breakouts)
        self.trading_start_hour = 9
        self.trading_start_minute = 45
        self.trading_end_hour = 10
        self.trading_end_minute = 30

    async def analyze(self,
                     market_data: Dict[str, Any],
                     options_data: Dict[str, Any],
                     context: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze opening range and detect breakouts.

        Args:
            market_data: Current price, opening range data, volume
            options_data: Current options IV and flow
            context: Current time, market regime

        Returns:
            Signal if breakout is detected, None otherwise
        """

        symbol = "SPY"

        # STEP 1: Check if we're in the right time window
        # Opening range strategy only works early in the day
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute

        # Convert to comparable format: 945 = 9:45 AM, 1030 = 10:30 AM
        current_time = current_hour * 100 + current_minute
        trading_start = self.trading_start_hour * 100 + self.trading_start_minute
        trading_end = self.trading_end_hour * 100 + self.trading_end_minute

        if not (trading_start <= current_time <= trading_end):
            # Not in the right time window for this strategy
            return None

        # STEP 2: Extract all required market data
        try:
            current_price = market_data.get(symbol, {}).get('current_price')
            volume = market_data.get(symbol, {}).get('volume')
            avg_volume = market_data.get(symbol, {}).get('avg_volume')
            vwap = market_data.get(symbol, {}).get('vwap')

            # Opening range data (should be pre-calculated by data provider)
            opening_high = market_data.get(symbol, {}).get('opening_high')
            opening_low = market_data.get(symbol, {}).get('opening_low')

            # Options data
            iv = options_data.get(symbol, {}).get('iv')

            # Context
            vix = context.get('vix', 20)

            # Validate minimum required data
            if not all([current_price, volume, opening_high, opening_low, vwap]):
                return None

        except (KeyError, TypeError, AttributeError):
            return None

        # STEP 3: Calculate opening range width
        # Width = how much room between the high and low
        # A wider range = stronger breakout required
        opening_range_width = opening_high - opening_low

        if opening_range_width <= 0:
            # No opening range data yet, can't trade
            return None

        # STEP 4: Detect breakout direction
        # Breakout above = price > opening_high + small buffer (buffer prevents whipsaws)
        # Breakout below = price < opening_low - small buffer

        breakout_buffer = opening_range_width * 0.05  # 5% buffer
        upside_breakout_level = opening_high + breakout_buffer
        downside_breakout_level = opening_low - breakout_buffer

        is_upside_breakout = current_price > upside_breakout_level
        is_downside_breakout = current_price < downside_breakout_level

        if not (is_upside_breakout or is_downside_breakout):
            # No breakout yet, price still in opening range
            return None

        # STEP 5: Confirm breakout with volume
        # Breakout needs volume - if it's on low volume, it's likely to fail

        score = 0.0
        signal_details = []

        if volume is not None and avg_volume is not None and avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio > self.volume_surge_multiplier:
                # Volume confirms the breakout
                score += 30
                signal_details.append(f"Volume surge {volume_ratio:.1f}x average confirms breakout (+30 pts)")
            else:
                # Low volume = weak breakout = less confident
                score += 10
                signal_details.append(f"Low volume {volume_ratio:.1f}x, breakout not fully confirmed (+10 pts)")

        # STEP 6: Confirm with VWAP alignment
        # If price is breaking up AND above VWAP, that's very strong
        # If price is breaking down AND below VWAP, that's very strong

        if is_upside_breakout and current_price > vwap:
            score += 20
            signal_details.append("Price above VWAP confirms uptrend (+20 pts)")
        elif is_downside_breakout and current_price < vwap:
            score += 20
            signal_details.append("Price below VWAP confirms downtrend (+20 pts)")
        else:
            # Price breaking but not aligned with VWAP = weaker signal
            score += 5
            signal_details.append("Breakout not fully confirmed by VWAP (+5 pts)")

        # STEP 7: Determine direction
        if is_upside_breakout:
            direction = "CALL"
            action = "BUY CALL"
            signal_details.insert(0, f"UPSIDE BREAKOUT above {opening_high:.2f}")
        else:
            direction = "PUT"
            action = "BUY PUT"
            signal_details.insert(0, f"DOWNSIDE BREAKOUT below {opening_low:.2f}")

        # STEP 8: Calculate confidence
        # Base confidence on score (0-50 pts = well-confirmed signal)
        base_confidence = min(0.85, 0.30 + (score / 100.0))

        # VIX adjustment: high VIX reduces confidence for 0DTE (more prone to whipsaws)
        if vix > 25:
            vix_reduction = 1.0 - ((vix - 25) / 50.0 * 0.2)
            base_confidence *= vix_reduction
            signal_details.append(f"VIX {vix:.1f} - reduced confidence due to elevated fear")

        self.last_score = score
        self.last_confidence = base_confidence

        # Don't trade if confidence is too low
        if base_confidence < 0.50:
            return None

        # STEP 9: Select strike and expiration
        # For 0DTE breakouts, we want short expiration for fast decay
        # ATM (at-the-money) for directional plays

        # Strike selection: ATM works best for breakouts
        strike = round(current_price * 2) / 2  # Round to nearest $0.50

        # DTE: 0DTE or 1DTE for opening range
        # Use 0DTE if very confident, 1DTE if less confident
        if base_confidence > 0.70:
            dte = 0  # Same day expiration = fastest decay
            expiry_str = "0DTE"
        else:
            dte = 1  # Next day expiration
            expiry_str = "1DTE"

        _expiry_date = datetime.now() + timedelta(days=dte)

        # STEP 10: Calculate entry, stop loss, and profit target
        # For 0DTE options, premiums are cheaper but move faster

        # Estimate premium: roughly (IV% / 100) * stock_price * days_to_expiration * 0.1
        # For 0DTE, this gets very small, so use minimum
        estimated_premium = max(0.05, (iv / 100.0) * current_price * 0.02)
        entry_price = estimated_premium

        # Stop loss: the opposite side of the opening range
        # If we're buying a CALL (bullish), stop loss is the opening low
        # If we're buying a PUT (bearish), stop loss is the opening high
        if direction == "CALL":
            _stop_loss_level = opening_low
        else:
            _stop_loss_level = opening_high

        # For options: convert stop loss level to option premium
        # Rough: if price drops below opening range, option loses value
        stop_loss = entry_price * 0.50  # Lost 50% of premium

        # Profit target: the range width * 1.5
        # If range was 449-451 (width 2), target is 3 points away
        range_profit_distance = opening_range_width * 1.5

        if direction == "CALL":
            # For call, target is opening high + range width * 1.5
            _target_price = opening_high + range_profit_distance
        else:
            # For put, target is opening low - range width * 1.5
            _target_price = opening_low - range_profit_distance

        # Convert price target to option premium estimate
        # Rough: option worth 2-3x entry premium if price moves favorably
        profit_target = entry_price * 2.5  # Aim for 2.5x return

        # Risk/reward
        potential_profit = profit_target - entry_price
        potential_loss = entry_price - stop_loss

        if potential_loss > 0:
            risk_reward = potential_profit / potential_loss
        else:
            risk_reward = 0

        # STEP 11: Create reasoning
        reasoning = f"""
        Opening Range Breakout Analysis:

        Opening Range: {opening_low:.2f} to {opening_high:.2f} (width: {opening_range_width:.2f})
        Current Price: {current_price:.2f}

        Signals:
        {chr(10).join(signal_details)}

        Trade Details:
        Direction: {direction} (breakout direction)
        Strike: ${strike:.2f}
        Expiration: {expiry_str} (0DTE is fastest)
        Entry: ${entry_price:.2f}
        Stop Loss: ${stop_loss:.2f} (opposite side of range)
        Profit Target: ${profit_target:.2f}
        Risk/Reward: {risk_reward:.2f}:1
        Confidence: {base_confidence*100:.1f}%

        Note: 0DTE breakouts are fast - profit target should be hit or stop loss
        triggered within hours, not days. Perfect for day traders.
        """.strip()

        self.last_reasoning = reasoning

        # STEP 12: Create and return Signal
        signal = Signal(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            strategy="OpeningRangeBreakout",
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
                "opening_high": opening_high,
                "opening_low": opening_low,
                "opening_range_width": opening_range_width,
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
