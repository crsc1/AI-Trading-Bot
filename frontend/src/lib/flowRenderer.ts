/**
 * GPU-accelerated bubble renderer using PixiJS v8.
 *
 * Visual design (researched from Bookmap, ATAS, FlowAlgo):
 * - Vibrant green/red: high-contrast on dark backgrounds
 * - Spray animation: new bubbles start 1.5x size, shrink over 300ms
 * - 3 tiers: normal (small), block (medium + thick border), whale (large + glow)
 * - Age fade: older bubbles fade to 30% over the window duration
 * - Pulse ring on recent trades for "alive" feel
 */
import * as PIXI from 'pixi.js';

export interface BubblePoint {
  x: number;
  y: number;
  r: number;
  tMs: number;
  opacity: number;
  deltaRatio: number; // -1 (all sell) to +1 (all buy)
}

const TIER_NAMES = ['tiny', 'small', 'medium', 'large', 'huge'] as const;
type TierName = (typeof TIER_NAMES)[number];

const TIER_SIZES: Record<TierName, number> = {
  tiny: 10, small: 16, medium: 24, large: 36, huge: 52,
};

const MAX_SPRITES = 5000;

// Vibrant, high-contrast colors for dark backgrounds
type ColorKey = 'buy' | 'sell' | 'neutral';

export class FlowBubbleRenderer {
  private app: PIXI.Application | null = null;
  private bubbleContainer: PIXI.Container | null = null;
  private labelContainer: PIXI.Container | null = null;
  private textures: Map<string, PIXI.Texture> = new Map();
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
      this.app.stage.addChild(this.bubbleContainer);

      this.labelContainer = new PIXI.Container();
      this.app.stage.addChild(this.labelContainer);

      this._createTextures(dpr);
      this.initialized = true;
    } catch (err) {
      console.error('[FlowBubbleRenderer] Init failed:', err);
      this.initialized = false;
    }
  }

  private _createTextures(dpr: number): void {
    // Vibrant colors: bright enough to pop on #0a0a12 background
    const colors: Record<ColorKey, { center: string; mid: string; edge: string }> = {
      buy:     { center: '#4ade80', mid: '#22c55e', edge: '#16a34a' },  // Vibrant green
      sell:    { center: '#f87171', mid: '#ef4444', edge: '#dc2626' },  // Vibrant red
      neutral: { center: '#94a3b8', mid: '#64748b', edge: '#475569' },  // Slate gray
    };

    for (const name of TIER_NAMES) {
      const baseSize = TIER_SIZES[name];
      const r = Math.ceil(baseSize * dpr);
      this.textureRadii.set(name, r);

      for (const [colorKey, color] of Object.entries(colors) as [ColorKey, { center: string; mid: string; edge: string }][]) {
        const canvas = document.createElement('canvas');
        canvas.width = r * 2;
        canvas.height = r * 2;
        const ctx = canvas.getContext('2d')!;

        // Solid vibrant fill with subtle radial gradient for depth
        const grad = ctx.createRadialGradient(
          r - r * 0.15, r - r * 0.15, r * 0.05,
          r, r, r
        );
        grad.addColorStop(0, color.center);
        grad.addColorStop(0.5, color.mid);
        grad.addColorStop(0.85, color.edge);
        grad.addColorStop(1, color.edge + 'aa'); // slight fade at edge

        ctx.beginPath();
        ctx.arc(r, r, r * 0.92, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        // Crisp border for definition
        ctx.strokeStyle = color.center + 'cc';
        ctx.lineWidth = Math.max(1, 1.5 * dpr);
        ctx.stroke();

        this.textures.set(`${colorKey}_${name}`, PIXI.Texture.from(canvas));
      }
    }
  }

  private _getTier(cssRadius: number): TierName {
    if (cssRadius <= 7) return 'tiny';
    if (cssRadius <= 13) return 'small';
    if (cssRadius <= 20) return 'medium';
    if (cssRadius <= 30) return 'large';
    return 'huge';
  }

  private _getColorKey(deltaRatio: number): ColorKey {
    if (deltaRatio > 0.1) return 'buy';
    if (deltaRatio < -0.1) return 'sell';
    return 'neutral';
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

    // Pass 1: Glow rings for very recent trades (spray effect)
    // Recent = within pulseThreshold. These start large and shrink.
    for (const p of points) {
      const age = now - p.tMs;
      if (age < pulseThresholdMs) {
        const sprite = this._getSprite();
        // Spray animation: starts at 1.8x, shrinks to 1.0x over pulseThreshold
        const sprayScale = 1.0 + 0.8 * (1 - age / pulseThresholdMs);
        const cssR = (p.r * sprayScale) / dpr;
        const tier = this._getTier(cssR);
        const colorKey = this._getColorKey(p.deltaRatio);
        sprite.texture = this.textures.get(`${colorKey}_${tier}`)!;
        sprite.position.set(p.x / dpr, p.y / dpr);
        const texR = this.textureRadii.get(tier)! / dpr;
        sprite.scale.set(cssR / texR);
        sprite.tint = 0xFFFFFF;
        // Fade out the glow as it shrinks
        sprite.alpha = 0.25 * (1 - age / pulseThresholdMs);
      }
    }

    // Pass 2: Main bubbles
    for (const p of points) {
      const sprite = this._getSprite();
      const cssR = p.r / dpr;
      const tier = this._getTier(cssR);
      const colorKey = this._getColorKey(p.deltaRatio);
      sprite.texture = this.textures.get(`${colorKey}_${tier}`)!;
      sprite.position.set(p.x / dpr, p.y / dpr);
      const texR = this.textureRadii.get(tier)! / dpr;
      sprite.scale.set(cssR / texR);
      sprite.tint = 0xFFFFFF;

      // Freshness opacity: recent trades are bright, old ones fade.
      // Use the actual bubble opacity (computed from window position in flowCanvas).
      sprite.alpha = Math.max(0.15, Math.min(0.95, p.opacity));
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
