"""
WebSocket connection manager for real-time dashboard updates
Handles broadcasting to multiple connected clients
"""

from collections import deque
from fastapi import WebSocket
from typing import List
import asyncio
import json
import logging
from datetime import datetime
from .config import cfg

logger = logging.getLogger(__name__)

# Max recent theta trades to buffer for replay on reconnect
_THETA_TRADE_BUFFER_SIZE = 200


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts real-time updates
    to all connected dashboard clients.

    Uses an asyncio.Lock to prevent race conditions when multiple
    coroutines connect/disconnect/broadcast concurrently.
    """

    def __init__(self):
        """Initialize the connection manager"""
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
        self.heartbeat_task = None
        # Buffer recent theta trades for replay when clients reconnect
        self._theta_trade_buffer: deque = deque(maxlen=_THETA_TRADE_BUFFER_SIZE)

    async def connect(self, websocket: WebSocket):
        """
        Accept a new WebSocket connection and replay buffered theta trades.
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
            count = len(self.active_connections)
        logger.info(f"[WS] Client connected. Total: {count}")

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Dashboard connected to server",
            "timestamp": datetime.now().isoformat()
        })

        # Replay recent theta trades so reconnecting clients recover options flow
        if self._theta_trade_buffer:
            replayed = 0
            for trade in self._theta_trade_buffer:
                try:
                    await websocket.send_json(trade)
                    replayed += 1
                except Exception:
                    break
            if replayed:
                logger.info(f"[WS] Replayed {replayed} theta trades to reconnecting client")

    async def disconnect(self, websocket: WebSocket):
        """Remove a disconnected WebSocket connection."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            count = len(self.active_connections)
        logger.info(f"[WS] Client disconnected. Remaining: {count}. Theta buffer: {len(self._theta_trade_buffer)} trades")

    async def broadcast(self, message: dict):
        """
        Broadcast a message to all connected clients.
        Buffers theta_trade events for replay on reconnect.
        """
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()

        # Buffer theta trades for replay
        if message.get("type") == "theta_trade":
            self._theta_trade_buffer.append(message)

        # Snapshot connections under lock
        async with self._lock:
            if not self.active_connections:
                return
            snapshot = list(self.active_connections)

        # Send to all connected clients
        disconnected = []
        for connection in snapshot:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for connection in disconnected:
                    if connection in self.active_connections:
                        self.active_connections.remove(connection)
                count = len(self.active_connections)
            logger.warning(f"[WS] {len(disconnected)} client(s) disconnected during broadcast. Remaining: {count}")

    async def broadcast_signal(self, signal_data: dict):
        """
        Broadcast a new trading signal to all clients

        Args:
            signal_data: Trading signal dictionary containing:
                - id, symbol, direction, strike, expiry, confidence,
                - entry_price, stop_loss, target_price, reasoning
        """
        await self.broadcast({
            "type": "new_signal",
            "data": signal_data,
            "timestamp": datetime.now().isoformat()
        })

    async def broadcast_trade_execution(self, trade_data: dict):
        """
        Broadcast a trade execution update

        Args:
            trade_data: Trade dictionary containing:
                - id, symbol, direction, entry_price, entry_time, status
        """
        await self.broadcast({
            "type": "trade_executed",
            "data": trade_data,
            "timestamp": datetime.now().isoformat()
        })

    async def broadcast_price_update(self, price_data: dict):
        """
        Broadcast a market price update

        Args:
            price_data: Price dictionary containing:
                - symbol, price, change, change_percent
        """
        await self.broadcast({
            "type": "price_update",
            "data": price_data,
            "timestamp": datetime.now().isoformat()
        })

    async def broadcast_pnl_update(self, pnl_data: dict):
        """
        Broadcast a P&L update

        Args:
            pnl_data: P&L dictionary containing:
                - daily_pnl, cumulative_pnl, trade_count, win_rate
        """
        await self.broadcast({
            "type": "pnl_update",
            "data": pnl_data,
            "timestamp": datetime.now().isoformat()
        })

    async def broadcast_options_flow(self, flow_data: dict):
        """
        Broadcast new options flow data

        Args:
            flow_data: Options flow dictionary containing:
                - symbol, option_type, strike, expiry, action, volume, amount, type
        """
        await self.broadcast({
            "type": "options_flow",
            "data": flow_data,
            "timestamp": datetime.now().isoformat()
        })

    async def broadcast_status_update(self, status_data: dict):
        """
        Broadcast bot status update

        Args:
            status_data: Status dictionary containing:
                - running, mode, positions, daily_pnl, day_trades_used
        """
        await self.broadcast({
            "type": "status_update",
            "data": status_data,
            "timestamp": datetime.now().isoformat()
        })

    async def start_heartbeat(self, interval: int = None):
        """
        Start a heartbeat task that pings all clients periodically

        Args:
            interval: Seconds between heartbeats (default from config)
        """
        if interval is None:
            interval = cfg.WS_HEARTBEAT_INTERVAL
        while True:
            await asyncio.sleep(interval)
            await self.broadcast({
                "type": "heartbeat",
                "timestamp": datetime.now().isoformat()
            })

    def get_connection_count(self) -> int:
        """Get the number of active connections"""
        return len(self.active_connections)
