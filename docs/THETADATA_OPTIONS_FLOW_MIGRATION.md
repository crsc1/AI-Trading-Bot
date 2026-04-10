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

### Phase 1: Rust parity

Add the missing Rust-side enrichment so `ThetaDataDx` can produce a frontend-ready option trade.

Needed:

- parse/decompose option contract identity into `root`, `expiration`, `strike`, `right`
- keep per-contract quote book
- classify trade side from latest bid/ask
- calculate `premium`
- calculate IV / delta / gamma
- maintain options VPIN state
- compute Smart Money Score
- carry a real timestamp

### Phase 2: Dynamic subscriptions

Add Rust HTTP endpoints for:

- subscribe current symbol 0DTE options
- subscribe scanner contracts
- reset / refresh symbol scope on frontend symbol change

At that point the current Python endpoint
[`/api/theta/subscribe`](../dashboard/app.py)
should drive the Rust engine instead of the Python Theta stream.

### Phase 3: Frontend cutover

Switch the frontend to trust only Rust-originated options events.

Success criteria:

- `OptionsFlow` keeps updating with no Python Theta dependency
- `OptionsHeatmap` still builds correctly
- `OptionsBubbleChart` still renders
- live chain patching still updates IV / delta / gamma
- unusual activity and scanner still work

### Phase 4: Scanner migration

Move the options flow scanner off Python `flow_scanner.py` if desired, or keep the scanner
logic in Python but feed it from the Rust event stream instead of `theta_stream.py`.

### Phase 5: Retire Python Theta flow path

Only after parity is verified:

- remove Python live forwarding ownership from `dashboard/app.py`
- retire `theta_stream.py` from the live options tape path
- keep it only for historical / fallback tools if still useful

## Recommended Next Implementation Slice

The safest next coding step is:

1. extend the Rust `ThetaDxEvent::OptionTrade` path to produce:
   - `root`
   - `expiration`
   - `strike`
   - `right`
   - `premium`
   - `timestamp`
2. extend Rust to maintain an option quote cache
3. compute `side`, `iv`, `delta`, `gamma`, `sms`
4. add a dynamic Rust subscription endpoint for the currently selected symbol

That gets the platform much closer to cutting over without trying to rewrite everything at once.

## Bottom Line

Today:

- `Theta Terminal` is the live options-flow source of truth
- `ThetaDataDx` is a partial parallel path

Target:

- `ThetaDataDx` should become the single live options-flow source of truth

But the cutover is not a toggle. It requires Rust-side parity with the enriched option trade
contract the frontend already depends on.
