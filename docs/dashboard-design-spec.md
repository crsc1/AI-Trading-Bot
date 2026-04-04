# SPY/SPX/XSP Options Trading Dashboard — Design Specification v1.0

---

## 1. Overall Design Philosophy & Mood

### Visual Identity: "Dark Precision"

The dashboard follows a **high-density dark terminal aesthetic** inspired by Bloomberg Terminal's information architecture, Bookmap's order flow clarity, and tastytrade's modern approachability — but purpose-built for a single use case: buying calls and puts on SPY, SPX, and XSP using order flow + price action.

**Why dark?** Traders stare at screens 6–8 hours daily. A dark theme (#0A0A12 base) minimizes eye fatigue while letting color-coded data — green buys, red sells, yellow neutrals — punch through without competing with the background. Every pixel of color carries meaning; nothing is decorative.

**Color Palette:**

| Token         | Hex       | Usage                                        |
|---------------|-----------|----------------------------------------------|
| `--bg0`       | `#0A0A12` | Page background, chart area                  |
| `--bg1`       | `#0F0F19` | Panels, header, sidebar                      |
| `--bg2`       | `#151520` | Section headers, elevated surfaces           |
| `--bg3`       | `#1B1B28` | Hover states, active elements                |
| `--border`    | `#22223A` | Dividers, grid lines                         |
| `--text`      | `#D0D0DA` | Primary text                                 |
| `--dim`       | `#6E6E88` | Secondary text, axis labels                  |
| `--muted`     | `#44445A` | Disabled text, faint labels                  |
| `--accent`    | `#5588EE` | Interactive highlights, selection, focus ring |
| `--buy`       | `#26A69A` | Buy pressure, bullish candles, positive delta |
| `--sell`      | `#EF5350` | Sell pressure, bearish candles, negative delta|
| `--neutral`   | `#FFB300` | Balanced flow, warnings, neutral zones       |
| `--buy-deep`  | `#00E676` | Maximum buying intensity (cloud edges)       |
| `--sell-deep` | `#FF1744` | Maximum selling intensity (cloud edges)      |

**Typography:** `SF Mono` → `Menlo` → `Consolas` → `monospace`. Monospace ensures columns align perfectly in option chains and footprint grids. Base size 11px, with 9px for dense data cells and 13–14px for the symbol/price header.

**Spacing Philosophy:** 4px grid system. Padding within cells: 3–6px. Gap between panels: 1px solid border (no gap — panels are flush to maximize data density). Every wasted pixel is a missed data point.

**Design Principles:**
1. **Color = Data.** If it's colored, it means something. Green = buy. Red = sell. Yellow = balanced. Blue = interactive/selected.
2. **Glanceable hierarchy.** The two most important things — current price and order flow imbalance — are visible in under 200ms of scanning.
3. **Contextual density.** Charts show maximum data per pixel; sidebars distill it into actionable summaries.
4. **Zero chrome.** No rounded cards, no drop shadows, no gradients. Flat surfaces, 1px borders, information-forward.

---

## 2. High-Level Dashboard Layout (Desktop-first, 1920×1080 minimum)

### Master Grid: 4-Row × 2-Column

```
┌─────────────────────────────────────────────────────────────────────────┐
│  TOP NAV BAR (40px)                                                     │
│  [SPY ▾] [SPX] [XSP]  │  Exp: [Mar28 ▾]  │  Strikes: ±20  │          │
│  [C/P: Both ▾]  │  Bar: [5m ▾]  │  ● Engine  ● Data  │  $572.34 +0.8%│
├────────────────────────────────────────────────────┬────────────────────┤
│                                                    │                    │
│  ORDER FLOW BUBBLE/CLOUD CHART (55% height)        │  RIGHT SIDEBAR     │
│  X = Time bars, Y = Price levels                   │  (260px fixed)     │
│  Bubbles: size=volume, color=delta                 │                    │
│  Linked crosshair ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │  ┌──────────────┐ │
│                                                    │  │ METRICS       │ │
│                                                    │  │ Delta: +1.2K  │ │
│                                                    │  │ CVD: +45K     │ │
│                                                    │  │ VWAP: 572.18  │ │
│                                                    │  │ P/C Ratio:0.82│ │
├────────────────────────────────────────────────────┤  │ IV: 14.2%     │ │
│                                                    │  │ Max Pain: 570 │ │
│  CANDLESTICK CHART (35% height)                    │  └──────────────┘ │
│  Standard OHLC candles + volume histogram          │  ┌──────────────┐ │
│  EMA 21, SMA 50, Bollinger Bands overlay           │  │ AI SIGNALS    │ │
│  Linked crosshair ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │  │ BUY 575C @3.2│ │
│  RSI sub-panel (60px)                              │  │ conf: 87%     │ │
│                                                    │  │ ────────────  │ │
│                                                    │  │ SELL 568P @2.1│ │
├────────────────────────────────────────────────────┤  │ conf: 72%     │ │
│  BOTTOM PANEL (120px) — Options Quick-Chain         │  └──────────────┘ │
│  Strike | C.Bid | C.Ask | C.Vol | STRIKE | P.Vol  │  ┌──────────────┐ │
│  Scrollable grid with ITM/OTM shading              │  │ OPTIONS CHAIN │ │
│                                                    │  │ Full detail   │ │
└────────────────────────────────────────────────────┴────────────────────┘
```

### Component Dimensions (1920×1080):

| Component                   | Width         | Height          |
|-----------------------------|---------------|-----------------|
| Top Nav Bar                 | 100%          | 40px            |
| Order Flow Chart            | calc(100%-260px) | 55% of remaining |
| Candlestick Chart + RSI     | calc(100%-260px) | 35% of remaining |
| Bottom Options Panel        | calc(100%-260px) | 120px fixed     |
| Right Sidebar               | 260px fixed   | 100% of remaining|

### Top Navigation Bar — Detailed Breakdown

The nav bar is the command center. It spans full width, 40px tall, `--bg1` background, bottom border.

**Left cluster (Symbol & Config):**
- **Symbol selector:** Pill-style toggle group — `[SPY]` `[SPX]` `[XSP]`. Active pill gets `--accent` background + white text. Click to switch; all charts and data reload for selected symbol.
- **Expiration selector:** Dropdown `[Mar 28 ▾]` showing nearest 6 expirations. Updates options chain and flow data.
- **Strike range filter:** Small stepper `[±10]` `[±20]` `[±50]` controlling how many strikes around ATM appear in the options chain.
- **Call/Put filter:** Toggle `[Calls]` `[Puts]` `[Both]`. When set to "Calls" or "Puts", the order flow chart only shows flow for that side. "Both" is default.

**Center cluster (Time controls):**
- **Bar duration selector:** `[1m]` `[5m]` `[15m]` `[30m]` `[1H]` — controls the aggregation period for order flow bubbles and candle chart simultaneously. Both charts always share the same time interval.

**Right cluster (Status & Price):**
- **Connection dots:** `● Engine` (green=connected, red=disconnected), `● ThetaData` (same), `● Alpaca` (same)
- **Live price:** Large bold `$572.34` with colored change `+$4.56 (+0.80%)` — green if positive, red if negative.

---

## 3. Detailed Chart Designs

### Chart 1: Order Flow Bubble/Cloud Chart (Top Panel)

This is the "why" chart — it answers *who is buying/selling and at what intensity*.

**Axes:**
- **X-axis:** Time (datetime), matching the selected bar duration (5m default). Each vertical column of bubbles represents one time bar.
- **Y-axis:** Price levels, rounded to $0.01 (SPY tick size). Auto-scales to show the visible price range with 2–3% padding above/below.

**Bubble Appearance:**
- Each bubble represents the **total volume traded at a specific price level within a specific time bar**.
- **Size:** Proportional to `totalVolume` at that (time, price) cell. The largest bubble in the visible range gets a max diameter of ~40px. Empty cells have no bubble. Minimum bubble size: 4px diameter (to avoid invisible noise).
- **Color:** Diverging colorscale based on **delta** (buyVolume − sellVolume):
  - Deep green (`#00E676`) → strong net buying (delta > +70% of cell volume)
  - Medium green (`#26A69A`) → moderate net buying
  - Yellow (`#FFB300`) → balanced (delta within ±15% of cell volume)
  - Medium red (`#EF5350`) → moderate net selling
  - Deep red (`#FF1744`) → strong net selling (delta < −70% of cell volume)
- **Opacity:** 0.75 base. Creates a soft "cloud" effect where overlapping bubbles at adjacent price levels bleed together visually, forming a dense cloud at high-volume areas (POC = Point of Control).
- **Border:** 0.5px white stroke at 0.15 opacity — gives each bubble definition without adding visual noise.

**Cloud Effect Details:**
- At high-volume price levels, adjacent bubbles overlap slightly (Y-axis price levels are dense enough that 40px bubbles touch), creating the signature "cloud" — a dense, colorful mass that instantly draws the eye to where the action is.
- Low-volume price levels have small, scattered bubbles — visually sparse, communicating "thin" liquidity.
- The result is an intuitive heat-map-like view: **thick green clouds = aggressive buying**, **thick red clouds = aggressive selling**, **thin scattered bubbles = low conviction**.

**Imbalance Highlighting:**
- When a cell's delta exceeds ±80% of its volume (extreme imbalance), add a subtle pulsing glow (CSS animation, 2s cycle, 0.3 opacity) around that bubble. This catches the trader's eye for potential sweep detection.
- When 3+ consecutive time bars at the same price level are all same-direction (all green or all red), render a faint horizontal "streak" line connecting them — visual pattern for sustained institutional pressure.

**Hover Template (rich tooltip):**
```
┌─────────────────────┐
│  10:35 AM  $572.15  │
│  Total:  12,450     │
│  Buy:     8,230     │
│  Sell:    4,220     │
│  Delta:  +4,010     │
│  % Bar:   3.2%      │
│  Imbal:  ■■■■■□□    │
└─────────────────────┘
```
Shows time, price, total volume, buy/sell breakdown, delta, percentage of bar's total volume, and a visual imbalance bar.

**Chart Background:** `#0A0A12`. Grid lines: horizontal at round $ values (e.g., $570, $575), vertical at bar boundaries — both at `rgba(255,255,255,0.03)`, barely visible. No clutter.

### Chart 2: Normal Candlestick Chart (Bottom Panel)

This is the "what" chart — it shows price action, trend, and structure.

**Candle Style:** Standard OHLC (not Heikin Ashi by default — HA smooths out real prices which matters for options entry).
- **Bullish:** Body `#26A69A`, border `#26A69A`, wick `#26A69A`
- **Bearish:** Body `#EF5350`, border `#EF5350`, wick `#EF5350`
- Body width: auto-scaled by Lightweight Charts (optimal density)

**Volume Histogram:** Below candles, using `priceScaleId: ''` (overlay on bottom 12% of chart area).
- Bullish volume bars: `rgba(38, 166, 154, 0.25)`
- Bearish volume bars: `rgba(239, 83, 80, 0.25)`
- Subtle enough to not compete with candles but scannable.

**Overlays (toggleable from toolbar):**
- **EMA 21:** `#FFB300` (amber), 1px line — fast trend
- **SMA 50:** `#42A5F5` (blue), 1px line — medium trend
- **Bollinger Bands (20, 2σ):** `rgba(156, 39, 176, 0.5)` (purple), with optional fill between bands at 0.05 opacity
- **VWAP:** `#5588EE` (accent), 1px dashed — intraday anchor

**RSI Sub-Panel (60px, below candles):**
- Purple line (`#AB47BC`), 1px
- 70/30 level lines: red/green at 0.3 opacity, dashed
- Time axis hidden (synced with main)

**OHLCV Tooltip (on crosshair):**
Floating tooltip near cursor showing O, H, L, C, Vol — matching the current bar.

### Chart Synchronization

This is critical for the "order flow + candles" workflow:

1. **Time axis sync:** Both charts share the exact same time range and scale. Zooming/panning either chart moves both. Implemented with `subscribeVisibleLogicalRangeChange` and a `syncing` guard to prevent recursion.
2. **Crosshair sync:** Moving the crosshair on the Order Flow chart draws a corresponding vertical line on the Candle chart at the same time, and vice versa. The trader can hover on a big green cloud and instantly see the candle shape at that moment.
3. **Bar duration sync:** Changing the bar selector (1m/5m/15m/etc.) re-aggregates both charts simultaneously. Both always show the same time granularity.
4. **Zoom linkage:** Mousewheel zoom on either chart zooms both. This keeps context aligned.

---

## 4. Color System — Complete Reference

### Primary Data Colors
| Purpose              | Color     | Hex       | Opacity |
|----------------------|-----------|-----------|---------|
| Strong buy pressure  | Deep green| `#00E676` | 0.85    |
| Buy pressure         | Green     | `#26A69A` | 0.75    |
| Neutral / balanced   | Amber     | `#FFB300` | 0.70    |
| Sell pressure        | Red       | `#EF5350` | 0.75    |
| Strong sell pressure | Deep red  | `#FF1744` | 0.85    |

### Chart Surface Colors
| Element              | Hex                    |
|----------------------|------------------------|
| Chart background     | `#0A0A12`              |
| Grid lines           | `rgba(255,255,255,0.03)` |
| Axis labels          | `#6E6E88`              |
| Crosshair line       | `rgba(85,136,238,0.2)` |
| Panel borders        | `#22223A`              |

### UI Surface Colors
| Element              | Hex       |
|----------------------|-----------|
| Page background      | `#0A0A12` |
| Panel background     | `#0F0F19` |
| Section header       | `#151520` |
| Hover / active       | `#1B1B28` |
| Focus ring           | `#5588EE` |

### High-Volume Clouds vs. Clean Candles
The design uses **separate vertical panels** (not overlaid) to avoid the order flow bubbles cluttering the candle chart. The candle chart stays clean and structural. The order flow chart is inherently dense — that density is its value. By keeping them in separate panels with linked crosshairs, the trader gets the "what" and "why" simultaneously without either chart degrading the other.

---

## 5. Interactions & UX Details

### Hover Behavior
- **Order Flow Chart:** Hovering a bubble shows the rich tooltip (time, price, vol breakdown, delta, imbalance bar). The bubble under the cursor slightly brightens (+10% opacity) and scales up 1.1x with a 100ms CSS transition.
- **Candle Chart:** Crosshair shows OHLCV tooltip. Standard Lightweight Charts behavior.
- **Both charts:** Crosshair is always synced — hovering one shows a ghost crosshair on the other.

### Click Behavior
- **Order Flow Chart:** Clicking a time column highlights it with a subtle `rgba(85,136,238,0.08)` vertical band on both charts. Double-click to clear.
- **Drawing tools** work on the candle chart only (horizontal lines, trendlines, fibonacci). Order flow chart is read-only — no drawing on clouds.

### Zoom & Pan
- **Mousewheel:** Zooms time axis on both charts simultaneously.
- **Click-drag:** Pans horizontally on both charts.
- **Pinch (trackpad):** Zoom.
- **Double-click time axis:** Fit all visible data.

### Real-Time Update Feel
- New bubbles fade in with a 200ms opacity transition (0 → 0.75).
- The current (forming) time bar's bubbles have a subtle 3s breathing animation (opacity oscillates 0.6–0.8) to indicate "this bar is still building."
- New candle updates are instant — no animation on price changes.
- New signals slide in from the right sidebar with a 300ms `translateX(20px)` → `translateX(0)` transition.

### Keyboard Shortcuts
| Key     | Action                                      |
|---------|---------------------------------------------|
| `1–6`   | Switch bar duration (1=1m, 2=5m, 3=15m, etc.)|
| `E`     | Toggle EMA overlay                           |
| `S`     | Toggle SMA overlay                           |
| `B`     | Toggle Bollinger Bands                       |
| `H`     | Horizontal line drawing mode                 |
| `T`     | Trendline drawing mode                       |
| `F`     | Fibonacci drawing mode                       |
| `Esc`   | Cancel active drawing / clear selection      |
| `Space` | Toggle between Order Flow and Candle focus   |
| `R`     | Reset zoom (fit all data)                    |
| `C`     | Cycle symbol: SPY → SPX → XSP → SPY         |

### Loading States
- Charts show a centered pulsing dot animation (3 dots, `--accent` color) with text "Loading {symbol} data..."
- The nav bar price shows `--` with `--dim` color until first data arrives.
- Connection dots are red by default, flip to green when their respective source connects.

### Empty States
- If no ticks are flowing: Candle chart shows last available EOD data. Order flow chart shows a centered message: "Waiting for trade data... Market may be closed." with a subtle clock icon.
- If data source is disconnected: Red banner below nav bar: "⚠ {Source} disconnected. Reconnecting..." with auto-retry indicator.

---

## 6. AI Signal Panel Design

The AI Signal Panel lives in the right sidebar, below the metrics section. It scrolls independently.

### Signal Card Layout
Each signal is a compact card (full sidebar width, ~48px tall):

```
┌──────────────────────────────┐
│ ● BUY  575C  Mar28     10:42│
│   @$3.20  Conf: 87%         │
│   Flow spike + support bounce│
└──────────────────────────────┘
```

**Card Structure:**
- **Row 1:** Direction pill (`BUY` in green or `SELL` in red, 8px bold uppercase), strike + type (`575C`), expiration (`Mar28`), timestamp (right-aligned, `--muted`)
- **Row 2:** Entry price (`@$3.20`, `--text`), confidence (`Conf: 87%` — color-coded: >80% green, 60-80% amber, <60% red)
- **Row 3:** One-line reasoning in `--dim` color (`Flow spike + support bounce`)

**Visual Cues:**
- Left border: 2px solid green (buy) or red (sell) — instant visual scanning
- Background: `--bg1` default, `--bg3` on hover
- New signal: brief 500ms highlight with `--accent` at 0.05 opacity background, then fade to normal

**Stacking:** Newest on top. Max 50 signals kept in memory. Older ones scroll down. Each card has a 1px bottom border for separation.

**Future Enhancement Placeholder:** Each card will eventually have action buttons: `[Enter]` to execute the trade, `[Dismiss]` to hide. For now, cards are read-only information displays.

---

## 7. Three Layout Variations

### Variation A: Side-by-Side Charts (Balanced)

```
┌───────────────────────────────────────────────────────────────────┐
│  TOP NAV BAR (40px)                                               │
├──────────────────────────┬──────────────────────────┬─────────────┤
│                          │                          │             │
│  ORDER FLOW              │  CANDLESTICK             │  SIDEBAR    │
│  BUBBLE/CLOUD            │  OHLC + Volume           │  260px      │
│  50% width               │  50% width               │             │
│                          │                          │  Metrics    │
│  Full height             │  Full height             │  Signals    │
│  (minus nav+bottom)      │  + RSI sub-panel         │  Options    │
│                          │                          │             │
├──────────────────────────┴──────────────────────────┤             │
│  BOTTOM: Options Quick-Chain (120px)                │             │
└─────────────────────────────────────────────────────┴─────────────┘
```

**Pros:** Both charts visible at full height. Easy left-right comparison. Natural "look left for flow, look right for candles" workflow.
**Cons:** Each chart is only 50% wide — fewer time bars visible horizontally. On 1920px: each chart gets ~830px width.
**Best for:** Traders who weight order flow and candles equally.

---

### Variation B: Stacked Vertically (Recommended — described in Section 2)

```
┌───────────────────────────────────────────────────────────────────┐
│  TOP NAV BAR (40px)                                               │
├─────────────────────────────────────────────────────┬─────────────┤
│                                                     │             │
│  ORDER FLOW BUBBLE/CLOUD (55% height)               │  SIDEBAR    │
│  Full width (minus sidebar)                         │  260px      │
│                                                     │             │
├─────────────────────────────────────────────────────┤  Metrics    │
│                                                     │  Signals    │
│  CANDLESTICK + RSI (35% height)                     │  Options    │
│  Full width (minus sidebar)                         │             │
│                                                     │             │
├─────────────────────────────────────────────────────┤             │
│  BOTTOM: Options Quick-Chain (120px)                │             │
└─────────────────────────────────────────────────────┴─────────────┘
```

**Pros:** Full horizontal width for both charts — maximum time bars visible. Order flow on top (primary focus), candles below (context). Vertical scanning is natural for price (Y-axis alignment). Crosshair vertical line aligns perfectly between charts.
**Cons:** Each chart gets less vertical space. On 1080px: order flow ~440px tall, candles ~320px tall.
**Best for:** Order-flow-first traders. Recommended default.

---

### Variation C: Tabbed Multi-View (Multi-Monitor Friendly)

```
┌───────────────────────────────────────────────────────────────────┐
│  TOP NAV BAR (40px)                                               │
│  [● Flow+Candles] [Flow Only] [Candles Only] [Options Board]     │
├─────────────────────────────────────────────────────┬─────────────┤
│                                                     │             │
│  ACTIVE TAB CONTENT                                 │  SIDEBAR    │
│  (Full remaining area)                              │  260px      │
│                                                     │             │
│  Tab 1: Stacked (Variation B)                       │  Persists   │
│  Tab 2: Order Flow full-screen                      │  across     │
│  Tab 3: Candles full-screen + RSI + CVD             │  all tabs   │
│  Tab 4: Full options chain matrix                   │             │
│                                                     │             │
│                                                     │             │
└─────────────────────────────────────────────────────┴─────────────┘
```

**Pros:** Each view gets maximum screen space. On multi-monitor setups, pop out a tab to its own window. "Flow Only" tab lets the order flow chart fill the entire area — ideal during high-volume moments. Options Board tab shows a full matrix grid of all strikes × expirations.
**Cons:** Can't see order flow and candles simultaneously in single-view tabs (except Tab 1). Adds navigation overhead.
**Best for:** Multi-monitor setups or traders who focus on one view at a time. Power users who want a full-screen options board.

---

## Implementation Tech Stack

When approved, the implementation will use:

- **Framework:** Single-page HTML + vanilla JS (no framework dependency — keeps it fast and portable, consistent with your existing `flow-dashboard.html`)
- **Charting:** Lightweight Charts v4 for candlestick chart; Plotly.js (via CDN) for the order flow bubble/cloud chart (Plotly's `go.Scatter` with `mode='markers'` is ideal for variable-size colored bubbles with rich hover)
- **Styling:** Custom CSS variables (already established in your codebase)
- **Data:** ThetaData REST API via FastAPI proxy endpoints + Flow Engine WebSocket for live ticks
- **No external build step.** Single HTML file, CDN libraries, production-ready.

---

*This completes the design phase. Let me know which variation you prefer (A, B, or C) or what changes you'd like before I generate the implementation code.*
