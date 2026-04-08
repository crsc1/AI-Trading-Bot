/**
 * WebSocket client with auto-reconnect and message routing.
 * Logs connect/disconnect events for debugging.
 */
export interface WSConfig {
  url: string;
  name?: string;  // Identifier for logging (e.g. 'SIP', 'Engine', 'Chat')
  onMessage: (data: any) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  maxRetries?: number;
  encoding?: 'json' | 'protobuf';
  skipTypes?: string[];  // Skip messages containing these strings (pre-JSON.parse filter)
}

export class WSClient {
  private ws: WebSocket | null = null;
  private config: WSConfig;
  private retryCount = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;
  private label: string;

  constructor(config: WSConfig) {
    this.config = {
      maxRetries: 10,
      encoding: 'json',
      ...config,
    };
    this.label = config.name || new URL(config.url).pathname;
  }

  connect() {
    if (this.destroyed) return;
    if (this.ws?.readyState === WebSocket.OPEN) return;

    console.log(`[WS:${this.label}] Connecting to ${this.config.url}...`);

    try {
      this.ws = new WebSocket(this.config.url);

      this.ws.onopen = () => {
        console.log(`[WS:${this.label}] Connected (retry count was ${this.retryCount})`);
        this.retryCount = 0;
        this.config.onConnect?.();
      };

      this.ws.onmessage = (event) => {
        try {
          if (this.config.encoding === 'json') {
            // Fast pre-filter: skip high-frequency messages we don't use.
            const raw = event.data as string;
            if (this.config.skipTypes) {
              for (const skip of this.config.skipTypes) {
                if (raw.indexOf(skip) < 20 && raw.indexOf(skip) >= 0) return;
              }
            }
            const data = JSON.parse(raw);
            this.config.onMessage(data);
          } else {
            this.config.onMessage(event.data);
          }
        } catch (e) {
          console.warn(`[WS:${this.label}] Parse error:`, e);
        }
      };

      this.ws.onclose = (ev) => {
        console.warn(`[WS:${this.label}] Disconnected (code=${ev.code} reason="${ev.reason || 'none'}")`);
        this.config.onDisconnect?.();
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        // onclose fires after onerror
      };
    } catch (e) {
      console.error(`[WS:${this.label}] Connection error:`, e);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.destroyed) return;
    if (this.retryCount >= (this.config.maxRetries ?? 10)) {
      console.error(`[WS:${this.label}] Max retries (${this.config.maxRetries}) reached, giving up`);
      return;
    }

    const delay = Math.min(3000 * Math.pow(2, this.retryCount), 60000);
    this.retryCount++;
    console.log(`[WS:${this.label}] Reconnecting in ${delay}ms (attempt ${this.retryCount})...`);

    this.retryTimer = setTimeout(() => {
      this.connect();
    }, delay);
  }

  send(data: unknown) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  destroy() {
    this.destroyed = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.close();
      this.ws = null;
    }
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
