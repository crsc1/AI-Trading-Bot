//! Footprint chart builder.
//!
//! Maintains a grid of time bars × price levels. Each cell tracks:
//!   - bid_vol: volume traded at bid (sells)
//!   - ask_vol: volume traded at ask (buys)
//!
//! Bars rotate on a configurable interval (default 1 minute).
//! On each tick, the current bar is updated and the full bar state
//! is available for publishing to agents.

use crate::events::{price_to_level, ClassifiedTick, FlowEvent, FootprintLevel, PriceLevel, TradeSide};
use chrono::{DateTime, Utc};
use std::collections::BTreeMap;

/// Configuration for footprint builder
#[derive(Debug, Clone)]
pub struct FootprintConfig {
    /// Bar duration in seconds (default 60 = 1 minute)
    pub bar_seconds: i64,
    /// Price tick size for level rounding (default 0.01 for SPY)
    pub tick_size: f64,
    /// Max number of completed bars to retain in memory
    pub max_bars: usize,
}

impl Default for FootprintConfig {
    fn default() -> Self {
        Self {
            bar_seconds: 60,
            tick_size: 0.01,
            max_bars: 390, // Full trading day of 1-min bars
        }
    }
}

/// Volume at a single price level
#[derive(Debug, Default, Clone)]
struct LevelVolume {
    bid_vol: u64,
    ask_vol: u64,
}

/// A single footprint bar (one time period)
#[derive(Debug, Clone)]
struct FootprintBar {
    bar_time: i64, // Unix timestamp of bar start
    levels: BTreeMap<PriceLevel, LevelVolume>,
    total_buy_vol: u64,
    total_sell_vol: u64,
}

impl FootprintBar {
    fn new(bar_time: i64) -> Self {
        Self {
            bar_time,
            levels: BTreeMap::new(),
            total_buy_vol: 0,
            total_sell_vol: 0,
        }
    }

    fn add_tick(&mut self, level: PriceLevel, size: u64, side: TradeSide) {
        let entry = self.levels.entry(level).or_default();
        match side {
            TradeSide::Buy => {
                entry.ask_vol += size;
                self.total_buy_vol += size;
            }
            TradeSide::Sell => {
                entry.bid_vol += size;
                self.total_sell_vol += size;
            }
            TradeSide::Unknown => {
                // Split evenly for unknown side
                entry.ask_vol += size / 2;
                entry.bid_vol += size / 2;
            }
        }
    }

    fn to_event(&self) -> FlowEvent {
        let levels: Vec<FootprintLevel> = self
            .levels
            .iter()
            .map(|(price, vol)| FootprintLevel {
                price: price.into_inner(),
                bid_vol: vol.bid_vol,
                ask_vol: vol.ask_vol,
            })
            .collect();

        FlowEvent::Footprint {
            bar_time: self.bar_time,
            levels,
            total_buy_vol: self.total_buy_vol,
            total_sell_vol: self.total_sell_vol,
        }
    }
}

/// Footprint chart builder — the core data structure.
pub struct FootprintBuilder {
    config: FootprintConfig,
    /// Currently active (in-progress) bar
    current_bar: Option<FootprintBar>,
    /// Completed bars (most recent last)
    completed_bars: Vec<FootprintBar>,
}

impl FootprintBuilder {
    pub fn new(config: FootprintConfig) -> Self {
        Self {
            config,
            current_bar: None,
            completed_bars: Vec::new(),
        }
    }

    /// Compute the bar start timestamp for a given time.
    fn bar_start(&self, timestamp: &DateTime<Utc>) -> i64 {
        let ts = timestamp.timestamp();
        ts - (ts % self.config.bar_seconds)
    }

    /// Process a classified tick. Returns a footprint event if the bar was updated.
    pub fn process_tick(&mut self, tick: &ClassifiedTick) -> FlowEvent {
        let bar_time = self.bar_start(&tick.timestamp);
        let level = price_to_level(tick.price, self.config.tick_size);

        // Check if we need to rotate to a new bar
        match &self.current_bar {
            Some(bar) if bar.bar_time == bar_time => {
                // Same bar, just update
            }
            Some(_) => {
                // New bar — archive current and start fresh
                let completed = self.current_bar.take().unwrap();
                self.completed_bars.push(completed);

                // Trim old bars
                if self.completed_bars.len() > self.config.max_bars {
                    let excess = self.completed_bars.len() - self.config.max_bars;
                    self.completed_bars.drain(0..excess);
                }

                self.current_bar = Some(FootprintBar::new(bar_time));
            }
            None => {
                self.current_bar = Some(FootprintBar::new(bar_time));
            }
        }

        // Update the current bar
        let bar = self.current_bar.as_mut().unwrap();
        bar.add_tick(level, tick.size, tick.side);

        // Return current bar state as event
        bar.to_event()
    }

    /// Get the current bar's imbalance levels (for the imbalance detector).
    pub fn current_levels(&self) -> Vec<(PriceLevel, u64, u64)> {
        match &self.current_bar {
            Some(bar) => bar
                .levels
                .iter()
                .map(|(p, v)| (*p, v.bid_vol, v.ask_vol))
                .collect(),
            None => Vec::new(),
        }
    }

    /// Get the number of completed bars in memory.
    pub fn completed_bar_count(&self) -> usize {
        self.completed_bars.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::TickSource;

    fn make_classified(price: f64, size: u64, side: TradeSide, ts: DateTime<Utc>) -> ClassifiedTick {
        ClassifiedTick {
            price,
            size,
            side,
            timestamp: ts,
            source: TickSource::ThetaData,
        }
    }

    #[test]
    fn test_footprint_accumulates_volume() {
        let config = FootprintConfig {
            bar_seconds: 60,
            tick_size: 0.01,
            max_bars: 10,
        };
        let mut fp = FootprintBuilder::new(config);
        let now = Utc::now();

        let tick1 = make_classified(562.35, 100, TradeSide::Buy, now);
        let tick2 = make_classified(562.35, 200, TradeSide::Sell, now);
        let tick3 = make_classified(562.36, 50, TradeSide::Buy, now);

        fp.process_tick(&tick1);
        fp.process_tick(&tick2);
        let event = fp.process_tick(&tick3);

        match event {
            FlowEvent::Footprint {
                total_buy_vol,
                total_sell_vol,
                levels,
                ..
            } => {
                assert_eq!(total_buy_vol, 150); // 100 + 50
                assert_eq!(total_sell_vol, 200);
                assert_eq!(levels.len(), 2); // Two price levels
            }
            _ => panic!("Expected Footprint event"),
        }
    }
}
