"""
Base agent class and shared data structures for the multi-agent system.

Each agent:
  - Runs independently on its own polling cycle
  - Produces an AgentVerdict (bullish/bearish/neutral + confidence + reasoning)
  - The SignalPublisher collects all verdicts and decides whether to publish
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum
import logging
import asyncio

logger = logging.getLogger(__name__)


class Direction(str, Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class AgentVerdict:
    """Output from any agent — its directional opinion + confidence."""
    agent_name: str
    direction: Direction
    confidence: float          # 0.0 - 1.0
    reasoning: str             # Human-readable explanation
    factors: List[str] = field(default_factory=list)  # Supporting data points
    data: Dict[str, Any] = field(default_factory=dict) # Raw data for other agents
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stale_after_seconds: int = 60  # How long this verdict is valid

    def is_stale(self) -> bool:
        """Check if this verdict has expired."""
        try:
            created = datetime.fromisoformat(self.timestamp)
            age = (datetime.now(timezone.utc) - created).total_seconds()
            return age > self.stale_after_seconds
        except Exception:
            return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent_name,
            "direction": self.direction.value,
            "confidence": round(self.confidence, 3),
            "reasoning": self.reasoning,
            "factors": self.factors,
            "timestamp": self.timestamp,
            "stale": self.is_stale(),
        }


@dataclass
class PublishedSignal:
    """A fully qualified trade signal published by the SignalPublisher."""
    signal_id: str
    action: str               # BUY_CALL, BUY_PUT
    symbol: str
    strike: float
    expiry: str
    entry_price: float
    target_price: float
    stop_price: float
    confidence: float
    tier: str                 # TEXTBOOK, HIGH, VALID
    reasoning: str
    verdicts: List[Dict]      # Contributing agent verdicts
    risk: Dict[str, Any]
    option_data: Dict[str, Any]
    levels: Dict[str, float]
    timestamp: str

    # P/L tracking
    status: str = "OPEN"      # OPEN, TARGET_HIT, STOPPED, EXPIRED, CLOSED
    current_price: float = 0.0
    pnl_dollars: float = 0.0
    pnl_percent: float = 0.0
    contracts: int = 1
    max_price: float = 0.0    # High water mark
    min_price: float = 0.0    # Low water mark
    closed_at: Optional[str] = None
    close_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal": self.action,
            "symbol": self.symbol,
            "strike": self.strike,
            "expiry": self.expiry,
            "entry_price": self.entry_price,
            "target_price": self.target_price,
            "stop_price": self.stop_price,
            "confidence": round(self.confidence, 3),
            "tier": self.tier,
            "reasoning": self.reasoning,
            "verdicts": self.verdicts,
            "risk_management": self.risk,
            "option_data": self.option_data,
            "levels": self.levels,
            "timestamp": self.timestamp,
            # P/L tracking
            "status": self.status,
            "current_price": round(self.current_price, 2),
            "pnl_dollars": round(self.pnl_dollars, 2),
            "pnl_percent": round(self.pnl_percent, 2),
            "contracts": self.contracts,
            "max_price": round(self.max_price, 2),
            "min_price": round(self.min_price, 2),
            "closed_at": self.closed_at,
            "close_reason": self.close_reason,
        }


class BaseAgent:
    """
    Base class for all trading agents.
    Subclasses implement `async def analyze()` which returns an AgentVerdict.
    """

    name: str = "BaseAgent"
    poll_interval: int = 15   # seconds between analysis cycles
    stale_seconds: int = 60   # how long verdicts remain valid

    def __init__(self):
        self.latest_verdict: Optional[AgentVerdict] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def analyze(self) -> AgentVerdict:
        """Override in subclass. Perform analysis and return verdict."""
        raise NotImplementedError

    async def _loop(self):
        """Main polling loop."""
        # Wait for server to be fully ready before polling endpoints
        await asyncio.sleep(8)
        while self._running:
            try:
                self.latest_verdict = await self.analyze()
                logger.debug(f"[{self.name}] {self.latest_verdict.direction.value} "
                           f"({self.latest_verdict.confidence:.0%}): {self.latest_verdict.reasoning[:80]}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[{self.name}] Analysis error: {e}")
                self.latest_verdict = AgentVerdict(
                    agent_name=self.name,
                    direction=Direction.NEUTRAL,
                    confidence=0.0,
                    reasoning=f"Error: {str(e)[:100]}",
                    stale_after_seconds=self.stale_seconds,
                )
            await asyncio.sleep(self.poll_interval)

    def start(self):
        """Start the agent's polling loop."""
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())
            logger.info(f"[{self.name}] Started (poll every {self.poll_interval}s)")

    def stop(self):
        """Stop the agent."""
        self._running = False
        if self._task:
            self._task.cancel()
            logger.info(f"[{self.name}] Stopped")

    def get_verdict(self) -> Optional[AgentVerdict]:
        """Get latest verdict if not stale."""
        if self.latest_verdict and not self.latest_verdict.is_stale():
            return self.latest_verdict
        return None
