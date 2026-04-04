//! Signal detectors: imbalance, sweep, absorption.
//!
//! These run on every tick after the footprint and CVD are updated,
//! checking for actionable order flow patterns.

use crate::events::{price_to_level, ClassifiedTick, FlowEvent, PriceLevel, TradeSide};
use chrono::{DateTime, Duration, Utc};
use std::collections::{BTreeMap, VecDeque};

// ─────────────────────────────────────────────────────────────────────────────
// Imbalance Detector
// ─────────────────────────────────────────────────────────────────────────────

/// Detects bid/ask volume imbalances at price levels.
/// Stacked imbalances (3+ consecutive levels with same-side imbalance)
/// indicate strong directional conviction.
pub struct ImbalanceDetector {
    /// Minimum ratio for imbalance (e.g., 3.0 = 3:1 ask:bid or bid:ask)
    pub min_ratio: f64,
    /// Minimum consecutive levels for "stacked" imbalance
    pub min_stacked: u32,
    /// Minimum volume at a level to consider (filters noise)
    pub min_level_volume: u64,
}

impl Default for ImbalanceDetector {
    fn default() -> Self {
        Self {
            min_ratio: 3.0,
            min_stacked: 3,
            min_level_volume: 50,
        }
    }
}

impl ImbalanceDetector {
    /// Check footprint levels for imbalances. Returns events for any detected.
    ///
    /// `levels` = sorted list of (price_level, bid_vol, ask_vol) from footprint.
    pub fn check(&self, levels: &[(PriceLevel, u64, u64)], timestamp: DateTime<Utc>) -> Vec<FlowEvent> {
        let mut events = Vec::new();

        // Track consecutive imbalances for stacking
        let mut buy_stack: Vec<(PriceLevel, f64)> = Vec::new();
        let mut sell_stack: Vec<(PriceLevel, f64)> = Vec::new();

        for &(price, bid_vol, ask_vol) in levels {
            let total = bid_vol + ask_vol;
            if total < self.min_level_volume {
                // Reset stacks at low-volume levels
                self.maybe_emit_stacked(&buy_stack, TradeSide::Buy, timestamp, &mut events);
                self.maybe_emit_stacked(&sell_stack, TradeSide::Sell, timestamp, &mut events);
                buy_stack.clear();
                sell_stack.clear();
                continue;
            }

            // Check buy imbalance (ask_vol >> bid_vol = aggressive buyers)
            if bid_vol > 0 {
                let buy_ratio = ask_vol as f64 / bid_vol as f64;
                if buy_ratio >= self.min_ratio {
                    buy_stack.push((price, buy_ratio));
                    // Reset sell stack since this level is buy-imbalanced
                    self.maybe_emit_stacked(&sell_stack, TradeSide::Sell, timestamp, &mut events);
                    sell_stack.clear();
                    continue;
                }
            } else if ask_vol >= self.min_level_volume {
                // No bid volume at all = extreme buy imbalance
                buy_stack.push((price, f64::INFINITY));
                self.maybe_emit_stacked(&sell_stack, TradeSide::Sell, timestamp, &mut events);
                sell_stack.clear();
                continue;
            }

            // Check sell imbalance (bid_vol >> ask_vol = aggressive sellers)
            if ask_vol > 0 {
                let sell_ratio = bid_vol as f64 / ask_vol as f64;
                if sell_ratio >= self.min_ratio {
                    sell_stack.push((price, sell_ratio));
                    self.maybe_emit_stacked(&buy_stack, TradeSide::Buy, timestamp, &mut events);
                    buy_stack.clear();
                    continue;
                }
            } else if bid_vol >= self.min_level_volume {
                sell_stack.push((price, f64::INFINITY));
                self.maybe_emit_stacked(&buy_stack, TradeSide::Buy, timestamp, &mut events);
                buy_stack.clear();
                continue;
            }

            // No imbalance at this level — flush stacks
            self.maybe_emit_stacked(&buy_stack, TradeSide::Buy, timestamp, &mut events);
            self.maybe_emit_stacked(&sell_stack, TradeSide::Sell, timestamp, &mut events);
            buy_stack.clear();
            sell_stack.clear();
        }

        // Flush remaining stacks
        self.maybe_emit_stacked(&buy_stack, TradeSide::Buy, timestamp, &mut events);
        self.maybe_emit_stacked(&sell_stack, TradeSide::Sell, timestamp, &mut events);

        events
    }

    fn maybe_emit_stacked(
        &self,
        stack: &[(PriceLevel, f64)],
        side: TradeSide,
        timestamp: DateTime<Utc>,
        events: &mut Vec<FlowEvent>,
    ) {
        if stack.len() as u32 >= self.min_stacked {
            let mid_idx = stack.len() / 2;
            let avg_ratio: f64 = stack.iter().map(|(_, r)| r.min(100.0)).sum::<f64>() / stack.len() as f64;
            events.push(FlowEvent::Imbalance {
                price: stack[mid_idx].0.into_inner(),
                side,
                ratio: (avg_ratio * 10.0).round() / 10.0,
                stacked: stack.len() as u32,
                timestamp,
            });
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Sweep Detector
// ─────────────────────────────────────────────────────────────────────────────

/// Detects large aggressive orders sweeping across multiple price levels
/// in rapid succession. Shows urgency from an institutional participant.
pub struct SweepDetector {
    /// Minimum total size across levels to qualify as a sweep
    pub min_total_size: u64,
    /// Max time window to group ticks into a sweep (milliseconds)
    pub window_ms: i64,
    /// Minimum number of price levels hit
    pub min_levels: u32,
    /// Recent aggressive ticks for grouping
    recent_ticks: VecDeque<SweepCandidate>,
}

#[derive(Debug, Clone)]
struct SweepCandidate {
    price: f64,
    size: u64,
    side: TradeSide,
    timestamp: DateTime<Utc>,
    level: PriceLevel,
}

impl Default for SweepDetector {
    fn default() -> Self {
        Self {
            min_total_size: 2000,
            window_ms: 500,
            min_levels: 2,
            recent_ticks: VecDeque::with_capacity(100),
        }
    }
}

impl SweepDetector {
    /// Process a classified tick. Returns a Sweep event if detected.
    pub fn process_tick(&mut self, tick: &ClassifiedTick) -> Option<FlowEvent> {
        if tick.side == TradeSide::Unknown {
            return None;
        }

        let level = price_to_level(tick.price, 0.01);

        self.recent_ticks.push_back(SweepCandidate {
            price: tick.price,
            size: tick.size,
            side: tick.side,
            timestamp: tick.timestamp,
            level,
        });

        // Prune old entries
        let cutoff = tick.timestamp - Duration::milliseconds(self.window_ms);
        while let Some(front) = self.recent_ticks.front() {
            if front.timestamp < cutoff {
                self.recent_ticks.pop_front();
            } else {
                break;
            }
        }

        // Check for sweep: same side, multiple levels, large total size
        for side in [TradeSide::Buy, TradeSide::Sell] {
            let same_side: Vec<&SweepCandidate> = self
                .recent_ticks
                .iter()
                .filter(|t| t.side == side)
                .collect();

            let total_size: u64 = same_side.iter().map(|t| t.size).sum();
            let unique_levels: std::collections::HashSet<PriceLevel> =
                same_side.iter().map(|t| t.level).collect();

            if total_size >= self.min_total_size && unique_levels.len() as u32 >= self.min_levels {
                // Found a sweep — emit event and clear window to avoid duplicates
                let avg_price = same_side.iter().map(|t| t.price).sum::<f64>() / same_side.len() as f64;
                self.recent_ticks.clear();

                return Some(FlowEvent::Sweep {
                    price: (avg_price * 100.0).round() / 100.0,
                    size: total_size,
                    side,
                    levels_hit: unique_levels.len() as u32,
                    timestamp: tick.timestamp,
                });
            }
        }

        None
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Absorption Detector
// ─────────────────────────────────────────────────────────────────────────────

/// Detects absorption: high volume traded at a price level where price does
/// NOT break through. This means a large participant is absorbing all the
/// aggression — a reversal signal.
pub struct AbsorptionDetector {
    /// Minimum volume at a level to be considered absorption
    pub min_volume: u64,
    /// How long price must stay at/above the level to confirm absorption (seconds)
    pub hold_seconds: i64,
    /// Track volume at watched levels
    level_volume: BTreeMap<PriceLevel, LevelWatch>,
}

#[derive(Debug, Clone)]
struct LevelWatch {
    total_volume: u64,
    side: TradeSide,
    first_seen: DateTime<Utc>,
    last_seen: DateTime<Utc>,
    emitted: bool,
}

impl Default for AbsorptionDetector {
    fn default() -> Self {
        Self {
            min_volume: 5000,
            hold_seconds: 10,
            level_volume: BTreeMap::new(),
        }
    }
}

impl AbsorptionDetector {
    /// Process a classified tick. Returns Absorption event if detected.
    pub fn process_tick(&mut self, tick: &ClassifiedTick) -> Option<FlowEvent> {
        let level = price_to_level(tick.price, 0.01);

        // Update or create watch entry
        let entry = self.level_volume.entry(level).or_insert_with(|| LevelWatch {
            total_volume: 0,
            side: tick.side,
            first_seen: tick.timestamp,
            last_seen: tick.timestamp,
            emitted: false,
        });

        entry.total_volume += tick.size;
        entry.last_seen = tick.timestamp;

        // Check if this level qualifies as absorption
        if !entry.emitted
            && entry.total_volume >= self.min_volume
            && (entry.last_seen - entry.first_seen).num_seconds() >= self.hold_seconds
        {
            entry.emitted = true;
            return Some(FlowEvent::Absorption {
                price: level.into_inner(),
                volume: entry.total_volume,
                side: entry.side,
                held: true,
                timestamp: tick.timestamp,
            });
        }

        // Prune very old levels (> 5 min)
        let cutoff = tick.timestamp - Duration::seconds(300);
        self.level_volume.retain(|_, v| v.last_seen >= cutoff);

        None
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
    fn test_imbalance_stacked_detection() {
        let detector = ImbalanceDetector {
            min_ratio: 3.0,
            min_stacked: 3,
            min_level_volume: 10,
        };

        let levels = vec![
            (OrderedFloat(562.30), 10u64, 50u64), // 5:1 buy
            (OrderedFloat(562.31), 10u64, 40u64), // 4:1 buy
            (OrderedFloat(562.32), 10u64, 35u64), // 3.5:1 buy
        ];

        let events = detector.check(&levels, Utc::now());
        assert!(!events.is_empty(), "Should detect stacked buy imbalance");

        if let FlowEvent::Imbalance { side, stacked, .. } = &events[0] {
            assert_eq!(*side, TradeSide::Buy);
            assert_eq!(*stacked, 3);
        } else {
            panic!("Expected Imbalance event");
        }
    }

    #[test]
    fn test_sweep_detection() {
        let mut detector = SweepDetector {
            min_total_size: 500,
            window_ms: 1000,
            min_levels: 2,
            recent_ticks: VecDeque::new(),
        };

        let now = Utc::now();
        let t1 = ClassifiedTick {
            price: 562.35,
            size: 300,
            side: TradeSide::Buy,
            timestamp: now,
            source: TickSource::ThetaData,
        };
        let t2 = ClassifiedTick {
            price: 562.36,
            size: 300,
            side: TradeSide::Buy,
            timestamp: now + Duration::milliseconds(50),
            source: TickSource::ThetaData,
        };

        detector.process_tick(&t1);
        let result = detector.process_tick(&t2);

        assert!(result.is_some(), "Should detect sweep across 2 levels");
        if let Some(FlowEvent::Sweep { levels_hit, size, .. }) = result {
            assert_eq!(levels_hit, 2);
            assert_eq!(size, 600);
        }
    }
}
