"""
Market Moments — Pattern memory for the trading brain.

Records full market snapshots at trigger points (setups, signals, flow events)
and tracks what happened 5/15/30 minutes later. Enables pattern recall:
"Last time I saw this setup in this regime, SPY moved +0.32% in 15 min."

Uses a 12-dimensional fingerprint for fast similarity search (<10ms over 1000+ rows).
"""

import json
import logging
import math
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
_DB_PATH = Path(__file__).parent.parent / "data" / "market_moments.db"


# ── Fingerprint encoding ────────────────────────────────────────────────────

def _encode_session_phase(phase: str) -> float:
    return {"opening_drive": 0.0, "morning_momentum": 0.15, "midday_chop": 0.33,
            "afternoon_trend": 0.66, "closing_drive": 0.85, "power_hour": 0.9}.get(phase, 0.5)

def _encode_cvd_trend(trend: str) -> float:
    return {"falling": 0.0, "neutral": 0.5, "rising": 1.0}.get(trend, 0.5)

def _encode_regime(regime: str) -> float:
    return {"bearish": 0.0, "neutral": 0.5, "bullish": 1.0}.get(regime, 0.5)

def _encode_vol(vol: str) -> float:
    return {"low": 0.0, "medium": 0.5, "high": 1.0}.get(vol, 0.5)

def _encode_gex(gex: str) -> float:
    return {"negative": 0.0, "neutral": 0.5, "positive": 1.0}.get(gex, 0.5)


def compute_fingerprint(
    session_phase: str = "",
    distance_from_vwap_pct: float = 0,
    imbalance: float = 0.5,
    cvd_trend: str = "neutral",
    vol_regime: str = "medium",
    gex_regime: str = "neutral",
    regime: str = "neutral",
    iv_rank: float = 50,
    sweep_count: int = 0,
    absorption_detected: bool = False,
    large_trade_count: int = 0,
    minutes_to_close: int = 195,
) -> List[float]:
    """Compute 12-dim normalized fingerprint for similarity search."""
    return [
        _encode_session_phase(session_phase),
        max(0.0, min(1.0, (distance_from_vwap_pct + 2.0) / 4.0)),  # -2% to +2% → 0-1
        max(0.0, min(1.0, imbalance)),
        _encode_cvd_trend(cvd_trend),
        _encode_vol(vol_regime),
        _encode_gex(gex_regime),
        _encode_regime(regime),
        max(0.0, min(1.0, iv_rank / 100.0)),
        min(1.0, sweep_count / 10.0),
        1.0 if absorption_detected else 0.0,
        min(1.0, large_trade_count / 20.0),
        max(0.0, min(1.0, minutes_to_close / 390.0)),
    ]


def _euclidean_distance(a: List[float], b: List[float]) -> float:
    """Euclidean distance between two fingerprints."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _similarity(a: List[float], b: List[float]) -> float:
    """Similarity score 0-1 (1 = identical)."""
    max_dist = math.sqrt(len(a))  # max possible distance in N-dim unit cube
    return 1.0 - (_euclidean_distance(a, b) / max_dist)


# ── Database ─────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS moments (
    id                      TEXT PRIMARY KEY,
    timestamp               TEXT NOT NULL,
    date                    TEXT NOT NULL,

    trigger_type            TEXT NOT NULL,
    trigger_name            TEXT,
    trigger_detail          TEXT,

    spy_price               REAL NOT NULL,
    vwap                    REAL,
    hod                     REAL,
    lod                     REAL,
    orb_high                REAL,
    orb_low                 REAL,
    distance_from_vwap_pct  REAL,

    session_phase           TEXT,
    minutes_to_close        INTEGER,

    cvd                     REAL,
    cvd_trend               TEXT,
    imbalance               REAL,
    large_trade_count       INTEGER DEFAULT 0,
    large_trade_bias        TEXT,
    absorption_detected     INTEGER DEFAULT 0,

    regime                  TEXT,
    vol_regime              TEXT,
    gex_regime              TEXT,
    iv_rank                 REAL,

    sweep_count             INTEGER DEFAULT 0,
    sweep_direction         TEXT,
    sweep_notional          REAL DEFAULT 0,

    setup_name              TEXT,
    setup_quality           REAL,
    setup_direction         TEXT,

    snapshot_json           TEXT,

    spy_5min                REAL,
    spy_15min               REAL,
    spy_30min               REAL,
    move_pct_5min           REAL,
    move_pct_15min          REAL,
    move_pct_30min          REAL,

    outcome_direction       TEXT,
    outcome_magnitude       TEXT,
    outcome_tradeable       INTEGER,

    brain_action            TEXT,
    brain_confidence        REAL,
    was_traded              INTEGER DEFAULT 0,
    trade_pnl               REAL,

    fingerprint             TEXT
);

CREATE INDEX IF NOT EXISTS idx_moments_date ON moments(date);
CREATE INDEX IF NOT EXISTS idx_moments_trigger ON moments(trigger_type, trigger_name);
CREATE INDEX IF NOT EXISTS idx_moments_regime ON moments(regime, vol_regime, session_phase);
CREATE INDEX IF NOT EXISTS idx_moments_outcome ON moments(outcome_direction, outcome_magnitude);
CREATE INDEX IF NOT EXISTS idx_moments_setup ON moments(setup_name);
CREATE INDEX IF NOT EXISTS idx_moments_ts ON moments(timestamp);

CREATE TABLE IF NOT EXISTS moment_outcomes (
    moment_id   TEXT PRIMARY KEY REFERENCES moments(id),
    checked_5min    INTEGER DEFAULT 0,
    checked_15min   INTEGER DEFAULT 0,
    checked_30min   INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS moment_correlations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    date            TEXT NOT NULL,
    pattern_key     TEXT NOT NULL,
    occurrences     INTEGER,
    wins            INTEGER,
    avg_move_pct    REAL,
    win_rate        REAL,
    avg_quality     REAL,
    sample_moment_ids TEXT,
    updated_at      TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_corr_key ON moment_correlations(pattern_key);
"""


class MarketMomentsDB:
    """Pattern memory for the trading brain."""

    def __init__(self, db_path: str = None):
        self._db_path = db_path or str(_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        # In-memory fingerprint cache for fast similarity search
        self._fp_cache: List[Tuple[str, List[float], Optional[str], Optional[float]]] = []
        # (moment_id, fingerprint, outcome_direction, move_pct_15min)
        self._load_fingerprint_cache()

    def _init_db(self):
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _load_fingerprint_cache(self, max_age_days: int = 30):
        """Load fingerprints from last N days into memory for fast search."""
        cutoff = (datetime.now(_ET) - timedelta(days=max_age_days)).strftime("%Y-%m-%d")
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    "SELECT id, fingerprint, outcome_direction, move_pct_15min "
                    "FROM moments WHERE date >= ? AND fingerprint IS NOT NULL",
                    (cutoff,),
                ).fetchall()
                self._fp_cache = []
                for r in rows:
                    try:
                        fp = [float(x) for x in r["fingerprint"].split(",")]
                        self._fp_cache.append((
                            r["id"], fp, r["outcome_direction"], r["move_pct_15min"]
                        ))
                    except (ValueError, AttributeError):
                        continue
                logger.info(f"[Moments] Loaded {len(self._fp_cache)} fingerprints into cache")
        except Exception as e:
            logger.warning(f"[Moments] Failed to load fingerprint cache: {e}")

    def record_moment(
        self,
        trigger_type: str,
        trigger_name: str = None,
        trigger_detail: str = None,
        brain_action: str = None,
        brain_confidence: float = None,
        snapshot: Any = None,
    ) -> str:
        """
        Record a market moment. Returns moment ID.
        `snapshot` is a MarketSnapshot dataclass (or dict with same fields).
        """
        moment_id = uuid.uuid4().hex[:12]
        now = datetime.now(_ET)

        # Extract fields from snapshot
        s = snapshot if snapshot else {}
        if hasattr(s, "__dict__"):
            s = s.__dict__ if not hasattr(s, "to_dict") else s.to_dict()

        price = s.get("price", 0)
        vwap = s.get("vwap", 0)
        distance_vwap = ((price - vwap) / vwap * 100) if vwap > 0 and price > 0 else 0

        # Compute fingerprint
        fp = compute_fingerprint(
            session_phase=s.get("session_phase", ""),
            distance_from_vwap_pct=distance_vwap,
            imbalance=s.get("imbalance", 0.5),
            cvd_trend=s.get("cvd_trend", "neutral"),
            vol_regime=s.get("vol_regime", "medium"),
            gex_regime=s.get("gex_regime", "neutral"),
            regime=s.get("regime", "neutral"),
            iv_rank=s.get("iv_rank", 50),
            sweep_count=s.get("sweep_count", 0),
            absorption_detected=bool(s.get("absorption_detected", False)),
            large_trade_count=s.get("large_trade_count", 0),
            minutes_to_close=s.get("minutes_to_close", 195),
        )
        fp_str = ",".join(f"{v:.4f}" for v in fp)

        # Get setup info
        setups = s.get("setups", [])
        setup_name = None
        setup_quality = None
        setup_direction = None
        if setups:
            top = setups[0] if isinstance(setups[0], dict) else {}
            setup_name = top.get("name")
            setup_quality = top.get("quality")
            setup_direction = top.get("direction")

        # Snapshot JSON (full context for CLI deep analysis)
        snapshot_json = json.dumps(s, default=str) if s else None

        try:
            with self._conn() as conn:
                conn.execute(
                    """INSERT INTO moments (
                        id, timestamp, date,
                        trigger_type, trigger_name, trigger_detail,
                        spy_price, vwap, hod, lod, orb_high, orb_low, distance_from_vwap_pct,
                        session_phase, minutes_to_close,
                        cvd, cvd_trend, imbalance, large_trade_count, large_trade_bias, absorption_detected,
                        regime, vol_regime, gex_regime, iv_rank,
                        sweep_count, sweep_direction, sweep_notional,
                        setup_name, setup_quality, setup_direction,
                        snapshot_json,
                        brain_action, brain_confidence,
                        fingerprint
                    ) VALUES (
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?,
                        ?, ?,
                        ?
                    )""",
                    (
                        moment_id, now.isoformat(), now.strftime("%Y-%m-%d"),
                        trigger_type, trigger_name, trigger_detail,
                        price, vwap, s.get("hod", 0), s.get("lod", 0),
                        s.get("orb_high", 0), s.get("orb_low", 0), distance_vwap,
                        s.get("session_phase", ""), s.get("minutes_to_close", 0),
                        s.get("cvd", 0), s.get("cvd_trend", ""), s.get("imbalance", 0.5),
                        s.get("large_trade_count", 0), s.get("large_trade_bias", ""),
                        1 if s.get("absorption_detected") else 0,
                        s.get("regime", ""), s.get("vol_regime", ""), s.get("gex_regime", ""),
                        s.get("iv_rank", 0),
                        s.get("sweep_count", 0), s.get("sweep_direction", ""),
                        s.get("sweep_notional", 0),
                        setup_name, setup_quality, setup_direction,
                        snapshot_json,
                        brain_action, brain_confidence,
                        fp_str,
                    ),
                )
                conn.execute(
                    "INSERT INTO moment_outcomes (moment_id, created_at) VALUES (?, ?)",
                    (moment_id, now.isoformat()),
                )

            # Add to fingerprint cache
            self._fp_cache.append((moment_id, fp, None, None))

            logger.debug(f"[Moments] Recorded {trigger_type}/{trigger_name} id={moment_id}")
            return moment_id

        except Exception as e:
            logger.error(f"[Moments] Failed to record moment: {e}")
            return ""

    def find_similar(
        self,
        fingerprint: List[float] = None,
        snapshot: Any = None,
        limit: int = 5,
        min_similarity: float = 0.70,
    ) -> List[Dict]:
        """
        Find similar past moments using fingerprint distance.
        Returns moments with outcomes, sorted by similarity.
        Uses in-memory cache. <10ms for 1000+ rows.
        """
        if fingerprint is None and snapshot is not None:
            s = snapshot.__dict__ if hasattr(snapshot, "__dict__") else snapshot
            price = s.get("price", 0)
            vwap = s.get("vwap", 0)
            distance_vwap = ((price - vwap) / vwap * 100) if vwap > 0 and price > 0 else 0
            fingerprint = compute_fingerprint(
                session_phase=s.get("session_phase", ""),
                distance_from_vwap_pct=distance_vwap,
                imbalance=s.get("imbalance", 0.5),
                cvd_trend=s.get("cvd_trend", "neutral"),
                vol_regime=s.get("vol_regime", "medium"),
                gex_regime=s.get("gex_regime", "neutral"),
                regime=s.get("regime", "neutral"),
                iv_rank=s.get("iv_rank", 50),
                sweep_count=s.get("sweep_count", 0),
                absorption_detected=bool(s.get("absorption_detected", False)),
                large_trade_count=s.get("large_trade_count", 0),
                minutes_to_close=s.get("minutes_to_close", 195),
            )

        if not fingerprint or not self._fp_cache:
            return []

        # Compute similarities against cache
        scored = []
        for mid, fp, outcome_dir, move_pct in self._fp_cache:
            sim = _similarity(fingerprint, fp)
            if sim >= min_similarity:
                scored.append((mid, sim, outcome_dir, move_pct))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:limit]

        if not top:
            return []

        # Fetch full moment data for top matches
        ids = [t[0] for t in top]
        sim_map = {t[0]: t[1] for t in top}

        try:
            with self._conn() as conn:
                placeholders = ",".join("?" for _ in ids)
                rows = conn.execute(
                    f"SELECT * FROM moments WHERE id IN ({placeholders})", ids
                ).fetchall()

                results = []
                for r in rows:
                    d = dict(r)
                    d["similarity"] = round(sim_map.get(r["id"], 0), 3)
                    d.pop("snapshot_json", None)  # Don't return blob in fast path
                    results.append(d)

                results.sort(key=lambda x: x["similarity"], reverse=True)
                return results
        except Exception as e:
            logger.error(f"[Moments] find_similar query failed: {e}")
            return []

    def get_pattern_edge(
        self,
        setup_name: str = None,
        regime: str = None,
        session_phase: str = None,
    ) -> Optional[Dict]:
        """
        Get pre-computed edge for a pattern combination.
        Returns {win_rate, avg_move, sample_size, confidence_adjustment}.
        Fast indexed lookup (<2ms).
        """
        parts = [setup_name or "any", regime or "any", session_phase or "any"]
        pattern_key = "+".join(parts)

        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT * FROM moment_correlations WHERE pattern_key = ?",
                    (pattern_key,),
                ).fetchone()
                if row and row["occurrences"] >= 5:
                    wr = row["win_rate"]
                    return {
                        "pattern_key": row["pattern_key"],
                        "win_rate": round(wr, 3),
                        "avg_move_pct": round(row["avg_move_pct"], 4),
                        "sample_size": row["occurrences"],
                        # Adjust confidence: above 50% = positive, below = negative
                        "confidence_adjustment": round((wr - 0.50) * 0.20, 3),
                    }
        except Exception as e:
            logger.debug(f"[Moments] get_pattern_edge error: {e}")
        return None

    def get_pending_outcomes(self, max_age_hours: int = 1) -> List[Dict]:
        """Get moments that need outcome checking."""
        cutoff = (datetime.now(_ET) - timedelta(hours=max_age_hours)).isoformat()
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT m.id, m.timestamp, m.spy_price,
                              o.checked_5min, o.checked_15min, o.checked_30min
                       FROM moments m
                       JOIN moment_outcomes o ON o.moment_id = m.id
                       WHERE o.created_at >= ?
                         AND (o.checked_5min = 0 OR o.checked_15min = 0 OR o.checked_30min = 0)
                       ORDER BY m.timestamp""",
                    (cutoff,),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Moments] get_pending_outcomes error: {e}")
            return []

    def update_outcome(
        self,
        moment_id: str,
        checkpoint: str,
        spy_price_now: float,
    ):
        """
        Fill in outcome for a moment at a checkpoint (5min, 15min, 30min).
        """
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT spy_price FROM moments WHERE id = ?", (moment_id,)
                ).fetchone()
                if not row:
                    return

                entry_price = row["spy_price"]
                if entry_price <= 0:
                    return

                move_pct = ((spy_price_now - entry_price) / entry_price) * 100

                if checkpoint == "5min":
                    conn.execute(
                        "UPDATE moments SET spy_5min = ?, move_pct_5min = ? WHERE id = ?",
                        (spy_price_now, move_pct, moment_id),
                    )
                    conn.execute(
                        "UPDATE moment_outcomes SET checked_5min = 1 WHERE moment_id = ?",
                        (moment_id,),
                    )
                elif checkpoint == "15min":
                    # Classify outcome at 15 min
                    if move_pct > 0.15:
                        direction = "up"
                    elif move_pct < -0.15:
                        direction = "down"
                    else:
                        direction = "flat"

                    abs_move = abs(move_pct)
                    if abs_move > 0.40:
                        magnitude = "large"
                    elif abs_move > 0.15:
                        magnitude = "medium"
                    else:
                        magnitude = "small"

                    tradeable = 1 if abs_move > 0.20 else 0

                    conn.execute(
                        """UPDATE moments SET
                            spy_15min = ?, move_pct_15min = ?,
                            outcome_direction = ?, outcome_magnitude = ?,
                            outcome_tradeable = ?
                           WHERE id = ?""",
                        (spy_price_now, move_pct, direction, magnitude, tradeable, moment_id),
                    )
                    conn.execute(
                        "UPDATE moment_outcomes SET checked_15min = 1 WHERE moment_id = ?",
                        (moment_id,),
                    )

                    # Update fingerprint cache with outcome
                    for i, (mid, fp, _, _) in enumerate(self._fp_cache):
                        if mid == moment_id:
                            self._fp_cache[i] = (mid, fp, direction, move_pct)
                            break

                elif checkpoint == "30min":
                    conn.execute(
                        "UPDATE moments SET spy_30min = ?, move_pct_30min = ? WHERE id = ?",
                        (spy_price_now, move_pct, moment_id),
                    )
                    conn.execute(
                        "UPDATE moment_outcomes SET checked_30min = 1 WHERE moment_id = ?",
                        (moment_id,),
                    )

        except Exception as e:
            logger.error(f"[Moments] update_outcome error: {e}")

    def get_recent(self, limit: int = 20) -> List[Dict]:
        """Return recent moments for the frontend feed."""
        try:
            with self._conn() as conn:
                rows = conn.execute(
                    """SELECT id, timestamp, trigger_type, trigger_name, trigger_detail,
                              spy_price, session_phase, regime, setup_name, setup_quality,
                              outcome_direction, outcome_magnitude, move_pct_15min,
                              brain_action, brain_confidence, was_traded, trade_pnl
                       FROM moments ORDER BY timestamp DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[Moments] get_recent error: {e}")
            return []

    def get_stats(self) -> Dict:
        """Return summary stats for the moments DB."""
        try:
            with self._conn() as conn:
                total = conn.execute("SELECT COUNT(*) FROM moments").fetchone()[0]
                with_outcomes = conn.execute(
                    "SELECT COUNT(*) FROM moments WHERE outcome_direction IS NOT NULL"
                ).fetchone()[0]
                today = datetime.now(_ET).strftime("%Y-%m-%d")
                today_count = conn.execute(
                    "SELECT COUNT(*) FROM moments WHERE date = ?", (today,)
                ).fetchone()[0]
                return {
                    "total_moments": total,
                    "with_outcomes": with_outcomes,
                    "today": today_count,
                    "cache_size": len(self._fp_cache),
                }
        except Exception:
            return {"total_moments": 0, "with_outcomes": 0, "today": 0, "cache_size": 0}


# ── Singleton ────────────────────────────────────────────────────────────────
moments_db = MarketMomentsDB()
