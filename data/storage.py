"""
SQLite database layer for the trading bot.

Handles persistent storage of:
- Trading signals
- Trade executions and results
- Historical market data
- Daily P&L
- Strategy statistics
- Bot settings

Uses aiosqlite for async database operations.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiosqlite

# Configure logger
logger = logging.getLogger(__name__)


class Database:
    """
    Async SQLite database handler for the trading bot.

    Manages tables for signals, trades, market data, P&L, and settings.
    """

    def __init__(self, db_path: str = "trading_bot.db"):
        """
        Initialize the database.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Connect to the database and create tables if needed."""
        try:
            self._connection = await aiosqlite.connect(self.db_path)
            # Enable foreign keys
            await self._connection.execute("PRAGMA foreign_keys = ON")
            await self._create_tables()
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Disconnected from database")

    async def _ensure_connection(self) -> aiosqlite.Connection:
        """Ensure there is an active database connection."""
        if not self._connection:
            await self.connect()
        return self._connection

    async def _create_tables(self) -> None:
        """Create all necessary database tables if they don't exist."""
        conn = await self._ensure_connection()

        try:
            # Table for trading signals
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    strength REAL,
                    indicators TEXT,
                    entry_price REAL,
                    target_price REAL,
                    stop_loss REAL,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for executed trades
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id INTEGER,
                    ticker TEXT NOT NULL,
                    trade_type TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    exit_price REAL,
                    exit_time TEXT,
                    quantity INTEGER NOT NULL,
                    status TEXT DEFAULT 'OPEN',
                    pnl REAL,
                    pnl_percent REAL,
                    duration_minutes INTEGER,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (signal_id) REFERENCES signals(id)
                )
            """)

            # Table for market data snapshots
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS market_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    price REAL NOT NULL,
                    bid REAL,
                    ask REAL,
                    volume INTEGER,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    vwap REAL,
                    data_source TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for daily P&L
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_pnl (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT UNIQUE NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0.0,
                    total_pnl_percent REAL DEFAULT 0.0,
                    largest_win REAL,
                    largest_loss REAL,
                    win_rate REAL,
                    avg_winning_trade REAL,
                    avg_losing_trade REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for strategy statistics
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS strategy_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_name TEXT UNIQUE NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    win_rate REAL,
                    profit_factor REAL,
                    avg_win REAL,
                    avg_loss REAL,
                    max_consecutive_wins INTEGER,
                    max_consecutive_losses INTEGER,
                    max_drawdown REAL,
                    total_profit REAL,
                    sharpe_ratio REAL,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Table for bot settings and configuration
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await conn.commit()
            logger.info("Database tables created successfully")

        except Exception as e:
            logger.error(f"Error creating tables: {e}")
            raise

    # ==================== SIGNAL METHODS ====================

    async def save_signal(
        self,
        ticker: str,
        signal_type: str,
        strength: float,
        indicators: Dict[str, Any],
        entry_price: Optional[float] = None,
        target_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Save a trading signal to the database.

        Args:
            ticker: Ticker symbol
            signal_type: Type of signal (BUY, SELL, etc.)
            strength: Signal strength (0-100)
            indicators: Dict of indicator values
            entry_price: Suggested entry price
            target_price: Profit target price
            stop_loss: Stop loss price
            notes: Additional notes

        Returns:
            ID of the inserted signal
        """
        conn = await self._ensure_connection()

        try:
            cursor = await conn.execute(
                """
                INSERT INTO signals
                (timestamp, ticker, signal_type, strength, indicators, entry_price, target_price, stop_loss, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    ticker,
                    signal_type,
                    strength,
                    json.dumps(indicators),  # Store dict as JSON
                    entry_price,
                    target_price,
                    stop_loss,
                    notes,
                ),
            )

            await conn.commit()
            signal_id = cursor.lastrowid
            logger.info(f"Saved signal {signal_id} for {ticker}")
            return signal_id

        except Exception as e:
            logger.error(f"Error saving signal: {e}")
            raise

    async def get_signals(
        self,
        ticker: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve signals from the database.

        Args:
            ticker: Optional filter by ticker
            limit: Maximum results
            offset: Number of results to skip

        Returns:
            List of signal records
        """
        conn = await self._ensure_connection()

        try:
            query = "SELECT * FROM signals"
            params: List[Any] = []

            if ticker:
                query += " WHERE ticker = ?"
                params.append(ticker)

            query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            signals = []
            for row in rows:
                signal = {
                    "id": row[0],
                    "timestamp": row[1],
                    "ticker": row[2],
                    "signal_type": row[3],
                    "strength": row[4],
                    "indicators": json.loads(row[5]) if row[5] else {},
                    "entry_price": row[6],
                    "target_price": row[7],
                    "stop_loss": row[8],
                    "notes": row[9],
                }
                signals.append(signal)

            return signals

        except Exception as e:
            logger.error(f"Error retrieving signals: {e}")
            return []

    # ==================== TRADE METHODS ====================

    async def save_trade(
        self,
        ticker: str,
        trade_type: str,
        entry_price: float,
        entry_time: str,
        quantity: int,
        signal_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Save a new trade to the database.

        Args:
            ticker: Ticker symbol
            trade_type: Type of trade (LONG, SHORT)
            entry_price: Price at entry
            entry_time: Time of entry (ISO format)
            quantity: Number of shares/contracts
            signal_id: Optional ID of signal that triggered this trade
            notes: Additional notes

        Returns:
            ID of the inserted trade
        """
        conn = await self._ensure_connection()

        try:
            cursor = await conn.execute(
                """
                INSERT INTO trades
                (signal_id, ticker, trade_type, entry_price, entry_time, quantity, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    ticker,
                    trade_type,
                    entry_price,
                    entry_time,
                    quantity,
                    "OPEN",
                    notes,
                ),
            )

            await conn.commit()
            trade_id = cursor.lastrowid
            logger.info(f"Saved trade {trade_id} for {ticker}")
            return trade_id

        except Exception as e:
            logger.error(f"Error saving trade: {e}")
            raise

    async def close_trade(
        self,
        trade_id: int,
        exit_price: float,
        exit_time: str,
    ) -> None:
        """
        Close an open trade and calculate P&L.

        Args:
            trade_id: ID of trade to close
            exit_price: Price at exit
            exit_time: Time of exit (ISO format)
        """
        conn = await self._ensure_connection()

        try:
            # Get the trade details
            cursor = await conn.execute(
                "SELECT entry_price, quantity, trade_type, entry_time FROM trades WHERE id = ?",
                (trade_id,),
            )
            row = await cursor.fetchone()

            if not row:
                logger.warning(f"Trade {trade_id} not found")
                return

            entry_price, quantity, trade_type, entry_time_str = row

            # Calculate P&L
            if trade_type == "LONG":
                pnl = (exit_price - entry_price) * quantity
            else:  # SHORT
                pnl = (entry_price - exit_price) * quantity

            pnl_percent = (pnl / (entry_price * quantity)) * 100 if entry_price != 0 else 0

            # Calculate duration
            try:
                entry_time = datetime.fromisoformat(entry_time_str)
                exit_time_dt = datetime.fromisoformat(exit_time)
                duration = int((exit_time_dt - entry_time).total_seconds() / 60)
            except Exception:
                duration = None

            # Update trade
            await conn.execute(
                """
                UPDATE trades
                SET exit_price = ?, exit_time = ?, status = ?, pnl = ?, pnl_percent = ?, duration_minutes = ?
                WHERE id = ?
                """,
                (exit_price, exit_time, "CLOSED", pnl, pnl_percent, duration, trade_id),
            )

            await conn.commit()
            logger.info(f"Closed trade {trade_id} with P&L: {pnl} ({pnl_percent:.2f}%)")

        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            raise

    async def get_trades(
        self,
        ticker: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve trades from the database.

        Args:
            ticker: Optional filter by ticker
            status: Optional filter by status (OPEN, CLOSED)
            limit: Maximum results
            offset: Number of results to skip

        Returns:
            List of trade records
        """
        conn = await self._ensure_connection()

        try:
            query = "SELECT * FROM trades"
            params: List[Any] = []
            conditions = []

            if ticker:
                conditions.append("ticker = ?")
                params.append(ticker)

            if status:
                conditions.append("status = ?")
                params.append(status)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY entry_time DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            trades = []
            for row in rows:
                trade = {
                    "id": row[0],
                    "signal_id": row[1],
                    "ticker": row[2],
                    "trade_type": row[3],
                    "entry_price": row[4],
                    "entry_time": row[5],
                    "exit_price": row[6],
                    "exit_time": row[7],
                    "quantity": row[8],
                    "status": row[9],
                    "pnl": row[10],
                    "pnl_percent": row[11],
                    "duration_minutes": row[12],
                    "notes": row[13],
                }
                trades.append(trade)

            return trades

        except Exception as e:
            logger.error(f"Error retrieving trades: {e}")
            return []

    # ==================== MARKET DATA METHODS ====================

    async def save_market_data(
        self,
        ticker: str,
        price: float,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        volume: Optional[int] = None,
        open_price: Optional[float] = None,
        high: Optional[float] = None,
        low: Optional[float] = None,
        close: Optional[float] = None,
        vwap: Optional[float] = None,
        data_source: str = "unknown",
    ) -> int:
        """
        Save a market data snapshot.

        Args:
            ticker: Ticker symbol
            price: Current price
            bid: Bid price
            ask: Ask price
            volume: Trading volume
            open_price: Opening price
            high: High price
            low: Low price
            close: Closing price
            vwap: Volume weighted average price
            data_source: Source of the data

        Returns:
            ID of the inserted record
        """
        conn = await self._ensure_connection()

        try:
            cursor = await conn.execute(
                """
                INSERT INTO market_data
                (timestamp, ticker, price, bid, ask, volume, open, high, low, close, vwap, data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(),
                    ticker,
                    price,
                    bid,
                    ask,
                    volume,
                    open_price,
                    high,
                    low,
                    close,
                    vwap,
                    data_source,
                ),
            )

            await conn.commit()
            return cursor.lastrowid

        except Exception as e:
            logger.error(f"Error saving market data: {e}")
            raise

    # ==================== P&L METHODS ====================

    async def save_daily_pnl(
        self,
        date: str,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        total_pnl: float,
        largest_win: Optional[float] = None,
        largest_loss: Optional[float] = None,
    ) -> None:
        """
        Save or update daily P&L data.

        Args:
            date: Date in YYYY-MM-DD format
            total_trades: Total number of trades
            winning_trades: Number of winning trades
            losing_trades: Number of losing trades
            total_pnl: Total profit/loss
            largest_win: Largest winning trade
            largest_loss: Largest losing trade
        """
        conn = await self._ensure_connection()

        try:
            # Calculate derived metrics
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            total_pnl_percent = total_pnl  # This would need account size to calculate properly

            avg_winning_trade = None
            avg_losing_trade = None

            # Try to calculate averages from trades
            if winning_trades > 0:
                cursor = await conn.execute(
                    """
                    SELECT AVG(pnl) FROM trades
                    WHERE DATE(exit_time) = ? AND pnl > 0
                    """,
                    (date,),
                )
                row = await cursor.fetchone()
                if row and row[0]:
                    avg_winning_trade = row[0]

            if losing_trades > 0:
                cursor = await conn.execute(
                    """
                    SELECT AVG(pnl) FROM trades
                    WHERE DATE(exit_time) = ? AND pnl < 0
                    """,
                    (date,),
                )
                row = await cursor.fetchone()
                if row and row[0]:
                    avg_losing_trade = row[0]

            # Insert or replace daily P&L
            await conn.execute(
                """
                INSERT OR REPLACE INTO daily_pnl
                (date, total_trades, winning_trades, losing_trades, total_pnl, total_pnl_percent, largest_win, largest_loss, win_rate, avg_winning_trade, avg_losing_trade)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date,
                    total_trades,
                    winning_trades,
                    losing_trades,
                    total_pnl,
                    total_pnl_percent,
                    largest_win,
                    largest_loss,
                    win_rate,
                    avg_winning_trade,
                    avg_losing_trade,
                ),
            )

            await conn.commit()
            logger.info(f"Saved daily P&L for {date}")

        except Exception as e:
            logger.error(f"Error saving daily P&L: {e}")
            raise

    async def get_daily_pnl(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve daily P&L data.

        Args:
            from_date: Optional start date (YYYY-MM-DD)
            to_date: Optional end date (YYYY-MM-DD)

        Returns:
            List of daily P&L records
        """
        conn = await self._ensure_connection()

        try:
            query = "SELECT * FROM daily_pnl"
            params: List[Any] = []
            conditions = []

            if from_date:
                conditions.append("date >= ?")
                params.append(from_date)

            if to_date:
                conditions.append("date <= ?")
                params.append(to_date)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY date DESC"

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            pnls = []
            for row in rows:
                pnl = {
                    "id": row[0],
                    "date": row[1],
                    "total_trades": row[2],
                    "winning_trades": row[3],
                    "losing_trades": row[4],
                    "total_pnl": row[5],
                    "total_pnl_percent": row[6],
                    "largest_win": row[7],
                    "largest_loss": row[8],
                    "win_rate": row[9],
                    "avg_winning_trade": row[10],
                    "avg_losing_trade": row[11],
                }
                pnls.append(pnl)

            return pnls

        except Exception as e:
            logger.error(f"Error retrieving daily P&L: {e}")
            return []

    # ==================== SETTINGS METHODS ====================

    async def save_setting(
        self,
        key: str,
        value: str,
        description: Optional[str] = None,
    ) -> None:
        """
        Save or update a settings key.

        Args:
            key: Settings key
            value: Settings value
            description: Optional description
        """
        conn = await self._ensure_connection()

        try:
            await conn.execute(
                """
                INSERT OR REPLACE INTO settings (key, value, description)
                VALUES (?, ?, ?)
                """,
                (key, value, description),
            )

            await conn.commit()

        except Exception as e:
            logger.error(f"Error saving setting {key}: {e}")
            raise

    async def get_setting(self, key: str) -> Optional[str]:
        """
        Retrieve a settings value.

        Args:
            key: Settings key

        Returns:
            Settings value or None if not found
        """
        conn = await self._ensure_connection()

        try:
            cursor = await conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            )

            row = await cursor.fetchone()
            return row[0] if row else None

        except Exception as e:
            logger.error(f"Error retrieving setting {key}: {e}")
            return None

    async def __aenter__(self):
        """Context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.disconnect()
