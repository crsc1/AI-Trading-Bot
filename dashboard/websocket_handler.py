"""
WebSocket connection manager for real-time dashboard updates
Handles broadcasting to multiple connected clients
"""

from fastapi import WebSocket
from typing import List
import asyncio
import logging
from datetime import datetime
from .config import cfg

logger = logging.getLogger(__name__)


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

    async def connect(self, websocket: WebSocket):
        """
        Accept a new WebSocket connection

        Args:
            websocket: The WebSocket connection to add
        """
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
            count = len(self.active_connections)
        logger.info(f"Client connected. Total connections: {count}")

        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "Dashboard connected to server",
            "timestamp": datetime.now().isoformat()
        })

    async def disconnect(self, websocket: WebSocket):
        """
        Remove a disconnected WebSocket connection

        Args:
            websocket: The WebSocket connection to remove
        """
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            count = len(self.active_connections)
        logger.info(f"Client disconnected. Total connections: {count}")

    async def broadcast(self, message: dict):
        """
        Broadcast a message to all connected clients

        Args:
            message: Dictionary with message data (should include 'type' field)
        """
        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now().isoformat()

        # Snapshot connections under lock to avoid mutation during iteration
        async with self._lock:
            if not self.active_connections:
                return
            snapshot = list(self.active_connections)

        # Send to all connected clients (outside lock to avoid holding it during I/O)
        disconnected = []
        for connection in snapshot:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for connection in disconnected:
                    if connection in self.active_connections:
                        self.active_connections.remove(connection)

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
