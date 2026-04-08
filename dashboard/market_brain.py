"""
Market Brain — LLM-powered trading decision engine.

Replaces: signal_engine.py (decision pipeline), agents/ (5-agent voting),
llm_validator.py (advisory validation), confluence.py scoring logic.

Architecture:
    Every 15s cycle:
    1. DataCollector gathers all provider data → MarketSnapshot
    2. Snapshot formatted as structured text → appended to conversation
    3. Claude Sonnet 4.6 analyzes → returns structured JSON decision
    4. If action == TRADE → re-evaluate with Opus 4.6 → pass to position_manager
    5. User chat messages interleaved in same conversation thread

The Brain maintains a rolling conversation window so it has context
of what it just analyzed when the user asks a question.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .data_collector import MarketSnapshot, collect_snapshot
from .brain_router import call_brain, get_router_stats

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_CONVERSATION_TURNS = 30     # Rolling window of conversation history
MAX_DECISIONS = 200             # Rolling window of stored decisions
ANALYSIS_INTERVAL = 15          # Seconds between analysis cycles


# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Market Brain, an expert 0DTE SPY/SPX options trader.

## Your Role
You analyze real-time market data every 15 seconds and decide whether to trade.
You manage risk strictly — your job is to protect capital first, profit second.

## Output Format
You MUST respond with valid JSON only. No markdown, no code blocks, no explanation outside the JSON.

{
  "action": "HOLD",
  "direction": null,
  "confidence": 0.0,
  "tier": "DEVELOPING",
  "reasoning": "Brief 1-2 sentence explanation",
  "key_factors": ["factor1", "factor2", "factor3"],
  "risk_notes": null,
  "chat_response": null
}

## Action Values
- HOLD: No trade opportunity. Continue monitoring.
- TRADE: Take a new position. Must include direction, confidence, tier.
- EXIT: Close an existing position. Include risk_notes with position details.
- ADJUST: Modify existing position (tighten stops, partial exit). Include risk_notes.

## Direction (when action=TRADE)
- BUY_CALL: Bullish — buy call options
- BUY_PUT: Bearish — buy put options

## Tier (confidence mapping)
- TEXTBOOK: confidence >= 0.80 — Multiple strong confluences, rare setup
- HIGH: confidence >= 0.60 — Clear direction with good confirmation
- VALID: confidence >= 0.45 — Reasonable setup, moderate risk
- DEVELOPING: confidence < 0.45 — Still forming, not ready

## Decision Rules
1. NEVER trade without at least 3 confirming factors
2. NEVER trade against strong order flow (CVD divergence = caution)
3. Respect session context: opening_drive is trending, midday_chop is dangerous
4. IV Rank > 80 = premiums too expensive, avoid new entries
5. After 2:30 PM ET, require quality >= 0.75 (late-day theta decay)
6. After 3:00 PM ET, no new entries (hard stop)
7. If daily P&L is negative, raise confidence threshold by 0.10
8. Maximum 3 open positions at any time
9. Setup-based entries (VWAP_BOUNCE, HOD_BREAK, etc.) are preferred over raw confluence

## Chat
If the user sent a message (indicated by "USER ASKS:"), include your response in chat_response.
Keep it concise but helpful. You have full context of the market data you just analyzed.
If the user gives an instruction (e.g., "tighten stops", "go bearish only"), acknowledge and adjust.

## Risk Management
- Always note concerns in risk_notes (e.g., "VIX elevated, reduce size")
- Flag if a trade conflicts with regime or order flow
- If you recommend EXIT, explain which position and why
"""

CHAT_SYSTEM_PROMPT = """You are Market Brain, the AI trading assistant built into a personal 0DTE SPY/SPX options trading platform.

You speak like a sharp, experienced trader who actually looks at charts. Direct, concrete, no fluff. You reference specific price levels, times, and patterns. Think senior trader at a prop desk explaining the day to a colleague.

When you receive market data (bars, price, etc.), analyze it thoroughly:
- Identify the trend, key levels, support/resistance
- Note volume patterns and significant candles
- Call out specific times and prices, not generalities
- If asked about setups, give actionable levels

Keep responses concise but substantive. Use plain text, not JSON. Format with line breaks for readability. Use $ for prices.

You have access to live market data that gets attached to each message. Use it. Reference specific numbers from the data. If the data shows SPY at $673.64 with HOD $675.15 and LOD $651.06, say exactly that.

When the market is closed, you can still analyze the day's chart, identify patterns, and discuss what happened. Don't refuse to analyze just because the session ended.

All times are Eastern Time (ET). Never display or reference UTC. Market hours are 9:30 AM - 4:00 PM ET.
"""


@dataclass
class BrainDecision:
    """One decision from the Market Brain."""
    id: str = ""
    timestamp: str = ""
    cycle: int = 0
    action: str = "HOLD"                # HOLD, TRADE, EXIT, ADJUST
    direction: Optional[str] = None     # BUY_CALL, BUY_PUT
    confidence: float = 0.0
    tier: str = "DEVELOPING"
    reasoning: str = ""
    key_factors: List[str] = field(default_factory=list)
    risk_notes: Optional[str] = None
    chat_response: Optional[str] = None
    model: str = ""
    latency_ms: int = 0
    snapshot_summary: str = ""          # The data Brain analyzed

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MarketBrain:
    """
    The Market Brain — single LLM instance that replaces the multi-agent pipeline.
    """

    def __init__(self):
        self.conversation: List[Dict[str, str]] = []    # Analysis cycle thread
        self.chat_history: List[Dict[str, str]] = []    # Chat thread (separate)
        self.decisions: deque = deque(maxlen=MAX_DECISIONS)
        self.cycle_count: int = 0
        self.status: str = "idle"       # idle, analyzing, trading, error
        self.last_decision: Optional[BrainDecision] = None
        self.chat_queue: List[str] = []  # Messages from user waiting for next cycle
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def get_state(self) -> Dict[str, Any]:
        """Return current Brain state for the frontend."""
        return {
            "status": self.status,
            "cycle_number": self.cycle_count,
            "last_action": self.last_decision.action if self.last_decision else "HOLD",
            "last_confidence": self.last_decision.confidence if self.last_decision else 0,
            "last_reasoning": self.last_decision.reasoning if self.last_decision else "",
            "model": self.last_decision.model if self.last_decision else "",
            "uptime_s": 0,  # TODO: track
            "router_stats": get_router_stats(),
        }

    def queue_chat_message(self, message: str) -> None:
        """Queue a user message for the next analysis cycle."""
        self.chat_queue.append(message)
        logger.info(f"[Brain] Chat message queued: {message[:80]}")

    async def _fetch_chat_context(self) -> str:
        """
        Fetch live market data from our own REST APIs to give the Brain
        current context for answering chat questions.
        """
        import aiohttp
        lines = []
        try:
            async with aiohttp.ClientSession() as session:
                # Market data (price, source)
                async with session.get("http://localhost:8000/api/market", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        spy = data.get("spy", {})
                        price = spy.get("price", 0)
                        if price > 0:
                            lines.append(f"SPY: ${price:.2f} (source: {spy.get('source', 'unknown')})")
                            lines.append(f"Ticks: {spy.get('ticks', 0)}")

                # Candle bars for chart analysis
                async with session.get("http://localhost:8000/api/bars?symbol=SPY&timeframe=5Min&limit=50", timeout=aiohttp.ClientTimeout(total=3)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        bars = data.get("bars", [])
                        if bars:
                            lines.append(f"\nRECENT 5-MIN BARS ({len(bars)} bars):")
                            for bar in bars[-20:]:
                                # Handle both unix timestamp and ISO format
                                t = bar.get("time", bar.get("t", ""))
                                if isinstance(t, (int, float)) and t > 1000000000:
                                    from datetime import datetime as _dt
                                    from zoneinfo import ZoneInfo as _ZI
                                    time_str = _dt.fromtimestamp(t, tz=_ZI("America/New_York")).strftime("%H:%M")
                                elif isinstance(t, str) and "T" in t:
                                    time_str = t.split("T")[1][:5]
                                else:
                                    time_str = str(t)
                                o = bar.get("open", bar.get("o", 0))
                                h = bar.get("high", bar.get("h", 0))
                                l = bar.get("low", bar.get("l", 0))
                                c = bar.get("close", bar.get("c", 0))
                                v = bar.get("volume", bar.get("v", 0))
                                direction = "+" if c >= o else "-"
                                lines.append(
                                    f"  {time_str} O={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f} V={v:,.0f} {direction}"
                                )
                            if len(bars) >= 2:
                                highs = [b.get("high", b.get("h", 0)) for b in bars]
                                lows = [b.get("low", b.get("l", 0)) for b in bars]
                                first_open = bars[0].get("open", bars[0].get("o", 0))
                                highs = [x for x in highs if x > 0]
                                lows = [x for x in lows if x > 0]
                                if highs and lows and first_open:
                                    lines.append(f"\nSESSION: HOD=${max(highs):.2f}, LOD=${min(lows):.2f}, Open=${first_open:.2f}")

                # Order flow stats
                async with session.get("http://localhost:8000/api/stream/stats", timeout=aiohttp.ClientTimeout(total=2)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("connected"):
                            lines.append(f"\nSTREAM: Connected, {data.get('trades_received', 0)} trades")
                            nbbo = data.get("nbbo", {})
                            if nbbo.get("bid"):
                                lines.append(f"NBBO: ${nbbo['bid']:.2f} / ${nbbo['ask']:.2f}")

        except Exception as e:
            logger.debug(f"[Brain] Chat context fetch error: {e}")

        if lines:
            return "[Live Market Data — all times Eastern]\n" + "\n".join(lines)
        return ""

    async def analyze_cycle(self, engine: Any) -> BrainDecision:
        """
        Run one analysis cycle:
        1. Collect market snapshot
        2. Format as prompt
        3. Call Claude
        4. Parse response
        5. Escalate to Opus if TRADE
        """
        self.status = "analyzing"
        self.cycle_count += 1
        cycle = self.cycle_count

        try:
            # 1. Collect snapshot
            snapshot = await collect_snapshot(engine)
            snapshot_text = snapshot.to_prompt()

            # 2. Build user message with snapshot + any queued chat
            user_parts = [f"[Cycle {cycle}] Market data:\n{snapshot_text}"]

            # Include queued chat messages
            if self.chat_queue:
                for msg in self.chat_queue:
                    user_parts.append(f"\nUSER ASKS: {msg}")
                self.chat_queue.clear()

            user_message = "\n".join(user_parts)

            # 3. Append to conversation (rolling window)
            self.conversation.append({"role": "user", "content": user_message})

            # Trim conversation to max turns
            while len(self.conversation) > MAX_CONVERSATION_TURNS * 2:
                self.conversation.pop(0)

            # 4. Call Sonnet
            result = await call_brain(
                system_prompt=SYSTEM_PROMPT,
                messages=self.conversation,
                escalate=False,
            )

            if result["error"]:
                self.status = "error"
                decision = BrainDecision(
                    id=str(uuid.uuid4())[:8],
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    cycle=cycle,
                    action="HOLD",
                    reasoning=f"Analysis error: {result['error']}",
                    model=result["model"],
                )
                self.last_decision = decision
                self.decisions.append(decision)
                return decision

            # 5. Parse JSON response
            raw_content = result["content"].strip()

            # Append assistant response to conversation
            self.conversation.append({"role": "assistant", "content": raw_content})

            decision = self._parse_decision(raw_content, cycle, result)
            decision.snapshot_summary = snapshot_text[:500]

            # 6. Escalate to Opus if TRADE
            if decision.action == "TRADE" and decision.confidence >= 0.45:
                self.status = "trading"
                logger.info(f"[Brain] Escalating to Opus for trade decision: {decision.direction}")

                # Build escalation prompt
                escalation_msg = (
                    f"You recommended {decision.direction} with {decision.confidence:.0%} confidence.\n"
                    f"Reasoning: {decision.reasoning}\n"
                    f"Key factors: {', '.join(decision.key_factors)}\n\n"
                    f"As a final check before execution, confirm or reject this trade. "
                    f"Respond with the same JSON format. If you reject, set action=HOLD."
                )
                self.conversation.append({"role": "user", "content": escalation_msg})

                opus_result = await call_brain(
                    system_prompt=SYSTEM_PROMPT,
                    messages=self.conversation,
                    escalate=True,
                )

                if not opus_result["error"]:
                    self.conversation.append({"role": "assistant", "content": opus_result["content"]})
                    opus_decision = self._parse_decision(opus_result["content"], cycle, opus_result)
                    # Opus has final say
                    if opus_decision.action != "TRADE":
                        logger.info(f"[Brain] Opus rejected trade: {opus_decision.reasoning}")
                        decision = opus_decision
                    else:
                        decision.model = opus_result["model"]
                        decision.latency_ms += opus_result["latency_ms"]

            self.status = "idle"
            self.last_decision = decision
            self.decisions.append(decision)

            logger.info(
                f"[Brain] Cycle {cycle}: {decision.action} "
                f"conf={decision.confidence:.2f} "
                f"model={decision.model} "
                f"latency={decision.latency_ms}ms"
            )

            return decision

        except Exception as e:
            self.status = "error"
            logger.error(f"[Brain] Cycle {cycle} error: {e}", exc_info=True)
            decision = BrainDecision(
                id=str(uuid.uuid4())[:8],
                timestamp=datetime.now(timezone.utc).isoformat(),
                cycle=cycle,
                action="HOLD",
                reasoning=f"Unexpected error: {str(e)[:100]}",
            )
            self.last_decision = decision
            self.decisions.append(decision)
            return decision

    async def chat_immediate(self, message: str) -> str:
        """
        Handle an immediate chat message.
        Uses a separate conversation thread with a chat-specific prompt
        so the Brain responds naturally instead of in JSON.
        """
        # Fetch live market context
        context = await self._fetch_chat_context()

        # Build the user message with context
        if context:
            user_msg = f"{context}\n\n{message}"
        else:
            user_msg = message

        self.chat_history.append({"role": "user", "content": user_msg})

        # Trim chat history
        while len(self.chat_history) > MAX_CONVERSATION_TURNS * 2:
            self.chat_history.pop(0)

        result = await call_brain(
            system_prompt=CHAT_SYSTEM_PROMPT,
            messages=self.chat_history,
            chat=True,
        )

        if result["error"]:
            return f"Sorry, I encountered an error: {result['error']}"

        content = result["content"].strip()
        self.chat_history.append({"role": "assistant", "content": content})
        return content

    def _parse_decision(self, raw: str, cycle: int, result: Dict) -> BrainDecision:
        """Parse JSON response from Claude into a BrainDecision."""
        decision = BrainDecision(
            id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(timezone.utc).isoformat(),
            cycle=cycle,
            model=result.get("model", ""),
            latency_ms=result.get("latency_ms", 0),
        )

        try:
            # Handle potential markdown code blocks
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            parsed = json.loads(text)
            decision.action = parsed.get("action", "HOLD")
            decision.direction = parsed.get("direction")
            decision.confidence = float(parsed.get("confidence", 0))
            decision.tier = parsed.get("tier", "DEVELOPING")
            decision.reasoning = parsed.get("reasoning", "")
            decision.key_factors = parsed.get("key_factors", [])
            decision.risk_notes = parsed.get("risk_notes")
            decision.chat_response = parsed.get("chat_response")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[Brain] Failed to parse response: {e}")
            decision.action = "HOLD"
            decision.reasoning = f"Parse error: {str(e)[:80]}. Raw: {raw[:200]}"

        return decision

    def get_recent_decisions(self, limit: int = 20) -> List[Dict]:
        """Return recent decisions, newest first."""
        return [d.to_dict() for d in reversed(list(self.decisions))][:limit]


# ── Singleton ─────────────────────────────────────────────────────────────────
brain = MarketBrain()
