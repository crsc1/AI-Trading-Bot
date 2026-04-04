"""
Event Calendar — Economic event awareness for trading decisions.

On CPI/FOMC/NFP days, the market behaves completely differently:
  - IV spikes 50-150% before high-impact releases
  - ±1-3% SPY moves happen in seconds after data
  - Normal technical patterns break down entirely

This module detects upcoming events and adjusts the bot's behavior:

Pre-event mode (15 min before high-impact):
  - Suppress new entries (spreads widen, fills are unreliable)
  - Increase stop-loss buffer on existing positions
  - Flag the event type for context

Post-event mode (0-30 min after release):
  - Enable IV crush trades (buy after IV drops)
  - Detect direction from first 5-min reaction
  - Use wider targets (post-event moves trend longer)

Event-neutral (no events within 60 min):
  - Normal operation

Data sources:
  - Finnhub free API (economic calendar)
  - Static table for FOMC dates (published annually)
  - Fallback: hardcoded high-impact event schedule
"""

import logging
import aiohttp
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"

# Cache for today's events (fetched once per day)
_event_cache: Dict = {"events": None, "date": None}


@dataclass
class EconomicEvent:
    """Single economic event."""
    name: str = ""
    time_utc: Optional[datetime] = None
    impact: str = "low"         # "high", "medium", "low"
    country: str = "US"
    actual: Optional[float] = None
    estimate: Optional[float] = None
    previous: Optional[float] = None
    released: bool = False

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "time_utc": self.time_utc.isoformat() if self.time_utc else None,
            "impact": self.impact,
            "country": self.country,
            "actual": self.actual,
            "estimate": self.estimate,
            "previous": self.previous,
            "released": self.released,
        }


@dataclass
class EventContext:
    """Current event awareness state."""

    # Mode
    mode: str = "normal"          # "pre_event", "post_event", "event_window", "normal"
    description: str = ""

    # Next event
    next_event: Optional[EconomicEvent] = None
    minutes_to_next: float = 999  # Minutes until next event

    # Today's events
    events_today: List[EconomicEvent] = field(default_factory=list)
    high_impact_today: bool = False

    # Adjustments
    suppress_entries: bool = False   # Don't open new positions
    widen_stops: bool = False        # Increase stop buffer
    iv_crush_opportunity: bool = False  # Post-event IV crush trade
    sizing_multiplier: float = 1.0   # Position size adjustment

    def to_dict(self) -> Dict:
        return {
            "mode": self.mode,
            "description": self.description,
            "next_event": self.next_event.to_dict() if self.next_event else None,
            "minutes_to_next": round(self.minutes_to_next, 1),
            "events_today_count": len(self.events_today),
            "high_impact_today": self.high_impact_today,
            "suppress_entries": self.suppress_entries,
            "widen_stops": self.widen_stops,
            "iv_crush_opportunity": self.iv_crush_opportunity,
            "sizing_multiplier": round(self.sizing_multiplier, 2),
        }


# ── High-impact event names (used for classification) ──
HIGH_IMPACT_KEYWORDS = {
    "nonfarm", "non-farm", "payroll", "nfp",
    "cpi", "consumer price",
    "fomc", "federal reserve", "interest rate decision", "fed funds",
    "gdp", "gross domestic",
    "ppi", "producer price",
    "retail sales",
    "unemployment",
    "ism manufacturing", "ism services",
    "pce", "personal consumption",
    "jolts", "job openings",
    "initial claims", "jobless claims",
}

MEDIUM_IMPACT_KEYWORDS = {
    "housing starts", "building permits",
    "durable goods",
    "trade balance",
    "michigan", "consumer sentiment",
    "industrial production",
    "existing home", "new home",
    "empire state", "philly fed",
    "core",
}


async def get_event_context() -> EventContext:
    """
    Get current event awareness state.

    Checks today's economic calendar and determines if we're
    in pre-event, post-event, or normal mode.
    """
    ctx = EventContext()
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Get today's events (cached)
    events = await _get_todays_events(today_str)
    ctx.events_today = events
    ctx.high_impact_today = any(e.impact == "high" for e in events)

    if not events:
        ctx.mode = "normal"
        ctx.description = "No economic events today"
        return ctx

    # Find next unreleased event and most recent released event
    next_event = None
    last_released = None

    for event in sorted(events, key=lambda e: e.time_utc or now):
        if event.time_utc is None:
            continue
        if not event.released and event.time_utc > now:
            if next_event is None:
                next_event = event
        elif event.released or (event.time_utc and event.time_utc <= now):
            last_released = event

    # Determine mode
    if next_event and next_event.time_utc:
        minutes_to = (next_event.time_utc - now).total_seconds() / 60
        ctx.next_event = next_event
        ctx.minutes_to_next = minutes_to

        if minutes_to <= 15 and next_event.impact == "high":
            ctx.mode = "pre_event"
            ctx.suppress_entries = True
            ctx.widen_stops = True
            ctx.sizing_multiplier = 0.3
            ctx.description = f"PRE-EVENT: {next_event.name} in {minutes_to:.0f}min — entries suppressed"

        elif minutes_to <= 30 and next_event.impact == "high":
            ctx.mode = "pre_event"
            ctx.suppress_entries = True
            ctx.sizing_multiplier = 0.5
            ctx.description = f"PRE-EVENT: {next_event.name} in {minutes_to:.0f}min — caution"

        elif minutes_to <= 60 and next_event.impact == "high":
            ctx.mode = "event_window"
            ctx.sizing_multiplier = 0.7
            ctx.description = f"EVENT WINDOW: {next_event.name} in {minutes_to:.0f}min — reduced size"

    # Check for post-event opportunity
    if last_released and last_released.time_utc and last_released.impact == "high":
        minutes_since = (now - last_released.time_utc).total_seconds() / 60
        if minutes_since <= 30:
            ctx.mode = "post_event"
            ctx.iv_crush_opportunity = True
            ctx.sizing_multiplier = 0.8
            ctx.description = f"POST-EVENT: {last_released.name} released {minutes_since:.0f}min ago — IV crush opportunity"

    # Default mode
    if ctx.mode == "normal":
        if ctx.high_impact_today:
            ctx.description = f"Event day: {sum(1 for e in events if e.impact == 'high')} high-impact events (next: {ctx.next_event.name if ctx.next_event else 'none'})"
        else:
            ctx.description = f"{len(events)} low/medium events today — normal operation"

    return ctx


async def _get_todays_events(today_str: str) -> List[EconomicEvent]:
    """
    Fetch today's economic events. Cached per day.

    Tries Finnhub API first, falls back to static FOMC schedule.
    """
    if _event_cache["date"] == today_str and _event_cache["events"] is not None:
        return _event_cache["events"]

    events = []

    # Try Finnhub
    if FINNHUB_KEY:
        try:
            events = await _fetch_finnhub_calendar(today_str)
        except Exception as e:
            logger.debug(f"Finnhub calendar error: {e}")

    # Merge with static high-impact dates
    static_events = _get_static_events(today_str)
    if static_events:
        # Add static events not already in Finnhub data
        existing_names = {e.name.lower() for e in events}
        for se in static_events:
            if se.name.lower() not in existing_names:
                events.append(se)

    # Sort by time
    events.sort(key=lambda e: e.time_utc or datetime.max.replace(tzinfo=timezone.utc))

    _event_cache["date"] = today_str
    _event_cache["events"] = events

    return events


async def _fetch_finnhub_calendar(today_str: str) -> List[EconomicEvent]:
    """Fetch economic calendar from Finnhub free API."""
    url = f"{FINNHUB_BASE}/calendar/economic"
    params = {
        "from": today_str,
        "to": today_str,
        "token": FINNHUB_KEY,
    }

    events = []

    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, params=params,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return []

            data = await resp.json()
            raw_events = data.get("economicCalendar", [])

            for raw in raw_events:
                country = raw.get("country", "")
                if country not in ("US", ""):
                    continue  # Only US events matter for SPY

                name = raw.get("event", "")
                impact = _classify_impact(name)

                # Parse time
                event_time = None
                time_str = raw.get("time", "")
                if time_str and time_str != "00:00:00":
                    try:
                        event_time = datetime.fromisoformat(
                            f"{today_str}T{time_str}+00:00"
                        )
                    except (ValueError, TypeError):
                        pass

                events.append(EconomicEvent(
                    name=name,
                    time_utc=event_time,
                    impact=impact,
                    country="US",
                    actual=raw.get("actual"),
                    estimate=raw.get("estimate"),
                    previous=raw.get("prev"),
                    released=raw.get("actual") is not None,
                ))

    return events


def _classify_impact(event_name: str) -> str:
    """Classify event impact from name."""
    name_lower = event_name.lower()

    for kw in HIGH_IMPACT_KEYWORDS:
        if kw in name_lower:
            return "high"

    for kw in MEDIUM_IMPACT_KEYWORDS:
        if kw in name_lower:
            return "medium"

    return "low"


def _get_static_events(today_str: str) -> List[EconomicEvent]:
    """
    Static high-impact event schedule.

    FOMC dates are published annually. These are the 2026 dates.
    CPI/NFP dates follow predictable monthly patterns.
    """
    # 2026 FOMC Meeting Dates (announcement at 2:00 PM ET = 18:00 UTC on day 2)
    fomc_dates_2026 = {
        "2026-01-28", "2026-03-18", "2026-05-06",
        "2026-06-17", "2026-07-29", "2026-09-16",
        "2026-11-04", "2026-12-16",
    }

    events = []

    if today_str in fomc_dates_2026:
        events.append(EconomicEvent(
            name="FOMC Interest Rate Decision",
            time_utc=datetime.fromisoformat(f"{today_str}T18:00:00+00:00"),
            impact="high",
            country="US",
        ))

    # CPI: Usually released at 8:30 AM ET (12:30 UTC) on ~12th of month
    # NFP: Usually first Friday of month at 8:30 AM ET (12:30 UTC)
    try:
        dt = datetime.strptime(today_str, "%Y-%m-%d")

        # CPI approximation: 10th-15th of month
        if 10 <= dt.day <= 15 and dt.weekday() < 5:
            events.append(EconomicEvent(
                name="CPI (Consumer Price Index)",
                time_utc=datetime.fromisoformat(f"{today_str}T12:30:00+00:00"),
                impact="high",
                country="US",
            ))

        # NFP: First Friday (day 1-7, weekday=4)
        if dt.day <= 7 and dt.weekday() == 4:
            events.append(EconomicEvent(
                name="Nonfarm Payrolls",
                time_utc=datetime.fromisoformat(f"{today_str}T12:30:00+00:00"),
                impact="high",
                country="US",
            ))

    except Exception:
        pass

    return events


# ── Scoring function for confluence integration ──

def score_event_context(
    ctx: EventContext,
) -> Tuple[float, str]:
    """
    Score event impact on current trading opportunity.

    Returns adjustment multiplier for final confidence score.
    This is multiplicative (0.3 to 1.1), not additive.

    Pre-event: Dramatically reduce (0.3-0.5)
    Post-event IV crush: Slight boost (1.05-1.1)
    No events: Neutral (1.0)
    """
    if ctx.mode == "pre_event":
        if ctx.minutes_to_next <= 15:
            return 0.3, f"BLOCKED: {ctx.next_event.name} in {ctx.minutes_to_next:.0f}min"
        else:
            return 0.5, f"CAUTION: {ctx.next_event.name} in {ctx.minutes_to_next:.0f}min"

    elif ctx.mode == "event_window":
        return 0.7, f"Event window: {ctx.next_event.name} in {ctx.minutes_to_next:.0f}min"

    elif ctx.mode == "post_event":
        if ctx.iv_crush_opportunity:
            return 1.1, f"Post-event: IV crush opportunity ({ctx.description})"
        return 1.0, "Post-event: neutral"

    else:
        if ctx.high_impact_today:
            return 0.9, f"Event day: high-impact events scheduled — slight caution"
        return 1.0, "No events — normal operation"
