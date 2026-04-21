//! Flow Engine — High-speed order flow analysis server.
//!
//! Ingests real-time tick data from Alpaca SIP (primary) with
//! ThetaData as fallback, computes order flow signals (footprint,
//! CVD, imbalances, sweeps, absorption, delta flips), and publishes
//! structured events to the dashboard via WebSocket.
//!
//! Architecture (Alpaca Algo Trader Plus):
//!   Alpaca SIP WebSocket (trades + quotes) → TradeClassifier → Engine Pipeline
//!     → FootprintBuilder + CvdCalculator + Detectors
//!       → FlowEvents published via WebSocket to dashboard
//!   Fallback: ThetaData REST → same pipeline

mod alpaca_ws;
mod classifier;
mod cvd;
mod detectors;
mod events;
mod footprint;
mod ingestion;
mod proto;
mod options_enrichment;
mod theta_dx;
mod webtransport;

use alpaca_ws::AlpacaWsConfig;
use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    http::StatusCode,
    response::{Html, IntoResponse},
    routing::{get, post},
    Json, Router,
};
use classifier::TradeClassifier;
use cvd::{CvdCalculator, CvdConfig};
use detectors::{AbsorptionDetector, ImbalanceDetector, SweepDetector};
use events::FlowEvent;
use footprint::{FootprintBuilder, FootprintConfig};
use futures::{SinkExt, StreamExt};
use ingestion::{IngestionConfig, IngestionMode, TickIngestor};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use thetadatadx::fpss::protocol::Contract;
use thetadatadx::fpss::FpssClient;
use std::collections::VecDeque;
use tokio::sync::{broadcast, Mutex, RwLock};
use tower_http::cors::{Any, CorsLayer};
use tracing::{info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Application state shared across handlers
// ─────────────────────────────────────────────────────────────────────────────

const MAX_RECENT_THETA_TRADES: usize = 2000;

struct AppState {
    /// Broadcast channel for flow events → WebSocket clients
    event_tx: broadcast::Sender<FlowEvent>,
    /// Broadcast channel for external JSON events (from Python) → WebSocket clients
    external_tx: broadcast::Sender<String>,
    /// Engine stats
    stats: RwLock<EngineStats>,
    /// Live flow state snapshot for Python signal bridge
    flow_state: RwLock<FlowStateSnapshot>,
    /// Optional direct ThetaDataDx client for dynamic option subscriptions.
    theta_dx_client: RwLock<Option<Arc<FpssClient>>>,
    /// Current UI-managed ThetaDataDx option scope (serialized updates).
    theta_dx_option_scope: Mutex<ThetaDxOptionScope>,
    /// Ring buffer of recent theta_trade JSON strings for frontend hydration on refresh.
    recent_theta_trades: RwLock<VecDeque<String>>,
    /// Live open interest by strike key (e.g. "710.0C" -> OI value)
    open_interest: RwLock<std::collections::HashMap<String, i32>>,
    /// 1-minute OHLC candle buffer (390 = full trading day)
    candles: RwLock<CandleBuffer>,
    /// Running VWAP from tick data
    vwap: RwLock<VwapCalculator>,
    /// RSI calculator (fed from 1-min candle closes)
    rsi: RwLock<RsiCalculator>,
    /// Volume profile for VPOC
    volume_profile: RwLock<VolumeProfile>,
}

#[derive(Debug, Default)]
struct EngineStats {
    ticks_processed: u64,
    events_published: u64,
    ws_clients_connected: u32,
    engine_running: bool,
    data_source: String,
    last_price: f64,
    webtransport_enabled: bool,
    webtransport_port: u16,
    theta_dx_status: String,
    theta_dx_reason: Option<String>,
    theta_dx_credential_source: Option<String>,
}

#[derive(Debug, Default, Clone, Serialize)]
struct FlowStateSnapshot {
    last_price: f64,
    cvd: i64,
    delta_1m: i64,
    delta_5m: i64,
    total_buy_vol: u64,
    total_sell_vol: u64,
    ticks_processed: u64,
    recent_sweeps: Vec<serde_json::Value>,
    recent_absorptions: Vec<serde_json::Value>,
    recent_imbalances: Vec<serde_json::Value>,
    data_source: String,
    session_high: f64,
    session_low: f64,
    // Indicators
    vwap: f64,
    rsi: f64,
    vpoc: f64,
    regime: String,
}

// ─────────────────────────────────────────────────────────────────────────────
// Indicators: VWAP, RSI, VPOC, Regime
// ─────────────────────────────────────────────────────────────────────────────

/// Running VWAP from tick data (most accurate — not candle approximation)
struct VwapCalculator {
    cum_price_vol: f64,
    cum_vol: f64,
    /// For VWAP bands: sum of (price - vwap)^2 * volume
    cum_var_vol: f64,
}

impl VwapCalculator {
    fn new() -> Self {
        Self { cum_price_vol: 0.0, cum_vol: 0.0, cum_var_vol: 0.0 }
    }

    fn update(&mut self, price: f64, volume: u64) {
        let vol = volume as f64;
        self.cum_price_vol += price * vol;
        self.cum_vol += vol;
        let vwap = self.vwap();
        self.cum_var_vol += (price - vwap).powi(2) * vol;
    }

    fn vwap(&self) -> f64 {
        if self.cum_vol > 0.0 { self.cum_price_vol / self.cum_vol } else { 0.0 }
    }

    fn std_dev(&self) -> f64 {
        if self.cum_vol > 0.0 {
            (self.cum_var_vol / self.cum_vol).sqrt()
        } else {
            0.0
        }
    }
}

/// RSI from 1-min candle closes using Wilder's smoothed moving average
struct RsiCalculator {
    period: usize,
    closes: VecDeque<f64>,
    avg_gain: f64,
    avg_loss: f64,
    initialized: bool,
}

impl RsiCalculator {
    fn new(period: usize) -> Self {
        Self {
            period,
            closes: VecDeque::with_capacity(period + 1),
            avg_gain: 0.0,
            avg_loss: 0.0,
            initialized: false,
        }
    }

    fn push_close(&mut self, close: f64) {
        self.closes.push_back(close);

        if self.closes.len() < 2 {
            return;
        }

        let len = self.closes.len();
        let change = self.closes[len - 1] - self.closes[len - 2];
        let gain = if change > 0.0 { change } else { 0.0 };
        let loss = if change < 0.0 { -change } else { 0.0 };

        if !self.initialized && self.closes.len() > self.period {
            // First calculation: simple average
            let mut total_gain = 0.0;
            let mut total_loss = 0.0;
            let start = self.closes.len() - self.period - 1;
            for i in (start + 1)..self.closes.len() {
                let c = self.closes[i] - self.closes[i - 1];
                if c > 0.0 { total_gain += c; } else { total_loss += -c; }
            }
            self.avg_gain = total_gain / self.period as f64;
            self.avg_loss = total_loss / self.period as f64;
            self.initialized = true;
        } else if self.initialized {
            // Wilder's smoothing
            let p = self.period as f64;
            self.avg_gain = (self.avg_gain * (p - 1.0) + gain) / p;
            self.avg_loss = (self.avg_loss * (p - 1.0) + loss) / p;
        }

        // Keep buffer bounded
        if self.closes.len() > self.period * 3 {
            self.closes.pop_front();
        }
    }

    fn rsi(&self) -> f64 {
        if !self.initialized { return 50.0; }
        if self.avg_loss == 0.0 { return 100.0; }
        let rs = self.avg_gain / self.avg_loss;
        100.0 - (100.0 / (1.0 + rs))
    }
}

/// Volume profile — tracks volume at each $0.10 price bucket, reports VPOC
struct VolumeProfile {
    buckets: std::collections::HashMap<i64, u64>,
}

impl VolumeProfile {
    fn new() -> Self {
        Self { buckets: std::collections::HashMap::new() }
    }

    fn update(&mut self, price: f64, volume: u64) {
        let bucket = (price * 10.0).round() as i64; // $0.10 buckets
        *self.buckets.entry(bucket).or_insert(0) += volume;
    }

    /// Volume Point of Control — price with highest volume
    fn vpoc(&self) -> f64 {
        self.buckets
            .iter()
            .max_by_key(|(_, v)| *v)
            .map(|(k, _)| *k as f64 / 10.0)
            .unwrap_or(0.0)
    }
}

/// Regime classification
fn classify_regime(
    cvd: i64,
    spot: f64,
    vwap: f64,
    session_high: f64,
    session_low: f64,
) -> String {
    let range = session_high - session_low;
    if range < 2.0 && cvd.unsigned_abs() > 100_000 {
        "RANGE".to_string()
    } else if cvd > 100_000 && spot > vwap {
        "TREND_UP".to_string()
    } else if cvd < -100_000 && spot < vwap {
        "TREND_DOWN".to_string()
    } else {
        "MIXED".to_string()
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// 1-minute OHLC candle buffer for intraday price history
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize)]
struct Candle {
    /// Minute timestamp (epoch seconds, floored to minute)
    ts: i64,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: u64,
    buy_volume: u64,
    sell_volume: u64,
    /// CVD at candle close
    cvd: i64,
}

struct CandleBuffer {
    candles: VecDeque<Candle>,
    current: Option<Candle>,
    max_candles: usize,
}

impl CandleBuffer {
    fn new(max_candles: usize) -> Self {
        Self {
            candles: VecDeque::with_capacity(max_candles),
            current: None,
            max_candles,
        }
    }

    fn update(&mut self, price: f64, volume: u64, is_buy: bool, cvd: i64) {
        let now = chrono::Utc::now().timestamp();
        let minute_ts = now - (now % 60);

        match &mut self.current {
            Some(c) if c.ts == minute_ts => {
                if price > c.high { c.high = price; }
                if price < c.low { c.low = price; }
                c.close = price;
                c.volume += volume;
                if is_buy { c.buy_volume += volume; } else { c.sell_volume += volume; }
                c.cvd = cvd;
            }
            Some(_) => {
                // New minute — close current candle and start fresh
                let finished = self.current.take().unwrap();
                if self.candles.len() >= self.max_candles {
                    self.candles.pop_front();
                }
                self.candles.push_back(finished);
                self.current = Some(Candle {
                    ts: minute_ts,
                    open: price,
                    high: price,
                    low: price,
                    close: price,
                    volume,
                    buy_volume: if is_buy { volume } else { 0 },
                    sell_volume: if is_buy { 0 } else { volume },
                    cvd,
                });
            }
            None => {
                self.current = Some(Candle {
                    ts: minute_ts,
                    open: price,
                    high: price,
                    low: price,
                    close: price,
                    volume,
                    buy_volume: if is_buy { volume } else { 0 },
                    sell_volume: if is_buy { 0 } else { volume },
                    cvd,
                });
            }
        }
    }

    fn all_candles(&self) -> Vec<Candle> {
        let mut result: Vec<Candle> = self.candles.iter().cloned().collect();
        if let Some(c) = &self.current {
            result.push(c.clone());
        }
        result
    }
}

#[derive(Debug, Default)]
struct ThetaDxOptionScope {
    symbol: Option<String>,
    expiration: Option<i32>,
    contracts: Vec<Contract>,
}

#[derive(Debug, Deserialize)]
struct ThetaDxSubscribeRequest {
    symbol: String,
    expiration: Option<i32>,
    spot_price: Option<f64>,
    strike_range: Option<i32>,
}

fn strike_spacing(symbol: &str, spot_price: f64) -> f64 {
    match symbol {
        "SPY" | "QQQ" | "IWM" => 1.0,
        _ if spot_price > 200.0 => 2.5,
        _ => 1.0,
    }
}

fn round_to_spacing(value: f64, spacing: f64) -> f64 {
    (value / spacing).round() * spacing
}

fn build_option_scope_contracts(
    symbol: &str,
    expiration: i32,
    spot_price: f64,
    strike_range: i32,
) -> Vec<Contract> {
    let spacing = strike_spacing(symbol, spot_price);
    let atm = round_to_spacing(spot_price, spacing);
    let mut contracts = Vec::new();

    for offset in -strike_range..=strike_range {
        let strike = (atm + spacing * offset as f64).max(spacing);
        let strike_raw = (strike * 1000.0).round() as i32;
        contracts.push(Contract::option_raw(
            symbol.to_string(),
            expiration,
            true,
            strike_raw,
        ));
        contracts.push(Contract::option_raw(
            symbol.to_string(),
            expiration,
            false,
            strike_raw,
        ));
    }

    contracts
}

// ─────────────────────────────────────────────────────────────────────────────
// Main entry point
// ─────────────────────────────────────────────────────────────────────────────

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "flow_engine=info,tower_http=info".into()),
        )
        .json()
        .init();

    // Install the rustls crypto provider before any TLS connections.
    // Required because both tokio-tungstenite (Alpaca WS) and wtransport (QUIC)
    // depend on rustls but neither auto-installs a provider.
    rustls::crypto::ring::default_provider()
        .install_default()
        .expect("Failed to install rustls crypto provider");

    info!("Starting Flow Engine v0.2.0");

    dotenvy::dotenv().ok();

    let (event_tx, _) = broadcast::channel::<FlowEvent>(1000);
    let (external_tx, _) = broadcast::channel::<String>(2000);

    let state = Arc::new(AppState {
        event_tx: event_tx.clone(),
        external_tx: external_tx.clone(),
        stats: RwLock::new(EngineStats::default()),
        flow_state: RwLock::new(FlowStateSnapshot::default()),
        theta_dx_client: RwLock::new(None),
        theta_dx_option_scope: Mutex::new(ThetaDxOptionScope::default()),
        recent_theta_trades: RwLock::new(VecDeque::with_capacity(MAX_RECENT_THETA_TRADES)),
        open_interest: RwLock::new(std::collections::HashMap::new()),
        candles: RwLock::new(CandleBuffer::new(390)),
        vwap: RwLock::new(VwapCalculator::new()),
        rsi: RwLock::new(RsiCalculator::new(14)),
        volume_profile: RwLock::new(VolumeProfile::new()),
    });

    // Build ingestion config from environment
    let ing_config = IngestionConfig {
        theta_enabled: std::env::var("THETA_ENABLED")
            .map(|v| v == "true" || v == "1")
            .unwrap_or(false),
        theta_base_url: std::env::var("THETA_BASE_URL")
            .unwrap_or_else(|_| "http://localhost:25503".to_string()),
        symbol: std::env::var("TRADING_SYMBOL").unwrap_or_else(|_| "SPY".to_string()),
        poll_interval_ms: std::env::var("THETA_POLL_MS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(200),
    };

    // Prepare Alpaca config (used as fallback if ThetaData isn't available)
    let alpaca_config = AlpacaWsConfig::from_env();

    // Spawn the engine pipeline
    let engine_state = state.clone();
    tokio::spawn(async move {
        run_engine(ing_config, engine_state, alpaca_config).await;
    });

    // Spawn heartbeat task
    let hb_tx = event_tx.clone();
    let hb_state = state.clone();
    tokio::spawn(async move {
        heartbeat_loop(hb_tx, hb_state).await;
    });

    // Spawn WebTransport (QUIC) server on port 4433
    let wt_port: u16 = std::env::var("WEBTRANSPORT_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(4433);
    {
        let mut stats = state.stats.write().await;
        stats.webtransport_enabled = true;
        stats.webtransport_port = wt_port;
        stats.theta_dx_status = "starting".to_string();
    }
    let wt_flow_tx = event_tx.clone();
    let wt_ext_tx = external_tx.clone();
    tokio::spawn(async move {
        webtransport::serve(wt_flow_tx, wt_ext_tx, wt_port).await;
    });

    // Spawn ThetaDataDx direct ingestion (if credentials available)
    // ThetaDx is the EXCLUSIVE source for options data.
    // Alpaca is the EXCLUSIVE source for equity/stock data.
    let tdx_ext_tx = external_tx.clone();
    let tdx_state = state.clone();
    tokio::spawn(async move {
        let config = theta_dx::ThetaDxConfig {
            option_contracts: vec![], // Options subscribed dynamically via API
        };

        match theta_dx::start_theta_dx(&config, 262_144) {
            theta_dx::ThetaDxStartOutcome::Connected {
                mut rx,
                client,
                credential_source,
            } => {
                let client = Arc::new(client);
                {
                    let mut holder = tdx_state.theta_dx_client.write().await;
                    *holder = Some(client.clone());
                }
                {
                    let mut stats = tdx_state.stats.write().await;
                    stats.theta_dx_status = "active".to_string();
                    stats.theta_dx_reason = None;
                    stats.theta_dx_credential_source = Some(credential_source.to_string());
                }
                info!("ThetaDataDx active — streaming directly from FPSS");

                // Options enrichment pipeline: IV, Greeks, VPIN, SMS
                let mut enricher = options_enrichment::OptionsEnricher::new();

                while let Some(event) = rx.recv().await {
                    // Update enricher with latest underlying price from equity pipeline
                    {
                        let fs = tdx_state.flow_state.read().await;
                        enricher.set_underlying_price(fs.last_price);
                    }

                    let json = match &event {
                        theta_dx::ThetaDxEvent::OptionQuote {
                            root,
                            expiration,
                            strike,
                            right,
                            contract_id,
                            bid,
                            ask,
                            bid_size,
                            ask_size,
                            ms_of_day,
                            date,
                        } => {
                            // Feed quote to enricher for Greeks computation on trades
                            enricher.on_quote(*contract_id, *bid, *ask);

                            serde_json::json!({
                                "type": "theta_quote",
                                "root": root.as_ref(),
                                "expiration": expiration,
                                "strike": strike,
                                "right": right.as_ref(),
                                "bid": bid, "ask": ask,
                                "bid_size": bid_size, "ask_size": ask_size,
                                "ms_of_day": ms_of_day,
                                "date": date,
                            })
                            .to_string()
                        }
                        theta_dx::ThetaDxEvent::OptionTrade {
                            root,
                            expiration,
                            strike,
                            right,
                            contract_id,
                            price,
                            size,
                            premium,
                            side,
                            condition,
                            exchange,
                            ms_of_day,
                            date,
                        } => {
                            let is_call = right.as_ref() == "C";
                            let enriched = enricher.enrich_trade(
                                *contract_id,
                                *strike,
                                is_call,
                                *price,
                                *size,
                                side,
                                *expiration,
                                *date,
                                *ms_of_day,
                            );

                            serde_json::json!({
                                "type": "theta_trade",
                                "root": root.as_ref(),
                                "expiration": expiration,
                                "strike": strike,
                                "right": right.as_ref(),
                                "price": price, "size": size,
                                "premium": premium,
                                "side": side,
                                "condition": condition, "exchange": exchange,
                                "ms_of_day": ms_of_day,
                                "date": date,
                                "timestamp": enriched.timestamp_ms as f64 / 1000.0,
                                "iv": enriched.iv,
                                "delta": enriched.delta,
                                "gamma": enriched.gamma,
                                "vpin": enriched.vpin,
                                "sms": enriched.sms,
                            })
                            .to_string()
                        }
                        theta_dx::ThetaDxEvent::OptionOpenInterest {
                            root,
                            expiration,
                            strike,
                            right,
                            open_interest,
                            ms_of_day,
                            date,
                            ..
                        } => {
                            // Update OI map
                            let key = format!("{}{}", strike, right.as_ref());
                            tdx_state.open_interest.write().await.insert(key, *open_interest);
                            serde_json::json!({
                                "type": "theta_oi",
                                "root": root.as_ref(),
                                "expiration": expiration,
                                "strike": strike,
                                "right": right.as_ref(),
                                "open_interest": open_interest,
                                "ms_of_day": ms_of_day,
                                "date": date,
                            })
                            .to_string()
                        }
                    };
                    // Buffer theta_trade events for frontend hydration on refresh
                    if matches!(&event, theta_dx::ThetaDxEvent::OptionTrade { .. }) {
                        let mut buf = tdx_state.recent_theta_trades.write().await;
                        if buf.len() >= MAX_RECENT_THETA_TRADES {
                            buf.pop_front();
                        }
                        buf.push_back(json.clone());
                    }
                    let _ = tdx_ext_tx.send(json);
                }
                warn!("ThetaDataDx stream ended");
                {
                    let mut holder = tdx_state.theta_dx_client.write().await;
                    *holder = None;
                }
                let mut stats = tdx_state.stats.write().await;
                stats.theta_dx_status = "disconnected".to_string();
                stats.theta_dx_reason = Some("stream_ended".to_string());
            }
            theta_dx::ThetaDxStartOutcome::Unavailable {
                reason,
                credential_source,
            } => {
                {
                    let mut stats = tdx_state.stats.write().await;
                    stats.theta_dx_status = "unavailable".to_string();
                    stats.theta_dx_reason = Some(reason.clone());
                    stats.theta_dx_credential_source =
                        credential_source.map(std::string::ToString::to_string);
                }
                info!("ThetaDataDx not available — using Python path for options data");
            }
        }
    });

    // Build HTTP/WebSocket server
    let app = Router::new()
        .route("/", get(index_handler))
        .route("/ws", get(ws_handler))
        .route("/health", get(health_handler))
        .route("/stats", get(stats_handler))
        .route("/ingest", post(ingest_handler))
        .route("/theta/options/subscribe", post(theta_dx_subscribe_handler))
        .route("/flow-state", get(flow_state_handler))
        .route("/theta/trades/recent", get(recent_theta_trades_handler))
        .route("/theta/open-interest", get(open_interest_handler))
        .route("/candles", get(candles_handler))
        .route("/cert-hash", get(cert_hash_handler))
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        .with_state(state);

    let port: u16 = std::env::var("FLOW_ENGINE_PORT")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(8081);

    let addr = format!("0.0.0.0:{}", port);
    info!("Flow Engine listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .expect("Failed to bind");

    axum::serve(listener, app).await.expect("Server error");
}

// ─────────────────────────────────────────────────────────────────────────────
// Engine pipeline: ingest → classify → compute → publish
//
// Priority: Alpaca SIP (trades+quotes) → ThetaData Realtime → ThetaData EOD
// ─────────────────────────────────────────────────────────────────────────────

async fn run_engine(
    config: IngestionConfig,
    state: Arc<AppState>,
    alpaca_config: Option<AlpacaWsConfig>,
) {
    info!(
        "Engine pipeline starting — symbol: {}, theta_enabled: {}",
        config.symbol, config.theta_enabled,
    );

    let mut ingestor = TickIngestor::new(config.clone());
    let classifier = TradeClassifier::new();
    let mut footprint = FootprintBuilder::new(FootprintConfig::default());
    let mut cvd_calc = CvdCalculator::new(CvdConfig::default());
    let imbalance_detector = ImbalanceDetector::default();
    let mut sweep_detector = SweepDetector::default();
    let mut absorption_detector = AbsorptionDetector::default();

    // Mark engine as running
    {
        let mut stats = state.stats.write().await;
        stats.engine_running = true;
    }

    // ── Data source routing ──
    // STOCKS: Alpaca WebSocket SIP (exclusive) → REST polling fallback
    // OPTIONS: ThetaData via ThetaDx FPSS (exclusive)

    let alpaca_available = alpaca_config
        .as_ref()
        .map(|c| c.is_configured())
        .unwrap_or(false);

    if alpaca_available {
        // ── Alpaca WebSocket SIP — real trades + NBBO quotes for stocks ──
        let alpaca_cfg = alpaca_config.unwrap();
        run_alpaca_primary(
            &alpaca_cfg,
            &classifier,
            &mut footprint,
            &mut cvd_calc,
            &imbalance_detector,
            &mut sweep_detector,
            &mut absorption_detector,
            &state,
        )
        .await;
    }

    // Alpaca unavailable or disconnected — fall back to REST polling for stocks
    warn!("Alpaca not available — falling back to REST polling for stock data");
    run_theta_fallback(
        &mut ingestor,
        &config,
        &classifier,
        &mut footprint,
        &mut cvd_calc,
        &imbalance_detector,
        &mut sweep_detector,
        &mut absorption_detector,
        &state,
        true,
    )
    .await;
}

async fn run_alpaca_primary(
    alpaca_cfg: &AlpacaWsConfig,
    classifier: &TradeClassifier,
    footprint: &mut FootprintBuilder,
    cvd_calc: &mut CvdCalculator,
    imbalance_detector: &ImbalanceDetector,
    sweep_detector: &mut SweepDetector,
    absorption_detector: &mut AbsorptionDetector,
    state: &Arc<AppState>,
) {
    info!(
        "Using Alpaca SIP as primary data source (trades + quotes): {}",
        alpaca_cfg.ws_url
    );
    {
        let mut stats = state.stats.write().await;
        stats.data_source = format!(
            "Alpaca SIP ({})",
            alpaca_cfg.ws_url.split('/').last().unwrap_or("ws")
        );
    }

    let mut alpaca_rx = alpaca_ws::spawn_alpaca_feed(alpaca_cfg.clone());

    info!("Waiting for live Alpaca trades + quotes...");

    loop {
        match alpaca_rx.recv().await {
            Some(alpaca_ws::AlpacaFeedMsg::Trade(raw_tick)) => {
                process_tick(
                    &raw_tick,
                    classifier,
                    footprint,
                    cvd_calc,
                    imbalance_detector,
                    sweep_detector,
                    absorption_detector,
                    state,
                )
                .await;
            }
            Some(alpaca_ws::AlpacaFeedMsg::Quote(nbbo)) => {
                classifier.update_quote(nbbo);
            }
            None => {
                warn!("Alpaca feed channel closed");
                return;
            }
        }
    }
}

/// Consume ThetaDataDx equity ticks as an order flow data source.
async fn run_theta_fallback(
    ingestor: &mut TickIngestor,
    config: &IngestionConfig,
    classifier: &TradeClassifier,
    footprint: &mut FootprintBuilder,
    cvd_calc: &mut CvdCalculator,
    imbalance_detector: &ImbalanceDetector,
    sweep_detector: &mut SweepDetector,
    absorption_detector: &mut AbsorptionDetector,
    state: &Arc<AppState>,
    log_no_alpaca: bool,
) {
    let mode = ingestor.detect_mode().await;
    if log_no_alpaca {
        info!("No Alpaca — ThetaData ingestion mode: {:?}", mode);
    } else {
        info!("ThetaData fallback ingestion mode: {:?}", mode);
    }

    match mode {
        IngestionMode::Realtime => {
            info!("Using ThetaData Standard real-time NBBO as data source");
            {
                let mut stats = state.stats.write().await;
                stats.data_source = "ThetaData Realtime".to_string();
            }

            let poll_interval = tokio::time::Duration::from_millis(config.poll_interval_ms);

            loop {
                let (ticks, nbbo) = ingestor.poll_realtime().await;
                if let Some(quote) = nbbo {
                    classifier.update_quote(quote);
                }
                for raw_tick in &ticks {
                    process_tick(
                        raw_tick,
                        classifier,
                        footprint,
                        cvd_calc,
                        imbalance_detector,
                        sweep_detector,
                        absorption_detector,
                        state,
                    )
                    .await;
                }
                tokio::time::sleep(poll_interval).await;
            }
        }
        _ => {
            info!("No real-time source — using ThetaData EOD replay");
            {
                let mut stats = state.stats.write().await;
                stats.data_source = "ThetaData EOD Replay".to_string();
            }

            let poll_interval = tokio::time::Duration::from_millis(config.poll_interval_ms);

            loop {
                let raw_ticks = ingestor.poll_replay().await;
                if let Some(quote) = ingestor.poll_eod_quote().await {
                    classifier.update_quote(quote);
                }
                for raw_tick in &raw_ticks {
                    process_tick(
                        raw_tick,
                        classifier,
                        footprint,
                        cvd_calc,
                        imbalance_detector,
                        sweep_detector,
                        absorption_detector,
                        state,
                    )
                    .await;
                }
                tokio::time::sleep(poll_interval).await;
            }
        }
    }
}

/// Process a single tick through the full pipeline.
async fn process_tick(
    raw_tick: &events::RawTick,
    classifier: &TradeClassifier,
    footprint: &mut FootprintBuilder,
    cvd_calc: &mut CvdCalculator,
    imbalance_detector: &ImbalanceDetector,
    sweep_detector: &mut SweepDetector,
    absorption_detector: &mut AbsorptionDetector,
    state: &Arc<AppState>,
) {
    let classified = classifier.classify(raw_tick);

    // 0. Broadcast tick for dashboard candle building
    publish_event(
        state,
        FlowEvent::Tick {
            price: classified.price,
            size: classified.size,
            side: classified.side,
            timestamp: classified.timestamp,
        },
    )
    .await;

    // 1. Update footprint
    let fp_event = footprint.process_tick(&classified);
    let fp_totals = if let FlowEvent::Footprint {
        total_buy_vol,
        total_sell_vol,
        ..
    } = &fp_event
    {
        Some((*total_buy_vol, *total_sell_vol))
    } else {
        None
    };
    publish_event(state, fp_event).await;

    // 2. Update CVD + detect delta flips / large trades
    let cvd_events = cvd_calc.process_tick(&classified);
    let mut latest_cvd: Option<(i64, i64, i64)> = None;
    for event in &cvd_events {
        if let FlowEvent::Cvd {
            value,
            delta_1m,
            delta_5m,
            ..
        } = event
        {
            latest_cvd = Some((*value, *delta_1m, *delta_5m));
        }
    }
    for event in cvd_events {
        publish_event(state, event).await;
    }

    // 3. Check imbalances
    let levels = footprint.current_levels();
    let imb_events = imbalance_detector.check(&levels, classified.timestamp);
    for event in imb_events {
        publish_event(state, event).await;
    }

    // 4. Check for sweeps
    if let Some(sweep_event) = sweep_detector.process_tick(&classified) {
        publish_event(state, sweep_event).await;
    }

    // 5. Check for absorption
    if let Some(abs_event) = absorption_detector.process_tick(&classified) {
        publish_event(state, abs_event).await;
    }

    // Update stats
    {
        let mut stats = state.stats.write().await;
        stats.ticks_processed += 1;
        stats.last_price = classified.price;
    }

    // Update VWAP + volume profile (tick-level, most accurate)
    {
        let mut vwap = state.vwap.write().await;
        vwap.update(classified.price, classified.size);
    }
    {
        let mut vp = state.volume_profile.write().await;
        vp.update(classified.price, classified.size);
    }

    // Update candle buffer + RSI (on candle close)
    {
        let is_buy = classified.side == events::TradeSide::Buy;
        let cvd_val = latest_cvd.map(|(c, _, _)| c).unwrap_or(0);
        let mut candles = state.candles.write().await;
        let prev_count = candles.candles.len();
        candles.update(classified.price, classified.size, is_buy, cvd_val);
        // Feed RSI when a candle closes (new candle started = previous one closed)
        if candles.candles.len() > prev_count {
            if let Some(closed) = candles.candles.back() {
                let close = closed.close;
                drop(candles);
                let mut rsi = state.rsi.write().await;
                rsi.push_close(close);
            }
        }
    }

    // Update flow state snapshot with all indicators
    {
        let vwap_val = state.vwap.read().await.vwap();
        let rsi_val = state.rsi.read().await.rsi();
        let vpoc_val = state.volume_profile.read().await.vpoc();

        let mut fs = state.flow_state.write().await;
        fs.last_price = classified.price;
        fs.ticks_processed += 1;
        // Track session high/low
        if classified.price > fs.session_high || fs.session_high == 0.0 {
            fs.session_high = classified.price;
        }
        if classified.price < fs.session_low || fs.session_low == 0.0 {
            fs.session_low = classified.price;
        }
        if let Some((cvd, d1m, d5m)) = latest_cvd {
            fs.cvd = cvd;
            fs.delta_1m = d1m;
            fs.delta_5m = d5m;
        }
        if let Some((buy_vol, sell_vol)) = fp_totals {
            fs.total_buy_vol = buy_vol;
            fs.total_sell_vol = sell_vol;
        }
        // Indicators
        fs.vwap = vwap_val;
        fs.rsi = rsi_val;
        fs.vpoc = vpoc_val;
        fs.regime = classify_regime(fs.cvd, fs.last_price, vwap_val, fs.session_high, fs.session_low);
    }
}

async fn publish_event(state: &Arc<AppState>, event: FlowEvent) {
    if state.event_tx.receiver_count() > 0 {
        if let Err(e) = state.event_tx.send(event) {
            warn!("Failed to publish event: {}", e);
        } else {
            let mut stats = state.stats.write().await;
            stats.events_published += 1;
        }
    }
}

async fn heartbeat_loop(tx: broadcast::Sender<FlowEvent>, state: Arc<AppState>) {
    let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(5));
    loop {
        interval.tick().await;
        let (ticks, price, source) = {
            let stats = state.stats.read().await;
            (
                stats.ticks_processed,
                stats.last_price,
                stats.data_source.clone(),
            )
        };
        let _ = tx.send(FlowEvent::Heartbeat {
            timestamp: chrono::Utc::now(),
            ticks_processed: ticks,
            last_price: price,
            data_source: if source.is_empty() {
                None
            } else {
                Some(source)
            },
        });
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// HTTP handlers
// ─────────────────────────────────────────────────────────────────────────────

async fn index_handler() -> Html<&'static str> {
    Html(
        r#"<html><body style="background:#0a0a14;color:#e0e0e0;font-family:monospace;padding:20px">
        <h1 style="color:#4488ff">Flow Engine v0.2.0</h1>
        <p>WebSocket endpoint: <code>ws://localhost:8081/ws</code></p>
        <p>Health: <a href="/health" style="color:#00c850">/health</a></p>
        <p>Stats: <a href="/stats" style="color:#00c850">/stats</a></p>
        </body></html>"#,
    )
}

async fn health_handler(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let stats = state.stats.read().await;
    axum::Json(serde_json::json!({
        "status": "ok",
        "engine_running": stats.engine_running,
        "ticks_processed": stats.ticks_processed,
        "data_source": stats.data_source,
        "webtransport": {
            "enabled": stats.webtransport_enabled,
            "port": stats.webtransport_port,
            "cert_hash_available": webtransport::cert_hash_available(),
            "clients_connected": webtransport::client_count(),
        },
        "theta_dx": {
            "status": stats.theta_dx_status,
            "active": stats.theta_dx_status == "active",
            "reason": stats.theta_dx_reason,
            "credential_source": stats.theta_dx_credential_source,
        },
    }))
}

async fn stats_handler(State(state): State<Arc<AppState>>) -> impl IntoResponse {
    let stats = state.stats.read().await;
    axum::Json(serde_json::json!({
        "ticks_processed": stats.ticks_processed,
        "events_published": stats.events_published,
        "ws_clients": stats.ws_clients_connected,
        "engine_running": stats.engine_running,
        "data_source": stats.data_source,
        "last_price": stats.last_price,
        "webtransport": {
            "enabled": stats.webtransport_enabled,
            "port": stats.webtransport_port,
            "cert_hash_available": webtransport::cert_hash_available(),
            "clients_connected": webtransport::client_count(),
        },
        "theta_dx": {
            "status": stats.theta_dx_status,
            "active": stats.theta_dx_status == "active",
            "reason": stats.theta_dx_reason,
            "credential_source": stats.theta_dx_credential_source,
        },
    }))
}

// ─────────────────────────────────────────────────────────────────────────────
// Ingest handler — accepts external JSON events from Python for unified broadcast
// ─────────────────────────────────────────────────────────────────────────────

async fn ingest_handler(
    State(state): State<Arc<AppState>>,
    Json(event): Json<serde_json::Value>,
) -> StatusCode {
    match serde_json::to_string(&event) {
        Ok(json) => {
            // Buffer theta_trade events from Python path for hydration
            if event.get("type").and_then(|v| v.as_str()) == Some("theta_trade") {
                let mut buf = state.recent_theta_trades.write().await;
                if buf.len() >= MAX_RECENT_THETA_TRADES {
                    buf.pop_front();
                }
                buf.push_back(json.clone());
            }
            let _ = state.external_tx.send(json);
            StatusCode::OK
        }
        Err(_) => StatusCode::BAD_REQUEST,
    }
}

async fn theta_dx_subscribe_handler(
    State(state): State<Arc<AppState>>,
    Json(body): Json<ThetaDxSubscribeRequest>,
) -> impl IntoResponse {
    let symbol = body.symbol.trim().to_uppercase();
    if symbol.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": "symbol_required" })),
        );
    }

    let Some(client) = state.theta_dx_client.read().await.clone() else {
        let stats = state.stats.read().await;
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(serde_json::json!({
                "error": "theta_dx_inactive",
                "theta_dx_status": stats.theta_dx_status,
                "theta_dx_reason": stats.theta_dx_reason,
                "theta_dx_credential_source": stats.theta_dx_credential_source,
            })),
        );
    };

    let spot_price = body.spot_price.unwrap_or(0.0);
    if spot_price <= 0.0 {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({ "error": "spot_price_required" })),
        );
    }

    let expiration = body.expiration.unwrap_or_else(|| {
        chrono::Utc::now()
            .format("%Y%m%d")
            .to_string()
            .parse()
            .unwrap_or_default()
    });
    let strike_range = body.strike_range.unwrap_or(15).clamp(1, 50);
    let new_contracts = build_option_scope_contracts(&symbol, expiration, spot_price, strike_range);

    let old_contracts = {
        let mut scope = state.theta_dx_option_scope.lock().await;
        let old = std::mem::take(&mut scope.contracts);
        scope.symbol = Some(symbol.clone());
        scope.expiration = Some(expiration);
        scope.contracts = new_contracts.clone();
        old
    };

    let mut unsubscribe_errors = Vec::new();
    for contract in &old_contracts {
        if let Err(err) = client.unsubscribe_quotes(contract) {
            unsubscribe_errors.push(format!("quote_unsub:{err}"));
        }
        if let Err(err) = client.unsubscribe_trades(contract) {
            unsubscribe_errors.push(format!("trade_unsub:{err}"));
        }
        if let Err(err) = client.unsubscribe_open_interest(contract) {
            unsubscribe_errors.push(format!("oi_unsub:{err}"));
        }
    }

    let mut subscribe_errors = Vec::new();
    for contract in &new_contracts {
        if let Err(err) = client.subscribe_quotes(contract) {
            subscribe_errors.push(format!("quote_sub:{err}"));
        }
        if let Err(err) = client.subscribe_trades(contract) {
            subscribe_errors.push(format!("trade_sub:{err}"));
        }
        if let Err(err) = client.subscribe_open_interest(contract) {
            subscribe_errors.push(format!("oi_sub:{err}"));
        }
    }

    let status = if subscribe_errors.is_empty() {
        StatusCode::OK
    } else {
        StatusCode::BAD_GATEWAY
    };

    (
        status,
        Json(serde_json::json!({
            "symbol": symbol,
            "expiration": expiration,
            "spot_price": spot_price,
            "strike_range": strike_range,
            "contracts": new_contracts.len(),
            "unsubscribed_contracts": old_contracts.len(),
            "unsubscribe_errors": unsubscribe_errors,
            "subscribe_errors": subscribe_errors,
        })),
    )
}

async fn cert_hash_handler() -> Json<serde_json::Value> {
    match webtransport::CERT_HASH.get() {
        Some(hash) => Json(serde_json::json!({
            "algorithm": "sha-256",
            "value": hash,
        })),
        None => Json(serde_json::json!({ "error": "no cert hash available" })),
    }
}

async fn flow_state_handler(State(state): State<Arc<AppState>>) -> Json<FlowStateSnapshot> {
    let snapshot = state.flow_state.read().await.clone();
    Json(snapshot)
}

#[derive(Debug, Deserialize)]
struct RecentTradesQuery {
    limit: Option<usize>,
}

async fn recent_theta_trades_handler(
    State(state): State<Arc<AppState>>,
    axum::extract::Query(q): axum::extract::Query<RecentTradesQuery>,
) -> impl IntoResponse {
    let limit = q.limit.unwrap_or(500).min(MAX_RECENT_THETA_TRADES);
    let buf = state.recent_theta_trades.read().await;
    // Return newest first (most recent trades at index 0)
    let trades: Vec<&str> = buf.iter().rev().take(limit).map(|s| s.as_str()).collect();
    // Build raw JSON array to avoid double-serialization
    let body = format!("[{}]", trades.join(","));
    (
        StatusCode::OK,
        [("content-type", "application/json")],
        body,
    )
}

async fn open_interest_handler(
    State(state): State<Arc<AppState>>,
) -> impl IntoResponse {
    let oi = state.open_interest.read().await;
    let body = serde_json::to_string(&*oi).unwrap_or_else(|_| "{}".to_string());
    (
        StatusCode::OK,
        [("content-type", "application/json")],
        body,
    )
}

#[derive(Debug, Deserialize)]
struct CandlesQuery {
    last: Option<usize>,
}

async fn candles_handler(
    State(state): State<Arc<AppState>>,
    axum::extract::Query(q): axum::extract::Query<CandlesQuery>,
) -> impl IntoResponse {
    let candles = state.candles.read().await;
    let mut all = candles.all_candles();
    if let Some(last) = q.last {
        let skip = all.len().saturating_sub(last);
        all = all.into_iter().skip(skip).collect();
    }
    let body = serde_json::to_string(&all).unwrap_or_else(|_| "[]".to_string());
    (
        StatusCode::OK,
        [("content-type", "application/json")],
        body,
    )
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket handler — streams FlowEvents to connected agents
// ─────────────────────────────────────────────────────────────────────────────

async fn ws_handler(ws: WebSocketUpgrade, State(state): State<Arc<AppState>>) -> impl IntoResponse {
    ws.on_upgrade(|socket| handle_ws_client(socket, state))
}

async fn handle_ws_client(socket: WebSocket, state: Arc<AppState>) {
    let (mut sender, mut receiver): (
        futures::stream::SplitSink<WebSocket, Message>,
        futures::stream::SplitStream<WebSocket>,
    ) = socket.split();
    let mut flow_rx = state.event_tx.subscribe();
    let mut ext_rx = state.external_tx.subscribe();

    {
        let mut stats = state.stats.write().await;
        stats.ws_clients_connected += 1;
    }
    info!(
        "WebSocket client connected (total: {})",
        state.stats.read().await.ws_clients_connected
    );

    // Listen to both channels: flow events (Rust-computed) + external events (from Python)
    // Encode all messages as protobuf binary for minimal wire size and off-thread decoding
    let send_task = tokio::spawn(async move {
        loop {
            let bytes: Vec<u8> = tokio::select! {
                Ok(event) = flow_rx.recv() => {
                    proto::encode_flow_event(&event)
                }
                Ok(ext_json) = ext_rx.recv() => {
                    proto::encode_external_json(&ext_json)
                }
                else => break,
            };
            if sender.send(Message::Binary(bytes.into())).await.is_err() {
                break;
            }
        }
    });

    let recv_task =
        tokio::spawn(async move { while let Some(Ok(_msg)) = receiver.next().await {} });

    tokio::select! {
        _ = send_task => {},
        _ = recv_task => {},
    }

    {
        let mut stats = state.stats.write().await;
        stats.ws_clients_connected = stats.ws_clients_connected.saturating_sub(1);
    }
    info!("WebSocket client disconnected");
}
