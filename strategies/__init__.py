"""
Strategy module initialization file.

This file imports all available trading strategies so they can be easily
accessed from the strategies package. Think of this as the "catalog" of
all available strategies the bot can use.

For beginners:
- Each strategy is a different approach to identifying trading opportunities
- The bot can run multiple strategies and combine their signals
- This __init__.py file makes all strategies available as: strategies.DirectionalStrategy, etc.
"""

from strategies.directional import DirectionalStrategy
from strategies.opening_range import OpeningRangeBreakout
from strategies.momentum import MomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.credit_spreads import CreditSpreadStrategy
from strategies.flow_based import FlowBasedStrategy
from strategies.base import BaseStrategy, Signal

__all__ = [
    "BaseStrategy",
    "Signal",
    "DirectionalStrategy",
    "OpeningRangeBreakout",
    "MomentumStrategy",
    "MeanReversionStrategy",
    "CreditSpreadStrategy",
    "FlowBasedStrategy",
]

__version__ = "1.0.0"
