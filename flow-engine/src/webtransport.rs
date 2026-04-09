//! WebTransport (QUIC) server — low-latency binary delivery to browsers.
//!
//! Runs alongside the WebSocket server on a separate port (default 4433).
//! Chrome/Firefox connect via WebTransport; Safari falls back to WebSocket.
//!
//! All messages are protobuf-encoded MarketMessage, same as the WebSocket path.

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{broadcast, RwLock};
use tracing::{error, info, warn};
use wtransport::{Endpoint, Identity, ServerConfig};

use crate::events::FlowEvent;
use crate::proto;

fn base64_encode(data: &[u8]) -> String {
    const CHARS: &[u8] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut result = String::new();
    for chunk in data.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = if chunk.len() > 1 { chunk[1] as u32 } else { 0 };
        let b2 = if chunk.len() > 2 { chunk[2] as u32 } else { 0 };
        let n = (b0 << 16) | (b1 << 8) | b2;
        result.push(CHARS[(n >> 18 & 0x3F) as usize] as char);
        result.push(CHARS[(n >> 12 & 0x3F) as usize] as char);
        if chunk.len() > 1 { result.push(CHARS[(n >> 6 & 0x3F) as usize] as char); } else { result.push('='); }
        if chunk.len() > 2 { result.push(CHARS[(n & 0x3F) as usize] as char); } else { result.push('='); }
    }
    result
}

/// Shared cert hash for the /cert-hash endpoint.
/// Set once at WebTransport server startup.
pub static CERT_HASH: std::sync::OnceLock<Vec<u8>> = std::sync::OnceLock::new();

/// Start the WebTransport server.
pub async fn serve(
    flow_tx: broadcast::Sender<FlowEvent>,
    external_tx: broadcast::Sender<String>,
    port: u16,
) {
    let identity = match Identity::self_signed(["localhost", "127.0.0.1", "::1"]) {
        Ok(id) => id,
        Err(e) => {
            error!("WebTransport: failed to create self-signed identity: {e}");
            return;
        }
    };

    // Extract and store the cert SHA-256 hash for browser serverCertificateHashes
    let certs = identity.certificate_chain();
    if let Some(cert) = certs.as_slice().first() {
        let hash = cert.hash();
        let hash_bytes = hash.as_ref().to_vec();
        let hex = hash_bytes.iter().map(|b| format!("{:02x}", b)).collect::<String>();
        info!("WebTransport cert SHA-256: {hex}");
        info!("WebTransport cert hash (base64): {}", base64_encode(&hash_bytes));
        let _ = CERT_HASH.set(hash_bytes);
    }

    info!("WebTransport server starting on port {port}");

    let config = ServerConfig::builder()
        .with_bind_default(port)
        .with_identity(identity)
        .keep_alive_interval(Some(Duration::from_secs(3)))
        .build();

    let server = match Endpoint::server(config) {
        Ok(s) => s,
        Err(e) => {
            error!("WebTransport: failed to create endpoint: {e}");
            return;
        }
    };

    info!("WebTransport server listening on port {port}");

    loop {
        let incoming = server.accept().await;
        let flow_rx = flow_tx.subscribe();
        let ext_rx = external_tx.subscribe();

        tokio::spawn(async move {
            match incoming.await {
                Ok(request) => {
                    match request.accept().await {
                        Ok(connection) => {
                            info!("WebTransport client connected");
                            handle_session(connection, flow_rx, ext_rx).await;
                            info!("WebTransport client disconnected");
                        }
                        Err(e) => warn!("WebTransport: session accept failed: {e}"),
                    }
                }
                Err(e) => warn!("WebTransport: incoming connection failed: {e}"),
            }
        });
    }
}

/// Handle a single WebTransport session.
/// Sends all events as datagrams (simplest, lowest latency).
/// If a datagram is too large for MTU, it's dropped — the next event replaces it.
async fn handle_session(
    connection: wtransport::Connection,
    mut flow_rx: broadcast::Receiver<FlowEvent>,
    mut ext_rx: broadcast::Receiver<String>,
) {
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

        // Send as datagram — unreliable but lowest latency.
        // If the message exceeds MTU (~1200 bytes), it will be dropped.
        // For large messages (footprint with many levels), this is acceptable
        // since the next footprint update replaces it.
        if let Err(e) = connection.send_datagram(bytes) {
            warn!("WebTransport datagram send failed: {e}");
            break;
        }
    }
}
