"""
Signal Database — SQLite persistence for signals, trades, and scorecard.

Lightweight local storage. No external dependencies.
Tables:
  signals  — every signal generated (traded or not)
  trades   — only signals that were entered (with entry/exit/P&L/grade)
  daily_scorecard — end-of-day performance snapshots
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_DEFAULT_DB_PATH = os.path.join(_DB_DIR, "signals.db")
DB_PATH = os.environ.get("SIGNAL_DB_PATH", _DEFAULT_DB_PATH)
_db_initialized = False


def _connect() -> sqlite3.Connection:
    db_dir = os.path.dirname(DB_PATH) or "."
    os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(force: bool = False):
    """Create tables if they don't exist."""
    global _db_initialized
    if _db_initialized and not force:
        return

    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            symbol TEXT DEFAULT 'SPY',
            direction TEXT NOT NULL,
            confidence REAL,
            tier TEXT,
            confluence_score REAL,
            factors TEXT,
            strike REAL,
            expiry TEXT,
            entry_price REAL,
            target_price REAL,
            stop_price REAL,
            was_traded INTEGER DEFAULT 0,
            reject_reason TEXT,
            gex_regime TEXT,
            gex_net REAL
        );

        CREATE TABLE IF NOT EXISTS trades (
            id TEXT PRIMARY KEY,
            signal_id TEXT REFERENCES signals(id),
            mode TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            exit_time TEXT,
            entry_price REAL NOT NULL,
            exit_price REAL,
            quantity INTEGER DEFAULT 1,
            pnl REAL,
            pnl_pct REAL,
            max_favorable REAL DEFAULT 0,
            max_adverse REAL DEFAULT 0,
            exit_reason TEXT,
            grade TEXT,
            greeks_at_entry TEXT,
            greeks_at_exit TEXT,
            strike REAL,
            expiry TEXT,
            option_type TEXT,
            symbol TEXT DEFAULT 'SPY',
            tier TEXT DEFAULT 'HIGH'
        );

        CREATE TABLE IF NOT EXISTS daily_scorecard (
            date TEXT PRIMARY KEY,
            trades INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            gross_profit REAL DEFAULT 0,
            gross_loss REAL DEFAULT 0,
            net_pnl REAL DEFAULT 0,
            win_rate REAL DEFAULT 0,
            profit_factor REAL DEFAULT 0,
            expectancy REAL DEFAULT 0,
            max_drawdown REAL DEFAULT 0,
            avg_hold_minutes REAL DEFAULT 0,
            grade_distribution TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(timestamp);
        CREATE INDEX IF NOT EXISTS idx_trades_signal ON trades(signal_id);
        CREATE INDEX IF NOT EXISTS idx_trades_entry ON trades(entry_time);

        -- ── Option 1: Signal outcome tracking ──────────────────────────────────
        -- Records what SPY did after every non-traded signal so the WeightLearner
        -- can learn from skipped signals, not just executed trades.
        CREATE TABLE IF NOT EXISTS signal_outcomes (
            signal_id   TEXT PRIMARY KEY REFERENCES signals(id),
            direction   TEXT NOT NULL,
            spy_price_at_signal REAL NOT NULL,
            spy_price_15min     REAL,
            spy_price_30min     REAL,
            move_pct_15min      REAL,
            move_pct_30min      REAL,
            direction_correct_15 INTEGER,    -- 1=correct, 0=wrong, NULL=ambiguous/pending
            direction_correct_30 INTEGER,
            checked_15min       INTEGER DEFAULT 0,
            checked_30min       INTEGER DEFAULT 0,
            weight_adjusted     INTEGER DEFAULT 0,
            created_at          TEXT NOT NULL
        );

        -- ── Option 2: LLM verdict persistence ──────────────────────────────────
        -- Persists Claude's advisory verdicts across restarts and back-fills
        -- was_correct once the signal outcome is known.
        CREATE TABLE IF NOT EXISTS llm_verdicts (
            id                  TEXT PRIMARY KEY,
            signal_id           TEXT,
            timestamp           TEXT NOT NULL,
            signal_direction    TEXT,
            signal_tier         TEXT,
            signal_confidence   REAL,
            verdict             TEXT NOT NULL,
            verdict_confidence  REAL,
            would_block         INTEGER DEFAULT 0,
            reasoning           TEXT,
            key_factors         TEXT,
            model               TEXT,
            latency_ms          INTEGER,
            was_correct         INTEGER,    -- NULL until outcome known; 1=correct, 0=wrong
            error               TEXT
        );

        -- ── LLM exit advisories ────────────────────────────────────────────
        -- Claude's real-time exit reasoning for open positions.
        CREATE TABLE IF NOT EXISTS llm_exit_advisories (
            id                  TEXT PRIMARY KEY,
            trade_id            TEXT NOT NULL,
            timestamp           TEXT NOT NULL,
            action              TEXT NOT NULL,      -- HOLD, TIGHTEN, SCALE_OUT, EXIT
            urgency_override    REAL,               -- NULL or 0.0-1.0
            trailing_adjustment REAL,               -- NULL or 0.1-1.0
            confidence          REAL,
            key_signals         TEXT,                -- JSON array
            reasoning           TEXT,
            model               TEXT,
            latency_ms          INTEGER,
            error               TEXT,
            -- Outcome tracking: what actually happened after this advisory
            actual_exit_reason  TEXT,               -- Filled when trade closes
            actual_pnl_pct      REAL                -- Filled when trade closes
        );

        CREATE INDEX IF NOT EXISTS idx_outcomes_created ON signal_outcomes(created_at);
        CREATE INDEX IF NOT EXISTS idx_verdicts_signal  ON llm_verdicts(signal_id);
        CREATE INDEX IF NOT EXISTS idx_verdicts_ts      ON llm_verdicts(timestamp);
        CREATE INDEX IF NOT EXISTS idx_exit_adv_trade   ON llm_exit_advisories(trade_id);
        CREATE INDEX IF NOT EXISTS idx_exit_adv_ts      ON llm_exit_advisories(timestamp);
    """)

    # ── Migrations: add columns if missing (existing DBs) ────────────────────
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()]
        if "tier" not in cols:
            conn.execute("ALTER TABLE trades ADD COLUMN tier TEXT DEFAULT 'HIGH'")
            conn.commit()
    except Exception:
        pass

    try:
        sig_cols = [row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()]
        if "spy_price" not in sig_cols:
            conn.execute("ALTER TABLE signals ADD COLUMN spy_price REAL")
            conn.commit()
    except Exception:
        pass

    # Migration: partial exit support
    try:
        trade_cols = [row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()]
        if "remaining_quantity" not in trade_cols:
            conn.execute("ALTER TABLE trades ADD COLUMN remaining_quantity INTEGER")
            conn.commit()
            # Backfill: remaining_quantity = quantity for all open trades
            conn.execute("UPDATE trades SET remaining_quantity = quantity WHERE exit_time IS NULL AND remaining_quantity IS NULL")
            conn.commit()
        if "partial_exits" not in trade_cols:
            conn.execute("ALTER TABLE trades ADD COLUMN partial_exits TEXT DEFAULT '[]'")
            conn.commit()
    except Exception:
        pass

    conn.close()
    _db_initialized = True


def _get_conn() -> sqlite3.Connection:
    init_db()
    return _connect()


# ── Signals ──

def store_signal(signal: Dict) -> str:
    """Store a generated signal. Returns signal ID."""
    import uuid
    sig_id = signal.get("id") or str(uuid.uuid4())[:12]

    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO signals
        (id, timestamp, symbol, direction, confidence, tier, confluence_score,
         factors, strike, expiry, entry_price, target_price, stop_price,
         gex_regime, gex_net, spy_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sig_id,
        signal.get("timestamp", datetime.now(timezone.utc).isoformat()),
        signal.get("symbol", "SPY"),
        signal.get("signal", "NO_TRADE"),
        signal.get("confidence", 0),
        signal.get("tier", "DEVELOPING"),
        signal.get("confidence", 0),
        json.dumps(signal.get("factors", [])),
        signal.get("strike"),
        signal.get("expiry"),
        signal.get("entry_price"),
        signal.get("target_price"),
        signal.get("stop_price"),
        signal.get("gex", {}).get("regime") if signal.get("gex") else None,
        signal.get("gex", {}).get("net_gex") if signal.get("gex") else None,
        signal.get("spy_price"),
    ))
    conn.commit()
    conn.close()
    return sig_id


def mark_signal_traded(sig_id: str):
    conn = _get_conn()
    conn.execute("UPDATE signals SET was_traded = 1 WHERE id = ?", (sig_id,))
    conn.commit()
    conn.close()


def mark_signal_rejected(sig_id: str, reason: str):
    conn = _get_conn()
    conn.execute("UPDATE signals SET reject_reason = ? WHERE id = ?", (reason, sig_id))
    conn.commit()
    conn.close()


def get_recent_signals(limit: int = 50) -> List[Dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM signals ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Trades ──

def store_trade(trade: Dict) -> str:
    """Store a new trade entry. Returns trade ID."""
    import uuid
    trade_id = trade.get("id") or str(uuid.uuid4())[:12]
    qty = trade.get("quantity", 1)

    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO trades
        (id, signal_id, mode, entry_time, entry_price, quantity,
         strike, expiry, option_type, symbol, greeks_at_entry, tier,
         remaining_quantity, partial_exits)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_id,
        trade.get("signal_id"),
        trade.get("mode", "simulation"),
        trade.get("entry_time", datetime.now(timezone.utc).isoformat()),
        trade.get("entry_price", 0),
        qty,
        trade.get("strike"),
        trade.get("expiry"),
        trade.get("option_type"),
        trade.get("symbol", "SPY"),
        json.dumps(trade.get("greeks_at_entry", {})),
        trade.get("tier", "HIGH"),
        qty,  # remaining_quantity starts equal to quantity
        "[]",  # no partial exits yet
    ))
    conn.commit()
    conn.close()
    return trade_id


def record_partial_exit(trade_id: str, qty_exited: int, exit_price: float,
                        reason: str, pnl: float) -> int:
    """
    Record a partial exit: decrement remaining_quantity, append to partial_exits log.
    Returns new remaining_quantity.
    """
    conn = _get_conn()
    row = conn.execute("SELECT remaining_quantity, partial_exits FROM trades WHERE id=?",
                       (trade_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Trade {trade_id} not found")

    remaining = (row["remaining_quantity"] or row.get("quantity", 1)) - qty_exited
    remaining = max(0, remaining)

    # Append to partial_exits log
    existing = json.loads(row["partial_exits"] or "[]")
    existing.append({
        "qty": qty_exited,
        "price": round(exit_price, 2),
        "reason": reason,
        "pnl": round(pnl, 2),
        "time": datetime.now(timezone.utc).isoformat(),
    })

    conn.execute("""
        UPDATE trades SET remaining_quantity=?, partial_exits=? WHERE id=?
    """, (remaining, json.dumps(existing), trade_id))
    conn.commit()
    conn.close()

    return remaining


def close_trade(trade_id: str, exit_data: Dict):
    """Update a trade with exit information."""
    conn = _get_conn()
    conn.execute("""
        UPDATE trades SET
            exit_time = ?, exit_price = ?, pnl = ?, pnl_pct = ?,
            max_favorable = ?, max_adverse = ?, exit_reason = ?,
            grade = ?, greeks_at_exit = ?
        WHERE id = ?
    """, (
        exit_data.get("exit_time", datetime.now(timezone.utc).isoformat()),
        exit_data.get("exit_price"),
        exit_data.get("pnl"),
        exit_data.get("pnl_pct"),
        exit_data.get("max_favorable", 0),
        exit_data.get("max_adverse", 0),
        exit_data.get("exit_reason"),
        exit_data.get("grade"),
        json.dumps(exit_data.get("greeks_at_exit", {})),
        trade_id,
    ))
    conn.commit()
    conn.close()


def get_open_trades() -> List[Dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE exit_time IS NULL ORDER BY entry_time DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trade_history(limit: int = 50) -> List[Dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE exit_time IS NOT NULL ORDER BY exit_time DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_todays_trades() -> List[Dict]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM trades WHERE entry_time LIKE ? ORDER BY entry_time",
        (f"{today}%",)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Scorecard ──

def compute_scorecard(trades: Optional[List[Dict]] = None) -> Dict:
    """Compute scorecard from trades. If trades not provided, uses today's."""
    if trades is None:
        trades = get_todays_trades()

    closed = [t for t in trades if t.get("exit_time")]
    if not closed:
        return {
            "trades": 0, "wins": 0, "losses": 0,
            "gross_profit": 0, "gross_loss": 0, "net_pnl": 0,
            "win_rate": 0, "profit_factor": 0, "expectancy": 0,
            "avg_hold_minutes": 0, "grade_distribution": {},
        }

    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl") or 0) <= 0]
    gross_profit = sum(t.get("pnl", 0) for t in wins)
    gross_loss = abs(sum(t.get("pnl", 0) for t in losses))

    win_rate = len(wins) / len(closed) if closed else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
    avg_win = gross_profit / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

    # Hold time
    hold_minutes = []
    for t in closed:
        try:
            entry = datetime.fromisoformat(t["entry_time"])
            exit_ = datetime.fromisoformat(t["exit_time"])
            hold_minutes.append((exit_ - entry).total_seconds() / 60)
        except Exception:
            pass

    # Grade distribution
    grades = {}
    for t in closed:
        g = t.get("grade", "?")
        grades[g] = grades.get(g, 0) + 1

    return {
        "trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pnl": round(gross_profit - gross_loss, 2),
        "win_rate": round(win_rate * 100, 1),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "avg_hold_minutes": round(sum(hold_minutes) / len(hold_minutes), 1) if hold_minutes else 0,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "grade_distribution": grades,
    }


def store_daily_scorecard(date_str: Optional[str] = None):
    """Snapshot today's scorecard to the database."""
    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sc = compute_scorecard()
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO daily_scorecard
        (date, trades, wins, losses, gross_profit, gross_loss, net_pnl,
         win_rate, profit_factor, expectancy, avg_hold_minutes, grade_distribution)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        date_str, sc["trades"], sc["wins"], sc["losses"],
        sc["gross_profit"], sc["gross_loss"], sc["net_pnl"],
        sc["win_rate"], sc["profit_factor"], sc["expectancy"],
        sc["avg_hold_minutes"], json.dumps(sc["grade_distribution"]),
    ))
    conn.commit()
    conn.close()


def get_daily_scorecards(limit: int = 30) -> List[Dict]:
    """Get recent daily scorecards ordered by date descending."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM daily_scorecard ORDER BY date DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()

    result = []
    for row in rows:
        d = dict(row)
        # Parse grade_distribution from JSON
        if d.get("grade_distribution"):
            try:
                d["grade_distribution"] = json.loads(d["grade_distribution"])
            except Exception:
                pass
        # Approximate beat_spy: positive net_pnl is a rough proxy
        # (full SPY comparison requires stored SPY daily returns)
        d["beat_spy"] = d.get("net_pnl", 0) > 0
        result.append(d)
    return result


# ── Signal Outcomes (Option 1) ─────────────────────────────────────────────────

def create_outcome_stub(signal_id: str, direction: str, spy_price: float) -> None:
    """
    Called when a non-traded signal is generated. Creates a pending outcome row
    that the outcome tracker will fill in at the 15-min and 30-min marks.
    """
    conn = _get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO signal_outcomes
            (signal_id, direction, spy_price_at_signal, created_at)
        VALUES (?, ?, ?, ?)
    """, (signal_id, direction, spy_price, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()


def update_outcome_checkpoint(
    signal_id: str,
    checkpoint: int,           # 15 or 30
    current_spy: float,
    direction_correct: Optional[int],   # 1, 0, or None (ambiguous)
    move_pct: float,
) -> None:
    """Record SPY price at the 15-min or 30-min checkpoint."""
    conn = _get_conn()
    if checkpoint == 15:
        conn.execute("""
            UPDATE signal_outcomes SET
                spy_price_15min      = ?,
                move_pct_15min       = ?,
                direction_correct_15 = ?,
                checked_15min        = 1
            WHERE signal_id = ?
        """, (current_spy, move_pct, direction_correct, signal_id))
    else:
        conn.execute("""
            UPDATE signal_outcomes SET
                spy_price_30min      = ?,
                move_pct_30min       = ?,
                direction_correct_30 = ?,
                checked_30min        = 1
            WHERE signal_id = ?
        """, (current_spy, move_pct, direction_correct, signal_id))
    conn.commit()
    conn.close()


def mark_outcome_weight_adjusted(signal_id: str) -> None:
    conn = _get_conn()
    conn.execute(
        "UPDATE signal_outcomes SET weight_adjusted = 1 WHERE signal_id = ?",
        (signal_id,)
    )
    conn.commit()
    conn.close()


def get_pending_outcomes(max_age_hours: int = 2) -> List[Dict]:
    """
    Return outcome rows that still need a 15-min or 30-min check.
    Filters to signals created within max_age_hours (stale data is useless).
    Includes entry_price and strike for dynamic profit threshold calculation.
    """
    conn = _get_conn()
    rows = conn.execute("""
        SELECT o.*, s.factors, s.entry_price, s.strike, s.target_price, s.stop_price
        FROM signal_outcomes o
        JOIN signals s ON s.id = o.signal_id
        WHERE (o.checked_15min = 0 OR o.checked_30min = 0)
          AND o.created_at > datetime('now', ?)
        ORDER BY o.created_at ASC
    """, (f"-{max_age_hours} hours",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_outcome_stats(lookback_days: int = 30) -> Dict:
    """
    Aggregate signal outcome accuracy for the stats panel.
    Returns accuracy by tier, by direction, and factor win rates.
    """
    conn = _get_conn()

    # Overall accuracy at 30-min mark
    rows = conn.execute("""
        SELECT
            s.tier,
            s.direction,
            COUNT(*) as total,
            SUM(CASE WHEN o.direction_correct_30 = 1 THEN 1 ELSE 0 END) as correct_30,
            SUM(CASE WHEN o.direction_correct_15 = 1 THEN 1 ELSE 0 END) as correct_15,
            AVG(ABS(o.move_pct_30min)) as avg_move_30
        FROM signal_outcomes o
        JOIN signals s ON s.id = o.signal_id
        WHERE o.checked_30min = 1
          AND o.created_at > datetime('now', ?)
        GROUP BY s.tier, s.direction
    """, (f"-{lookback_days} days",)).fetchall()
    conn.close()

    by_tier: Dict[str, Dict] = {}
    for r in rows:
        d = dict(r)
        tier = d["tier"] or "UNKNOWN"
        if tier not in by_tier:
            by_tier[tier] = {"total": 0, "correct_30": 0, "correct_15": 0, "avg_move_30": 0}
        by_tier[tier]["total"] += d["total"]
        by_tier[tier]["correct_30"] += d["correct_30"] or 0
        by_tier[tier]["correct_15"] += d["correct_15"] or 0

    result = []
    for tier, vals in by_tier.items():
        total = vals["total"]
        result.append({
            "tier": tier,
            "total": total,
            "accuracy_30min": round(vals["correct_30"] / total * 100, 1) if total else 0,
            "accuracy_15min": round(vals["correct_15"] / total * 100, 1) if total else 0,
        })

    return {"by_tier": sorted(result, key=lambda x: -x["total"])}


# ── LLM Verdicts (Option 2) ────────────────────────────────────────────────────

def store_llm_verdict(verdict: Dict) -> None:
    """Persist a single LLM verdict to SQLite."""
    import json as _json
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO llm_verdicts
            (id, signal_id, timestamp, signal_direction, signal_tier,
             signal_confidence, verdict, verdict_confidence, would_block,
             reasoning, key_factors, model, latency_ms, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        verdict.get("id"),
        verdict.get("signal_id"),
        verdict.get("timestamp", datetime.now(timezone.utc).isoformat()),
        verdict.get("signal_direction"),
        verdict.get("signal_tier"),
        verdict.get("signal_confidence"),
        verdict.get("verdict"),
        verdict.get("verdict_confidence"),
        int(bool(verdict.get("would_block", False))),
        verdict.get("reasoning", "")[:500],
        _json.dumps(verdict.get("key_factors", [])),
        verdict.get("model"),
        verdict.get("latency_ms"),
        verdict.get("error"),
    ))
    conn.commit()
    conn.close()


def backfill_verdict_outcome(signal_id: str, was_correct: int) -> None:
    """
    Called by the outcome tracker once a signal's direction is confirmed.
    Marks all verdicts for that signal as correct or incorrect.
    """
    conn = _get_conn()
    conn.execute(
        "UPDATE llm_verdicts SET was_correct = ? WHERE signal_id = ?",
        (was_correct, signal_id)
    )
    conn.commit()
    conn.close()


def get_llm_verdict_stats(lookback_days: int = 30) -> Dict:
    """LLM accuracy: when Claude says REJECT, how often was the signal wrong?"""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT
            verdict,
            COUNT(*) as total,
            SUM(CASE WHEN was_correct = 1 THEN 1 ELSE 0 END) as signal_correct,
            SUM(CASE WHEN was_correct = 0 THEN 1 ELSE 0 END) as signal_wrong,
            AVG(latency_ms) as avg_latency_ms
        FROM llm_verdicts
        WHERE timestamp > datetime('now', ?)
          AND was_correct IS NOT NULL
        GROUP BY verdict
    """, (f"-{lookback_days} days",)).fetchall()
    conn.close()
    return {
        "by_verdict": [dict(r) for r in rows],
        "note": "signal_correct=1 means market moved in the signal's direction at 30min"
    }


def get_persisted_verdicts(limit: int = 100) -> List[Dict]:
    """Return recent LLM verdicts from SQLite (survives restarts)."""
    import json as _json
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM llm_verdicts ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["key_factors"] = _json.loads(d.get("key_factors") or "[]")
        except Exception:
            d["key_factors"] = []
        result.append(d)
    return result


# ── LLM Exit Advisories ───────────────────────────────────────────────────────

def store_exit_advisory(advisory: Dict) -> None:
    """Persist a single exit advisory to SQLite."""
    import json as _json
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO llm_exit_advisories
            (id, trade_id, timestamp, action, urgency_override,
             trailing_adjustment, confidence, key_signals, reasoning,
             model, latency_ms, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        advisory.get("id"),
        advisory.get("trade_id"),
        advisory.get("timestamp", datetime.now(timezone.utc).isoformat()),
        advisory.get("action"),
        advisory.get("urgency_override"),
        advisory.get("trailing_adjustment"),
        advisory.get("confidence"),
        _json.dumps(advisory.get("key_signals", [])),
        advisory.get("reasoning", "")[:500],
        advisory.get("model"),
        advisory.get("latency_ms"),
        advisory.get("error"),
    ))
    conn.commit()
    conn.close()


def backfill_exit_advisory_outcome(trade_id: str, exit_reason: str, pnl_pct: float) -> None:
    """
    Called when a trade closes. Marks all advisories for that trade
    with the actual outcome so we can measure advisory quality.
    """
    conn = _get_conn()
    conn.execute(
        "UPDATE llm_exit_advisories SET actual_exit_reason = ?, actual_pnl_pct = ? WHERE trade_id = ?",
        (exit_reason, pnl_pct, trade_id)
    )
    conn.commit()
    conn.close()


def get_exit_advisory_stats(lookback_days: int = 30) -> Dict:
    """Exit advisor accuracy: when Claude says EXIT, what was the outcome?"""
    conn = _get_conn()
    rows = conn.execute("""
        SELECT
            action,
            COUNT(*) as total,
            AVG(actual_pnl_pct) as avg_pnl_after,
            AVG(confidence) as avg_confidence,
            AVG(latency_ms) as avg_latency_ms
        FROM llm_exit_advisories
        WHERE timestamp > datetime('now', ?)
          AND actual_pnl_pct IS NOT NULL
        GROUP BY action
    """, (f"-{lookback_days} days",)).fetchall()
    conn.close()
    return {
        "by_action": [dict(r) for r in rows],
        "note": "avg_pnl_after = average final P&L% of trades where this action was the last advisory"
    }


def get_persisted_exit_advisories(trade_id: str = None, limit: int = 100) -> List[Dict]:
    """Return recent exit advisories from SQLite."""
    import json as _json
    conn = _get_conn()
    if trade_id:
        rows = conn.execute(
            "SELECT * FROM llm_exit_advisories WHERE trade_id = ? ORDER BY timestamp DESC LIMIT ?",
            (trade_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM llm_exit_advisories ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["key_signals"] = _json.loads(d.get("key_signals") or "[]")
        except Exception:
            d["key_signals"] = []
        result.append(d)
    return result
