"""
LLM API call rate limiter — enforces daily call limits per feature.

Tracks calls in memory (resets on server restart or at midnight ET).
Exposed via /api/pm/settings for the UI settings panel.
"""

from datetime import datetime, timezone, timedelta
import logging

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except ImportError:
    ET = timezone(timedelta(hours=-4))

logger = logging.getLogger(__name__)


class LLMRateLimiter:
    def __init__(self):
        self._counts = {
            "news": 0,
            "validator": 0,
            "exit_advisor": 0,
            "daily_review": 0,
        }
        self._total = 0
        self._date = datetime.now(ET).date()

    def _check_reset(self):
        """Reset counters at midnight ET."""
        today = datetime.now(ET).date()
        if today != self._date:
            logger.info(f"[LLMRate] Daily reset: {self._total} calls yesterday")
            self._counts = {k: 0 for k in self._counts}
            self._total = 0
            self._date = today

    def can_call(self, feature: str) -> bool:
        """Check if a call is allowed for this feature."""
        from .config import cfg
        self._check_reset()

        # Global limit (-1 = unlimited, 0 = blocked, >0 = daily cap)
        global_limit = cfg.LLM_DAILY_CALL_LIMIT
        if global_limit == 0:
            return False
        if global_limit > 0 and self._total >= global_limit:
            return False

        # Per-feature limit
        feature_limit = {
            "news": cfg.LLM_NEWS_CALL_LIMIT,
            "validator": cfg.LLM_VALIDATOR_CALL_LIMIT,
            "exit_advisor": cfg.LLM_EXIT_ADVISOR_CALL_LIMIT,
            "daily_review": 0,  # No per-feature limit on daily review
        }.get(feature, 0)

        if feature_limit == 0:
            return False
        if feature_limit > 0 and self._counts.get(feature, 0) >= feature_limit:
            return False

        return True

    def record_call(self, feature: str):
        """Record that a call was made."""
        self._check_reset()
        self._counts[feature] = self._counts.get(feature, 0) + 1
        self._total += 1

    def get_usage(self) -> dict:
        """Return current usage for the settings panel."""
        from .config import cfg
        self._check_reset()
        return {
            "total_calls_today": self._total,
            "global_limit": cfg.LLM_DAILY_CALL_LIMIT,
            "features": {
                "news": {
                    "calls": self._counts.get("news", 0),
                    "limit": cfg.LLM_NEWS_CALL_LIMIT,
                },
                "validator": {
                    "calls": self._counts.get("validator", 0),
                    "limit": cfg.LLM_VALIDATOR_CALL_LIMIT,
                },
                "exit_advisor": {
                    "calls": self._counts.get("exit_advisor", 0),
                    "limit": cfg.LLM_EXIT_ADVISOR_CALL_LIMIT,
                },
                "daily_review": {
                    "calls": self._counts.get("daily_review", 0),
                    "limit": 0,  # Uncapped (runs once/day)
                },
            },
        }

    def update_limits(self, settings: dict):
        """Update limits from settings panel."""
        from .config import cfg
        if "global_limit" in settings:
            cfg.LLM_DAILY_CALL_LIMIT = int(settings["global_limit"])
        if "news_limit" in settings:
            cfg.LLM_NEWS_CALL_LIMIT = int(settings["news_limit"])
        if "validator_limit" in settings:
            cfg.LLM_VALIDATOR_CALL_LIMIT = int(settings["validator_limit"])
        if "exit_advisor_limit" in settings:
            cfg.LLM_EXIT_ADVISOR_CALL_LIMIT = int(settings["exit_advisor_limit"])
        logger.info(
            f"[LLMRate] Limits updated: global={cfg.LLM_DAILY_CALL_LIMIT}, "
            f"news={cfg.LLM_NEWS_CALL_LIMIT}, val={cfg.LLM_VALIDATOR_CALL_LIMIT}, "
            f"exit={cfg.LLM_EXIT_ADVISOR_CALL_LIMIT}"
        )


# Singleton
rate_limiter = LLMRateLimiter()
