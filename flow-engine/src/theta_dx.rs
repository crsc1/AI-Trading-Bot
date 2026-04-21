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
//! returns an unavailable status so the engine continues with the Python
//! /ingest path and can report why ThetaDataDx is inactive.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};
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
        root: Arc<str>,
        expiration: i32,
        strike: f64,
        right: Arc<str>,
        contract_id: i32,
        bid: f64,
        ask: f64,
        bid_size: i32,
        ask_size: i32,
        ms_of_day: i32,
        date: i32,
    },
    OptionTrade {
        root: Arc<str>,
        expiration: i32,
        strike: f64,
        right: Arc<str>,
        contract_id: i32,
        price: f64,
        size: i32,
        premium: f64,
        side: &'static str,
        condition: i32,
        exchange: i32,
        ms_of_day: i32,
        date: i32,
    },
    OptionOpenInterest {
        root: Arc<str>,
        expiration: i32,
        strike: f64,
        right: Arc<str>,
        contract_id: i32,
        open_interest: i32,
        ms_of_day: i32,
        date: i32,
    },
}

#[derive(Debug, Clone)]
enum ParsedFpssSymbol {
    Option {
        root: Arc<str>,
        expiration: i32,
        strike: f64,
        right: Arc<str>,
    },
    Equity {
        root: Arc<str>,
    },
}

fn parse_fpss_symbol(symbol: &str) -> Option<ParsedFpssSymbol> {
    let parts: Vec<&str> = symbol.split_whitespace().collect();
    match parts.as_slice() {
        [root, "STOCK"] => Some(ParsedFpssSymbol::Equity {
            root: Arc::<str>::from((*root).to_owned()),
        }),
        [root, "OPTION", expiration, right, strike_raw] => {
            let expiration = expiration.parse().ok()?;
            let strike_raw = strike_raw.parse::<i32>().ok()?;
            let right = if right.eq_ignore_ascii_case("P") {
                Arc::<str>::from("P")
            } else {
                Arc::<str>::from("C")
            };
            Some(ParsedFpssSymbol::Option {
                root: Arc::<str>::from((*root).to_owned()),
                expiration,
                strike: strike_raw as f64 / 1000.0,
                right,
            })
        }
        _ => None,
    }
}

fn classify_trade_side(price: f64, bid: f64, ask: f64) -> &'static str {
    if bid > 0.0 && ask > 0.0 {
        if price >= ask {
            "buy"
        } else if price <= bid {
            "sell"
        } else {
            "mid"
        }
    } else {
        "mid"
    }
}

/// Configuration for which option contracts to subscribe.
pub struct ThetaDxConfig {
    /// Option contracts: (root, expiration YYYYMMDD, strike "$", right "C"/"P")
    pub option_contracts: Vec<(String, String, String, String)>,
}

pub enum ThetaDxStartOutcome {
    Connected {
        rx: mpsc::Receiver<ThetaDxEvent>,
        client: FpssClient,
        credential_source: &'static str,
    },
    Unavailable {
        reason: String,
        credential_source: Option<&'static str>,
    },
}

/// Start the ThetaDataDx FPSS streaming client.
///
/// Returns the live channel when connected, or an unavailable status with a
/// reason so the caller can report runtime diagnostics without scraping logs.
pub fn start_theta_dx(config: &ThetaDxConfig, channel_size: usize) -> ThetaDxStartOutcome {
    // Load credentials from environment
    let email = std::env::var("THETADATA_EMAIL").ok();
    let password = std::env::var("THETADATA_PASSWORD").ok();

    let (creds, credential_source) = match (email, password) {
        (Some(e), Some(p)) if !e.is_empty() && !p.is_empty() => {
            (Credentials::new(e, p), "environment")
        }
        _ => {
            // Try file-based credentials
            match Credentials::from_file("creds.txt") {
                Ok(c) => (c, "creds.txt"),
                Err(_) => {
                    warn!("ThetaDataDx: no credentials found (set THETADATA_EMAIL + THETADATA_PASSWORD or create creds.txt). Falling back to Python path.");
                    return ThetaDxStartOutcome::Unavailable {
                        reason: "missing_credentials".to_string(),
                        credential_source: None,
                    };
                }
            }
        }
    };

    let hosts = DirectConfig::production().fpss_hosts;
    let (tx, rx) = mpsc::channel::<ThetaDxEvent>(channel_size);
    let quote_book: Arc<RwLock<HashMap<i32, (f64, f64)>>> = Arc::new(RwLock::new(HashMap::new()));

    // Start FPSS client with callback on Disruptor thread
    let tx_clone = tx.clone();
    let quote_book_clone = quote_book.clone();
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
                    contract_id,
                    symbol,
                    bid,
                    ask,
                    bid_size,
                    ask_size,
                    ms_of_day,
                    date,
                    ..
                }) => {
                    match parse_fpss_symbol(symbol.as_ref()) {
                        Some(ParsedFpssSymbol::Option {
                            root,
                            expiration,
                            strike,
                            right,
                        }) => {
                            if let Ok(mut quotes) = quote_book_clone.write() {
                                quotes.insert(*contract_id, (*bid, *ask));
                            }
                            // Use try_send to never block the FPSS thread
                            let _ = tx_clone.try_send(ThetaDxEvent::OptionQuote {
                                root,
                                expiration,
                                strike,
                                right,
                                contract_id: *contract_id,
                                bid: *bid,
                                ask: *ask,
                                bid_size: *bid_size,
                                ask_size: *ask_size,
                                ms_of_day: *ms_of_day,
                                date: *date,
                            });
                        }
                        Some(ParsedFpssSymbol::Equity { .. }) => {
                            // Equity quotes handled by Alpaca, skip
                        }
                        None => {
                            warn!("ThetaDataDx: could not parse quote symbol {symbol}");
                        }
                    }
                }
                FpssEvent::Data(FpssData::Trade {
                    contract_id,
                    symbol,
                    price,
                    size,
                    condition,
                    exchange,
                    ms_of_day,
                    date,
                    ..
                }) => match parse_fpss_symbol(symbol.as_ref()) {
                    Some(ParsedFpssSymbol::Option {
                        root,
                        expiration,
                        strike,
                        right,
                    }) => {
                        let (bid, ask) = quote_book_clone
                            .read()
                            .ok()
                            .and_then(|quotes| quotes.get(contract_id).copied())
                            .unwrap_or((0.0, 0.0));
                        let side = classify_trade_side(*price, bid, ask);
                        let _ = tx_clone.try_send(ThetaDxEvent::OptionTrade {
                            root,
                            expiration,
                            strike,
                            right,
                            contract_id: *contract_id,
                            price: *price,
                            size: *size,
                            premium: *price * *size as f64 * 100.0,
                            side,
                            condition: *condition,
                            exchange: *exchange,
                            ms_of_day: *ms_of_day,
                            date: *date,
                        });
                    }
                    Some(ParsedFpssSymbol::Equity { .. }) => {
                        // Equity trades handled by Alpaca, skip
                    }
                    None => {
                        warn!("ThetaDataDx: could not parse trade symbol {symbol}");
                    }
                },
                FpssEvent::Data(FpssData::OpenInterest {
                    contract_id,
                    symbol,
                    open_interest,
                    ms_of_day,
                    date,
                    ..
                }) => match parse_fpss_symbol(symbol.as_ref()) {
                    Some(ParsedFpssSymbol::Option {
                        root,
                        expiration,
                        strike,
                        right,
                    }) => {
                        let _ = tx_clone.try_send(ThetaDxEvent::OptionOpenInterest {
                            root,
                            expiration,
                            strike,
                            right,
                            contract_id: *contract_id,
                            open_interest: *open_interest,
                            ms_of_day: *ms_of_day,
                            date: *date,
                        });
                    }
                    _ => {}
                },
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
            return ThetaDxStartOutcome::Unavailable {
                reason: format!("connection_failed: {e}"),
                credential_source: Some(credential_source),
            };
        }
    };

    info!("ThetaDataDx FPSS connected successfully");

    // Subscribe to option contracts
    for (root, exp, strike, right) in &config.option_contracts {
        let contract =
            Contract::option(root.as_str(), exp.as_str(), strike.as_str(), right.as_str());
        if let Err(e) = client.subscribe_quotes(&contract) {
            error!(
                "ThetaDataDx: failed to subscribe option quote {root} {exp} {strike}{right}: {e}"
            );
        }
        if let Err(e) = client.subscribe_trades(&contract) {
            error!(
                "ThetaDataDx: failed to subscribe option trade {root} {exp} {strike}{right}: {e}"
            );
        }
    }

    ThetaDxStartOutcome::Connected {
        rx,
        client,
        credential_source,
    }
}

#[cfg(test)]
mod tests {
    use super::{classify_trade_side, parse_fpss_symbol, ParsedFpssSymbol};

    #[test]
    fn parses_option_symbol_fields() {
        match parse_fpss_symbol("SPY OPTION 20261218 P 45000") {
            Some(ParsedFpssSymbol::Option {
                root,
                expiration,
                strike,
                right,
            }) => {
                assert_eq!(root.as_ref(), "SPY");
                assert_eq!(expiration, 20261218);
                assert_eq!(strike, 45.0);
                assert_eq!(right.as_ref(), "P");
            }
            other => panic!("unexpected parse result: {other:?}"),
        }
    }

    #[test]
    fn parses_stock_symbol_fields() {
        match parse_fpss_symbol("SPY STOCK") {
            Some(ParsedFpssSymbol::Equity { root }) => {
                assert_eq!(root.as_ref(), "SPY");
            }
            other => panic!("unexpected parse result: {other:?}"),
        }
    }

    #[test]
    fn classifies_trade_side_from_quote_edge() {
        assert_eq!(classify_trade_side(2.15, 2.00, 2.15), "buy");
        assert_eq!(classify_trade_side(2.00, 2.00, 2.15), "sell");
        assert_eq!(classify_trade_side(2.07, 2.00, 2.15), "mid");
    }
}
