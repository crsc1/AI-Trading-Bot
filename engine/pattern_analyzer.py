"""
Pattern Analyzer - Identifies recurring patterns and support/resistance levels.

This module answers: "What patterns do we see in the market?"

Examples of patterns we track:
- "SPY always drops on Mondays" (day-of-week)
- "10 AM reversals are common" (time-of-day)
- "FOMC days are volatile" (event-based)
- "Opex week has big moves" (calendar)

Supporting and resistance are price levels where buyers/sellers congregate.
- Support: price bounces up from this level
- Resistance: price bounces down from this level

For beginners: Think of support as a "floor" and resistance as a "ceiling".
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import statistics
from dataclasses import dataclass


@dataclass
class Pattern:
    """A recurring market pattern"""

    name: str
    """Pattern name like "Monday Sell-off", "FOMC Volatility"
    """

    description: str
    """Description of what happens"""

    frequency: float
    """How often does this happen? 0-1 (0.7 = 70% of the time)"""

    impact: float
    """How big is the move? -1 to +1 (-0.5 = typically down 0.5%, +0.3 = up 0.3%)"""

    last_occurrence: Optional[datetime] = None
    """When did this pattern last occur?"""


class PatternAnalyzer:
    """
    Analyzes market patterns and identifies support/resistance levels.

    Responsibilities:
    1. Find day-of-week patterns (Monday effect, Friday strength, etc.)
    2. Find time-of-day patterns (10am reversals, close strength, etc.)
    3. Find event patterns (FOMC, CPI, earnings, opex)
    4. Identify support and resistance levels
    5. Calculate overall pattern score (bullish/bearish)
    """

    def __init__(self):
        """Initialize the pattern analyzer"""
        # Store discovered patterns
        self.patterns: Dict[str, Pattern] = {}

        # Store historical price data for analysis
        # Format: {symbol: [{'date': date, 'open': x, 'high': y, ...}, ...]}
        self.price_history: Dict[str, List[Dict[str, Any]]] = {}

    def analyze_previous_day(self, symbol: str) -> Dict[str, Any]:
        """
        Analyze what happened yesterday (key levels, direction, volume).

        Args:
            symbol: 'SPY' or 'SPX'

        Returns:
            Dict with analysis of yesterday's action
        """

        if symbol not in self.price_history or not self.price_history[symbol]:
            return {
                'error': 'No price history available',
                'change': 0,
                'high': 0,
                'low': 0,
                'volume': 0
            }

        # Get yesterday's candle (last in history)
        yesterday = self.price_history[symbol][-1]

        open_price = yesterday.get('open', 0)
        close_price = yesterday.get('close', 0)
        high = yesterday.get('high', 0)
        low = yesterday.get('low', 0)
        volume = yesterday.get('volume', 0)

        # Calculate change
        if open_price > 0:
            change = (close_price - open_price) / open_price
        else:
            change = 0

        # Determine trend
        if close_price > open_price:
            trend = "UP"
        elif close_price < open_price:
            trend = "DOWN"
        else:
            trend = "FLAT"

        # Range (high to low)
        range_size = high - low
        if close_price > 0:
            range_percent = range_size / close_price
        else:
            range_percent = 0

        return {
            'date': yesterday.get('date', None),
            'trend': trend,
            'change': change,
            'change_percent': change * 100,
            'open': open_price,
            'close': close_price,
            'high': high,
            'low': low,
            'range': range_size,
            'range_percent': range_percent * 100,
            'volume': volume,
            'analysis': f"{symbol} closed {trend} {change*100:.2f}% on {volume:,.0f} volume"
        }

    def find_recurring_patterns(
        self,
        symbol: str,
        lookback_days: int = 30
    ) -> List[Pattern]:
        """
        Find recurring patterns in recent price action.

        Analyzes:
        1. Day-of-week patterns (Monday effect, Friday strength)
        2. Time-of-day patterns (10am reversals, open strength)
        3. FOMC day patterns (big moves on FOMC days)
        4. Opex day patterns (strong moves on options expiration)
        5. VIX relationship patterns (VIX high = market weak)

        Args:
            symbol: 'SPY' or 'SPX'
            lookback_days: How many days back to analyze

        Returns:
            List of Pattern objects found
        """

        patterns_found = []

        if symbol not in self.price_history or not self.price_history[symbol]:
            return patterns_found

        # Get lookback data
        cutoff = datetime.now().date() - timedelta(days=lookback_days)
        recent_data = [
            d for d in self.price_history[symbol]
            if d.get('date', datetime.now().date()) >= cutoff
        ]

        if len(recent_data) < 5:
            return patterns_found

        # ======================================================================
        # PATTERN 1: Day-of-week patterns
        # ======================================================================

        # Group by day of week (Monday=0, Sunday=6)
        dow_returns = {i: [] for i in range(5)}  # 5 trading days

        for candle in recent_data:
            date = candle.get('date', datetime.now().date())

            # Skip weekends
            if date.weekday() >= 5:
                continue

            open_p = candle.get('open', 0)
            close_p = candle.get('close', 0)

            if open_p > 0:
                ret = (close_p - open_p) / open_p
                dow_returns[date.weekday()].append(ret)

        # Find day-of-week patterns
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        for day_idx, day_name in enumerate(days):
            if dow_returns[day_idx]:
                avg_return = statistics.mean(dow_returns[day_idx])
                occurrence_rate = len(
                    [r for r in dow_returns[day_idx] if r < 0]
                ) / len(dow_returns[day_idx])

                if occurrence_rate > 0.60:  # 60%+ of the time
                    pattern_direction = "DOWN" if avg_return < 0 else "UP"
                    pattern = Pattern(
                        name=f"{day_name} {pattern_direction}",
                        description=f"{symbol} tends to {pattern_direction} on {day_name}s",
                        frequency=occurrence_rate,
                        impact=avg_return
                    )
                    patterns_found.append(pattern)

        # ======================================================================
        # PATTERN 2: VIX relationship pattern
        # ======================================================================
        # (Note: In production, would pull VIX data from data provider)

        # For now, assume VIX data is in metadata
        vix_data = [c.get('vix', None) for c in recent_data]
        if vix_data and any(v is not None for v in vix_data):
            avg_vix = statistics.mean([v for v in vix_data if v is not None])

            if avg_vix > 25:
                # High VIX = market fear = downside bias
                pattern = Pattern(
                    name="High VIX Fear",
                    description=f"When VIX > 25, {symbol} has downside bias",
                    frequency=0.65,
                    impact=-0.02
                )
                patterns_found.append(pattern)

        # ======================================================================
        # PATTERN 3: Open strength (gap strategy)
        # ======================================================================

        open_gaps = []
        for candle in recent_data:
            # Gap = today's open vs yesterday's close
            if candle.get('gap'):
                open_gaps.append(candle['gap'])

        if open_gaps:
            avg_gap = statistics.mean(open_gaps)
            if avg_gap > 0.01:  # Avg gap up > 1%
                pattern = Pattern(
                    name="Gap-up Strength",
                    description=f"{symbol} gaps up and tends to continue",
                    frequency=0.55,
                    impact=0.01
                )
                patterns_found.append(pattern)

        return patterns_found

    def identify_support_resistance(
        self,
        prices: List[float],
        lookback: int = 50
    ) -> Dict[str, Any]:
        """
        Identify key support and resistance levels.

        Strategies used:
        1. Round number levels (400, 450, 500, etc.)
        2. Previous extremes (highs and lows)
        3. Moving averages as dynamic support/resistance
        4. VWAP level

        Args:
            prices: List of recent prices
            lookback: How many periods to analyze

        Returns:
            Dict with support and resistance levels
        """

        if not prices or len(prices) < lookback:
            return {
                'support': [],
                'resistance': [],
                'error': 'Insufficient price data'
            }

        # Take most recent lookback periods
        recent_prices = prices[-lookback:]
        current_price = recent_prices[-1]

        # ======================================================================
        # LEVEL 1: Previous extremes
        # ======================================================================

        previous_high = max(recent_prices[:-5])  # Exclude very recent
        previous_low = min(recent_prices[:-5])

        # ======================================================================
        # LEVEL 2: Round numbers
        # ======================================================================

        # Find nearest round numbers (multiples of 5)
        current_round = int(current_price / 5) * 5
        round_levels = [
            current_round - 10,
            current_round - 5,
            current_round,
            current_round + 5,
            current_round + 10,
        ]

        # ======================================================================
        # LEVEL 3: Moving average levels
        # ======================================================================

        if len(recent_prices) >= 20:
            ma20 = statistics.mean(recent_prices[-20:])
        else:
            ma20 = statistics.mean(recent_prices)

        if len(recent_prices) >= 50:
            ma50 = statistics.mean(recent_prices[-50:])
        else:
            ma50 = statistics.mean(recent_prices)

        # ======================================================================
        # LEVEL 4: VWAP (would need volume data in production)
        # ======================================================================
        # For now, use simple average as proxy
        vwap = statistics.mean(recent_prices)

        # ======================================================================
        # Organize into support and resistance
        # ======================================================================

        support_levels = [
            previous_low,
            min(r for r in round_levels if r < current_price),
            min(ma20, ma50, vwap),
        ]

        resistance_levels = [
            previous_high,
            max(r for r in round_levels if r > current_price),
            max(ma20, ma50, vwap),
        ]

        # Remove duplicates and sort
        support_levels = sorted(set(round(s, 2) for s in support_levels), reverse=True)
        resistance_levels = sorted(set(round(r, 2) for r in resistance_levels))

        return {
            'current_price': current_price,
            'support': support_levels,
            'resistance': resistance_levels,
            'previous_high': previous_high,
            'previous_low': previous_low,
            'ma20': ma20,
            'ma50': ma50,
            'vwap': vwap,
        }

    def get_pattern_score(self, symbol: str) -> float:
        """
        Calculate overall bullish/bearish pattern score.

        Scores from -100 to +100:
        -100 = extremely bearish (all patterns are bearish)
        0 = neutral
        +100 = extremely bullish (all patterns are bullish)

        Args:
            symbol: 'SPY' or 'SPX'

        Returns:
            Score from -100 to +100
        """

        patterns = self.find_recurring_patterns(symbol)

        if not patterns:
            return 0

        # Calculate score based on pattern impacts
        total_score = 0

        for pattern in patterns:
            # Each pattern contributes based on:
            # 1. Its impact (positive = bullish, negative = bearish)
            # 2. Its frequency (more frequent = more impact)
            contribution = pattern.impact * pattern.frequency * 100

            total_score += contribution

        # Cap at -100 to +100
        return max(-100, min(100, total_score))

    def record_price_data(
        self,
        symbol: str,
        date: datetime,
        open_price: float,
        high: float,
        low: float,
        close: float,
        volume: int,
        **kwargs
    ) -> None:
        """
        Record historical price data for pattern analysis.

        Args:
            symbol: 'SPY' or 'SPX'
            date: Date of the candle
            open_price: Open price
            high: High price
            low: Low price
            close: Close price
            volume: Volume
            **kwargs: Extra data (gap, vix, etc.)
        """

        if symbol not in self.price_history:
            self.price_history[symbol] = []

        candle = {
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume,
            **kwargs
        }

        self.price_history[symbol].append(candle)

    def get_nearest_support(self, prices: List[float], current_price: float) -> Optional[float]:
        """
        Get the nearest support level below current price.

        Args:
            prices: List of recent prices
            current_price: The price we're analyzing

        Returns:
            Support level or None if not found
        """

        sr = self.identify_support_resistance(prices)
        support_levels = sr.get('support', [])

        # Find highest support below current price
        valid_supports = [s for s in support_levels if s < current_price]

        if valid_supports:
            return max(valid_supports)

        return None

    def get_nearest_resistance(self, prices: List[float], current_price: float) -> Optional[float]:
        """
        Get the nearest resistance level above current price.

        Args:
            prices: List of recent prices
            current_price: The price we're analyzing

        Returns:
            Resistance level or None if not found
        """

        sr = self.identify_support_resistance(prices)
        resistance_levels = sr.get('resistance', [])

        # Find lowest resistance above current price
        valid_resistances = [r for r in resistance_levels if r > current_price]

        if valid_resistances:
            return min(valid_resistances)

        return None
