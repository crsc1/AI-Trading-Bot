// ══════════════════════════════════════════════════════════════════════════
// ORDER FLOW — fetch and render volume clouds
// ══════════════════════════════════════════════════════════════════════════
async function loadOrderFlow(){
  // Show loading
  ['flowLoading','flowLoadingFull'].forEach(id => {
    const el = document.getElementById(id);
    if(el){ el.style.display = 'flex'; el.innerHTML = '<div class="loading-dots"><span></span><span></span><span></span></div> Loading order flow...'; }
  });

  try{
    const r = await fetch(`/api/orderflow/clouds?symbol=${S.sym}&bar_minutes=${S.barMinutes}`);
    const d = await r.json();

    if(d.error){
      ['flowLoading','flowLoadingFull'].forEach(id => {
        const el = document.getElementById(id);
        if(el){ el.style.display='flex'; el.innerHTML = `<span style="color:var(--red)">${esc(d.error)}</span>`; }
      });
      return;
    }

    // Show date + trade count in toolbar
    if(d.meta){
      const dateStr = d.meta.date || '';
      const count = d.meta.trade_count || 0;
      const feed = d.meta.feed || '';
      document.getElementById('sTradeCount').textContent = count.toLocaleString();
      if(dateStr && count > 0){
        document.getElementById('dotData').className = 'dot on';
        document.getElementById('lblData').textContent = `${feed.toUpperCase()} — ${dateStr}`;
      }
    }

    if(d.warning || (!d.clouds || !d.clouds.length)){
      const msg = d.warning || 'No order flow data. Market may be closed.';
      ['flowLoading','flowLoadingFull'].forEach(id => {
        const el = document.getElementById(id);
        if(el){ el.style.display='flex'; el.innerHTML = `<span style="color:var(--ylw)">${esc(msg)}</span>`; }
      });
      return;
    }

    S.flowData = d;
    // Store for merging with live ticks in renderLiveFlow()
    historicalClouds = d;

    // Update stats
    const meta = d.meta || {};
    document.getElementById('sTradeCount').textContent = (meta.trade_count || 0).toLocaleString();

    let totalBuy = 0, totalSell = 0;
    (d.bars_summary || []).forEach(b => { totalBuy += b.buy_vol; totalSell += b.sell_vol; });
    document.getElementById('sBuyVol').textContent = formatVol(totalBuy);
    document.getElementById('sSellVol').textContent = formatVol(totalSell);
    const delta = totalBuy - totalSell;
    const deltaEl = document.getElementById('sDelta');
    deltaEl.textContent = (delta >= 0 ? '+' : '') + formatVol(delta);
    deltaEl.style.color = delta >= 0 ? 'var(--grn)' : 'var(--red)';

    // Update sidebar metrics
    document.getElementById('mDelta').textContent = (delta >= 0 ? '+' : '') + formatVol(delta);
    document.getElementById('mDelta').style.color = delta >= 0 ? 'var(--grn)' : 'var(--red)';
    document.getElementById('mCvd').textContent = formatVol(delta);

    // Render in active tab
    if(S.activeTab === 'combined'){
      renderFlowChart('flowWrapCombined', d, false);
    } else if(S.activeTab === 'flow'){
      renderFlowChart('flowWrapFull', d, true);
    }

    // Hide loading
    ['flowLoading','flowLoadingFull'].forEach(id => {
      const el = document.getElementById(id);
      if(el) el.style.display = 'none';
    });

  } catch(e){
    console.error('Order flow load failed:', e);
    ['flowLoading','flowLoadingFull'].forEach(id => {
      const el = document.getElementById(id);
      if(el){ el.style.display='flex'; el.innerHTML = `<span style="color:var(--red)">Failed: ${esc(e.message)}</span>`; }
    });
  }
}

// Track data revision for efficient Plotly.react diffing
let flowDataRevision = 0;

// ══════════════════════════════════════════════════════════════════════════
// CANVAS-BASED ORDER FLOW RENDERER — Prismadic-style streaming bubbles
// ══════════════════════════════════════════════════════════════════════════
// Uses HTML5 Canvas + requestAnimationFrame for smooth 60fps rendering.
// Each bubble = one data point at (time, price), sized by volume, colored by delta.
// The trail flows left-to-right as time advances, like Prismadic.

var _flowCanvases = {}; // containerId → {canvas, ctx, dpr}

// ── Shared Layout Config ──────────────────────────────────────────────
// ALL canvas renderers (bubbles, per-price, footprint) MUST use these
// constants × dpr for pixel coordinates. This prevents DPR scaling bugs
// where raw pixel values look correct on 1× displays but overlap on 2×.
//
// Usage: const val = FLOW_LAYOUT.headerH * dpr;
//        const fontSize = FLOW_LAYOUT.fontSize.title * dpr;
const FLOW_LAYOUT = {
  // Shared header area (title + subtitle + separator)
  headerH: 44,            // CSS px reserved for chart title area
  titleY: 16,             // CSS px from top — title baseline
  subtitleY: 30,          // CSS px from top — subtitle baseline

  // Margins (bubbles view uses these; others may override)
  marginL: 50,            // Left margin for price labels
  marginT: 8,             // Top margin (bubbles; per-price/footprint use headerH)
  ladderW: 110,           // Right-side price ladder width

  // Font sizes (CSS px — multiply by dpr when setting ctx.font)
  fontSize: {
    title: 11,            // Chart titles ("FOOTPRINT CHART", "PER-PRICE VOLUME PROFILE")
    subtitle: 9,          // Subtitles / descriptions
    label: 8,             // Price labels, axis labels
    tick: 7,              // Time labels, small annotations
    empty: 12,            // "Waiting for data..." messages
  },

  // Colors
  bg: T.surface0,          // Canvas background
  titleColor: T.accent,   // Chart title
  subtitleColor: T.dim,    // Subtitle / empty message
  labelColor: T.dim,       // Price/time labels
  gridColor: T.borderSubtle, // Grid lines
  separatorColor: 'rgba(255,255,255,0.06)', // Section separators

  // Overlay thresholds (shared across renderers)
  largePrintThreshold: 5000,

  // Font family
  fontFamily: 'SF Mono, Menlo, monospace',
};

function _ensureCanvas(containerId){
  let entry = _flowCanvases[containerId];
  const container = document.getElementById(containerId);
  if(!container) return null;

  if(!entry || !entry.canvas.parentElement){
    // Remove any existing Plotly chart (if Plotly was loaded)
    if(typeof Plotly !== 'undefined' && container.querySelector('.js-plotly-plot')){
      Plotly.purge(containerId);
    }
    // Remove old canvas if stale
    const old = container.querySelector('canvas.flow-canvas');
    if(old) old.remove();

    const canvas = document.createElement('canvas');
    canvas.className = 'flow-canvas';
    canvas.style.cssText = 'width:100%;height:100%;display:block;';
    container.appendChild(canvas);

    const dpr = window.devicePixelRatio || 1;
    entry = {canvas, ctx: canvas.getContext('2d'), dpr};
    _flowCanvases[containerId] = entry;
  }

  // Resize to container — skip if container is hidden (zero dimensions)
  const rect = container.getBoundingClientRect();
  if(rect.width < 2 || rect.height < 2) return null; // Container not visible yet

  // FIX: Update DPR on every call (handles display changes, e.g. moving between monitors)
  entry.dpr = window.devicePixelRatio || 1;

  const w = Math.round(rect.width * entry.dpr);
  const h = Math.round(rect.height * entry.dpr);
  if(entry.canvas.width !== w || entry.canvas.height !== h){
    entry.canvas.width = w;
    entry.canvas.height = h;
    // NOTE: Drawing code uses physical pixel coordinates (manual * dpr scaling).
    // No setTransform needed — the ctx identity matrix is correct for this approach.
  }
  return entry;
}

function deltaToColor(deltaRatio, opacity){
  // Map delta_ratio (-1 to +1) to red → gray → green
  const t = (deltaRatio + 1) / 2; // 0=full sell, 1=full buy
  let r, g, b;
  if(t < 0.45){
    // Red zone (sell)
    const f = t / 0.45;
    r = Math.round(230 - 50 * f);
    g = Math.round(40 + 100 * f);
    b = Math.round(60 + 80 * f);
  } else if(t > 0.55){
    // Green zone (buy)
    const f = (t - 0.55) / 0.45;
    r = Math.round(140 - 140 * f);
    g = Math.round(140 + 90 * f);
    b = Math.round(140 - 22 * f);
  } else {
    // Neutral gray zone
    r = 180; g = 180; b = 180;
  }
  return {r, g, b, a: opacity};
}

// Convert delta ratio to hex color for PixiJS tint (same logic as deltaToColor but returns 0xRRGGBB)
function deltaToHex(deltaRatio){
  const t = (deltaRatio + 1) / 2;
  let r, g, b;
  if(t < 0.45){
    const f = t / 0.45;
    r = Math.round(230 - 50 * f);
    g = Math.round(40 + 100 * f);
    b = Math.round(60 + 80 * f);
  } else if(t > 0.55){
    const f = (t - 0.55) / 0.45;
    r = Math.round(140 - 140 * f);
    g = Math.round(140 + 90 * f);
    b = Math.round(140 - 22 * f);
  } else {
    r = 180; g = 180; b = 180;
  }
  return (r << 16) | (g << 8) | b;
}

// ══════════════════════════════════════════════════════════════════════════
// PixiJS v8 GPU-ACCELERATED BUBBLE RENDERER
// Canvas 2D: grids, labels, backgrounds, volume bars, ladder, indicators, trail
// PixiJS:    bubbles + pulse rings (the performance-critical part)
// ══════════════════════════════════════════════════════════════════════════
window.USE_PIXIJS = (typeof PIXI !== 'undefined');

class FlowRenderer {
  constructor(){
    this.app = null;
    this.initialized = false;
    this.initPromise = null;
    this.bubbleContainer = null;
    this.textures = {};
    this.spritePool = [];
    this.poolIndex = 0;
  }

  async init(containerId){
    if(this.initPromise) return this.initPromise;
    this.initPromise = this._doInit(containerId);
    return this.initPromise;
  }

  async _doInit(containerId){
    try {
      const container = document.getElementById(containerId);
      if(!container) return;

      this.app = new PIXI.Application();
      const dpr = window.devicePixelRatio || 1;

      await this.app.init({
        backgroundAlpha: 0,
        antialias: true,
        resolution: dpr,
        autoDensity: true,
      });

      // Overlay PixiJS canvas on top of Canvas 2D
      this.app.canvas.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:2;';
      const pos = getComputedStyle(container).position;
      if(pos === 'static') container.style.position = 'relative';
      container.appendChild(this.app.canvas);

      // Create bubble layer
      this.bubbleContainer = new PIXI.Container();
      this.app.stage.addChild(this.bubbleContainer);

      // Pre-bake gradient textures for 5 size tiers
      this._createTextures(dpr);
      this.initialized = true;
      console.log('[FlowRenderer] PixiJS v8 GPU bubble renderer ready (' + PIXI.VERSION + ')');
    } catch(err){
      console.error('[FlowRenderer] Init failed, falling back to Canvas 2D:', err);
      window.USE_PIXIJS = false;
    }
  }

  destroy(){
    try {
      if(this.bubbleContainer){ this.bubbleContainer.destroy({children:true}); this.bubbleContainer = null; }
      Object.values(this.textures).forEach(t => { try{t.destroy(true)}catch(e){} });
      this.textures = {};
      this.spritePool = [];
      this.poolIndex = 0;
      if(this.app){ this.app.destroy(true, {children:true, texture:true}); this.app = null; }
      this.initialized = false;
      this.initPromise = null;
    } catch(e){ console.warn('[FlowRenderer] Destroy error:', e); }
  }

  _createTextures(dpr){
    // 5 pre-baked gradient circle textures (white/gray — tinted per-sprite for color)
    // Using Canvas 2D to create the gradient, then wrapping as PIXI.Texture
    const sizes = {tiny: 10, small: 16, medium: 24, large: 36, huge: 52};

    for(const [name, baseSize] of Object.entries(sizes)){
      const r = Math.ceil(baseSize * dpr);
      const canvas = document.createElement('canvas');
      canvas.width = r * 2;
      canvas.height = r * 2;
      const ctx = canvas.getContext('2d');

      // 3D sphere gradient: bright highlight offset top-left, dark at edge
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

      // Subtle edge glow
      ctx.strokeStyle = 'rgba(255,255,255,0.06)';
      ctx.lineWidth = Math.max(0.5, 0.5 * dpr);
      ctx.stroke();

      const tex = PIXI.Texture.from(canvas);
      tex._bubbleRadius = r; // Store for scale calculation
      this.textures[name] = tex;
    }
  }

  _getTier(cssRadius){
    if(cssRadius <= 7) return 'tiny';
    if(cssRadius <= 13) return 'small';
    if(cssRadius <= 20) return 'medium';
    if(cssRadius <= 30) return 'large';
    return 'huge';
  }

  _getSprite(){
    if(this.poolIndex < this.spritePool.length){
      const s = this.spritePool[this.poolIndex++];
      s.visible = true;
      return s;
    }
    const s = new PIXI.Sprite();
    s.anchor.set(0.5);
    this.bubbleContainer.addChild(s);
    this.spritePool.push(s);
    this.poolIndex++;
    return s;
  }

  resize(width, height){
    if(!this.app) return;
    this.app.renderer.resize(width, height);
  }

  renderBubbles(points, dpr, pulseThreshold, latestMs){
    if(!this.initialized) return;
    this.poolIndex = 0;

    // Pass 1: Pulse rings (rendered behind main bubbles)
    for(const p of points){
      if(latestMs - p.tMs < pulseThreshold){
        const sprite = this._getSprite();
        const cssR = (p.r * 1.4) / dpr;
        const tier = this._getTier(cssR);
        sprite.texture = this.textures[tier];
        sprite.position.set(p.x / dpr, p.y / dpr);
        const texR = this.textures[tier]._bubbleRadius / dpr;
        sprite.scale.set(cssR / texR);
        sprite.tint = p.c.delta_ratio >= 0 ? 0x00e676 : 0xff1744;
        sprite.alpha = 0.12;
      }
    }

    // Pass 2: Main bubbles
    for(const p of points){
      const sprite = this._getSprite();
      const cssR = p.r / dpr;
      const tier = this._getTier(cssR);
      sprite.texture = this.textures[tier];
      sprite.position.set(p.x / dpr, p.y / dpr);
      const texR = this.textures[tier]._bubbleRadius / dpr;
      sprite.scale.set(cssR / texR);
      sprite.tint = deltaToHex(p.c.delta_ratio);
      sprite.alpha = p.opacity;
    }

    // Hide unused pooled sprites
    for(let i = this.poolIndex; i < this.spritePool.length; i++){
      this.spritePool[i].visible = false;
    }
  }

  destroy(){
    if(this.app){
      this.app.destroy(true, {children: true});
      this.app = null;
    }
    this.initialized = false;
    this.initPromise = null;
    this.spritePool = [];
    this.poolIndex = 0;
    this.textures = {};
  }
}

var flowRenderers = {}; // containerId → FlowRenderer instance

// Destroy all PixiJS renderers to free GPU memory (call on symbol switch)
function _destroyAllFlowRenderers(){
  Object.keys(flowRenderers).forEach(id => {
    try{ flowRenderers[id].destroy(); }catch(e){}
  });
  flowRenderers = {};
}

// ══════════════════════════════════════════════════════════════════════════
// ORDER FLOW LEGEND + BUBBLE TOOLTIPS
// ══════════════════════════════════════════════════════════════════════════

// Stores last rendered bubble points per container for hit-testing
var _flowBubblePoints = {}; // containerId → [{x, y, r, c, tMs, opacity}, ...]

function _buildLegendHTML(){
  return `
    <div class="flow-legend-title">How to Read Bubbles <button class="flow-legend-close" onclick="this.closest('.flow-legend').classList.add('u-hidden');var b=this.closest('.flow-legend').parentElement.querySelector('.flow-legend-toggle');if(b)b.classList.remove('u-hidden')">&times;</button></div>
    <div class="flow-legend-row">
      <div class="flow-legend-swatch" style="background:var(--positive)"></div>
      <div><div class="flow-legend-label">Green = Net Buying</div><div class="flow-legend-sub">More buy volume than sell</div></div>
    </div>
    <div class="flow-legend-row">
      <div class="flow-legend-swatch" style="background:var(--negative)"></div>
      <div><div class="flow-legend-label">Red = Net Selling</div><div class="flow-legend-sub">More sell volume than buy</div></div>
    </div>
    <div class="flow-legend-row">
      <div class="flow-legend-swatch" style="background:#b4b4b4"></div>
      <div><div class="flow-legend-label">Gray = Neutral</div><div class="flow-legend-sub">Buy ≈ Sell (balanced flow)</div></div>
    </div>
    <div class="flow-legend-divider"></div>
    <div class="flow-legend-row">
      <div class="flow-legend-swatch sz-sm" style="background:#8888aa"></div>
      <div class="flow-legend-swatch sz-md" style="background:#8888aa"></div>
      <div class="flow-legend-swatch sz-lg" style="background:#8888aa"></div>
      <div><div class="flow-legend-label">Size = Volume</div><div class="flow-legend-sub">Bigger bubble = more contracts</div></div>
    </div>
    <div class="flow-legend-divider"></div>
    <div class="flow-legend-row">
      <div class="flow-legend-swatch pulse-ring"></div>
      <div><div class="flow-legend-label">Gold Ring = Large Print</div><div class="flow-legend-sub">Institutional-size order (≥5K vol)</div></div>
    </div>
    <div class="flow-legend-row">
      <div class="flow-legend-swatch" style="background:none;border:2px solid rgba(0,230,118,0.5)"></div>
      <div><div class="flow-legend-label">Pulse = Recent Trade</div><div class="flow-legend-sub">Fading glow on newest data</div></div>
    </div>
    <div class="flow-legend-divider"></div>
    <div style="color:var(--dim);font-size:7.5px;line-height:1.4">
      <b style="color:var(--txt)">Y-axis</b> = Price level<br>
      <b style="color:var(--txt)">X-axis</b> = Time<br>
      <b style="color:var(--txt)">Opacity</b> = Age (brighter = newer)<br>
      <b style="color:var(--txt)">Hover</b> a bubble for details
    </div>
  `;
}

function toggleFlowLegend(containerId){
  const legendId = containerId === 'flowWrapCombined' ? 'flowLegendCombined' : 'flowLegendFull';
  const el = document.getElementById(legendId);
  const btn = el ? el.parentElement.querySelector('.flow-legend-toggle') : null;
  if(!el) return;
  if(el.classList.contains('u-hidden')){
    el.innerHTML = _buildLegendHTML();
    el.classList.remove('u-hidden');
    if(btn) btn.classList.add('u-hidden');
  } else {
    el.classList.add('u-hidden');
    if(btn) btn.classList.remove('u-hidden');
  }
}

// Re-show ? button when legend is closed via the X inside the legend
document.addEventListener('click', function(e){
  if(e.target.closest('.flow-legend-close')){
    const legend = e.target.closest('.flow-legend');
    if(legend){
      legend.classList.add('u-hidden');
      const btn = legend.parentElement.querySelector('.flow-legend-toggle');
      if(btn) btn.classList.remove('u-hidden');
    }
  }
});

// ── Bubble Tooltip on Hover ──
// Hit-test mouse position against stored bubble points
function _initFlowTooltips(containerId){
  const container = document.getElementById(containerId);
  if(!container || container._flowTooltipInit) return;
  container._flowTooltipInit = true;

  const tooltipId = containerId === 'flowWrapCombined' ? 'flowTooltipCombined' : 'flowTooltipFull';
  const tooltip = document.getElementById(tooltipId);
  if(!tooltip) return;

  let _lastHitIdx = -1;

  container.addEventListener('mousemove', function(e){
    const points = _flowBubblePoints[containerId];
    if(!points || points.length === 0){ tooltip.style.display = 'none'; _lastHitIdx = -1; return; }

    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const mx = (e.clientX - rect.left) * dpr;
    const my = (e.clientY - rect.top) * dpr;

    // Find closest bubble within hit radius
    let bestIdx = -1, bestDist = Infinity;
    for(let i = points.length - 1; i >= 0; i--){
      const p = points[i];
      const dx = mx - p.x, dy = my - p.y;
      const dist = Math.sqrt(dx*dx + dy*dy);
      const hitR = Math.max(p.r, 8 * dpr); // Min hit area of 8px
      if(dist <= hitR && dist < bestDist){
        bestDist = dist;
        bestIdx = i;
      }
    }

    if(bestIdx === -1){
      tooltip.style.display = 'none';
      _lastHitIdx = -1;
      return;
    }

    // Only update DOM if different bubble
    if(bestIdx !== _lastHitIdx){
      _lastHitIdx = bestIdx;
      const p = points[bestIdx];
      const c = p.c;
      const buyVol = c.buy_vol || 0;
      const sellVol = c.sell_vol || 0;
      const totalVol = c.total_vol || (buyVol + sellVol);
      const delta = c.delta || (buyVol - sellVol);
      const deltaRatio = c.delta_ratio || 0;
      const deltaColor = delta >= 0 ? 'var(--grn)' : 'var(--red)';
      const deltaSign = delta >= 0 ? '+' : '';
      const time = c.time ? new Date(c.time).toLocaleTimeString('en-US', {hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:false}) : '';
      const price = c.price ? c.price.toFixed(2) : '';

      tooltip.innerHTML = `
        <div class="tt-price">$${price}</div>
        <div class="tt-row"><span class="tt-label">Buy Vol</span><span class="tt-val-buy">${formatVol(buyVol)}</span></div>
        <div class="tt-row"><span class="tt-label">Sell Vol</span><span class="tt-val-sell">${formatVol(sellVol)}</span></div>
        <div class="tt-row"><span class="tt-label">Total</span><span>${formatVol(totalVol)}</span></div>
        <div class="tt-row"><span class="tt-label">Delta</span><span class="tt-val-delta" style="color:${deltaColor}">${deltaSign}${formatVol(Math.abs(delta))}</span></div>
        <div class="tt-row"><span class="tt-label">Delta %</span><span class="tt-val-delta" style="color:${deltaColor}">${(deltaRatio * 100).toFixed(0)}%</span></div>
        ${totalVol >= FLOW_LAYOUT.largePrintThreshold ? '<div style="color:var(--warning);font-weight:700;margin-top:2px;font-size:var(--font-xs)">⚡ LARGE PRINT</div>' : ''}
        <div class="tt-time">${time}</div>
      `;
    }

    // Position tooltip near cursor, clamped to container
    const ttW = tooltip.offsetWidth || 140;
    const ttH = tooltip.offsetHeight || 100;
    let tx = (e.clientX - rect.left) + 14;
    let ty = (e.clientY - rect.top) - ttH / 2;
    if(tx + ttW > rect.width - 4) tx = (e.clientX - rect.left) - ttW - 14;
    if(ty < 4) ty = 4;
    if(ty + ttH > rect.height - 4) ty = rect.height - ttH - 4;
    tooltip.style.left = tx + 'px';
    tooltip.style.top = ty + 'px';
    tooltip.style.display = 'block';
  });

  container.addEventListener('mouseleave', function(){
    tooltip.style.display = 'none';
    _lastHitIdx = -1;
  });
}

// Initialize tooltips for both flow containers on first load
// Uses setTimeout(0) to ensure DOM is fully parsed even if script runs mid-parse
document.addEventListener('DOMContentLoaded', function(){
  setTimeout(function(){
    _initFlowTooltips('flowWrapCombined');
    _initFlowTooltips('flowWrapFull');
  }, 0);
});

// Canvas 2D fallback for bubble rendering (used while PixiJS initializes or if WebGL unavailable)
// Performance: uses cached offscreen bubble sprites instead of per-frame gradient creation
const _bubbleSpriteCache = new Map(); // key: "r,g,b,a,radius" → OffscreenCanvas
function _getBubbleSprite(col, radius){
  const rInt = Math.round(radius);
  if(rInt < 1) return null;
  const key = `${col.r},${col.g},${col.b},${(col.a * 100)|0},${rInt}`;
  let sprite = _bubbleSpriteCache.get(key);
  if(sprite) return sprite;
  // Evict oldest entries if cache grows too large (LRU-lite)
  if(_bubbleSpriteCache.size > 200){
    const firstKey = _bubbleSpriteCache.keys().next().value;
    _bubbleSpriteCache.delete(firstKey);
  }
  const sz = rInt * 2 + 2;
  sprite = new OffscreenCanvas(sz, sz);
  const sCtx = sprite.getContext('2d');
  const cx = rInt + 1, cy = rInt + 1;
  const grad = sCtx.createRadialGradient(cx - rInt*0.25, cy - rInt*0.25, rInt*0.08, cx, cy, rInt);
  const hlR = Math.min(255, col.r + 60), hlG = Math.min(255, col.g + 60), hlB = Math.min(255, col.b + 60);
  grad.addColorStop(0, `rgba(${hlR},${hlG},${hlB},${(col.a * 0.9).toFixed(2)})`);
  grad.addColorStop(0.5, `rgba(${col.r},${col.g},${col.b},${col.a.toFixed(2)})`);
  grad.addColorStop(1, `rgba(${Math.max(0,col.r-40)},${Math.max(0,col.g-40)},${Math.max(0,col.b-40)},${(col.a * 0.6).toFixed(2)})`);
  sCtx.beginPath();
  sCtx.arc(cx, cy, rInt, 0, Math.PI * 2);
  sCtx.fillStyle = grad;
  sCtx.fill();
  sCtx.strokeStyle = `rgba(255,255,255,${(col.a * 0.08).toFixed(2)})`;
  sCtx.lineWidth = 0.5;
  sCtx.stroke();
  _bubbleSpriteCache.set(key, sprite);
  return sprite;
}
// Pre-computed pulse colors to avoid string allocation in hot loop
const _PULSE_GREEN = 'rgba(0,230,118,0.12)';
const _PULSE_RED = 'rgba(255,23,68,0.12)';

function _drawBubblesCanvas2D(ctx, points, dpr, pulseThreshold, latestMs){
  const tau = Math.PI * 2;
  for(let i = 0, len = points.length; i < len; i++){
    const p = points[i];
    const {x, y, r, tMs, opacity, c} = p;

    // Pulse ring for newest data
    if(latestMs - tMs < pulseThreshold){
      ctx.beginPath();
      ctx.arc(x, y, r * 1.4, 0, tau);
      ctx.fillStyle = c.delta_ratio >= 0 ? _PULSE_GREEN : _PULSE_RED;
      ctx.fill();
    }

    // Draw cached bubble sprite (gradient computed once, reused across frames)
    const col = deltaToColor(c.delta_ratio, opacity);
    const sprite = _getBubbleSprite(col, r);
    if(sprite){
      ctx.drawImage(sprite, x - r - 1, y - r - 1);
    } else {
      // Tiny bubble fallback — solid color, no gradient overhead
      ctx.beginPath();
      ctx.arc(x, y, r, 0, tau);
      ctx.fillStyle = `rgba(${col.r},${col.g},${col.b},${col.a.toFixed(2)})`;
      ctx.fill();
    }
  }
}

// ── Per-Price placeholder (Phase 2) ──
function renderPerPriceProfile(containerId, data, fullScreen){
  const container = document.getElementById(containerId);
  if(!container) return;
  const entry = _ensureCanvas(containerId);
  if(!entry) return;
  const {canvas, ctx, dpr} = entry;
  const W = canvas.width, H = canvas.height;
  const L = FLOW_LAYOUT;

  ctx.fillStyle = L.bg;
  ctx.fillRect(0, 0, W, H);

  const cells = data.clouds || [];
  if(!cells.length){
    ctx.fillStyle = L.subtitleColor;
    ctx.font = `${L.fontSize.empty * dpr}px ${L.fontFamily}`;
    ctx.textAlign = 'center';
    ctx.fillText('Per-Price Volume Profile — Waiting for flow data...', W / 2, H / 2);
    return;
  }

  // ── Aggregate volume by price level ──
  const priceTick = liveFlow.priceTick || 0.05;
  const priceMap = new Map(); // price → {buy, sell, delta, total, trades}
  cells.forEach(c => {
    const p = (Math.round(c.price / priceTick) * priceTick);
    const key = p.toFixed(2);
    if(!priceMap.has(key)) priceMap.set(key, {price: p, buy: 0, sell: 0, delta: 0, total: 0, trades: 0});
    const lv = priceMap.get(key);
    lv.buy += c.buy_vol || 0;
    lv.sell += c.sell_vol || 0;
    lv.delta += c.delta || 0;
    lv.total += c.total_vol || 0;
    lv.trades++;
  });

  const levels = [...priceMap.values()].sort((a, b) => b.price - a.price);
  if(!levels.length) return;

  // ── Find POC (Point of Control) — highest volume level ──
  let pocIdx = 0, pocVol = 0;
  levels.forEach((lv, i) => { if(lv.total > pocVol){ pocVol = lv.total; pocIdx = i; } });

  // ── Value Area (70% of total volume around POC) ──
  const totalVol = levels.reduce((s, lv) => s + lv.total, 0);
  const vaTarget = totalVol * 0.70;
  let vaHigh = pocIdx, vaLow = pocIdx, vaVol = levels[pocIdx].total;
  while(vaVol < vaTarget && (vaHigh > 0 || vaLow < levels.length - 1)){
    const upVol = vaHigh > 0 ? levels[vaHigh - 1].total : 0;
    const dnVol = vaLow < levels.length - 1 ? levels[vaLow + 1].total : 0;
    if(upVol >= dnVol && vaHigh > 0){ vaHigh--; vaVol += levels[vaHigh].total; }
    else if(vaLow < levels.length - 1){ vaLow++; vaVol += levels[vaLow].total; }
    else break;
  }

  // ── Stacked imbalance detection (diagonal comparison) ──
  // Buy imbalance: buy[i] > sell[i+1] * 3 for 3+ consecutive levels
  const imbalanceFlags = new Array(levels.length).fill(0); // 1=buy stack, -1=sell stack
  for(let i = 0; i < levels.length - 1; i++){
    const buyImb = levels[i].buy > 0 && levels[i + 1].sell > 0 && levels[i].buy / levels[i + 1].sell >= 3;
    const sellImb = levels[i].sell > 0 && levels[i + 1].buy > 0 && levels[i].sell / levels[i + 1].buy >= 3;
    if(buyImb) imbalanceFlags[i] = (imbalanceFlags[i] || 0) + 1;
    if(sellImb) imbalanceFlags[i] = (imbalanceFlags[i] || 0) - 1;
  }
  // Mark runs of 3+ consecutive imbalances
  const stackedBuy = new Set(), stackedSell = new Set();
  let runStart = 0, runType = 0;
  for(let i = 0; i <= levels.length; i++){
    const f = i < levels.length ? (imbalanceFlags[i] > 0 ? 1 : imbalanceFlags[i] < 0 ? -1 : 0) : 0;
    if(f === runType && f !== 0) continue;
    if(i - runStart >= 3){
      const set = runType > 0 ? stackedBuy : stackedSell;
      for(let j = runStart; j < i; j++) set.add(j);
    }
    runStart = i; runType = f;
  }

  // ── Layout geometry ──
  const headerH = L.headerH * dpr;
  const deltaColW = 55 * dpr;    // Right-side delta column
  const priceLabelW = 52 * dpr;  // Center price labels
  const bottomPad = 12 * dpr;
  const availH = H - headerH - bottomPad;
  const rowH = Math.max(6 * dpr, Math.min(22 * dpr, availH / levels.length));
  const visibleCount = Math.min(levels.length, Math.floor(availH / rowH));
  const barAreaW = (W - priceLabelW - deltaColW) / 2; // Each side of center
  const centerX = barAreaW;  // Sell bars go left from here, buy bars go right
  const maxVol = Math.max(...levels.map(lv => Math.max(lv.buy, lv.sell)), 1);

  // ── Header ──
  ctx.fillStyle = L.titleColor;
  ctx.font = `bold ${L.fontSize.title * dpr}px ${L.fontFamily}`;
  ctx.textAlign = 'center';
  ctx.fillText('VOLUME PROFILE', W / 2, L.titleY * dpr);
  ctx.fillStyle = L.subtitleColor;
  ctx.font = `${L.fontSize.subtitle * dpr}px ${L.fontFamily}`;
  ctx.fillText(`${levels.length} levels  ·  ${formatVol(totalVol)} total  ·  POC ${levels[pocIdx].price.toFixed(2)}  ·  VA ${levels[vaHigh].price.toFixed(2)}–${levels[vaLow].price.toFixed(2)}`, W / 2, L.subtitleY * dpr);

  // Separator
  ctx.strokeStyle = L.separatorColor;
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, headerH - 4 * dpr); ctx.lineTo(W, headerH - 4 * dpr); ctx.stroke();

  // Center line
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.beginPath(); ctx.moveTo(centerX, headerH); ctx.lineTo(centerX, headerH + visibleCount * rowH); ctx.stroke();

  // Delta column separator
  const deltaX = W - deltaColW;
  ctx.beginPath(); ctx.moveTo(deltaX, headerH); ctx.lineTo(deltaX, headerH + visibleCount * rowH); ctx.stroke();

  // Column headers
  ctx.font = `${6 * dpr}px ${L.fontFamily}`;
  ctx.fillStyle = 'rgba(239,83,80,0.6)';
  ctx.textAlign = 'right';
  ctx.fillText('SELL', centerX - 4 * dpr, headerH - 6 * dpr);
  ctx.fillStyle = 'rgba(38,166,154,0.6)';
  ctx.textAlign = 'left';
  ctx.fillText('BUY', centerX + priceLabelW + 4 * dpr, headerH - 6 * dpr);
  ctx.fillStyle = L.subtitleColor;
  ctx.textAlign = 'center';
  ctx.fillText('DELTA', deltaX + deltaColW / 2, headerH - 6 * dpr);

  // ── Draw rows ──
  for(let i = 0; i < visibleCount; i++){
    const lv = levels[i];
    const y = headerH + i * rowH;
    const inVA = i >= vaHigh && i <= vaLow;
    const isPOC = i === pocIdx;
    const isBuyStack = stackedBuy.has(i);
    const isSellStack = stackedSell.has(i);

    // Value area background
    if(inVA){
      ctx.fillStyle = 'rgba(255,255,255,0.015)';
      ctx.fillRect(0, y, W - deltaColW, rowH);
    }

    // Grid line
    ctx.strokeStyle = L.gridColor;
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();

    // ── Sell bar (grows LEFT from center) ──
    const sellW = (lv.sell / maxVol) * (barAreaW - 4 * dpr);
    const sellAlpha = 0.35 + (lv.sell / maxVol) * 0.50;
    ctx.fillStyle = isSellStack
      ? `rgba(255,23,68,${Math.min(sellAlpha + 0.2, 0.95)})`
      : `rgba(239,83,80,${sellAlpha})`;
    ctx.fillRect(centerX - sellW, y + 1, sellW, rowH - 2);

    // Sell volume label
    if(rowH >= 8 * dpr && lv.sell > 0){
      ctx.fillStyle = 'rgba(239,83,80,0.8)';
      const fs = Math.min(L.fontSize.label, (rowH / dpr) - 3);
      ctx.font = `${fs * dpr}px ${L.fontFamily}`;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'middle';
      ctx.fillText(formatVol(lv.sell), centerX - sellW - 3 * dpr, y + rowH / 2);
    }

    // ── Buy bar (grows RIGHT from center + price label width) ──
    const buyStartX = centerX + priceLabelW;
    const buyW = (lv.buy / maxVol) * (barAreaW - priceLabelW - 4 * dpr);
    const buyAlpha = 0.35 + (lv.buy / maxVol) * 0.50;
    ctx.fillStyle = isBuyStack
      ? `rgba(0,230,118,${Math.min(buyAlpha + 0.2, 0.95)})`
      : `rgba(38,166,154,${buyAlpha})`;
    ctx.fillRect(buyStartX, y + 1, buyW, rowH - 2);

    // Buy volume label
    if(rowH >= 8 * dpr && lv.buy > 0){
      ctx.fillStyle = 'rgba(38,166,154,0.8)';
      const fs = Math.min(L.fontSize.label, (rowH / dpr) - 3);
      ctx.font = `${fs * dpr}px ${L.fontFamily}`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillText(formatVol(lv.buy), buyStartX + buyW + 3 * dpr, y + rowH / 2);
    }

    // ── Price label (center column) ──
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const priceFS = Math.min(L.fontSize.subtitle, (rowH / dpr) - 2);
    ctx.font = isPOC ? `bold ${priceFS * dpr}px ${L.fontFamily}` : `${priceFS * dpr}px ${L.fontFamily}`;
    ctx.fillStyle = isPOC ? T.txt : L.labelColor;
    ctx.fillText(lv.price.toFixed(2), centerX + priceLabelW / 2, y + rowH / 2);

    // POC marker
    if(isPOC){
      ctx.fillStyle = T.warning;
      const dotR = 2.5 * dpr;
      ctx.beginPath();
      ctx.arc(centerX + priceLabelW / 2 - (priceFS * dpr * 2), y + rowH / 2, dotR, 0, Math.PI * 2);
      ctx.fill();
    }

    // Stacked imbalance markers
    if(isBuyStack){
      ctx.fillStyle = 'rgba(0,230,118,0.7)';
      ctx.fillRect(0, y, 3 * dpr, rowH);
    }
    if(isSellStack){
      ctx.fillStyle = 'rgba(255,23,68,0.7)';
      ctx.fillRect(0, y, 3 * dpr, rowH);
    }

    // ── Delta column ──
    const deltaVal = lv.delta;
    const deltaColor = deltaVal >= 0 ? 'rgba(38,166,154,0.8)' : 'rgba(239,83,80,0.8)';
    ctx.fillStyle = deltaColor;
    const deltaFS = Math.min(L.fontSize.label, (rowH / dpr) - 3);
    ctx.font = `${deltaFS * dpr}px ${L.fontFamily}`;
    ctx.textAlign = 'center';
    const deltaStr = formatDelta(deltaVal);
    ctx.fillText(deltaStr, deltaX + deltaColW / 2, y + rowH / 2);

    // Delta bar (background fill proportional to magnitude)
    const maxDelta = Math.max(...levels.map(lv => Math.abs(lv.delta)), 1);
    const deltaPct = Math.abs(deltaVal) / maxDelta;
    const deltaBarW = deltaPct * (deltaColW - 10 * dpr);
    ctx.fillStyle = deltaVal >= 0 ? 'rgba(38,166,154,0.06)' : 'rgba(239,83,80,0.06)';
    ctx.fillRect(deltaX + (deltaColW - deltaBarW) / 2, y + 1, deltaBarW, rowH - 2);

    ctx.textBaseline = 'alphabetic';
  }

  // ── Bottom summary bar ──
  const sumY = headerH + visibleCount * rowH + 4 * dpr;
  const totalBuy = levels.reduce((s, lv) => s + lv.buy, 0);
  const totalSell = levels.reduce((s, lv) => s + lv.sell, 0);
  const totalDelta = totalBuy - totalSell;
  ctx.font = `${L.fontSize.tick * dpr}px ${L.fontFamily}`;
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(239,83,80,0.6)';
  ctx.fillText(`SELL ${formatVol(totalSell)}`, centerX / 2, sumY + 6 * dpr);
  ctx.fillStyle = 'rgba(38,166,154,0.6)';
  ctx.fillText(`BUY ${formatVol(totalBuy)}`, centerX + priceLabelW + (barAreaW - priceLabelW) / 2, sumY + 6 * dpr);
  ctx.fillStyle = totalDelta >= 0 ? 'rgba(38,166,154,0.7)' : 'rgba(239,83,80,0.7)';
  ctx.fillText(`Δ ${formatDelta(totalDelta)}`, deltaX + deltaColW / 2, sumY + 6 * dpr);
}

// ── Phase 3: Full Footprint Chart ──
// Professional bid×ask footprint — numeric values at each price level per time bar
// with delta column, POC markers, imbalance highlighting, and finished auction detection
function renderFootprintChart(containerId, data, fullScreen){
  const container = document.getElementById(containerId);
  if(!container) return;
  const entry = _ensureCanvas(containerId);
  if(!entry) return;
  const {canvas, ctx, dpr} = entry;
  const W = canvas.width, H = canvas.height;
  const L = FLOW_LAYOUT;

  ctx.fillStyle = L.bg;
  ctx.fillRect(0, 0, W, H);

  const cells = data.clouds || [];
  if(!cells.length){
    ctx.fillStyle = L.subtitleColor;
    ctx.font = `${L.fontSize.empty * dpr}px ${L.fontFamily}`;
    ctx.textAlign = 'center';
    ctx.fillText('Footprint Chart — Waiting for flow data...', W / 2, H / 2);
    return;
  }

  // ── Aggregate into {timeBar → {priceLevel → {buy, sell}}} ──
  const priceTick = liveFlow.priceTick || 0.05;
  const barBuckets = new Map(); // timeKey → Map<priceKey, {buy, sell, total, delta}>
  const allPricesSet = new Set();

  cells.forEach(c => {
    const tKey = c.time.substring(0, 16); // minute-level bucket
    if(!barBuckets.has(tKey)) barBuckets.set(tKey, new Map());
    const bar = barBuckets.get(tKey);
    const p = (Math.round(c.price / priceTick) * priceTick);
    const pKey = p.toFixed(2);
    allPricesSet.add(pKey);
    if(!bar.has(pKey)) bar.set(pKey, {price: p, buy: 0, sell: 0, total: 0, delta: 0});
    const lv = bar.get(pKey);
    lv.buy += c.buy_vol || 0;
    lv.sell += c.sell_vol || 0;
    lv.total += c.total_vol || 0;
    lv.delta += c.delta || 0;
  });

  const timeKeys = [...barBuckets.keys()].sort();
  const allPrices = [...allPricesSet].map(Number).sort((a, b) => b - a);
  if(!timeKeys.length || !allPrices.length) return;

  // ── Per-bar metadata: POC, bar delta, finished auction ──
  const barMeta = new Map();
  timeKeys.forEach(tKey => {
    const bar = barBuckets.get(tKey);
    let pocPrice = null, pocVol = 0, barDelta = 0, barTotal = 0;
    bar.forEach((lv, pKey) => {
      if(lv.total > pocVol){ pocVol = lv.total; pocPrice = pKey; }
      barDelta += lv.delta;
      barTotal += lv.total;
    });
    // Finished auction: top price has more sell than buy, bottom has more buy than sell
    const topPrice = allPrices[0].toFixed(2);
    const botPrice = allPrices[allPrices.length - 1].toFixed(2);
    const topLv = bar.get(topPrice);
    const botLv = bar.get(botPrice);
    const finishedTop = topLv ? topLv.sell > topLv.buy : false;
    const finishedBot = botLv ? botLv.buy > botLv.sell : false;
    barMeta.set(tKey, {pocPrice, barDelta, barTotal, finishedTop, finishedBot});
  });

  // ── Layout geometry ──
  const headerH = L.headerH * dpr;
  const priceLabelW = 52 * dpr;
  const timeLabelH = 16 * dpr;
  const availW = W - priceLabelW;
  const availH = H - headerH - timeLabelH;
  const rowH = Math.max(10 * dpr, Math.min(20 * dpr, availH / allPrices.length));
  const visiblePrices = Math.min(allPrices.length, Math.floor(availH / rowH));
  // Size columns to fit, showing as many time bars as possible
  const minColW = 70 * dpr;
  const maxCols = Math.max(1, Math.floor(availW / minColW));
  const visibleTimes = timeKeys.slice(-maxCols);
  const colW = Math.min(140 * dpr, availW / visibleTimes.length);
  const startX = priceLabelW;
  const startY = headerH;

  // Global max volume for cell intensity scaling
  let globalMaxVol = 1;
  barBuckets.forEach(bar => bar.forEach(lv => { globalMaxVol = Math.max(globalMaxVol, lv.total); }));

  // Imbalance threshold ratio
  const IMB_RATIO = 3.0;

  // ── Header ──
  ctx.fillStyle = L.titleColor;
  ctx.font = `bold ${L.fontSize.title * dpr}px ${L.fontFamily}`;
  ctx.textAlign = 'center';
  ctx.fillText('FOOTPRINT CHART', W / 2, L.titleY * dpr);
  ctx.fillStyle = L.subtitleColor;
  ctx.font = `${L.fontSize.subtitle * dpr}px ${L.fontFamily}`;
  ctx.fillText(`${allPrices.length} levels × ${visibleTimes.length} bars  ·  Sell × Buy  ·  Imbalance ≥ ${IMB_RATIO}:1`, W / 2, L.subtitleY * dpr);

  // Separator
  ctx.strokeStyle = L.separatorColor;
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(0, headerH - 4 * dpr); ctx.lineTo(W, headerH - 4 * dpr); ctx.stroke();

  // ── Draw grid and cells ──
  // Pre-compute fonts and colors outside the hot nested loop to avoid string allocations
  const labelFont = `${L.fontSize.label * dpr}px ${L.fontFamily}`;
  const _pocFill = 'rgba(255,179,0,0.5)';
  const _sellNorm = 'rgba(239,83,80,0.75)';
  const _buyNorm = 'rgba(38,166,154,0.75)';
  const _sepColor = 'rgba(255,255,255,0.15)';
  // Pre-build intensity color lookup tables (quantized to 20 steps to avoid per-cell string creation)
  const _bgBuyImb = [], _bgSellImb = [], _bgNeutral = [];
  for(let q = 0; q <= 20; q++){
    const t = q / 20;
    _bgBuyImb[q] = `rgba(0,230,118,${(0.05 + t * 0.22).toFixed(3)})`;
    _bgSellImb[q] = `rgba(255,23,68,${(0.05 + t * 0.22).toFixed(3)})`;
    _bgNeutral[q] = `rgba(255,255,255,${(0.01 + t * 0.06).toFixed(3)})`;
  }
  // Number formatter cache (avoids toLocaleString per cell — pre-format at grid scope)
  const _fmtNum = (n) => n > 0 ? formatVol(n) : '·';

  for(let pi = 0; pi < visiblePrices; pi++){
    const priceVal = allPrices[pi];
    const pKey = priceVal.toFixed(2);
    const y = startY + pi * rowH;

    // Price label
    ctx.fillStyle = L.labelColor;
    ctx.font = labelFont;
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(pKey, startX - 5 * dpr, y + rowH / 2);

    // Horizontal grid line
    ctx.strokeStyle = L.gridColor;
    ctx.beginPath(); ctx.moveTo(startX, y); ctx.lineTo(W, y); ctx.stroke();

    for(let ti = 0; ti < visibleTimes.length; ti++){
      const tKey = visibleTimes[ti];
      const x = startX + ti * colW;
      const bar = barBuckets.get(tKey);
      const lv = bar ? bar.get(pKey) : null;
      const meta = barMeta.get(tKey);
      const isPOC = meta && meta.pocPrice === pKey;

      // Vertical column separator
      if(pi === 0){
        ctx.strokeStyle = L.separatorColor;
        ctx.beginPath(); ctx.moveTo(x, startY); ctx.lineTo(x, startY + visiblePrices * rowH); ctx.stroke();
      }

      if(!lv || lv.total === 0) continue;

      // Cell intensity — quantized to 20-step lookup table
      const qIdx = Math.min(20, (lv.total / globalMaxVol * 20) | 0);

      // Imbalance detection
      const buyImb = lv.sell > 0 ? lv.buy / lv.sell >= IMB_RATIO : lv.buy > 0;
      const sellImb = lv.buy > 0 ? lv.sell / lv.buy >= IMB_RATIO : lv.sell > 0;

      // Cell background — uses pre-computed color lookup
      ctx.fillStyle = buyImb && lv.buy > 0 ? _bgBuyImb[qIdx] : sellImb && lv.sell > 0 ? _bgSellImb[qIdx] : _bgNeutral[qIdx];
      ctx.fillRect(x + 1, y + 1, colW - 2, rowH - 2);

      // POC row marker — bright left edge
      if(isPOC){
        ctx.fillStyle = _pocFill;
        ctx.fillRect(x + 1, y + 1, 3 * dpr, rowH - 2);
      }

      // Cell text: sell × buy
      const cellFS = Math.max(6, Math.min(L.fontSize.label, Math.min(rowH / dpr - 4, colW / dpr / 10)));
      const cellFont = `${cellFS * dpr}px ${L.fontFamily}`;
      const cellFontBold = `bold ${cellFS * dpr}px ${L.fontFamily}`;
      ctx.font = cellFont;
      ctx.textBaseline = 'middle';
      const textY = y + rowH / 2;

      // Sell number (left side of cell)
      ctx.textAlign = 'right';
      ctx.fillStyle = sellImb ? T.negative : _sellNorm;
      if(sellImb) ctx.font = cellFontBold;
      ctx.fillText(_fmtNum(lv.sell), x + colW * 0.42, textY);

      // Separator ×
      ctx.textAlign = 'center';
      ctx.fillStyle = _sepColor;
      ctx.font = cellFont;
      ctx.fillText('×', x + colW * 0.5, textY);

      // Buy number (right side of cell)
      ctx.textAlign = 'left';
      ctx.fillStyle = buyImb ? T.positive : _buyNorm;
      if(buyImb) ctx.font = cellFontBold;
      else ctx.font = cellFont;
      ctx.fillText(lv.buy > 0 ? formatVol(lv.buy) : '·', x + colW * 0.58, textY);

      ctx.textBaseline = 'alphabetic';
    }
  }

  // ── Last column separator ──
  const lastColX = startX + visibleTimes.length * colW;
  ctx.strokeStyle = L.separatorColor;
  ctx.beginPath(); ctx.moveTo(lastColX, startY); ctx.lineTo(lastColX, startY + visiblePrices * rowH); ctx.stroke();

  // ── Bottom row: bar delta + time labels ──
  const bottomY = startY + visiblePrices * rowH;
  ctx.strokeStyle = L.separatorColor;
  ctx.beginPath(); ctx.moveTo(startX, bottomY); ctx.lineTo(W, bottomY); ctx.stroke();

  for(let ti = 0; ti < visibleTimes.length; ti++){
    const tKey = visibleTimes[ti];
    const x = startX + ti * colW;
    const meta = barMeta.get(tKey);

    // Bar delta
    if(meta){
      const d = meta.barDelta;
      ctx.fillStyle = d >= 0 ? 'rgba(38,166,154,0.8)' : 'rgba(239,83,80,0.8)';
      ctx.font = `bold ${L.fontSize.tick * dpr}px ${L.fontFamily}`;
      ctx.textAlign = 'center';
      ctx.fillText(formatDelta(d), x + colW / 2, bottomY + 8 * dpr);

      // Finished auction indicators
      if(meta.finishedTop){
        ctx.fillStyle = 'rgba(239,83,80,0.4)';
        ctx.fillRect(x + colW / 2 - 3 * dpr, startY - 4 * dpr, 6 * dpr, 3 * dpr);
      }
      if(meta.finishedBot){
        ctx.fillStyle = 'rgba(38,166,154,0.4)';
        ctx.fillRect(x + colW / 2 - 3 * dpr, bottomY + 1, 6 * dpr, 3 * dpr);
      }
    }

    // Time label
    ctx.fillStyle = L.labelColor;
    ctx.font = `${L.fontSize.tick * dpr}px ${L.fontFamily}`;
    ctx.textAlign = 'center';
    ctx.fillText(tKey.substring(11, 16), x + colW / 2, H - 3 * dpr);
  }

  // ── Price label for "DELTA" row ──
  ctx.fillStyle = L.subtitleColor;
  ctx.font = `${L.fontSize.tick * dpr}px ${L.fontFamily}`;
  ctx.textAlign = 'right';
  ctx.fillText('Δ', startX - 5 * dpr, bottomY + 8 * dpr);
}

function renderFlowChart(containerId, data, fullScreen){
  const container = document.getElementById(containerId);
  if(!container || !data.clouds || !data.clouds.length) return;

  // Route to correct renderer based on flow sub-tab
  if(currentFlowView === 'perprice'){
    renderPerPriceProfile(containerId, data, fullScreen);
    return;
  }
  if(currentFlowView === 'footprint'){
    renderFootprintChart(containerId, data, fullScreen);
    return;
  }

  // Default: Bubbles view (existing renderer)
  const entry = _ensureCanvas(containerId);
  if(!entry) return;
  const {canvas, ctx, dpr} = entry;
  const W = canvas.width;
  const H = canvas.height;

  const allCells = data.clouds;
  // Pre-compute millisecond timestamps once (avoids new Date() in every filter/map call)
  for(let i = 0; i < allCells.length; i++){
    if(allCells[i]._ms === undefined) allCells[i]._ms = new Date(allCells[i].time).getTime();
  }
  allCells.sort((a,b) => a._ms - b._ms || a.price - b.price);

  // === SLIDING WINDOW ===
  const windowMs = liveFlow.visibleWindowMs || 4 * 60 * 1000;
  const hasLiveData = liveFlow.ticks.length > 0;

  let xEndMs, xStartMs;
  if(hasLiveData){
    xEndMs = Date.now();
  } else {
    // Use cached _ms instead of creating Date objects
    let maxMs = 0;
    for(let i = 0; i < allCells.length; i++) if(allCells[i]._ms > maxMs) maxMs = allCells[i]._ms;
    xEndMs = maxMs;
  }
  xStartMs = xEndMs - windowMs;

  // Filter to visible window using cached _ms
  let cells = allCells.filter(c => c._ms >= xStartMs);

  // If no cells in window (REST polling latency), re-anchor to latest data point
  if(!cells.length && allCells.length){
    const latestDataMs = allCells[allCells.length - 1]._ms; // Already sorted, last is latest
    const gap = xEndMs - latestDataMs;
    if(gap > 0 && gap < 10 * 60 * 1000){
      xEndMs = latestDataMs + windowMs * 0.1;
      xStartMs = xEndMs - windowMs;
      cells = allCells.filter(c => c._ms >= xStartMs);
    }
  }

  if(!cells.length){
    ctx.clearRect(0, 0, W, H);
    return;
  }

  // Layout constants — Prismadic-style: price labels on left, volume profile ladder on right
  // Sourced from FLOW_LAYOUT shared config to stay consistent across all renderers
  const marginL = FLOW_LAYOUT.marginL * dpr;
  const ladderW = FLOW_LAYOUT.ladderW * dpr;
  const marginR = ladderW;
  const marginT = FLOW_LAYOUT.marginT * dpr;
  // THREE DISTINCT ZONES: [Chart area] | [Time labels] | [Volume bars]
  // Adaptive sizing: when chart is short (combined view ≤400px CSS), use compact bottom zones
  const isCompact = (H / dpr) < 420;
  const timeLabelH = isCompact ? 24 * dpr : 40 * dpr;
  const volBarH = isCompact ? Math.round(H * 0.10) : Math.round(H * 0.15);
  const separatorH = 2 * dpr;   // Visual separator lines between zones
  const marginB = timeLabelH + volBarH + separatorH * 2; // Total bottom reservation
  const plotW = W - marginL - marginR;
  const plotH = H - marginT - marginB;
  // Zone Y positions (top to bottom)
  const timeLabelTop = marginT + plotH + separatorH;  // Where time labels start
  const volTop = timeLabelTop + timeLabelH + separatorH; // Where volume bars start
  const volH = volBarH - 4 * dpr; // Leave a little breathing room

  // === PRICE RANGE — snap to user-configurable tick grid ===
  const priceTick = liveFlow.priceTick || 0.05;
  const prices = cells.map(c => c.price).sort((a, b) => a - b);

  // --- Outlier filtering via IQR ---
  // Bad ticks or block trades at extreme prices destroy the Y-axis.
  // Use interquartile range to clip outliers before computing axis bounds.
  const q1Idx = Math.floor(prices.length * 0.25);
  const q3Idx = Math.floor(prices.length * 0.75);
  const q1 = prices[q1Idx], q3 = prices[q3Idx];
  const iqr = q3 - q1 || priceTick * 10; // fallback if all same price
  const iqrFence = 3.0; // 3× IQR — generous enough to keep real moves, clips bad ticks
  const lowerFence = q1 - iqrFence * iqr;
  const upperFence = q3 + iqrFence * iqr;
  const cleanPrices = prices.filter(p => p >= lowerFence && p <= upperFence);
  // Fallback to all prices if filtering removes everything
  const usePrices = cleanPrices.length >= 3 ? cleanPrices : prices;

  const rawMin = usePrices[0];
  const rawMax = usePrices[usePrices.length - 1];
  const rawRange = rawMax - rawMin;
  const dataMid = (rawMin + rawMax) / 2;

  // === FIXED 22px SPACING — enforce equal, readable distance between price labels ===
  // Target: exactly 22 CSS-pixels between each price label on the ladder.
  const TARGET_LABEL_PX = 22 * dpr;

  // How many labels fit in the plot area at the target spacing
  const numLabels = Math.floor(plotH / TARGET_LABEL_PX);

  // Pick the smallest "nice" price step that covers the data range within numLabels.
  // Nice steps: $0.05, $0.10, $0.25, $0.50, $1.00, $2.00, $5.00
  const nicePriceSteps = [0.05, 0.10, 0.25, 0.50, 1.00, 2.00, 5.00];
  let labelStep = priceTick;
  for(const s of nicePriceSteps){
    if(s >= priceTick && s * numLabels >= rawRange * 1.3){ // 1.3× so data has breathing room
      labelStep = s;
      break;
    }
  }
  // Fallback: if no nice step works, compute one
  if(labelStep * numLabels < rawRange){
    labelStep = Math.ceil(rawRange / numLabels / priceTick) * priceTick;
  }

  // Compute Y range centered on data midpoint, covering exactly numLabels × labelStep
  const totalRange = numLabels * labelStep;
  const yMin = Math.floor((dataMid - totalRange / 2) / labelStep) * labelStep;
  const yMax = yMin + totalRange;

  // Coordinate mappers
  const tToX = (ms) => marginL + ((ms - xStartMs) / windowMs) * plotW;
  const pToY = (p) => marginT + plotH - ((p - yMin) / (yMax - yMin)) * plotH;

  // === BUBBLE SIZE TIERS (absolute volume thresholds for SPY) ===
  // Bubbles sized to OVERLAP at typical density — creates continuous "snake" trail (Prismadic)
  // At 1s agg with 2m window: ~120 bubbles across plotW → spacing = plotW/120
  // We want even "tiny" bubbles to nearly touch → radius ≈ spacing/2
  const aggScale = Math.max(liveFlow.aggSeconds || 1, 0.01);
  const numBuckets = windowMs / (aggScale * 1000);
  const pxPerBubble = plotW / Math.max(numBuckets, 1);
  const minR = Math.max(4 * dpr, pxPerBubble * 0.55); // Base radius for overlap
  const maxR = Math.max(minR * 3.5, (fullScreen ? 28 : 24) * dpr); // Maximum bubble radius

  // DYNAMIC volume-to-radius: use actual data percentiles so bubbles ALWAYS vary in size
  // This works in any market condition (after-hours, regular, high-volatility)
  const allVols = cells.map(c => c.total_vol || (c.buy_vol + c.sell_vol)).filter(v => v > 0).sort((a,b) => a - b);
  const p20 = allVols[Math.floor(allVols.length * 0.20)] || 1;
  const p50 = allVols[Math.floor(allVols.length * 0.50)] || 10;
  const p80 = allVols[Math.floor(allVols.length * 0.80)] || 100;
  const p95 = allVols[Math.floor(allVols.length * 0.95)] || 1000;

  function volToRadius(vol){
    // Continuous interpolation based on data percentiles — guarantees visible size variation
    if(vol <= p20) return minR;
    if(vol <= p50) {
      const t = (vol - p20) / (p50 - p20 || 1);
      return minR + t * (minR * 0.5);
    }
    if(vol <= p80) {
      const t = (vol - p50) / (p80 - p50 || 1);
      return minR * 1.5 + t * (minR * 1.0);
    }
    if(vol <= p95) {
      const t = (vol - p80) / (p95 - p80 || 1);
      return minR * 2.5 + t * (minR * 1.0);
    }
    // Above p95 — scale up to maxR
    const t = Math.min(1, (vol - p95) / (p95 * 2 || 1));
    return minR * 3.5 + t * (maxR - minR * 3.5);
  }

  // === CLEAR & DRAW ===
  ctx.clearRect(0, 0, W, H);

  // Background
  ctx.fillStyle = FLOW_LAYOUT.bg;
  ctx.fillRect(0, 0, W, H);

  // === VISUAL SEPARATORS between components ===
  // Separator 1: Below chart area (between chart and time labels)
  ctx.fillStyle = 'rgba(255,255,255,0.08)';
  ctx.fillRect(marginL, marginT + plotH, plotW, separatorH);
  // Separator 2: Below time labels (between time labels and volume bars)
  ctx.fillRect(marginL, volTop - separatorH, plotW, separatorH);
  // Slightly darker background for time label zone
  ctx.fillStyle = 'rgba(8,8,16,0.5)';
  ctx.fillRect(marginL, timeLabelTop, plotW, timeLabelH);
  // Slightly different background for volume zone
  ctx.fillStyle = 'rgba(12,12,20,0.4)';
  ctx.fillRect(marginL, volTop, plotW, volH + 4 * dpr);

  // === Y-AXIS GRID — snapped to labelStep for equal 22px spacing ===
  ctx.lineWidth = 1;
  const firstPriceTick = Math.ceil(yMin / labelStep) * labelStep;
  for(let p = firstPriceTick; p <= yMax; p += labelStep){
    const gy = pToY(p);
    if(gy < marginT || gy > marginT + plotH) continue;
    ctx.strokeStyle = 'rgba(255,255,255,0.04)';
    ctx.beginPath(); ctx.moveTo(marginL, gy); ctx.lineTo(W - marginR, gy); ctx.stroke();
  }

  // === X-AXIS GRID — Prismadic-style: very dense, ~1 line per aggregation bucket ===
  const aggMs = (liveFlow.aggSeconds || 1) * 1000;
  // Time step = agg interval (every bubble gets a grid line, like Prismadic)
  let timeStep = aggMs;
  // But cap max grid lines to prevent performance issues (~200 max)
  const maxGridLines = 200;
  const minTimeStep = windowMs / maxGridLines;
  if(timeStep < minTimeStep) timeStep = minTimeStep;
  // Snap sub-second to nice values
  const niceSteps = [5, 10, 25, 50, 100, 250, 500, 1000, 2000, 3000, 5000, 10000, 15000, 30000, 60000, 120000, 300000];
  if(timeStep > aggMs){
    for(const s of niceSteps){
      if(s >= timeStep){ timeStep = s; break; }
    }
  }

  const firstTimeTick = Math.ceil(xStartMs / timeStep) * timeStep;
  // Major lines every 5s or 10s depending on scale
  const majorTimeStep = timeStep <= 1000 ? 5000 : timeStep <= 5000 ? 15000 : timeStep * 5;
  for(let t = firstTimeTick; t <= xEndMs; t += timeStep){
    const gx = tToX(t);
    if(gx < marginL || gx > W - marginR) continue;
    const isMajorTime = Math.abs(t % majorTimeStep) < (timeStep / 2);
    ctx.strokeStyle = isMajorTime ? 'rgba(255,255,255,0.07)' : 'rgba(255,255,255,0.025)';
    ctx.beginPath(); ctx.moveTo(gx, marginT); ctx.lineTo(gx, marginT + plotH); ctx.stroke();
  }

  // === LEFT PRICE LABELS — aligned to labelStep grid for equal 22px spacing ===
  ctx.font = `${9 * dpr}px "SF Mono", Menlo, monospace`;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for(let p = firstPriceTick; p <= yMax; p += labelStep){
    const gy = pToY(p);
    if(gy < marginT + 6 || gy > marginT + plotH - 6) continue;
    ctx.fillStyle = '#7a7a94';
    const leftLabel = p % 1 === 0 ? p.toFixed(0) : parseFloat(p.toFixed(2)).toString();
    ctx.fillText(leftLabel, marginL - 6 * dpr, gy);
  }

  // === PRICE LADDER (right side) — Prismadic layout: price labels LEFT of ladder, bars grow RIGHT ===
  // Aggregate volume by price tick bins for the profile
  const ladderProfile = {};
  cells.forEach(c => {
    const binPrice = (Math.round(c.price / priceTick) * priceTick).toFixed(2);
    if(!ladderProfile[binPrice]) ladderProfile[binPrice] = {buy:0, sell:0};
    ladderProfile[binPrice].buy += c.buy_vol;
    ladderProfile[binPrice].sell += c.sell_vol;
  });
  const ladderMaxVol = Math.max(...Object.values(ladderProfile).map(v => v.buy + v.sell), 1);
  const ladderX = W - ladderW; // Left edge of ladder area
  const priceLabelW = 46 * dpr; // Space for price labels on LEFT side of ladder
  const ladderBarMaxW = ladderW - priceLabelW - 4 * dpr; // Space for volume bars growing RIGHT

  // Background for ladder area
  ctx.fillStyle = 'rgba(15,15,25,0.6)';
  ctx.fillRect(ladderX, marginT, ladderW, plotH);
  // Separator line
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(ladderX, marginT); ctx.lineTo(ladderX, marginT + plotH); ctx.stroke();

  // Fixed 22px spacing — font size is constant since spacing is guaranteed
  ctx.font = `${9 * dpr}px "SF Mono", Menlo, monospace`;

  // Prismadic layout: price labels on LEFT side of ladder, bars start after labels and grow RIGHT
  const priceLabelX = ladderX + priceLabelW; // Right edge of price label area (= left edge of bars)
  const barStartX = priceLabelX + 2 * dpr;   // Bars start just after price labels

  // Aggregate volume into labelStep bins for the ladder bars
  const ladderStepProfile = {};
  cells.forEach(c => {
    const binPrice = (Math.round(c.price / labelStep) * labelStep).toFixed(2);
    if(!ladderStepProfile[binPrice]) ladderStepProfile[binPrice] = {buy:0, sell:0};
    ladderStepProfile[binPrice].buy += c.buy_vol;
    ladderStepProfile[binPrice].sell += c.sell_vol;
  });
  const ladderStepMaxVol = Math.max(...Object.values(ladderStepProfile).map(v => v.buy + v.sell), 1);

  for(let p = firstPriceTick; p <= yMax; p += labelStep){
    const gy = pToY(p);
    if(gy < marginT + 4 || gy > marginT + plotH - 4) continue;
    const pKey = p.toFixed(2);
    const vol = ladderStepProfile[pKey];

    // Subtle grid line across ladder
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    ctx.beginPath(); ctx.moveTo(ladderX, gy); ctx.lineTo(W, gy); ctx.stroke();

    // VOLUME BARS — grow RIGHT from after price labels (Prismadic style)
    if(vol){
      const totalVol = vol.buy + vol.sell;
      const totalW = (totalVol / ladderStepMaxVol) * ladderBarMaxW;
      const sellW = totalW * (vol.sell / (totalVol || 1));
      const buyW = totalW - sellW;
      const barH = Math.max(2 * dpr, Math.min(TARGET_LABEL_PX * 0.7, 14 * dpr));

      // Sell bar (red, starts at barStartX, grows right)
      ctx.fillStyle = 'rgba(239,83,80,0.75)';
      ctx.fillRect(barStartX, gy - barH/2, sellW, barH);
      // Buy bar (green, continues right after sell)
      ctx.fillStyle = 'rgba(38,166,154,0.75)';
      ctx.fillRect(barStartX + sellW, gy - barH/2, buyW, barH);
    }

    // PRICE LABEL — every label shown (equal 22px spacing guaranteed)
    const hasVol = !!vol;
    ctx.fillStyle = hasVol ? '#9898b0' : '#52526a';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.fillText(pKey, priceLabelX - 2 * dpr, gy);
  }

  // === X-AXIS LABELS (time) — Prismadic-style: rotated diagonal labels, very dense ===
  const showMs = timeStep < 1000;
  const showSeconds = timeStep < 60000;

  // Prismadic uses small ~60° rotated labels packed extremely tight
  const timeFontSize = 7;
  ctx.font = `${timeFontSize * dpr}px "SF Mono", Menlo, monospace`;

  // With rotation, effective horizontal footprint is much smaller — pack tighter
  const sampleLabel = showMs ? '32.005' : showSeconds ? '09:45:32' : '09:45';
  const labelTextW = ctx.measureText(sampleLabel).width;
  // Rotated label takes less horizontal space: width * cos(angle) + height * sin(angle)
  const rotAngle = -60 * (Math.PI / 180); // -60 degrees (angled left like Prismadic)
  const effectiveLabelW = Math.abs(labelTextW * Math.cos(rotAngle)) + Math.abs(timeFontSize * dpr * Math.sin(rotAngle));
  const labelPxW = effectiveLabelW + 2 * dpr; // minimal gap between rotated labels
  const pxPerStep = (plotW / windowMs) * timeStep;
  const labelTimeSkip = Math.max(1, Math.ceil(labelPxW / pxPerStep));

  let labelTimeIdx = 0;
  for(let t = firstTimeTick; t <= xEndMs; t += timeStep){
    const gx = tToX(t);
    if(gx < marginL + 5 || gx > W - marginR - 5){ labelTimeIdx++; continue; }

    if(labelTimeIdx % labelTimeSkip === 0){
      const d = new Date(t);
      let label;
      if(showMs){
        const sec = String(d.getSeconds()).padStart(2, '0');
        const ms = String(d.getMilliseconds()).padStart(3, '0');
        label = `${sec}.${ms}`;
      } else if(showSeconds){
        label = d.toLocaleTimeString('en-US', {hour12:false, hour:'2-digit', minute:'2-digit', second:'2-digit'});
      } else {
        label = d.toLocaleTimeString('en-US', {hour12:false, hour:'2-digit', minute:'2-digit'});
      }
      // Alternate brighter/dimmer for readability at high density
      const isMajorLabel = Math.abs(t % majorTimeStep) < (timeStep / 2);
      ctx.fillStyle = isMajorLabel ? '#8888a0' : '#5a5a72';

      // Draw rotated label (Prismadic style: ~60° angle)
      ctx.save();
      ctx.translate(gx, timeLabelTop + 3 * dpr);
      ctx.rotate(rotAngle);
      ctx.textAlign = 'right';
      ctx.textBaseline = 'top';
      ctx.fillText(label, 0, 0);
      ctx.restore();
    }
    labelTimeIdx++;
  }

  // === VOLUME BARS at bottom (clipped to volume zone — cannot overflow into time labels) ===
  const barBuckets = {};
  cells.forEach(c => {
    const t = new Date(c.time).getTime();
    const bucketMs = Math.floor(t / (liveFlow.aggSeconds * 1000)) * (liveFlow.aggSeconds * 1000);
    if(!barBuckets[bucketMs]) barBuckets[bucketMs] = {buy:0, sell:0};
    barBuckets[bucketMs].buy += c.buy_vol;
    barBuckets[bucketMs].sell += c.sell_vol;
  });
  const barMaxVol = Math.max(...Object.values(barBuckets).map(b => b.buy + b.sell), 1);
  const barW = Math.max(1, (plotW / (windowMs / (liveFlow.aggSeconds * 1000))) * 0.7);

  // Volume scale labels on left
  ctx.font = `${7 * dpr}px "SF Mono", Menlo, monospace`;
  ctx.textAlign = 'right';
  ctx.fillStyle = '#52526a';
  const volScaleSteps = 4;
  for(let i = 0; i <= volScaleSteps; i++){
    const volVal = Math.round((barMaxVol / volScaleSteps) * i);
    const vy = volTop + volH - (i / volScaleSteps) * volH;
    const volLabel = formatVol(volVal);
    ctx.fillText(volLabel, marginL - 6 * dpr, vy);
    // Subtle grid line
    ctx.strokeStyle = 'rgba(255,255,255,0.03)';
    ctx.beginPath(); ctx.moveTo(marginL, vy); ctx.lineTo(W - marginR, vy); ctx.stroke();
  }

  // Clip volume bars strictly to their zone — prevents overflow into time labels
  ctx.save();
  ctx.beginPath();
  ctx.rect(marginL - 1, volTop, plotW + 2, volH + 4 * dpr);
  ctx.clip();

  Object.entries(barBuckets).forEach(([ms, b]) => {
    const x = tToX(parseInt(ms));
    if(x < marginL || x > W - marginR) return;
    const totalH = ((b.buy + b.sell) / barMaxVol) * volH;
    const buyH = totalH * (b.buy / (b.buy + b.sell || 1));
    const sellH = totalH - buyH;
    // Buy bar (green/yellow, grows upward from baseline)
    ctx.fillStyle = 'rgba(38,166,154,0.7)';
    ctx.fillRect(x - barW/2, volTop + volH - totalH, barW, buyH);
    // Sell bar (red, stacked on top of buy)
    ctx.fillStyle = 'rgba(239,83,80,0.7)';
    ctx.fillRect(x - barW/2, volTop + volH - sellH, barW, sellH);
  });

  ctx.restore(); // Remove clip region

  // ═══════════════════════════════════════════════════════════════════════
  // INDICATOR 1: BID/ASK IMBALANCE BAR (at each price level in ladder)
  // ═══════════════════════════════════════════════════════════════════════
  // Display green up-arrow if buy_vol > sell_vol by 60%+, red down-arrow if reverse
  // Imbalance ratio = (buy - sell) / (buy + sell). Threshold: |ratio| > 0.2 (20%)
  for(let p = firstPriceTick; p <= yMax; p += labelStep){
    const gy = pToY(p);
    if(gy < marginT + 4 || gy > marginT + plotH - 4) continue;
    const pKey = p.toFixed(2);
    const vol = ladderStepProfile[pKey];

    if(vol && vol.buy + vol.sell > 0){
      const imbalanceRatio = (vol.buy - vol.sell) / (vol.buy + vol.sell);
      const threshold = 0.2; // 20% imbalance threshold

      if(Math.abs(imbalanceRatio) > threshold){
        const isImbalancedBuy = imbalanceRatio > threshold;
        const arrowColor = isImbalancedBuy ? T.positive : T.negative;
        const arrowSize = 8 * dpr;
        const arrowX = W - 10 * dpr; // Position at far right edge of ladder area

        ctx.fillStyle = arrowColor;
        ctx.globalAlpha = 0.65;

        if(isImbalancedBuy){
          // Green up-arrow (triangle pointing up)
          ctx.beginPath();
          ctx.moveTo(arrowX - arrowSize/2, gy + arrowSize/2);
          ctx.lineTo(arrowX + arrowSize/2, gy + arrowSize/2);
          ctx.lineTo(arrowX, gy - arrowSize/2);
          ctx.closePath();
          ctx.fill();
        } else {
          // Red down-arrow (triangle pointing down)
          ctx.beginPath();
          ctx.moveTo(arrowX - arrowSize/2, gy - arrowSize/2);
          ctx.lineTo(arrowX + arrowSize/2, gy - arrowSize/2);
          ctx.lineTo(arrowX, gy + arrowSize/2);
          ctx.closePath();
          ctx.fill();
        }

        ctx.globalAlpha = 1.0;
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // INDICATOR 2: DELTA DIVERGENCE DETECTION
  // ═══════════════════════════════════════════════════════════════════════
  // Detect when price trend opposes cumulative delta trend (bearish/bullish divergence)
  // Track rolling CVD over visible window & compare last 30% of price vs CVD slopes
  let recentPrices = null, recentCVD = null;
  let cumulativeDelta = [], runningDeltaTotal = 0;
  if(cells.length >= 3){
    // Calculate cumulative volume delta across all cells
    cells.forEach(c => {
      runningDeltaTotal += c.delta;
      cumulativeDelta.push(runningDeltaTotal);
    });

    // Get last 30% of data
    const cutoffIdx = Math.max(0, Math.floor(cells.length * 0.7));
    recentPrices = cells.slice(cutoffIdx).map(c => c.price);
    recentCVD = cumulativeDelta.slice(cutoffIdx);

    if(recentPrices.length >= 2 && recentCVD.length >= 2){
      // Calculate price slope (rise / run)
      const priceSlope = recentPrices[recentPrices.length - 1] - recentPrices[0];
      // Calculate CVD slope
      const cvdSlope = recentCVD[recentCVD.length - 1] - recentCVD[0];

      // Divergence: opposite signs (price up, CVD down = bearish distribution) or (price down, CVD up = bullish accumulation)
      const isBearishDiv = priceSlope > 0 && cvdSlope < 0; // Price rising but CVD falling
      const isBullishDiv = priceSlope < 0 && cvdSlope > 0; // Price falling but CVD rising

      if(isBearishDiv || isBullishDiv){
        const barW = 60 * dpr;
        const barH = 12 * dpr;
        const barX = marginL + 8 * dpr;
        const barY = marginT + 5 * dpr;
        const divColor = isBullishDiv ? T.positive : T.negative;
        const divLabel = isBullishDiv ? 'BULL DIV' : 'BEAR DIV';

        // Draw colored indicator bar at top-left
        ctx.fillStyle = divColor;
        ctx.globalAlpha = 0.55;
        ctx.fillRect(barX, barY, barW, barH);
        ctx.globalAlpha = 1.0;

        // Draw text label
        ctx.fillStyle = divColor;
        ctx.font = `${10 * dpr}px "SF Mono", Menlo, monospace`;
        ctx.fontWeight = '700';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(divLabel, barX + 4 * dpr, barY + barH / 2);
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // INDICATOR 3: ABSORPTION DETECTION MARKERS
  // ═══════════════════════════════════════════════════════════════════════
  // Mark price levels where large volume traded but price didn't move much
  // If total volume at price level is in top 20% but price stayed within 1 tick, highlight
  const sortedVolumes = Object.values(ladderStepProfile)
    .map(v => v.buy + v.sell)
    .sort((a, b) => b - a);
  const vol20thPercentile = sortedVolumes.length > 0 ? sortedVolumes[Math.floor(sortedVolumes.length * 0.2)] : 0;

  if(vol20thPercentile > 0){
    for(let p = firstPriceTick; p <= yMax; p += labelStep){
      const gy = pToY(p);
      if(gy < marginT + 4 || gy > marginT + plotH - 4) continue;
      const pKey = p.toFixed(2);
      const vol = ladderStepProfile[pKey];

      if(vol && (vol.buy + vol.sell) >= vol20thPercentile){
        const nextPrice = p + labelStep;
        const prevPrice = p - labelStep;
        const nextVol = ladderStepProfile[nextPrice.toFixed(2)] || {buy: 0, sell: 0};
        const prevVol = ladderStepProfile[prevPrice.toFixed(2)] || {buy: 0, sell: 0};

        const neighborVol = Math.max(nextVol.buy + nextVol.sell, prevVol.buy + prevVol.sell);
        const absorption = (vol.buy + vol.sell) / Math.max(neighborVol, 1);

        if(absorption > 1.5){
          const barW = 4 * dpr;
          const barH = Math.abs(pToY(p) - pToY(p + labelStep)) * 0.8;
          const barX = marginL + 2 * dpr; // Leftmost part of plot area

          ctx.fillStyle = T.warning; // POC highlight
          ctx.globalAlpha = 0.48;
          ctx.fillRect(barX, gy - barH/2, barW, barH);
          ctx.globalAlpha = 1.0;
        }
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // DRAW FLOWING TRAIL — connecting line + bubbles ===
  // ═══════════════════════════════════════════════════════════════════════
  const latestMs = Math.max(...cells.map(c => new Date(c.time).getTime()));
  const pulseThreshold = Math.max((liveFlow.aggSeconds || 1) * 2000, 3000);

  // Pre-compute positions and radii for trail line + bubbles
  // Uses tier-based absolute volume sizing (not relative log scale)
  const points = cells.map(c => {
    const tMs = new Date(c.time).getTime();
    const x = tToX(tMs);
    const y = pToY(c.price);
    const r = volToRadius(c.total_vol);
    const age = (tMs - xStartMs) / windowMs;
    const opacity = Math.max(0.15, Math.min(0.95, 0.15 + age * 0.80));
    return {x, y, r, tMs, opacity, c};
  }).filter(p => p.x >= marginL - 30 && p.x <= W - marginR + 30);

  // Store points for tooltip hit-testing
  _flowBubblePoints[containerId] = points;

  // ── STEP 1: Subtle shadow trail under bubbles (NOT a visible line chart) ──
  // This is just a faint shadow to give depth, bubbles themselves carry the visual weight
  if(points.length >= 2){
    // Very thin, very faint shadow — just enough to show flow direction without looking like a line chart
    const shadowW = Math.max(2 * dpr, minR * 0.4);

    ctx.globalAlpha = 0.08;
    ctx.lineWidth = shadowW;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = 'rgba(255,255,255,0.15)';
    ctx.beginPath();
    ctx.moveTo(points[0].x, points[0].y);
    for(let i = 1; i < points.length; i++){
      ctx.lineTo(points[i].x, points[i].y);
    }
    ctx.stroke();
    ctx.globalAlpha = 1.0;
  }

  // ── STEP 2: Draw bubbles (GPU-accelerated PixiJS or Canvas 2D fallback) ──
  if(window.USE_PIXIJS){
    // Initialize PixiJS renderer for this container if not yet created
    if(!flowRenderers[containerId]){
      flowRenderers[containerId] = new FlowRenderer();
      flowRenderers[containerId].init(containerId);
    } else if(!flowRenderers[containerId].initialized && !flowRenderers[containerId].initPromise){
      // Re-init if previous init failed
      flowRenderers[containerId].init(containerId);
    }
    const fr = flowRenderers[containerId];
    if(fr.initialized){
      // Sync PixiJS canvas size with container
      const rect = container.getBoundingClientRect();
      fr.resize(rect.width, rect.height);
      // GPU-render all bubbles as tinted sprites (~5 draw calls vs ~500 gradient ops)
      fr.renderBubbles(points, dpr, pulseThreshold, latestMs);
    } else {
      // PixiJS still loading — use Canvas 2D for this frame
      _drawBubblesCanvas2D(ctx, points, dpr, pulseThreshold, latestMs);
    }
  } else {
    // WebGL not available or disabled — pure Canvas 2D rendering
    _drawBubblesCanvas2D(ctx, points, dpr, pulseThreshold, latestMs);
  }

  // ═══════════════════════════════════════════════════════════════════════
  // STEP 3: PHASE 1 OVERLAYS — Large Prints, Absorption Bands,
  //         Volume Clusters, Divergence Arrows
  // ═══════════════════════════════════════════════════════════════════════

  // ── 3a: Large Print Rings ──
  // Draw golden pulsing rings around bubbles with volume ≥ LARGE_PRINT_THRESHOLD
  const largePrints = points.filter(p => p.c.total_vol >= FLOW_LAYOUT.largePrintThreshold);
  if(largePrints.length > 0){
    largePrints.forEach(p => {
      const ringR = p.r + 6 * dpr;
      // Outer glow
      ctx.beginPath();
      ctx.arc(p.x, p.y, ringR + 3 * dpr, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255,235,59,0.15)';
      ctx.lineWidth = 4 * dpr;
      ctx.stroke();
      // Inner ring
      ctx.beginPath();
      ctx.arc(p.x, p.y, ringR, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255,235,59,0.6)';
      ctx.lineWidth = 1.5 * dpr;
      ctx.setLineDash([4 * dpr, 3 * dpr]);
      ctx.stroke();
      ctx.setLineDash([]);
      // Volume label above bubble
      ctx.fillStyle = T.warning;
      ctx.font = `bold ${8 * dpr}px SF Mono, Menlo, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'bottom';
      ctx.fillText(formatVol(p.c.total_vol), p.x, p.y - ringR - 2 * dpr);
    });
  }

  // ── 3b: Absorption Bands ──
  // Full-width shaded horizontal bands at price levels where high volume didn't move price
  if(vol20thPercentile > 0){
    for(let p = firstPriceTick; p <= yMax; p += labelStep){
      const gy = pToY(p);
      if(gy < marginT + 4 || gy > marginT + plotH - 4) continue;
      const pKey = p.toFixed(2);
      const vol = ladderStepProfile[pKey];
      if(!vol || (vol.buy + vol.sell) < vol20thPercentile) continue;

      const nextVol = ladderStepProfile[(p + labelStep).toFixed(2)] || {buy:0, sell:0};
      const prevVol = ladderStepProfile[(p - labelStep).toFixed(2)] || {buy:0, sell:0};
      const neighborVol = Math.max(nextVol.buy + nextVol.sell, prevVol.buy + prevVol.sell);
      const absorption = (vol.buy + vol.sell) / Math.max(neighborVol, 1);

      if(absorption > 1.8){
        const bandH = Math.abs(pToY(p) - pToY(p + labelStep)) * 0.9;
        // Full-width semi-transparent cyan band
        ctx.fillStyle = 'rgba(0,188,212,0.08)';
        ctx.fillRect(marginL, gy - bandH/2, plotW, bandH);
        // Left edge accent
        ctx.fillStyle = 'rgba(0,188,212,0.35)';
        ctx.fillRect(marginL, gy - bandH/2, 3 * dpr, bandH);
        // Right-side label
        ctx.fillStyle = 'rgba(0,188,212,0.5)';
        ctx.font = `${7 * dpr}px SF Mono, Menlo, monospace`;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';
        const absLabel = absorption >= 3 ? 'STRONG ABS' : 'ABS';
        ctx.fillText(absLabel, marginL + plotW - 4 * dpr, gy);
      }
    }
  }

  // ── 3c: Volume Cluster Highlights ──
  // Detect time periods where multiple large bubbles cluster (institutional activity)
  if(points.length > 3){
    const clusterWindowMs = 15000; // 15-second clustering window
    const clusterMinBubbles = 3;
    const clusterMinVol = 2000;
    let i = 0;
    while(i < points.length){
      let j = i;
      let clusterVol = 0;
      while(j < points.length && points[j].tMs - points[i].tMs <= clusterWindowMs){
        clusterVol += points[j].c.total_vol;
        j++;
      }
      const count = j - i;
      if(count >= clusterMinBubbles && clusterVol >= clusterMinVol * count){
        const x1 = points[i].x;
        const x2 = points[j - 1].x;
        const colW = Math.max(x2 - x1, 10 * dpr);
        // Vertical highlight band
        const grad = ctx.createLinearGradient(0, marginT, 0, marginT + plotH);
        grad.addColorStop(0, 'rgba(124,77,255,0.06)');
        grad.addColorStop(0.5, 'rgba(124,77,255,0.03)');
        grad.addColorStop(1, 'rgba(124,77,255,0.06)');
        ctx.fillStyle = grad;
        ctx.fillRect(x1 - 4 * dpr, marginT, colW + 8 * dpr, plotH);
        // Top cluster label
        ctx.fillStyle = 'rgba(124,77,255,0.5)';
        ctx.font = `${7 * dpr}px SF Mono, Menlo, monospace`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(`${count}× ${formatVol(clusterVol)}`, (x1 + x2) / 2, marginT + 2 * dpr);
      }
      i = j > i ? j : i + 1;
    }
  }

  // ── 3d: Divergence Arrow ──
  // If divergence is detected, draw an arrow in the chart area (not just the label)
  if(recentPrices && recentPrices.length >= 2 && recentCVD && recentCVD.length >= 2){
    const priceSlope2 = recentPrices[recentPrices.length - 1] - recentPrices[0];
    const cvdSlope2 = recentCVD[recentCVD.length - 1] - recentCVD[0];
    const isBearDiv2 = priceSlope2 > 0 && cvdSlope2 < 0;
    const isBullDiv2 = priceSlope2 < 0 && cvdSlope2 > 0;

    if((isBearDiv2 || isBullDiv2) && points.length > 1){
      const lastPt = points[points.length - 1];
      const arrowX = lastPt.x + 12 * dpr;
      const arrowLen = 20 * dpr;
      const arrowDir = isBullDiv2 ? -1 : 1; // up for bullish, down for bearish
      const arrowColor = isBullDiv2 ? T.positive : T.negative;
      const arrowY = lastPt.y + arrowDir * (lastPt.r + 10 * dpr);

      // Arrow shaft
      ctx.beginPath();
      ctx.moveTo(arrowX, arrowY);
      ctx.lineTo(arrowX, arrowY + arrowDir * arrowLen);
      ctx.strokeStyle = arrowColor;
      ctx.lineWidth = 2 * dpr;
      ctx.globalAlpha = 0.7;
      ctx.stroke();
      // Arrow head
      ctx.beginPath();
      ctx.moveTo(arrowX, arrowY);
      ctx.lineTo(arrowX - 5 * dpr, arrowY + arrowDir * 7 * dpr);
      ctx.lineTo(arrowX + 5 * dpr, arrowY + arrowDir * 7 * dpr);
      ctx.closePath();
      ctx.fillStyle = arrowColor;
      ctx.fill();
      ctx.globalAlpha = 1.0;
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // END PHASE 1 OVERLAYS
  // ═══════════════════════════════════════════════════════════════════════

  // ═══════════════════════════════════════════════════════════════════════
  // FLOW DETAIL SIDEBAR WIRING
  // Populate the sidebar with live overlay data computed above
  // ═══════════════════════════════════════════════════════════════════════
  (function updateFlowDetailSidebar(){
    // Only update if the Flow Detail widget is visible (not hidden by context)
    const fdWidget = document.getElementById('wFlowDetail');
    if(!fdWidget || fdWidget.classList.contains('hidden-ctx')) return;

    // --- 1. Flow Summary section ---
    const totalBuy = cells.reduce((s, c) => s + c.buy_vol, 0);
    const totalSell = cells.reduce((s, c) => s + c.sell_vol, 0);
    const totalVol = totalBuy + totalSell;
    const totalDelta = runningDeltaTotal;
    const aggBuyPct = totalVol > 0 ? ((totalBuy / totalVol) * 100).toFixed(1) : '--';

    const fdDelta = document.getElementById('fdDelta');
    if(fdDelta){
      fdDelta.textContent = formatDelta(totalDelta);
      fdDelta.style.color = totalDelta >= 0 ? 'var(--grn)' : 'var(--red)';
    }

    const fdCvdTrend = document.getElementById('fdCvdTrend');
    if(fdCvdTrend && cumulativeDelta.length >= 2){
      const cvdStart = cumulativeDelta[Math.floor(cumulativeDelta.length * 0.7)] || 0;
      const cvdEnd = cumulativeDelta[cumulativeDelta.length - 1] || 0;
      const cvdDiff = cvdEnd - cvdStart;
      // Require meaningful CVD change (at least 0.5% of total volume) to avoid noise
      const cvdThreshold = totalVol * 0.005;
      const cvdDir = cvdDiff > cvdThreshold ? 'Rising' : cvdDiff < -cvdThreshold ? 'Falling' : 'Flat';
      fdCvdTrend.textContent = cvdDir;
      fdCvdTrend.style.color = cvdDir === 'Rising' ? 'var(--grn)' : cvdDir === 'Falling' ? 'var(--red)' : 'var(--mut)';
    }

    const fdDivergence = document.getElementById('fdDivergence');
    if(fdDivergence){
      if(recentPrices && recentPrices.length >= 5 && recentCVD && recentCVD.length >= 5){
        const ps = recentPrices[recentPrices.length - 1] - recentPrices[0];
        const cs = recentCVD[recentCVD.length - 1] - recentCVD[0];
        // Require meaningful moves: price >= $0.05 and CVD >= 1% of total volume
        const priceSigThreshold = 0.05;
        const cvdSigThreshold = totalVol * 0.01;
        if(Math.abs(ps) >= priceSigThreshold && Math.abs(cs) >= cvdSigThreshold){
          if(ps > 0 && cs < 0){ fdDivergence.textContent = 'BEAR DIV'; fdDivergence.style.color = 'var(--red)'; }
          else if(ps < 0 && cs > 0){ fdDivergence.textContent = 'BULL DIV'; fdDivergence.style.color = 'var(--grn)'; }
          else { fdDivergence.textContent = 'None'; fdDivergence.style.color = 'var(--mut)'; }
        } else { fdDivergence.textContent = 'None'; fdDivergence.style.color = 'var(--mut)'; }
      } else { fdDivergence.textContent = 'None'; fdDivergence.style.color = 'var(--mut)'; }
    }

    // Agg Buy % — now shows volume context alongside percentage
    const fdAggBuy = document.getElementById('fdAggBuy');
    if(fdAggBuy){
      if(aggBuyPct !== '--'){
        const pct = parseFloat(aggBuyPct);
        fdAggBuy.textContent = aggBuyPct + '% (' + formatVol(totalVol) + ')';
        fdAggBuy.style.color = pct > 55 ? 'var(--grn)' : pct < 45 ? 'var(--red)' : 'var(--mut)';
      } else {
        fdAggBuy.textContent = '--';
      }
    }

    // Total Volume (replaces redundant "Large Trades" count)
    const fdLargeTrades = document.getElementById('fdLargeTrades');
    if(fdLargeTrades){
      fdLargeTrades.textContent = formatVol(totalBuy) + ' / ' + formatVol(totalSell);
      fdLargeTrades.style.color = totalBuy > totalSell ? 'var(--grn)' : totalSell > totalBuy ? 'var(--red)' : 'var(--mut)';
    }

    // --- 2. Large Prints feed (element-pooled — reuses DOM nodes instead of destroying/rebuilding) ---
    const lgFeed = document.getElementById('lgPrintFeed');
    const lgEmpty = document.getElementById('lgPrintEmpty');
    if(lgFeed){
      if(!lgFeed._pool) lgFeed._pool = [];
      const recentLg = largePrints.length > 0 ? largePrints.slice(-8).reverse() : [];
      if(lgEmpty) lgEmpty.style.display = recentLg.length > 0 ? 'none' : '';
      // Ensure pool has enough elements
      while(lgFeed._pool.length < recentLg.length){
        const el = document.createElement('div');
        el.className = 'lg-entry';
        el.style.cssText = 'display:flex;justify-content:space-between;font-size:9px;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.02)';
        // Pre-create child spans (4 columns: time, side, volume, price)
        for(let s = 0; s < 4; s++) el.appendChild(document.createElement('span'));
        lgFeed.appendChild(el);
        lgFeed._pool.push(el);
      }
      for(let i = 0; i < lgFeed._pool.length; i++){
        const el = lgFeed._pool[i];
        if(i < recentLg.length){
          el.style.display = '';
          const c = recentLg[i].c;
          const isBuy = c.delta >= 0;
          const spans = el.children;
          spans[0].textContent = c._timeStr || (c._timeStr = new Date(c.time).toLocaleTimeString('en-US',{hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'}));
          spans[0].style.color = 'var(--mut)';
          spans[1].textContent = isBuy ? 'BUY' : 'SELL';
          spans[1].style.color = isBuy ? 'var(--grn)' : 'var(--red)';
          spans[2].textContent = formatVol(c.total_vol);
          spans[2].style.color = T.warning; spans[2].style.fontWeight = '600';
          spans[3].textContent = '@' + c.price.toFixed(2);
          spans[3].style.color = 'var(--txt)';
        } else {
          el.style.display = 'none';
        }
      }
    }

    // --- 3. Absorption zone (element-pooled) ---
    // Absorption = high volume at a price level that acts as a wall (price rejected)
    // Requires: volume significantly above neighbors AND balanced buy/sell (both sides active)
    const absFeed = document.getElementById('absorbFeed');
    const absEmpty = document.getElementById('absorbEmpty');
    if(absFeed){
      if(!absFeed._pool) absFeed._pool = [];
      const absData = [];
      if(vol20thPercentile > 0){
        for(let p = firstPriceTick; p <= yMax; p += labelStep){
          const pKey = p.toFixed(2);
          const vol = ladderStepProfile[pKey];
          if(!vol) continue;
          const totalV = vol.buy + vol.sell;
          if(totalV < vol20thPercentile * 1.5) continue; // Must be well above average
          const nextVol = ladderStepProfile[(p + labelStep).toFixed(2)] || {buy:0, sell:0};
          const prevVol = ladderStepProfile[(p - labelStep).toFixed(2)] || {buy:0, sell:0};
          const neighborVol = Math.max(nextVol.buy + nextVol.sell, prevVol.buy + prevVol.sell);
          const absRatio = totalV / Math.max(neighborVol, 1);
          // True absorption: volume wall (2.5x+) with both sides present (not one-sided)
          const minSide = Math.min(vol.buy, vol.sell);
          const buySellBalance = minSide / Math.max(vol.buy, vol.sell, 1);
          if(absRatio >= 2.5 && buySellBalance >= 0.2){
            const dominant = vol.buy > vol.sell ? 'BID' : 'ASK';
            absData.push({price: parseFloat(pKey), totalV, ratio: absRatio, dominant, buy: vol.buy, sell: vol.sell});
          }
        }
      }
      // Sort by strength (ratio * volume), keep top 3
      absData.sort((a, b) => (b.ratio * b.totalV) - (a.ratio * a.totalV));
      const absSlice = absData.slice(0, 3);
      while(absFeed._pool.length < absSlice.length){
        const el = document.createElement('div');
        el.className = 'abs-entry';
        el.style.cssText = 'display:flex;justify-content:space-between;align-items:center;font-size:9px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.03)';
        for(let s = 0; s < 4; s++) el.appendChild(document.createElement('span'));
        absFeed.appendChild(el);
        absFeed._pool.push(el);
      }
      for(let i = 0; i < absFeed._pool.length; i++){
        const el = absFeed._pool[i];
        if(i < absSlice.length){
          el.style.display = '';
          const d = absSlice[i], spans = el.children;
          // Show: dominant side (BID/ASK absorbing), price, volume, strength
          const domColor = d.dominant === 'BID' ? 'var(--grn)' : 'var(--red)';
          spans[0].textContent = d.dominant + ' WALL'; spans[0].style.color = domColor; spans[0].style.fontWeight = '600';
          spans[1].textContent = '@' + d.price.toFixed(2); spans[1].style.color = 'var(--txt)';
          spans[2].textContent = formatVol(d.totalV); spans[2].style.color = 'var(--mut)';
          spans[3].textContent = d.ratio.toFixed(1) + '×'; spans[3].style.color = 'var(--cyan)'; spans[3].style.fontWeight = '600';
        } else {
          el.style.display = 'none';
        }
      }
      if(absEmpty) absEmpty.style.display = absSlice.length > 0 ? 'none' : '';
    }

    // --- 4. Imbalance alerts (element-pooled, deduplicated) ---
    const imbFeed = document.getElementById('imbFeed');
    const imbEmpty = document.getElementById('imbEmpty');
    if(imbFeed){
      if(!imbFeed._pool) imbFeed._pool = [];
      // Compute imbalance data — tighter thresholds to reduce noise
      const imbData = [];
      const ladderKeys = Object.keys(ladderStepProfile);
      for(let k = 0; k < ladderKeys.length; k++){
        const price = ladderKeys[k];
        const v = ladderStepProfile[price];
        const total = v.buy + v.sell;
        if(total <= 500) continue; // Minimum 500 contracts to be meaningful
        const ratio = v.buy > v.sell ? v.buy / Math.max(v.sell, 1) : v.sell / Math.max(v.buy, 1);
        if(ratio >= 2.5) imbData.push({price: parseFloat(price), buy: v.buy, sell: v.sell, total, ratio});
      }
      // Sort by imbalance strength (ratio * volume) descending
      imbData.sort((a, b) => (b.ratio * b.total) - (a.ratio * a.total));
      // Keep only top 4 most significant imbalances
      const imbSlice = imbData.slice(0, 4);

      while(imbFeed._pool.length < imbSlice.length){
        const el = document.createElement('div');
        el.className = 'imb-entry';
        el.style.cssText = 'display:flex;justify-content:space-between;font-size:9px;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.02)';
        for(let s = 0; s < 3; s++) el.appendChild(document.createElement('span'));
        imbFeed.appendChild(el);
        imbFeed._pool.push(el);
      }
      for(let i = 0; i < imbFeed._pool.length; i++){
        const el = imbFeed._pool[i];
        if(i < imbSlice.length){
          el.style.display = '';
          const lv = imbSlice[i], spans = el.children;
          const isBid = lv.buy > lv.sell;
          spans[0].textContent = (isBid ? 'BID ' : 'ASK ') + lv.ratio.toFixed(1) + '×';
          spans[0].style.color = isBid ? 'var(--grn)' : 'var(--red)'; spans[0].style.fontWeight = '600';
          spans[1].textContent = '@' + lv.price.toFixed(2); spans[1].style.color = 'var(--txt)';
          spans[2].textContent = formatVol(lv.total); spans[2].style.color = 'var(--mut)';
        } else {
          el.style.display = 'none';
        }
      }
      if(imbEmpty) imbEmpty.style.display = imbSlice.length > 0 ? 'none' : '';
    }

    // --- 5. Mini volume profile with visual bars ---
    const fpGrid = document.getElementById('fpMiniGrid');
    if(fpGrid && cells.length > 0){
      const priceTick = liveFlow.priceTick || 0.05;
      const vpProfile = {};
      let vpMaxVol = 1, vpPocPrice = null, vpPocVol = 0;
      cells.forEach(c => {
        const binP = (Math.round(c.price / priceTick) * priceTick).toFixed(2);
        if(!vpProfile[binP]) vpProfile[binP] = {buy:0, sell:0, total:0};
        vpProfile[binP].buy += c.buy_vol;
        vpProfile[binP].sell += c.sell_vol;
        vpProfile[binP].total += c.total_vol;
      });
      Object.entries(vpProfile).forEach(([p, v]) => {
        vpMaxVol = Math.max(vpMaxVol, v.total);
        if(v.total > vpPocVol){ vpPocVol = v.total; vpPocPrice = p; }
      });
      const vpEntries = Object.entries(vpProfile)
        .map(([p, v]) => ({price: parseFloat(p), ...v}))
        .sort((a, b) => b.price - a.price)
        .slice(0, 10);

      let html = '';
      vpEntries.forEach(e => {
        const buyPct = Math.round((e.buy / vpMaxVol) * 100);
        const sellPct = Math.round((e.sell / vpMaxVol) * 100);
        const isPOC = e.price.toFixed(2) === vpPocPrice;
        const delta = e.buy - e.sell;
        const deltaColor = delta >= 0 ? 'var(--grn)' : 'var(--red)';
        html += `<div style="display:grid;grid-template-columns:50px 1fr 1fr 36px;gap:2px;align-items:center;font-size:8px;padding:1px 0;${isPOC ? 'background:rgba(255,179,0,0.06);border-left:2px solid rgba(255,179,0,0.5);padding-left:2px' : ''}">`;
        html += `<span style="color:${isPOC ? 'var(--warning)' : 'var(--txt)'};font-weight:${isPOC ? '700' : '400'};text-align:right;font-size:7px">${e.price.toFixed(2)}</span>`;
        // Sell bar (grows right)
        html += `<div style="position:relative;height:10px;display:flex;align-items:center">`;
        html += `<div style="position:absolute;right:0;height:8px;width:${sellPct}%;background:rgba(239,83,80,${0.3 + sellPct/100*0.5});border-radius:1px"></div>`;
        html += `<span style="position:relative;color:var(--red);font-size:7px;padding-left:2px">${e.sell > 0 ? e.sell.toLocaleString() : ''}</span></div>`;
        // Buy bar (grows right)
        html += `<div style="position:relative;height:10px;display:flex;align-items:center">`;
        html += `<div style="position:absolute;left:0;height:8px;width:${buyPct}%;background:rgba(38,166,154,${0.3 + buyPct/100*0.5});border-radius:1px"></div>`;
        html += `<span style="position:relative;color:var(--grn);font-size:7px;padding-left:2px">${e.buy > 0 ? e.buy.toLocaleString() : ''}</span></div>`;
        // Delta
        html += `<span style="text-align:right;color:${deltaColor};font-size:7px">${delta >= 0 ? '+' : ''}${delta}</span>`;
        html += '</div>';
      });
      fpGrid.innerHTML = html;
    }

    // --- 6. Stacked imbalance detection for sidebar ---
    const imbFeedEl = document.getElementById('imbFeed');
    if(imbFeedEl){
      // CLEAR old stacked entries first to prevent accumulation spam
      imbFeedEl.querySelectorAll('.imb-stack-entry').forEach(el => el.remove());

      // Check for stacked imbalances (3+ consecutive levels with buy/sell ratio >= 3:1)
      const imbLevels = Object.entries(ladderStepProfile)
        .map(([price, v]) => ({price: parseFloat(price), buy: v.buy, sell: v.sell}))
        .sort((a, b) => b.price - a.price);

      const stacks = [];
      let runLen = 0, runType = '', runStart = -1;
      for(let i = 0; i < imbLevels.length; i++){
        const lv = imbLevels[i];
        const buyImb = lv.sell > 0 && lv.buy / lv.sell >= 3;
        const sellImb = lv.buy > 0 && lv.sell / lv.buy >= 3;
        const curType = buyImb ? 'BUY' : sellImb ? 'SELL' : '';

        if(curType && curType === runType){
          runLen++;
        } else {
          if(runLen >= 3 && runType){
            stacks.push({type: runType, start: runStart, len: runLen});
          }
          runType = curType; runLen = curType ? 1 : 0; runStart = i;
        }
      }
      if(runLen >= 3 && runType){
        stacks.push({type: runType, start: runStart, len: runLen});
      }

      // Deduplicate: keep only the strongest stack per type (max levels)
      const bestByType = {};
      stacks.forEach(s => {
        if(!bestByType[s.type] || s.len > bestByType[s.type].len) bestByType[s.type] = s;
      });

      // Render stacked imbalances (max 2 — one buy, one sell)
      const firstEntry = imbFeedEl.querySelector('.imb-entry');
      Object.values(bestByType).forEach(s => {
        const color = s.type === 'BUY' ? 'var(--grn)' : 'var(--red)';
        const variant = s.type === 'BUY' ? 'green' : 'red';
        const topP = imbLevels[s.start].price.toFixed(2);
        const botP = imbLevels[s.start + s.len - 1].price.toFixed(2);
        const el = document.createElement('div');
        el.className = 'imb-stack-entry';
        el.style.cssText = 'display:flex;justify-content:space-between;align-items:center;font-size:9px;padding:3px 0;border-bottom:1px solid rgba(255,255,255,0.04)';
        el.innerHTML = `${UI.badge('STACK ' + s.type, variant)}<span style="color:var(--txt);font-weight:500">${topP}–${botP}</span><span style="color:${color};font-weight:600">${s.len} lvls</span>`;
        if(firstEntry) imbFeedEl.insertBefore(el, firstEntry);
        else imbFeedEl.appendChild(el);
      });
    }
  })();

  // Store points for hover detection
  entry._points = points;
  entry._dpr = dpr;

  // Attach hover listener once per canvas
  if(!entry._hoverBound){
    entry._hoverBound = true;
    const tooltip = document.createElement('div');
    tooltip.className = 'flow-tooltip';
    tooltip.style.cssText = `display:none;position:fixed;z-index:var(--z-tooltip);padding:var(--space-sm) var(--space-lg);background:rgba(15,15,25,0.94);border:1px solid var(--border-strong);border-radius:var(--radius-md);font-size:var(--font-base);color:var(--text-primary);pointer-events:none;white-space:nowrap;font-family:var(--font-mono);box-shadow:var(--shadow-md);`;
    document.body.appendChild(tooltip);

    entry.canvas.addEventListener('mousemove', (e) => {
      const pts = entry._points;
      if(!pts || !pts.length){ tooltip.style.display = 'none'; return; }
      const rect = entry.canvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) * entry._dpr;
      const my = (e.clientY - rect.top) * entry._dpr;
      let closest = null, closestDist = Infinity;
      for(const p of pts){
        const dx = p.x - mx, dy = p.y - my;
        const dist = Math.sqrt(dx*dx + dy*dy);
        if(dist < p.r + 8 * entry._dpr && dist < closestDist){
          closest = p; closestDist = dist;
        }
      }
      if(closest){
        const c = closest.c;
        const d = new Date(c.time);
        const ts = d.toLocaleTimeString('en-US',{timeZone:'America/New_York',hour12:false,hour:'2-digit',minute:'2-digit',second:'2-digit'});
        const delta = c.delta >= 0 ? `<span style="color:var(--positive)">+${c.delta.toLocaleString()}</span>` : `<span style="color:var(--negative)">${c.delta.toLocaleString()}</span>`;
        // Volume size label based on relative position in data
        const volRatio = closest.r / maxR;
        let tierName = volRatio > 0.8 ? 'HUGE' : volRatio > 0.6 ? 'LARGE' : volRatio > 0.35 ? 'medium' : volRatio > 0.15 ? 'small' : 'tiny';
        const tierColor = tierName === 'HUGE' ? T.negative : tierName === 'LARGE' ? T.warning : T.dim;
        tooltip.innerHTML = `<b>$${c.price.toFixed(2)}</b> @ ${ts}<br>Vol: ${c.total_vol.toLocaleString()} <span style="color:${tierColor}">[${tierName}]</span> &nbsp; Delta: ${delta}<br>Buy: ${c.buy_vol.toLocaleString()} &nbsp; Sell: ${c.sell_vol.toLocaleString()}`;
        tooltip.style.display = 'block';
        tooltip.style.left = (e.clientX + 14) + 'px';
        tooltip.style.top = (e.clientY - 10) + 'px';
        entry.canvas.style.cursor = 'crosshair';
      } else {
        tooltip.style.display = 'none';
        entry.canvas.style.cursor = 'default';
      }
    });
    entry.canvas.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
  }

  // Price ladder is now drawn directly on canvas above (no separate Plotly profile)
}

// (Volume profile is now integrated into the canvas-drawn price ladder — no separate Plotly chart)

// ══════════════════════════════════════════════════════════════════════════
// REAL-TIME FLOW STREAMING — accumulate ticks into live flow data
// ══════════════════════════════════════════════════════════════════════════
var liveFlow = {
  ticks: [],          // raw ticks: {price, size, side, ts}
  maxTicks: 50000,    // cap to prevent memory bloat
  aggSeconds: 0.25,    // aggregation interval — 250ms for smooth flowing trail
  lastRender: 0,
  renderInterval: 100, // ms between re-renders (~10fps for smooth streaming)
  prevPrice: 0,
  prevSide: 'neutral',
  visibleWindowMs: 2 * 60 * 1000,  // 2-minute sliding window — best for flowing trail
  priceTick: 0.05,    // Y-axis grid step ($0.05 default for SPY — tighter ladder)
};

function setAgg(seconds){
  liveFlow.aggSeconds = seconds;
  document.querySelectorAll('[data-agg]').forEach(b => b.classList.toggle('active', parseFloat(b.dataset.agg)===seconds));

  // Auto-adjust visible window — sub-second aggs need shorter windows to avoid overload
  const autoWindows = {0.005: 10, 0.05: 30, 0.5: 60, 1: 120, 5: 240, 15: 600, 60: 1800};
  const autoWin = autoWindows[seconds] || (seconds < 1 ? 30 : 600);
  liveFlow.visibleWindowMs = autoWin * 1000;
  document.querySelectorAll('[data-win]').forEach(b => b.classList.toggle('active', parseInt(b.dataset.win)===autoWin));

  // For sub-second aggs, increase render frequency for smoother streaming
  liveFlow.renderInterval = seconds <= 0.25 ? 80 : seconds < 1 ? 100 : 200;

  // Re-render — try live ticks first, fall back to historical cloud data
  if(S.activeTab === 'flow' || S.activeTab === 'combined'){
    if(liveFlow.ticks.length){
      renderLiveFlow();
    } else if(S.flowData){
      if(S.activeTab === 'combined') renderFlowChart('flowWrapCombined', S.flowData, false);
      if(S.activeTab === 'flow') renderFlowChart('flowWrapFull', S.flowData, true);
    }
  }
}

function setFlowWindow(seconds){
  liveFlow.visibleWindowMs = seconds * 1000;
  document.querySelectorAll('[data-win]').forEach(b => b.classList.toggle('active', parseInt(b.dataset.win)===seconds));
  // Re-render — live ticks first, then historical
  if(liveFlow.ticks.length){
    renderLiveFlow();
  } else if(S.flowData){
    if(S.activeTab === 'combined') renderFlowChart('flowWrapCombined', S.flowData, false);
    if(S.activeTab === 'flow') renderFlowChart('flowWrapFull', S.flowData, true);
  }
}

function setPriceTick(step){
  liveFlow.priceTick = step;
  document.querySelectorAll('[data-ptick]').forEach(b => b.classList.toggle('active', parseFloat(b.dataset.ptick)===step));
  if(liveFlow.ticks.length){
    renderLiveFlow();
  } else if(S.flowData){
    if(S.activeTab === 'combined') renderFlowChart('flowWrapCombined', S.flowData, false);
    if(S.activeTab === 'flow') renderFlowChart('flowWrapFull', S.flowData, true);
  }
}

function handleFlowTick(price, size, side, tickTimestamp){
  if(!price || price <= 0) return;

  // Tick-rule classification if side not provided
  if(!side || side === 'unknown'){
    if(price > liveFlow.prevPrice) side = 'buy';
    else if(price < liveFlow.prevPrice) side = 'sell';
    else side = liveFlow.prevSide;
  }
  liveFlow.prevPrice = price;
  liveFlow.prevSide = side;

  // Use the tick's original exchange timestamp, not when we received it
  const ts = tickTimestamp || Date.now();

  liveFlow.ticks.push({
    price: Math.round(price * 100) / 100,
    size: size || 1,
    side,
    ts,
  });

  // Real-time candle update (works on any intraday TF)
  updateRealtimeCandle(price, size || 1);

  // Cap memory
  if(liveFlow.ticks.length > liveFlow.maxTicks){
    liveFlow.ticks = liveFlow.ticks.slice(-Math.floor(liveFlow.maxTicks * 0.8));
  }

  // Data-driven render is no longer needed here — the continuous animation loop handles it.
  // Just mark that new data arrived so the loop knows to redraw.
  liveFlow._dirty = true;
}

// ── Continuous animation loop ──
// Redraws the flow chart at a steady frame rate regardless of trade arrival frequency.
// Performance: uses setTimeout at the configured interval instead of RAF polling at 60fps.
// RAF was wasting ~50/60 frames doing nothing but a timestamp check.
var _flowAnimRunning = false;
var _flowAnimTimer = null;
function startFlowAnimLoop(){
  if(_flowAnimRunning) return;
  _flowAnimRunning = true;
  function tick(){
    if(!_flowAnimRunning){ _flowAnimTimer = null; return; }
    if(liveFlow.ticks.length && (S.activeTab === 'flow' || S.activeTab === 'combined')){
      renderLiveFlow();
    }
    _flowAnimTimer = setTimeout(tick, liveFlow.renderInterval);
  }
  _flowAnimTimer = setTimeout(tick, liveFlow.renderInterval);
}
function stopFlowAnimLoop(){
  _flowAnimRunning = false;
  if(_flowAnimTimer){ clearTimeout(_flowAnimTimer); _flowAnimTimer = null; }
}
// Start animation loop as soon as first tick arrives or on page load
startFlowAnimLoop();

// Store historical cloud data from REST for merging with live ticks
let historicalClouds = null;

function renderLiveFlow(){
  if(!liveFlow.ticks.length) return;

  const aggMs = liveFlow.aggSeconds * 1000;

  // Aggregate live ticks into ONE bubble per time bucket at VWAP price
  // (Prismadic-style: single flowing point per second, not per unique price)
  const buckets = {};

  liveFlow.ticks.forEach(t => {
    const barStart = Math.floor(t.ts / aggMs) * aggMs;
    if(!buckets[barStart]) buckets[barStart] = {time: barStart, priceSum:0, volSum:0, buy:0, sell:0};
    buckets[barStart].priceSum += t.price * t.size;
    buckets[barStart].volSum += t.size;
    buckets[barStart][t.side] += t.size;
  });

  const liveCells = Object.values(buckets).map(b => {
    const vwap = b.volSum > 0 ? b.priceSum / b.volSum : 0;
    const delta = b.buy - b.sell;
    return {
      time: new Date(b.time).toISOString(),
      price: Math.round(vwap * 100) / 100,
      total_vol: b.volSum,
      buy_vol: b.buy,
      sell_vol: b.sell,
      delta,
      delta_ratio: b.volSum > 0 ? delta / b.volSum : 0,
      pct_of_bar: 100,
    };
  });

  // Merge: historical clouds (from REST bars) + live tick clouds
  // Historical covers 9:30 - now (from bars), live overlays the most recent ticks
  let mergedCells = liveCells;
  let mergedSummary = [];
  if(historicalClouds && historicalClouds.clouds && historicalClouds.clouds.length){
    const earliestLiveTs = liveFlow.ticks.length ? new Date(Math.min(...liveFlow.ticks.map(t=>t.ts))).toISOString() : null;
    if(earliestLiveTs){
      // Only include historical bars within 1.5x the visible window (avoids lone disconnected bars)
      const cutoffMs = Date.now() - liveFlow.visibleWindowMs * 1.5;
      const cutoffTs = new Date(cutoffMs).toISOString();
      const olderHistorical = historicalClouds.clouds.filter(c => c.time < earliestLiveTs && c.time >= cutoffTs);
      mergedCells = [...olderHistorical, ...liveCells];
    } else {
      mergedCells = [...historicalClouds.clouds, ...liveCells];
    }
    mergedSummary = historicalClouds.bars_summary || [];
  }

  const mergedData = {
    clouds: mergedCells,
    bars_summary: mergedSummary,
    meta: {
      trade_count: liveFlow.ticks.length + (historicalClouds?.meta?.trade_count || 0),
    },
  };
  S.flowData = mergedData;

  // Update stats
  let totalBuy = 0, totalSell = 0;
  mergedCells.forEach(c => { totalBuy += c.buy_vol; totalSell += c.sell_vol; });
  document.getElementById('sTradeCount').textContent = mergedData.meta.trade_count.toLocaleString();
  document.getElementById('sBuyVol').textContent = formatVol(totalBuy);
  document.getElementById('sSellVol').textContent = formatVol(totalSell);
  const delta = totalBuy - totalSell;
  const deltaEl = document.getElementById('sDelta');
  deltaEl.textContent = (delta >= 0 ? '+' : '') + formatVol(delta);
  deltaEl.style.color = delta >= 0 ? 'var(--grn)' : 'var(--red)';
  document.getElementById('mDelta').textContent = (delta >= 0 ? '+' : '') + formatVol(delta);
  document.getElementById('mDelta').style.color = delta >= 0 ? 'var(--grn)' : 'var(--red)';

  if(S.activeTab === 'combined'){
    renderFlowChart('flowWrapCombined', mergedData, false);
  }
  if(S.activeTab === 'flow'){
    renderFlowChart('flowWrapFull', mergedData, true);
  }
}

function formatVol(n){
  if(n === undefined || n === null || isNaN(n) || n === 0) return '·';
  const abs = Math.abs(n), sign = n < 0 ? '-' : '';
  if(abs >= 1e6) return sign + (abs/1e6).toFixed(1) + 'M';
  if(abs >= 1e3) return sign + (abs/1e3).toFixed(1) + 'K';
  return sign + String(Math.round(abs));
}
function formatDelta(n){
  if(n === undefined || n === null || isNaN(n)) return '·';
  const abs = Math.abs(n), sign = n >= 0 ? '+' : '-';
  if(abs >= 1e6) return sign + (abs/1e6).toFixed(1) + 'M';
  if(abs >= 1e3) return sign + (abs/1e3).toFixed(1) + 'K';
  return (n >= 0 ? '+' : '') + Math.round(n);
}

