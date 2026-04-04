//! Cumulative Volume Delta (CVD) calculator.
//!
//! CVD = running sum of signed volume:
//!   +size for buys (aggressive buyers lifting asks)
//!   -size for sells (aggressive sellers hitting bids)
//!
//! Tracks rolling windows (1-min, 5-min) for delta momentum.
//! Detects delta flips (sign changes) which are key trading signals.

use crate::events::{ClassifiedTick, FlowEvent, TradeSide};
use chrono::{DateTime, Duration, Utc};
use std::collections::VecDeque;

/// Configuration for CVD calculator
#[derive(Debug, Clone)]
pub struct CvdConfig {
    /// Large trade threshold (shares) for LargeTrade events
    pub large_trade_threshold: u64,
    /// Rolling window for 1-min delta
    pub window_1m_secs: i64,
    /// Rolling window for 5-min delta
    pub window_5m_secs: i64,
}

impl Default for CvdConfig {
    fn default() -> Self {
        Self {
            large_trade_threshold: 1000, // SPY: 1000 shares ≈ $562K notional
            window_1m_secs: 60,
            window_5m_secs: 300,
        }
    }
}

/// Timestamped delta entry for rolling window calculations
#[derive(Debug, Clone)]
struct DeltaEntry {
    timestamp: DateTime<Utc>,
    signed_volume: i64,
}

/// CVD calculator with rolling windows and flip detection.
pub struct CvdCalculator {
    config: CvdConfig,
    /// Running cumulative delta (all-session)
    cumulative: i64,
    /// Recent deltas for rolling window calc
    recent_deltas: VecDeque<DeltaEntry>,
    /// Last sign of CVD for flip detection
    last_sign: Option<bool>, // true = positive, false = negative
    /// Total ticks processed
    ticks_processed: u64,
}

impl CvdCalculator {
    pub fn new(config: CvdConfig) -> Self {
        Self {
            config,
            cumulative: 0,
            recent_deltas: VecDeque::with_capacity(10_000),
            last_sign: None,
            ticks_processed: 0,
        }
    }

    /// Process a classified tick. Returns CVD update event + optional signals.
    pub fn process_tick(&mut self, tick: &ClassifiedTick) -> Vec<FlowEvent> {
        let mut events = Vec::new();
        self.ticks_processed += 1;

        // Compute signed volume
        let signed_vol: i64 = match tick.side {
            TradeSide::Buy => tick.size as i64,
            TradeSide::Sell => -(tick.size as i64),
            TradeSide::Unknown => 0,
        };

        // Update cumulative
        self.cumulative += signed_vol;

        // Store for rolling window
        self.recent_deltas.push_back(DeltaEntry {
            timestamp: tick.timestamp,
            signed_volume: signed_vol,
        });

        // Prune entries older than 5 minutes (largest window)
        let cutoff = tick.timestamp - Duration::seconds(self.config.window_5m_secs + 10);
        while let Some(front) = self.recent_deltas.front() {
            if front.timestamp < cutoff {
                self.recent_deltas.pop_front();
            } else {
                break;
            }
        }

        // Calculate rolling deltas
        let delta_1m = self.rolling_delta(tick.timestamp, self.config.window_1m_secs);
        let delta_5m = self.rolling_delta(tick.timestamp, self.config.window_5m_secs);

        // CVD update event
        events.push(FlowEvent::Cvd {
            value: self.cumulative,
            delta_1m,
            delta_5m,
            timestamp: tick.timestamp,
        });

        // Check for delta flip
        let current_sign = self.cumulative > 0;
        if let Some(last) = self.last_sign {
            if current_sign != last && self.cumulative.abs() > 100 {
                // Sign changed and delta is meaningful (not just noise at 0)
                let (from, to) = if current_sign {
                    (TradeSide::Sell, TradeSide::Buy)
                } else {
                    (TradeSide::Buy, TradeSide::Sell)
                };
                events.push(FlowEvent::DeltaFlip {
                    from,
                    to,
                    cvd_at_flip: self.cumulative,
                    timestamp: tick.timestamp,
                });
            }
        }
        self.last_sign = Some(current_sign);

        // Check for large trade
        if tick.size >= self.config.large_trade_threshold && tick.side != TradeSide::Unknown {
            events.push(FlowEvent::LargeTrade {
                price: tick.price,
                size: tick.size,
                side: tick.side,
                timestamp: tick.timestamp,
            });
        }

        events
    }

    /// Sum signed volume within a rolling window ending at `now`.
    fn rolling_delta(&self, now: DateTime<Utc>, window_secs: i64) -> i64 {
        let cutoff = now - Duration::seconds(window_secs);
        self.recent_deltas
            .iter()
            .filter(|e| e.timestamp >= cutoff)
            .map(|e| e.signed_volume)
            .sum()
    }

    /// Get the current cumulative delta value.
    pub fn current_cvd(&self) -> i64 {
        self.cumulative
    }

    /// Reset CVD (e.g., at start of new trading day).
    pub fn reset(&mut self) {
        self.cumulative = 0;
        self.recent_deltas.clear();
        self.last_sign = None;
        self.ticks_processed = 0;
    }

    pub fn ticks_processed(&self) -> u64 {
        self.ticks_processed
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::TickSource;

    fn make_tick(price: f64, size: u64, side: TradeSide) -> ClassifiedTick {
        ClassifiedTick {
            price,
            size,
            side,
            timestamp: Utc::now(),
            source: TickSource::ThetaData,
        }
    }

    #[test]
    fn test_cvd_accumulation() {
        let mut cvd = CvdCalculator::new(CvdConfig::default());

        cvd.process_tick(&make_tick(562.35, 100, TradeSide::Buy));
        assert_eq!(cvd.current_cvd(), 100);

        cvd.process_tick(&make_tick(562.34, 200, TradeSide::Sell));
        assert_eq!(cvd.current_cvd(), -100);

        cvd.process_tick(&make_tick(562.36, 50, TradeSide::Buy));
        assert_eq!(cvd.current_cvd(), -50);
    }

    #[test]
    fn test_large_trade_detection() {
        let config = CvdConfig {
            large_trade_threshold: 500,
            ..Default::default()
        };
        let mut cvd = CvdCalculator::new(config);

        let events = cvd.process_tick(&make_tick(562.35, 1000, TradeSide::Buy));

        let has_large = events.iter().any(|e| matches!(e, FlowEvent::LargeTrade { .. }));
        assert!(has_large, "Should detect large trade of 1000 shares");
    }

    #[test]
    fn test_delta_flip_detection() {
        let mut cvd = CvdCalculator::new(CvdConfig::default());

        // Push CVD positive
        cvd.process_tick(&make_tick(562.35, 500, TradeSide::Buy));
        assert_eq!(cvd.current_cvd(), 500);

        // Push CVD negative (flip)
        let events = cvd.process_tick(&make_tick(562.30, 1000, TradeSide::Sell));

        let has_flip = events.iter().any(|e| matches!(e, FlowEvent::DeltaFlip { .. }));
        assert!(has_flip, "Should detect delta flip from positive to negative");
    }

    #[test]
    fn test_reset() {
        let mut cvd = CvdCalculator::new(CvdConfig::default());
        cvd.process_tick(&make_tick(562.35, 100, TradeSide::Buy));
        assert_eq!(cvd.current_cvd(), 100);

        cvd.reset();
        assert_eq!(cvd.current_cvd(), 0);
        assert_eq!(cvd.ticks_processed(), 0);
    }
}
