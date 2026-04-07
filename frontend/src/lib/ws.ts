/**
 * WebSocket client with auto-reconnect and message routing.
 * Supports both JSON (current) and Protobuf (future) encoding.
 */
export interface WSConfig {
  url: string;
  onMessage: (data: any) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  maxRetries?: number;
  encoding?: 'json' | 'protobuf';
}

export class WSClient {
  private ws: WebSocket | null = null;
  private config: WSConfig;
  private retryCount = 0;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private destroyed = false;

  constructor(config: WSConfig) {
    this.config = {
      maxRetries: 10,
      encoding: 'json',
      ...config,
    };
  }

  connect() {
    if (this.destroyed) return;
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      this.ws = new WebSocket(this.config.url);

      this.ws.onopen = () => {
        this.retryCount = 0;
        this.config.onConnect?.();
      };

      this.ws.onmessage = (event) => {
        try {
          if (this.config.encoding === 'json') {
            const data = JSON.parse(event.data);
            this.config.onMessage(data);
          } else {
            // Protobuf decode path — will be implemented when backend adds support
            this.config.onMessage(event.data);
          }
        } catch (e) {
          console.warn('[WS] Failed to parse message:', e);
        }
      };

      this.ws.onclose = () => {
        this.config.onDisconnect?.();
        this.scheduleReconnect();
      };

      this.ws.onerror = () => {
        // onclose will fire after onerror
      };
    } catch (e) {
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (this.destroyed) return;
    if (this.retryCount >= (this.config.maxRetries ?? 10)) return;

    const delay = Math.min(3000 * Math.pow(2, this.retryCount), 60000);
    this.retryCount++;

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
      this.ws.onclose = null; // Prevent reconnect on intentional close
      this.ws.close();
      this.ws = null;
    }
  }

  get connected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
