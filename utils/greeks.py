"""
Greeks Calculator - Calculates Options Greeks (delta, gamma, theta, vega, rho).

Greeks are the "sensitivities" of an option price to changes in market conditions.
Think of them like weather forecasting - they tell you how sensitive a trade is
to different factors.

For beginners, here's what each Greek means in plain English:

DELTA (Δ):
- How much the option price changes when the stock moves $1
- Call delta: 0 to +1 (price rises as stock rises)
- Put delta: 0 to -1 (price rises as stock falls)
- Example: SPY $450 call with delta 0.6 means it's 60% as responsive as the stock
- Practical use: Delta × 100 = rough probability the option expires in-the-money

GAMMA (Γ):
- How much delta changes when the stock moves $1
- High gamma = delta changes a lot (risky but responsive)
- Low gamma = delta stable (predictable but less responsive)
- Practical use: High gamma = "accelerator", need to watch it closely

THETA (Θ):
- How much the option LOSES per day due to time decay
- Always negative (time decay hurts option buyers)
- Positive for option sellers (they benefit from time decay)
- Example: Theta = -0.05 means you lose 5 cents per day if nothing else changes
- Practical use: This is YOUR enemy if you're buying. Your friend if you're selling.

VEGA (ν):
- How much the option price changes for 1% change in volatility
- Example: Vega = 0.10 means if IV increases 1%, the option is worth 10 cents more
- Practical use: High IV = buy options cheap (eventually IV will drop). Low IV = sell options.

RHO (ρ):
- How much the option price changes for 1% change in interest rates
- Usually not important for day trading (interest rates change slowly)
- More important for longer-dated options

IMPORTANT: This module tries to use py_vollib (professional library).
If it's not installed, it falls back to simplified Black-Scholes formulas.
The fallback won't be 100% accurate, but is good enough for risk management.
"""

from typing import Dict, Optional
import math
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to import py_vollib (professional options library)
# This is much more accurate than our simplified formulas
try:
    from py_vollib.black_scholes.greeks import (
        delta, gamma, theta, vega, rho
    )
    from py_vollib.black_scholes import black_scholes
    VOLLIB_AVAILABLE = True
    logger.info("py_vollib library available - using professional Greeks calculations")
except ImportError:
    VOLLIB_AVAILABLE = False
    logger.warning(
        "py_vollib not installed. Using simplified Black-Scholes formulas. "
        "Install with: pip install py_vollib"
    )


# ============================================================================
# SIMPLIFIED BLACK-SCHOLES FORMULAS (fallback if py_vollib not available)
# ============================================================================

def _normal_pdf(x: float) -> float:
    """
    Standard normal probability distribution function (PDF).
    This is a bell curve - used in Black-Scholes calculations.
    """
    return (1 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x)


def _normal_cdf(x: float) -> float:
    """
    Standard normal cumulative distribution function (CDF).
    Returns the probability that a random value <= x.
    Used in Black-Scholes calculations.
    """
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _black_scholes_simplified(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'
) -> float:
    """
    Simplified Black-Scholes formula to calculate option price.

    This is the theoretical "fair value" of an option given market conditions.

    Args:
        S: Current stock price (e.g., 450.50)
        K: Strike price (e.g., 450)
        T: Time to expiration in years (e.g., 0.05 = 5 days)
        r: Risk-free rate as decimal (e.g., 0.05 = 5%)
        sigma: Volatility as decimal (e.g., 0.20 = 20%)
        option_type: 'C' for call, 'P' for put

    Returns:
        Theoretical option price
    """

    # Validate inputs
    if S <= 0 or K <= 0 or T < 0 or sigma <= 0:
        return 0

    # Calculate d1 and d2 (these are in the Black-Scholes formula)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    # Get probability values
    nd1 = _normal_cdf(d1)
    nd2 = _normal_cdf(d2)
    _pdf_d1 = _normal_pdf(d1)

    if option_type.upper() == 'C':
        # Call option price
        price = S * nd1 - K * math.exp(-r * T) * nd2
    else:
        # Put option price
        price = K * math.exp(-r * T) * (1 - nd2) - S * (1 - nd1)

    return max(price, 0)  # Option price can't be negative


def _delta_simplified(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'
) -> float:
    """Simplified delta calculation"""

    if T <= 0 or sigma <= 0:
        # Expiration: delta is 0 (out-of-money) or 1/-1 (in-the-money)
        if option_type.upper() == 'C':
            return 1.0 if S > K else 0.0
        else:
            return -1.0 if S < K else 0.0

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    if option_type.upper() == 'C':
        return _normal_cdf(d1)
    else:
        return _normal_cdf(d1) - 1


def _gamma_simplified(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'  # Note: gamma is same for calls and puts
) -> float:
    """Simplified gamma calculation"""

    if T <= 0 or sigma <= 0 or S <= 0:
        return 0

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    return _normal_pdf(d1) / (S * sigma * math.sqrt(T))


def _theta_simplified(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'
) -> float:
    """Simplified theta calculation (per day)"""

    if T <= 0 or sigma <= 0:
        return 0

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    nd1_pdf = _normal_pdf(d1)
    nd2_cdf = _normal_cdf(d2)

    if option_type.upper() == 'C':
        # Call theta
        theta_value = (
            -S * nd1_pdf * sigma / (2 * math.sqrt(T))
            - r * K * math.exp(-r * T) * nd2_cdf
        )
    else:
        # Put theta
        theta_value = (
            -S * nd1_pdf * sigma / (2 * math.sqrt(T))
            + r * K * math.exp(-r * T) * (1 - nd2_cdf)
        )

    # Convert to per-day theta
    return theta_value / 365


def _vega_simplified(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'  # Note: vega is same for calls and puts
) -> float:
    """Simplified vega calculation (per 1% change in IV)"""

    if T <= 0 or sigma <= 0 or S <= 0:
        return 0

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))

    vega_value = S * _normal_pdf(d1) * math.sqrt(T) / 100

    return vega_value


def _rho_simplified(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'
) -> float:
    """Simplified rho calculation (per 1% change in interest rates)"""

    if T <= 0 or sigma <= 0:
        return 0

    d2 = (
        (math.log(S / K) + (r - 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    )

    if option_type.upper() == 'C':
        rho_value = K * T * math.exp(-r * T) * _normal_cdf(d2) / 100
    else:
        rho_value = -K * T * math.exp(-r * T) * _normal_cdf(-d2) / 100

    return rho_value


# ============================================================================
# PUBLIC FUNCTIONS - USE THESE!
# ============================================================================

def calculate_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'
) -> Dict[str, float]:
    """
    Calculate all option Greeks.

    Args:
        S: Current stock price (e.g., 450.50)
        K: Strike price (e.g., 450)
        T: Time to expiration in years (e.g., 0.05 = 5 days = 5/365)
        r: Risk-free rate as decimal (e.g., 0.05 = 5% per year)
        sigma: Implied volatility as decimal (e.g., 0.20 = 20%)
        option_type: 'C' for call, 'P' for put

    Returns:
        Dict with keys: delta, gamma, theta, vega, rho, price
        All values are simplified (not exact Greeks)

    Example:
        greeks = calculate_greeks(
            S=450.50,      # Stock price
            K=450,         # Strike
            T=7/365,       # 7 days to expiration
            r=0.05,        # 5% interest rate
            sigma=0.18,    # 18% volatility
            option_type='C'
        )
        print(f"Delta: {greeks['delta']:.3f}")  # How much it moves with stock
        print(f"Theta: {greeks['theta']:.4f}")  # Daily decay
    """

    try:
        if VOLLIB_AVAILABLE:
            # Use professional library
            price = black_scholes(option_type.upper(), S, K, T, r, sigma)
            delta_val = delta(option_type.upper(), S, K, T, r, sigma)
            gamma_val = gamma(option_type.upper(), S, K, T, r, sigma)
            theta_val = theta(option_type.upper(), S, K, T, r, sigma) / 365
            vega_val = vega(option_type.upper(), S, K, T, r, sigma) / 100
            rho_val = rho(option_type.upper(), S, K, T, r, sigma) / 100

        else:
            # Use simplified formulas
            price = _black_scholes_simplified(S, K, T, r, sigma, option_type)
            delta_val = _delta_simplified(S, K, T, r, sigma, option_type)
            gamma_val = _gamma_simplified(S, K, T, r, sigma, option_type)
            theta_val = _theta_simplified(S, K, T, r, sigma, option_type)
            vega_val = _vega_simplified(S, K, T, r, sigma, option_type)
            rho_val = _rho_simplified(S, K, T, r, sigma, option_type)

        return {
            'price': float(price),
            'delta': float(delta_val),
            'gamma': float(gamma_val),
            'theta': float(theta_val),
            'vega': float(vega_val),
            'rho': float(rho_val),
        }

    except Exception as e:
        logger.error(f"Error calculating greeks: {e}")
        return {
            'price': 0,
            'delta': 0,
            'gamma': 0,
            'theta': 0,
            'vega': 0,
            'rho': 0,
        }


def _newton_iv(
    option_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = 'C',
    tol: float = 1e-6,
    max_iter: int = 50,
) -> Optional[float]:
    """
    Newton-Raphson implied volatility solver.
    Uses BS price + vega for fast convergence. No external libraries needed.
    Returns IV as decimal or None if solver fails to converge.
    """
    if option_price <= 0 or S <= 0 or K <= 0 or T <= 0:
        return None

    # Intrinsic value check
    intrinsic = max(S - K, 0) if option_type.upper() == 'C' else max(K - S, 0)
    if option_price < intrinsic - 0.01:
        return None  # Below intrinsic — arbitrage, IV undefined

    # Initial guess: Brenner-Subrahmanyam approximation
    sigma = math.sqrt(2 * math.pi / T) * (option_price / S)
    sigma = max(0.01, min(sigma, 5.0))  # Clamp to reasonable range

    for _ in range(max_iter):
        price = _black_scholes_simplified(S, K, T, r, sigma, option_type)
        diff = price - option_price

        if abs(diff) < tol:
            return sigma

        # Vega = S * sqrt(T) * N'(d1)
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        vega_val = S * math.sqrt(T) * _normal_pdf(d1)

        if vega_val < 1e-12:
            break  # Vega too small, solver would diverge

        sigma -= diff / vega_val
        sigma = max(0.001, min(sigma, 10.0))  # Keep in bounds

    return sigma if 0.001 < sigma < 10.0 else None


def calculate_iv(
    option_price: float,
    S: float,
    K: float,
    T: float,
    r: float,
    option_type: str = 'C'
) -> Optional[float]:
    """
    Calculate Implied Volatility (IV) from an option price.

    This is the "reverse" of Black-Scholes:
    Given an option price, what volatility does it imply?

    This requires iterative calculation (binary search).

    Args:
        option_price: Market price of the option
        S: Current stock price
        K: Strike price
        T: Time to expiration (years)
        r: Risk-free rate
        option_type: 'C' or 'P'

    Returns:
        Implied volatility as decimal, or None if can't calculate

    Example:
        # A call option trading at $5 on SPY, what's the implied vol?
        iv = calculate_iv(
            option_price=5.00,
            S=450.50,
            K=450,
            T=7/365,
            r=0.05,
            option_type='C'
        )
        print(f"IV: {iv*100:.1f}%")  # e.g., IV: 18.5%
    """

    if VOLLIB_AVAILABLE:
        try:
            from py_vollib.black_scholes_merton.implied_vol import implied_vol
            iv = implied_vol(option_price, S, K, T, r, option_type.upper())
            return float(iv)
        except Exception as e:
            logger.debug(f"py_vollib IV failed, trying Newton-Raphson: {e}")

    # Fallback: Newton-Raphson IV solver (no external library needed)
    try:
        return _newton_iv(option_price, S, K, T, r, option_type)
    except Exception as e:
        logger.debug(f"Newton-Raphson IV failed: {e}")
        return None


def calculate_theoretical_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = 'C'
) -> float:
    """
    Calculate theoretical option price using Black-Scholes.

    This tells you what an option "should" be worth based on:
    - Stock price
    - Strike price
    - Time to expiration
    - Interest rates
    - Volatility

    If market price > theoretical price, the option is overpriced (sell it).
    If market price < theoretical price, the option is underpriced (buy it).

    Args:
        S: Stock price
        K: Strike
        T: Time to expiration (years)
        r: Risk-free rate
        sigma: Volatility
        option_type: 'C' or 'P'

    Returns:
        Theoretical option price

    Example:
        theo_price = calculate_theoretical_price(
            S=450.50,
            K=450,
            T=7/365,
            r=0.05,
            sigma=0.18,
            option_type='C'
        )
        market_price = 2.50
        if market_price < theo_price:
            print("Option is underpriced - BUY IT!")
    """

    greeks = calculate_greeks(S, K, T, r, sigma, option_type)
    return greeks['price']


def interpret_greeks(greeks: Dict[str, float]) -> str:
    """
    Convert Greek values into plain English interpretation.

    Args:
        greeks: Dict returned from calculate_greeks()

    Returns:
        String interpretation

    Example:
        interpretation = interpret_greeks(greeks)
        print(interpretation)
    """

    delta = greeks.get('delta', 0)
    gamma = greeks.get('gamma', 0)
    theta = greeks.get('theta', 0)
    vega = greeks.get('vega', 0)

    lines = []

    # Delta interpretation
    if abs(delta) < 0.30:
        lines.append(f"• Delta {delta:.3f}: Out-of-the-money. Small moves with stock.")
    elif abs(delta) < 0.70:
        lines.append(f"• Delta {delta:.3f}: Near-the-money. Good responsiveness.")
    else:
        lines.append(f"• Delta {delta:.3f}: In-the-money. Very responsive to stock moves.")

    # Gamma interpretation
    if gamma < 0.02:
        lines.append(f"• Gamma {gamma:.4f}: Low. Delta won't change much.")
    else:
        lines.append(f"• Gamma {gamma:.4f}: High. Delta sensitive to stock moves. (Watch closely!)")

    # Theta interpretation
    if theta < -0.05:
        lines.append(f"• Theta {theta:.4f}: Fast decay. Losing {abs(theta*100):.2f}¢ per day. (Sell this)")
    elif theta < -0.01:
        lines.append(f"• Theta {theta:.4f}: Moderate decay. Losing {abs(theta*100):.2f}¢ per day.")
    else:
        lines.append(f"• Theta {theta:.4f}: Slow decay. Time is on your side. (Buy this)")

    # Vega interpretation
    if vega > 0.1:
        lines.append(f"• Vega {vega:.4f}: Very sensitive to IV. (IV drops = loses money)")
    else:
        lines.append(f"• Vega {vega:.4f}: Low IV sensitivity. Stable to volatility changes.")

    return "\n".join(lines)
