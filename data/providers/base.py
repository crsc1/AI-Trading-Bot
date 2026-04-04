"""
Base class for all data providers.

Provides common functionality for API communication including:
- Async HTTP session management
- Rate limiting using token bucket algorithm
- Retry logic with exponential backoff
- Error handling and logging
- Cache integration
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import aiohttp

from data.cache import Cache

# Configure logger for this module
logger = logging.getLogger(__name__)


class TokenBucket:
    """
    Token bucket for rate limiting.

    Allows a maximum number of requests per time window.
    Tokens are refilled at a constant rate.
    """

    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize the token bucket.

        Args:
            capacity: Maximum tokens in the bucket
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> None:
        """
        Wait until the requested number of tokens are available.

        Args:
            tokens: Number of tokens to acquire (default: 1)
        """
        async with self.lock:
            while self.tokens < tokens:
                # Calculate how many tokens to add
                now = time.time()
                time_passed = now - self.last_refill
                tokens_to_add = time_passed * self.refill_rate

                # Refill tokens, but don't exceed capacity
                self.tokens = min(self.capacity, self.tokens + tokens_to_add)
                self.last_refill = now

                # If still not enough tokens, wait a bit
                if self.tokens < tokens:
                    await asyncio.sleep(0.1)

            # Consume the tokens
            self.tokens -= tokens


class BaseDataProvider(ABC):
    """
    Abstract base class for all data providers.

    Subclasses must implement the specific API endpoints for their data source.
    This class handles common concerns like HTTP sessions, rate limiting, and retries.
    """

    # API configuration (override in subclasses)
    BASE_URL: str = ""
    DEFAULT_RATE_LIMIT: int = 10  # requests per second
    MAX_RETRIES: int = 3
    INITIAL_BACKOFF: float = 1.0  # seconds

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit: Optional[int] = None,
        cache: Optional[Cache] = None,
        timeout: int = 30,
    ):
        """
        Initialize the data provider.

        Args:
            api_key: API key for authentication (if required)
            rate_limit: Maximum requests per second (defaults to provider's limit)
            cache: Cache instance for storing responses
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.rate_limit = rate_limit or self.DEFAULT_RATE_LIMIT
        self.cache = cache
        self.timeout = timeout

        # Create rate limiter (capacity = 1 second of requests)
        self.rate_limiter = TokenBucket(
            capacity=self.rate_limit,
            refill_rate=self.rate_limit,
        )

        # HTTP session (created lazily)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """
        Get or create an aiohttp ClientSession.

        Returns:
            Active ClientSession for making HTTP requests
        """
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with rate limiting, retries, and caching.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (appended to BASE_URL)
            params: Query parameters
            json_body: JSON body for POST requests
            use_cache: Whether to check cache first

        Returns:
            Parsed JSON response

        Raises:
            Exception: If all retries are exhausted
        """
        url = f"{self.BASE_URL}{endpoint}"

        # Check cache first
        if use_cache and self.cache:
            cache_key = f"{method}:{url}:{params}"
            cached = self.cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {url}")
                return cached

        # Apply rate limiting
        await self.rate_limiter.acquire()

        # Retry logic with exponential backoff
        backoff = self.INITIAL_BACKOFF
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                session = await self._get_session()

                async with session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as response:
                    # Handle rate limit headers
                    remaining = response.headers.get("x-ratelimit-remaining")
                    if remaining:
                        logger.debug(
                            f"{self.__class__.__name__} rate limit remaining: {remaining}"
                        )

                    # Check for HTTP errors
                    if response.status == 429:  # Too Many Requests
                        retry_after = float(response.headers.get("retry-after", backoff))
                        logger.warning(
                            f"Rate limited on {url}, waiting {retry_after}s"
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    if response.status >= 400:
                        error_text = await response.text()
                        logger.error(
                            f"HTTP {response.status} from {url}: {error_text}"
                        )
                        raise Exception(
                            f"HTTP {response.status}: {error_text[:200]}"
                        )

                    # Parse response
                    data = await response.json()

                    # Cache the result
                    if use_cache and self.cache:
                        # Cache for 60 seconds by default
                        self.cache.set(cache_key, data, ttl_seconds=60)

                    return data

            except asyncio.TimeoutError:
                last_error = "Request timeout"
                logger.warning(f"Timeout on attempt {attempt + 1} for {url}")
            except aiohttp.ClientError as e:
                last_error = str(e)
                logger.warning(f"Client error on attempt {attempt + 1}: {last_error}")
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Error on attempt {attempt + 1}: {last_error}")

            # Wait before retrying (except on last attempt)
            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(backoff)
                backoff *= 2  # Exponential backoff

        # All retries exhausted
        error_msg = f"Failed to fetch {url} after {self.MAX_RETRIES} attempts: {last_error}"
        logger.error(error_msg)
        raise Exception(error_msg)

    @abstractmethod
    async def fetch_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch latest quote for a symbol.

        Args:
            symbol: Ticker symbol (e.g., 'SPY')

        Returns:
            Quote data with price, volume, etc.
        """
        pass

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        await self.close()
