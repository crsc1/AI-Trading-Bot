/**
 * GPU-accelerated bubble renderer using PixiJS v8.
 *
 * Bookmap-style split-circle bubbles:
 * - Each bubble shows the buy/sell RATIO as a two-arc pie chart
 * - Green arc = buy volume proportion, Red arc = sell volume proportion
 * - Size = total volume (percentile-scaled)
 * - 11 quantized ratio steps × 5 size tiers = 55 pre-rendered textures
 * - Spray animation: new bubbles start 1.5x size with glow ring
 * - Age fade: older bubbles fade to 15% over the window duration
 */
import * as PIXI from 'pixi.js';

export interface BubblePoint {
  x: number;
  y: number;
  r: number;
  tMs: number;
  opacity: number;
  deltaRatio: number; // -1 (all sell) to +1 (all buy)
  buyRatio: number;   // 0.0 (all sell) to 1.0 (all buy) — drives split-circle texture
}

const TIER_NAMES = ['tiny', 'small', 'medium', 'large', 'huge'] as const;
type TierName = (typeof TIER_NAMES)[number];

const TIER_SIZES: Record<TierName, number> = {
  tiny: 10, small: 16, medium: 24, large: 36, huge: 52,
};

const MAX_SPRITES = 5000;

// 11 quantized buy ratio steps: 0%, 10%, 20%, ..., 100%
const RATIO_STEPS = 11;

// Colors for split-circle arcs
const BUY_COLORS = { center: '#4ade80', mid: '#22c55e', edge: '#16a34a' };
const SELL_COLORS = { center: '#f87171', mid: '#ef4444', edge: '#dc2626' };

export class FlowBubbleRenderer {
  private app: PIXI.Application | null = null;
  private bubbleContainer: PIXI.Container | null = null;
  private labelContainer: PIXI.Container | null = null;
  private textures: Map<string, PIXI.Texture> = new Map();
  // Fast lookup: texGrid[ratioIndex][tierIndex]
  // ratioIndex: 0 = 0% buy (all sell), 10 = 100% buy (all buy)
  private texGrid: PIXI.Texture[][] = [];
  private tierRadii: number[] = [];
  private spritePool: PIXI.Sprite[] = [];
  private poolIndex = 0;
  private initialized = false;
  private initPromise: Promise<void> | null = null;
  private textureRadii: Map<TierName, number> = new Map();

  async init(container: HTMLElement): Promise<void> {
    if (this.initPromise) return this.initPromise;
    this.initPromise = this._doInit(container);
    return this.initPromise;
  }

  private async _doInit(container: HTMLElement): Promise<void> {
    try {
      this.app = new PIXI.Application();
      const dpr = window.devicePixelRatio || 1;

      await this.app.init({
        backgroundAlpha: 0,
        antialias: true,
        resolution: dpr,
        autoDensity: true,
      });

      this.app.canvas.style.cssText =
        'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2;';
      const pos = getComputedStyle(container).position;
      if (pos === 'static') container.style.position = 'relative';
      container.appendChild(this.app.canvas);

      this.bubbleContainer = new PIXI.Container();
      this.bubbleContainer.sortableChildren = false;
      this.app.stage.addChild(this.bubbleContainer);

      this.labelContainer = new PIXI.Container();
      this.app.stage.addChild(this.labelContainer);

      this._createTextures(dpr);

      // Build fast lookup grid: texGrid[ratioIdx][tierIdx]
      this.texGrid = Array.from({ length: RATIO_STEPS }, (_, ri) =>
        TIER_NAMES.map(tn => this.textures.get(`r${ri}_${tn}`)!)
      );
      this.tierRadii = TIER_NAMES.map(tn => this.textureRadii.get(tn)!);
      this.initialized = true;
    } catch (err) {
      console.error('[FlowBubbleRenderer] Init failed:', err);
      this.initialized = false;
    }
  }

  private _createTextures(dpr: number): void {
    for (const name of TIER_NAMES) {
      const baseSize = TIER_SIZES[name];
      const r = Math.ceil(baseSize * dpr);
      this.textureRadii.set(name, r);

      for (let ri = 0; ri < RATIO_STEPS; ri++) {
        const buyFrac = ri / (RATIO_STEPS - 1); // 0.0 to 1.0

        const canvas = document.createElement('canvas');
        canvas.width = r * 2;
        canvas.height = r * 2;
        const ctx = canvas.getContext('2d')!;

        const circR = r * 0.92;
        const startAngle = -Math.PI / 2; // 12 o'clock

        if (buyFrac >= 0.999) {
          // Pure buy: solid green circle
          this._drawSolidCircle(ctx, r, circR, dpr, BUY_COLORS);
        } else if (buyFrac <= 0.001) {
          // Pure sell: solid red circle
          this._drawSolidCircle(ctx, r, circR, dpr, SELL_COLORS);
        } else {
          const buyAngle = buyFrac * 2 * Math.PI;

          // Buy arc (green) — from 12 o'clock, clockwise
          this._drawArc(ctx, r, circR, startAngle, startAngle + buyAngle, BUY_COLORS);

          // Sell arc (red) — remainder
          this._drawArc(ctx, r, circR, startAngle + buyAngle, startAngle + 2 * Math.PI, SELL_COLORS);

          // Full circle border — color interpolates between green and red
          const borderColor = buyFrac > 0.5
            ? BUY_COLORS.center + 'bb'
            : SELL_COLORS.center + 'bb';
          ctx.beginPath();
          ctx.arc(r, r, circR, 0, Math.PI * 2);
          ctx.strokeStyle = borderColor;
          ctx.lineWidth = Math.max(1, 1.5 * dpr);
          ctx.stroke();
        }

        this.textures.set(`r${ri}_${name}`, PIXI.Texture.from(canvas));
      }
    }
  }

  /** Draw a solid circle with radial gradient (for pure buy or pure sell). */
  private _drawSolidCircle(
    ctx: CanvasRenderingContext2D,
    center: number,
    radius: number,
    dpr: number,
    colors: { center: string; mid: string; edge: string },
  ): void {
    const grad = ctx.createRadialGradient(
      center - center * 0.15, center - center * 0.15, center * 0.05,
      center, center, center
    );
    grad.addColorStop(0, colors.center);
    grad.addColorStop(0.5, colors.mid);
    grad.addColorStop(0.85, colors.edge);
    grad.addColorStop(1, colors.edge + 'aa');

    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.strokeStyle = colors.center + 'cc';
    ctx.lineWidth = Math.max(1, 1.5 * dpr);
    ctx.stroke();
  }

  /** Draw a pie-slice arc with a solid fill. */
  private _drawArc(
    ctx: CanvasRenderingContext2D,
    center: number,
    radius: number,
    startAngle: number,
    endAngle: number,
    colors: { center: string; mid: string; edge: string },
  ): void {
    ctx.beginPath();
    ctx.moveTo(center, center);
    ctx.arc(center, center, radius, startAngle, endAngle);
    ctx.closePath();

    // Radial gradient for depth within the arc
    const grad = ctx.createRadialGradient(
      center - center * 0.1, center - center * 0.1, center * 0.05,
      center, center, center
    );
    grad.addColorStop(0, colors.center);
    grad.addColorStop(0.5, colors.mid);
    grad.addColorStop(0.85, colors.edge);
    grad.addColorStop(1, colors.edge + 'aa');

    ctx.fillStyle = grad;
    ctx.fill();
  }

  // Quantize buyRatio (0.0-1.0) to texture index (0-10)
  private _getRatioIdx(buyRatio: number): number {
    return Math.round(Math.min(1, Math.max(0, buyRatio)) * (RATIO_STEPS - 1));
  }

  private _getTierIdx(cssRadius: number): number {
    if (cssRadius <= 7) return 0;
    if (cssRadius <= 13) return 1;
    if (cssRadius <= 20) return 2;
    if (cssRadius <= 30) return 3;
    return 4;
  }

  private _getSprite(): PIXI.Sprite {
    if (this.poolIndex < this.spritePool.length) {
      const s = this.spritePool[this.poolIndex++];
      s.visible = true;
      return s;
    }
    if (this.spritePool.length >= MAX_SPRITES) {
      const s = this.spritePool[this.poolIndex % MAX_SPRITES];
      this.poolIndex++;
      s.visible = true;
      return s;
    }
    const s = new PIXI.Sprite();
    s.anchor.set(0.5);
    this.bubbleContainer!.addChild(s);
    this.spritePool.push(s);
    this.poolIndex++;
    return s;
  }

  resize(width: number, height: number): void {
    if (!this.app) return;
    this.app.renderer.resize(width, height);
  }

  renderBubbles(points: BubblePoint[], dpr: number, pulseThresholdMs: number): void {
    if (!this.initialized || !this.bubbleContainer) return;
    this.poolIndex = 0;

    const now = Date.now();
    const invDpr = 1 / dpr;
    const invPulse = 1 / pulseThresholdMs;

    for (const p of points) {
      const age = now - p.tMs;
      const ratioIdx = this._getRatioIdx(p.buyRatio);

      // Glow ring for recent trades (spray effect)
      if (age < pulseThresholdMs) {
        const sprite = this._getSprite();
        const freshness = 1 - age * invPulse;
        const sprayScale = 1.0 + 0.8 * freshness;
        const cssR = p.r * sprayScale * invDpr;
        const tierIdx = this._getTierIdx(cssR);
        sprite.texture = this.texGrid[ratioIdx][tierIdx];
        sprite.position.set(p.x * invDpr, p.y * invDpr);
        sprite.scale.set(cssR / (this.tierRadii[tierIdx] * invDpr));
        sprite.tint = 0xFFFFFF;
        sprite.alpha = 0.25 * freshness;
      }

      // Main bubble
      const sprite = this._getSprite();
      const cssR = p.r * invDpr;
      const tierIdx = this._getTierIdx(cssR);
      sprite.texture = this.texGrid[ratioIdx][tierIdx];
      sprite.position.set(p.x * invDpr, p.y * invDpr);
      sprite.scale.set(cssR / (this.tierRadii[tierIdx] * invDpr));
      sprite.tint = 0xFFFFFF;
      sprite.alpha = p.opacity > 0.95 ? 0.95 : p.opacity < 0.15 ? 0.15 : p.opacity;
    }

    // Hide unused
    for (let i = this.poolIndex; i < this.spritePool.length; i++) {
      this.spritePool[i].visible = false;
    }
  }

  renderLabels(_labels: { x: number; y: number; text: string; color?: number }[], _dpr: number): void {
    // Reserved for future GPU text
  }

  destroy(): void {
    try {
      if (this.bubbleContainer) { this.bubbleContainer.destroy({ children: true }); this.bubbleContainer = null; }
      if (this.labelContainer) { this.labelContainer.destroy({ children: true }); this.labelContainer = null; }
      for (const tex of this.textures.values()) { try { tex.destroy(true); } catch {} }
      this.textures.clear();
      this.textureRadii.clear();
      this.spritePool = [];
      this.poolIndex = 0;
      if (this.app) { this.app.destroy(true, { children: true }); this.app = null; }
      this.initialized = false;
      this.initPromise = null;
    } catch (e) {
      console.warn('[FlowBubbleRenderer] Destroy error:', e);
    }
  }

  get isReady(): boolean {
    return this.initialized;
  }
}
