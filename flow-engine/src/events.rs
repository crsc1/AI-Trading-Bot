//! Event types published from the Rust engine to Python agents via WebSocket.
//!
//! Every event is a tagged JSON object with `"type"` discriminator so the
//! Python side can pattern-match easily.

use chrono::{DateTime, Utc};
use ordered_float::OrderedFloat;
use serde::{Deserialize, Serialize};

// ─────────────────────────────────────────────────────────────────────────────
// Raw tick from data provider (ThetaData / Alpaca / Finnhub)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RawTick {
    pub price: f64,
    pub size: u64,
    pub timestamp: DateTime<Utc>,
    /// Exchange conditions / flags from the feed
    pub conditions: Vec<String>,
    /// Data source identifier
    pub source: TickSource,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TickSource {
    ThetaData,
    Alpaca,
    Finnhub,
}

// ─────────────────────────────────────────────────────────────────────────────
// Classified tick (after buy/sell classification)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TradeSide {
    Buy,
    Sell,
    Unknown,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ClassifiedTick {
    pub price: f64,
    pub size: u64,
    pub side: TradeSide,
    pub timestamp: DateTime<Utc>,
    pub source: TickSource,
}

// ─────────────────────────────────────────────────────────────────────────────
// NBBO quote (National Best Bid/Offer)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NbboQuote {
    pub bid: f64,
    pub ask: f64,
    pub bid_size: u64,
    pub ask_size: u64,
    pub timestamp: DateTime<Utc>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Footprint level: volume at a single price level within a time bar
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FootprintLevel {
    pub price: f64,
    pub bid_vol: u64,
    pub ask_vol: u64,
}

// ─────────────────────────────────────────────────────────────────────────────
// Published events (Rust → Python agents)
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum FlowEvent {
    /// Updated footprint bar (sent on every tick or throttled)
    Footprint {
        bar_time: i64,
        levels: Vec<FootprintLevel>,
        total_buy_vol: u64,
        total_sell_vol: u64,
    },

    /// Cumulative Volume Delta update
    Cvd {
        value: i64,
        delta_1m: i64,
        delta_5m: i64,
        timestamp: DateTime<Utc>,
    },

    /// Imbalance detected at a price level
    Imbalance {
        price: f64,
        side: TradeSide,
        ratio: f64,
        /// Number of consecutive levels with imbalance (stacked)
        stacked: u32,
        timestamp: DateTime<Utc>,
    },

    /// Large aggressive sweep across multiple levels
    Sweep {
        price: f64,
        size: u64,
        side: TradeSide,
        levels_hit: u32,
        timestamp: DateTime<Utc>,
    },

    /// Volume absorbed at a level without price breaking through
    Absorption {
        price: f64,
        volume: u64,
        side: TradeSide,
        /// Whether the level held (true = absorption confirmed)
        held: bool,
        timestamp: DateTime<Utc>,
    },

    /// CVD sign change
    DeltaFlip {
        from: TradeSide,
        to: TradeSide,
        cvd_at_flip: i64,
        timestamp: DateTime<Utc>,
    },

    /// Single large trade
    LargeTrade {
        price: f64,
        size: u64,
        side: TradeSide,
        timestamp: DateTime<Utc>,
    },

    /// Live tick — broadcast every trade so the dashboard can build candles
    Tick {
        price: f64,
        size: u64,
        side: TradeSide,
        timestamp: DateTime<Utc>,
    },

    /// Heartbeat — sent every N seconds so agents know engine is alive
    Heartbeat {
        timestamp: DateTime<Utc>,
        ticks_processed: u64,
        last_price: f64,
        #[serde(skip_serializing_if = "Option::is_none")]
        data_source: Option<String>,
    },
}

// ─────────────────────────────────────────────────────────────────────────────
// Price level key — OrderedFloat so we can use it in BTreeMap
// ─────────────────────────────────────────────────────────────────────────────

pub type PriceLevel = OrderedFloat<f64>;

/// Round price to nearest tick (e.g., $0.01 for SPY equities)
pub fn price_to_level(price: f64, tick_size: f64) -> PriceLevel {
    OrderedFloat((price / tick_size).round() * tick_size)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_price_to_level() {
        let level = price_to_level(562.347, 0.01);
        assert_eq!(level, OrderedFloat(562.35));
    }

    #[test]
    fn test_flow_event_serialization() {
        let event = FlowEvent::LargeTrade {
            price: 562.35,
            size: 2500,
            side: TradeSide::Buy,
            timestamp: Utc::now(),
        };
        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"type\":\"large_trade\""));
        assert!(json.contains("\"side\":\"buy\""));
    }
}
