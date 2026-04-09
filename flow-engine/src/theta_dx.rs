//! ThetaDataDx direct ingestion — FPSS real-time streaming without Java Terminal.
//!
//! Architecture:
//!   FpssClient (blocking std::thread with LMAX Disruptor)
//!     → tokio mpsc channel
//!     → main engine broadcast channels
//!
//! The FPSS callback runs on a dedicated OS thread (not tokio). We bridge
//! to async via a bounded mpsc channel. If the channel fills (engine too slow),
//! we drop events rather than block the FPSS thread — market data is ephemeral.
//!
//! Graceful fallback: if credentials are missing or connection fails,
//! returns Ok(None) so the engine continues with the Python /ingest path.

use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::{error, info, warn};

use thetadatadx::auth::Credentials;
use thetadatadx::config::DirectConfig;
use thetadatadx::fpss::protocol::Contract;
use thetadatadx::fpss::{FpssClient, FpssData, FpssEvent};

/// Events from the FPSS stream, normalized for our pipeline.
#[derive(Debug, Clone)]
pub enum ThetaDxEvent {
    OptionQuote {
        symbol: Arc<str>,
        contract_id: i32,
        bid: f64,
        ask: f64,
        bid_size: i32,
        ask_size: i32,
        ms_of_day: i32,
        date: i32,
    },
    OptionTrade {
        symbol: Arc<str>,
        contract_id: i32,
        price: f64,
        size: i32,
        condition: i32,
        exchange: i32,
        ms_of_day: i32,
        date: i32,
    },
    EquityQuote {
        symbol: Arc<str>,
        bid: f64,
        ask: f64,
        bid_size: i32,
        ask_size: i32,
        ms_of_day: i32,
    },
    EquityTrade {
        symbol: Arc<str>,
        price: f64,
        size: i32,
        exchange: i32,
        ms_of_day: i32,
    },
}

/// Configuration for which symbols to subscribe.
pub struct ThetaDxConfig {
    /// Equity symbols for quotes + trades (e.g., ["SPY", "QQQ"])
    pub equity_symbols: Vec<String>,
    /// Option contracts: (root, expiration YYYYMMDD, strike "$", right "C"/"P")
    pub option_contracts: Vec<(String, String, String, String)>,
}

/// Start the ThetaDataDx FPSS streaming client.
///
/// Returns `Ok(Some(rx))` with a channel receiver for events, or `Ok(None)` if
/// credentials are missing / connection fails (graceful fallback to Python path).
///
/// The `FpssClient` handle is returned so the caller can subscribe additional
/// contracts later and shut down cleanly.
pub fn start_theta_dx(
    config: &ThetaDxConfig,
    channel_size: usize,
) -> Result<Option<(mpsc::Receiver<ThetaDxEvent>, FpssClient)>, Box<dyn std::error::Error + Send + Sync>> {
    // Load credentials from environment
    let email = std::env::var("THETADATA_EMAIL").ok();
    let password = std::env::var("THETADATA_PASSWORD").ok();

    let creds = match (email, password) {
        (Some(e), Some(p)) if !e.is_empty() && !p.is_empty() => {
            Credentials::new(e, p)
        }
        _ => {
            // Try file-based credentials
            match Credentials::from_file("creds.txt") {
                Ok(c) => c,
                Err(_) => {
                    warn!("ThetaDataDx: no credentials found (set THETADATA_EMAIL + THETADATA_PASSWORD or create creds.txt). Falling back to Python path.");
                    return Ok(None);
                }
            }
        }
    };

    let hosts = DirectConfig::production().fpss_hosts;
    let (tx, rx) = mpsc::channel::<ThetaDxEvent>(channel_size);

    // Start FPSS client with callback on Disruptor thread
    let tx_clone = tx.clone();
    let client = match FpssClient::connect(
        &creds,
        &hosts,
        4096, // ring buffer size
        Default::default(),
        Default::default(),
        true, // auto-reconnect
        move |event: &FpssEvent| {
            match event {
                FpssEvent::Data(FpssData::Quote {
                    contract_id, symbol, bid, ask,
                    bid_size, ask_size, ms_of_day, date, ..
                }) => {
                    // Use try_send to never block the FPSS thread
                    let _ = tx_clone.try_send(ThetaDxEvent::OptionQuote {
                        symbol: symbol.clone(),
                        contract_id: *contract_id,
                        bid: *bid,
                        ask: *ask,
                        bid_size: *bid_size,
                        ask_size: *ask_size,
                        ms_of_day: *ms_of_day,
                        date: *date,
                    });
                }
                FpssEvent::Data(FpssData::Trade {
                    contract_id, symbol, price, size,
                    condition, exchange, ms_of_day, date, ..
                }) => {
                    let _ = tx_clone.try_send(ThetaDxEvent::OptionTrade {
                        symbol: symbol.clone(),
                        contract_id: *contract_id,
                        price: *price,
                        size: *size,
                        condition: *condition,
                        exchange: *exchange,
                        ms_of_day: *ms_of_day,
                        date: *date,
                    });
                }
                FpssEvent::Control(ctrl) => {
                    info!("ThetaDataDx control event: {:?}", ctrl);
                }
                _ => {}
            }
        },
    ) {
        Ok(c) => c,
        Err(e) => {
            warn!("ThetaDataDx connection failed: {e}. Falling back to Python path.");
            return Ok(None);
        }
    };

    info!("ThetaDataDx FPSS connected successfully");

    // Subscribe to equity symbols
    for sym in &config.equity_symbols {
        if let Err(e) = client.subscribe_quotes(&Contract::stock(sym.as_str())) {
            error!("ThetaDataDx: failed to subscribe quotes for {sym}: {e}");
        }
        if let Err(e) = client.subscribe_trades(&Contract::stock(sym.as_str())) {
            error!("ThetaDataDx: failed to subscribe trades for {sym}: {e}");
        }
        info!("ThetaDataDx: subscribed to {sym} quotes + trades");
    }

    // Subscribe to option contracts
    for (root, exp, strike, right) in &config.option_contracts {
        let contract = Contract::option(root.as_str(), exp.as_str(), strike.as_str(), right.as_str());
        if let Err(e) = client.subscribe_quotes(&contract) {
            error!("ThetaDataDx: failed to subscribe option quote {root} {exp} {strike}{right}: {e}");
        }
        if let Err(e) = client.subscribe_trades(&contract) {
            error!("ThetaDataDx: failed to subscribe option trade {root} {exp} {strike}{right}: {e}");
        }
    }

    Ok(Some((rx, client)))
}
