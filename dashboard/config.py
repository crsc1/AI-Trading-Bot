"""
Centralized Configuration — Single source of truth for all tunable parameters.

Every hardcoded value that was scattered across the codebase lives here.
All values are loaded from environment variables with sensible defaults.

Usage:
    from .config import cfg
    # Then: cfg.ACCOUNT_BALANCE, cfg.MIN_TRADE_CONFIDENCE, etc.

Categories:
    ACCOUNT & RISK      — balance, loss limits, position sizing
    MARKET HOURS        — session phases, entry/exit cutoff times
    THETADATA           — API connection, timeouts, retries, cache
    ALPACA              — API connection, timeouts, cache
    SIGNAL ENGINE       — analysis params, confidence tiers, factor weights
    POSITION MANAGEMENT — exit rules, trade modes, entry filters
    FLOW ENGINE         — Rust engine connection
    SERVER              — dashboard host/port, CORS, WebSocket
"""

import os
import json
import logging
from datetime import time as dt_time
from typing import Dict

logger = logging.getLogger(__name__)

# ── Load .env file ────────────────────────────────────────────────────────────
# Try python-dotenv first; fall back to a lightweight manual parser so the
# server works even when python-dotenv isn't installed in the venv.
def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except ImportError:
        pass

    # Manual fallback: find .env relative to this file (dashboard/../.env)
    _here = os.path.dirname(os.path.abspath(__file__))
    _dotenv = os.path.join(_here, "..", ".env")
    if not os.path.exists(_dotenv):
        return
    with open(_dotenv) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _, _val = _line.partition("=")
            _key = _key.strip()
            # Strip inline comments and surrounding quotes
            _val = _val.split("#")[0].strip().strip('"').strip("'")
            os.environ.setdefault(_key, _val)

_load_dotenv()


def _env(key: str, default: str = "") -> str:
    """Get env var with default."""
    return os.environ.get(key, default)


def _env_float(key: str, default: float) -> float:
    """Get env var as float."""
    try:
        return float(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_int(key: str, default: int) -> int:
    """Get env var as int."""
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    """Get env var as bool."""
    val = os.environ.get(key, str(default)).lower().strip()
    return val in ("true", "1", "yes", "on")


def _env_time(key: str, default_h: int, default_m: int) -> dt_time:
    """Get env var as time (HH:MM format)."""
    val = os.environ.get(key, "")
    if val:
        try:
            parts = val.split(":")
            return dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            pass
    return dt_time(default_h, default_m)


class Config:
    """
    Immutable-ish configuration loaded once at startup from env vars.
    All values have sensible defaults for a $5K 0DTE SPY scalping account.
    """

    def __init__(self):
        self._load()

    def _load(self):
        """Load all configuration from environment."""

        # ═══════════════════════════════════════════════════════════════════
        # ACCOUNT & RISK
        # ═══════════════════════════════════════════════════════════════════

        self.ACCOUNT_BALANCE: float = _env_float("ACCOUNT_BALANCE", 5000.0)
        self.STARTING_CAPITAL: float = _env_float("STARTING_CAPITAL", 5000.0)

        # Risk limits (dollar amounts — scale with account)
        self.MAX_DAILY_LOSS: float = _env_float("MAX_DAILY_LOSS_HARD", 150.0)
        self.DAILY_LOSS_THROTTLE: float = _env_float("DAILY_LOSS_THROTTLE", 75.0)
        self.MAX_RISK_PER_TRADE_PCT: float = _env_float("MAX_RISK_PER_TRADE", 0.02)

        # Position limits
        self.MAX_OPEN_POSITIONS: int = _env_int("MAX_TOTAL_OPEN_POSITIONS", 2)
        self.MAX_TRADES_PER_DAY: int = _env_int("MAX_TRADES_PER_DAY", 0)  # 0 = unlimited
        self.MIN_SECONDS_BETWEEN_TRADES: int = _env_int("MIN_SECONDS_BETWEEN_TRADES", 60)

        # Risk per tier (% of account)
        self.RISK_TABLE: Dict[str, float] = {
            "TEXTBOOK": _env_float("RISK_TIER_TEXTBOOK_PCT", 2.0),
            "HIGH":     _env_float("RISK_TIER_HIGH_PCT", 1.5),
            "VALID":    _env_float("RISK_TIER_VALID_PCT", 0.75),
            "DEVELOPING": 0.0,  # never trade
        }

        # ═══════════════════════════════════════════════════════════════════
        # MARKET HOURS (Eastern Time)
        # ═══════════════════════════════════════════════════════════════════

        self.MARKET_OPEN: dt_time = _env_time("MARKET_OPEN", 9, 30)
        self.MARKET_CLOSE: dt_time = _env_time("MARKET_CLOSE", 16, 0)

        # Trading windows
        self.TRADING_START: dt_time = _env_time("TRADING_START_TIME", 9, 50)
        self.TRADING_END: dt_time = _env_time("TRADING_END_TIME", 15, 0)
        self.NO_NEW_ENTRIES_AFTER: dt_time = _env_time("NO_NEW_ENTRIES_TIME", 14, 30)
        self.CLOSE_LOSERS_AT: dt_time = _env_time("CLOSE_LOSERS_TIME", 14, 45)
        self.HARD_EXIT_TIME: dt_time = _env_time("HARD_EXIT_TIME", 15, 0)

        # Session phases (for time-of-day factor scoring)
        self.SESSION_PHASES = {
            "pre_market":      (dt_time(4, 0),  dt_time(9, 29)),
            "opening_drive":   (dt_time(9, 30), dt_time(9, 59)),
            "morning_trend":   (dt_time(10, 0), dt_time(11, 29)),
            "midday_chop":     (dt_time(11, 30), dt_time(13, 29)),
            "afternoon_trend": (dt_time(13, 30), dt_time(14, 59)),
            "power_hour":      (dt_time(15, 0), dt_time(15, 44)),
            "close_risk":      (dt_time(15, 45), dt_time(16, 0)),
        }

        # ═══════════════════════════════════════════════════════════════════
        # THETADATA
        # ═══════════════════════════════════════════════════════════════════

        self.THETA_BASE_URL: str = _env("THETA_BASE_URL", "http://localhost:25503")
        self.THETA_V2_BASE_URL: str = _env("THETA_V2_BASE_URL", "http://localhost:25510")
        self.THETA_ENABLED: bool = _env_bool("THETA_ENABLED", True)

        # WebSocket streaming (ThetaData Terminal — Standard plan)
        self.THETA_WS_URL: str = _env("THETA_WS_URL", "ws://localhost:25520/v1/events")
        self.THETA_STREAM_ENABLED: bool = _env_bool("THETA_STREAM_ENABLED", True)

        # Timeouts and retries
        self.THETA_REQUEST_TIMEOUT: float = _env_float("THETA_REQUEST_TIMEOUT", 8.0)
        self.THETA_RETRY_MAX: int = _env_int("THETA_RETRY_MAX", 3)
        self.THETA_RETRY_BASE_TIMEOUT: float = _env_float("THETA_RETRY_BASE_TIMEOUT", 5.0)
        self.THETA_RETRY_BACKOFF: float = _env_float("THETA_RETRY_BACKOFF", 1.5)

        # Health thresholds
        self.THETA_HEALTH_DEGRADED_AFTER: int = _env_int("THETA_HEALTH_DEGRADED_AFTER", 2)
        self.THETA_HEALTH_DOWN_AFTER: int = _env_int("THETA_HEALTH_DOWN_AFTER", 5)

        # Chain params
        self.THETA_STRIKE_RANGE: int = _env_int("THETA_STRIKE_RANGE", 15)

        # Cache TTLs (seconds)
        self.CHAIN_CACHE_TTL: int = _env_int("CHAIN_CACHE_TTL", 30)
        self.QUOTE_CACHE_TTL: int = _env_int("QUOTE_CACHE_TTL", 5)
        self.BAR_CACHE_TTL: int = _env_int("BAR_CACHE_TTL", 60)
        self.EXPIRATION_CACHE_TTL: int = _env_int("EXPIRATION_CACHE_TTL", 300)

        # ═══════════════════════════════════════════════════════════════════
        # ALPACA
        # ═══════════════════════════════════════════════════════════════════

        self.ALPACA_API_KEY: str = _env("ALPACA_API_KEY", "")
        self.ALPACA_SECRET_KEY: str = _env("ALPACA_SECRET_KEY", "")
        self.ALPACA_BASE_URL: str = _env("ALPACA_BASE_URL", "https://paper-api.alpaca.markets/v2")
        self.ALPACA_DATA_URL: str = "https://data.alpaca.markets"  # stable, no env needed
        self.ALPACA_DATA_FEED: str = _env("ALPACA_DATA_FEED", "iex")
        self.ALPACA_WS_URL: str = _env("ALPACA_WS_URL", "wss://stream.data.alpaca.markets/v2/sip")

        # Timeouts
        self.ALPACA_QUOTE_TIMEOUT: float = _env_float("ALPACA_QUOTE_TIMEOUT", 3.0)
        self.ALPACA_BAR_TIMEOUT: float = _env_float("ALPACA_BAR_TIMEOUT", 15.0)
        self.ALPACA_REQUEST_TIMEOUT: float = _env_float("ALPACA_REQUEST_TIMEOUT", 5.0)

        # Computed headers
        self.ALPACA_HEADERS: Dict[str, str] = {
            "APCA-API-KEY-ID": self.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": self.ALPACA_SECRET_KEY,
            "Accept": "application/json",
        }

        # ═══════════════════════════════════════════════════════════════════
        # SIGNAL ENGINE
        # ═══════════════════════════════════════════════════════════════════

        # Confidence tiers
        self.TIER_TEXTBOOK: float = _env_float("TIER_TEXTBOOK", 0.80)
        self.TIER_HIGH: float = _env_float("TIER_HIGH", 0.60)
        self.TIER_VALID: float = _env_float("TIER_VALID", 0.45)
        self.TIER_DEVELOPING: float = _env_float("TIER_DEVELOPING", 0.30)

        # Entry gate — ONE value used by BOTH confluence and position manager
        self.MIN_TRADE_CONFIDENCE: float = _env_float("MIN_TRADE_CONFIDENCE", 0.40)
        self.MIN_COMPOSITE_SCORE: float = _env_float("MIN_COMPOSITE_SCORE", 4.0)

        # Analysis loop
        self.SIGNAL_ANALYSIS_INTERVAL: int = _env_int("SIGNAL_ANALYSIS_INTERVAL", 15)
        self.SIGNAL_HISTORY_MAX: int = _env_int("SIGNAL_HISTORY_MAX", 50)

        # Signal engine data fetch
        self.SIGNAL_FETCH_TIMEOUT: float = _env_float("SIGNAL_FETCH_TIMEOUT", 5.0)
        self.SIGNAL_BARS_1M_LIMIT: int = _env_int("SIGNAL_BARS_1M_LIMIT", 500)
        self.SIGNAL_BARS_DAILY_LIMIT: int = _env_int("SIGNAL_BARS_DAILY_LIMIT", 5)
        self.SIGNAL_MIN_TRADES: int = _env_int("SIGNAL_MIN_TRADES", 5)

        # Strike selection
        self.TARGET_DELTA: float = _env_float("STRIKE_TARGET_DELTA", 0.30)
        self.LARGE_TRADE_THRESHOLD: int = _env_int("LARGE_TRADE_THRESHOLD", 5000)

        # SPX multiplier (SPX ≈ SPY × 10)
        self.SPX_MULTIPLIER: float = _env_float("SPX_MULTIPLIER", 10.0)

        # Factor weights (v7 baseline — overridable by weight learner at runtime)
        self.FACTOR_WEIGHTS_BASELINE: Dict[str, float] = {
            "order_flow_imbalance": 1.5,
            "cvd_divergence": 1.0,
            "gex_alignment": 1.5,
            "dex_levels": 1.0,
            "vwap_rejection": 1.0,
            "volume_spike": 0.5,
            "delta_regime": 1.0,
            "pcr": 0.5,
            "max_pain": 0.5,
            "time_of_day": 0.5,
            "vanna_alignment": 0.75,
            "charm_pressure": 0.75,
            "sweep_activity": 0.75,
            "flow_toxicity": 0.5,
            "sector_divergence": 0.5,
            "agent_consensus": 1.5,
            "ema_sma_trend": 0.75,
            "bb_squeeze": 0.75,
            "support_resistance": 1.0,
            "candle_pattern": 0.5,
            "orb_breakout": 1.25,
            "market_breadth": 1.0,
            "vol_edge": 0.75,
        }

        # Allow JSON override of factor weights via env
        weights_json = _env("FACTOR_WEIGHTS_JSON", "")
        if weights_json:
            try:
                overrides = json.loads(weights_json)
                self.FACTOR_WEIGHTS_BASELINE.update(overrides)
                logger.info(f"[Config] Factor weights overridden: {list(overrides.keys())}")
            except json.JSONDecodeError:
                logger.warning("[Config] Invalid FACTOR_WEIGHTS_JSON, using defaults")

        # ═══════════════════════════════════════════════════════════════════
        # POSITION MANAGEMENT — EXIT RULES
        # ═══════════════════════════════════════════════════════════════════

        # Profit / Loss exits
        self.EXIT_STOP_LOSS_PCT: float = _env_float("EXIT_STOP_LOSS_PCT", -0.50)
        self.EXIT_PROFIT_TARGET_PCT: float = _env_float("EXIT_PROFIT_TARGET_PCT", 1.00)
        self.EXIT_TRAILING_STOP_PCT: float = _env_float("EXIT_TRAILING_STOP_PCT", 0.15)
        self.EXIT_TRAILING_ACTIVATION_PCT: float = _env_float("EXIT_TRAILING_ACTIVATION_PCT", 0.10)

        # Time exits
        self.EXIT_MAX_HOLD_MINUTES: int = _env_int("EXIT_MAX_HOLD_MINUTES", 45)

        # Theta decay exits
        self.EXIT_THETA_DECAY_ENABLED: bool = _env_bool("EXIT_THETA_DECAY_ENABLED", True)
        self.EXIT_THETA_DECAY_THRESHOLD: float = _env_float("EXIT_THETA_DECAY_THRESHOLD", -0.03)

        # Partial exit / scale-out configuration
        self.PARTIAL_EXIT_ENABLED: bool = _env_bool("PARTIAL_EXIT_ENABLED", True)
        self.PARTIAL_EXIT_TIERS: list = [
            {"pnl_pct": 0.30, "exit_frac": 0.34, "label": "T1_SCALEOUT"},  # +30% → sell ~1/3
            {"pnl_pct": 0.60, "exit_frac": 0.50, "label": "T2_SCALEOUT"},  # +60% → sell 1/2 of remaining
        ]
        # After all tiers hit, remainder trails with tighter stop
        self.PARTIAL_EXIT_REMAINDER_TRAIL_PCT: float = _env_float("PARTIAL_REMAINDER_TRAIL", 0.10)
        # Single-contract mode: lower trailing activation when partials aren't possible
        self.SINGLE_CONTRACT_TRAIL_ACTIVATION: float = _env_float("SINGLE_TRAIL_ACTIVATION", 0.25)

        # Dynamic Exit Engine v2 — 5-scorer composite urgency
        self.DYNAMIC_EXIT_ENABLED: bool = _env_bool("DYNAMIC_EXIT_ENABLED", True)
        self.DYNAMIC_EXIT_WEIGHTS: Dict[str, float] = {
            "momentum": _env_float("DEX_W_MOMENTUM", 0.20),
            "greeks":   _env_float("DEX_W_GREEKS", 0.25),
            "levels":   _env_float("DEX_W_LEVELS", 0.20),
            "session":  _env_float("DEX_W_SESSION", 0.15),
            "flow":     _env_float("DEX_W_FLOW", 0.20),
        }
        # Urgency thresholds (0.0-1.0)
        self.DYNAMIC_EXIT_URGENT: float = _env_float("DEX_URGENT", 0.80)
        self.DYNAMIC_EXIT_WARNING: float = _env_float("DEX_WARNING", 0.60)
        self.DYNAMIC_EXIT_CAUTION: float = _env_float("DEX_CAUTION", 0.40)

        # Entry filters (position manager)
        self.PM_MIN_TIER: str = _env("PM_MIN_TIER", "VALID")
        self.PM_MIN_CONFIDENCE: float = self.MIN_TRADE_CONFIDENCE  # uses the SAME value

        # Trade modes (exit strategy profiles)
        self.TRADE_MODE_PARAMS: Dict[str, Dict] = {
            "scalp": {
                "target_pct": 0.20,
                "stop_pct": 0.25,
                "max_hold_minutes": 10,
                "trailing_stop_pct": 0.10,
                "description": "Quick in/out scalp — tight targets, fast exits",
            },
            "standard": {
                "target_pct": 0.50,
                "stop_pct": 0.35,
                "max_hold_minutes": 25,
                "trailing_stop_pct": 0.15,
                "description": "Balanced trade — moderate hold, decent targets",
            },
            "swing": {
                "target_pct": 0.80,
                "stop_pct": 0.45,
                "max_hold_minutes": 45,
                "trailing_stop_pct": 0.20,
                "description": "Longer hold — wider targets, more room to run",
            },
        }

        # ═══════════════════════════════════════════════════════════════════
        # FLOW ENGINE (Rust)
        # ═══════════════════════════════════════════════════════════════════

        self.FLOW_ENGINE_PORT: int = _env_int("FLOW_ENGINE_PORT", 8081)
        self.FLOW_ENGINE_HTTP_URL: str = _env(
            "FLOW_ENGINE_URL_HTTP",
            f"http://localhost:{self.FLOW_ENGINE_PORT}"
        )
        self.FLOW_ENGINE_WS_URL: str = _env(
            "FLOW_ENGINE_URL",
            f"ws://localhost:{self.FLOW_ENGINE_PORT}/ws"
        )
        self.FLOW_ENGINE_STATS_TIMEOUT: float = _env_float("FLOW_ENGINE_STATS_TIMEOUT", 2.0)
        self.FLOW_ENGINE_HEARTBEAT_STALE: int = _env_int("FLOW_ENGINE_HEARTBEAT_STALE", 60)

        # ═══════════════════════════════════════════════════════════════════
        # SERVER
        # ═══════════════════════════════════════════════════════════════════

        self.DASHBOARD_HOST: str = _env("DASHBOARD_HOST", "127.0.0.1")
        self.DASHBOARD_PORT: int = _env_int("DASHBOARD_PORT", 8000)
        self.DASHBOARD_BASE_URL: str = _env(
            "DASHBOARD_BASE_URL",
            f"http://{self.DASHBOARD_HOST}:{self.DASHBOARD_PORT}"
        )
        self.LOG_LEVEL: str = _env("LOG_LEVEL", "INFO")
        self.PAPER_TRADING: bool = _env_bool("PAPER_TRADING", True)

        # CORS
        self.CORS_ORIGINS: list = json.loads(
            _env("CORS_ORIGINS", f'["http://localhost:{self.DASHBOARD_PORT}"]')
        )

        # WebSocket
        self.WS_HEARTBEAT_INTERVAL: int = _env_int("WS_HEARTBEAT_INTERVAL", 30)

        # Orderflow
        self.ORDERFLOW_TRADES_LIMIT: int = _env_int("ORDERFLOW_TRADES_LIMIT", 500)
        self.ORDERFLOW_TRADES_TIMEOUT: float = _env_float("ORDERFLOW_TRADES_TIMEOUT", 5.0)

        # ═══════════════════════════════════════════════════════════════════
        # Loop intervals (background tasks)
        # ═══════════════════════════════════════════════════════════════════

        self.SIGNAL_CONSUMER_INTERVAL: int = _env_int("SIGNAL_CONSUMER_INTERVAL", 3)
        self.EXIT_MONITOR_INTERVAL: int = _env_int("EXIT_MONITOR_INTERVAL", 5)
        self.CHAIN_REFRESH_MIN_INTERVAL: int = _env_int("CHAIN_REFRESH_MIN_INTERVAL", 15)
        self.DECISION_LOG_MAX: int = _env_int("DECISION_LOG_MAX", 200)

        # ═══════════════════════════════════════════════════════════════════
        # FAST PATH (event-driven entry via Rust flow engine WebSocket)
        # ═══════════════════════════════════════════════════════════════════

        # Master switch — disable to fall back to 15s polling only
        self.FAST_PATH_ENABLED: bool = _env_bool("FAST_PATH_ENABLED", True)

        # Rolling window for cluster detection (seconds)
        self.FAST_PATH_WINDOW_SECONDS: int = _env_int("FAST_PATH_WINDOW_SECONDS", 60)

        # Minimum sweeps same-direction in the window to fire SWEEP_CLUSTER
        self.FAST_PATH_SWEEP_CLUSTER_MIN: int = _env_int("FAST_PATH_SWEEP_CLUSTER_MIN", 3)

        # Minimum absorbed-and-held events same-direction to fire ABSORPTION_CLUSTER
        self.FAST_PATH_ABSORPTION_CLUSTER_MIN: int = _env_int(
            "FAST_PATH_ABSORPTION_CLUSTER_MIN", 2
        )

        # Absolute 1-minute CVD delta to fire LARGE_CVD_SPIKE (contracts)
        self.FAST_PATH_CVD_SPIKE_THRESHOLD: int = _env_int(
            "FAST_PATH_CVD_SPIKE_THRESHOLD", 5000
        )

        # Cooldown between consecutive fast triggers (seconds) — prevents burst entries
        self.FAST_PATH_COOLDOWN_SECONDS: int = _env_int("FAST_PATH_COOLDOWN_SECONDS", 30)

        # How old a signal can be (seconds) and still be used by fast_evaluate
        self.FAST_PATH_SIGNAL_MAX_AGE_SECONDS: int = _env_int(
            "FAST_PATH_SIGNAL_MAX_AGE_SECONDS", 300
        )

        # Minimum tier and confidence for fast-path execution
        self.FAST_PATH_MIN_TIER: str = _env("FAST_PATH_MIN_TIER", "VALID")
        self.FAST_PATH_MIN_CONFIDENCE: float = _env_float("FAST_PATH_MIN_CONFIDENCE", 0.45)

        # ═══════════════════════════════════════════════════════════════════
        # LLM VALIDATOR (Phase 2)
        # ═══════════════════════════════════════════════════════════════════

        self.ANTHROPIC_API_KEY: str = _env("ANTHROPIC_API_KEY", "")
        # Model to use for signal validation
        self.LLM_VALIDATOR_MODEL: str = _env("LLM_VALIDATOR_MODEL", "claude-sonnet-4-6")
        # Enable/disable the LLM validator (advisory mode — never blocks trades)
        self.LLM_VALIDATOR_ENABLED: bool = _env_bool("LLM_VALIDATOR_ENABLED", True)
        # Only validate signals at or above this tier (skip low-quality signals)
        self.LLM_VALIDATOR_MIN_TIER: str = _env("LLM_VALIDATOR_MIN_TIER", "DEVELOPING")

    def reload(self):
        """Reload config from environment (useful after .env changes)."""
        self._load()
        logger.info("[Config] Reloaded from environment")


# ═══════════════════════════════════════════════════════════════════════════════
# Singleton instance — import this everywhere
# ═══════════════════════════════════════════════════════════════════════════════

cfg = Config()
