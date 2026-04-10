//! Alpaca real-time WebSocket feed for live trade data.
//!
//! Connects to Alpaca's SIP real-time stream via WebSocket:
//!   wss://stream.data.alpaca.markets/v2/sip  (Algo Trader Plus)
//!
//! Protocol:
//!   1. Connect → receive [{"T":"success","msg":"connected"}]
//!   2. Auth    → send {"action":"auth","key":"...","secret":"..."}
//!              → receive [{"T":"success","msg":"authenticated"}]
//!   3. Sub     → send {"action":"subscribe","trades":["SPY"]}
//!              → receive [{"T":"subscription","trades":["SPY"],...}]
//!   4. Stream  → receive [{"T":"t","S":"SPY","p":562.35,"s":100,"t":"...","c":[...],...}]
//!
//! SIP feed: Full real-time trades from all US exchanges (requires Algo Trader Plus).

use crate::events::{RawTick, TickSource};
use chrono::{DateTime, Utc};
use futures::{SinkExt, StreamExt};
use serde::{Deserialize, Serialize};
use tokio::sync::mpsc;
use tokio_tungstenite::{connect_async, tungstenite::Message};
use tracing::{error, info, warn};

// ─────────────────────────────────────────────────────────────────────────────
// Configuration
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Clone)]
pub struct AlpacaWsConfig {
    pub api_key: String,
    pub secret_key: String,
    pub symbol: String,
    /// WebSocket URL (default: wss://stream.data.alpaca.markets/v2/sip for Algo Trader Plus)
    pub ws_url: String,
}

impl AlpacaWsConfig {
    pub fn from_env() -> Option<Self> {
        let api_key = std::env::var("ALPACA_API_KEY").ok()?;
        let secret_key = std::env::var("ALPACA_SECRET_KEY").ok()?;

        if api_key.is_empty() || secret_key.is_empty() {
            return None;
        }

        let symbol = std::env::var("TRADING_SYMBOL").unwrap_or_else(|_| "SPY".to_string());
        let ws_url = std::env::var("ALPACA_WS_URL")
            .unwrap_or_else(|_| "wss://stream.data.alpaca.markets/v2/sip".to_string());

        Some(Self {
            api_key,
            secret_key,
            symbol,
            ws_url,
        })
    }

    pub fn is_configured(&self) -> bool {
        !self.api_key.is_empty() && !self.secret_key.is_empty()
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Alpaca WebSocket message types
// ─────────────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize)]
struct AlpacaAuthMsg {
    action: String,
    key: String,
    secret: String,
}

#[derive(Debug, Serialize)]
struct AlpacaSubMsg {
    action: String,
    trades: Vec<String>,
    quotes: Vec<String>,
}

/// A single message element from Alpaca's stream.
/// The `T` field discriminates: "success", "error", "subscription", "t" (trade), "q" (quote).
#[derive(Debug, Deserialize)]
struct AlpacaStreamElement {
    #[serde(rename = "T")]
    msg_type: String,
    /// For success messages
    msg: Option<String>,
    /// For trade messages
    #[serde(rename = "S")]
    symbol: Option<String>,
    /// Trade price / Quote: ask price
    p: Option<f64>,
    /// Trade size / Quote: ask size
    s: Option<u64>,
    /// Timestamp (RFC3339)
    t: Option<String>,
    /// Conditions
    c: Option<Vec<String>>,
    /// Error code
    code: Option<i32>,
    /// Quote: bid price
    bp: Option<f64>,
    /// Quote: bid size
    bs: Option<u64>,
    /// Quote: ask price
    ap: Option<f64>,
    /// Quote: ask size
    #[serde(rename = "as")]
    ask_size: Option<u64>,
}

// ─────────────────────────────────────────────────────────────────────────────
// Alpaca WebSocket client
// ─────────────────────────────────────────────────────────────────────────────

use crate::events::NbboQuote;

/// Output from the Alpaca feed: either a trade tick or a quote update.
#[derive(Debug, Clone)]
pub enum AlpacaFeedMsg {
    Trade(RawTick),
    Quote(NbboQuote),
}

#[derive(Debug)]
enum AlpacaConnectError {
    Retryable(String),
    Fatal(String),
}

impl std::fmt::Display for AlpacaConnectError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Retryable(msg) | Self::Fatal(msg) => f.write_str(msg),
        }
    }
}

impl std::error::Error for AlpacaConnectError {}

/// Spawns an Alpaca WebSocket connection that sends trades + quotes through an mpsc channel.
/// Automatically reconnects on disconnect with exponential backoff.
pub fn spawn_alpaca_feed(config: AlpacaWsConfig) -> mpsc::Receiver<AlpacaFeedMsg> {
    let (tx, rx) = mpsc::channel::<AlpacaFeedMsg>(10_000);

    tokio::spawn(async move {
        let mut backoff_secs = 1u64;

        loop {
            match run_alpaca_connection(&config, &tx).await {
                Ok(()) => {
                    info!("Alpaca WebSocket closed gracefully");
                    backoff_secs = 1; // Reset on clean close
                }
                Err(AlpacaConnectError::Retryable(e)) => {
                    error!("Alpaca WebSocket error: {}", e);
                }
                Err(AlpacaConnectError::Fatal(e)) => {
                    error!("Alpaca WebSocket fatal error: {}", e);
                    break;
                }
            }

            // Don't reconnect if channel is closed (receiver dropped)
            if tx.is_closed() {
                info!("Alpaca feed channel closed — stopping reconnect");
                break;
            }

            warn!("Alpaca WebSocket reconnecting in {}s...", backoff_secs);
            tokio::time::sleep(tokio::time::Duration::from_secs(backoff_secs)).await;
            backoff_secs = (backoff_secs * 2).min(60);
        }
    });

    rx
}

async fn run_alpaca_connection(
    config: &AlpacaWsConfig,
    tx: &mpsc::Sender<AlpacaFeedMsg>,
) -> Result<(), AlpacaConnectError> {
    info!("Connecting to Alpaca WebSocket: {}", config.ws_url);

    let (ws_stream, _response) = connect_async(&config.ws_url)
        .await
        .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
    let (mut write, mut read) = ws_stream.split();

    // Step 1: Wait for "connected" message
    if let Some(msg) = read.next().await {
        let msg = msg.map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
        if let Message::Text(text) = msg {
            let elements: Vec<AlpacaStreamElement> = serde_json::from_str(&text)
                .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
            if let Some(el) = elements.first() {
                if el.msg_type == "success" && el.msg.as_deref() == Some("connected") {
                    info!("Alpaca WebSocket connected");
                } else {
                    return Err(AlpacaConnectError::Retryable(format!(
                        "Unexpected first message: {:?}",
                        el
                    )));
                }
            }
        }
    }

    // Step 2: Authenticate
    let auth_msg = AlpacaAuthMsg {
        action: "auth".to_string(),
        key: config.api_key.clone(),
        secret: config.secret_key.clone(),
    };
    write
        .send(Message::Text(
            serde_json::to_string(&auth_msg)
                .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?
                .into(),
        ))
        .await
        .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;

    // Wait for auth response
    if let Some(msg) = read.next().await {
        let msg = msg.map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
        if let Message::Text(text) = msg {
            let elements: Vec<AlpacaStreamElement> = serde_json::from_str(&text)
                .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
            if let Some(el) = elements.first() {
                if el.msg_type == "success" && el.msg.as_deref() == Some("authenticated") {
                    info!("Alpaca WebSocket authenticated");
                } else if el.msg_type == "error" {
                    return Err(AlpacaConnectError::Fatal(format!(
                        "Alpaca auth failed (code {:?}): {:?}",
                        el.code, el.msg
                    )));
                }
            }
        }
    }

    // Step 3: Subscribe to trades + quotes (Algo Trader Plus — full SIP NBBO)
    let sub_msg = AlpacaSubMsg {
        action: "subscribe".to_string(),
        trades: vec![config.symbol.clone()],
        quotes: vec![config.symbol.clone()],
    };
    write
        .send(Message::Text(
            serde_json::to_string(&sub_msg)
                .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?
                .into(),
        ))
        .await
        .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;

    // Wait for subscription confirmation
    if let Some(msg) = read.next().await {
        let msg = msg.map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
        if let Message::Text(text) = msg {
            let elements: Vec<AlpacaStreamElement> = serde_json::from_str(&text)
                .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
            if let Some(el) = elements.first() {
                if el.msg_type == "subscription" {
                    info!("Alpaca subscribed to trades for {}", config.symbol);
                }
            }
        }
    }

    // Step 4: Stream trades
    let mut trade_count: u64 = 0;

    while let Some(msg) = read.next().await {
        let msg = msg.map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;

        match msg {
            Message::Text(text) => {
                // Alpaca sends arrays of elements
                match serde_json::from_str::<Vec<AlpacaStreamElement>>(&text) {
                    Ok(elements) => {
                        for el in elements {
                            if el.msg_type == "t" {
                                // Trade message
                                if let (Some(price), Some(size)) = (el.p, el.s) {
                                    let timestamp =
                                        el.t.as_ref()
                                            .and_then(|ts| ts.parse::<DateTime<Utc>>().ok())
                                            .unwrap_or_else(Utc::now);

                                    let conditions = el.c.unwrap_or_default();

                                    let tick = RawTick {
                                        price,
                                        size,
                                        timestamp,
                                        conditions,
                                        source: TickSource::Alpaca,
                                    };

                                    if tx.send(AlpacaFeedMsg::Trade(tick)).await.is_err() {
                                        return Ok(());
                                    }

                                    trade_count += 1;
                                    if trade_count % 1000 == 0 {
                                        info!(
                                            "Alpaca: {} trades received for {}",
                                            trade_count, config.symbol
                                        );
                                    }
                                }
                            } else if el.msg_type == "q" {
                                // Quote message — NBBO for buy/sell classification
                                if let (Some(bp), Some(ap)) = (el.bp, el.ap) {
                                    let timestamp =
                                        el.t.as_ref()
                                            .and_then(|ts| ts.parse::<DateTime<Utc>>().ok())
                                            .unwrap_or_else(Utc::now);

                                    let quote = NbboQuote {
                                        bid: bp,
                                        ask: ap,
                                        bid_size: el.bs.unwrap_or(0),
                                        ask_size: el.ask_size.unwrap_or(0),
                                        timestamp,
                                    };

                                    if tx.send(AlpacaFeedMsg::Quote(quote)).await.is_err() {
                                        return Ok(());
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!(
                            "Failed to parse Alpaca message: {} — raw: {}",
                            e,
                            &text[..text.len().min(200)]
                        );
                    }
                }
            }
            Message::Ping(data) => {
                write
                    .send(Message::Pong(data))
                    .await
                    .map_err(|e| AlpacaConnectError::Retryable(e.to_string()))?;
            }
            Message::Close(_) => {
                info!("Alpaca WebSocket received close frame");
                break;
            }
            _ => {}
        }
    }

    info!("Alpaca WebSocket stream ended after {} trades", trade_count);
    Ok(())
}
