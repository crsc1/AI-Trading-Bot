"""
Agent Orchestration API — exposes the multi-agent system to the frontend.

Endpoints:
  GET  /api/agents/status     — Status of all 5 agents
  GET  /api/agents/signals    — All signals (open + recent closed) with live P/L
  GET  /api/agents/open       — Only open signals with live P/L
  GET  /api/agents/performance — Win rate, total P/L, profit factor
  GET  /api/agents/verdicts   — Raw verdicts from each agent
"""

from fastapi import APIRouter
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["agents"])

# Global publisher instance — initialized by app startup
_publisher = None


def get_publisher():
    """Get or create the global SignalPublisher."""
    global _publisher
    if _publisher is None:
        from .signal_publisher import SignalPublisher
        _publisher = SignalPublisher()
    return _publisher


def start_agents():
    """Start all agents — call from app startup."""
    publisher = get_publisher()
    publisher.start_all()
    logger.info("Agent orchestration system started")


def stop_agents():
    """Stop all agents — call from app shutdown."""
    if _publisher:
        _publisher.stop_all()
        logger.info("Agent orchestration system stopped")


@router.get("/status")
async def get_agent_status():
    """Get status of all 5 agents with their current verdicts."""
    publisher = get_publisher()
    return {
        "agents": publisher.get_agent_status(),
        "open_signals": len(publisher.open_signals),
        "closed_signals": len(publisher.closed_signals),
        "system": "running" if publisher._running else "stopped",
    }


@router.get("/signals")
async def get_all_signals():
    """Get all signals — open (with live P/L) + recently closed."""
    publisher = get_publisher()
    return {
        "signals": publisher.get_all_signals(),
        "count": len(publisher.open_signals) + len(publisher.closed_signals),
    }


@router.get("/open")
async def get_open_signals():
    """Get only currently open signals with live P/L tracking."""
    publisher = get_publisher()
    return {
        "signals": publisher.get_open_signals(),
        "count": len(publisher.open_signals),
    }


@router.get("/performance")
async def get_performance():
    """Get trading performance metrics."""
    publisher = get_publisher()
    return publisher.get_performance()


@router.get("/verdicts")
async def get_agent_verdicts():
    """Get raw verdicts from each individual agent."""
    publisher = get_publisher()
    verdicts = {}
    for agent in publisher._agents:
        v = agent.get_verdict()
        if v:
            verdicts[agent.name] = v.to_dict()
        else:
            verdicts[agent.name] = {
                "agent": agent.name,
                "direction": "none",
                "confidence": 0,
                "reasoning": "No data yet or verdict expired",
                "stale": True,
            }
    return {"verdicts": verdicts}
