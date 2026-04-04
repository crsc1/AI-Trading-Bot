"""
Credit Spread Strategy Module - Income from Selling Premium

This is a different style of trading: instead of buying options (buying premium),
we SELL options (collect premium). It's for traders with more capital and risk tolerance.

For beginners: When you BUY a call, you pay money ($100) hoping to sell it for $150 (profit $50).
When you SELL a call spread, you COLLECT money upfront ($30), and keep it if price doesn't move
too far. You risk $70 to keep $30.

Key concepts:
- Bull Put Spread: sell puts when bullish (high IV environment)
- Bear Call Spread: sell calls when bearish
- Iron Condor: sell both sides when neutral and IV is elevated
- Probability of Profit (POP): statistical chance the trade wins > 65%
- These DO NOT count as day trades (great for PDT!)

Important: This is a more advanced strategy for traders with:
- More capital (wider spreads = more capital requirement)
- Understanding of credit risk
- OK with systematic losses on some trades for consistent small wins
"""

from datetime import datetime
from typing import Optional, Dict, Any
from strategies.base import BaseStrategy, Signal


class CreditSpreadStrategy(BaseStrategy):
    """
    Credit Spread Strategy for consistent income from elevated IV environments.

    This strategy sells option spreads (collects premium) instead of buying options.

    Logic:
    1. Wait for IV to be elevated (IV Rank > 50)
    2. Sell OTM spreads with 65%+ probability of profit
    3. Bull put spread when bullish
    4. Bear call spread when bearish
    5. Iron condor when neutral
    6. Collect credit, manage for 50% of max credit received
    7. Close before expiration to avoid assignment risk

    Key advantages:
    - Collect money TODAY (not wait for profit)
    - Work even if market doesn't move (theta decay is our friend)
    - PDT exempt (can hold spreads multiple days)
    - High win rate on credit spreads (usually 65-70% wins)
    - Limited risk (defined by spread width)

    Key disadvantages:
    - Requires more capital (to cover spread width)
    - Some losses can be bigger than profits
    - Need good risk management
    """

    def __init__(self, name: str = "CreditSpreadStrategy", weight: float = 1.0):
        """
        Initialize the Credit Spread Strategy.

        Args:
            name: Strategy name for logging
            weight: How much this strategy influences final decision
        """
        super().__init__(name=name, weight=weight)

        # Store for confidence calculation
        self.last_score = 0.0
        self.last_confidence = 0.0
        self.last_reasoning = ""

        # IV parameters (when to sell spreads)
        self.iv_rank_threshold = 50  # IV Rank > 50% = elevated IV (good for selling)
        self.iv_rank_very_high_threshold = 75  # IV Rank > 75% = extremely high (best selling)

        # Probability of Profit (POP) targets
        self.min_pop = 0.65  # Minimum 65% chance the trade wins
        self.target_pop = 0.70  # Target 70% chance of profit

        # Spread parameters
        self.min_spread_width = 2  # Minimum $2 wide
        self.max_spread_width = 5  # Maximum $5 wide

        # DTE (Days To Expiration)
        self.min_dte = 14  # Minimum 2 weeks
        self.max_dte = 30  # Maximum 4 weeks
        self.preferred_dte = 21  # Target 3 weeks

    async def analyze(self,
                     market_data: Dict[str, Any],
                     options_data: Dict[str, Any],
                     context: Dict[str, Any]) -> Optional[Signal]:
        """
        Analyze IV environment and generate credit spread signals.

        Args:
            market_data: Current price, technical indicators
            options_data: IV, IV Rank, options chain data
            context: Market regime, VIX

        Returns:
            Signal if credit spread setup is found, None otherwise
        """

        symbol = "SPY"

        # STEP 1: Extract all required data
        try:
            current_price = market_data.get(symbol, {}).get('current_price')

            # IV data
            iv = options_data.get(symbol, {}).get('iv')
            iv_rank = options_data.get(symbol, {}).get('iv_rank')  # 0-100 scale

            # Technical indicators to determine bias
            rsi = market_data.get(symbol, {}).get('rsi')
            ema_9 = market_data.get(symbol, {}).get('ema_9')
            ema_21 = market_data.get(symbol, {}).get('ema_21')

            # Context data
            vix = context.get('vix', 20)

            # Validate required data
            if not all([current_price, iv, iv_rank, rsi, ema_9, ema_21]):
                return None

        except (KeyError, TypeError, AttributeError):
            return None

        # STEP 2: Check if IV is elevated enough to justify selling premium
        if iv_rank < self.iv_rank_threshold:
            # IV is too low, not worth selling premium
            return None

        score = 0.0
        signal_details = []

        # STEP 3: Score the IV environment
        if iv_rank > self.iv_rank_very_high_threshold:
            score += 30
            signal_details.append(f"IV Rank {iv_rank:.0f}% - EXTREMELY HIGH (best for selling)")
        elif iv_rank > self.iv_rank_threshold:
            score += 20
            signal_details.append(f"IV Rank {iv_rank:.0f}% - Elevated (good for selling)")

        # STEP 4: Determine market bias (bullish/bearish/neutral) to pick spread type
        is_uptrend = ema_9 > ema_21
        is_downtrend = ema_9 < ema_21

        if is_uptrend and rsi < 70:
            # Uptrend but not overbought = bullish = sell put spread (bet on up movement)
            spread_type = "BULL_PUT_SPREAD"
            direction = "PUT"
            bias = "BULLISH"
            signal_details.append("EMA shows uptrend, selling put spread")
            score += 15

        elif is_downtrend and rsi > 30:
            # Downtrend but not oversold = bearish = sell call spread (bet on down movement)
            spread_type = "BEAR_CALL_SPREAD"
            direction = "CALL"
            bias = "BEARISH"
            signal_details.append("EMA shows downtrend, selling call spread")
            score -= 15

        else:
            # Choppy/neutral market = sell iron condor (sell both sides)
            spread_type = "IRON_CONDOR"
            direction = "NEUTRAL"
            bias = "NEUTRAL"
            signal_details.append("Market is range-bound, selling iron condor")
            score += 10

        # STEP 5: Calculate strikes for the spread
        # Key principle: sell OTM (out of the money) to maximize probability of profit

        # For bull put spread: sell puts below current price
        # Example: SPY at 450, sell 448 put, buy 446 put (2-wide spread)

        # For bear call spread: sell calls above current price
        # For iron condor: sell both calls and puts

        # Determine spread width based on IV and confidence
        if iv_rank > 75:
            spread_width = 5  # High IV = wider spreads, more credit
        elif iv_rank > 60:
            spread_width = 4
        else:
            spread_width = 3

        # Calculate strikes (OTM = safer)
        strike_offset = spread_width * 1.5  # Sell strike is 1.5x width away from current

        if spread_type == "BULL_PUT_SPREAD":
            # Sell puts below current price
            short_strike = round((current_price - strike_offset) * 2) / 2
            long_strike = short_strike - spread_width  # Long strike is further OTM

            signal_details.append(f"Sell ${short_strike:.2f} Put, Buy ${long_strike:.2f} Put")

        elif spread_type == "BEAR_CALL_SPREAD":
            # Sell calls above current price
            short_strike = round((current_price + strike_offset) * 2) / 2
            long_strike = short_strike + spread_width  # Long strike is further OTM

            signal_details.append(f"Sell ${short_strike:.2f} Call, Buy ${long_strike:.2f} Call")

        else:  # IRON CONDOR
            # Sell both calls and puts
            call_short = round((current_price + strike_offset) * 2) / 2
            call_long = call_short + spread_width

            put_short = round((current_price - strike_offset) * 2) / 2
            put_long = put_short - spread_width

            signal_details.append(f"Iron Condor: Sell {put_short:.2f}P/{call_short:.2f}C")
            signal_details.append(f"            Buy {put_long:.2f}P/{call_long:.2f}C")

        # STEP 6: Estimate probability of profit (POP)
        # Rough estimate: ATM option has 50% POP, each strike away = ~5% better
        # Short strike is OTM, so we start with better than 50%

        strike_distance = strike_offset / current_price  # Distance as % of price
        estimated_pop = 0.50 + (strike_distance * 0.3)  # Simplified
        estimated_pop = min(0.85, max(0.50, estimated_pop))  # Clamp to reasonable range

        if estimated_pop < self.min_pop:
            # POP too low, don't trade this spread
            return None

        signal_details.append(f"Probability of Profit: {estimated_pop*100:.1f}%")

        # Normalize score
        score = max(-100, min(100, score))

        # STEP 7: Calculate confidence
        # Confidence depends on: IV rank, POP, and market regime

        base_confidence = 0.50

        # IV Rank boost
        base_confidence += (iv_rank / 100.0) * 0.25

        # POP boost
        if estimated_pop > 0.70:
            base_confidence += 0.15
        else:
            base_confidence += 0.05

        base_confidence = min(0.90, base_confidence)

        # VIX adjustment: high VIX makes spreads more profitable but riskier
        if vix > 35:
            vix_boost = 1.0 + ((vix - 35) / 50.0 * 0.1)
            base_confidence *= vix_boost

        self.last_score = score
        self.last_confidence = base_confidence

        # Don't trade if confidence is too low
        if base_confidence < 0.55:
            return None

        # STEP 8: Select expiration
        # Credit spreads are typically 14-30 DTE
        # 21 DTE is the sweet spot (theta decay accelerates in final 2 weeks)

        dte = self.preferred_dte
        expiry_str = f"{dte}DTE"

        # STEP 9: Calculate credit received and risk
        # Rough estimation of credit:
        # Higher IV = higher premiums
        # OTM = lower premium

        # Estimate: credit = (IV% / 100) * current_price * 0.02 * spread_width
        estimated_credit = (iv / 100.0) * current_price * 0.02 * spread_width
        estimated_credit = max(0.10, estimated_credit)  # Minimum realistic credit

        # Max loss = spread width - credit received
        max_risk = (spread_width * 100) - (estimated_credit * 100)  # In dollars (100 share contract)
        max_risk = max(50, max_risk)  # Minimum realistic risk

        # Entry price: we RECEIVE the credit (positive cash)
        entry_price = estimated_credit

        # Profit target: 50% of max credit
        profit_target = estimated_credit * 0.5

        # Stop loss: 100% of credit (break-even) or 150% of credit if trade is going wrong
        stop_loss = estimated_credit * 1.5

        # Risk/reward for credit spread (reversed: we're collecting, not buying)
        potential_profit = profit_target
        potential_risk = max_risk / 100.0  # Convert back to option contract price

        if potential_risk > 0:
            risk_reward = potential_profit / potential_risk
        else:
            risk_reward = 0

        # STEP 10: Create reasoning
        action = f"SELL {spread_type.replace('_', ' ')}"

        reasoning = f"""
        Credit Spread Analysis (Sell Premium):

        IV Environment: Rank {iv_rank:.0f}%, Absolute {iv:.1f}%
        Market Bias: {bias}
        Spread Type: {spread_type}

        Signals:
        {chr(10).join(signal_details)}

        Spread Details:
        Action: {action}
        Width: ${spread_width:.2f}
        Expiration: {dte} days ({expiry_str})
        Probability of Profit: {estimated_pop*100:.1f}%

        Credit Management:
        Credit Received: ${estimated_credit:.2f}
        Profit Target: ${profit_target:.2f} (50% of credit)
        Stop Loss: ${stop_loss:.2f} (150% of credit)
        Max Risk per Spread: ${max_risk:.0f} (spread width)
        Risk/Reward: {risk_reward:.2f}:1
        Confidence: {base_confidence*100:.1f}%

        Strategy Notes:
        - THIS DOES NOT COUNT AS A DAY TRADE (good for PDT!)
        - Sell premium when IV is elevated
        - Management: close at 50% max profit or 150% of credit max loss
        - Avoid holding into earnings
        - Exit with 7+ DTE remaining (avoid gamma risk)
        - Multiple spreads can be sold across different strikes (iron butterfly, etc)
        """.strip()

        self.last_reasoning = reasoning

        # STEP 11: Create and return Signal
        signal = Signal(
            timestamp=datetime.now(),
            symbol=symbol,
            direction=direction,
            strategy="CreditSpreadStrategy",
            score=score,
            confidence=base_confidence,
            recommended_action=action,
            strike=round(current_price * 2) / 2,  # Just for reference
            expiry=expiry_str,
            entry_price=entry_price,  # This is CREDIT received (positive)
            stop_loss=stop_loss,  # Max loss in credits
            profit_target=profit_target,  # 50% of credit
            risk_reward=risk_reward,
            reasoning=reasoning,
            metadata={
                "iv_rank": iv_rank,
                "iv": iv,
                "spread_type": spread_type,
                "spread_width": spread_width,
                "estimated_pop": estimated_pop,
                "vix": vix,
                "market_bias": bias,
                "max_risk_dollars": max_risk,
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
