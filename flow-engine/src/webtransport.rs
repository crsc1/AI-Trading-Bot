//! WebTransport (QUIC) server — low-latency binary delivery to browsers.
//!
//! Runs alongside the WebSocket server on a separate port (default 4433).
//! Chrome/Firefox connect via WebTransport; Safari falls back to WebSocket.
//!
//! All messages are protobuf-encoded MarketMessage, same as the WebSocket path.

use std::sync::Arc;
use std::time::Duration;
use tokio::sync::broadcast;
use tracing::{error, info, warn};
use wtransport::{Endpoint, Identity, ServerConfig};

use crate::events::FlowEvent;
use crate::proto;

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
