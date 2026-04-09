/**
 * Dual-transport client — WebTransport (QUIC) with WebSocket fallback.
 *
 * Feature-detects WebTransport support. Chrome/Firefox use QUIC datagrams
 * for lowest latency. Safari and older browsers fall back to WebSocket
 * binary frames. Both paths deliver ArrayBuffer to the same handler.
 */

export interface TransportClient {
  onMessage(handler: (buffer: ArrayBuffer) => void): void;
  close(): void;
  readonly connected: boolean;
  readonly transport: 'webtransport' | 'websocket';
}

// ── WebTransport Client ────────────────────────────────────────────────────

class WebTransportClient implements TransportClient {
  private wt: WebTransport;
  private handler: ((buffer: ArrayBuffer) => void) | null = null;
  private reading = false;
  readonly transport = 'webtransport' as const;

  constructor(wt: WebTransport) {
    this.wt = wt;
  }

  onMessage(handler: (buffer: ArrayBuffer) => void) {
    this.handler = handler;
    if (!this.reading) {
      this.reading = true;
      this.readDatagrams();
    }
  }

  private async readDatagrams() {
    try {
      const reader = this.wt.datagrams.readable.getReader();
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        // value is Uint8Array — convert to ArrayBuffer for consistency
        if (value && this.handler) {
          this.handler(value.buffer as ArrayBuffer);
        }
      }
    } catch {
      // Connection closed
    }
  }

  close() {
    try { this.wt.close(); } catch {}
  }

  get connected(): boolean {
    return this.wt.ready !== undefined;
  }
}

// ── WebSocket Client (fallback) ────────────────────────────────────────────

class WebSocketTransportClient implements TransportClient {
  private ws: WebSocket;
  private handler: ((buffer: ArrayBuffer) => void) | null = null;
  readonly transport = 'websocket' as const;

  constructor(url: string) {
    this.ws = new WebSocket(url);
    this.ws.binaryType = 'arraybuffer';
    this.ws.onmessage = (event) => {
      if (this.handler && event.data instanceof ArrayBuffer) {
        this.handler(event.data);
      }
    };
  }

  onMessage(handler: (buffer: ArrayBuffer) => void) {
    this.handler = handler;
  }

  close() {
    this.ws.onclose = null;
    this.ws.close();
  }

  get connected(): boolean {
    return this.ws.readyState === WebSocket.OPEN;
  }
}

// ── Factory ────────────────────────────────────────────────────────────────

function timeout(ms: number): Promise<never> {
  return new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), ms));
}

/**
 * Fetch the self-signed cert hash from the Rust engine.
 * Required for WebTransport with self-signed certs in dev.
 */
async function fetchCertHash(host: string, wsPort: number): Promise<ArrayBuffer | null> {
  try {
    const resp = await fetch(`http://${host}:${wsPort}/cert-hash`);
    if (!resp.ok) return null;
    const data = await resp.json();
    if (data.value && Array.isArray(data.value)) {
      return new Uint8Array(data.value).buffer;
    }
  } catch {}
  return null;
}

/**
 * Create the best available transport connection.
 * Tries WebTransport first (QUIC, no HoL blocking), falls back to WebSocket.
 */
export async function createTransport(
  host: string,
  wtPort = 4433,
  wsPort = 8081,
): Promise<TransportClient> {
  // Try WebTransport first (Chrome 114+, Firefox partial)
  if (typeof WebTransport !== 'undefined') {
    try {
      // Fetch self-signed cert hash from Rust engine for dev mode
      const certHash = await fetchCertHash(host, wsPort);

      const url = `https://${host}:${wtPort}`;
      const options: any = {};

      if (certHash) {
        options.serverCertificateHashes = [{
          algorithm: 'sha-256',
          value: certHash,
        }];
        console.log('[Transport] Using self-signed cert hash for WebTransport');
      }

      const wt = new WebTransport(url, options);

      // Race: connect within 3 seconds or fall through
      await Promise.race([wt.ready, timeout(3000)]);
      console.log(`[Transport] WebTransport connected to ${url}`);
      return new WebTransportClient(wt);
    } catch (e) {
      console.warn('[Transport] WebTransport failed, falling back to WebSocket:', e);
    }
  }

  // Fallback: WebSocket (Safari, cert issues, older browsers)
  const wsUrl = `ws://${host}:${wsPort}/ws`;
  console.log(`[Transport] Using WebSocket fallback: ${wsUrl}`);
  return new WebSocketTransportClient(wsUrl);
}
