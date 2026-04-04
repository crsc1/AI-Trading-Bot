"""
Test suite for signal_api.py - OrderFlowAnalyzer and signal generation.

Demonstrates:
- Delta divergence detection
- Volume exhaustion analysis
- Absorption level identification
- Large trade detection
- Signal generation with confidence scoring
- Dynamic risk sizing
"""

import sys
from datetime import datetime, timedelta, timezone
from signal_engine import SignalEngine
from confluence import ACCOUNT_BALANCE


def create_test_trades(
    count: int = 100,
    price_trend: str = "up",
    volume_trend: str = "consistent",
) -> list:
    """
    Create synthetic trade data for testing.

    Args:
        count: Number of trades to generate
        price_trend: "up", "down", or "sideways"
        volume_trend: "increasing", "decreasing", or "consistent"

    Returns:
        List of trade dicts with t, p, s, side
    """
    trades = []
    base_price = 650.0
    base_time = datetime.now(timezone.utc)

    for i in range(count):
        # Price movement
        if price_trend == "up":
            price = base_price + (i * 0.01)
        elif price_trend == "down":
            price = base_price - (i * 0.01)
        else:  # sideways
            price = base_price + ((i % 10) - 5) * 0.005

        # Volume pattern
        if volume_trend == "increasing":
            size = 100 + (i * 10)
        elif volume_trend == "decreasing":
            size = 100 + ((count - i) * 10)
        else:  # consistent
            size = 100 + (i % 50)

        # Determine buy/sell side (add bias based on trend)
        if price_trend == "up":
            side = "buy" if (i % 3) != 0 else "sell"  # More buys
        elif price_trend == "down":
            side = "sell" if (i % 3) != 0 else "buy"  # More sells
        else:
            side = "buy" if (i % 2) == 0 else "sell"

        trade = {
            "t": (base_time + timedelta(seconds=i)).isoformat(),
            "p": round(price, 2),
            "s": int(size),
            "side": side,
        }
        trades.append(trade)

    return trades


def test_bullish_divergence():
    """Test detection of bullish divergence (price down, CVD up = BUY_CALL)."""
    print("\n" + "="*70)
    print("TEST 1: Bullish Divergence Detection")
    print("="*70)

    analyzer = SignalEngine("SPY")

    # Create a strong bullish divergence: price falls but buying accelerates
    trades = []
    base_price = 650.0
    base_time = datetime.now(timezone.utc)

    for i in range(100):
        # Price falling
        price = base_price - (i * 0.02)

        # Volume increasing for buys
        size = 500 + (i * 50)

        # More buys than sells (at least 65% buy volume)
        side = "buy" if (i % 3) != 0 else "sell"

        trade = {
            "t": (base_time + timedelta(seconds=i)).isoformat(),
            "p": round(price, 2),
            "s": int(size),
            "side": side,
        }
        trades.append(trade)

    # Add large buy blocks for extra strength
    for i in range(3):
        trades.append({
            "t": (base_time + timedelta(seconds=100+i)).isoformat(),
            "p": 649.00 + (i * 0.05),
            "s": 5000,
            "side": "buy",
        })

    quote = {
        "bid": 649.95,
        "ask": 650.05,
        "last": 650.00,
        "time": datetime.now(timezone.utc).isoformat(),
    }

    signal = analyzer.analyze(trades, quote)

    print(f"Signal: {signal['signal']}")
    print(f"Confidence: {signal['confidence']:.2%}")
    print(f"Divergence Type: {signal['indicators']['divergence']}")
    print(f"Price Trend: {signal['indicators']['price_trend']}")
    print(f"CVD Trend: {signal['indicators']['cvd_trend']}")
    print(f"Risk: {signal['risk_pct']}% (${signal['risk_management']['risk_amount']:.2f})")
    print(f"Max Contracts: {signal['risk_management']['max_contracts']}")
    print(f"Reasoning: {signal['reasoning']}")

    assert signal["signal"] == "BUY_CALL", f"Should generate BUY_CALL on bullish divergence, got {signal['signal']}"
    print("\n✓ Bullish divergence test PASSED")


def test_bearish_divergence():
    """Test detection of bearish divergence (price up, CVD down = BUY_PUT)."""
    print("\n" + "="*70)
    print("TEST 2: Bearish Divergence Detection")
    print("="*70)

    analyzer = SignalEngine("SPY")

    # Create a strong bearish divergence: price rises but selling accelerates
    trades = []
    base_price = 650.0
    base_time = datetime.now(timezone.utc)

    for i in range(100):
        # Price rising
        price = base_price + (i * 0.02)

        # Volume increasing
        size = 500 + (i * 50)

        # More sells than buys (at least 65% sell volume)
        side = "sell" if (i % 3) != 0 else "buy"

        trade = {
            "t": (base_time + timedelta(seconds=i)).isoformat(),
            "p": round(price, 2),
            "s": int(size),
            "side": side,
        }
        trades.append(trade)

    # Add large sell blocks for extra strength
    for i in range(3):
        trades.append({
            "t": (base_time + timedelta(seconds=100+i)).isoformat(),
            "p": 651.00 + (i * 0.05),
            "s": 5000,
            "side": "sell",
        })

    quote = {
        "bid": 650.95,
        "ask": 651.05,
        "last": 651.00,
        "time": datetime.now(timezone.utc).isoformat(),
    }

    signal = analyzer.analyze(trades, quote)

    print(f"Signal: {signal['signal']}")
    print(f"Confidence: {signal['confidence']:.2%}")
    print(f"Divergence Type: {signal['indicators']['divergence']}")
    print(f"Price Trend: {signal['indicators']['price_trend']}")
    print(f"CVD Trend: {signal['indicators']['cvd_trend']}")
    print(f"Risk: {signal['risk_pct']}% (${signal['risk_management']['risk_amount']:.2f})")
    print(f"Reasoning: {signal['reasoning']}")

    assert signal["signal"] == "BUY_PUT", f"Should generate BUY_PUT on bearish divergence, got {signal['signal']}"
    print("\n✓ Bearish divergence test PASSED")


def test_dynamic_risk_sizing():
    """Test dynamic risk sizing based on confidence levels."""
    print("\n" + "="*70)
    print("TEST 3: Dynamic Risk Sizing")
    print("="*70)

    analyzer = SignalEngine("SPY")

    test_cases = [
        ("Low Confidence", 0.55, 0.5),
        ("Medium Confidence", 0.70, 1.0),
        ("High Confidence", 0.85, 2.0),
    ]

    for name, confidence, expected_risk in test_cases:
        risk = analyzer._calculate_risk(confidence, ACCOUNT_BALANCE)

        print(f"\n{name} ({confidence:.0%}):")
        print(f"  Expected Risk: {expected_risk}%")
        print(f"  Actual Risk: {risk['risk_pct']}%")
        print(f"  Risk Amount: ${risk['risk_amount']:.2f}")
        print(f"  Max Contracts: {risk['max_contracts']}")
        print(f"  Position %: {risk['position_pct']:.2f}%")

        assert risk["risk_pct"] == expected_risk, f"Risk sizing mismatch for {name}"

    print("\n✓ Dynamic risk sizing test PASSED")


def test_strike_selection():
    """Test strike selection based on signal direction."""
    print("\n" + "="*70)
    print("TEST 4: Strike Selection")
    print("="*70)

    analyzer = SignalEngine("SPY")
    current_price = 650.00

    # Test CALL selection
    call_strike = analyzer._select_strike(current_price, "BUY_CALL")
    print(f"\nCurrent Price: ${current_price:.2f}")
    print(f"BUY_CALL Strike: ${call_strike:.2f} (should be slightly OTM)")
    assert call_strike > current_price, "CALL strike should be above current price"

    # Test PUT selection
    put_strike = analyzer._select_strike(current_price, "BUY_PUT")
    print(f"BUY_PUT Strike: ${put_strike:.2f} (should be slightly OTM)")
    assert put_strike < current_price, "PUT strike should be below current price"

    print("\n✓ Strike selection test PASSED")


def test_option_pricing():
    """Test option price estimation."""
    print("\n" + "="*70)
    print("TEST 5: Option Price Estimation")
    print("="*70)

    analyzer = SignalEngine("SPY")

    test_cases = [
        ("At-the-money CALL", 650.0, 650.0, "BUY_CALL"),
        ("Out-of-the-money CALL", 650.0, 651.0, "BUY_CALL"),
        ("In-the-money CALL", 650.0, 649.0, "BUY_CALL"),
        ("At-the-money PUT", 650.0, 650.0, "BUY_PUT"),
        ("Out-of-the-money PUT", 650.0, 649.0, "BUY_PUT"),
        ("In-the-money PUT", 650.0, 651.0, "BUY_PUT"),
    ]

    for name, current_price, strike, signal in test_cases:
        price = analyzer._estimate_option_price(strike, signal, current_price)
        intrinsic = max(0, abs(current_price - strike))

        print(f"\n{name}:")
        print(f"  Current: ${current_price:.2f}, Strike: ${strike:.2f}")
        print(f"  Estimated Price: ${price:.2f}")
        print(f"  Intrinsic Value: ${intrinsic:.2f}")

        # Prices should be realistic ($0.50 - $5.00)
        assert 0.50 <= price <= 5.00, f"Option price out of range: ${price}"

    print("\n✓ Option pricing test PASSED")


def test_absorption_detection():
    """Test absorption level detection."""
    print("\n" + "="*70)
    print("TEST 6: Absorption Level Detection")
    print("="*70)

    analyzer = SignalEngine("SPY")

    # Create trades with absorption at 650.00
    trades = []
    base_time = datetime.now(timezone.utc)

    # High volume at 650.00
    for i in range(30):
        trades.append({
            "t": (base_time + timedelta(seconds=i)).isoformat(),
            "p": 650.00,
            "s": 500 + (i * 50),  # High volume
            "side": "buy" if i % 2 == 0 else "sell",
        })

    # Lower volume at other levels
    for i in range(10):
        trades.append({
            "t": (base_time + timedelta(seconds=30+i)).isoformat(),
            "p": 649.50 + (i * 0.10),
            "s": 100,
            "side": "sell",
        })

    absorption_levels = analyzer._detect_absorption(trades, 650.00)

    print(f"Detected Absorption Levels: {absorption_levels}")
    print(f"Number of Absorption Levels: {len(absorption_levels)}")

    assert 650.0 in absorption_levels, "Should detect absorption at 650.00"
    print("\n✓ Absorption detection test PASSED")


def test_large_trade_detection():
    """Test large trade detection (blocks)."""
    print("\n" + "="*70)
    print("TEST 7: Large Trade Detection")
    print("="*70)

    analyzer = SignalEngine("SPY")

    trades = []
    base_time = datetime.now(timezone.utc)

    # Add some normal trades
    for i in range(20):
        trades.append({
            "t": (base_time + timedelta(seconds=i)).isoformat(),
            "p": 650.00 + (i * 0.01),
            "s": 100,
            "side": "buy" if i % 2 == 0 else "sell",
        })

    # Add large block trades
    large_trades_count = 3
    for i in range(large_trades_count):
        trades.append({
            "t": (base_time + timedelta(seconds=20+i)).isoformat(),
            "p": 650.20 + (i * 0.05),
            "s": 10000,  # Large block
            "side": "buy",
        })

    detected_large = analyzer._detect_large_trades(trades, threshold=5000)

    print(f"Total Trades: {len(trades)}")
    print(f"Large Trades (>= 5000 shares): {len(detected_large)}")
    for trade in detected_large:
        print(f"  - {trade['s']} shares @ ${trade['p']} ({trade['side']})")

    assert len(detected_large) >= large_trades_count, "Should detect all large trades"
    print("\n✓ Large trade detection test PASSED")


def test_no_trade_conditions():
    """Test NO_TRADE signal generation."""
    print("\n" + "="*70)
    print("TEST 8: NO_TRADE Signal Generation")
    print("="*70)

    analyzer = SignalEngine("SPY")

    # Test with insufficient data
    trades = create_test_trades(count=5)  # Too few trades
    quote = {"bid": 649.95, "ask": 650.05, "last": 650.00}

    signal = analyzer.analyze(trades, quote)
    print(f"\nInsufficient trades: {signal['signal']}")
    assert signal["signal"] == "NO_TRADE"

    # Test with invalid quote
    trades = create_test_trades(count=100)
    quote = {"bid": 649.95, "ask": 650.05}  # Missing 'last'

    signal = analyzer.analyze(trades, quote)
    print(f"Missing quote data: {signal['signal']}")
    assert signal["signal"] == "NO_TRADE"

    print("\n✓ NO_TRADE conditions test PASSED")


def test_full_signal_workflow():
    """Test complete signal generation workflow."""
    print("\n" + "="*70)
    print("TEST 9: Full Signal Generation Workflow")
    print("="*70)

    analyzer = SignalEngine("SPY")

    # Create realistic market scenario
    trades = create_test_trades(
        count=150,
        price_trend="down",
        volume_trend="increasing"
    )

    # Add some large blocks
    base_time = datetime.now(timezone.utc)
    for i in range(3):
        trades.append({
            "t": (base_time + timedelta(seconds=150+i)).isoformat(),
            "p": 649.50 + (i * 0.10),
            "s": 8000,
            "side": "buy",
        })

    quote = {
        "bid": 649.95,
        "ask": 650.05,
        "last": 650.00,
        "time": datetime.now(timezone.utc).isoformat(),
    }

    options_data = {
        "call_volume": 45000,
        "put_volume": 52000,
        "chains": [
            {"strike": 650.0, "open_interest": 150000},
            {"strike": 652.0, "open_interest": 120000},
            {"strike": 648.0, "open_interest": 100000},
        ]
    }

    signal = analyzer.analyze(trades, quote, options_data, ACCOUNT_BALANCE)

    print("\nSignal Analysis Result:")
    print(f"  Action: {signal['signal']}")
    print(f"  Symbol: {signal['symbol']}")
    print(f"  Strike: ${signal['strike']}")
    print(f"  Expiry: {signal['expiry']}")
    print(f"  Entry Price: ${signal['entry_price']}")
    print(f"  Target Price: ${signal['target_price']}")
    print(f"  Stop Price: ${signal['stop_price']}")
    print(f"  Confidence: {signal['confidence']:.2%}")
    print(f"  Risk: {signal['risk_pct']}%")

    print("\nIndicators:")
    for key, value in signal['indicators'].items():
        print(f"  {key}: {value}")

    print("\nRisk Management:")
    for key, value in signal['risk_management'].items():
        print(f"  {key}: {value}")

    print(f"\nReasoning: {signal['reasoning']}")

    # Verify structure
    assert signal["signal"] in ["BUY_CALL", "BUY_PUT", "NO_TRADE"]
    assert isinstance(signal["confidence"], (int, float))
    assert "reasoning" in signal
    assert "risk_management" in signal

    print("\n✓ Full workflow test PASSED")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("SIGNAL API TEST SUITE")
    print("="*70)

    try:
        test_bullish_divergence()
        test_bearish_divergence()
        test_dynamic_risk_sizing()
        test_strike_selection()
        test_option_pricing()
        test_absorption_detection()
        test_large_trade_detection()
        test_no_trade_conditions()
        test_full_signal_workflow()

        print("\n" + "="*70)
        print("ALL TESTS PASSED ✓")
        print("="*70)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
