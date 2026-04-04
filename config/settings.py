"""
Configuration management for the SPX/SPY Options Trading Bot.

Uses pydantic-settings to load and validate all configuration from
environment variables and .env files.

Data sources:
  - ThetaData Standard ($80/mo): SOLE options data source (quotes, OI, OHLC via OPRA)
    Greeks computed locally via Black-Scholes. Also provides stock EOD/index data.
  - Alpaca Algo Trader Plus: SIP real-time equity trades/quotes/bars + broker.
    Emergency fallback only for options if ThetaData Terminal is down.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import List
from datetime import time


class Settings(BaseSettings):
    """
    Main settings class — loads from environment variables / .env.

    Priority: env vars > .env file > defaults below.
    """

    # ========================================================================
    # API KEYS — Alpaca + ThetaData only
    # ========================================================================

    alpaca_api_key: str = Field(
        default="",
        description="Alpaca API Key ID (APCA-API-KEY-ID)"
    )
    alpaca_secret_key: str = Field(
        default="",
        description="Alpaca Secret Key (APCA-API-SECRET-KEY)"
    )
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets/v2",
        description="Alpaca trading API base URL (paper or live)"
    )
    alpaca_ws_url: str = Field(
        default="wss://stream.data.alpaca.markets/v2/sip",
        description="Alpaca WebSocket URL for real-time streaming"
    )
    alpaca_data_feed: str = Field(
        default="sip",
        description="Alpaca data feed: 'sip' (Algo Trader Plus) or 'iex' (free)"
    )

    # ThetaData (runs locally via Theta Terminal on port 25503)
    theta_enabled: bool = Field(
        default=True,
        description="Enable ThetaData as options/EOD data source"
    )
    theta_base_url: str = Field(
        default="http://localhost:25503",
        description="ThetaData Terminal REST API base URL"
    )
    theta_poll_ms: int = Field(
        default=200,
        description="ThetaData polling interval in milliseconds"
    )

    # ========================================================================
    # FLOW ENGINE (Rust process)
    # ========================================================================

    flow_engine_port: int = Field(
        default=8081,
        description="Rust flow engine HTTP/WS port"
    )
    flow_engine_url: str = Field(
        default="ws://localhost:8081/ws",
        description="Flow engine WebSocket URL"
    )
    trading_symbol: str = Field(
        default="SPY",
        description="Primary symbol for the flow engine"
    )

    # ========================================================================
    # TRADING SYMBOLS & HOURS
    # ========================================================================

    trading_symbols: List[str] = Field(
        default=["SPY", "SPX"],
        description="List of symbols to trade"
    )

    @field_validator("trading_symbols", mode="before")
    @classmethod
    def parse_trading_symbols(cls, v):
        """Handle comma-separated string or JSON array from .env."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                return json.loads(v)
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    market_open_time: time = Field(default=time(9, 30))
    market_close_time: time = Field(default=time(16, 0))
    trading_start_time: time = Field(default=time(9, 45))
    trading_end_time: time = Field(default=time(15, 30))

    # ========================================================================
    # RISK MANAGEMENT
    # ========================================================================

    starting_capital: float = Field(default=5000.0)
    max_risk_per_trade: float = Field(default=0.02)
    max_daily_loss: float = Field(default=0.0)  # 0 = no daily loss limit
    max_position_size: float = Field(default=0.05)
    max_total_open_positions: int = Field(default=5)

    # ========================================================================
    # POSITION DURATION & TARGETS
    # ========================================================================

    default_hold_minutes: int = Field(default=60)
    default_stop_loss_percent: float = Field(default=0.10)
    default_profit_target_percent: float = Field(default=0.25)

    # ========================================================================
    # PDT RULES
    # ========================================================================

    max_day_trades: int = Field(default=3)
    day_trade_window_days: int = Field(default=5)

    # ========================================================================
    # STRATEGY WEIGHTS
    # ========================================================================

    weight_flow_analysis: float = Field(default=0.30)
    weight_technical: float = Field(default=0.25)
    weight_sentiment: float = Field(default=0.20)
    weight_volatility: float = Field(default=0.15)
    weight_economic: float = Field(default=0.10)

    # ========================================================================
    # SIGNAL THRESHOLDS
    # ========================================================================

    min_signal_confidence: float = Field(default=65.0)
    high_confidence_threshold: float = Field(default=80.0)

    # ========================================================================
    # OPTIONS SELECTION
    # ========================================================================

    preferred_dte: int = Field(default=7)
    min_dte: int = Field(default=3)
    max_dte: int = Field(default=30)
    min_option_volume: int = Field(default=50)
    min_option_open_interest: int = Field(default=100)

    # ========================================================================
    # TRADING MODE
    # ========================================================================

    trading_mode: str = Field(default="SIGNAL")
    paper_trading: bool = Field(default=True)

    # ========================================================================
    # DASHBOARD
    # ========================================================================

    dashboard_host: str = Field(default="127.0.0.1")
    dashboard_port: int = Field(default=8000)

    # ========================================================================
    # DATA & LOGGING
    # ========================================================================

    database_path: str = Field(default="./data/trading_bot.db")
    log_level: str = Field(default="INFO")
    log_file: str = Field(default="./logs/trading_bot.log")
    cache_ttl_seconds: int = Field(default=60)

    # ========================================================================
    # PYDANTIC CONFIG
    # ========================================================================

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Silently ignore unknown .env keys


# Singleton instance
settings = Settings()
