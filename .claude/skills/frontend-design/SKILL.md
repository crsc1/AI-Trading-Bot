---
name: frontend-design
description: Full dashboard redesign workflow for the trading platform. Audit current UI, identify issues, design improvements, then implement with atomic commits. Use when asked to redesign, restyle, improve UI, fix layout, or make the dashboard look better.
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
**Theme:** Dark only. Navy-black surfaces, green/red semantic, teal accent.

## Workflow

### Phase 1: Audit (always run first)

Read these files to understand current state:
- `dashboard/static/css/tokens.css` — full design token system
- `dashboard/static/flow-dashboard.html` — layout structure and inline styles
- Recent git log for frontend changes: `git log --oneline -10 -- dashboard/static/`

Then assess scope from the user's request (`$ARGUMENTS`):
- `all` or empty → full dashboard audit, all pages
- A page name (e.g., `agent`, `flow`, `options`) → scope to that page's JS + HTML
- A component (e.g., `sidebar`, `charts`, `signals panel`) → scope to that element

Report what you find:
- Current layout structure
- Design token usage vs hardcoded values
- Spacing/alignment inconsistencies
- Missing responsive breakpoints
- Empty states quality
- Color consistency

### Phase 2: Design (propose before building)

For each issue found, propose a fix:

```
ISSUE: [what's wrong]
IMPACT: [what the trader experiences]
FIX: [specific CSS/HTML change]
FILES: [which files to modify]
```

Present all proposals to the user. Wait for approval before implementing.

If the scope is large (3+ pages), group into priority tiers:
- P0: Broken layouts, unreadable text, missing functionality
- P1: Inconsistent spacing, wrong token usage, bad hierarchy
- P2: Polish, animations, micro-interactions

### Phase 3: Implement (one commit per fix)

For each approved fix:

1. Read the source file
2. Make the minimal change
3. Commit atomically: `git commit -m "style: [short description]"`
4. Verify the dashboard still loads: `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000`

**Rules:**
- Use design tokens from `tokens.css` exclusively. Never hardcode colors, sizes, or spacing.
- Use existing CSS component classes (`dashboard/static/css/*.css`) before writing new CSS.
- Prefer CSS changes over JS changes. CSS is safer and more reversible.
- All new CSS goes in `flow-dashboard.html` `<style>` or the appropriate `css/*.css` file.
- Never add external dependencies (no Tailwind, no Bootstrap, no CDN fonts).
- Preserve the monospace terminal aesthetic. This is a trading terminal, not a SaaS landing page.
- Test responsive: verify layout doesn't break at 768px and 375px viewports.

### Phase 4: Verify

After all fixes:
1. Restart the dashboard if needed: `./restart.sh --dash-only`
2. Check all modified pages load without console errors
3. Run the test suite: `python -m pytest tests/ -x --ignore=tests/test_frontend.py -q`
4. Report summary: files changed, commits made, before/after comparison

## Design Principles (trading platform specific)

1. **Density is a feature.** Traders want more data per pixel, not more whitespace.
   Never add padding "for breathing room." If it looks cramped, fix alignment, not spacing.

2. **Numbers must align.** Use `font-variant-numeric: tabular-nums` on all numeric displays.
   Monospace font handles this, but verify columns line up.

3. **Color is semantic, not decorative.** Green = profit/bullish. Red = loss/bearish.
   Yellow = warning/caution. Teal = accent/info. No decorative gradients.

4. **The chart is king.** Charts should always get maximum available space.
   Panels and sidebars serve the chart, not the other way around.

5. **States matter more than layouts.** A position card in profit vs loss vs breakeven
   should be immediately distinguishable. Empty states need warm messaging.

6. **Keyboard-first.** Traders don't want to reach for a mouse during live trading.
   All key interactions should have keyboard shortcuts.

7. **No AI slop.** No 3-column feature grids. No centered hero sections. No purple
   gradients. No decorative blobs. This is a professional tool.

8. **Performance is design.** Charts at 60fps. No layout shifts. No font flashes.
   Skeleton loaders that match real content shapes.

## Token Reference (quick lookup)

```
Surfaces:  --surface-0 (darkest) → --surface-4 (lightest)
Text:      --text-primary, --text-secondary, --text-muted
Semantic:  --positive (green), --negative (red), --warning (yellow), --accent (blue)
Spacing:   --space-xs (4px), --space-sm (6px), --space-md (8px), --space-lg (10px), --space-xl (12px)
Radius:    --radius-xs (2px), --radius-sm (3px), --radius-md (4px), --radius-lg (6px)
Font:      --font-xs (9px), --font-sm (10px), --font-base (11px), --font-md (12px)
Z-index:   --z-base (0), --z-overlay (20), --z-modal (40), --z-toast (60)
```

## Anti-patterns (never do these)

- Adding `!important` unless overriding a third-party library
- Using inline styles in JS when a CSS class would work
- Creating new color variables that duplicate existing tokens
- Adding media queries below 375px (not a real use case for a trading terminal)
- Animating layout properties (width, height, top, left) — use transform/opacity only
- Adding comments like "TODO: fix later" — fix it now or don't touch it
