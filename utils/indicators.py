"""
Technical Indicators - Calculations for RSI, MACD, Bollinger Bands, ATR, ADX, etc.

Technical indicators are mathematical formulas applied to price and volume data.
They help identify trends, momentum, volatility, and potential reversals.

For beginners, think of indicators like a speedometer and fuel gauge in a car:
- Speedometer (RSI): How fast is the stock moving? (0-100 scale)
- Fuel gauge (MACD): Is momentum increasing or decreasing?
- Temperature gauge (Bollinger Bands): Is price at extremes?

KEY CONCEPTS:

TREND INDICATORS:
- Moving averages (SMA, EMA): Smooth out noise, show direction
- ADX: How strong is the trend? (0-100, >30 = strong)

MOMENTUM INDICATORS:
- RSI: Is stock overbought (>70) or oversold (<30)?
- MACD: Is momentum accelerating or slowing?

VOLATILITY INDICATORS:
- Bollinger Bands: Are we at extremes?
- ATR: How much are prices swinging?

This module wraps the pandas_ta library (professional indicator calculations).
If not installed: pip install pandas-ta

All functions work with pandas Series/DataFrames. For beginners:
- pandas Series = a column of data (like prices)
- pandas DataFrame = a table with multiple columns
"""

from typing import Dict, Optional
import pandas as pd
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import pandas_ta (professional indicators library)
try:
    import pandas_ta as ta
    TA_AVAILABLE = True
    logger.info("pandas-ta library available - using professional indicator calculations")
except ImportError:
    TA_AVAILABLE = False
    logger.warning(
        "pandas-ta not installed. Using simplified calculations. "
        "Install with: pip install pandas-ta"
    )


# ============================================================================
# SIMPLIFIED FALLBACK IMPLEMENTATIONS (if pandas_ta not available)
# ============================================================================

def _sma_simplified(prices: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average - average of last N prices"""
    return prices.rolling(window=period).mean()


def _ema_simplified(prices: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average - gives more weight to recent prices"""
    return prices.ewm(span=period, adjust=False).mean()


def _rsi_simplified(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index - measures momentum (0-100).
    >70 = overbought, <30 = oversold
    """
    # Calculate price changes
    delta = prices.diff()

    # Separate gains and losses
    gains = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    losses = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Calculate RS and RSI
    rs = gains / losses
    rsi = 100 - (100 / (1 + rs))

    return rsi


def _macd_simplified(prices: pd.Series) -> Dict[str, pd.Series]:
    """
    Moving Average Convergence Divergence.
    Momentum indicator showing trend direction and strength.
    """
    ema_12 = prices.ewm(span=12, adjust=False).mean()
    ema_26 = prices.ewm(span=26, adjust=False).mean()

    macd_line = ema_12 - ema_26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    return {
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    }


def _bollinger_bands_simplified(
    prices: pd.Series,
    period: int = 20,
    num_std: float = 2.0
) -> Dict[str, pd.Series]:
    """
    Bollinger Bands - shows volatility and extremes.
    Price touching upper band = potentially overbought
    Price touching lower band = potentially oversold
    """
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()

    upper = sma + (std * num_std)
    lower = sma - (std * num_std)

    return {
        'upper': upper,
        'middle': sma,
        'lower': lower,
        'band_width': upper - lower
    }


def _atr_simplified(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Average True Range - measures volatility.
    High ATR = high volatility, big swings expected
    Low ATR = low volatility, small swings expected
    """
    # True Range = max(high - low, abs(high - previous_close), abs(low - previous_close))
    tr = pd.concat([
        high - low,
        abs(high - close.shift()),
        abs(low - close.shift())
    ], axis=1).max(axis=1)

    # ATR = average of True Range
    atr = tr.rolling(window=period).mean()

    return atr


def _adx_simplified(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Average Directional Index - measures trend strength (0-100).
    >30 = strong trend
    <20 = weak trend, choppy
    """
    # Calculate Plus/Minus DM
    plus_dm = high.diff()
    minus_dm = -low.diff()

    # Remove non-positive values
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0

    # Calculate TR and ATR
    tr = pd.concat([
        high - low,
        abs(high - close.shift()),
        abs(low - close.shift())
    ], axis=1).max(axis=1)

    atr_val = tr.rolling(window=period).mean()

    # Calculate DI
    plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr_val)
    minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr_val)

    # Calculate ADX
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()

    return adx


def _vwap_simplified(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series
) -> pd.Series:
    """
    Volume-Weighted Average Price - shows what the market paid on average.
    Price above VWAP = buyers in control
    Price below VWAP = sellers in control
    """
    typical_price = (high + low + close) / 3
    vwap = (typical_price * volume).cumsum() / volume.cumsum()

    return vwap


# ============================================================================
# PUBLIC FUNCTIONS - USE THESE!
# ============================================================================

def calculate_sma(
    prices: pd.Series,
    period: int = 20
) -> pd.Series:
    """
    Calculate Simple Moving Average (SMA).

    SMA = average of last N closing prices.
    Useful for identifying trend direction.

    Args:
        prices: Series of prices
        period: Number of periods (days) for the average

    Returns:
        Series with SMA values

    Example:
        import pandas as pd
        prices = pd.Series([450, 451, 449, 452, 450])
        sma_20 = calculate_sma(prices, period=20)
    """

    try:
        if TA_AVAILABLE:
            return ta.sma(prices, length=period)
        else:
            return _sma_simplified(prices, period)
    except Exception as e:
        logger.error(f"Error calculating SMA: {e}")
        return pd.Series(index=prices.index, dtype=float)


def calculate_ema(
    prices: pd.Series,
    period: int = 20
) -> pd.Series:
    """
    Calculate Exponential Moving Average (EMA).

    EMA = moving average that gives more weight to recent prices.
    More responsive than SMA to recent price changes.

    Args:
        prices: Series of prices
        period: Number of periods for the average

    Returns:
        Series with EMA values

    Example:
        ema_50 = calculate_ema(prices, period=50)
        # Faster moving average for quick signals
    """

    try:
        if TA_AVAILABLE:
            return ta.ema(prices, length=period)
        else:
            return _ema_simplified(prices, period)
    except Exception as e:
        logger.error(f"Error calculating EMA: {e}")
        return pd.Series(index=prices.index, dtype=float)


def calculate_rsi(
    prices: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).

    RSI measures momentum on a scale of 0-100:
    - RSI > 70: Overbought (potential sell signal)
    - RSI < 30: Oversold (potential buy signal)
    - RSI 30-70: Neutral zone

    Args:
        prices: Series of prices
        period: Number of periods (default 14 is standard)

    Returns:
        Series with RSI values (0-100)

    Example:
        rsi = calculate_rsi(prices)
        oversold = rsi[rsi < 30]  # Where price was oversold
        overbought = rsi[rsi > 70]  # Where price was overbought
    """

    try:
        if TA_AVAILABLE:
            return ta.rsi(prices, length=period)
        else:
            return _rsi_simplified(prices, period)
    except Exception as e:
        logger.error(f"Error calculating RSI: {e}")
        return pd.Series(index=prices.index, dtype=float)


def calculate_macd(prices: pd.Series) -> Dict[str, pd.Series]:
    """
    Calculate MACD (Moving Average Convergence Divergence).

    MACD shows momentum and trend changes:
    - MACD line: 12-day EMA minus 26-day EMA
    - Signal line: 9-day EMA of MACD
    - Histogram: MACD minus signal (shows convergence/divergence)

    When MACD crosses above signal line = bullish
    When MACD crosses below signal line = bearish

    Args:
        prices: Series of prices

    Returns:
        Dict with 'macd', 'signal', 'histogram'

    Example:
        macd_data = calculate_macd(prices)
        print(f"MACD: {macd_data['macd'].iloc[-1]:.3f}")
        print(f"Signal: {macd_data['signal'].iloc[-1]:.3f}")
        print(f"Histogram: {macd_data['histogram'].iloc[-1]:.3f}")
    """

    try:
        if TA_AVAILABLE:
            result = ta.macd(prices)
            # pandas_ta returns a DataFrame, convert to dict
            return {
                'macd': result.iloc[:, 0],
                'signal': result.iloc[:, 1],
                'histogram': result.iloc[:, 2]
            }
        else:
            return _macd_simplified(prices)
    except Exception as e:
        logger.error(f"Error calculating MACD: {e}")
        return {
            'macd': pd.Series(index=prices.index, dtype=float),
            'signal': pd.Series(index=prices.index, dtype=float),
            'histogram': pd.Series(index=prices.index, dtype=float)
        }


def calculate_bollinger_bands(
    prices: pd.Series,
    period: int = 20,
    std: float = 2.0
) -> Dict[str, pd.Series]:
    """
    Calculate Bollinger Bands.

    Bollinger Bands show volatility and price extremes:
    - Upper band: SMA + (2 × standard deviation)
    - Middle band: SMA
    - Lower band: SMA - (2 × standard deviation)

    Price touching upper band = potentially overbought
    Price touching lower band = potentially oversold

    Args:
        prices: Series of prices
        period: Period for SMA (default 20)
        std: Number of standard deviations (default 2.0)

    Returns:
        Dict with 'upper', 'middle', 'lower', 'band_width'

    Example:
        bb = calculate_bollinger_bands(prices)
        print(f"Upper: {bb['upper'].iloc[-1]:.2f}")
        print(f"Width: {bb['band_width'].iloc[-1]:.2f}")  # Volatility measure
    """

    try:
        if TA_AVAILABLE:
            result = ta.bbands(prices, length=period, std=std)
            return {
                'lower': result.iloc[:, 0],
                'middle': result.iloc[:, 1],
                'upper': result.iloc[:, 2],
                'band_width': result.iloc[:, 2] - result.iloc[:, 0]
            }
        else:
            return _bollinger_bands_simplified(prices, period, std)
    except Exception as e:
        logger.error(f"Error calculating Bollinger Bands: {e}")
        return {
            'upper': pd.Series(index=prices.index, dtype=float),
            'middle': pd.Series(index=prices.index, dtype=float),
            'lower': pd.Series(index=prices.index, dtype=float),
            'band_width': pd.Series(index=prices.index, dtype=float)
        }


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate Average True Range (ATR).

    ATR measures volatility (how much price swings):
    - High ATR = high volatility, big moves expected
    - Low ATR = low volatility, small moves expected

    Useful for setting stop losses:
    - Conservative: stop = entry - (2 × ATR)
    - Aggressive: stop = entry - (1 × ATR)

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        period: Period for ATR (default 14)

    Returns:
        Series with ATR values

    Example:
        atr = calculate_atr(high, low, close)
        stop_loss = entry_price - (2 * atr.iloc[-1])
        print(f"Suggested stop loss: ${stop_loss:.2f}")
    """

    try:
        if TA_AVAILABLE:
            return ta.atr(high, low, close, length=period)
        else:
            return _atr_simplified(high, low, close, period)
    except Exception as e:
        logger.error(f"Error calculating ATR: {e}")
        return pd.Series(index=close.index, dtype=float)


def calculate_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14
) -> pd.Series:
    """
    Calculate Average Directional Index (ADX).

    ADX measures trend STRENGTH (not direction) on 0-100 scale:
    - ADX > 40: Very strong trend
    - ADX 25-40: Strong trend
    - ADX < 20: Weak trend, choppy, range-bound

    Useful for knowing when to use trend-following vs range-trading strategies.

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        period: Period for ADX (default 14)

    Returns:
        Series with ADX values

    Example:
        adx = calculate_adx(high, low, close)
        if adx.iloc[-1] > 30:
            print("Strong trend - use trend-following strategy")
        else:
            print("Weak trend - use range-trading strategy")
    """

    try:
        if TA_AVAILABLE:
            result = ta.adx(high, low, close, length=period)
            # pandas_ta returns ADX in the first column
            return result.iloc[:, 0]
        else:
            return _adx_simplified(high, low, close, period)
    except Exception as e:
        logger.error(f"Error calculating ADX: {e}")
        return pd.Series(index=close.index, dtype=float)


def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series
) -> pd.Series:
    """
    Calculate Volume-Weighted Average Price (VWAP).

    VWAP shows what the market has paid on average, weighted by volume.
    It's a reference point for fair value:
    - Price above VWAP = buyers in control (bullish)
    - Price below VWAP = sellers in control (bearish)

    VWAP resets daily, so it's useful for intraday trading.

    Args:
        high: Series of high prices
        low: Series of low prices
        close: Series of close prices
        volume: Series of volumes

    Returns:
        Series with VWAP values

    Example:
        vwap = calculate_vwap(high, low, close, volume)
        current_price = close.iloc[-1]
        current_vwap = vwap.iloc[-1]

        if current_price > current_vwap:
            print("Price above VWAP - bullish bias")
        else:
            print("Price below VWAP - bearish bias")
    """

    try:
        if TA_AVAILABLE:
            return ta.vwap(high, low, close, volume)
        else:
            return _vwap_simplified(high, low, close, volume)
    except Exception as e:
        logger.error(f"Error calculating VWAP: {e}")
        return pd.Series(index=close.index, dtype=float)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_indicator_summary(
    prices: pd.Series,
    high: Optional[pd.Series] = None,
    low: Optional[pd.Series] = None,
    volume: Optional[pd.Series] = None,
) -> Dict[str, float]:
    """
    Calculate a quick summary of all key indicators (latest values).

    Useful for getting a snapshot of technical condition.

    Args:
        prices: Series of close prices
        high: Series of high prices (for ATR/ADX)
        low: Series of low prices (for ATR/ADX)
        volume: Series of volumes (for VWAP)

    Returns:
        Dict with latest indicator values

    Example:
        summary = get_indicator_summary(prices, high, low, volume)
        print(f"RSI: {summary['rsi']:.1f}")
        print(f"ATR: {summary['atr']:.2f}")
    """

    summary = {}

    try:
        # RSI
        rsi = calculate_rsi(prices)
        summary['rsi'] = float(rsi.iloc[-1]) if not rsi.empty else None

        # MACD
        macd_data = calculate_macd(prices)
        summary['macd'] = float(macd_data['macd'].iloc[-1]) if not macd_data['macd'].empty else None
        summary['macd_signal'] = float(macd_data['signal'].iloc[-1]) if not macd_data['signal'].empty else None
        summary['macd_histogram'] = float(macd_data['histogram'].iloc[-1]) if not macd_data['histogram'].empty else None

        # Moving averages
        summary['sma_20'] = float(calculate_sma(prices, 20).iloc[-1]) if not prices.empty else None
        summary['ema_50'] = float(calculate_ema(prices, 50).iloc[-1]) if not prices.empty else None

        # Bollinger Bands
        bb = calculate_bollinger_bands(prices)
        summary['bb_width'] = float(bb['band_width'].iloc[-1]) if not bb['band_width'].empty else None

        # ATR and ADX (if high/low provided)
        if high is not None and low is not None:
            atr = calculate_atr(high, low, prices)
            summary['atr'] = float(atr.iloc[-1]) if not atr.empty else None

            adx = calculate_adx(high, low, prices)
            summary['adx'] = float(adx.iloc[-1]) if not adx.empty else None

        # VWAP (if volume provided)
        if volume is not None:
            vwap = calculate_vwap(high or prices, low or prices, prices, volume)
            summary['vwap'] = float(vwap.iloc[-1]) if not vwap.empty else None

    except Exception as e:
        logger.error(f"Error calculating indicator summary: {e}")

    return summary
