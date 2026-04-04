"""
Tick Store — SQLite persistence for order flow ticks.

Stores trade-level data from Alpaca SIP stream for:
  - Session replay (load historical ticks on page refresh)
  - Backtesting (replay past sessions through the visualization)
  - Data analysis (volume profile, imbalance detection on historical data)

Schema optimized for time-range queries with covering index.
Uses WAL mode for concurrent reads during writes.
Auto-prunes ticks older than retention period (default 7 days).
"""

import sqlite3
import os
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TICK_DB_PATH = os.path.join(_DB_DIR, "ticks.db")

# Configuration
RETENTION_DAYS = 7           # Auto-prune ticks older than this
BATCH_SIZE = 500             # Flush to disk after this many buffered ticks
FLUSH_INTERVAL_S = 2.0       # Max seconds between flushes

# In-memory write buffer for batching inserts
_write_buffer: List[tuple] = []
_last_flush_ts: float = 0.0
_total_stored: int = 0


def _get_conn() -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and optimized pragmas."""
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(TICK_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes, still crash-safe with WAL
    conn.execute("PRAGMA cache_size=-8000")     # 8MB cache
    conn.execute("PRAGMA temp_store=MEMORY")
    return conn


def init_tick_db():
    """Create ticks table and indexes if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_ms INTEGER NOT NULL,
            symbol TEXT NOT NULL DEFAULT 'SPY',
            price REAL NOT NULL,
            size INTEGER NOT NULL DEFAULT 1,
            side TEXT NOT NULL DEFAULT 'neutral',
            exchange TEXT DEFAULT NULL,
            conditions TEXT DEFAULT NULL,
            nbbo_mid REAL DEFAULT NULL
        );

        -- Covering index for time-range + symbol queries (most common access pattern)
        CREATE INDEX IF NOT EXISTS idx_ticks_sym_ts
            ON ticks(symbol, ts_ms);

        -- Index for pruning old data
        CREATE INDEX IF NOT EXISTS idx_ticks_ts
            ON ticks(ts_ms);
    """)
    conn.close()
    logger.info(f"Tick store initialized at {TICK_DB_PATH}")


def store_tick(
    ts_ms: int,
    symbol: str,
    price: float,
    size: int,
    side: str,
    exchange: str = None,
    conditions: str = None,
    nbbo_mid: float = None,
):
    """
    Buffer a tick for batch insertion.
    Ticks are flushed to SQLite when the buffer reaches BATCH_SIZE
    or FLUSH_INTERVAL_S seconds have elapsed.
    """
    global _last_flush_ts, _total_stored

    _write_buffer.append((
        ts_ms, symbol, price, size, side,
        exchange, conditions, nbbo_mid,
    ))

    now = time.monotonic()
    if len(_write_buffer) >= BATCH_SIZE or (now - _last_flush_ts) >= FLUSH_INTERVAL_S:
        flush_ticks()


def flush_ticks():
    """Write buffered ticks to SQLite in a single transaction."""
    global _write_buffer, _last_flush_ts, _total_stored

    if not _write_buffer:
        return

    batch = _write_buffer
    _write_buffer = []
    _last_flush_ts = time.monotonic()

    try:
        conn = _get_conn()
        conn.executemany(
            """INSERT INTO ticks (ts_ms, symbol, price, size, side, exchange, conditions, nbbo_mid)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            batch,
        )
        conn.commit()
        conn.close()
        _total_stored += len(batch)
        if _total_stored % 5000 < len(batch):
            logger.info(f"Tick store: {_total_stored} ticks persisted ({len(batch)} flushed)")
    except Exception as e:
        logger.error(f"Tick store flush failed: {e}")
        # Re-buffer on failure (will retry next flush)
        _write_buffer = batch + _write_buffer


def get_ticks(
    symbol: str = "SPY",
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    limit: int = 50000,
) -> List[Dict[str, Any]]:
    """
    Retrieve ticks for a symbol within a time range.

    Args:
        symbol: Ticker symbol
        start_ms: Start timestamp in milliseconds (default: 30 min ago)
        end_ms: End timestamp in milliseconds (default: now)
        limit: Maximum ticks to return

    Returns:
        List of tick dicts sorted by timestamp ascending
    """
    if start_ms is None:
        start_ms = int((datetime.now(timezone.utc) - timedelta(minutes=30)).timestamp() * 1000)
    if end_ms is None:
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    conn = _get_conn()
    rows = conn.execute(
        """SELECT ts_ms, price, size, side, exchange, nbbo_mid
           FROM ticks
           WHERE symbol = ? AND ts_ms >= ? AND ts_ms <= ?
           ORDER BY ts_ms ASC
           LIMIT ?""",
        (symbol, start_ms, end_ms, limit),
    ).fetchall()
    conn.close()

    return [
        {
            "ts": r["ts_ms"],
            "p": r["price"],
            "s": r["size"],
            "side": r["side"],
            "x": r["exchange"],
            "mid": r["nbbo_mid"],
        }
        for r in rows
    ]


def get_tick_stats(symbol: str = "SPY") -> Dict[str, Any]:
    """Get summary statistics for stored ticks."""
    conn = _get_conn()
    row = conn.execute(
        """SELECT
             COUNT(*) as total,
             MIN(ts_ms) as first_ts,
             MAX(ts_ms) as last_ts,
             SUM(size) as total_volume,
             SUM(CASE WHEN side='buy' THEN size ELSE 0 END) as buy_volume,
             SUM(CASE WHEN side='sell' THEN size ELSE 0 END) as sell_volume
           FROM ticks WHERE symbol = ?""",
        (symbol,),
    ).fetchone()
    conn.close()

    if not row or row["total"] == 0:
        return {"total": 0, "symbol": symbol}

    return {
        "symbol": symbol,
        "total": row["total"],
        "first_ts": row["first_ts"],
        "last_ts": row["last_ts"],
        "total_volume": row["total_volume"],
        "buy_volume": row["buy_volume"],
        "sell_volume": row["sell_volume"],
        "delta": (row["buy_volume"] or 0) - (row["sell_volume"] or 0),
        "span_minutes": round(((row["last_ts"] or 0) - (row["first_ts"] or 0)) / 60000, 1),
    }


def prune_old_ticks(retention_days: int = RETENTION_DAYS) -> int:
    """Delete ticks older than retention period. Returns count deleted."""
    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(days=retention_days)).timestamp() * 1000)
    conn = _get_conn()
    cursor = conn.execute("DELETE FROM ticks WHERE ts_ms < ?", (cutoff_ms,))
    deleted = cursor.rowcount
    conn.commit()
    if deleted > 0:
        conn.execute("PRAGMA optimize")  # Reanalyze after large delete
    conn.close()
    if deleted > 0:
        logger.info(f"Tick store: pruned {deleted} ticks older than {retention_days} days")
    return deleted


def get_available_sessions(symbol: str = "SPY") -> List[Dict[str, Any]]:
    """
    List available trading sessions (grouped by date) for replay.
    Returns date, tick count, volume, and time range per session.
    """
    conn = _get_conn()
    rows = conn.execute(
        """SELECT
             DATE(ts_ms / 1000, 'unixepoch') as session_date,
             COUNT(*) as tick_count,
             SUM(size) as volume,
             MIN(ts_ms) as first_ts,
             MAX(ts_ms) as last_ts
           FROM ticks
           WHERE symbol = ?
           GROUP BY session_date
           ORDER BY session_date DESC
           LIMIT 30""",
        (symbol,),
    ).fetchall()
    conn.close()

    return [
        {
            "date": r["session_date"],
            "tick_count": r["tick_count"],
            "volume": r["volume"],
            "first_ts": r["first_ts"],
            "last_ts": r["last_ts"],
            "duration_min": round((r["last_ts"] - r["first_ts"]) / 60000, 1),
        }
        for r in rows
    ]
