# PixiJS v8 Migration Plan — Order Flow Renderer

## Executive Summary

Migrate the order flow chart renderer from Canvas 2D to PixiJS v8 (WebGL) to achieve GPU-accelerated bubble rendering, eliminate frame drops during high-volume market conditions, and produce a visual quality closer to professional platforms like Prismadic/Bookmap.

**Estimated effort:** 3-4 focused sessions
**Risk level:** Medium (fallback to Canvas 2D preserved)
**Performance target:** 60fps with 2,000+ bubbles (current limit: ~500 before jank)

---

## Current Architecture (What We Have)

```
flow-dashboard.html (single file, ~3000 lines)
├── CSS styles (lines 1-180)
├── HTML layout (lines 180-420)
├── Lightweight Charts integration (lines 420-930)
├── Canvas 2D renderer: renderFlowChart() (lines 994-1622)
│   ├── Layout calculation (margins, zones, coordinate mappers)
│   ├── Background + separators (5 fillRect)
│   ├── Grid lines (150+ strokes)
│   ├── Price labels LEFT (30+ fillText)
│   ├── Price ladder RIGHT with volume bars (60+ fillRect)
│   ├── Rotated time labels (120+ fillText with save/translate/rotate/restore)
│   ├── Volume bars BOTTOM with clipping (200+ fillRect)
│   ├── Indicators (imbalance arrows, divergence, absorption)
│   ├── Flow trail shadow (1 polyline stroke)
│   └── Bubbles (200+ × [createRadialGradient + 3 colorStops + arc + fill + stroke])
├── Live data pipeline: renderLiveFlow() (lines 1729-1807)
├── Tick handler: handleFlowTick() (lines 1720-1728)
└── Toolbar controls: setAgg/setFlowWindow/setPriceTick (lines 1641-1686)
```

**Current bottleneck:** ~1,800 draw calls per frame, all CPU-bound. The radial gradient per bubble is the killer — each `createRadialGradient()` + 3 `addColorStop()` + `arc()` + `fill()` is expensive. At 500+ bubbles × 5-20 renders/sec = 2,500-10,000 gradient operations/second.

---

## Target Architecture (What We're Building)

```
flow-dashboard.html
├── CSS + HTML + Lightweight Charts (UNCHANGED)
├── PixiJS v8 loaded from CDN (new <script> tag)
├── FlowRenderer class (NEW — replaces renderFlowChart)
│   ├── pixi.Application (WebGL context)
│   ├── Layer: gridLayer (Graphics — static grid lines)
│   ├── Layer: labelLayer (BitmapText — price/time labels)
│   ├── Layer: volumeBarLayer (Graphics — bottom volume bars, masked)
│   ├── Layer: ladderLayer (Graphics — right-side volume profile)
│   ├── Layer: trailLayer (Graphics — flow trail shadow)
│   ├── Layer: bubbleLayer (Container or ParticleContainer — main bubbles)
│   ├── Layer: indicatorLayer (Graphics — arrows, divergence, absorption)
│   └── Layer: tooltipLayer (DOM element — hover tooltip, unchanged)
├── Live data pipeline: renderLiveFlow() (MODIFIED — calls FlowRenderer.update())
├── Tick handler: handleFlowTick() (UNCHANGED)
└── Toolbar controls (MODIFIED — calls FlowRenderer.reconfigure())
```

---

## Migration Strategy: Incremental, Not Big-Bang

### Why Incremental?
- We can test each component in isolation
- Canvas 2D fallback stays working throughout
- If PixiJS has issues on certain hardware, we can fall back
- Each phase produces a working dashboard

### Phase Breakdown

#### Phase 1: Foundation (Session 1)
**Goal:** PixiJS Application running alongside Canvas 2D, rendering just the bubbles.

1. Add PixiJS v8 CDN script tag to HTML `<head>`
2. Create `FlowRenderer` class with `init(containerId)` method
3. Create PixiJS `Application` with WebGL renderer, sized to container
4. Pre-render 5 gradient circle textures (tiny/small/medium/large/huge) using `Graphics` + `FillGradient` → `renderTexture`
5. Create `bubbleLayer` as `Container`
6. On each render call, clear bubbleLayer, create `Sprite` per bubble using pre-baked gradient textures
7. Apply `tint` for delta color (red/gray/green), `scale` for volume-based size, `alpha` for age fade
8. **Canvas 2D still draws everything else** (grids, labels, bars, indicators)
9. **PixiJS canvas overlays on top** with `position:absolute` and transparent background

**Deliverable:** Bubbles rendered by PixiJS GPU, everything else still Canvas 2D.
**Validation:** Compare visual output to current. Measure FPS with 500+ bubbles.

#### Phase 2: Static Elements (Session 2)
**Goal:** Move grids, labels, and backgrounds to PixiJS.

1. Create `gridLayer` using single `Graphics` object with `pixelLine=true`
   - All horizontal grid lines in one draw call
   - All vertical grid lines in one draw call
2. Create `labelLayer` using `BitmapText` for all text
   - Generate bitmap font from "SF Mono" at initialization
   - Price labels (left axis): 30 BitmapText objects, positioned and styled
   - Time labels (bottom axis): 120 BitmapText objects with `rotation` property (no save/restore needed)
   - Volume scale labels: 5 BitmapText objects
3. Create background `Graphics` for zone fills and separators
4. **Remove Canvas 2D grid/label/background drawing code**

**Deliverable:** All static elements on PixiJS. Only volume bars, ladder, and indicators remain on Canvas 2D.
**Validation:** Grid lines pixel-perfect. Text crisp. No visual regression.

#### Phase 3: Volume Bars + Ladder (Session 3)
**Goal:** Move all remaining rectangular elements to PixiJS.

1. Create `volumeBarLayer` inside a masked `Container`
   - Mask = `Graphics.rect()` → scissor masking (GPU-optimal for rectangles)
   - Individual `Graphics.rect().fill()` per bar, or single Graphics with all rects batched
2. Create `ladderLayer` for right-side volume profile
   - Price labels: BitmapText
   - Volume bars: Graphics rects growing rightward
   - Imbalance arrows: Graphics triangles
3. Move indicator drawing (divergence label, absorption markers) to `indicatorLayer`
4. **Remove Canvas 2D entirely** — delete the old `_flowCanvases` cache and `_ensureCanvas` function
5. Keep tooltip as DOM element (it's position:fixed, works fine with PixiJS)

**Deliverable:** Full PixiJS rendering. Canvas 2D code removed.
**Validation:** All components render correctly. Hover tooltip works. Performance at 60fps.

#### Phase 4: Optimization (Session 4, if needed)
**Goal:** Push performance ceiling for high-volume scenarios.

1. If bubble count routinely exceeds 1,000: switch from `Container` to `ParticleContainer`
   - Pre-bake 15 gradient textures (5 sizes × 3 color families: red, gray, green)
   - Use dynamic position + scale + tint
2. Implement dirty-flag rendering: only re-render layers that changed
   - `gridLayer` and `labelLayer` only redraw on price range change or window resize
   - `bubbleLayer` redraws every tick
   - `volumeBarLayer` redraws every tick
3. Add `requestAnimationFrame` loop instead of interval-based rendering
4. Profile with Chrome DevTools → GPU tab to verify WebGL batching

---

## Technical Decisions

### Decision 1: Pre-baked Textures vs. Live Gradients

**Choice: Pre-baked textures**

Rationale: Creating a `FillGradient` per bubble per frame defeats the purpose of GPU acceleration. Instead, render 5-15 gradient circles to `RenderTexture` once at startup, then use `Sprite` objects with these textures. Color variation achieved via PixiJS `tint` property (GPU-free color multiplication).

```
Startup:
  For each size tier (tiny, small, medium, large, huge):
    Create Graphics circle with white radial gradient (highlight → white → dark)
    Render to RenderTexture at 2x resolution
    Store as reusable Texture

Per frame:
  For each bubble:
    sprite.texture = sizeTextures[tier]
    sprite.tint = deltaToHexColor(delta_ratio)  // GPU color tinting
    sprite.position.set(x, y)
    sprite.alpha = ageFade
    sprite.scale.set(radiusMultiplier)
```

**Performance gain:** 1 draw call per texture atlas page (batched automatically by PixiJS). 500 bubbles = ~5 draw calls total instead of 500 gradient operations.

### Decision 2: Container vs. ParticleContainer for Bubbles

**Choice: Start with Container, upgrade to ParticleContainer if needed**

- Container supports individual tint, alpha, scale, position per sprite. Adequate for < 1,000 sprites.
- ParticleContainer: 100K+ sprites but more restrictive. Reserve for Phase 4 if needed.
- Our typical bubble count: 120-500 (2min window at 1s agg). Container is sufficient.

### Decision 3: BitmapText vs. Text

**Choice: BitmapText**

- 200+ labels changing every frame → BitmapText uses shared texture atlas
- Regular `Text` would regenerate internal canvas texture on every change — slower
- Monospace font (SF Mono) is ideal for bitmap fonts

### Decision 4: Single Canvas vs. Overlay

**Choice: Single PixiJS canvas replaces Canvas 2D**

- No overlay complexity
- No multiple WebGL context issues
- PixiJS renders everything including backgrounds
- Tooltip remains a DOM element (position:fixed, pointer-events:none)

### Decision 5: Grid Line Strategy

**Choice: Single Graphics object with pixelLine=true**

- All grid lines in one `Graphics` object = one draw call
- `pixelLine = true` ensures crisp 1px lines regardless of DPR
- Redraw only when price range or time window changes (dirty flag)

---

## File Changes

### Modified Files
| File | Change |
|------|--------|
| `dashboard/static/flow-dashboard.html` | Add PixiJS CDN, replace renderFlowChart with FlowRenderer class, keep all data pipeline code |

### New Dependencies
| Dependency | Source | Size |
|-----------|--------|------|
| PixiJS v8.17.1 | `https://cdn.jsdelivr.net/npm/pixi.js@8/dist/pixi.min.js` | ~300KB gzipped |

### Deleted Code (by end of Phase 3)
- `_flowCanvases` object and `_ensureCanvas()` function
- Old `renderFlowChart()` function (replaced by FlowRenderer)
- All `ctx.*` Canvas 2D drawing calls within the flow chart renderer

### Preserved Code (unchanged)
- `handleFlowTick()` — tick ingestion
- `renderLiveFlow()` — data aggregation (modified to call FlowRenderer.update instead of renderFlowChart)
- `setAgg()`, `setFlowWindow()`, `setPriceTick()` — toolbar controls (modified to call FlowRenderer.reconfigure)
- `deltaToColor()` — color mapping (converted to return hex for PixiJS tint)
- All Lightweight Charts code (candlesticks, RSI — separate canvas)
- Tooltip DOM element and hover logic (adapted for PixiJS hit testing)
- WebSocket connection and data pipeline
- All backend Python code

---

## Risk Assessment

### Risk 1: WebGL Not Available
**Probability:** Low (< 2% of modern browsers)
**Impact:** Chart won't render
**Mitigation:** PixiJS has automatic `CanvasRenderer` fallback. If neither works, show error message with "Your browser doesn't support WebGL."

### Risk 2: Visual Regression
**Probability:** Medium (gradient tinting may look slightly different)
**Impact:** Colors/sizes don't match current look
**Mitigation:** Phase 1 overlay approach lets us A/B compare. Git branch for rollback.

### Risk 3: Memory Leak from Texture/Sprite Churn
**Probability:** Medium (creating/destroying sprites every 200ms)
**Impact:** Memory grows over time
**Mitigation:** Object pooling — pre-allocate max sprites, show/hide instead of create/destroy. Explicit `texture.destroy()` cleanup.

### Risk 4: Text Rendering Quality
**Probability:** Low-Medium (BitmapText can look blurry at non-integer scales)
**Impact:** Labels look fuzzy
**Mitigation:** Generate bitmap fonts at 2x DPR resolution. Use `resolution` parameter on Application.

### Risk 5: PixiJS CDN Unavailability
**Probability:** Very Low
**Impact:** Chart doesn't load
**Mitigation:** Fallback to local copy or Canvas 2D renderer.

---

## Rollback Strategy

1. All work done on a git branch (`feature/pixijs-renderer`)
2. Old Canvas 2D code kept commented (not deleted) until Phase 3 is validated
3. Feature flag: `window.USE_PIXIJS = true` — if false, falls back to old renderer
4. At any point, `git checkout main` restores the working Canvas 2D version

---

## Performance Expectations

| Metric | Canvas 2D (Current) | PixiJS v8 (Target) |
|--------|---------------------|---------------------|
| Bubbles at 60fps | ~500 | 5,000+ |
| Draw calls per frame | ~1,800 | ~20-30 |
| Gradient cost | CPU per bubble | GPU tint (free) |
| Grid lines | 150 strokes | 1 draw call |
| Text labels | 200 fillText | 1 texture atlas |
| Frame time (200 bubbles) | 8-12ms | <2ms |
| Frame time (2000 bubbles) | 40-60ms (jank) | <5ms |

---

## Implementation Status

### Phase 1: GPU Bubble Rendering ✅ COMPLETE
- [x] Add PixiJS v8.17.1 CDN script tag
- [x] Create `FlowRenderer` class with async `init()`, sprite pooling, pre-baked textures
- [x] Pre-bake 5 gradient circle textures (tiny/small/medium/large/huge) via Canvas 2D → PIXI.Texture
- [x] Bubble rendering via GPU-tinted sprites (~5 draw calls instead of ~500 gradient ops)
- [x] Pulse ring rendering on PixiJS layer
- [x] Canvas 2D fallback (`_drawBubblesCanvas2D`) for first frame + WebGL-unavailable cases
- [x] `window.USE_PIXIJS` feature flag for instant rollback
- [x] `flowRenderers` map supports multiple containers (combined + fullscreen views)
- [x] `pointer-events:none` on PixiJS canvas preserves tooltip hover on Canvas 2D
- [x] All 103 tests passing

### Phase 2-3: DEFERRED (not needed for performance target)
**Engineering decision:** Phase 1 alone eliminates the bottleneck (gradient operations).
The remaining Canvas 2D operations (~200 fillRect/fillText/stroke) cost ~2-3ms/frame — well within 60fps.
Moving text to PixiJS would actually REGRESS performance (PIXI.Text creates hidden canvases per object).
The hybrid architecture (Canvas 2D for simple shapes/text + PixiJS for GPU-intensive bubbles) is optimal.

- [ ] Phase 2: Move grid lines to PixiJS Graphics (deferred)
- [ ] Phase 2: Move text labels to PixiJS BitmapText (deferred — would regress perf)
- [ ] Phase 3: Move volume bars + ladder to PixiJS (deferred)
- [ ] Phase 3: Remove Canvas 2D code (deferred — kept as fallback)

### Phase 4: Optimization (if needed after profiling)
- [ ] ParticleContainer upgrade (if bubble count routinely exceeds 1,000)
- [ ] Dirty-flag rendering optimization
- [ ] requestAnimationFrame loop
