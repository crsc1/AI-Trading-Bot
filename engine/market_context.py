"""
Market Context - Determines the overall market regime and macro context.

This module answers: "What's the overall environment right now?"

Think of market context like weather:
- Sunny (trending up) = good for buying
- Rainy (trending down) = good for shorting
- Foggy (range-bound) = need different strategy
- Stormy (volatile) = be careful

This module tells you:
1. Are we in an uptrend or downtrend?
2. Is volatility high or low?
3. Are there important events today (FOMC, earnings, etc.)?
4. How do other assets (oil, bonds, dollar) affect SPY?

For beginners: Context is CRUCIAL. The same strategy works differently
in different markets. You can't use the same approach in a bull market
as you would in a bear market.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, time
from enum import Enum


class MarketRegime(Enum):
    """The overall market trend"""

    TRENDING_UP = "trending_up"
    """Strong uptrend: good for call buying, call spreads"""

    TRENDING_DOWN = "trending_down"
    """Strong downtrend: good for put buying, put spreads"""

    RANGE_BOUND = "range_bound"
    """Trading in a range: good for iron condors, selling premium"""

    VOLATILE = "volatile"
    """High volatility: good for long options, spreads"""


class MarketContext:
    """
    Analyzes the overall market environment.

    Responsibilities:
    1. Determine market regime (trending, range, volatile)
    2. Check for important events (FOMC, earnings, etc.)
    3. Analyze correlation with other assets (oil, bonds, dollar)
    4. Calculate risk periods (first/last hour, holidays, etc.)
    """

    def __init__(self):
        """Initialize market context"""
        self.last_regime: Optional[MarketRegime] = None
        self.last_regime_update: Optional[datetime] = None

    def get_market_regime(
        self,
        atr: Optional[float] = None,
        adx: Optional[float] = None,
        vix: Optional[float] = None,
        prices: Optional[List[float]] = None
    ) -> str:
        """
        Determine the current market regime.

        Uses technical indicators:
        - ADX: How strong is the trend?
          - ADX > 30: strong trend
          - ADX < 20: weak/no trend
        - VIX: How volatile?
          - VIX > 25: elevated volatility
          - VIX < 12: low volatility
        - ATR: True range (volatility measure)
        - Moving averages: Are they aligned upward/downward?

        Args:
            atr: Average True Range value (volatility)
            adx: ADX value (trend strength)
            vix: VIX level (market fear)
            prices: List of recent prices for MA analysis

        Returns:
            String: "trending_up", "trending_down", "range_bound", "volatile"
        """

        # Default values if not provided
        if adx is None:
            adx = 25
        if vix is None:
            vix = 20

        # ======================================================================
        # STEP 1: Check for strong trend
        # ======================================================================

        strong_trend = adx > 30

        if strong_trend and prices and len(prices) >= 50:
            # Determine direction of trend using moving averages
            recent_prices = prices[-10:]
            older_prices = prices[-50:-40]

            avg_recent = sum(recent_prices) / len(recent_prices)
            avg_older = sum(older_prices) / len(older_prices)

            if avg_recent > avg_older:
                return MarketRegime.TRENDING_UP.value

            else:
                return MarketRegime.TRENDING_DOWN.value

        # ======================================================================
        # STEP 2: Check for high volatility
        # ======================================================================

        high_volatility = vix > 25

        if high_volatility:
            return MarketRegime.VOLATILE.value

        # ======================================================================
        # STEP 3: Default to range-bound
        # ======================================================================

        return MarketRegime.RANGE_BOUND.value

    def get_correlation_signals(
        self,
        oil_price: Optional[float] = None,
        oil_change_percent: Optional[float] = None,
        dollar_index: Optional[float] = None,
        dollar_change_percent: Optional[float] = None,
        bond_yield: Optional[float] = None,
        bond_yield_change_bps: Optional[float] = None,
        vix: Optional[float] = None,
        vix_change: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Analyze how other assets affect SPY/SPX.

        Key relationships (correlations):

        Oil (CL) vs SPY:
        - Oil ↑ = inflation fears = SPY ↓
        - Oil ↓ = better economic outlook OR recession fears = mixed
        - Strong negative correlation in normal times

        Dollar (DXY) vs SPY:
        - Dollar ↑ = US strong BUT hurts exports = SPY ↓
        - Dollar ↓ = exports attractive = SPY ↑
        - Inverse relationship (when dollar up, SPY down)

        Bonds (TLT) vs SPY:
        - Bonds ↑ = flight to safety = SPY ↓
        - Bonds ↓ = risk on, stocks up = SPY ↑
        - Usually inverse, but both rise on growth fear

        VIX vs SPY:
        - VIX ↑ = fear = SPY ↓
        - VIX ↓ = confidence = SPY ↑
        - Strong inverse relationship

        Args:
            oil_price: Current oil price
            oil_change_percent: Oil change % (0.05 = 5%)
            dollar_index: Dollar index level
            dollar_change_percent: Dollar change %
            bond_yield: 10-year Treasury yield
            bond_yield_change_bps: Change in basis points
            vix: Current VIX level
            vix_change: Change in VIX points

        Returns:
            Dict with correlation analysis
        """

        signals = {}

        # ======================================================================
        # OIL ANALYSIS
        # ======================================================================

        if oil_change_percent is not None:
            if oil_change_percent > 0.02:  # Oil up 2%+
                # Inflation = bad for stocks
                signals['oil_signal'] = {
                    'direction': 'BEARISH',
                    'reason': f'Oil up {oil_change_percent*100:.1f}% (inflation concern)',
                    'impact': 'SPY likely to decline'
                }
            elif oil_change_percent < -0.02:  # Oil down 2%+
                signals['oil_signal'] = {
                    'direction': 'BULLISH',
                    'reason': f'Oil down {oil_change_percent*100:.1f}% (lower inflation)',
                    'impact': 'SPY likely to rise'
                }
            else:
                signals['oil_signal'] = {
                    'direction': 'NEUTRAL',
                    'reason': 'Oil relatively flat',
                    'impact': 'Minimal impact on SPY'
                }

        # ======================================================================
        # DOLLAR ANALYSIS
        # ======================================================================

        if dollar_change_percent is not None:
            if dollar_change_percent > 0.01:  # Dollar up 1%+
                # Strong dollar = bad for exports
                signals['dollar_signal'] = {
                    'direction': 'BEARISH',
                    'reason': f'Dollar up {dollar_change_percent*100:.2f}% (hurts exports)',
                    'impact': 'SPY may decline'
                }
            elif dollar_change_percent < -0.01:  # Dollar down 1%+
                signals['dollar_signal'] = {
                    'direction': 'BULLISH',
                    'reason': f'Dollar down {dollar_change_percent*100:.2f}% (helps exports)',
                    'impact': 'SPY may rise'
                }
            else:
                signals['dollar_signal'] = {
                    'direction': 'NEUTRAL',
                    'reason': 'Dollar relatively stable',
                    'impact': 'Minimal impact on SPY'
                }

        # ======================================================================
        # BOND ANALYSIS
        # ======================================================================

        if bond_yield_change_bps is not None:
            if bond_yield_change_bps > 5:  # Yields up 5+ bps
                # Rising yields = money flows to bonds = SPY down
                signals['bond_signal'] = {
                    'direction': 'BEARISH',
                    'reason': f'10Y yield up {bond_yield_change_bps:.0f} bps (flight to safety)',
                    'impact': 'SPY may decline'
                }
            elif bond_yield_change_bps < -5:  # Yields down 5+ bps
                # Falling yields = flight to risk = SPY up
                signals['bond_signal'] = {
                    'direction': 'BULLISH',
                    'reason': f'10Y yield down {bond_yield_change_bps:.0f} bps (risk on)',
                    'impact': 'SPY may rise'
                }
            else:
                signals['bond_signal'] = {
                    'direction': 'NEUTRAL',
                    'reason': 'Bond yields stable',
                    'impact': 'Minimal impact on SPY'
                }

        # ======================================================================
        # VIX ANALYSIS
        # ======================================================================

        if vix_change is not None:
            if vix_change > 1:  # VIX up 1+ points
                # Rising VIX = fear = SPY down
                signals['vix_signal'] = {
                    'direction': 'BEARISH',
                    'reason': f'VIX up {vix_change:.1f} points (fear increasing)',
                    'impact': 'SPY likely to decline'
                }
            elif vix_change < -1:  # VIX down 1+ points
                # Falling VIX = confidence = SPY up
                signals['vix_signal'] = {
                    'direction': 'BULLISH',
                    'reason': f'VIX down {vix_change:.1f} points (fear decreasing)',
                    'impact': 'SPY likely to rise'
                }
            else:
                signals['vix_signal'] = {
                    'direction': 'NEUTRAL',
                    'reason': 'VIX stable',
                    'impact': 'Minimal impact on SPY'
                }

        return signals

    def is_high_risk_period(self) -> bool:
        """
        Are we in a high-risk time period?

        High-risk periods include:
        - First hour (9:30-10:30): Volatile, news reactions, open gaps
        - Last hour (15:00-16:00): Close positioning, end-of-day moves
        - FOMC announcement day: Fed policy = big moves
        - CPI/jobs report day: Economic data = big moves
        - Earnings season: Single stock volatility
        - Options expiration (Friday): Gamma pinning, hedging
        - Holidays or half-days: Low volume, wide spreads
        - First/last trading days of month: Month-end positioning

        Note: For production, would integrate with economic calendar API

        Returns:
            True if we're in a high-risk period
        """

        now = datetime.now()
        current_time = now.time()
        day_of_week = now.weekday()  # Monday=0, Friday=4

        # ======================================================================
        # FIRST HOUR: 9:30-10:30 ET
        # ======================================================================

        if time(9, 30) <= current_time <= time(10, 30):
            return True

        # ======================================================================
        # LAST HOUR: 15:00-16:00 ET
        # ======================================================================

        if time(15, 0) <= current_time <= time(16, 0):
            return True

        # ======================================================================
        # FRIDAY OPEX: Last Friday of month (rough check)
        # ======================================================================

        # Get day of month
        day_of_month = now.day

        # If it's Friday (day_of_week == 4) and close to month end (>20)
        if day_of_week == 4 and day_of_month > 20:
            return True

        # ======================================================================
        # NOTE: In production, would check:
        # - Is FOMC announcement today?
        # - Is CPI report today?
        # - Are we in earnings season?
        # - Is there a holiday tomorrow?
        # ======================================================================

        return False

    def get_risk_period_info(self) -> Dict[str, Any]:
        """
        Get detailed information about current risk period.

        Returns:
            Dict with risk period details
        """

        now = datetime.now()
        current_time = now.time()
        day_of_week = now.weekday()

        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        day_name = days[day_of_week]

        info = {
            'is_high_risk': self.is_high_risk_period(),
            'current_time': current_time.strftime('%H:%M'),
            'day_of_week': day_name,
            'day_of_month': now.day,
            'reasons': []
        }

        if time(9, 30) <= current_time <= time(10, 30):
            info['reasons'].append('First hour - high volatility')

        if time(15, 0) <= current_time <= time(16, 0):
            info['reasons'].append('Last hour - close positioning')

        if day_of_week == 4 and now.day > 20:
            info['reasons'].append('Options expiration week')

        return info

    def get_context_summary(
        self,
        market_regime: Optional[str] = None,
        vix: Optional[float] = None,
        adx: Optional[float] = None,
        oil_change: Optional[float] = None,
        dollar_change: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Get a complete summary of market context.

        Args:
            market_regime: Current regime ('trending_up', 'trending_down', etc.)
            vix: Current VIX level
            adx: Current ADX value
            oil_change: Oil change %
            dollar_change: Dollar change %

        Returns:
            Dict with comprehensive context
        """

        return {
            'timestamp': datetime.now(),
            'market_regime': market_regime or 'unknown',
            'vix_level': vix,
            'adx_value': adx,
            'is_high_risk_period': self.is_high_risk_period(),
            'risk_period_info': self.get_risk_period_info(),
            'correlation_signals': self.get_correlation_signals(
                oil_change_percent=oil_change,
                dollar_change_percent=dollar_change,
                vix_change=None  # Would calculate from previous VIX
            ),
            'trading_recommendation': self._generate_recommendation(
                market_regime, vix
            )
        }

    def _generate_recommendation(
        self,
        market_regime: Optional[str],
        vix: Optional[float]
    ) -> str:
        """
        Generate a trading recommendation based on context.

        Args:
            market_regime: Current regime
            vix: VIX level

        Returns:
            Recommendation string
        """

        if market_regime == 'trending_up':
            return "Bullish bias: Favor call strategies and call spreads"

        elif market_regime == 'trending_down':
            return "Bearish bias: Favor put strategies and put spreads"

        elif market_regime == 'range_bound':
            return "Range trade: Iron condors and strangle sells are ideal"

        elif market_regime == 'volatile':
            if vix and vix > 30:
                return "High volatility: Buy premium (long calls/puts)"
            else:
                return "Moderate volatility: Mixed strategies work"

        else:
            return "Unknown regime: Use small positions"
