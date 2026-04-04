# Signal API Documentation

Real-time AI trading signal generation from order flow analysis.

## Overview

The Signal API (`signal_api.py`) analyzes order flow data and generates qualified trading signals with dynamic risk sizing. It implements advanced order flow patterns and integrates with the FastAPI dashboard.

## Key Features

### 1. Order Flow Analysis

Detects multiple trading patterns:

- **Delta Divergence**: Mismatch between price direction and volume delta (strongest signal)
- **Volume Exhaustion**: Declining volume at new highs/lows indicates reversal
- **Absorption**: High volume at a price level with no movement (institutional accumulation/distribution)
- **Large Trade Detection**: Tracks block trades (>= 5,000 shares) and their direction

### 2. Signal Generation

Signal types:
- `BUY_CALL` - Bullish signal
- `BUY_PUT` - Bearish signal
- `NO_TRADE` - Insufficient pattern strength

Confidence scoring:
- Divergence: +35%
- Volume Exhaustion: +20%
- Absorption: +15%
- Large Trades: +15%
- Imbalance: +10%
- **Minimum required: 50%** to trigger trade signal

### 3. Dynamic Risk Sizing

Risk is scaled by confidence level:

| Confidence | Risk | Example (Account: $5,000) |
|-----------|------|--------------------------|
| < 60%     | 0.5% | $25 risk, 1 contract max |
| 60-80%    | 1.0% | $50 risk, 1 contract max |
| > 80%     | 2.0% | $100 risk, 2 contracts max |

### 4. Options Selection

For day trading on SPY weeklies:

- **Delta Target**: 0.30-0.40 (directional)
- **Expiry**: Nearest Friday (0DTE on Friday, weekly any other day)
- **Strike Selection**:
  - Calls: ~1.00 OTM above current price
  - Puts: ~1.00 OTM below current price
- **Entry**: Current ask price
- **Target**: Entry × 1.5 (50% profit)
- **Stop**: Entry × 0.5 (50% loss)

## API Endpoints

### GET /api/signals/latest

Returns the most recent AI signal.

**Response:**
```json
{
  "signal": "BUY_CALL",
  "symbol": "SPY",
  "strike": 651.0,
  "expiry": "2026-03-27",
  "entry_price": 2.50,
  "target_price": 3.75,
  "stop_price": 1.25,
  "confidence": 0.75,
  "risk_pct": 1.0,
  "reasoning": "Delta divergence: price +0.15% but CVD -2.3K. Absorption at 646.80...",
  "indicators": {
    "delta": 5400,
    "cvd_trend": "rising",
    "price_trend": "rising",
    "divergence": "bullish",
    "absorption_levels": [646.80, 647.00],
    "imbalance": 0.12,
    "large_trades": 3,
    "pcr": 1.14,
    "max_pain": 655
  },
  "risk_management": {
    "account_balance": 5000.0,
    "risk_amount": 50.0,
    "risk_pct": 1.0,
    "max_contracts": 1,
    "position_pct": 1.0
  },
  "timestamp": "2026-03-26T14:30:00+00:00"
}
```

### GET /api/signals/history

Returns signal history (last 20 signals by default).

**Query Parameters:**
- `limit` (integer, 1-100): Maximum signals to return (default: 20)

**Response:**
```json
[
  {signal1},
  {signal2},
  ...
]
```

### GET /api/signals/config

Returns current signal generation configuration.

**Response:**
```json
{
  "account_balance": 5000.0,
  "risk_config": {
    "low_confidence": 0.5,
    "medium_confidence": 1.0,
    "high_confidence": 2.0
  },
  "min_confidence_threshold": 0.5,
  "signal_history_size": 20,
  "current_signals_stored": 5,
  "default_strike_delta": "0.30-0.40",
  "default_expiry": "nearest Friday (0DTE on Friday)",
  "profit_target": "50% (entry × 1.5)",
  "stop_loss": "50% (entry × 0.5)"
}
```

### POST /api/signals/analyze

Analyze order flow data and generate signal (rarely used directly - typically called internally).

**Request Body:**
```json
{
  "trades": [
    {
      "t": "2026-03-26T14:30:00Z",
      "p": 650.00,
      "s": 1000,
      "side": "buy"
    }
  ],
  "quote": {
    "bid": 649.95,
    "ask": 650.05,
    "last": 650.00,
    "time": "2026-03-26T14:30:00Z"
  },
  "options_data": {
    "call_volume": 45000,
    "put_volume": 52000,
    "chains": [...]
  },
  "symbol": "SPY"
}
```

## OrderFlowAnalyzer Class

Core signal generation engine.

### Methods

#### analyze(trades, quote, options_data=None, account_balance=5000.0)

Main analysis method. Returns complete signal dict.

**Parameters:**
- `trades` (List[Dict]): Trade data with keys: t (timestamp), p (price), s (size), side (buy/sell)
- `quote` (Dict): Current quote with keys: bid, ask, last, time
- `options_data` (Dict): Optional options chain data
- `account_balance` (float): Account balance for risk calculation

**Returns:** Signal dict with action, confidence, strike, expiry, price targets, and reasoning

#### _detect_delta_divergence(trades, current_price)

Analyzes CVD vs price direction.

**Returns:**
```python
{
    "delta": int,              # Cumulative volume delta
    "trend": str,              # "rising", "falling", "neutral"
    "price_trend": str,        # "rising", "falling", "neutral"
    "divergence_type": str,    # "bullish", "bearish", "none"
}
```

#### _detect_volume_exhaustion(trades)

Checks if volume is declining at new highs/lows.

**Returns:**
```python
{
    "exhausted": bool,   # Is volume exhausting?
    "strength": float,   # Strength of exhaustion (0-1)
}
```

#### _detect_absorption(trades, current_price)

Identifies absorption levels (high volume, no price movement).

**Returns:** List of price levels with absorption activity

#### _detect_large_trades(trades, threshold=5000)

Finds block trades.

**Returns:** List of large trade dicts

#### _calculate_risk(confidence, account_balance)

Dynamic risk sizing based on confidence.

**Returns:**
```python
{
    "account_balance": float,
    "risk_amount": float,
    "risk_pct": float,
    "max_contracts": int,
    "position_pct": float,
}
```

## Integration with Dashboard

The Signal API is automatically integrated into the FastAPI app:

```python
# In dashboard/app.py
from dashboard.signal_api import router as signal_router
app.include_router(signal_router)  # Registers /api/signals/* endpoints
```

## WebSocket Integration

For real-time signal updates, the dashboard can broadcast signals to connected clients:

```python
from dashboard.signal_api import get_latest_stored_signal

# In WebSocket event handler
signal = get_latest_stored_signal()
if signal:
    await manager.broadcast({
        "type": "signal",
        "data": signal
    })
```

## Configuration

Key configuration values (in `signal_api.py`):

```python
ACCOUNT_BALANCE = 5000.0      # Account size for risk calculation
RISK_CONFIG = {
    "low_confidence": 0.5,    # Risk % for low confidence signals
    "medium_confidence": 1.0, # Risk % for medium confidence
    "high_confidence": 2.0,   # Risk % for high confidence
}
```

Can be overridden via environment variables or passed to analyze() method.

## Usage Examples

### Example 1: Generate Signal from Recent Trades

```python
from dashboard.signal_api import OrderFlowAnalyzer
from datetime import datetime, timezone

analyzer = OrderFlowAnalyzer("SPY")

# Get recent trades (from Alpaca API)
trades = [
    {"t": "2026-03-26T14:30:00Z", "p": 650.00, "s": 1000, "side": "buy"},
    {"t": "2026-03-26T14:30:01Z", "p": 650.01, "s": 1500, "side": "buy"},
    # ... more trades
]

# Current market quote
quote = {
    "bid": 649.95,
    "ask": 650.05,
    "last": 650.00,
    "time": datetime.now(timezone.utc).isoformat()
}

# Generate signal
signal = analyzer.analyze(trades, quote)

if signal["signal"] != "NO_TRADE":
    print(f"Generated {signal['signal']} signal with {signal['confidence']:.0%} confidence")
    print(f"Risk: ${signal['risk_management']['risk_amount']:.2f}")
    print(f"Entry: ${signal['entry_price']}, Target: ${signal['target_price']}")
```

### Example 2: Monitor Signal History

```python
from dashboard.signal_api import signal_history

# Get latest signal
latest = signal_history[-1] if signal_history else None

# Get all signals from last hour
from datetime import datetime, timedelta, timezone
one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

recent_signals = [
    s for s in signal_history
    if s["timestamp"] > one_hour_ago
]

print(f"Generated {len(recent_signals)} signals in last hour")
```

### Example 3: Use with Alpaca Trade Data

```python
from dashboard.signal_api import OrderFlowAnalyzer
from dashboard.orderflow_api import _classify_trades
import aiohttp

async def analyze_spy_trades():
    # Fetch recent trades from Alpaca
    async with aiohttp.ClientSession(headers=ALPACA_HEADERS) as session:
        async with session.get(
            f"{ALPACA_DATA_URL}/stocks/SPY/trades",
            params={"start": start_time, "end": end_time, "feed": "sip"}
        ) as resp:
            data = await resp.json()
            trades = data.get("trades", [])

    # Classify with tick rule
    classified = _classify_trades(trades)

    # Get current quote
    quote = {
        "bid": 649.95,
        "ask": 650.05,
        "last": 650.00,
    }

    # Generate signal
    analyzer = OrderFlowAnalyzer("SPY")
    signal = analyzer.analyze(classified, quote)

    return signal
```

## Error Handling

The API handles errors gracefully:

```python
signal = analyzer.analyze(invalid_trades, invalid_quote)

# Returns NO_TRADE signal with reason
if signal["signal"] == "NO_TRADE":
    print(signal["reasoning"])  # Explains why no signal was generated
```

Common reasons for NO_TRADE:
- Insufficient trade data (< 10 trades)
- Invalid quote data (missing 'last' price)
- Low confidence (< 50%)
- Conflicting order flow patterns

## Performance Considerations

- Signal generation is **O(n)** where n = number of trades (typically < 200)
- Typical execution time: **5-20ms** per signal
- Memory usage: Minimal (trades kept only for current analysis)
- Signal history: Limited to 20 signals in-memory (configurable via `deque(maxlen=20)`)

## Testing

Run the test suite:

```bash
cd dashboard
python test_signal_api.py
```

Tests cover:
- Bullish and bearish divergence detection
- Dynamic risk sizing
- Strike selection
- Option pricing estimation
- Absorption level detection
- Large trade identification
- NO_TRADE conditions
- Full workflow integration

## Troubleshooting

### Signal is always NO_TRADE

- **Cause**: Insufficient trade data or weak patterns
- **Solution**: Ensure trades list has at least 10 recent trades; check order flow quality

### Confidence too low

- **Cause**: Multiple order flow signals conflict
- **Solution**: Wait for clearer patterns; consider relaxing minimum confidence threshold

### Strike/Expiry is None

- **Cause**: Signal is NO_TRADE
- **Solution**: Check signal["reasoning"] for details

### Risk amount seems wrong

- **Cause**: Confidence level not where expected
- **Solution**: Check signal["confidence"] and compare to RISK_CONFIG tiers

## Future Enhancements

- Integrate Greeks (delta, gamma, vega) from options data
- Add IV Rank/Percentile analysis
- Implement spread strategies (iron condors, call spreads)
- Support for other symbols (SPX, QQQ)
- Machine learning confidence calibration
- Real-time PCR analysis
- Market microstructure analysis (VWAP, TWAP)

## References

- **Order Flow Analysis**: Van Tharp's order flow concepts
- **Delta Divergence**: Price vs CVD mismatch signals reversals
- **Absorption**: Institutional accumulation/distribution patterns
- **Risk Management**: Kelly Criterion, position sizing

