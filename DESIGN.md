# Design System — AI Trading Bot

## Product Context
- **What this is:** Personal 0DTE SPY/SPX options trading dashboard with AI-powered signal engine, order flow analysis, and Market Brain LLM assistant
- **Who it's for:** Solo day trader running a $5K cash account on single-leg options
- **Space/industry:** Fintech / Trading platforms (TradingView, Thinkorswim, Bloomberg Terminal, Sierra Chart)
- **Project type:** Real-time data dashboard (SolidJS + TypeScript + FastAPI)

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian with aerospace precision
- **Decoration level:** Minimal — typography and spacing do all the work
- **Mood:** A precision instrument panel that grew up from a terminal. Dense, confident, spartan. Every pixel either carries data or gets cut. The kind of tool that reads as "this person built a serious tool" in the first 3 seconds.
- **Reference sites:** TradingView (benchmark for charting UI), Robinhood Legend (P&L color language), Bloomberg Terminal (data density)

## Typography
- **Display/Headers:** Geist (weight 300-500) — clean geometric sans, engineered feel, creates hierarchy without making it feel like a SaaS dashboard
- **Body/UI Labels:** Geist at 12-13px, weight 400-500 — panel headers, section titles, navigation, buttons
- **Data/Prices:** Geist Mono at 11-13px — all price data, P&L, Greeks, timestamps. Must use `font-variant-numeric: tabular-nums` for column alignment
- **AI/Market Brain:** JetBrains Mono at 11-12px — distinct "voice" for AI output, visually separates machine analysis from market data
- **Code:** JetBrains Mono
- **System Fallback:** SF Mono, Menlo, Consolas (already in font stack)
- **Loading:** Google Fonts CDN
  ```html
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600&family=JetBrains+Mono:wght@300;400;500&display=swap" rel="stylesheet">
  ```
- **Scale:**
  | Level | Size | Weight | Font | Usage |
  |-------|------|--------|------|-------|
  | hero | 22px | 500 | Geist | Main price display, page title |
  | h1 | 15px | 500 | Geist | Section titles |
  | h2 | 13px | 500 | Geist | Panel headers |
  | label | 11px | 500 | Geist | Uppercase section labels (letter-spacing: 0.6-0.8px) |
  | body | 13px | 400 | Geist | Descriptions, body text |
  | data-lg | 14-18px | 500 | Geist Mono | Primary P&L, current price |
  | data | 13px | 400 | Geist Mono | Prices, Greeks, percentages |
  | data-sm | 11px | 400 | Geist Mono | Secondary data, axis labels, timestamps |
  | ai | 11-12px | 400 | JetBrains Mono | Market Brain output |

## Color
- **Approach:** Restrained — 1 accent + neutrals, color is rare and meaningful

### Surfaces (darkest to lightest)
| Token | Hex | Usage |
|-------|-----|-------|
| `--surface-0` | `#0a0a12` | Page background, the void between panels |
| `--surface-1` | `#0f0f19` | Panel backgrounds |
| `--surface-2` | `#151520` | Raised elements, cards, active wells, input backgrounds |
| `--surface-3` | `#1b1b28` | Hover states, selected rows |
| `--surface-4` | `#222236` | Scrollbar thumbs, high-elevation elements |

### Borders
| Token | Value | Usage |
|-------|-------|-------|
| `--border` | `#22223a` | Primary panel borders |
| `--border-subtle` | `rgba(255,255,255,0.08)` | Table row separators |
| `--border-medium` | `rgba(255,255,255,0.12)` | Section dividers |
| `--border-strong` | `rgba(255,255,255,0.12)` | Active/focus borders |

### Text
| Token | Hex | Usage |
|-------|-----|-------|
| `--text-primary` | `#f0f0f8` | Primary content, prices, values |
| `--text-secondary` | `#b0b0c8` | Labels, axis ticks, secondary info |
| `--text-muted` | `#8080a0` | Placeholders, column headers, disabled |

### Accent & Semantic
| Token | Hex | Usage |
|-------|-----|-------|
| `--accent` | `#5588ee` | Primary accent (links, active tabs, focus rings, confluence bar) |
| `--accent-hover` | `#6699ff` | Hover state for accent elements |
| `--positive` | `#00C805` | Profit, bullish, buy signals — Robinhood green |
| `--positive-bright` | `#00E676` | Emphasized positive (hover, bright indicators) |
| `--negative` | `#FF5000` | Loss, bearish, sell signals — Robinhood red |
| `--negative-bright` | `#FF6B2C` | Emphasized negative |
| `--warning` | `#ffb300` | Theta decay warnings, caution states |
| `--info` | `#29b6f6` | Informational, Market Brain updates |
| `--purple` | `#7b61ff` | AI-specific only: Market Brain border, thinking pulse, AI panel title |
| `--cyan` | `#00bcd4` | Chart indicators (VWAP) |

### Chart Indicators
| Token | Hex | Indicator |
|-------|-----|-----------|
| `--chart-rsi` | `#ab47bc` | RSI line |
| `--chart-sma` | `#42a5f5` | Simple Moving Average |
| `--chart-ema` | `#ffb300` | Exponential Moving Average |
| `--chart-vwap` | `#00e5ff` | VWAP |
| `--chart-bb` | `#42a5f5` | Bollinger Bands |

### Dark mode strategy
This is a dark-first product. No light mode is planned. If light mode is ever added: redesign surfaces (not just invert), reduce saturation 10-20% on semantic colors, use `--positive: #00a004` and `--negative: #d44000` for sufficient contrast on white.

## Spacing
- **Base unit:** 4px
- **Density:** Compact — this is a power tool, not a consumer app
- **Scale:**

| Token | Value | Usage |
|-------|-------|-------|
| `--space-2xs` | 2px | Micro gaps (between data label and value on same line) |
| `--space-xs` | 4px | Between data elements in same group |
| `--space-sm` | 8px | Padding inside compact elements (buttons, pills) |
| `--space-md` | 12px | Between conceptual groups, panel padding |
| `--space-lg` | 16px | Between sections within a panel |
| `--space-xl` | 24px | Between panels, major section breaks |
| `--space-2xl` | 32px | Page-level spacing |

### Density rules
- 4px between data elements in same row
- 12px between conceptual groups within a panel
- 24px between panels
- Line height: 1.2 on data, 1.4 on UI text, 1.5 on AI prose output
- Never add "breathing room" spacing. If there's space, it should be intentional separation between semantic groups.

## Layout
- **Approach:** Grid-disciplined
- **Grid:** Main layout is flexbox-based: charts (80%) | panels (20%). Charts split: candle (57%) | flow (43%)
- **Max content width:** Full viewport (trading dashboards use every pixel)
- **Border radius:**
  | Token | Value | Usage |
  |-------|-------|-------|
  | `--radius-sm` | 2px | Panels, cards, alerts |
  | `--radius-md` | 4px | Buttons, inputs, interactive affordances |
  | `--radius-full` | 9999px | Pills, badges (sparingly) |

  Panels get 2px max. No bubbly rounded corners. This is an instrument, not an app.

## Motion
- **Approach:** Minimal-functional — only transitions that aid comprehension
- **Easing:** `ease-out` for enter, `ease-in` for exit, `ease-in-out` for movement
- **Duration:**
  | Token | Value | Usage |
  |-------|-------|-------|
  | micro | 50-100ms | Hover color changes, focus rings |
  | short | 150ms | Tab switches, panel state changes, button feedback |
  | medium | 250ms | Collapsible sections, slide transitions |
- No entrance animations on page load
- No scroll-driven animations
- No decorative motion
- Chart animations handled by LWC (Lightweight Charts) internally

## AI Panel Design Rules
The Market Brain / AI chat panel has a distinct visual treatment:
- Left border: `2px solid rgba(123, 97, 255, 0.4)` (purple at 40% opacity)
- Panel title color: `--purple` (#7b61ff) instead of `--text-secondary`
- Text: JetBrains Mono (not Geist Mono), creating a different "voice"
- Input border: `rgba(123, 97, 255, 0.2)`, focus: `rgba(123, 97, 255, 0.5)`
- This separation makes the AI feel like a different layer of intelligence, not just another data panel

## Anti-Patterns (never do these)
- Purple/violet gradients as backgrounds or buttons
- Rounded corners > 4px on panels
- Decorative shadows or glows (except focus rings)
- Background patterns or textures
- Marketing-style hero sections
- Centered layouts with generous whitespace
- Using `--positive` or `--negative` for non-P&L purposes
- Using `--purple` for anything other than AI-related elements
- Sans-serif fonts for price data (always monospace with tabular-nums)

## CSS Variable Reference
```css
:root {
  /* Surfaces */
  --surface-0: #0a0a12;
  --surface-1: #0f0f19;
  --surface-2: #151520;
  --surface-3: #1b1b28;
  --surface-4: #222236;

  /* Borders */
  --border: #22223a;
  --border-subtle: rgba(255,255,255,0.03);
  --border-medium: rgba(255,255,255,0.06);
  --border-strong: rgba(255,255,255,0.12);

  /* Text */
  --text-primary: #e0e0ea;
  --text-secondary: #6e6e88;
  --text-muted: #44445a;

  /* Accent */
  --accent: #5588ee;
  --accent-hover: #6699ff;

  /* Semantic */
  --positive: #00C805;
  --positive-bright: #00E676;
  --negative: #FF5000;
  --negative-bright: #FF6B2C;
  --warning: #ffb300;
  --info: #29b6f6;

  /* AI */
  --purple: #7b61ff;
  --cyan: #00bcd4;
  --cyan-bright: #00e5ff;

  /* Fonts */
  --font-display: 'Geist', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-data: 'Geist Mono', 'SF Mono', 'Menlo', monospace;
  --font-ai: 'JetBrains Mono', 'Fira Code', monospace;

  /* Spacing */
  --space-2xs: 2px;
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 12px;
  --space-lg: 16px;
  --space-xl: 24px;
  --space-2xl: 32px;

  /* Radius */
  --radius-sm: 2px;
  --radius-md: 4px;
  --radius-full: 9999px;
}
```

## Decisions Log
| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-07 | Initial design system created | Created by /design-consultation. Researched TradingView, Robinhood Legend, Thinkorswim. Independent Claude subagent proposed "Instrument Panel" direction which informed final system. |
| 2026-04-07 | Geist + Geist Mono + JetBrains Mono typography stack | Geist adds hierarchy to mono-first UI without SaaS feel. JetBrains Mono gives AI a distinct voice. Both subagent and primary analysis converged on Geist. |
| 2026-04-07 | Purple (#7b61ff) reserved for AI only | Creates visual separation between trading data and AI analysis. Subagent proposed this, primary analysis agreed. |
| 2026-04-07 | Text primary bumped to #e0e0ea from #d0d0da | Slightly brighter for better readability on deep dark surfaces, especially at 11px data sizes. |
| 2026-04-07 | 4px base spacing, compact density | Trading dashboards must maximize information density. 4px base with 12px group separation and 24px panel separation. |
