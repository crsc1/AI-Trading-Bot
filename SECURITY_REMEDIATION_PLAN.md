# Security Remediation Plan
**AI Trading Bot Security Fixes**
**Status:** Action items for deployment safety

---

## CRITICAL SECURITY FIXES (Implement Before Any Live Trading)

### 1. API Key Exposure

**Current Status:** CRITICAL ⚠️
- File: `.env` lines 5-6 contain plaintext Alpaca credentials
- Risk: If code is ever shared or repo is compromised, keys grant full trading access

**Fix (5 minutes):**
```bash
# 1. Revoke keys immediately in Alpaca dashboard
# https://app.alpaca.markets/settings/developer (click "Deactivate")

# 2. Generate new keys (same dashboard)

# 3. Update .env with new credentials
ALPACA_API_KEY=<NEW_KEY>
ALPACA_SECRET_KEY=<NEW_SECRET>

# 4. Verify .gitignore includes .env (already done)
# $ cat .gitignore | grep env
# .env ✓

# 5. NEVER commit .env — use environment variable injection in production
```

**Production Pattern (AWS Lambda / Deployment):**
```python
# ✓ CORRECT: Read from environment only
ALPACA_KEY = os.environ["ALPACA_API_KEY"]  # Fails loudly if not set
ALPACA_SECRET = os.environ["ALPACA_SECRET_KEY"]

# ✗ WRONG: Never do this
ALPACA_KEY = os.environ.get("ALPACA_API_KEY", "default_key")  # Silent fallback
```

---

### 2. CORS Misconfiguration

**Current Status:** CRITICAL ⚠️
- File: `dashboard/app.py` lines 55-61
- Risk: Wildcard origins + credentials = XSS vulnerability

**Fix:**

**File:** `dashboard/app.py`

**Before:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**After (Development):**
```python
import os

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

if os.getenv("ENV") == "production":
    # Production: only your domain
    ALLOWED_ORIGINS = [
        "https://yourdomain.com",
        "https://www.yourdomain.com",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # Not "*"
    allow_headers=["Content-Type", "Authorization"],  # Explicit
    allow_credentials=False,  # Only True if you need cookies
    max_age=3600,  # Cache preflight for 1 hour
)
```

---

### 3. WebSocket Authentication

**Current Status:** CRITICAL ⚠️
- File: `dashboard/app.py` lines 95-109
- Risk: Any client can connect to real-time signal stream

**Fix:**

**File:** `dashboard/app.py`

**Before:**
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    ...
```

**After:**
```python
import os
import secrets
import hmac

# Simple token store (in production, use JWT with RS256)
VALID_WS_TOKENS = {
    os.getenv("WS_TOKEN_DASHBOARD", "dev-token-1"),
    os.getenv("WS_TOKEN_METRICS", "dev-token-2"),
}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """WebSocket endpoint with authentication."""
    if token not in VALID_WS_TOKENS:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received (authenticated): {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
```

**Better (Production with JWT):**
```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"

def create_ws_token(user_id: str) -> str:
    """Generate JWT token for WebSocket auth."""
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_ws_token(token: str) -> dict:
    """Verify and decode JWT token."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    """WebSocket with JWT authentication."""
    payload = verify_ws_token(token)
    if not payload:
        await websocket.close(code=1008, reason="Unauthorized")
        return

    websocket.scope["user_id"] = payload["user_id"]
    await manager.connect(websocket)
    ...
```

**Client Usage:**
```javascript
// Get token from server
const response = await fetch('/api/ws-token', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${user_token}` }
});
const { ws_token } = await response.json();

// Connect with token
const ws = new WebSocket(`wss://yourdomain.com/ws?token=${ws_token}`);
```

---

### 4. REST Endpoint Input Validation

**Current Status:** HIGH ⚠️
- Files: `dashboard/api_routes.py`, `dashboard/orderflow_api.py`
- Risk: Unvalidated symbol parameters could cause Alpaca API errors or potential injection

**Fix:**

**File:** `dashboard/validators.py` (NEW)
```python
"""Input validation helpers."""
import re
from typing import Optional
from fastapi import HTTPException

VALID_SYMBOLS = {
    "SPY", "SPX", "QQQ", "IWM", "DIA",  # Major indices
    "AAPL", "MSFT", "GOOGL", "TSLA", "META",  # Major stocks
}

VALID_EXPIRY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")  # YYYY-MM-DD
VALID_SYMBOL_PATTERN = re.compile(r"^[A-Z]{1,5}$")

def validate_symbol(symbol: str) -> str:
    """Validate stock symbol."""
    if not VALID_SYMBOL_PATTERN.match(symbol):
        raise HTTPException(400, f"Invalid symbol: {symbol}")
    if symbol not in VALID_SYMBOLS:
        raise HTTPException(400, f"Symbol {symbol} not supported")
    return symbol

def validate_date(date_str: str) -> str:
    """Validate YYYY-MM-DD date format."""
    if not VALID_EXPIRY_PATTERN.match(date_str):
        raise HTTPException(400, f"Invalid date: {date_str}")
    return date_str

def validate_limit(limit: int, max_limit: int = 10000) -> int:
    """Validate query limit."""
    if not 1 <= limit <= max_limit:
        raise HTTPException(400, f"Limit must be 1-{max_limit}, got {limit}")
    return limit
```

**File:** `dashboard/api_routes.py` (UPDATE)
```python
from dashboard.validators import validate_symbol, validate_date, validate_limit

@router.get("/market")
async def get_market_snapshot(symbol: str = Query("SPY")):
    symbol = validate_symbol(symbol)  # ← Add this
    ...

@router.get("/quote")
async def get_live_quote(symbol: str = Query("SPY"), feed: str = Query("sip")):
    symbol = validate_symbol(symbol)  # ← Add this
    if feed not in ("sip", "iex"):
        raise HTTPException(400, "feed must be 'sip' or 'iex'")
    ...
```

**File:** `dashboard/orderflow_api.py` (UPDATE)
```python
from dashboard.validators import validate_symbol, validate_date, validate_limit

@router.get("/clouds")
async def get_volume_clouds(
    symbol: str = Query("SPY"),
    bar_minutes: int = Query(5, ge=1, le=60),
    date: Optional[str] = Query(None),
    min_volume: int = Query(0, ge=0),
    feed: str = Query("sip"),
):
    symbol = validate_symbol(symbol)  # ← Add this
    if date:
        date = validate_date(date)  # ← Add this
    if feed not in ("sip", "iex"):
        raise HTTPException(400, "feed must be 'sip' or 'iex'")
    ...
```

---

### 5. Rate Limiting

**Current Status:** HIGH ⚠️
- No rate limiting on public endpoints
- Risk: Brute force, DDoS, Alpaca quota exhaustion

**Fix:**

**Install:**
```bash
pip install slowapi
```

**File:** `dashboard/app.py` (ADD TO TOP)
```python
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request, exc):
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded"},
    )
```

**File:** `dashboard/api_routes.py` (UPDATE ROUTES)
```python
from slowapi import Limiter

# Configure per endpoint
@router.get("/market")
@limiter.limit("60/minute")  # 60 requests per minute
async def get_market_snapshot(symbol: str = Query("SPY")):
    ...

@router.get("/quote")
@limiter.limit("100/minute")  # More generous for quote
async def get_live_quote(symbol: str = Query("SPY")):
    ...

@router.get("/bars")
@limiter.limit("30/minute")  # Lower for heavy operations
async def get_bars(symbol: str = Query("SPY")):
    ...
```

---

### 6. Secrets Management

**Current Status:** HIGH ⚠️
- .env file with plaintext secrets
- Risk: Secrets in logs, backups, process listings

**Fix (Choose One):**

**Option A: AWS Secrets Manager (Recommended for Production)**
```python
import boto3
import json

def get_secrets():
    """Fetch secrets from AWS Secrets Manager."""
    client = boto3.client('secretsmanager', region_name='us-east-1')
    try:
        response = client.get_secret_value(SecretId='trading-bot/alpaca')
        return json.loads(response['SecretString'])
    except Exception as e:
        logger.error(f"Failed to fetch secrets: {e}")
        raise

# In app startup:
secrets = get_secrets()
ALPACA_KEY = secrets['ALPACA_API_KEY']
ALPACA_SECRET = secrets['ALPACA_SECRET_KEY']
```

**Option B: HashiCorp Vault**
```python
import hvac

vault_client = hvac.Client(url='https://vault.yourdomain.com', token=os.getenv('VAULT_TOKEN'))
secrets = vault_client.secrets.kv.read_secret_version(path='trading-bot/alpaca')
ALPACA_KEY = secrets['data']['data']['ALPACA_API_KEY']
ALPACA_SECRET = secrets['data']['data']['ALPACA_SECRET_KEY']
```

**Option C: Environment Variables (Simple, For Dev)**
```bash
# ✓ Never check .env into git
# ✓ Use shell export or docker-compose for local dev
export ALPACA_API_KEY="pk6..."
export ALPACA_SECRET_KEY="fdz..."
python -m dashboard.app
```

---

### 7. Logging Security

**Current Status:** MEDIUM ⚠️
- Debug middleware may log sensitive data
- Risk: Credentials, signal data, trade details in logs

**Fix:**

**File:** `dashboard/debug_middleware.py` (UPDATE)
```python
import logging
import re

SECRETS_PATTERN = re.compile(
    r'(api[_-]?key|secret|password|token|auth|credential)[\s=:]+[^\s,}]+',
    re.IGNORECASE
)

def redact_secrets(text: str) -> str:
    """Redact sensitive data from logs."""
    return SECRETS_PATTERN.sub(r'\1=***REDACTED***', text)

class DebugLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Don't log sensitive endpoints
            path = scope.get("path", "")
            if any(s in path for s in ["/api/auth", "/api/account", "/api/trades"]):
                # Minimal logging for sensitive paths
                logger.info(f"Request: {scope['method']} {path}")
                await self.app(scope, receive, send)
            else:
                # Standard logging for public endpoints
                body = await receive()
                body_text = body.get("body", b"").decode()
                body_text = redact_secrets(body_text)
                logger.info(f"Request body: {body_text}")
                # Continue normally...
```

---

### 8. HTTPS/TLS in Production

**Current Status:** LOCAL DEV (no HTTPS needed)
- Risk: In production, all traffic must be encrypted

**Fix:**

**For Docker/Production:**
```yaml
# docker-compose.yml
services:
  dashboard:
    image: trading-bot:latest
    ports:
      - "8443:8000"  # HTTPS
    environment:
      - SSL_CERT=/etc/ssl/certs/cert.pem
      - SSL_KEY=/etc/ssl/private/key.pem
    volumes:
      - /etc/ssl/certs:/etc/ssl/certs
      - /etc/ssl/private:/etc/ssl/private
```

**For Uvicorn (HTTPS):**
```bash
uvicorn dashboard.app:app \
  --host 0.0.0.0 \
  --port 8443 \
  --ssl-keyfile=/path/to/key.pem \
  --ssl-certfile=/path/to/cert.pem
```

**For AWS ALB/ELB:**
- Use AWS Certificate Manager (ACM) for free TLS
- Terminate SSL at load balancer
- Internal traffic between ALB and app can be unencrypted

---

## Summary of Changes

| Issue | Severity | Fix Type | Effort |
|-------|----------|----------|--------|
| API keys hardcoded | CRITICAL | Revoke + regenerate | 5 min |
| CORS misconfigured | CRITICAL | Restrict origins | 5 min |
| WebSocket no auth | CRITICAL | Add JWT validation | 20 min |
| Input validation missing | HIGH | Add validators | 15 min |
| Rate limiting absent | HIGH | Add slowapi | 10 min |
| Secrets in .env | HIGH | Use secrets manager | 30 min |
| Logging sensitive data | MEDIUM | Redact logs | 15 min |
| No HTTPS | MEDIUM | Configure TLS | 20 min (prod) |

**Total Time to Fix:** ~2 hours for development environment, ~1 day for production-ready setup

---

## Testing Security Fixes

**After implementing fixes, test:**

```bash
# 1. Verify CORS is restricted
curl -H "Origin: https://evil.com" http://localhost:8000/api/quote
# Should return 400 or be blocked

# 2. Verify WebSocket requires auth
wscat -c ws://localhost:8000/ws
# Should fail with "Unauthorized"

wscat -c "ws://localhost:8000/ws?token=valid-token"
# Should connect

# 3. Verify rate limiting
for i in {1..100}; do curl http://localhost:8000/api/quote; done
# After ~60 requests, should see 429 (Too Many Requests)

# 4. Verify secrets are not in logs
grep -r "ALPACA_API_KEY\|ALPACA_SECRET" logs/
# Should return nothing

# 5. Verify input validation
curl "http://localhost:8000/api/market?symbol=../etc/passwd"
# Should return 400 (Bad Request)
```

---

**End of Remediation Plan**
