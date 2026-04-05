"""
Flow Toxicity (VPIN) — Volume-Synchronized Probability of Informed Trading.

VPIN measures the probability that informed traders are present in the order flow.
High VPIN = information asymmetry = expect large directional move.

Academic basis:
  - Predicted the 2010 Flash Crash >1 hour before it happened
  - Works best during elevated volatility regimes
  - Published by Easley, Lopez de Prado, and O'Hara (2012)

Algorithm:
  1. Divide trade volume into equal-sized "buckets" (volume bars, not time bars)
  2. Classify each trade as buy-initiated or sell-initiated (Lee-Ready algorithm)
  3. VPIN = moving average of |buy_volume - sell_volume| / total_volume
  4. High VPIN (>0.7) = high toxicity = informed traders active

For SPY 0DTE:
  - Normal VPIN: 0.2-0.4 (balanced flow)
  - Elevated VPIN: 0.5-0.6 (some informed activity)
  - High VPIN: 0.7+ (strong informed trading — expect big move)
  - When VPIN aligns with our signal direction → higher conviction
  - When VPIN is high but direction unclear → reduce size, wait for clarity

Data: Computed from trade data we already receive (Alpaca trades + ThetaData).
"""

import logging
from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# VPIN parameters
BUCKET_SIZE = 1000            # Volume per bucket (shares for equity, contracts for options)
NUM_BUCKETS = 50              # Rolling window of buckets for VPIN calculation
VPIN_HIGH_THRESHOLD = 0.70    # Above this = high toxicity
VPIN_ELEVATED_THRESHOLD = 0.50


@dataclass
class VPINState:
    """Current VPIN (flow toxicity) state."""

    vpin: float = 0.0               # Current VPIN value (0-1)
    toxicity_level: str = "normal"  # "normal", "elevated", "high"
    buy_volume: float = 0.0         # Recent classified buy volume
    sell_volume: float = 0.0        # Recent classified sell volume
    total_volume: float = 0.0       # Total classified volume
    bucket_count: int = 0           # Buckets filled so far
    imbalance_direction: str = "neutral"  # "buy_heavy", "sell_heavy", "neutral"
    imbalance_ratio: float = 0.0    # Buy/Sell ratio (>1 = buy heavy)

    def to_dict(self) -> Dict:
        return {
            "vpin": round(self.vpin, 4),
            "toxicity_level": self.toxicity_level,
            "buy_volume": round(self.buy_volume, 0),
            "sell_volume": round(self.sell_volume, 0),
            "total_volume": round(self.total_volume, 0),
            "bucket_count": self.bucket_count,
            "imbalance_direction": self.imbalance_direction,
            "imbalance_ratio": round(self.imbalance_ratio, 3),
        }


class VPINCalculator:
    """
    Rolling VPIN calculator using volume-bucketed trade classification.

    Usage:
        calculator = VPINCalculator()
        for trade in trades:
            calculator.add_trade(trade)
        state = calculator.get_state()
    """

    def __init__(
        self,
        bucket_size: int = BUCKET_SIZE,
        num_buckets: int = NUM_BUCKETS,
    ):
        self.bucket_size = bucket_size
        self.num_buckets = num_buckets

        # Current bucket accumulation
        self._current_buy_vol = 0.0
        self._current_sell_vol = 0.0
        self._current_total_vol = 0.0

        # Completed bucket history
        self._bucket_imbalances: deque = deque(maxlen=num_buckets)

        # Running totals
        self._total_buy = 0.0
        self._total_sell = 0.0

        # Last known bid/ask for Lee-Ready classification
        self._last_bid = 0.0
        self._last_ask = 0.0
        self._last_mid = 0.0

    def update_quote(self, bid: float, ask: float):
        """Update the current bid/ask for trade classification."""
        if bid > 0 and ask > 0:
            self._last_bid = bid
            self._last_ask = ask
            self._last_mid = (bid + ask) / 2

    def add_trade(self, price: float, size: float, bid: float = 0, ask: float = 0):
        """
        Add a single trade to the VPIN calculation.

        Uses Lee-Ready algorithm to classify:
          - Trade at ask price → buy-initiated (informed buying)
          - Trade at bid price → sell-initiated (informed selling)
          - Trade at mid → split 50/50
        """
        if size <= 0:
            return

        # Update quote if provided
        if bid > 0 and ask > 0:
            self.update_quote(bid, ask)

        # Classify using Lee-Ready
        buy_pct = self._classify_trade(price)
        buy_vol = size * buy_pct
        sell_vol = size * (1 - buy_pct)

        self._current_buy_vol += buy_vol
        self._current_sell_vol += sell_vol
        self._current_total_vol += size

        # Check if bucket is full
        while self._current_total_vol >= self.bucket_size:
            # Finalize this bucket
            overflow = self._current_total_vol - self.bucket_size

            # Proportionally split the overflow
            if self._current_total_vol > 0:
                overflow_ratio = overflow / self._current_total_vol
            else:
                overflow_ratio = 0

            bucket_buy = self._current_buy_vol * (1 - overflow_ratio)
            bucket_sell = self._current_sell_vol * (1 - overflow_ratio)

            # Store bucket imbalance
            imbalance = abs(bucket_buy - bucket_sell)
            self._bucket_imbalances.append(imbalance)

            self._total_buy += bucket_buy
            self._total_sell += bucket_sell

            # Carry overflow to next bucket
            self._current_buy_vol = self._current_buy_vol * overflow_ratio
            self._current_sell_vol = self._current_sell_vol * overflow_ratio
            self._current_total_vol = overflow

    def _classify_trade(self, price: float) -> float:
        """
        Lee-Ready trade classification.

        Returns: probability this trade is buy-initiated (0.0 to 1.0)
        """
        if self._last_mid <= 0 or price <= 0:
            return 0.5  # Unknown → split

        spread = self._last_ask - self._last_bid

        if spread <= 0:
            return 0.5

        if price >= self._last_ask:
            return 1.0  # At ask → buy
        elif price <= self._last_bid:
            return 0.0  # At bid → sell
        else:
            # Between bid and ask → linear interpolation
            return (price - self._last_bid) / spread

    def get_state(self) -> VPINState:
        """Get current VPIN state."""
        state = VPINState()

        n = len(self._bucket_imbalances)
        state.bucket_count = n

        if n < 5:
            # Not enough data
            state.vpin = 0.0
            state.toxicity_level = "normal"
            return state

        # VPIN = mean(|buy_vol - sell_vol|) / bucket_size
        total_imbalance = sum(self._bucket_imbalances)
        state.vpin = total_imbalance / (n * self.bucket_size) if n > 0 else 0

        # Classify toxicity
        if state.vpin >= VPIN_HIGH_THRESHOLD:
            state.toxicity_level = "high"
        elif state.vpin >= VPIN_ELEVATED_THRESHOLD:
            state.toxicity_level = "elevated"
        else:
            state.toxicity_level = "normal"

        # Volume breakdown
        state.buy_volume = self._total_buy + self._current_buy_vol
        state.sell_volume = self._total_sell + self._current_sell_vol
        state.total_volume = state.buy_volume + state.sell_volume

        # Imbalance direction
        if state.buy_volume > 0 and state.sell_volume > 0:
            state.imbalance_ratio = state.buy_volume / state.sell_volume
            if state.imbalance_ratio > 1.3:
                state.imbalance_direction = "buy_heavy"
            elif state.imbalance_ratio < 0.7:
                state.imbalance_direction = "sell_heavy"
            else:
                state.imbalance_direction = "neutral"

        return state

    def reset(self):
        """Reset calculator state (e.g., at start of new trading day)."""
        self._current_buy_vol = 0.0
        self._current_sell_vol = 0.0
        self._current_total_vol = 0.0
        self._bucket_imbalances.clear()
        self._total_buy = 0.0
        self._total_sell = 0.0


def compute_vpin_from_trades(
    trades: List[Dict],
    bucket_size: int = BUCKET_SIZE,
) -> VPINState:
    """
    Compute VPIN from a batch of trade data.

    Convenience function — creates a calculator, feeds all trades,
    and returns the final state.

    Args:
        trades: List of trade dicts with keys: price, size (or qty),
                and optionally bid, ask
        bucket_size: Volume per bucket

    Returns:
        VPINState with current VPIN value
    """
    calc = VPINCalculator(bucket_size=bucket_size)

    for t in trades:
        price = t.get("price", 0) or t.get("p", 0)
        size = t.get("size", 0) or t.get("qty", 0) or t.get("s", 0) or t.get("volume", 0)
        bid = t.get("bid", 0) or t.get("bp", 0)
        ask = t.get("ask", 0) or t.get("ap", 0)

        if price > 0 and size > 0:
            calc.add_trade(price, size, bid, ask)

    return calc.get_state()


# ── Scoring function for confluence integration ──

def score_flow_toxicity(
    state: VPINState,
    signal_direction: str,
) -> Tuple[float, str]:
    """
    Score flow toxicity alignment with proposed trade.

    High VPIN + aligned direction → higher conviction (informed traders agree)
    High VPIN + no clear direction → reduce size (big move coming, unclear direction)
    Low VPIN → neutral (no edge from toxicity)

    Max 0.5 points.
    Returns (score, explanation)
    """
    if state.bucket_count < 5:
        return 0.0, "Insufficient data for VPIN calculation"

    is_bullish = signal_direction == "BUY_CALL"
    vpin = state.vpin

    if vpin < VPIN_ELEVATED_THRESHOLD:
        return 0.0, f"VPIN normal ({vpin:.2f}) — balanced flow"

    # Elevated or high toxicity — check if it aligns
    if state.imbalance_direction == "buy_heavy" and is_bullish:
        score = min(0.5, vpin * 0.7)
        explain = f"VPIN {vpin:.2f} ({state.toxicity_level}) — informed buying aligns"
    elif state.imbalance_direction == "sell_heavy" and not is_bullish:
        score = min(0.5, vpin * 0.7)
        explain = f"VPIN {vpin:.2f} ({state.toxicity_level}) — informed selling aligns"
    elif state.imbalance_direction == "neutral":
        score = -0.15  # Uncertainty penalty — big move coming but unclear direction
        explain = f"VPIN {vpin:.2f} ({state.toxicity_level}) — informed activity but neutral direction"
    else:
        score = -0.25  # Opposing
        explain = f"VPIN {vpin:.2f} ({state.toxicity_level}) — informed flow opposes trade"

    return round(score, 3), explain
