//! Tick ingestion from ThetaData Terminal v3 REST API.
//!
//! ThetaData runs a local Java process ("Theta Terminal") that exposes
//! a REST API on localhost:25503 (v3 default port).
//!
//! v3 Endpoints used:
//!   GET /v3/stock/list/symbols                  (Free tier — health check)
//!   GET /v3/stock/history/eod?symbol=SPY&...    (Free tier — EOD bars)
//!   GET /v3/stock/snapshot/quote?symbol=SPY     (Standard+ — real-time NBBO)
//!
//! Free tier:  EOD data only → synthetic tick replay
//! Standard:   Real-time NBBO polling → generates live ticks from quote changes
//!
//! The engine polls the quote snapshot every ~200ms. When the NBBO changes
//! (bid/ask price or size shift), it generates a RawTick that feeds the full
//! pipeline (footprint, CVD, detectors).

use crate::events::{NbboQuote, RawTick, TickSource};
use chrono::{DateTime, Utc};
use reqwest::Client;
use serde::Deserialize;
use std::time::Duration;
use tracing::{debug, error, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct IngestionConfig {
    /// ThetaData Terminal base URL (default: http://localhost:25503)
    pub theta_base_url: String,
    /// Polling interval in milliseconds
    pub poll_interval_ms: u64,
    /// Symbol to track
    pub symbol: String,
    /// Whether ThetaData is enabled
    pub theta_enabled: bool,
}

impl Default for IngestionConfig {
    fn default() -> Self {
        Self {
            theta_base_url: "http://localhost:25503".to_string(),
            poll_interval_ms: 200,
            symbol: "SPY".to_string(),
            theta_enabled: false,
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ThetaData v3 response types (JSON format)
// ─────────────────────────────────────────────────────────────────────────────

/// v3 EOD response
#[derive(Debug, Deserialize)]
struct ThetaV3EodResponse {
    response: Vec<ThetaV3EodBar>,
}

#[derive(Debug, Clone, Deserialize)]
struct ThetaV3EodBar {
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: u64,
    #[allow(dead_code)]
    count: Option<u64>,
    bid: Option<f64>,
    ask: Option<f64>,
    bid_size: Option<u64>,
    ask_size: Option<u64>,
    #[serde(default)]
    #[allow(dead_code)]
    last_trade: Option<String>,
}

/// v3 quote snapshot response (Standard+)
#[derive(Debug, Deserialize)]
struct ThetaV3QuoteResponse {
    response: Vec<ThetaV3Quote>,
}

#[derive(Debug, Clone, Deserialize)]
struct ThetaV3Quote {
    bid: f64,
    ask: f64,
    #[serde(default)]
    bid_size: Option<u64>,
    #[serde(default)]
    ask_size: Option<u64>,
    /// Milliseconds since midnight ET
    #[serde(default)]
    ms_of_day: Option<u64>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Last quote state — used to detect changes for tick generation
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
struct LastQuoteState {
    bid: f64,
    ask: f64,
    bid_size: u64,
    ask_size: u64,
    mid: f64,
}

// ─────────────────────────────────────────────────────────────────────────────
// Ingestion mode
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IngestionMode {
    /// Standard+ subscription: real-time NBBO quote polling
    Realtime,
    /// Free tier: EOD bar replay
    EodReplay,
    /// ThetaData not available at all
    Disabled,
}

// ─────────────────────────────────────────────────────────────────────────────
// Tick Ingestion Engine
// ─────────────────────────────────────────────────────────────────────────────

pub struct TickIngestor {
    config: IngestionConfig,
    client: Client,
    /// Current ingestion mode
    mode: IngestionMode,
    /// Ticks ingested count
    ticks_ingested: u64,
    /// EOD replay buffer — synthetic ticks generated from daily bars
    replay_buffer: Vec<RawTick>,
    /// Whether initial EOD load has been done
    eod_loaded: bool,
    /// Index into replay buffer for drip-feeding ticks
    replay_index: usize,
    /// Last known quote (for detecting changes in real-time mode)
    last_quote: Option<LastQuoteState>,
    /// Consecutive quote poll failures (for fallback logic)
    quote_failures: u32,
}

impl TickIngestor {
    pub fn new(config: IngestionConfig) -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(5))
            .build()
            .expect("Failed to build HTTP client");

        Self {
            config,
            client,
            mode: IngestionMode::Disabled,
            ticks_ingested: 0,
            replay_buffer: Vec::new(),
            eod_loaded: false,
            replay_index: 0,
            last_quote: None,
            quote_failures: 0,
        }
    }

    pub fn mode(&self) -> IngestionMode {
        self.mode
    }

    /// Check if ThetaData Terminal is running and detect subscription tier.
    /// Returns the detected ingestion mode.
    pub async fn detect_mode(&mut self) -> IngestionMode {
        if !self.config.theta_enabled {
            self.mode = IngestionMode::Disabled;
            return self.mode;
        }

        // 1. Basic health check (free endpoint)
        let health_url = format!(
            "{}/v3/stock/list/symbols?format=json",
            self.config.theta_base_url
        );

        match self.client.get(&health_url).send().await {
            Ok(resp) if resp.status().is_success() => {
                info!(
                    "ThetaData Terminal v3 is healthy (port {})",
                    self.config.theta_base_url.split(':').last().unwrap_or("?")
                );
            }
            Ok(resp) => {
                let status = resp.status();
                warn!("ThetaData Terminal returned status {}", status);
                self.mode = IngestionMode::Disabled;
                return self.mode;
            }
            Err(e) => {
                error!(
                    "Cannot reach ThetaData Terminal at {}: {}",
                    self.config.theta_base_url, e
                );
                self.mode = IngestionMode::Disabled;
                return self.mode;
            }
        }

        // 2. Try the Standard-tier quote snapshot to detect subscription level
        let quote_url = format!(
            "{}/v3/stock/snapshot/quote?symbol={}&format=json",
            self.config.theta_base_url, self.config.symbol
        );

        match self.client.get(&quote_url).send().await {
            Ok(resp) if resp.status().is_success() => {
                match resp.json::<ThetaV3QuoteResponse>().await {
                    Ok(data) if !data.response.is_empty() => {
                        let q = &data.response[0];
                        info!(
                            "ThetaData Standard tier detected — real-time NBBO available (bid={:.2}, ask={:.2})",
                            q.bid, q.ask
                        );
                        self.mode = IngestionMode::Realtime;
                    }
                    _ => {
                        info!("ThetaData quote snapshot returned empty — using EOD replay");
                        self.mode = IngestionMode::EodReplay;
                    }
                }
            }
            Ok(resp) => {
                let status = resp.status();
                info!(
                    "ThetaData quote snapshot returned {} — likely Free tier, using EOD replay",
                    status
                );
                self.mode = IngestionMode::EodReplay;
            }
            Err(e) => {
                warn!("ThetaData quote snapshot failed: {} — using EOD replay", e);
                self.mode = IngestionMode::EodReplay;
            }
        }

        self.mode
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Real-time mode: poll NBBO quote snapshot, generate ticks from changes
    // ─────────────────────────────────────────────────────────────────────────

    /// Poll ThetaData quote snapshot and generate ticks from NBBO changes.
    /// Each time the bid/ask moves, we create a RawTick that flows through
    /// the pipeline (footprint, CVD, detectors).
    pub async fn poll_realtime(&mut self) -> (Vec<RawTick>, Option<NbboQuote>) {
        let url = format!(
            "{}/v3/stock/snapshot/quote?symbol={}&format=json",
            self.config.theta_base_url, self.config.symbol
        );

        match self.client.get(&url).send().await {
            Ok(resp) if resp.status().is_success() => {
                self.quote_failures = 0;

                match resp.json::<ThetaV3QuoteResponse>().await {
                    Ok(data) => {
                        if let Some(q) = data.response.first() {
                            let bid = q.bid;
                            let ask = q.ask;
                            let bid_size = q.bid_size.unwrap_or(100);
                            let ask_size = q.ask_size.unwrap_or(100);
                            let mid = (bid + ask) / 2.0;

                            let nbbo = NbboQuote {
                                bid,
                                ask,
                                bid_size,
                                ask_size,
                                timestamp: Utc::now(),
                            };

                            let mut ticks = Vec::new();

                            if let Some(last) = &self.last_quote {
                                // Generate tick if mid price changed
                                let mid_changed = (mid - last.mid).abs() > 0.001;
                                // Also generate tick if significant size change at same price
                                // (indicates a trade filled at the level)
                                let bid_size_drop = bid_size < last.bid_size.saturating_sub(50);
                                let ask_size_drop = ask_size < last.ask_size.saturating_sub(50);

                                if mid_changed || bid_size_drop || ask_size_drop {
                                    // Determine trade direction from quote movement
                                    let (price, size) = if mid > last.mid {
                                        // Price went up → buyer lifted the ask
                                        (ask, ask_size.max(1))
                                    } else if mid < last.mid {
                                        // Price went down → seller hit the bid
                                        (bid, bid_size.max(1))
                                    } else if ask_size_drop {
                                        // Ask size decreased → buyer took liquidity at ask
                                        let consumed = last.ask_size.saturating_sub(ask_size);
                                        (ask, consumed.max(1))
                                    } else {
                                        // Bid size decreased → seller took liquidity at bid
                                        let consumed = last.bid_size.saturating_sub(bid_size);
                                        (bid, consumed.max(1))
                                    };

                                    ticks.push(RawTick {
                                        price,
                                        size,
                                        timestamp: Utc::now(),
                                        conditions: vec!["nbbo_live".to_string()],
                                        source: TickSource::ThetaData,
                                    });
                                    self.ticks_ingested += 1;
                                }
                            } else {
                                // First quote — generate an initial tick at mid
                                ticks.push(RawTick {
                                    price: mid,
                                    size: 100,
                                    timestamp: Utc::now(),
                                    conditions: vec!["nbbo_init".to_string()],
                                    source: TickSource::ThetaData,
                                });
                                self.ticks_ingested += 1;
                            }

                            self.last_quote = Some(LastQuoteState {
                                bid,
                                ask,
                                bid_size,
                                ask_size,
                                mid,
                            });

                            return (ticks, Some(nbbo));
                        }
                    }
                    Err(e) => {
                        debug!("Failed to parse ThetaData quote: {}", e);
                    }
                }
            }
            Ok(resp) => {
                self.quote_failures += 1;
                if self.quote_failures <= 3 {
                    warn!("ThetaData quote returned {}", resp.status());
                }
            }
            Err(e) => {
                self.quote_failures += 1;
                if self.quote_failures <= 3 {
                    warn!("ThetaData quote poll failed: {}", e);
                }
            }
        }

        (Vec::new(), None)
    }

    // ─────────────────────────────────────────────────────────────────────────
    // EOD replay mode (free tier fallback)
    // ─────────────────────────────────────────────────────────────────────────

    /// Load EOD bars and convert to synthetic ticks for pipeline testing.
    pub async fn load_eod_replay(&mut self, days: u32) -> usize {
        if !self.config.theta_enabled {
            return 0;
        }

        let today = Utc::now().format("%Y%m%d").to_string();
        let start = (Utc::now() - chrono::Duration::days(days as i64))
            .format("%Y%m%d")
            .to_string();

        let url = format!(
            "{}/v3/stock/history/eod?symbol={}&start_date={}&end_date={}&format=json",
            self.config.theta_base_url, self.config.symbol, start, today
        );

        info!("Loading EOD data from ThetaData: {} to {}", start, today);

        match self.client.get(&url).send().await {
            Ok(resp) => {
                if !resp.status().is_success() {
                    let body = resp.text().await.unwrap_or_default();
                    warn!(
                        "ThetaData EOD request failed: {}",
                        &body[..body.len().min(300)]
                    );
                    return 0;
                }

                match resp.json::<ThetaV3EodResponse>().await {
                    Ok(data) => {
                        let bar_count = data.response.len();
                        self.replay_buffer = self.eod_to_synthetic_ticks(&data.response);
                        self.replay_index = 0;
                        self.eod_loaded = true;

                        info!(
                            "Loaded {} EOD bars → {} synthetic ticks for replay",
                            bar_count,
                            self.replay_buffer.len()
                        );

                        self.replay_buffer.len()
                    }
                    Err(e) => {
                        warn!("Failed to parse ThetaData EOD response: {}", e);
                        0
                    }
                }
            }
            Err(e) => {
                error!("ThetaData EOD request failed: {}", e);
                0
            }
        }
    }

    /// Convert EOD bars into synthetic ticks.
    fn eod_to_synthetic_ticks(&self, bars: &[ThetaV3EodBar]) -> Vec<RawTick> {
        let mut ticks = Vec::new();

        for (i, bar) in bars.iter().enumerate() {
            let vol_per_tick = bar.volume / 4;
            let base_ts = Utc::now() - chrono::Duration::days((bars.len() - i) as i64);

            for (j, price) in [bar.open, bar.high, bar.low, bar.close].iter().enumerate() {
                let size = if j == 3 {
                    bar.volume - (vol_per_tick * 3)
                } else {
                    vol_per_tick
                };
                ticks.push(RawTick {
                    price: *price,
                    size,
                    timestamp: base_ts + chrono::Duration::seconds(j as i64),
                    conditions: vec!["eod_replay".to_string()],
                    source: TickSource::ThetaData,
                });
            }
        }

        ticks
    }

    /// Poll for replay ticks (free tier / offline mode).
    pub async fn poll_replay(&mut self) -> Vec<RawTick> {
        if !self.config.theta_enabled {
            return Vec::new();
        }

        // First call: load EOD data if not done yet
        if !self.eod_loaded {
            self.load_eod_replay(30).await;
        }

        // Drip-feed 4 ticks per poll (one bar's worth)
        if !self.replay_buffer.is_empty() && self.replay_index < self.replay_buffer.len() {
            let end = (self.replay_index + 4).min(self.replay_buffer.len());
            let batch: Vec<RawTick> = self.replay_buffer[self.replay_index..end].to_vec();
            self.replay_index = end;
            self.ticks_ingested += batch.len() as u64;

            if self.replay_index >= self.replay_buffer.len() {
                info!(
                    "EOD replay complete — {} total ticks processed",
                    self.ticks_ingested
                );
            }

            return batch;
        }

        Vec::new()
    }

    /// Fetch latest NBBO quote (used in EOD mode — gets EOD bid/ask).
    pub async fn poll_eod_quote(&self) -> Option<NbboQuote> {
        if !self.config.theta_enabled {
            return None;
        }

        let today = Utc::now().format("%Y%m%d").to_string();
        let url = format!(
            "{}/v3/stock/history/eod?symbol={}&start_date={}&end_date={}&format=json",
            self.config.theta_base_url, self.config.symbol, today, today
        );

        match self.client.get(&url).send().await {
            Ok(resp) => {
                if !resp.status().is_success() {
                    return None;
                }
                match resp.json::<ThetaV3EodResponse>().await {
                    Ok(data) => {
                        let bar = data.response.last()?;
                        let bid = bar.bid.unwrap_or(bar.close - 0.01);
                        let ask = bar.ask.unwrap_or(bar.close + 0.01);

                        Some(NbboQuote {
                            bid,
                            ask,
                            bid_size: bar.bid_size.unwrap_or(100),
                            ask_size: bar.ask_size.unwrap_or(100),
                            timestamp: Utc::now(),
                        })
                    }
                    Err(e) => {
                        debug!("Failed to parse EOD quote: {}", e);
                        None
                    }
                }
            }
            Err(e) => {
                debug!("ThetaData quote poll failed: {}", e);
                None
            }
        }
    }

    pub fn ticks_ingested(&self) -> u64 {
        self.ticks_ingested
    }

    pub fn replay_progress(&self) -> (usize, usize) {
        (self.replay_index, self.replay_buffer.len())
    }
}
