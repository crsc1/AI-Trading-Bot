"""
Dynamic Exit Engine v2 — 5-Scorer adaptive exit system.

Replaces static exit thresholds with a composite urgency score
that adapts to live market conditions every 5 seconds.

Scorers:
  1. Momentum Exhaustion   — CVD flattening, volume declining, price divergence
  2. Greeks Dynamics        — Theta acceleration, gamma risk, IV crush
  3. Level Proximity        — Distance to VWAP bands, GEX walls, HOD/LOD, pivots
  4. Session Context        — Phase transitions, time remaining, session quality
  5. Flow Reversal          — Order flow turning against position direction

Composite logic:
  urgency > 0.80 → URGENT: exit immediately
  urgency > 0.60 → WARNING: tighten trailing stop to 50%
  urgency > 0.40 → CAUTION: move stop to breakeven if profitable
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple

logger = logging.getLogger(__name__)


# ─── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ScorerResult:
    """Output from a single scorer."""
    name: str
    score: float        # 0.0 (no concern) to 1.0 (maximum urgency)
    detail: str = ""    # Human-readable reason
    signals: List[str] = field(default_factory=list)  # Individual signal names that fired

    def __repr__(self):
        return f"{self.name}={self.score:.2f}"


@dataclass
class ExitUrgency:
    """Composite result from all 5 scorers."""
    urgency: float = 0.0                 # Weighted average, 0.0-1.0
    level: str = "HOLD"                  # HOLD, CAUTION, WARNING, URGENT
    scorers: List[ScorerResult] = field(default_factory=list)
    trailing_multiplier: float = 1.0     # 1.0 = normal, 0.5 = tightened
    move_to_breakeven: bool = False
    force_exit: bool = False
    detail: str = ""

    def to_dict(self) -> Dict:
        return {
            "urgency": round(self.urgency, 3),
            "level": self.level,
            "trailing_multiplier": self.trailing_multiplier,
            "move_to_breakeven": self.move_to_breakeven,
            "force_exit": self.force_exit,
            "detail": self.detail,
            "scorers": {s.name: {"score": round(s.score, 3), "detail": s.detail}
                        for s in self.scorers},
        }


# ─── Scorer Weights ──────────────────────────────────────────────────────────

DEFAULT_WEIGHTS = {
    "momentum":  0.20,
    "greeks":    0.25,
    "levels":    0.20,
    "session":   0.15,
    "flow":      0.20,
}


# ─── Scorer 1: Momentum Exhaustion ───────────────────────────────────────────

def score_momentum(position: Dict, flow: Optional[Dict],
                   levels: Optional[Dict],
                   breadth: Optional[Dict] = None) -> ScorerResult:
    """
    Detect momentum exhaustion — signs the move is losing steam.

    Checks:
      - CVD flattening/reversing after directional move
      - Volume declining on continuation
      - Price overextension (distance from VWAP/EMA)
      - Market breadth divergence (broad market disagreeing with position)
    """
    score = 0.0
    signals = []
    details = []

    direction = _position_direction(position)
    position.get("unrealized_pnl_pct", 0)

    if flow:
        cvd_trend = flow.get("cvd_trend", "neutral")
        cvd_accel = flow.get("cvd_acceleration", 0)

        # CVD reversing against our direction
        if direction == "bullish" and cvd_trend == "falling":
            score += 0.35
            signals.append("cvd_reversing")
            details.append("CVD falling against long position")
        elif direction == "bearish" and cvd_trend == "rising":
            score += 0.35
            signals.append("cvd_reversing")
            details.append("CVD rising against short position")

        # CVD decelerating (momentum fading)
        if direction == "bullish" and cvd_accel < -0.3:
            score += 0.20
            signals.append("cvd_decelerating")
            details.append(f"CVD deceleration {cvd_accel:.2f}")
        elif direction == "bearish" and cvd_accel > 0.3:
            score += 0.20
            signals.append("cvd_decelerating")
            details.append(f"CVD deceleration {cvd_accel:.2f}")

        # Volume exhaustion detected
        if flow.get("volume_exhausted", False):
            score += 0.25
            signals.append("volume_exhausted")
            details.append(f"Volume exhaustion (str={flow.get('exhaustion_strength', 0):.2f})")

    # Price overextension from VWAP (mean reversion risk)
    if levels:
        price = levels.get("current_price", 0)
        levels.get("vwap", 0)
        vwap_2u = levels.get("vwap_upper_2", 0)
        vwap_2l = levels.get("vwap_lower_2", 0)

        if price > 0 and vwap_2u > 0:
            if direction == "bullish" and price > vwap_2u:
                score += 0.20
                signals.append("overextended_above_vwap2")
                details.append(f"Price ${price:.2f} above VWAP+2σ ${vwap_2u:.2f}")
            elif direction == "bearish" and price < vwap_2l:
                score += 0.20
                signals.append("overextended_below_vwap2")
                details.append(f"Price ${price:.2f} below VWAP-2σ ${vwap_2l:.2f}")

    # Market breadth divergence — broad market opposing our direction
    if breadth:
        bs = breadth.get("breadth_score", 0)
        divergence = breadth.get("breadth_divergence", False)

        if direction == "bullish" and bs < -0.3:
            score += 0.20
            signals.append("breadth_opposing")
            details.append(f"Breadth opposing bullish ({bs:+.2f})")
        elif direction == "bearish" and bs > 0.3:
            score += 0.20
            signals.append("breadth_opposing")
            details.append(f"Breadth opposing bearish ({bs:+.2f})")

        if divergence:
            div_dir = breadth.get("divergence_direction", "none")
            if (direction == "bullish" and div_dir == "bearish_div") or \
               (direction == "bearish" and div_dir == "bullish_div"):
                score += 0.15
                signals.append("breadth_divergence")
                details.append(f"Breadth divergence: {div_dir}")

    return ScorerResult(
        name="momentum",
        score=min(1.0, score),
        detail=" | ".join(details) if details else "Momentum intact",
        signals=signals,
    )


# ─── Scorer 2: Greeks Dynamics ───────────────────────────────────────────────

def score_greeks(position: Dict,
                 vol_regime: Optional[Dict] = None) -> ScorerResult:
    """
    Detect Greeks working against the position.

    Checks:
      - Theta acceleration (non-linear after 2 PM on 0DTE)
      - Gamma flip risk (positive→negative gamma)
      - IV crush (entry IV vs current IV)
      - Delta erosion (option losing sensitivity)
      - Vol regime penalty (expensive options = theta headwind stronger)
    """
    score = 0.0
    signals = []
    details = []

    live_greeks = position.get("live_greeks", {})
    entry_greeks = position.get("greeks_at_entry", {})
    greeks_pnl = position.get("greeks_pnl", {})
    position.get("hold_minutes", 0)

    # Theta acceleration — 0DTE theta accelerates sharply after 2 PM
    theta = live_greeks.get("theta")
    entry_theta = entry_greeks.get("theta")
    if theta is not None and entry_theta is not None:
        # Theta gets more negative over time; ratio shows acceleration
        if entry_theta < 0 and theta < 0:
            theta_ratio = abs(theta) / abs(entry_theta) if entry_theta != 0 else 1
            if theta_ratio > 2.0:
                score += 0.35
                signals.append("theta_accelerating")
                details.append(f"Theta {theta_ratio:.1f}x worse than entry")
            elif theta_ratio > 1.5:
                score += 0.20
                signals.append("theta_rising")
                details.append(f"Theta {theta_ratio:.1f}x entry")

    # Theta P&L component eating profits
    theta_pnl_pct = greeks_pnl.get("theta_pnl_pct", 0) if greeks_pnl else 0
    if theta_pnl_pct < -0.05:
        score += 0.20
        signals.append("theta_bleeding")
        details.append(f"Theta P&L {theta_pnl_pct:+.1%}")

    # IV crush — current IV significantly lower than entry IV
    iv = live_greeks.get("iv")
    entry_iv = entry_greeks.get("iv")
    if iv is not None and entry_iv is not None and entry_iv > 0:
        iv_change = (iv - entry_iv) / entry_iv
        if iv_change < -0.15:  # IV dropped 15%+
            score += 0.25
            signals.append("iv_crush")
            details.append(f"IV crush {iv_change:+.1%} from entry")
        elif iv_change < -0.08:
            score += 0.10
            signals.append("iv_declining")
            details.append(f"IV declining {iv_change:+.1%}")

    # Delta erosion — option losing sensitivity (going deeper OTM)
    delta = live_greeks.get("delta")
    entry_delta = entry_greeks.get("delta")
    if delta is not None and entry_delta is not None:
        delta_ratio = abs(delta) / abs(entry_delta) if entry_delta != 0 else 1
        if delta_ratio < 0.5:  # Lost half its delta
            score += 0.20
            signals.append("delta_eroded")
            details.append(f"Delta {abs(delta):.2f} vs entry {abs(entry_delta):.2f}")

    # Vol regime — expensive options have stronger theta headwind
    if vol_regime:
        regime = vol_regime.get("vol_regime", "fair")
        if regime in ("expensive", "very_expensive"):
            bonus = 0.15 if regime == "very_expensive" else 0.08
            score += bonus
            signals.append("vol_expensive")
            ratio = vol_regime.get("iv_rv_ratio", 1.0)
            details.append(f"Options {regime} (IV/RV={ratio:.2f}) — theta headwind amplified")
        elif regime in ("cheap", "very_cheap"):
            # Cheap options = gamma tailwind, reduce greeks urgency
            reduction = 0.10 if regime == "very_cheap" else 0.05
            score = max(0, score - reduction)
            if reduction > 0:
                signals.append("vol_cheap_cushion")
                details.append(f"Options {regime} — gamma cushion")

    return ScorerResult(
        name="greeks",
        score=min(1.0, score),
        detail=" | ".join(details) if details else "Greeks stable",
        signals=signals,
    )


# ─── Scorer 3: Level Proximity ──────────────────────────────────────────────

def score_levels(position: Dict, levels: Optional[Dict],
                 gex: Optional[Dict]) -> ScorerResult:
    """
    Detect price approaching strong resistance/support levels.

    For longs: approaching resistance = urgency to take profits
    For shorts: approaching support = urgency to take profits
    """
    score = 0.0
    signals = []
    details = []

    if not levels:
        return ScorerResult("levels", 0.0, "No level data", [])

    direction = _position_direction(position)
    price = levels.get("current_price", 0)
    atr = levels.get("atr_1m", 0.10)  # Fallback to avoid division by 0

    if price <= 0 or atr <= 0:
        return ScorerResult("levels", 0.0, "No price/ATR data", [])

    # Collect obstacles in the profit direction
    obstacles: List[Tuple[str, float, float]] = []  # (name, level, distance_in_atr)

    if direction == "bullish":
        # Resistance levels above current price
        _add_obstacle(obstacles, "HOD", levels.get("hod", 0), price, atr, "above")
        _add_obstacle(obstacles, "VWAP+2σ", levels.get("vwap_upper_2", 0), price, atr, "above")
        _add_obstacle(obstacles, "VWAP+3σ", levels.get("vwap_upper_3", 0), price, atr, "above")
        _add_obstacle(obstacles, "R1", levels.get("r1", 0), price, atr, "above")
        _add_obstacle(obstacles, "R2", levels.get("r2", 0), price, atr, "above")
        _add_obstacle(obstacles, "PrevHigh", levels.get("prev_high", 0), price, atr, "above")
        _add_obstacle(obstacles, "ORB30H", levels.get("orb_30_high", 0), price, atr, "above")
        if gex:
            _add_obstacle(obstacles, "CallWall", gex.get("call_wall", 0), price, atr, "above")
    else:
        # Support levels below current price
        _add_obstacle(obstacles, "LOD", levels.get("lod", 0), price, atr, "below")
        _add_obstacle(obstacles, "VWAP-2σ", levels.get("vwap_lower_2", 0), price, atr, "below")
        _add_obstacle(obstacles, "VWAP-3σ", levels.get("vwap_lower_3", 0), price, atr, "below")
        _add_obstacle(obstacles, "S1", levels.get("s1", 0), price, atr, "below")
        _add_obstacle(obstacles, "S2", levels.get("s2", 0), price, atr, "below")
        _add_obstacle(obstacles, "PrevLow", levels.get("prev_low", 0), price, atr, "below")
        _add_obstacle(obstacles, "ORB30L", levels.get("orb_30_low", 0), price, atr, "below")
        if gex:
            _add_obstacle(obstacles, "PutWall", gex.get("put_wall", 0), price, atr, "below")

    # Score based on nearest obstacles
    if obstacles:
        obstacles.sort(key=lambda x: x[2])  # Sort by distance
        nearest_name, nearest_level, nearest_dist = obstacles[0]

        if nearest_dist < 1.0:  # Within 1 ATR — very close
            score += 0.45
            signals.append(f"at_{nearest_name.lower()}")
            details.append(f"At {nearest_name} ${nearest_level:.2f} ({nearest_dist:.1f} ATR away)")
        elif nearest_dist < 2.0:  # Within 2 ATR
            score += 0.25
            signals.append(f"near_{nearest_name.lower()}")
            details.append(f"Near {nearest_name} ${nearest_level:.2f} ({nearest_dist:.1f} ATR)")
        elif nearest_dist < 3.0:  # Within 3 ATR
            score += 0.10
            details.append(f"Approaching {nearest_name} ${nearest_level:.2f} ({nearest_dist:.1f} ATR)")

        # Multiple levels clustered = stronger resistance/support
        close_levels = [o for o in obstacles if o[2] < 2.5]
        if len(close_levels) >= 3:
            score += 0.25
            signals.append("level_cluster")
            names = ", ".join(o[0] for o in close_levels[:3])
            details.append(f"Level cluster: {names}")
        elif len(close_levels) >= 2:
            score += 0.10
            signals.append("dual_levels")

    return ScorerResult(
        name="levels",
        score=min(1.0, score),
        detail=" | ".join(details) if details else "No nearby levels",
        signals=signals,
    )


def _add_obstacle(obstacles, name, level, price, atr, side):
    """Add a level as an obstacle if it's in the profit direction."""
    if level <= 0:
        return
    if side == "above" and level > price:
        dist = (level - price) / atr
        obstacles.append((name, level, dist))
    elif side == "below" and level < price:
        dist = (price - level) / atr
        obstacles.append((name, level, dist))


# ─── Scorer 4: Session Context ──────────────────────────────────────────────

# Phase transition risk — how dangerous is holding through the next phase?
PHASE_HOLD_RISK = {
    "opening_drive":    0.10,  # Safe — high momentum
    "morning_trend":    0.15,  # Safe — established trends
    "midday_chop":      0.55,  # Dangerous — choppy, theta eating
    "afternoon_trend":  0.30,  # Moderate — less time
    "power_hour":       0.50,  # Dangerous — high vol + theta cliff
    "close_risk":       0.90,  # Critical — must be exiting
    "pre_market":       0.80,  # Should not hold
}

# Minutes warning before phase transition
PHASE_TRANSITION_WINDOW = 10  # minutes

# Approximate phase boundaries (minutes after 9:30 ET)
PHASE_BOUNDARIES = {
    "opening_drive":    30,   # 10:00 AM
    "morning_trend":    120,  # 11:30 AM
    "midday_chop":      240,  # 1:30 PM
    "afternoon_trend":  330,  # 3:00 PM
    "power_hour":       375,  # 3:45 PM
    "close_risk":       390,  # 4:00 PM
}


def score_session(position: Dict, session: Optional[Dict]) -> ScorerResult:
    """
    Score session-related exit urgency.

    Checks:
      - Current phase hold risk
      - Approaching unfavorable phase transition
      - Time remaining until close
      - Hold duration vs. expected trade lifetime
    """
    score = 0.0
    signals = []
    details = []

    if not session:
        return ScorerResult("session", 0.0, "No session data", [])

    phase = session.get("phase", "unknown")
    minutes_to_close = session.get("minutes_to_close", 999)
    session_quality = session.get("session_quality", 0.5)
    hold_minutes = position.get("hold_minutes", 0)

    # Base phase risk
    phase_risk = PHASE_HOLD_RISK.get(phase, 0.3)
    if phase_risk >= 0.5:
        score += phase_risk * 0.5  # Scale to 0-0.5 contribution
        signals.append(f"risky_phase_{phase}")
        details.append(f"{phase} phase (risk={phase_risk:.2f})")

    # Time pressure — approaching market close
    if minutes_to_close < 15:
        score += 0.40
        signals.append("close_imminent")
        details.append(f"Close in {minutes_to_close}min")
    elif minutes_to_close < 30:
        score += 0.25
        signals.append("close_approaching")
        details.append(f"Close in {minutes_to_close}min")
    elif minutes_to_close < 60:
        score += 0.10
        details.append(f"{minutes_to_close}min to close")

    # Low session quality — environment not favorable
    if session_quality < 0.3:
        score += 0.15
        signals.append("low_quality_session")
        details.append(f"Session quality {session_quality:.2f}")

    # Extended hold time — 0DTE trades shouldn't linger
    if hold_minutes > 30:
        score += 0.15
        signals.append("extended_hold")
        details.append(f"Held {hold_minutes:.0f}min")
    elif hold_minutes > 20:
        score += 0.05

    return ScorerResult(
        name="session",
        score=min(1.0, score),
        detail=" | ".join(details) if details else f"{phase} — {minutes_to_close}min left",
        signals=signals,
    )


# ─── Scorer 5: Flow Reversal ────────────────────────────────────────────────

def score_flow(position: Dict, flow: Optional[Dict]) -> ScorerResult:
    """
    Detect order flow turning against the position.

    Checks:
      - Flow imbalance opposing direction
      - Large trade bias opposing direction
      - Absorption detected against position
      - Divergence (price vs. CVD)
    """
    score = 0.0
    signals = []
    details = []

    if not flow:
        return ScorerResult("flow", 0.0, "No flow data", [])

    direction = _position_direction(position)

    # Flow imbalance opposing direction
    imbalance = flow.get("imbalance", 0.5)  # 0=sell, 1=buy, 0.5=neutral
    if direction == "bullish" and imbalance < 0.35:
        score += 0.30
        signals.append("flow_opposing")
        details.append(f"Sell imbalance {imbalance:.0%} vs long position")
    elif direction == "bearish" and imbalance > 0.65:
        score += 0.30
        signals.append("flow_opposing")
        details.append(f"Buy imbalance {imbalance:.0%} vs short position")

    # Large trade bias against position
    large_bias = flow.get("large_trade_bias", "neutral")
    large_count = flow.get("large_trade_count", 0)
    if large_count >= 2:
        if direction == "bullish" and large_bias == "sell":
            score += 0.25
            signals.append("large_blocks_opposing")
            details.append(f"{large_count} large sell blocks")
        elif direction == "bearish" and large_bias == "buy":
            score += 0.25
            signals.append("large_blocks_opposing")
            details.append(f"{large_count} large buy blocks")

    # Absorption at levels — smart money absorbing against our direction
    if flow.get("absorption_detected", False):
        abs_bias = flow.get("absorption_bias", "neutral")
        if direction == "bullish" and abs_bias == "bearish":
            score += 0.25
            signals.append("bearish_absorption")
            details.append("Bearish absorption detected")
        elif direction == "bearish" and abs_bias == "bullish":
            score += 0.25
            signals.append("bullish_absorption")
            details.append("Bullish absorption detected")

    # Price-CVD divergence against position
    divergence = flow.get("divergence", "none")
    if direction == "bullish" and divergence == "bearish":
        score += 0.20
        signals.append("bearish_divergence")
        details.append("Bearish CVD divergence — hidden selling")
    elif direction == "bearish" and divergence == "bullish":
        score += 0.20
        signals.append("bullish_divergence")
        details.append("Bullish CVD divergence — hidden buying")

    return ScorerResult(
        name="flow",
        score=min(1.0, score),
        detail=" | ".join(details) if details else "Flow aligned with position",
        signals=signals,
    )


# ─── Composite Engine ────────────────────────────────────────────────────────

class DynamicExitEngine:
    """
    Combines 5 scorers into a composite exit urgency signal.

    Usage:
        engine = DynamicExitEngine()
        urgency = engine.evaluate(position, flow, levels, session, gex)
        if urgency.force_exit:
            exit_trade(...)
        elif urgency.trailing_multiplier < 1.0:
            tighten_trailing(urgency.trailing_multiplier)
    """

    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._last_urgency: Dict[str, ExitUrgency] = {}  # trade_id → last result

    def evaluate(
        self,
        position: Dict,
        flow: Optional[Dict] = None,
        levels: Optional[Dict] = None,
        session: Optional[Dict] = None,
        gex: Optional[Dict] = None,
        breadth: Optional[Dict] = None,
        gex_regime: Optional[Dict] = None,
        vol_regime: Optional[Dict] = None,
    ) -> ExitUrgency:
        """
        Run all 5 scorers and produce a composite exit urgency.

        Args:
            position: From _compute_position() — P&L, Greeks, time, etc.
            flow: OrderFlowState.to_dict() — CVD, imbalance, absorption
            levels: MarketLevels.to_dict() — VWAP, pivots, ORB, ATR
            session: SessionContext.to_dict() — phase, quality, time to close
            gex: GEXResult.to_dict() — call wall, put wall, regime
            breadth: MarketBreadth.to_dict() — breadth score, divergence, risk appetite
            gex_regime: RegimeProfile.to_dict() — regime-aware urgency offset
            vol_regime: VolAnalysis.to_dict() — IV vs RV cheap/expensive

        Returns:
            ExitUrgency with composite score + per-scorer breakdown
        """
        # Run all scorers
        s_momentum = score_momentum(position, flow, levels, breadth)
        s_greeks = score_greeks(position, vol_regime)
        s_levels = score_levels(position, levels, gex)
        s_session = score_session(position, session)
        s_flow = score_flow(position, flow)

        scorers = [s_momentum, s_greeks, s_levels, s_session, s_flow]

        # Weighted average
        w = self.weights
        total_weight = sum(w.values())
        if total_weight <= 0:
            total_weight = 1.0

        urgency_raw = (
            w.get("momentum", 0) * s_momentum.score +
            w.get("greeks", 0) * s_greeks.score +
            w.get("levels", 0) * s_levels.score +
            w.get("session", 0) * s_session.score +
            w.get("flow", 0) * s_flow.score
        ) / total_weight

        # v9: GEX regime urgency offset
        # Positive GEX → +offset (more eager to exit, moves are capped)
        # Negative GEX → -offset (less eager, let trends develop)
        regime_offset = 0.0
        if gex_regime:
            regime_offset = gex_regime.get("exit_urgency_offset", 0.0)

        urgency = min(1.0, max(0.0, urgency_raw + regime_offset))

        # Determine action level
        pnl_pct = position.get("unrealized_pnl_pct", 0)

        if urgency > 0.80:
            level = "URGENT"
            force_exit = True
            trailing_mult = 0.0  # N/A — we're exiting
            move_to_be = False
            detail = f"URGENT EXIT — urgency {urgency:.2f}"
        elif urgency > 0.60:
            level = "WARNING"
            force_exit = False
            trailing_mult = 0.50  # Tighten trailing to 50%
            move_to_be = pnl_pct > 0.05  # Also move to BE if profitable
            detail = f"WARNING — trailing tightened 50%, urgency {urgency:.2f}"
        elif urgency > 0.40:
            level = "CAUTION"
            force_exit = False
            trailing_mult = 0.75  # Slightly tighter trailing
            move_to_be = pnl_pct > 0.05  # Move to BE if profitable
            detail = f"CAUTION — trailing tightened 75%, urgency {urgency:.2f}"
        else:
            level = "HOLD"
            force_exit = False
            trailing_mult = 1.0  # Normal trailing
            move_to_be = False
            detail = f"HOLD — urgency {urgency:.2f}"

        result = ExitUrgency(
            urgency=urgency,
            level=level,
            scorers=scorers,
            trailing_multiplier=trailing_mult,
            move_to_breakeven=move_to_be,
            force_exit=force_exit,
            detail=detail,
        )

        # Cache for dashboard display
        trade_id = position.get("trade_id", "")
        if trade_id:
            self._last_urgency[trade_id] = result

        return result

    def get_last_urgency(self, trade_id: str) -> Optional[ExitUrgency]:
        """Get most recent urgency for a trade (for dashboard display)."""
        return self._last_urgency.get(trade_id)

    def clear_trade(self, trade_id: str):
        """Remove cached urgency when trade closes."""
        self._last_urgency.pop(trade_id, None)

    def update_weights(self, new_weights: Dict[str, float]):
        """Update scorer weights (from config or ML tuning)."""
        for k, v in new_weights.items():
            if k in self.weights:
                self.weights[k] = v

    def to_dict(self) -> Dict:
        """Current state for API/dashboard."""
        return {
            "weights": self.weights,
            "active_trades": {
                tid: u.to_dict() for tid, u in self._last_urgency.items()
            },
        }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _position_direction(position: Dict) -> str:
    """Infer whether a position is bullish or bearish."""
    option_type = (position.get("option_type") or "").lower()
    right = (position.get("right") or "").upper()
    if "call" in option_type or right == "C":
        return "bullish"
    elif "put" in option_type or right == "P":
        return "bearish"
    return "neutral"


# ─── Singleton ────────────────────────────────────────────────────────────────

dynamic_exit_engine = DynamicExitEngine()
