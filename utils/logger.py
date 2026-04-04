"""
Logger - Centralized logging configuration for the trading bot.

This module provides a consistent, professional logging setup that writes to
both console (for immediate feedback) and files (for long-term records).

For beginners: Logging is like a captain's log for a ship. Every important
event gets recorded. When something goes wrong, you can review the log to
understand what happened.

Log levels (from least to most severe):
- DEBUG: Detailed info for developers (too verbose for production)
- INFO: General info (strategies running, trades executed)
- WARNING: Something might be wrong (low confidence signal)
- ERROR: Something broke (API failure, invalid signal)
- CRITICAL: Everything is broken (shut down the bot)

Example:
    logger = get_logger(__name__)
    logger.info("Trade executed: BUY 1 SPY $450C")
    logger.warning("Daily loss limit approaching: $400 of $500")
    logger.error("Failed to fetch options data: Connection timeout")
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional
from config.settings import settings


# Color codes for console output (makes logs easier to read)
class ColoredFormatter(logging.Formatter):
    """
    Custom formatter that adds colors to console output.

    Colors make different log levels stand out:
    - DEBUG: Cyan (detailed info)
    - INFO: Green (normal operation)
    - WARNING: Yellow (heads up)
    - ERROR: Red (something's wrong)
    - CRITICAL: Bold red (critical issue)
    """

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[1;31m', # Bold red
        'RESET': '\033[0m',       # Reset to default
    }

    def format(self, record: logging.LogRecord) -> str:
        """
        Format the log record with colors.

        Args:
            record: The log record to format

        Returns:
            Formatted log string with color codes
        """
        # Get the color for this log level
        color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']

        # Create the colored level name
        record.levelname = f"{color}{record.levelname}{reset}"

        # Format the message
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    This is the main function to use in your code:

        logger = get_logger(__name__)
        logger.info("Hello world!")

    Each module gets its own logger named after the module,
    but they all write to the same files and console.

    Args:
        name: Name of the logger (usually __name__)

    Returns:
        logging.Logger instance

    Example:
        # In strategies/technical.py:
        logger = get_logger(__name__)  # Logger name will be "strategies.technical"
        logger.info("RSI analyzed")
    """

    logger = logging.getLogger(name)

    # Only configure if not already configured
    # (avoid duplicate handlers)
    if not logger.handlers:
        # Set the logger level (the minimum level we care about)
        log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
        logger.setLevel(log_level)

        # ======================================================================
        # CONSOLE HANDLER - Display logs on screen
        # ======================================================================

        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)

        # Format: [13:45:22] [INFO] [strategies.technical] Message here
        console_format = ColoredFormatter(
            fmt='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_format)

        logger.addHandler(console_handler)

        # ======================================================================
        # FILE HANDLER - Write logs to rotating files
        # ======================================================================

        try:
            # Create log directory if it doesn't exist
            log_path = Path(settings.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Create rotating file handler
            # maxBytes: 10 MB per file
            # backupCount: keep 5 old files
            # When the log exceeds 10MB, it renames the current file and starts a new one
            # Example: trading_bot.log -> trading_bot.log.1 -> trading_bot.log.2, etc.
            file_handler = logging.handlers.RotatingFileHandler(
                filename=settings.log_file,
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5
            )

            file_handler.setLevel(log_level)

            # File format (more detailed, includes milliseconds)
            # [2025-01-17 13:45:22,123] [INFO] [strategies.technical] Message here
            file_format = logging.Formatter(
                fmt='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_format)

            logger.addHandler(file_handler)

        except Exception as e:
            # If file logging fails, at least we have console logging
            logger.warning(f"Could not set up file logging: {e}")

    return logger


# Create a root logger that other modules will inherit from
# This ensures consistent formatting across all loggers
root_logger = get_logger('trading_bot')


def set_log_level(level: str) -> None:
    """
    Change the logging level at runtime.

    Args:
        level: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'

    Example:
        set_log_level('DEBUG')  # Now we see all detailed logs
    """

    log_level = getattr(logging, level.upper(), logging.INFO)

    # Update the root logger
    root_logger.setLevel(log_level)

    # Update all existing handlers
    for handler in root_logger.handlers:
        handler.setLevel(log_level)


def log_trade_execution(
    symbol: str,
    action: str,
    entry_price: float,
    contracts: int = 1,
    reasoning: str = ""
) -> None:
    """
    Convenience function to log a trade execution.

    Args:
        symbol: SPY or SPX
        action: BUY CALL, SELL PUT SPREAD, etc.
        entry_price: Entry price
        contracts: Number of contracts
        reasoning: Why we're taking this trade
    """

    logger = get_logger('trading')
    message = f"TRADE: {action} {contracts}x {symbol} @ ${entry_price:.2f}"

    if reasoning:
        message += f" | Reason: {reasoning}"

    logger.info(message)


def log_signal(
    strategy: str,
    symbol: str,
    direction: str,
    score: float,
    confidence: float
) -> None:
    """
    Convenience function to log a signal.

    Args:
        strategy: Strategy name
        symbol: SPY or SPX
        direction: CALL or PUT
        score: Signal score (-100 to +100)
        confidence: Confidence (0-1)
    """

    logger = get_logger('signals')
    logger.info(
        f"SIGNAL: {strategy} | {symbol} {direction} "
        f"| Score: {score:+.0f} | Confidence: {confidence*100:.0f}%"
    )


def log_error_with_context(
    error_message: str,
    context: Optional[dict] = None
) -> None:
    """
    Log an error with additional context information.

    Args:
        error_message: The error message
        context: Optional dict with additional context

    Example:
        log_error_with_context(
            "Failed to calculate greeks",
            {'strike': 450, 'symbol': 'SPY', 'iv': 18.5}
        )
    """

    logger = get_logger('error_handler')

    if context:
        context_str = " | ".join(f"{k}={v}" for k, v in context.items())
        logger.error(f"{error_message} | {context_str}")
    else:
        logger.error(error_message)
