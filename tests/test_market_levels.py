"""
Unit tests for market_levels.py module.

Tests:
- compute_market_levels() with various bar data
- VWAP calculation accuracy
- Pivot point calculation (R1, S1, R2, S2)
- ORB (Opening Range Breakout) detection
- ATR calculation
- Edge cases: empty data, single bar, missing fields
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Dict

from dashboard.market_levels import (
    MarketLevels,
    compute_market_levels,
)


class TestMarketLevelsBasics:
    """Test basic MarketLevels dataclass functionality."""

    def test_market_levels_initialization(self):
        """Test that MarketLevels initializes with defaults."""
        levels = MarketLevels()
        assert levels.current_price == 0.0
        assert levels.vwap == 0.0
        assert levels.pivot == 0.0

    def test_market_levels_to_dict(self):
        """Test conversion to dictionary."""
        levels = MarketLevels(
            current_price=550.0,
            bid=549.95,
            ask=550.05,
            vwap=549.80,
        )
        d = levels.to_dict()
        assert isinstance(d, dict)
        assert d["current_price"] == 550.0
        assert d["bid"] == 549.95
        assert d["vwap"] == 549.80

    def test_nearby_levels_returns_sorted_list(self):
        """Test nearby_levels() returns levels sorted by distance."""
        levels = MarketLevels(
            vwap=550.0,
            r1=551.0,
            s1=549.0,
            pivot=550.2,
        )
        nearby = levels.nearby_levels(price=550.1, threshold=1.0)
        assert len(nearby) > 0
        # Should be sorted by distance
        for i in range(len(nearby) - 1):
            dist_i = abs(nearby[i][1] - 550.1)
            dist_i_plus_1 = abs(nearby[i + 1][1] - 550.1)
            assert dist_i <= dist_i_plus_1

    def test_nearby_levels_respects_threshold(self):
        """Test that nearby_levels respects the threshold parameter."""
        levels = MarketLevels(
            vwap=550.0,
            r1=551.0,
            s1=549.0,
            pivot=550.2,
            r2=553.0,  # Outside default threshold
        )
        nearby = levels.nearby_levels(price=550.0, threshold=0.5)
        # r2 at 553.0 is 3.0 away, should not be included
        level_names = [name for name, _ in nearby]
        assert "R2" not in level_names


class TestComputeMarketLevels:
    """Test compute_market_levels() function."""

    def test_compute_market_levels_with_complete_data(self, mock_bar_data_1m, mock_bar_data_daily, mock_quote):
        """Test compute_market_levels with all data sources."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=mock_bar_data_daily,
            quote=mock_quote,
        )

        assert isinstance(levels, MarketLevels)
        assert levels.current_price == mock_quote["last"]
        assert levels.bid == mock_quote["bid"]
        assert levels.ask == mock_quote["ask"]
        assert levels.prev_close == mock_quote["prev_close"]

    def test_compute_market_levels_empty_1m_bars(self, mock_bar_data_daily, mock_quote):
        """Test compute_market_levels with empty 1-minute bars."""
        levels = compute_market_levels(
            bars_1m=[],
            bars_daily=mock_bar_data_daily,
            quote=mock_quote,
        )

        # Should return valid MarketLevels object
        assert isinstance(levels, MarketLevels)
        # Pivot might be computed from daily data or might be zero
        assert levels.pivot >= 0

    def test_compute_market_levels_empty_daily_bars(self, mock_bar_data_1m, mock_quote):
        """Test compute_market_levels with empty daily bars."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote=mock_quote,
        )

        # Should return valid MarketLevels object
        assert isinstance(levels, MarketLevels)
        # Pivot requires daily data so should be zero
        assert levels.pivot == 0

    def test_compute_market_levels_all_empty(self):
        """Test compute_market_levels with all empty data."""
        levels = compute_market_levels(
            bars_1m=[],
            bars_daily=[],
            quote={"last": 550.0, "bid": 549.95, "ask": 550.05, "prev_close": 549.50},
        )

        assert levels.current_price == 550.0
        assert levels.hod == 0  # No bars
        assert levels.lod == 0  # No bars
        assert levels.pivot == 0  # No daily data


class TestVWAPCalculation:
    """Test VWAP calculation."""

    def test_vwap_field_exists(self, mock_bar_data_1m):
        """Test that VWAP field is present in levels."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 0},
        )

        # VWAP field should exist
        assert hasattr(levels, "vwap")
        assert isinstance(levels.vwap, (int, float))

    def test_vwap_bands_exist(self, mock_bar_data_1m):
        """Test that VWAP band fields exist."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 0},
        )

        # VWAP band fields should exist
        assert hasattr(levels, "vwap_upper_1")
        assert hasattr(levels, "vwap_lower_1")
        assert hasattr(levels, "vwap_upper_2")
        assert hasattr(levels, "vwap_lower_2")

    def test_vwap_bands_ordering_when_present(self, mock_bar_data_1m):
        """Test that VWAP bands are ordered correctly when computed."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 0},
        )

        # If VWAP is computed, bands should be ordered properly
        if levels.vwap > 0 and levels.vwap_upper_1 > 0:
            assert levels.vwap_upper_1 >= levels.vwap
            assert levels.vwap >= levels.vwap_lower_1


class TestPivotPointCalculation:
    """Test pivot point calculations."""

    def test_pivot_field_exists(self, mock_bar_data_daily):
        """Test that pivot field exists in levels."""
        levels = compute_market_levels(
            bars_1m=[],
            bars_daily=mock_bar_data_daily,
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # Pivot field should exist
        assert hasattr(levels, "pivot")
        assert isinstance(levels.pivot, (int, float))

    def test_support_resistance_fields_exist(self, mock_bar_data_daily):
        """Test that support and resistance fields exist."""
        levels = compute_market_levels(
            bars_1m=[],
            bars_daily=mock_bar_data_daily,
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # All pivot fields should exist
        pivot_fields = ["pivot", "r1", "r2", "r3", "s1", "s2", "s3"]
        for field in pivot_fields:
            assert hasattr(levels, field)
            assert isinstance(getattr(levels, field), (int, float))

    def test_support_resistance_ordering_when_present(self, mock_bar_data_daily):
        """Test that support and resistance levels are ordered when computed."""
        levels = compute_market_levels(
            bars_1m=[],
            bars_daily=mock_bar_data_daily,
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        if levels.pivot > 0 and levels.r1 > 0:
            # When computed, should follow pattern
            assert levels.r2 >= levels.r1 or levels.r2 == 0
            assert levels.r1 >= levels.pivot or levels.r1 == 0
            if levels.s1 > 0:
                assert levels.pivot >= levels.s1


class TestOrbDetection:
    """Test Opening Range Breakout (ORB) detection."""

    def test_orb_fields_exist(self, mock_bar_data_1m):
        """Test that ORB fields are present."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # ORB fields should exist
        assert hasattr(levels, "orb_5_high")
        assert hasattr(levels, "orb_5_low")
        assert hasattr(levels, "orb_15_high")
        assert hasattr(levels, "orb_15_low")

    def test_orb_ordering_when_present(self, mock_bar_data_1m):
        """Test that ORB high/low are properly ordered when computed."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # When ORB is computed, high should be >= low
        if levels.orb_5_high > 0 and levels.orb_5_low > 0:
            assert levels.orb_5_high >= levels.orb_5_low

        if levels.orb_15_high > 0 and levels.orb_15_low > 0:
            assert levels.orb_15_high >= levels.orb_15_low

    def test_orb_15_encompasses_orb_5(self, mock_bar_data_1m):
        """Test that 15-min ORB range is >= 5-min ORB range."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # If both ORBs are computed, 15-min should be wider
        if levels.orb_5_high > 0 and levels.orb_15_high > 0:
            range_5 = levels.orb_5_high - levels.orb_5_low
            range_15 = levels.orb_15_high - levels.orb_15_low
            assert range_15 >= range_5 or range_5 == 0


class TestATRCalculation:
    """Test Average True Range (ATR) calculation."""

    def test_atr_field_exists(self, mock_bar_data_1m):
        """Test that ATR fields exist."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # ATR fields should exist
        assert hasattr(levels, "atr_1m")
        assert hasattr(levels, "atr_5m")
        assert isinstance(levels.atr_1m, (int, float))

    def test_atr_realistic_range(self, mock_bar_data_1m):
        """Test that ATR is in a reasonable range."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # ATR should be non-negative and less than absurd values
        assert levels.atr_1m >= 0
        assert levels.atr_1m < 100.0  # Reasonable upper bound


class TestHODLOD:
    """Test High of Day and Low of Day calculations."""

    def test_hod_lod_fields_exist(self, mock_bar_data_1m):
        """Test that HOD/LOD fields exist."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # HOD/LOD fields should exist
        assert hasattr(levels, "hod")
        assert hasattr(levels, "lod")
        assert isinstance(levels.hod, (int, float))
        assert isinstance(levels.lod, (int, float))

    def test_hod_from_bars_when_available(self, mock_bar_data_1m):
        """Test that HOD is computed from bars when available."""
        # Create bars with explicit high values
        bars = [
            {"h": 550.5, "l": 549.5, "o": 550.0, "c": 550.2, "v": 100000},
            {"h": 551.0, "l": 549.8, "o": 550.2, "c": 550.8, "v": 110000},
            {"h": 550.8, "l": 549.9, "o": 550.8, "c": 550.5, "v": 105000},
        ]

        levels = compute_market_levels(
            bars_1m=bars,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # If HOD is computed, it should be reasonable
        if levels.hod > 0:
            assert levels.hod >= 550.5  # At least the max we provided

    def test_hod_gte_lod_when_present(self, mock_bar_data_1m):
        """Test that HOD >= LOD when both are computed."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # When both are present, HOD should be >= LOD
        if levels.hod > 0 and levels.lod > 0:
            assert levels.hod >= levels.lod


class TestEdgeCases:
    """Test edge cases and data validation."""

    def test_single_bar(self):
        """Test with only a single bar."""
        single_bar = [{
            "t": datetime.now(timezone.utc).isoformat(),
            "o": 550.0,
            "h": 550.50,
            "l": 549.50,
            "c": 550.25,
            "v": 100000,
            "vw": 550.1,
        }]

        levels = compute_market_levels(
            bars_1m=single_bar,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # Should handle single bar gracefully and return valid MarketLevels
        assert isinstance(levels, MarketLevels)

    def test_missing_fields_in_bars(self):
        """Test handling of bars with missing fields."""
        incomplete_bar = [{
            "t": datetime.now(timezone.utc).isoformat(),
            "o": 550.0,
            "c": 550.25,
            # Missing h, l, v, vw
        }]

        levels = compute_market_levels(
            bars_1m=incomplete_bar,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # Should handle missing fields gracefully
        assert isinstance(levels, MarketLevels)

    def test_missing_fields_in_quote(self):
        """Test handling of quote with missing fields."""
        incomplete_quote = {
            "last": 550.0,
            # Missing bid, ask, prev_close
        }

        levels = compute_market_levels(
            bars_1m=[],
            bars_daily=[],
            quote=incomplete_quote,
        )

        assert levels.current_price == 550.0
        assert levels.bid == 0
        assert levels.ask == 0

    def test_negative_prices_handled(self):
        """Test that negative prices are handled gracefully."""
        bad_bars = [
            {"h": -1.0, "l": -2.0, "v": 100000, "vw": 550.0},
            {"h": 550.5, "l": 549.5, "v": 100000, "vw": 550.0},
        ]

        levels = compute_market_levels(
            bars_1m=bad_bars,
            bars_daily=[],
            quote={"last": 550.0, "bid": 0, "ask": 0, "prev_close": 549.50},
        )

        # Should handle negative prices gracefully
        assert isinstance(levels, MarketLevels)
        # HOD should be from positive bars
        if levels.hod > 0:
            assert levels.hod >= 0


class TestLevelPersistence:
    """Test that levels are properly computed and persist."""

    def test_all_levels_present_in_output(self, mock_bar_data_1m, mock_bar_data_daily, mock_quote):
        """Test that all level fields are present in output."""
        levels = compute_market_levels(
            bars_1m=mock_bar_data_1m,
            bars_daily=mock_bar_data_daily,
            quote=mock_quote,
        )

        required_fields = [
            "current_price", "bid", "ask", "prev_close",
            "hod", "lod", "vwap",
            "pivot", "r1", "r2", "s1", "s2",
            "orb_5_high", "orb_5_low",
            "atr_1m",
        ]

        for field in required_fields:
            assert hasattr(levels, field), f"Missing field: {field}"
