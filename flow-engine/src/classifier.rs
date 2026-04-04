//! Buy/sell trade classification using NBBO quotes.
//!
//! Primary method: compare trade price to last known bid/ask.
//!   - Trade at ask or above → BUY (aggressive buyer lifting offers)
//!   - Trade at bid or below → SELL (aggressive seller hitting bids)
//!   - Trade between bid/ask → use tick rule fallback
//!
//! Tick rule fallback: compare to previous trade price.
//!   - Price uptick → BUY
//!   - Price downtick → SELL
//!   - Same price → inherit previous classification

use crate::events::{ClassifiedTick, NbboQuote, RawTick, TradeSide};
use std::sync::RwLock;

/// Maintains quote state and classifies incoming trades.
pub struct TradeClassifier {
    /// Most recent NBBO quote
    last_quote: RwLock<Option<NbboQuote>>,
    /// Last trade price for tick rule fallback
    last_trade_price: RwLock<Option<f64>>,
    /// Last assigned side for tick rule (zero-tick case)
    last_side: RwLock<TradeSide>,
    /// Stats
    stats: RwLock<ClassifierStats>,
}

#[derive(Debug, Default)]
pub struct ClassifierStats {
    pub total_classified: u64,
    pub quote_classified: u64,
    pub tick_rule_classified: u64,
    pub unknown_classified: u64,
}

impl TradeClassifier {
    pub fn new() -> Self {
        Self {
            last_quote: RwLock::new(None),
            last_trade_price: RwLock::new(None),
            last_side: RwLock::new(TradeSide::Unknown),
            stats: RwLock::new(ClassifierStats::default()),
        }
    }

    /// Update the latest NBBO quote. Call this for every quote tick.
    pub fn update_quote(&self, quote: NbboQuote) {
        let mut q = self.last_quote.write().unwrap();
        *q = Some(quote);
    }

    /// Classify a raw trade tick into buy/sell.
    pub fn classify(&self, tick: &RawTick) -> ClassifiedTick {
        let side = self.determine_side(tick.price);

        // Update state for tick rule
        {
            let mut ltp = self.last_trade_price.write().unwrap();
            *ltp = Some(tick.price);
        }
        if side != TradeSide::Unknown {
            let mut ls = self.last_side.write().unwrap();
            *ls = side;
        }

        // Update stats
        {
            let mut stats = self.stats.write().unwrap();
            stats.total_classified += 1;
        }

        ClassifiedTick {
            price: tick.price,
            size: tick.size,
            side,
            timestamp: tick.timestamp,
            source: tick.source,
        }
    }

    fn determine_side(&self, price: f64) -> TradeSide {
        let quote = self.last_quote.read().unwrap();

        if let Some(ref q) = *quote {
            let mid = (q.bid + q.ask) / 2.0;
            let spread = q.ask - q.bid;

            // Only use quote classification if spread is reasonable (< $0.50)
            if spread > 0.0 && spread < 0.50 {
                if price >= q.ask {
                    self.stats.write().unwrap().quote_classified += 1;
                    return TradeSide::Buy;
                }
                if price <= q.bid {
                    self.stats.write().unwrap().quote_classified += 1;
                    return TradeSide::Sell;
                }
                // Between bid and ask — above midpoint leans buy, below leans sell
                if price > mid + 0.005 {
                    self.stats.write().unwrap().quote_classified += 1;
                    return TradeSide::Buy;
                }
                if price < mid - 0.005 {
                    self.stats.write().unwrap().quote_classified += 1;
                    return TradeSide::Sell;
                }
            }
        }

        // Fallback: tick rule
        self.tick_rule(price)
    }

    fn tick_rule(&self, price: f64) -> TradeSide {
        let ltp = self.last_trade_price.read().unwrap();
        let mut stats = self.stats.write().unwrap();

        match *ltp {
            Some(last_price) => {
                if price > last_price {
                    stats.tick_rule_classified += 1;
                    TradeSide::Buy
                } else if price < last_price {
                    stats.tick_rule_classified += 1;
                    TradeSide::Sell
                } else {
                    // Zero tick — inherit last side
                    let ls = self.last_side.read().unwrap();
                    stats.tick_rule_classified += 1;
                    *ls
                }
            }
            None => {
                stats.unknown_classified += 1;
                TradeSide::Unknown
            }
        }
    }

    pub fn get_stats(&self) -> ClassifierStats {
        let s = self.stats.read().unwrap();
        ClassifierStats {
            total_classified: s.total_classified,
            quote_classified: s.quote_classified,
            tick_rule_classified: s.tick_rule_classified,
            unknown_classified: s.unknown_classified,
        }
    }
}

impl Default for TradeClassifier {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::events::{TickSource, NbboQuote};
    use chrono::Utc;

    fn make_tick(price: f64, size: u64) -> RawTick {
        RawTick {
            price,
            size,
            timestamp: Utc::now(),
            conditions: vec![],
            source: TickSource::ThetaData,
        }
    }

    #[test]
    fn test_classify_at_ask_is_buy() {
        let c = TradeClassifier::new();
        c.update_quote(NbboQuote {
            bid: 562.30,
            ask: 562.35,
            bid_size: 100,
            ask_size: 200,
            timestamp: Utc::now(),
        });
        let result = c.classify(&make_tick(562.35, 100));
        assert_eq!(result.side, TradeSide::Buy);
    }

    #[test]
    fn test_classify_at_bid_is_sell() {
        let c = TradeClassifier::new();
        c.update_quote(NbboQuote {
            bid: 562.30,
            ask: 562.35,
            bid_size: 100,
            ask_size: 200,
            timestamp: Utc::now(),
        });
        let result = c.classify(&make_tick(562.30, 100));
        assert_eq!(result.side, TradeSide::Sell);
    }

    #[test]
    fn test_tick_rule_fallback() {
        let c = TradeClassifier::new();
        // No quote → tick rule
        let r1 = c.classify(&make_tick(562.30, 100));
        assert_eq!(r1.side, TradeSide::Unknown); // First tick, no reference

        let r2 = c.classify(&make_tick(562.35, 100));
        assert_eq!(r2.side, TradeSide::Buy); // Uptick

        let r3 = c.classify(&make_tick(562.32, 100));
        assert_eq!(r3.side, TradeSide::Sell); // Downtick
    }
}
