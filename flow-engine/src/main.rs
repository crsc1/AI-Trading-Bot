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
mod theta_dx;
mod webtransport;

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
use alpaca_ws::AlpacaWsConfig;
use classifier::TradeClassifier;
use cvd::{CvdCalculator, CvdConfig};
use detectors::{AbsorptionDetector, ImbalanceDetector, SweepDetector};
use events::FlowEvent;
use serde::Serialize;
use footprint::{FootprintBuilder, FootprintConfig};
use futures::{SinkExt, StreamExt};
use ingestion::{IngestionConfig, IngestionMode, TickIngestor};
use std::sync::Arc;
use tokio::sync::{broadcast, mpsc, RwLock};
use tower_http::cors::{Any, CorsLayer};
use tracing::{error, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Application state shared across handlers
// ─────────────────────────────────────────────────────────────────────────────

struct AppState {
    /// Broadcast channel for flow events → WebSocket clients
    event_tx: broadcast::Sender<FlowEvent>,
    /// Broadcast channel for external JSON events (from Python) → WebSocket clients
    external_tx: broadcast::Sender<String>,
    /// Engine stats
    stats: RwLock<EngineStats>,
    /// Live flow state snapshot for Python signal bridge
    flow_state: RwLock<FlowStateSnapshot>,
}

#[derive(Debug, Default)]
struct EngineStats {
    ticks_processed: u64,
    events_published: u64,
    ws_clients_connected: u32,
    engine_running: bool,
    data_source: String,
    last_price: f64,
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
    let wt_flow_tx = event_tx.clone();
    let wt_ext_tx = external_tx.clone();
    tokio::spawn(async move {
        webtransport::serve(wt_flow_tx, wt_ext_tx, wt_port).await;
    });

    // Spawn ThetaDataDx direct ingestion (if credentials available)
    let tdx_ext_tx = external_tx.clone();
    tokio::spawn(async move {
        let config = theta_dx::ThetaDxConfig {
            equity_symbols: vec!["SPY".to_string()],
            option_contracts: vec![], // Options subscribed dynamically via API
        };

        match theta_dx::start_theta_dx(&config, 8192) {
            Ok(Some((mut rx, _client))) => {
                info!("ThetaDataDx active — streaming directly from FPSS");
                while let Some(event) = rx.recv().await {
                    // Convert ThetaDxEvent to JSON and broadcast via external channel
                    // This keeps the same format the frontend expects
                    let json = match &event {
                        theta_dx::ThetaDxEvent::OptionQuote { symbol, bid, ask, bid_size, ask_size, ms_of_day, .. } => {
                            serde_json::json!({
                                "type": "theta_quote",
                                "root": symbol.as_ref(),
                                "bid": bid, "ask": ask,
                                "bid_size": bid_size, "ask_size": ask_size,
                                "ms_of_day": ms_of_day,
                            }).to_string()
                        }
                        theta_dx::ThetaDxEvent::OptionTrade { symbol, price, size, condition, exchange, ms_of_day, .. } => {
                            serde_json::json!({
                                "type": "theta_trade",
                                "root": symbol.as_ref(),
                                "price": price, "size": size,
                                "condition": condition, "exchange": exchange,
                                "ms_of_day": ms_of_day,
                            }).to_string()
                        }
                        theta_dx::ThetaDxEvent::EquityQuote { symbol, bid, ask, bid_size, ask_size, ms_of_day } => {
                            serde_json::json!({
                                "type": "quote",
                                "symbol": symbol.as_ref(),
                                "bid": bid, "ask": ask,
                                "bid_size": bid_size, "ask_size": ask_size,
                                "timestamp": ms_of_day,
                            }).to_string()
                        }
                        theta_dx::ThetaDxEvent::EquityTrade { symbol, price, size, exchange, ms_of_day } => {
                            serde_json::json!({
                                "type": "trade",
                                "symbol": symbol.as_ref(),
                                "price": price, "size": size,
                                "exchange": exchange,
                                "timestamp": ms_of_day,
                            }).to_string()
                        }
                    };
                    let _ = tdx_ext_tx.send(json);
                }
            }
            Ok(None) => {
                info!("ThetaDataDx not available — using Python path for options data");
            }
            Err(e) => {
                warn!("ThetaDataDx initialization error: {e}");
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
        .route("/flow-state", get(flow_state_handler))
        .route("/cert-hash", get(cert_hash_handler))
        .layer(CorsLayer::new().allow_origin(Any).allow_methods(Any).allow_headers(Any))
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

    axum::serve(listener, app)
        .await
        .expect("Server error");
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

    // ── Data source priority ──
    // 1. Alpaca WebSocket SIP (best for order flow — actual trades, real timestamps)
    // 2. ThetaData Realtime NBBO (synthetic ticks from quote changes)
    // 3. ThetaData EOD replay (offline/testing only)
    //
    // Note: ThetaData is ALWAYS used for options data via the dashboard's
    // api_routes.py. The engine only handles stock ticks for order flow.

    let alpaca_available = alpaca_config
        .as_ref()
        .map(|c| c.is_configured())
        .unwrap_or(false);

    if alpaca_available {
        // ── PRIMARY: Alpaca WebSocket SIP — real trades + NBBO quotes ──
        let alpaca_cfg = alpaca_config.unwrap();
        info!(
            "Using Alpaca SIP as primary data source (trades + quotes): {}",
            alpaca_cfg.ws_url
        );
        {
            let mut stats = state.stats.write().await;
            stats.data_source = format!("Alpaca SIP ({})", alpaca_cfg.ws_url.split('/').last().unwrap_or("ws"));
        }

        let mut alpaca_rx = alpaca_ws::spawn_alpaca_feed(alpaca_cfg);

        // Main loop: consume trades and quotes from Alpaca
        info!("Waiting for live Alpaca trades + quotes...");

        loop {
            match alpaca_rx.recv().await {
                Some(alpaca_ws::AlpacaFeedMsg::Trade(raw_tick)) => {
                    process_tick(
                        &raw_tick,
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
                Some(alpaca_ws::AlpacaFeedMsg::Quote(nbbo)) => {
                    // Update classifier with NBBO for accurate buy/sell classification
                    classifier.update_quote(nbbo);
                }
                None => {
                    warn!("Alpaca feed channel closed");
                    break;
                }
            }
        }
    } else {
        // ── FALLBACK: ThetaData only ──
        let mode = ingestor.detect_mode().await;
        info!("No Alpaca — ThetaData ingestion mode: {:?}", mode);

        match mode {
            IngestionMode::Realtime => {
                info!("Using ThetaData Standard real-time NBBO as data source");
                {
                    let mut stats = state.stats.write().await;
                    stats.data_source = "ThetaData Realtime".to_string();
                }

                let poll_interval =
                    tokio::time::Duration::from_millis(config.poll_interval_ms);

                loop {
                    let (ticks, nbbo) = ingestor.poll_realtime().await;
                    if let Some(quote) = nbbo {
                        classifier.update_quote(quote);
                    }
                    for raw_tick in &ticks {
                        process_tick(
                            raw_tick,
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
                    tokio::time::sleep(poll_interval).await;
                }
            }
            _ => {
                info!("No real-time source — using ThetaData EOD replay");
                {
                    let mut stats = state.stats.write().await;
                    stats.data_source = "ThetaData EOD Replay".to_string();
                }

                let poll_interval =
                    tokio::time::Duration::from_millis(config.poll_interval_ms);

                loop {
                    let raw_ticks = ingestor.poll_replay().await;
                    if let Some(quote) = ingestor.poll_eod_quote().await {
                        classifier.update_quote(quote);
                    }
                    for raw_tick in &raw_ticks {
                        process_tick(
                            raw_tick,
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
                    tokio::time::sleep(poll_interval).await;
                }
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
    let fp_totals = if let FlowEvent::Footprint { total_buy_vol, total_sell_vol, .. } = &fp_event {
        Some((*total_buy_vol, *total_sell_vol))
    } else { None };
    publish_event(state, fp_event).await;

    // 2. Update CVD + detect delta flips / large trades
    let cvd_events = cvd_calc.process_tick(&classified);
    let mut latest_cvd: Option<(i64, i64, i64)> = None;
    for event in &cvd_events {
        if let FlowEvent::Cvd { value, delta_1m, delta_5m, .. } = event {
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

    // Update flow state snapshot for Python signal bridge
    {
        let mut fs = state.flow_state.write().await;
        fs.last_price = classified.price;
        fs.ticks_processed += 1;
        if let Some((cvd, d1m, d5m)) = latest_cvd {
            fs.cvd = cvd;
            fs.delta_1m = d1m;
            fs.delta_5m = d5m;
        }
        if let Some((buy_vol, sell_vol)) = fp_totals {
            fs.total_buy_vol = buy_vol;
            fs.total_sell_vol = sell_vol;
        }
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
            (stats.ticks_processed, stats.last_price, stats.data_source.clone())
        };
        let _ = tx.send(FlowEvent::Heartbeat {
            timestamp: chrono::Utc::now(),
            ticks_processed: ticks,
            last_price: price,
            data_source: if source.is_empty() { None } else { Some(source) },
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
            let _ = state.external_tx.send(json);
            StatusCode::OK
        }
        Err(_) => StatusCode::BAD_REQUEST,
    }
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

async fn flow_state_handler(
    State(state): State<Arc<AppState>>,
) -> Json<FlowStateSnapshot> {
    let snapshot = state.flow_state.read().await.clone();
    Json(snapshot)
}

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket handler — streams FlowEvents to connected agents
// ─────────────────────────────────────────────────────────────────────────────

async fn ws_handler(
    ws: WebSocketUpgrade,
    State(state): State<Arc<AppState>>,
) -> impl IntoResponse {
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

    let recv_task = tokio::spawn(async move {
        while let Some(Ok(_msg)) = receiver.next().await {}
    });

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
