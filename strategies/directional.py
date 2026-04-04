"""
Directional Strategy Module - The Core Multi-Signal Analyzer

This is the main workhorse strategy that combines multiple technical indicators,
sentiment analysis, and options flow to determine market direction (bullish or bearish).

For beginners: Think of this strategy as a "panel of experts" where each expert
(RSI, MACD, sentiment, etc.) votes on whether the market is going up or down.
The strategy adds up all the votes and decides which way to trade.

Key Signals:
- RSI oversold (<30) = market is too low, likely to bounce up (BUY CALL)
- RSI overbought (>70) = market is too high, likely to pull back (BUY PUT)
- MACD bullish crossover = momentum turning up (BUY CALL)
- MACD bearish crossover = momentum turning down (BUY PUT)
- Price above VWAP = trading above fair value = bullish
- Volume surge = confirms the move is strong
- Positive sentiment = smart money buying
- Bullish options flow = big money is buying calls
- Low VIX = complacency, OK to trade
- High VIX = fear, need more confirmation
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from strategies.base import BaseStrategy, Signal


class DirectionalStrategy(BaseStrategy):
    """
    Multi-Signal Directional Analysis Strategy.

    This strategy scores multiple technical and sentiment indicators to generate
    BUY CALL or BUY PUT signals. It's the most comprehensive strategy.

    Scoring System:
    - RSI oversold (<30): +20 points (bullish)
    - RSI overbought (>70): -20 points (bearish)
    - MACD bullish crossover: +15 points
    - MACD bearish crossover: -15 points
    - Price above VWAP: +10 points
    - Price below VWAP: -10 points
    - Volume surge (>1.5x average): +10 points
    - Positive sentiment: +15 points
    - Negative sentiment: -15 points
    - Bullish options flow: +20 points
    - Bearish options flow: -20 points
    - VIX adjustment: reduce confidence by 20% if VIX > 25

    Total score range: -100 to +100
    """

    def __init__(self, name: str = "DirectionalStrategy", weight: float = 1.0):
        """
        Initialize the Directional Strategy.

        Args:
            name: Strategy name for logging
            weight: How much this strategy influences the final decision
        """
        super().__init__(name=name, weight=weight)

        # Store the last calculated score and confidence for the confidence() method
        self.last_score = 0.0
        self.last_confidence = 0.0
        self.last_reasoning = ""

        # RSI parameters (standard settings)
        self.rsi_oversold = 30      # RSI below 30 = too low (bullish bounce)
        self.rsi_overbought = 70    # RSI above 70 = too high (bearish pullback)

        # Volume threshold for "surge detection"
        self.volume_surge_multiplier = 1.5  # 50% above average is a surge

        # VIX threshold for market fear
        self.vix_caution_level = 25  # Above 25 = elevated fear

    async def analyze(self,
                     market_data: Dict[str, Any],
                     options_data: Dict[str, Any],
                     context: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze market conditions using multiple signals and generate a trading signal.

        Args:
            market_data: Current price, volume, technical indicators
            options_data: Options chain info, IV, flow data
            context: VIX, market regime, time of day

        Returns:
            Signal object if conditions are met, None otherwise
        """

        # For this example, we'll work with SPY (you could make this configurable)
        symbol = "SPY"

        # STEP 1: Extract all the data we need
        # If any critical data is missing, return None (don't crash)
        try:
            current_price = market_data.get(symbol, {}).get('current_price')
            _high = market_data.get(symbol, {}).get('high')
            _low = market_data.get(symbol, {}).get('low')
            volume = market_data.get(symbol, {}).get('volume')
            avg_volume = market_data.get(symbol, {}).get('avg_volume')
            vwap = market_data.get(symbol, {}).get('vwap')

            # Technical indicators
            rsi = market_data.get(symbol, {}).get('rsi')
            macd = market_data.get(symbol, {}).get('macd')
            macd_signal = market_data.get(symbol, {}).get('macd_signal')

            # Options and sentiment
            iv = options_data.get(symbol, {}).get('iv')
            call_volume = options_data.get(symbol, {}).get('call_volume')
            put_volume = options_data.get(symbol, {}).get('put_volume')
            sentiment = options_data.get(symbol, {}).get('sentiment')  # 1.0 = bullish, -1.0 = bearish
            options_flow = options_data.get(symbol, {}).get('options_flow')  # bullish/bearish/neutral

            # Context data
            vix = context.get('vix', 20)

            # Validate minimum required data
            if not all([current_price, volume, rsi, macd, macd_signal, vwap]):
                return None

        except (KeyError, TypeError, AttributeError):
            return None

        # STEP 2: Calculate the score by evaluating each signal
        score = 0.0
        signal_count = 0
        signal_details = []

        # ===== RSI ANALYSIS =====
        # RSI measures momentum. <30 = oversold, >70 = overbought
        if rsi is not None:
            if rsi < self.rsi_oversold:
                # Oversold = market is too low, likely to bounce UP
                score += 20
                signal_details.append(f"RSI oversold at {rsi:.1f} (+20 pts)")
                signal_count += 1
            elif rsi > self.rsi_overbought:
                # Overbought = market is too high, likely to pull back DOWN
                score -= 20
                signal_details.append(f"RSI overbought at {rsi:.1f} (-20 pts)")
                signal_count += 1

        # ===== MACD ANALYSIS =====
        # MACD crossover indicates momentum shift. Bullish = MACD > signal
        if macd is not None and macd_signal is not None:
            macd_histogram = macd - macd_signal

            if macd_histogram > 0 and macd > macd_signal:
                # MACD above signal line = bullish momentum
                score += 15
                signal_details.append("MACD bullish crossover (+15 pts)")
                signal_count += 1
            elif macd_histogram < 0 and macd < macd_signal:
                # MACD below signal line = bearish momentum
                score -= 15
                signal_details.append("MACD bearish crossover (-15 pts)")
                signal_count += 1

        # ===== VWAP ANALYSIS =====
        # VWAP is the volume-weighted average price (fair value)
        # Price above VWAP = strong hands in control = bullish
        # Price below VWAP = weak hands in control = bearish
        if vwap is not None and current_price is not None:
            if current_price > vwap:
                score += 10
                signal_details.append("Price above VWAP (+10 pts)")
                signal_count += 1
            elif current_price < vwap:
                score -= 10
                signal_details.append("Price below VWAP (-10 pts)")
                signal_count += 1

        # ===== VOLUME ANALYSIS =====
        # Volume surge = move is strong and confirmed by buyers/sellers
        if volume is not None and avg_volume is not None and avg_volume > 0:
            volume_ratio = volume / avg_volume
            if volume_ratio > self.volume_surge_multiplier:
                # High volume confirms the move
                score += 10 if score > 0 else -10  # Confirm existing direction
                signal_details.append(f"Volume surge {volume_ratio:.1f}x average (+/- 10 pts)")
                signal_count += 1

        # ===== SENTIMENT ANALYSIS =====
        # Sentiment ranges from -1 (very bearish) to +1 (very bullish)
        if sentiment is not None:
            if sentiment > 0.5:
                # Strongly positive sentiment
                score += 15
                signal_details.append(f"Positive sentiment {sentiment:.2f} (+15 pts)")
                signal_count += 1
            elif sentiment < -0.5:
                # Strongly negative sentiment
                score -= 15
                signal_details.append(f"Negative sentiment {sentiment:.2f} (-15 pts)")
                signal_count += 1

        # ===== OPTIONS FLOW ANALYSIS =====
        # Options flow = ratio of bullish calls vs bearish puts
        # Bullish flow = smart money buying calls
        # Bearish flow = smart money buying puts
        if options_flow is not None:
            if options_flow == "bullish":
                score += 20
                signal_details.append("Bullish options flow (+20 pts)")
                signal_count += 1
            elif options_flow == "bearish":
                score -= 20
                signal_details.append("Bearish options flow (-20 pts)")
                signal_count += 1
        elif call_volume is not None and put_volume is not None:
            # Calculate flow from call/put volume if available
            if call_volume + put_volume > 0:
                call_ratio = call_volume / (call_volume + put_volume)
                if call_ratio > 0.6:
                    score += 20
                    signal_details.append(f"Strong call volume ratio {call_ratio:.2f} (+20 pts)")
                    signal_count += 1
                elif call_ratio < 0.4:
                    score -= 20
                    signal_details.append(f"Strong put volume ratio {call_ratio:.2f} (-20 pts)")
                    signal_count += 1

        # STEP 3: Normalize score to -100 to +100 range
        score = max(-100, min(100, score))

        # STEP 4: Calculate confidence
        # Confidence depends on:
        # 1. How many signals are confirming the direction?
        # 2. How strong is the signal (absolute value of score)?
        # 3. Is VIX elevated (which reduces confidence)?

        base_confidence = 0.0
        if signal_count > 0:
            # More confirming signals = higher confidence
            base_confidence = min(0.95, 0.40 + (signal_count * 0.15))

        # Score strength: The further from 0, the more confident
        if abs(score) > 0:
            base_confidence += (abs(score) / 100.0) * 0.3

        # Cap at 0.95 maximum
        base_confidence = min(0.95, base_confidence)

        # VIX adjustment: High VIX = high fear = reduce confidence
        if vix > self.vix_caution_level:
            vix_adjustment = 1.0 - ((vix - self.vix_caution_level) / 100.0 * 0.3)
            base_confidence *= vix_adjustment
            signal_details.append(f"VIX {vix:.1f} - reduced confidence by 20%")

        # Store for the calculate_confidence() method
        self.last_score = score
        self.last_confidence = base_confidence

        # STEP 5: Decide if we have a strong enough signal to trade
        # Minimum confidence threshold (configurable, default 0.5 = 50%)
        min_confidence = 0.5

        if base_confidence < min_confidence:
            # Signal is too weak - don't trade
            return None

        # STEP 6: Determine direction and set up the trade
        # Score > 0 = bullish (BUY CALL)
        # Score < 0 = bearish (BUY PUT)
        # Score == 0 = neutral (no trade)

        if score > 0:
            direction = "CALL"
            action = "BUY CALL"
        elif score < 0:
            direction = "PUT"
            action = "BUY PUT"
        else:
            # No clear signal
            return None

        # STEP 7: Select strike price and expiration
        # ATM (At The Money) = current price
        # OTM (Out of The Money) = cheaper but riskier
        # Usually pick ATM or 1 strike OTM

        # For SPY, strikes are usually $1 apart
        strike_offset = 1.0 if base_confidence < 0.65 else 0  # 1 OTM if less confident, ATM if confident

        if direction == "CALL":
            strike = round((current_price + strike_offset) * 2) / 2  # Round to nearest $0.50
        else:  # PUT
            strike = round((current_price - strike_offset) * 2) / 2

        # DTE (Days To Expiration) selection based on confidence
        # Higher confidence = more willing to hold longer
        if base_confidence > 0.75:
            dte = 7  # 7 days = good time decay balance
        elif base_confidence > 0.60:
            dte = 5
        else:
            dte = 3  # 3 days minimum = faster profit/loss

        _expiry_date = datetime.now() + timedelta(days=dte)
        expiry_str = f"{dte}DTE"  # Format: "7DTE", "5DTE", etc.

        # STEP 8: Calculate entry price, stop loss, and profit target
        # Entry price is estimated option premium
        # For now, we'll estimate based on IV and moneyness

        # Rough estimation: ATM options cost about 0.01-0.05 per day of theta
        estimated_premium = (iv / 100.0) * current_price * 0.05  # Simplified estimate
        entry_price = max(0.05, estimated_premium)  # Minimum $0.05 for a real option

        # Stop loss: 15% below entry (max loss tolerance)
        stop_loss = entry_price * 0.85

        # Profit target: 30-50% above entry based on confidence
        profit_multiplier = 1.3 + (base_confidence * 0.2)  # 1.3x to 1.5x
        profit_target = entry_price * profit_multiplier

        # Risk/Reward ratio
        potential_profit = profit_target - entry_price
        potential_loss = entry_price - stop_loss

        if potential_loss > 0:
            risk_reward = potential_profit / potential_loss
        else:
            risk_reward = 0

        # STEP 9: Create the reasoning message (explain WHY we're trading)
        reasoning = f"""
        {symbol} Directional Analysis:

        Technical Signals ({signal_count} confirmed):
        {chr(10).join(signal_details)}

        Score: {score:.0f}/100 (bullish direction)
        Confidence: {base_confidence*100:.1f}%

        Entry: Buy {direction} option at ${entry_price:.2f}
        Strike: ${strike:.2f} ({dte} DTE)
        Stop Loss: ${stop_loss:.2f} (max loss)
        Profit Target: ${profit_target:.2f} (30-50% gain)
        Risk/Reward: {risk_reward:.2f}:1

        VIX: {vix:.1f} - {('High fear' if vix > self.vix_caution_level else 'Normal')}
        IV: {iv:.1f}% (implied volatility)
        """.strip()

        self.last_reasoning = reasoning

        # STEP 10: Create and return the Signal object
        signal = Signal(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            strategy="DirectionalStrategy",
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
                "macd_histogram": (macd - macd_signal) if macd and macd_signal else None,
                "vix": vix,
                "iv": iv,
                "signal_count": signal_count,
                "vwap": vwap,
            }
        )

        # Validate the signal before returning it
        if self.validate_signal(signal):
            return signal
        else:
            return None

    def calculate_confidence(self) -> float:
        """
        Return the confidence of this strategy's latest signal.

        Returns:
            Float from 0.0 to 1.0 representing confidence
        """
        return self.last_confidence
