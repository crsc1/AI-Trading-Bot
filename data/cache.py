"""
Simple in-memory cache with TTL (Time To Live).

Provides a thread-safe cache for storing API responses with automatic expiration.
"""

import asyncio
import time
from typing import Any, Dict, Optional


class Cache:
    """
    Simple TTL-based in-memory cache.

    Stores key-value pairs with optional expiration times.
    Thread-safe using asyncio.Lock.
    """

    def __init__(self):
        """Initialize the cache."""
        # Dictionary to store cached values
        self._cache: Dict[str, Dict[str, Any]] = {}
        # Lock for thread-safe access
        self._lock = asyncio.Lock()

    async def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int = 300,
    ) -> None:
        """
        Store a value in the cache.

        Args:
            key: Cache key (should be unique)
            value: Value to cache
            ttl_seconds: Time to live in seconds (default 5 minutes)
        """
        async with self._lock:
            # Calculate expiration time (current time + TTL)
            expires_at = time.time() + ttl_seconds

            # Store value and expiration time together
            self._cache[key] = {
                "value": value,
                "expires_at": expires_at,
            }

    async def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache.

        Returns None if the key doesn't exist or has expired.

        Args:
            key: Cache key to look up

        Returns:
            Cached value if found and not expired, None otherwise
        """
        async with self._lock:
            if key not in self._cache:
                return None

            entry = self._cache[key]

            # Check if the entry has expired
            if time.time() > entry["expires_at"]:
                # Remove expired entry and return None
                del self._cache[key]
                return None

            # Return the cached value
            return entry["value"]

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self._cache.clear()

    async def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.

        Called periodically to prevent memory leaks.

        Returns:
            Number of entries removed
        """
        async with self._lock:
            current_time = time.time()
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if current_time > entry["expires_at"]
            ]

            for key in expired_keys:
                del self._cache[key]

            return len(expired_keys)

    async def size(self) -> int:
        """
        Get the current number of cache entries.

        Returns:
            Number of items in cache
        """
        async with self._lock:
            return len(self._cache)

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache size and expiration info
        """
        async with self._lock:
            current_time = time.time()
            expired_count = sum(
                1 for entry in self._cache.values()
                if current_time > entry["expires_at"]
            )

            return {
                "total_entries": len(self._cache),
                "expired_entries": expired_count,
                "active_entries": len(self._cache) - expired_count,
            }
