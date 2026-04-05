# Changelog

## [Unreleased]

### Fixed
- WebSocket reconnection spam: engine WS and dashboard WS now use exponential backoff with max 10 retries instead of retrying forever
- 404 page: non-API routes redirect to dashboard instead of showing raw JSON
- README: updated project structure and docs table to reflect current state

### Changed
- Consolidated 15 docs from root into `docs/` directory
- Removed stale plan/summary files (11 files, 4,327 lines)

## [1.0.0] - 2026-03-24

Initial release of the SPY/SPX 0DTE options trading bot.

### Added
- Confluence-based signal engine with multi-factor scoring
- Claude-powered LLM trade validation
- Rust WebSocket flow engine for real-time order flow analysis
- 8-tab dashboard: Charts, Flow, Candles, Options, Signals, AI Agent, Journal, Settings
- Paper trading via Alpaca integration
- Dynamic exit engine with partial profit-taking and trailing stops
- ThetaData options data provider
- CI pipeline with ruff lint/format and pytest
