# ThetaData Options Flow Migration Audit

Date: 2026-04-10

## Goal

Make `ThetaDataDx` the single authoritative source of live options order flow for the UI.

Today, the platform is not wired that way. The live options flow UI depends on the Python
`Theta Terminal` path, while `ThetaDataDx` exists in parallel on the Rust side but does not
emit the full enriched contract the frontend expects.

## Current Live Path

Current options flow seen in the UI:

1. `Theta Terminal` websocket streams option quotes and trades into
   [`dashboard/theta_stream.py`](../dashboard/theta_stream.py)
2. Python enriches trades with:
   - Lee-Ready side
   - Black-Scholes IV / delta / gamma / theta / vega
   - options VPIN
   - Smart Money Score
3. [`dashboard/app.py`](../dashboard/app.py) adds:
   - `premium`
   - fallback `timestamp`
   - scanner fanout
4. Python forwards enriched JSON to Rust via [`/ingest`](../flow-engine/src/main.rs)
5. Rust broadcasts that JSON to the frontend through WebSocket / WebTransport
6. Frontend consumes the enriched `theta_trade` in
   [`frontend/src/lib/data.ts`](../frontend/src/lib/data.ts)

This means the current options flow UI is powered by:

- `Theta Terminal -> Python enrichment -> Rust broadcast -> frontend`

Not by direct `ThetaDataDx`.

## ThetaDataDx Today

Current direct `ThetaDataDx` path:

- [`flow-engine/src/theta_dx.rs`](../flow-engine/src/theta_dx.rs)
- [`flow-engine/src/main.rs`](../flow-engine/src/main.rs)

What it does today:

- connects directly to FPSS
- subscribes to equities from config
- supports option contracts from config
- emits raw option quotes and raw option trades into the Rust engine

What it does **not** do today:

- dynamic UI-driven options subscriptions
- option contract decomposition for frontend use
- side classification
- IV / delta / gamma enrichment
- VPIN enrichment
- Smart Money Score enrichment
- premium calculation in the direct path
- reliable frontend-ready timestamps

`ThetaDataDx` is therefore a partial ingestion path, not a drop-in replacement for the
current options flow contract.

## Frontend Contract

The frontend options flow store is defined in
[`frontend/src/signals/optionsFlow.ts`](../frontend/src/signals/optionsFlow.ts).

The live `theta_trade` consumer is in
[`frontend/src/lib/data.ts`](../frontend/src/lib/data.ts).

The current frontend `OptionTrade` shape is:

- `root`
- `strike`
- `right`
- `price`
- `size`
- `premium`
- `exchange`
- `timestamp`
- `expiration`
- `condition`
- `side`
- `iv`
- `delta`
- `gamma`
- `vpin`
- `sms`
- `spyPrice`
- `tag` (derived in frontend)
- `clusterId` (derived in frontend)

### Which fields are truly required by the UI

Required for the options tape:

- `strike`
- `right`
- `price`
- `size`
- `premium`
- `timestamp`
- `exchange`
- `side`
- `iv`
- `sms`

Required for client-side clustering / sweep tagging:

- `strike`
- `right`
- `price`
- `size`
- `premium`
- `timestamp`
- `exchange`
- `side`

Required for the live chain patching path:

- `strike`
- `right`
- `price`
- `size`
- `iv`
- `delta`
- `gamma`

Required for bubble/heatmap/chart-side linked widgets:

- `strike`
- `right`
- `size`
- `premium`
- `timestamp`
- `side`
- `sms`
- `spyPrice`

Useful but not strictly required for first cutover:

- `condition`
- `expiration`
- `vpin`

## Current Python-Enriched Payload

`theta_stream.py` currently emits trades with:

- `type`
- `root`
- `expiration`
- `strike`
- `right`
- `price`
- `size`
- `side`
- `iv`
- `delta`
- `gamma`
- `vpin`
- `sms`
- `exchange`
- `sequence`
- `condition`
- `ms_of_day`
- `status`

Then `dashboard/app.py` enriches that payload again with:

- `premium`
- `timestamp`

This is why the frontend works when `Theta Terminal` is healthy.

## Current ThetaDataDx Payload

Direct `ThetaDataDx` normalized events in
[`flow-engine/src/theta_dx.rs`](../flow-engine/src/theta_dx.rs):

### OptionQuote

- `symbol`
- `contract_id`
- `bid`
- `ask`
- `bid_size`
- `ask_size`
- `ms_of_day`
- `date`

### OptionTrade

- `symbol`
- `contract_id`
- `price`
- `size`
- `condition`
- `exchange`
- `ms_of_day`
- `date`

But the JSON that Rust currently forwards in
[`flow-engine/src/main.rs`](../flow-engine/src/main.rs) is even thinner:

- `type`
- `root` (currently just `symbol.as_ref()`)
- `price`
- `size`
- `condition`
- `exchange`
- `ms_of_day`

That is not enough for the current frontend.

## Gap Matrix

### Already available from ThetaDataDx raw trade stream

- `price`
- `size`
- `condition`
- `exchange`
- `ms_of_day`
- `date`
- some form of contract `symbol`
- `contract_id`

### Missing before frontend cutover

- `strike`
- `right`
- `expiration`
- guaranteed `root`
- `premium`
- `timestamp`
- `side`
- `iv`
- `delta`
- `gamma`
- `vpin`
- `sms`
- `spyPrice`

### Missing as platform plumbing

- dynamic option subscription API into Rust
- option subscription ownership linked to current UI symbol / scanner scope
- quote cache for Lee-Ready and Greeks
- underlying price feed for options Greeks / ATM distance / SMS

## Why ThetaDataDx Alone Does Not Fix Options Flow Yet

The direct Rust path is currently too raw and too narrow:

- it starts with `option_contracts: vec![]`
- there is no API in the Rust engine to add contracts dynamically
- there is no option quote book / Greeks book / VPIN book equivalent to Python
- there is no frontend-ready option event schema emitted by the Rust path

So even with working credentials, `ThetaDataDx` is not yet capable of replacing the
Python `Theta Terminal` flow path without additional implementation.

## Recommended Target Architecture

Single-source-of-truth target:

1. `ThetaDataDx` becomes the only live options ingestion source
2. Rust owns:
   - option subscriptions
   - quote cache
   - trade classification
   - Greeks enrichment
   - VPIN enrichment
   - Smart Money Score
3. Rust emits a complete `OptionTrade` payload already matching frontend needs
4. Frontend consumes only Rust option events
5. Python `theta_stream.py` is retired from the live options-flow path

## Recommended Event Contract From Rust

Rust should emit a single frontend-ready `theta_trade` payload with at least:

- `type`
- `root`
- `expiration`
- `strike`
- `right`
- `price`
- `size`
- `premium`
- `exchange`
- `timestamp`
- `ms_of_day`
- `condition`
- `side`
- `iv`
- `delta`
- `gamma`
- `vpin`
- `sms`
- `spy_price`

Optional:

- `theta`
- `vega`
- `sequence`
- `contract_id`

## Migration Order

### Phase 1: Rust parity ✅ DONE (2026-04-10)

Rust-side enrichment in [`flow-engine/src/options_enrichment.rs`](../flow-engine/src/options_enrichment.rs):

- ✅ parse/decompose option contract identity into `root`, `expiration`, `strike`, `right`
- ✅ keep per-contract quote book (bid/ask cache by contract_id)
- ✅ classify trade side from latest bid/ask (Lee-Ready)
- ✅ calculate `premium` (price × size × 100)
- ✅ calculate IV / delta / gamma (Newton-Raphson BS solver, 30 iterations)
- ✅ maintain options VPIN state (200 contracts/bucket, 40-bucket rolling window)
- ✅ compute Smart Money Score (size + gamma + aggression + ATM proximity)
- ✅ carry a real timestamp (date + ms_of_day → Unix ms)

### Phase 2: Dynamic subscriptions ✅ DONE (pre-existing)

Already implemented before the migration audit:

- ✅ `POST /theta/options/subscribe` endpoint in Rust (symbol, expiration, spot_price, strike_range)
- ✅ Frontend `switchSymbol()` calls `/api/theta/subscribe` which bridges to Rust
- ✅ Python `/api/theta/subscribe` forwards to Rust endpoint
- ✅ Automatic unsubscribe of old contracts on symbol change

### Phase 3: Frontend cutover ✅ DONE (2026-04-10)

De-duplication guard in [`dashboard/app.py`](../dashboard/app.py):

- ✅ `_theta_dx_is_active()` checks Rust health endpoint at startup
- ✅ `_python_theta_forward_enabled` flag gates Python → Rust forwarding
- ✅ When ThetaDx active: Python `broadcast_theta_trade` skips `forward_to_rust()`
- ✅ Frontend receives enriched theta_trade exclusively from Rust ThetaDx
- ✅ Chain patching reads IV/delta/gamma from Rust-enriched trades

### Phase 4: Scanner migration ✅ DONE (2026-04-10)

Scanner stays in Python but de-duplicated:

- ✅ Python theta_stream always subscribes SPY + scanner symbols (for scanner feed)
- ✅ `flow_scanner.on_trade()` always called regardless of ThetaDx status
- ✅ Forward-to-Rust skipped when ThetaDx active (no duplicate broadcast)
- ✅ Scanner symbols (SPY, QQQ, AAPL, TSLA, NVDA, etc.) fed from Python path
- ✅ Current UI symbol options fed from Rust ThetaDx (enriched)

### Phase 5: Retire Python Theta flow path — DEFERRED

The Python theta_stream still serves two purposes:

1. Scanner feed for multi-symbol option flow alerts
2. Fallback when ThetaDx FPSS credentials are unavailable

Full retirement requires either:

- Moving scanner to Rust (subscribe all scanner symbols via FPSS)
- Or adding a Rust → Python scanner feed (Rust POSTs trades to Python endpoint)

Neither is urgent since the de-duplication guard prevents duplicate broadcasts.

## Bottom Line

As of 2026-04-10:

- `ThetaDataDx` is the live options-flow source of truth for the frontend
- Rust produces fully enriched `theta_trade` events (IV, Greeks, VPIN, SMS)
- Python theta_stream runs alongside for scanner feed only (no duplicate broadcast)
- Fallback: if ThetaDx credentials are missing, Python path auto-activates
