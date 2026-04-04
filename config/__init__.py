"""
Configuration package for the SPX/SPY Options Trading Bot.

This package exports the main Settings object that should be imported
throughout the application for accessing configuration values.

Example:
    from config import settings
    print(settings.starting_capital)  # Access config values
"""

from config.settings import settings

__all__ = ["settings"]
