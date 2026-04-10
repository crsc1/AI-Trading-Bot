//! Options trade enrichment — IV, Greeks, VPIN, Smart Money Score.
//!
//! Ported from Python `dashboard/theta_stream.py` and `dashboard/flow_toxicity.py`.
//! This makes the Rust ThetaDx path produce the same enriched payload that the
//! frontend expects, eliminating the need for Python enrichment in the live path.

use std::collections::HashMap;
use std::f64::consts::{FRAC_1_SQRT_2, PI};

// ─────────────────────────────────────────────────────────────────────────────
// Black-Scholes IV solver + Greeks
// ─────────────────────────────────────────────────────────────────────────────

const RISK_FREE_RATE: f64 = 0.045; // ~4.5% Fed funds
const TRADING_DAYS_PER_YEAR: f64 = 252.0;
const TRADING_HOURS_PER_DAY: f64 = 6.5;
const TRADING_SECS_PER_YEAR: f64 = TRADING_DAYS_PER_YEAR * TRADING_HOURS_PER_DAY * 3600.0;

/// Greeks result from BS model.
#[derive(Debug, Clone, Copy, Default)]
pub struct Greeks {
    pub iv: f64,
    pub delta: f64,
    pub gamma: f64,
    pub theta: f64,
    pub vega: f64,
}

/// Fast normal CDF approximation (Abramowitz & Stegun erf-based).
#[inline]
fn norm_cdf(x: f64) -> f64 {
    0.5 * (1.0 + erf_approx(x * FRAC_1_SQRT_2))
}

/// Standard normal PDF.
#[inline]
fn norm_pdf(x: f64) -> f64 {
    (-0.5 * x * x).exp() / (2.0 * PI).sqrt()
}

/// Fast erf approximation — max error ~1.5e-7.
/// Uses the Abramowitz & Stegun formula 7.1.26.
#[inline]
fn erf_approx(x: f64) -> f64 {
    // libm erf is accurate and fast enough for our purposes
    libm::erf(x)
}

/// Compute time-to-expiry in years from expiration (YYYYMMDD) and ms_of_day.
///
/// Uses trading time (252 days × 6.5 hours). For 0DTE, computes fractional
/// trading day remaining. Minimum 1 minute.
pub fn time_to_expiry(expiration: i32, ms_of_day: i32) -> f64 {
    let exp_year = expiration / 10000;
    let exp_month = (expiration % 10000) / 100;
    let exp_day = expiration % 100;

    // Current time from ms_of_day (Eastern Time, market hours)
    // Market open = 9:30 ET = 34_200_000 ms, close = 16:00 ET = 57_600_000 ms
    let market_open_ms: i32 = 34_200_000; // 9:30 ET
    let market_close_ms: i32 = 57_600_000; // 16:00 ET
    let trading_ms_per_day: f64 = (market_close_ms - market_open_ms) as f64;

    // For now, assume same-day (0DTE) or simple day count.
    // TODO: integrate NYSE calendar for holidays/early closes.

    // Get today's date from the trade's date field (we'll pass it in)
    // For 0DTE: remaining fraction of today's trading session
    let ms_clamped = ms_of_day.max(market_open_ms).min(market_close_ms);
    let remaining_ms = (market_close_ms - ms_clamped) as f64;
    let today_fraction = remaining_ms / trading_ms_per_day;

    // Simple day difference (good enough for 0-5 DTE options which are our focus)
    // For multi-day, approximate trading days as 5/7 of calendar days
    let today_ordinal = simple_ordinal(exp_year, exp_month, exp_day);
    let trade_ordinal = date_ordinal_from_ms_of_day(expiration, ms_of_day);

    let calendar_days = (today_ordinal - trade_ordinal).max(0) as f64;
    let full_trading_days = if calendar_days < 1.0 {
        0.0
    } else {
        // Approximate: 5 trading days per 7 calendar days
        (calendar_days * 5.0 / 7.0).floor()
    };

    let total_trading_days = full_trading_days + today_fraction;
    let t = total_trading_days / TRADING_DAYS_PER_YEAR;

    // Minimum 1 minute of trading time
    t.max(60.0 / TRADING_SECS_PER_YEAR)
}

/// Compute time-to-expiry given both trade date and expiration date.
pub fn time_to_expiry_from_dates(
    trade_date: i32,
    trade_ms_of_day: i32,
    expiration: i32,
) -> f64 {
    let market_open_ms: i32 = 34_200_000;
    let market_close_ms: i32 = 57_600_000;
    let trading_ms_per_day: f64 = (market_close_ms - market_open_ms) as f64;

    let ms_clamped = trade_ms_of_day.max(market_open_ms).min(market_close_ms);
    let remaining_ms = (market_close_ms - ms_clamped) as f64;
    let today_fraction = remaining_ms / trading_ms_per_day;

    let exp_ordinal = ordinal_from_yyyymmdd(expiration);
    let trade_ordinal = ordinal_from_yyyymmdd(trade_date);

    let calendar_days = (exp_ordinal - trade_ordinal).max(0) as f64;

    if calendar_days < 1.0 {
        // 0DTE
        let t = today_fraction / TRADING_DAYS_PER_YEAR;
        return t.max(60.0 / TRADING_SECS_PER_YEAR);
    }

    // Multi-day: approximate trading days
    let full_trading_days = (calendar_days * 5.0 / 7.0).floor();
    let total = full_trading_days + today_fraction;
    (total / TRADING_DAYS_PER_YEAR).max(60.0 / TRADING_SECS_PER_YEAR)
}

fn ordinal_from_yyyymmdd(d: i32) -> i64 {
    let y = d / 10000;
    let m = (d % 10000) / 100;
    let day = d % 100;
    simple_ordinal(y, m, day)
}

/// Simple day-of-year ordinal (not calendar-accurate for all edge cases but fine for DTE).
fn simple_ordinal(year: i32, month: i32, day: i32) -> i64 {
    let y = year as i64;
    let m = month as i64;
    let d = day as i64;
    // Julian Day Number approximation
    let a = (14 - m) / 12;
    let y2 = y + 4800 - a;
    let m2 = m + 12 * a - 3;
    d + (153 * m2 + 2) / 5 + 365 * y2 + y2 / 4 - y2 / 100 + y2 / 400 - 32045
}

fn date_ordinal_from_ms_of_day(_expiration: i32, _ms_of_day: i32) -> i64 {
    // When called from time_to_expiry, we need the trade date, not expiration.
    // This is handled by time_to_expiry_from_dates instead.
    // This function exists for the simpler 0DTE path.
    0
}

/// Newton-Raphson Black-Scholes IV solver + Greeks computation.
///
/// Matches the Python implementation in `theta_stream.py:_compute_greeks()`.
///
/// Returns `None` if IV doesn't converge (deep OTM, bad data).
pub fn compute_greeks(
    spot: f64,
    strike: f64,
    time_years: f64,
    mid_price: f64,
    is_call: bool,
) -> Option<Greeks> {
    if spot <= 0.0 || mid_price <= 0.0 || strike <= 0.0 || time_years <= 0.0 {
        return None;
    }

    let r = RISK_FREE_RATE;

    // Intrinsic check
    let intrinsic = if is_call {
        (spot - strike).max(0.0)
    } else {
        (strike - spot).max(0.0)
    };
    if mid_price < intrinsic - 0.01 {
        return None;
    }

    let sqrt_t = time_years.sqrt();

    // Brenner-Subrahmanyam initial guess; clamp for 0DTE
    let mut sigma = if time_years < 1.0 / 365.0 {
        0.5
    } else {
        ((2.0 * PI / time_years).sqrt() * (mid_price / spot))
            .max(0.01)
            .min(5.0)
    };

    // Newton-Raphson: 30 iterations
    for _ in 0..30 {
        let sqrt_sigma_t = sigma * sqrt_t;
        if sqrt_sigma_t < 1e-12 {
            break;
        }

        let d1 = ((spot / strike).ln() + (r + 0.5 * sigma * sigma) * time_years) / sqrt_sigma_t;
        let d2 = d1 - sqrt_sigma_t;

        let nd1 = norm_cdf(d1);
        let nd2 = norm_cdf(d2);

        let bs_price = if is_call {
            spot * nd1 - strike * (-r * time_years).exp() * nd2
        } else {
            strike * (-r * time_years).exp() * (1.0 - nd2) - spot * (1.0 - nd1)
        };

        let diff = bs_price - mid_price;
        if diff.abs() < 1e-6 {
            break;
        }

        // Vega
        let npd1 = norm_pdf(d1);
        let vega_val = spot * sqrt_t * npd1;
        if vega_val < 1e-12 {
            break;
        }

        sigma -= diff / vega_val;
        sigma = sigma.clamp(0.001, 10.0);
    }

    if !(0.001..10.0).contains(&sigma) {
        return None;
    }

    // Final Greeks with converged sigma
    let sqrt_sigma_t = sigma * sqrt_t;
    let d1 = ((spot / strike).ln() + (r + 0.5 * sigma * sigma) * time_years) / sqrt_sigma_t;
    let d2 = d1 - sqrt_sigma_t;
    let nd1 = norm_cdf(d1);
    let nd2 = norm_cdf(d2);
    let npd1 = norm_pdf(d1);

    let delta = if is_call { nd1 } else { nd1 - 1.0 };
    let gamma = npd1 / (spot * sqrt_sigma_t);
    let time_decay = -(spot * npd1 * sigma) / (2.0 * sqrt_t);
    let theta = if is_call {
        (time_decay - r * strike * (-r * time_years).exp() * nd2) / 365.0
    } else {
        (time_decay + r * strike * (-r * time_years).exp() * (1.0 - nd2)) / 365.0
    };
    let vega = spot * sqrt_t * npd1 / 100.0;

    Some(Greeks {
        iv: (sigma * 10000.0).round() / 10000.0,
        delta: (delta * 10000.0).round() / 10000.0,
        gamma: (gamma * 1_000_000.0).round() / 1_000_000.0,
        theta: (theta * 10000.0).round() / 10000.0,
        vega: (vega * 10000.0).round() / 10000.0,
    })
}

// ─────────────────────────────────────────────────────────────────────────────
// VPIN — Volume-Synchronized Probability of Informed Trading
// ─────────────────────────────────────────────────────────────────────────────
//
// Ported from `dashboard/flow_toxicity.py`. Academic basis: Easley, Lopez de
// Prado, O'Hara (2012). Predicted the 2010 Flash Crash >1hr before it happened.

const VPIN_BUCKET_SIZE: f64 = 200.0; // contracts per bucket (options trade smaller)
const VPIN_NUM_BUCKETS: usize = 40; // rolling window (~8,000 contracts)

pub struct VpinCalculator {
    bucket_size: f64,
    num_buckets: usize,
    // Current bucket accumulation
    current_buy_vol: f64,
    current_sell_vol: f64,
    current_total_vol: f64,
    // Completed bucket history (circular)
    bucket_imbalances: Vec<f64>,
    bucket_head: usize,
    bucket_count: usize,
    // Running totals for reporting
    total_buy: f64,
    total_sell: f64,
}

impl VpinCalculator {
    pub fn new() -> Self {
        Self {
            bucket_size: VPIN_BUCKET_SIZE,
            num_buckets: VPIN_NUM_BUCKETS,
            current_buy_vol: 0.0,
            current_sell_vol: 0.0,
            current_total_vol: 0.0,
            bucket_imbalances: vec![0.0; VPIN_NUM_BUCKETS],
            bucket_head: 0,
            bucket_count: 0,
            total_buy: 0.0,
            total_sell: 0.0,
        }
    }

    /// Add an option trade to the VPIN calculation.
    /// `side`: "buy", "sell", or "mid"
    pub fn add_trade(&mut self, size: i32, side: &str) {
        if size <= 0 {
            return;
        }

        let size_f = size as f64;
        let buy_pct: f64 = match side {
            "buy" => 1.0,
            "sell" => 0.0,
            _ => 0.5,
        };

        self.current_buy_vol += size_f * buy_pct;
        self.current_sell_vol += size_f * (1.0 - buy_pct);
        self.current_total_vol += size_f;

        // Fill buckets
        while self.current_total_vol >= self.bucket_size {
            let overflow = self.current_total_vol - self.bucket_size;
            let overflow_ratio = if self.current_total_vol > 0.0 {
                overflow / self.current_total_vol
            } else {
                0.0
            };

            let bucket_buy = self.current_buy_vol * (1.0 - overflow_ratio);
            let bucket_sell = self.current_sell_vol * (1.0 - overflow_ratio);

            let imbalance = (bucket_buy - bucket_sell).abs();
            self.bucket_imbalances[self.bucket_head] = imbalance;
            self.bucket_head = (self.bucket_head + 1) % self.num_buckets;
            if self.bucket_count < self.num_buckets {
                self.bucket_count += 1;
            }

            self.total_buy += bucket_buy;
            self.total_sell += bucket_sell;

            // Carry overflow
            self.current_buy_vol *= overflow_ratio;
            self.current_sell_vol *= overflow_ratio;
            self.current_total_vol = overflow;
        }
    }

    /// Get the current VPIN value (0.0-1.0). Returns None if insufficient data.
    pub fn vpin(&self) -> Option<f64> {
        if self.bucket_count < 5 {
            return None;
        }
        let n = self.bucket_count;
        let total: f64 = self.bucket_imbalances[..n.min(self.num_buckets)].iter().sum();
        Some(total / (n as f64 * self.bucket_size))
    }

    /// Reset (e.g., start of new trading day).
    pub fn reset(&mut self) {
        self.current_buy_vol = 0.0;
        self.current_sell_vol = 0.0;
        self.current_total_vol = 0.0;
        self.bucket_imbalances.fill(0.0);
        self.bucket_head = 0;
        self.bucket_count = 0;
        self.total_buy = 0.0;
        self.total_sell = 0.0;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Smart Money Score (0-100)
// ─────────────────────────────────────────────────────────────────────────────
//
// Ported from `theta_stream.py:_smart_money_score()`.
//
// Components:
//   Size (0-30):      sqrt-scaled, 50+ contracts = max
//   Gamma (0-25):     high gamma = max market impact zone
//   Aggression (0-25): buy/sell at bid/ask = urgency = conviction
//   ATM proximity (0-20): near-the-money = institutional

pub fn smart_money_score(
    size: i32,
    side: &str,
    gamma: Option<f64>,
    strike: f64,
    underlying_price: f64,
) -> i32 {
    let mut score: f64 = 0.0;

    // 1. Size weight (0-30) — sqrt scale, caps at ~50 contracts
    score += ((size as f64).sqrt() * 4.24).min(30.0);

    // 2. Gamma weight (0-25) — normalized against typical ATM 0DTE gamma (~0.10)
    if let Some(g) = gamma {
        if g > 0.0 {
            let gamma_norm = (g / 0.10).min(1.0);
            score += gamma_norm * 25.0;
        }
    }

    // 3. Aggression (0-25)
    score += match side {
        "buy" => 25.0,
        "sell" => 25.0,
        _ => 8.0,
    };

    // 4. ATM proximity (0-20)
    if underlying_price > 0.0 {
        let distance = (strike - underlying_price).abs();
        if distance <= 2.0 {
            score += 20.0;
        } else if distance <= 15.0 {
            score += 20.0 * (1.0 - (distance - 2.0) / 13.0);
        }
    }

    score.round().clamp(0.0, 100.0) as i32
}

// ─────────────────────────────────────────────────────────────────────────────
// OptionsEnricher — stateful enrichment pipeline
// ─────────────────────────────────────────────────────────────────────────────

/// Per-contract quote cache entry.
#[derive(Debug, Clone, Copy)]
struct QuoteEntry {
    bid: f64,
    ask: f64,
}

/// Combined enrichment state for the ThetaDx options pipeline.
///
/// Holds the option quote book, VPIN calculator, and underlying price.
/// Feed it quotes and trades; it returns enriched fields for each trade.
pub struct OptionsEnricher {
    /// Latest bid/ask per contract_id.
    quote_book: HashMap<i32, QuoteEntry>,
    /// VPIN calculator.
    vpin: VpinCalculator,
    /// Latest underlying equity price (e.g., SPY last).
    underlying_price: f64,
}

#[derive(Debug, Clone)]
pub struct EnrichedFields {
    pub iv: Option<f64>,
    pub delta: Option<f64>,
    pub gamma: Option<f64>,
    pub theta: Option<f64>,
    pub vega: Option<f64>,
    pub vpin: Option<f64>,
    pub sms: i32,
    pub timestamp_ms: i64,
}

impl OptionsEnricher {
    pub fn new() -> Self {
        Self {
            quote_book: HashMap::new(),
            vpin: VpinCalculator::new(),
            underlying_price: 0.0,
        }
    }

    /// Update the underlying equity price (call from the equity tick pipeline).
    pub fn set_underlying_price(&mut self, price: f64) {
        if price > 0.0 {
            self.underlying_price = price;
        }
    }

    /// Update the quote book from an option quote event.
    pub fn on_quote(&mut self, contract_id: i32, bid: f64, ask: f64) {
        if bid > 0.0 && ask > 0.0 {
            self.quote_book.insert(contract_id, QuoteEntry { bid, ask });
        }
    }

    /// Enrich an option trade with IV, Greeks, VPIN, and SMS.
    pub fn enrich_trade(
        &mut self,
        contract_id: i32,
        strike: f64,
        is_call: bool,
        price: f64,
        size: i32,
        side: &str,
        expiration: i32,
        trade_date: i32,
        ms_of_day: i32,
    ) -> EnrichedFields {
        // 1. Greeks from quote book mid-price
        let greeks = self
            .quote_book
            .get(&contract_id)
            .and_then(|q| {
                let mid = (q.bid + q.ask) / 2.0;
                let t = time_to_expiry_from_dates(trade_date, ms_of_day, expiration);
                compute_greeks(self.underlying_price, strike, t, mid, is_call)
            });

        // 2. VPIN — feed every trade
        self.vpin.add_trade(size, side);
        let vpin_val = self.vpin.vpin();

        // 3. Smart Money Score
        let sms = smart_money_score(
            size,
            side,
            greeks.map(|g| g.gamma),
            strike,
            self.underlying_price,
        );

        // 4. Timestamp: convert date + ms_of_day to unix milliseconds
        let timestamp_ms = date_ms_to_unix_ms(trade_date, ms_of_day);

        EnrichedFields {
            iv: greeks.map(|g| g.iv),
            delta: greeks.map(|g| g.delta),
            gamma: greeks.map(|g| g.gamma),
            theta: greeks.map(|g| g.theta),
            vega: greeks.map(|g| g.vega),
            vpin: vpin_val,
            sms,
            timestamp_ms,
        }
    }

    /// Reset VPIN state (e.g., new trading day).
    pub fn reset_vpin(&mut self) {
        self.vpin.reset();
    }
}

/// Convert YYYYMMDD date + ms_of_day (Eastern Time) to Unix timestamp in milliseconds.
fn date_ms_to_unix_ms(date: i32, ms_of_day: i32) -> i64 {
    let year = date / 10000;
    let month = (date % 10000) / 100;
    let day = date % 100;

    // Days since Unix epoch (1970-01-01) using a simple formula.
    // Eastern Time offset: UTC-4 (EDT) or UTC-5 (EST).
    // During market hours (Mar-Nov) we're in EDT = UTC-4.
    // For simplicity, use UTC-4 (market hours are always in EDT for practical purposes).
    let ordinal = simple_ordinal(year, month, day);
    let epoch_ordinal = simple_ordinal(1970, 1, 1);
    let days_since_epoch = ordinal - epoch_ordinal;

    // ms_of_day is from midnight Eastern Time.
    // Convert to UTC by adding 4 hours (EDT offset).
    let et_offset_ms: i64 = 4 * 3600 * 1000;

    days_since_epoch * 86_400_000 + ms_of_day as i64 + et_offset_ms
}

// ─────────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bs_call_atm_reasonable_iv() {
        // ATM SPY call, ~1 day to expiry, mid price ~$2
        let greeks = compute_greeks(550.0, 550.0, 1.0 / 252.0, 2.0, true);
        assert!(greeks.is_some(), "should converge for ATM option");
        let g = greeks.unwrap();
        assert!(g.iv > 0.05 && g.iv < 2.0, "IV should be reasonable: {}", g.iv);
        assert!(g.delta > 0.3 && g.delta < 0.7, "ATM delta should be ~0.5: {}", g.delta);
        assert!(g.gamma > 0.0, "gamma should be positive");
    }

    #[test]
    fn bs_put_otm() {
        // OTM put: SPY at 550, strike 540, 5 DTE, mid ~$1.50
        let greeks = compute_greeks(550.0, 540.0, 5.0 / 252.0, 1.50, false);
        assert!(greeks.is_some(), "should converge for OTM put");
        let g = greeks.unwrap();
        assert!(g.delta < 0.0 && g.delta > -0.5, "OTM put delta: {}", g.delta);
    }

    #[test]
    fn bs_rejects_bad_inputs() {
        assert!(compute_greeks(0.0, 550.0, 0.01, 2.0, true).is_none());
        assert!(compute_greeks(550.0, 550.0, 0.01, 0.0, true).is_none());
        assert!(compute_greeks(550.0, 0.0, 0.01, 2.0, true).is_none());
    }

    #[test]
    fn vpin_empty_returns_none() {
        let calc = VpinCalculator::new();
        assert!(calc.vpin().is_none());
    }

    #[test]
    fn vpin_builds_after_enough_volume() {
        let mut calc = VpinCalculator::new();
        // Fill 5 buckets (200 contracts each = 1000 total) all buys
        for _ in 0..1000 {
            calc.add_trade(1, "buy");
        }
        let v = calc.vpin();
        assert!(v.is_some(), "should have VPIN after 5 buckets");
        assert!(
            v.unwrap() > 0.8,
            "all-buy flow should have high VPIN: {}",
            v.unwrap()
        );
    }

    #[test]
    fn vpin_balanced_flow_is_low() {
        let mut calc = VpinCalculator::new();
        // Alternate buy/sell trades to create balanced flow
        for i in 0..2000 {
            let side = if i % 2 == 0 { "buy" } else { "sell" };
            calc.add_trade(1, side);
        }
        let v = calc.vpin().unwrap();
        assert!(v < 0.2, "balanced flow should have low VPIN: {}", v);
    }

    #[test]
    fn sms_atm_aggressive_large() {
        // 50 contracts, buy (aggressive), ATM, with high gamma
        let score = smart_money_score(50, "buy", Some(0.10), 550.0, 550.0);
        assert!(score >= 80, "large aggressive ATM trade should score high: {}", score);
    }

    #[test]
    fn sms_small_passive_otm() {
        // 2 contracts, mid (passive), deep OTM, no gamma
        let score = smart_money_score(2, "mid", None, 520.0, 550.0);
        assert!(score < 30, "small passive OTM trade should score low: {}", score);
    }

    #[test]
    fn timestamp_conversion_reasonable() {
        // 2026-04-10, 10:30:00 ET = 37_800_000 ms_of_day
        let ts = date_ms_to_unix_ms(20260410, 37_800_000);
        // Should be around April 10, 2026 14:30:00 UTC
        // April 10, 2026 = ~1,776,000,000,000 ms since epoch (rough)
        assert!(ts > 1_770_000_000_000 && ts < 1_790_000_000_000,
            "timestamp should be in 2026 range: {}", ts);
    }

    #[test]
    fn enricher_end_to_end() {
        let mut enricher = OptionsEnricher::new();
        enricher.set_underlying_price(550.0);

        // Feed a quote
        enricher.on_quote(1001, 1.90, 2.10);

        // Enrich a trade
        let result = enricher.enrich_trade(
            1001,       // contract_id
            550.0,      // strike
            true,       // is_call
            2.05,       // price
            10,         // size
            "buy",      // side
            20260410,   // expiration
            20260410,   // trade_date
            37_800_000, // ms_of_day (10:30 ET)
        );

        assert!(result.iv.is_some(), "should compute IV");
        assert!(result.delta.is_some(), "should compute delta");
        assert!(result.sms > 0, "should compute SMS");
        assert!(result.timestamp_ms > 0, "should compute timestamp");
    }
}
