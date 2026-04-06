---
name: frontend-design
description: Full dashboard redesign workflow for the trading platform. Audit current UI visually with browser screenshots, find every small issue, design improvements, then implement with atomic commits. Use when asked to redesign, restyle, improve UI, fix layout, or make the dashboard look better.
disable-model-invocation: true
allowed-tools: Bash Read Edit Write Grep Glob Agent
argument-hint: "[scope: all | page-name | component]"
---

# /frontend-design — Trading Dashboard Redesign Workflow

You are a senior frontend engineer and product designer working on a 0DTE SPY
options trading platform. The dashboard serves one user (the trader) and must be
dense, fast, and readable during live market hours.

## Project Context

**Stack:** Vanilla HTML/CSS/JS served by FastAPI. No React, no build step.
**Entry point:** `dashboard/static/flow-dashboard.html` (served at `/`)
**Design system:** `dashboard/static/css/tokens.css` (CSS custom properties)
**Component CSS:** `dashboard/static/css/*.css` (panel, button, badge, tabs, modal, etc.)
**JS modules:** `dashboard/static/js/*.js` (one per page/feature)
**Reusable components:** `dashboard/static/js/components/*.js` (DataTable, Panel, Modal, Tabs, Toast)

**Classification:** APP UI (workspace-driven, data-dense, task-focused)
**Font:** SF Mono / Menlo / Consolas (monospace — intentional for trading data)
**Theme:** Dark only. Navy-black surfaces, Robinhood-style green/red, teal accent.

**Design references:**
- Robinhood: clean green (#00C805) for profit, red (#FF5000) for loss
- TradingView: dark charts, dense but organized panels
- Bloomberg Terminal: maximum density, monospace, keyboard-driven

## Browse Setup (REQUIRED — visual inspection is the whole point)

```bash
export PATH="$HOME/.bun/bin:$PATH"
B=~/.claude/skills/gstack/browse/dist/browse
if [ -x "$B" ]; then
  echo "BROWSE_READY: $B"
else
  echo "BROWSE_NOT_AVAILABLE"
fi
```

If `BROWSE_NOT_AVAILABLE`: Tell the user the browse tool is needed for visual
inspection and offer to set it up. Without the browser, this skill cannot do
its job properly. Fallback to source-code-only review but warn that it will
miss visual issues.

## Workflow

### Phase 1: Visual Audit (browse every page, screenshot everything)

**This is the most important phase.** Do NOT skip it. Do NOT substitute source
code reading for visual inspection. The browser shows what the user actually sees.

1. Navigate to the dashboard and take screenshots of EVERY page:

```bash
$B goto http://localhost:8000
sleep 2
$B screenshot "/tmp/frontend-design/charts.png"

# Click through each sidebar nav item
$B snapshot -i   # get interactive elements
# For each nav button: click, wait, screenshot
```

2. For each page, also check:
```bash
$B console --errors                    # JS errors
$B js "JSON.stringify(/* check specific element visibility */)"
```

3. Take responsive screenshots of key pages:
```bash
$B responsive "/tmp/frontend-design/charts"    # mobile + tablet + desktop
```

4. After screenshots, **Read each image** using the Read tool so you can see
   what the user sees. Do not skip this. The screenshots ARE the audit.

### Phase 1a.5: Structural Verification (REQUIRED before visual audit)

**Screenshots lie.** A section can "look present" in a screenshot while being
collapsed to 50px by a CSS bug. Before doing any visual audit, run this JS
check on EVERY major page to measure actual rendered sizes:

```bash
$B js "
const results = [];
// Check all major sections, tables, and content areas
document.querySelectorAll('section, [class*=section], [class*=panel], [class*=wrap], table, [class*=table]').forEach(el => {
  const rect = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  if(rect.width > 50) { // skip tiny elements
    const clipped = el.scrollHeight > el.clientHeight + 2;
    const tooSmall = rect.height < 80 && el.children.length > 1;
    if(clipped || tooSmall) {
      results.push({
        el: el.tagName + '.' + (el.className||'').substring(0,30),
        id: el.id || '',
        renderedH: Math.round(rect.height),
        contentH: el.scrollHeight,
        overflow: cs.overflow,
        clipped: clipped,
        tooSmall: tooSmall,
      });
    }
  }
});
JSON.stringify(results, null, 2);
"
```

**Any section with `clipped: true` or `tooSmall: true` is a P0 bug.**
Investigate the cause (usually `overflow: hidden` in flex, or a `max-height`
that's too aggressive). Fix it before proceeding to visual audit.

Also measure the primary content sections on each page:
```bash
$B js "
// Check that primary content areas are getting fair share of viewport
const vh = window.innerHeight;
const sections = document.querySelectorAll('.pos-section, .chart-wrap, .sub-pane, .tab-panel.active');
const sizes = [];
sections.forEach(s => {
  const h = s.offsetHeight;
  const hdr = s.querySelector('[class*=hdr], [class*=header], [class*=title]');
  sizes.push({
    name: (hdr?.textContent||s.className).trim().substring(0,30),
    height: h,
    pctViewport: Math.round(h/vh*100) + '%',
    issue: h < 60 ? 'COLLAPSED' : h < 100 ? 'TOO_SMALL' : 'ok',
  });
});
JSON.stringify(sizes, null, 2);
"
```

**If a section says COLLAPSED or TOO_SMALL, stop and fix it.** Don't proceed
to color or spacing issues. Layout is the foundation.

### Phase 1b: Trading-Specific Audit (what generic design tools miss)

Go through EVERY item. Check by looking at the screenshots you just took.
**For every checkbox, state what you measured or observed. "Looks fine" is not
an acceptable check.** Give the actual height, the actual color value, or the
actual text content.
If something fails, it's P0. Be ruthless. Find every small issue.

**Critical visibility (can the trader see what they need?):**
- [ ] Open positions table: visible, readable, P&L updating in real-time
- [ ] Position P&L: green/red color, dollar amount AND percentage shown
- [ ] Greeks per position: delta, theta at minimum visible without scrolling
- [ ] Exit urgency: the 6-scorer composite + level (HOLD/CAUTION/WARNING/URGENT) visible
- [ ] Charm/vanna scorer output visible somewhere (new, post-1:30 PM this is dominant)
- [ ] Current SPY price: large, prominent, always visible regardless of active tab
- [ ] Bid/ask spread: visible near price (tells you about liquidity)
- [ ] Signal tier + confidence: clear on signal cards
- [ ] Time to close: countdown visible during trading hours

**Critical interaction (can the trader act fast?):**
- [ ] Exit position: one click, no confirmation during URGENT (confirmation for non-urgent)
- [ ] Exit all: accessible, has confirmation
- [ ] Switch between pages: instant (no loading spinners for navigation)
- [ ] Timeframe buttons (1m/5m/15m): responsive, current selection obvious

**Layout and alignment (pixel-level):**
- [ ] Charts are CENTERED in their container, not offset or clipped
- [ ] Panels align to a consistent grid, nothing floats randomly
- [ ] Tables have aligned columns, numbers right-aligned
- [ ] Sidebar panel content doesn't overflow or get cut off
- [ ] No orphaned labels or headings with no content below them
- [ ] Scrollbars appear only when needed, styled consistently
- [ ] No unnecessary horizontal scrolling on any viewport

**Color consistency (Robinhood style):**
- [ ] Profit/bullish: bright clean green (#00C805 or similar, NOT the muted teal #26a69a)
- [ ] Loss/bearish: clean red (#FF5000 or similar, NOT dark/muted red)
- [ ] These colors are used CONSISTENTLY for P&L, direction arrows, badges everywhere
- [ ] Neutral/flat: gray/muted, not green or red
- [ ] Warning: amber/yellow
- [ ] Background surfaces: dark but distinguishable layers
- [ ] Text contrast: primary text easily readable, secondary clearly dimmer

**Information hierarchy per page:**

Charts page:
- [ ] Charts CENTERED in container, filling available space
- [ ] Order flow bubbles readable at current zoom
- [ ] Candlestick chart has enough vertical space
- [ ] Volume bars visible below chart
- [ ] VWAP line distinguishable from price action
- [ ] No empty gaps or wasted space around charts

AI Agent page:
- [ ] 5-agent cards: direction + confidence scannable at a glance
- [ ] Positions table: dominates the page when positions are open
- [ ] Trade history: scrollable, sortable, P&L column prominent
- [ ] Equity curve: renders with real data (not just placeholder)
- [ ] Beat SPY scorecard: YOUR P&L vs SPY % clear comparison

Options page:
- [ ] Chain table: calls left, puts right, ATM row highlighted
- [ ] Greeks columns: visible without horizontal scroll
- [ ] P/C ratio, max pain, IV rank: visible in sidebar or header

Flow page:
- [ ] Delta bar (buy vs sell volume): clear, real-time
- [ ] CVD trend: visible
- [ ] Volume profile: price levels with volume bars readable
- [ ] Large trades: highlighted differently from normal flow

**Small details that add up:**
- [ ] No text clipping or overflow hidden cutting off important data
- [ ] Tooltips work on hover for truncated text
- [ ] Active tab/button has clear visual distinction (not subtle)
- [ ] Loading states use skeletons that match content shape, not generic spinners
- [ ] Empty states have warm messaging with context, not just "No data"
- [ ] Border radius is consistent (not some elements rounded, some sharp)
- [ ] Spacing between sections is consistent (not random gaps)
- [ ] Font sizes follow the token scale (no arbitrary sizes)
- [ ] Icons are consistent style (all outline OR all filled, not mixed)

**Data freshness indicators:**
- [ ] Stale data warning: if data is >30s old, show indicator
- [ ] Connection status: engine connected/disconnected obvious
- [ ] Market status: open/closed/pre-market clear without reading small text

**Off-hours experience:**
- [ ] No alarming red warnings when market is simply closed
- [ ] Empty states are warm and informative, not blank or scary
- [ ] "Market opens in X hours" more useful than "BLOCKED"

### Phase 2: Design (propose before building)

For each issue found, propose a fix with specific details:

```
ISSUE: [what's wrong — be specific, reference the screenshot]
IMPACT: [what the trader experiences because of this]
FIX: [exact CSS/HTML change — name the property, the value, the selector]
FILES: [which files to modify]
PRIORITY: P0/P1/P2
```

Present ALL proposals grouped by priority. Wait for approval.

### Phase 3: Implement (one commit per fix)

For each approved fix:

1. Read the source file
2. Make the minimal change
3. Commit atomically: `git commit -m "style: [short description]"`
4. Verify the dashboard still loads: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000`

**Rules:**
- Use design tokens from `tokens.css` exclusively. Never hardcode colors, sizes, or spacing.
- When updating colors to Robinhood style, update the TOKENS first, then everything
  inherits automatically. Don't hunt-and-replace hex values across files.
- Use existing CSS component classes (`dashboard/static/css/*.css`) before writing new CSS.
- Prefer CSS changes over JS changes. CSS is safer and more reversible.
- All new CSS goes in `flow-dashboard.html` `<style>` or the appropriate `css/*.css` file.
- Never add external dependencies (no Tailwind, no Bootstrap, no CDN fonts).
- Preserve the monospace terminal aesthetic. This is a trading terminal, not a SaaS app.
- Test responsive: verify layout at 1280px, 768px, and 375px.

### Phase 4: Verify (screenshot AFTER fixes)

After all fixes, take new screenshots of every changed page and compare:

```bash
$B goto http://localhost:8000
$B screenshot "/tmp/frontend-design/after-charts.png"
# ... for each page
```

Read the after screenshots. Compare with before. Report:
- What changed visually
- Files modified, commits made
- Any remaining issues deferred

Run tests: `python -m pytest tests/ -x --ignore=tests/test_frontend.py -q`

## Design Principles (trading platform specific)

1. **Density is a feature.** Traders want more data per pixel, not more whitespace.
   Never add padding "for breathing room." If it looks cramped, fix alignment, not spacing.

2. **Numbers must align.** Use `font-variant-numeric: tabular-nums` on all numeric displays.
   Monospace font handles this, but verify columns line up.

3. **Color is Robinhood-clean.** Bright green for profit. Clean red-orange for loss.
   Not muted. Not pastel. The P&L color should hit you instantly.

4. **The chart is king.** Charts should always be centered in their container and get
   maximum available space. Panels and sidebars serve the chart, not the other way around.
   If a chart is off-center, clipped, or has dead space around it, that's P0.

5. **States matter more than layouts.** A position card in profit vs loss vs breakeven
   should be immediately distinguishable. Empty states need warm messaging.

6. **Everything aligns.** No elements floating randomly. Consistent grid. Consistent
   spacing between sections. If two things should be aligned, they must be pixel-perfect.

7. **No AI slop.** No 3-column feature grids. No centered hero sections. No purple
   gradients. No decorative blobs. This is a professional tool.

8. **Performance is design.** Charts at 60fps. No layout shifts. No font flashes.

## Token Reference (quick lookup)

```
Surfaces:  --surface-0 (darkest) through --surface-4 (lightest)
Text:      --text-primary, --text-secondary, --text-muted
Semantic:  --positive (green), --negative (red), --warning (yellow), --accent (blue)
Spacing:   --space-xs (4px) through --space-5xl (32px)
Radius:    --radius-xs (2px) through --radius-xl (8px)
Font:      --font-xs (9px) through --font-hero (18px)
Z-index:   --z-base (0) through --z-debug (99)
```

## Anti-patterns (never do these)

- Adding `!important` unless overriding a third-party library
- Using inline styles in JS when a CSS class would work
- Creating new color variables that duplicate existing tokens
- Adding media queries below 375px (not a real use case)
- Animating layout properties (width, height, top, left) — use transform/opacity only
- Leaving misaligned elements because "it's close enough"
- Using muted/teal for profit — profit is BRIGHT GREEN, always
