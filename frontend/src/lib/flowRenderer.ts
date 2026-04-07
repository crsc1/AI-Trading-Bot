/**
 * GPU-accelerated bubble renderer using PixiJS v8.
 * Ported from dashboard/static/js/flow.js:234 (FlowRenderer class).
 *
 * Renders volume bubbles as sprites with pre-baked gradient textures.
 * Sprite pooling avoids GC pressure. Pulse rings highlight recent trades.
 */
import * as PIXI from 'pixi.js';

export interface BubblePoint {
  x: number;      // Physical pixel X
  y: number;      // Physical pixel Y
  r: number;      // Physical pixel radius
  tMs: number;    // Timestamp in ms
  opacity: number; // 0-1
  deltaRatio: number; // -1 to +1
}

const TIER_NAMES = ['tiny', 'small', 'medium', 'large', 'huge'] as const;
type TierName = (typeof TIER_NAMES)[number];

const TIER_SIZES: Record<TierName, number> = {
  tiny: 10,
  small: 16,
  medium: 24,
  large: 36,
  huge: 52,
};

export class FlowBubbleRenderer {
  private app: PIXI.Application | null = null;
  private bubbleContainer: PIXI.Container | null = null;
  private textures: Map<TierName, PIXI.Texture> = new Map();
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

      // Overlay PixiJS canvas on top of Canvas 2D
      this.app.canvas.style.cssText =
        'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2;';
      const pos = getComputedStyle(container).position;
      if (pos === 'static') container.style.position = 'relative';
      container.appendChild(this.app.canvas);

      this.bubbleContainer = new PIXI.Container();
      this.app.stage.addChild(this.bubbleContainer);

      this._createTextures(dpr);
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

      const canvas = document.createElement('canvas');
      canvas.width = r * 2;
      canvas.height = r * 2;
      const ctx = canvas.getContext('2d')!;

      // 3D sphere gradient: bright highlight offset top-left
      const grad = ctx.createRadialGradient(
        r - r * 0.25, r - r * 0.25, r * 0.08,
        r, r, r
      );
      grad.addColorStop(0, 'rgba(255,255,255,0.95)');
      grad.addColorStop(0.45, 'rgba(235,235,235,1.0)');
      grad.addColorStop(1, 'rgba(120,120,120,0.55)');

      ctx.beginPath();
      ctx.arc(r, r, r * 0.96, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.fill();

      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = Math.max(0.5, 0.5 * dpr);
      ctx.stroke();

      const tex = PIXI.Texture.from(canvas);
      this.textures.set(name, tex);
      this.textureRadii.set(name, r);
    }
  }

  private _getTier(cssRadius: number): TierName {
    if (cssRadius <= 7) return 'tiny';
    if (cssRadius <= 13) return 'small';
    if (cssRadius <= 20) return 'medium';
    if (cssRadius <= 30) return 'large';
    return 'huge';
  }

  private _getSprite(): PIXI.Sprite {
    if (this.poolIndex < this.spritePool.length) {
      const s = this.spritePool[this.poolIndex++];
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

    const latestMs = points.length > 0 ? Math.max(...points.map((p) => p.tMs)) : 0;

    // Pass 1: Pulse rings (behind main bubbles)
    for (const p of points) {
      if (latestMs - p.tMs < pulseThresholdMs) {
        const sprite = this._getSprite();
        const cssR = (p.r * 1.4) / dpr;
        const tier = this._getTier(cssR);
        sprite.texture = this.textures.get(tier)!;
        sprite.position.set(p.x / dpr, p.y / dpr);
        const texR = this.textureRadii.get(tier)! / dpr;
        sprite.scale.set(cssR / texR);
        sprite.tint = p.deltaRatio >= 0 ? 0x00e676 : 0xff1744;
        sprite.alpha = 0.12;
      }
    }

    // Pass 2: Main bubbles
    for (const p of points) {
      const sprite = this._getSprite();
      const cssR = p.r / dpr;
      const tier = this._getTier(cssR);
      sprite.texture = this.textures.get(tier)!;
      sprite.position.set(p.x / dpr, p.y / dpr);
      const texR = this.textureRadii.get(tier)! / dpr;
      sprite.scale.set(cssR / texR);
      sprite.tint = deltaToHex(p.deltaRatio);
      sprite.alpha = p.opacity;
    }

    // Hide unused pooled sprites
    for (let i = this.poolIndex; i < this.spritePool.length; i++) {
      this.spritePool[i].visible = false;
    }
  }

  destroy(): void {
    try {
      if (this.bubbleContainer) {
        this.bubbleContainer.destroy({ children: true });
        this.bubbleContainer = null;
      }
      for (const tex of this.textures.values()) {
        try { tex.destroy(true); } catch (_) { /* noop */ }
      }
      this.textures.clear();
      this.textureRadii.clear();
      this.spritePool = [];
      this.poolIndex = 0;
      if (this.app) {
        this.app.destroy(true, { children: true });
        this.app = null;
      }
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

/** Map delta ratio (-1 to +1) to hex color for PixiJS tint */
function deltaToHex(deltaRatio: number): number {
  const t = (deltaRatio + 1) / 2;
  let r: number, g: number, b: number;
  if (t < 0.45) {
    const f = t / 0.45;
    r = Math.round(230 - 50 * f);
    g = Math.round(40 + 100 * f);
    b = Math.round(60 + 80 * f);
  } else if (t > 0.55) {
    const f = (t - 0.55) / 0.45;
    r = Math.round(140 - 140 * f);
    g = Math.round(140 + 90 * f);
    b = Math.round(140 - 22 * f);
  } else {
    r = 180; g = 180; b = 180;
  }
  return (r << 16) | (g << 8) | b;
}
