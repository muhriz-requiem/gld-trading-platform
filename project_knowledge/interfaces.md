# Interfaces & Data Contract Mapping

## Stage 2 → Stage 3 Integration Lock

---

### Bar Dict — Canonical Internal Format

All Stage 3 components produce and consume bars in this shape.
This is NOT a contract class — it is a raw dict passed between data layer components only.

```
{
  "t": str,   # ISO 8601 UTC timestamp — e.g. "2024-01-15T00:00:00+00:00"
  "o": float, # open price
  "h": float, # high price
  "l": float, # low price
  "c": float, # close price
  "v": float, # volume
  "symbol": str  # ticker — e.g. "GLD"
}
```

Bar dicts are internal to the data layer. They are NEVER passed directly to Stage 2 contracts.
Strategies (Stage 5) are responsible for converting bar data into Signal objects.

---

### Bar Schema Enforcement

**All data entering feature engineering MUST pass bar_validator.py.**

Validation is performed by `src/contracts/validation/bar_validator.py`.
No bar dict may be passed to Stage 4 (feature engineering) without first passing validation.

- `validate_bar(bar)` → validates a single bar dict. Returns `(valid: bool, errors: list[str])`.
- `validate_bars(bars)` → validates a list. Returns aggregated `(valid: bool, errors: list[str])`.

Enforcement point: callers of `AlpacaHistoricalConnector.get_bars()` and `RealtimeFeedInterface.on_bar()`
must validate output before passing bars downstream.

---

### alpaca_historical → Signal (indirect)

- `AlpacaHistoricalConnector.get_bars()` returns `list[dict]` (bar format above)
- Output feeds into feature engineering (Stage 4), which feeds strategies (Stage 5)
- Strategies produce `Signal` objects using `src.contracts.signal.Signal`
- Mapping: `bar["c"]` (close price) → price input for signal generation
- Mapping: `bar["t"]` → parsed via `time_utils.parse_alpaca_timestamp()` → `Signal.generated_at`

---

### realtime_feed → Signal (indirect)

- `RealtimeFeedInterface.on_bar(callback)` delivers bar dicts matching canonical format above
- Same downstream path as historical: bar → features → strategy → `Signal`
- `Signal.generated_at` must always be UTC-aware datetime (enforced by `time_utils.to_utc()`)

---

### bar_cache — Persistence Format

- `LocalBarCache` stores and retrieves `list[dict]` in canonical bar format
- Cache is keyed by: `{symbol}_{timeframe}_{start}_{end}.json`
- Cache contents are JSON-serialised bar dicts — no contract objects are persisted
- On cache read, bar dicts are returned as-is and follow the same downstream path

---

### Stage 2 Contract Fields — Source Mapping

#### Signal
| Field          | Source                                      |
|----------------|---------------------------------------------|
| symbol         | bar["symbol"] or query parameter            |
| direction      | Derived by strategy logic (Stage 5)         |
| confidence     | Derived by strategy logic (Stage 5)         |
| strategy_id    | Set by strategy instance (Stage 5)          |
| generated_at   | parse_alpaca_timestamp(bar["t"]) → to_utc() |
| metadata       | Optional — strategy may attach bar context  |

#### Order
| Field        | Source                                          |
|--------------|-------------------------------------------------|
| symbol       | Derived from Signal.symbol                      |
| side         | Derived from Signal.direction (LONG→BUY, etc.)  |
| order_type   | Set by execution layer (Stage 8)                |
| quantity     | Set by risk/allocation layer (Stage 6/7)        |
| limit_price  | Optional — set by execution layer               |
| created_at   | Set at order creation — UTC datetime            |

#### Position
| Field            | Source                                      |
|------------------|---------------------------------------------|
| symbol           | From filled Order.symbol                    |
| quantity         | From filled Order.quantity                  |
| avg_entry_price  | From Order.filled_price                     |
| current_price    | From latest bar["c"] for that symbol        |
| opened_at        | From Order.filled_at                        |

---

### Time Alignment Assumptions

- All timestamps are UTC throughout the system
- `parse_alpaca_timestamp()` normalises all Alpaca timestamps to UTC-aware datetime
- `to_utc()` is applied to any datetime before it enters a contract object
- `align_to_timeframe()` filters bars to a fixed grid — missing bars are dropped, not filled
- No forward-filling or interpolation occurs in the data layer

---

### Schema Validation — No Duplicates

| Concern                        | Status                                      |
|-------------------------------|---------------------------------------------|
| Bar dict defined in one place  | ✅ Canonical format documented here only    |
| Contract classes defined once  | ✅ All in src/contracts/                    |
| No contract objects in cache   | ✅ Cache stores raw bar dicts only          |
| No bar dicts in contracts      | ✅ Contracts use typed fields only          |
| Order import in data layer     | ✅ Removed from alpaca_historical.py        |
| Bar validation enforced        | ✅ src/contracts/validation/bar_validator.py |

---

## Feature Layer Contracts

---

### Feature Input

All feature functions must accept only validated bar data.

- Input is exclusively a `list[dict]` of bar dicts that have already passed `bar_validator.py`
- No raw market data, no contract objects, no nested structures may enter a feature function
- Feature functions must not re-validate — validation is the caller's responsibility

---

### Feature Output Schema

Feature functions return a flat numeric feature map:

```
{
  "feature_name": float,  # e.g. "rsi_14": 54.3
  "feature_name": float,  # e.g. "return_1d": 0.0042
  ...
}
```

Constraints on output:
- All values must be `int` or `float` — no strings, no nested dicts, no lists
- No raw OHLCV fields may appear in the output (o, h, l, c, v are not features)
- The timestamp key `"t"` and `"symbol"` must NOT be included in the feature map

---

### Feature Constraints

| Constraint            | Rule                                                                 |
|-----------------------|----------------------------------------------------------------------|
| No NaNs               | Any `float("nan")` or `math.nan` in output is a hard failure        |
| Deterministic         | Identical input bars must always produce identical feature values    |
| No lookahead bias     | Features at index `i` may only use bars at indices `0` through `i`  |
| Flat output only      | No nested objects, lists, or non-numeric values permitted            |
| No side effects       | Feature functions must not write to cache, disk, or external state   |

---

### Feature Function Signature Contract

**All feature functions must accept only validated bar data and return flat numeric feature maps.**

Required signature shape:

```python
def compute_<feature_name>(bars: list[dict]) -> dict[str, float]:
    ...
```

- `bars` — validated bar dicts, ordered ascending by timestamp
- return — flat `dict[str, float]` representing features at the final bar in the window
- must raise `ValueError` if input list is too short to compute the feature

---

### Feature Layer Boundary Summary

| Boundary                        | Rule                                              |
|---------------------------------|---------------------------------------------------|
| Entry into feature layer        | Must pass bar_validator.py — no exceptions        |
| Exit from feature layer         | Flat numeric dict only                            |
| Raw price data in output        | Prohibited                                        |
| NaN in output                   | Prohibited                                        |
| Lookahead into future bars      | Prohibited                                        |
| External I/O inside feature fn  | Prohibited                                        |

---

## Signal Layer Contract

---

### Transformation: Features → Signals

The signal layer is the strict transformation boundary between feature values and strategy inputs.

```
validated bars → features (kernel.py) → FeatureSignal (signal_schema.py) → Strategy (Stage 5)
```

- Signal layer receives only `dict[str, float]` feature maps from `src/features/kernel.py`
- Signal layer produces only `FeatureSignal` objects defined in `src/signals/signal_schema.py`
- Signal layer has NO access to raw bar data
- Signal layer has NO strategy, portfolio, or order logic

---

### FeatureSignal Schema

```
FeatureSignal:
  timestamp:   datetime  — UTC-aware, aligned to source bar
  symbol:      str       — ticker (e.g. "GLD")
  signal_name: str       — stable name from SIGNAL_REGISTRY
  value:       float     — numeric signal value derived from features
  confidence:  float     — normalised score in [0.0, 1.0]
```

Enforced at construction via `__post_init__`:
- `confidence` outside `[0.0, 1.0]` → raises `ValueError`
- `timestamp` without UTC tzinfo → raises `ValueError`
- `value` or `confidence` is NaN → raises `ValueError`

---

### Signal Registry Contract

`src/signals/signal_registry.py` maps stable signal names to feature function references.

- Every signal name in `SIGNAL_REGISTRY` is permanent — rename requires versioning (e.g. `_v2`)
- Registry contains definitions only — no computation, no I/O, no execution logic
- All `feature_fn` references must point exclusively to functions in `src/features/kernel.py`

---

### Separation from Strategy Layer

| Layer          | Responsibility                                  | Prohibited                         |
|----------------|-------------------------------------------------|------------------------------------|
| Signal layer   | features → FeatureSignal                        | Bar data, strategy logic, orders   |
| Strategy layer | FeatureSignal → src.contracts.signal.Signal     | Feature computation, bar access    |

`FeatureSignal` is the handoff type. Strategies consume it; they do not produce it.
`src.contracts.signal.Signal` is the strategy output consumed by the allocator (Stage 6).

---

### Signal Layer Constraints

| Constraint              | Rule                                                      |
|-------------------------|-----------------------------------------------------------|
| Input                   | Feature dicts only — no bar dicts                         |
| Output                  | FeatureSignal only                                        |
| NaN                     | Prohibited in value and confidence                        |
| Determinism             | Same features → same FeatureSignal                        |
| Naming stability        | Signal names locked at implementation — versioned on change|
| Bar data access         | Prohibited in signal layer                                |
| Strategy logic          | Prohibited in signal layer                                |


---

## Signal Layer Taxonomy

---

### Signal Types

#### 1. FeatureSignal — `src/signals/signal_schema.py`

| Property       | Definition                                                   |
|----------------|--------------------------------------------------------------|
| Origin         | Derived directly from feature function outputs (kernel.py)   |
| Representation | Intermediate — not a trading decision                        |
| Tradable       | No — must never reach the execution layer                    |
| Usage          | Transformation input for strategy layer only                 |
| Fields         | `timestamp`, `symbol`, `signal_name`, `value`, `confidence`  |

#### 2. Strategy Signal — `src/contracts/signal.py`

| Property       | Definition                                                         |
|----------------|--------------------------------------------------------------------|
| Origin         | Produced exclusively by strategy logic (Stage 5)                   |
| Representation | Final trading decision object                                      |
| Tradable       | Yes — consumed by execution layer (Stage 8) via allocator (Stage 6)|
| Usage          | Passed to meta-allocator, risk layer, and execution engine         |
| Fields         | `symbol`, `direction`, `confidence`, `strategy_id`, `generated_at`, `metadata` |

---

### Hard Separation Rules

- `FeatureSignal` MUST NEVER be passed to the execution layer under any condition
- `Strategy Signal` MUST NEVER call or import feature functions from `src/features/`
- The only permitted conversion in the system is: `FeatureSignal → Strategy Signal`
- This conversion is the sole responsibility of the strategy layer (Stage 5)
- No layer below Stage 5 may produce a `Strategy Signal`
- No layer above Stage 4 may produce or modify a `FeatureSignal`

---

### Permitted Data Flow

```
kernel.py → FeatureSignal → [Strategy Layer] → Strategy Signal → Allocator → Execution
```

Any flow that bypasses this sequence is a contract violation.

---

### Naming Rule

`FeatureSignal` field names and `signal_name` values must never overlap with `Strategy Signal` field names.

| FeatureSignal fields              | Strategy Signal fields                          |
|-----------------------------------|-------------------------------------------------|
| `timestamp`                       | `generated_at`  ← different name, same concept |
| `symbol`                          | `symbol`        ← shared, permitted             |
| `signal_name`                     | `strategy_id`   ← different name, different role|
| `value`                           | *(no equivalent — not present in Strategy Signal)*|
| `confidence`                      | `confidence`    ← shared field name             |

**Rule:** `signal_name` values in `SIGNAL_REGISTRY` (e.g. `"signal_momentum_v1"`) must never
match any field name on `src.contracts.signal.Signal`. Registry key naming must use the
`signal_<feature>_v<n>` prefix convention to prevent collision.

---

### Debugging Rule

All log entries involving signals must explicitly label signal type.

- FeatureSignal log entries must include the prefix: `[FeatureSignal]`
- Strategy Signal log entries must include the prefix: `[StrategySignal]`
- Mixing or omitting the label in log output is a convention violation
- Example:
  - Correct: `[FeatureSignal] symbol=GLD signal_name=signal_momentum_v1 value=0.042`
  - Correct: `[StrategySignal] symbol=GLD direction=long strategy_id=momentum_basic confidence=0.7`
  - Incorrect: `Signal generated for GLD` ← type is ambiguous

---

### Taxonomy Enforcement Summary

| Rule                                          | Status    |
|-----------------------------------------------|-----------|
| FeatureSignal never reaches execution layer   | Enforced by layer boundary — Stage 5 converts |
| Strategy Signal never calls feature functions | Enforced by import prohibition in Stage 5      |
| Only one conversion path permitted            | FeatureSignal → Strategy Signal in Stage 5 only|
| No naming overlap between signal types        | Enforced by registry prefix convention         |
| Log entries label signal type explicitly      | Required in all logging from Stage 5 onward    |

---

## Baseline Strategy Contract

---

### Transformation: FeatureSignal → StrategySignal

`src/strategies/baseline_momentum.py` is the sole Stage 5 implementation.

- Input: `list[FeatureSignal]` — filtered to `signal_momentum_v1` only
- Output: exactly one `src.contracts.signal.Signal` per call
- Logic: threshold comparison on `momentum_v1` value — no ML, no optimisation

### Rules

| Rule                                    | Enforcement                                    |
|-----------------------------------------|------------------------------------------------|
| No direct feature function access       | Strategy imports from `src.signals` only       |
| No execution logic                      | No order, fill, or broker references           |
| No sizing logic                         | No quantity, weight, or allocation computation |
| One signal out per call                 | `generate()` returns a single `Signal`         |
| Stateless                               | No instance variables, no global state         |
| Missing required signal raises          | `ValueError` if `signal_momentum_v1` absent    |

### Thresholds (v1)

| Condition                  | Direction | Confidence                              |
|----------------------------|-----------|-----------------------------------------|
| `momentum_v1 > +0.02`      | LONG      | `min(value / 0.10, 1.0)`               |
| `momentum_v1 < -0.02`      | SHORT     | `min(abs(value) / 0.10, 1.0)`          |
| Otherwise                  | FLAT      | `0.0`                                   |

---

## Strategy Evaluation Contract

**Evaluation does not influence live strategy behavior in Stage 6.**

---

### Scope

The evaluation layer consumes `StrategySignal` outputs (`src.contracts.signal.Signal`) and
realized return series only. It produces observational metrics — no feedback into strategy logic.

### Rules

| Rule                                         | Enforcement                                      |
|----------------------------------------------|--------------------------------------------------|
| Input is StrategySignal only                 | No FeatureSignal, no bar data, no feature fns    |
| No execution system access                   | No broker, order, or position references         |
| No raw feature access                        | Evaluation imports from `src.contracts` only     |
| Metrics are read-only observations           | No return value modifies strategy or signal state|
| Stateless and deterministic                  | Same inputs → same metric outputs always         |

### Metrics (v1)

| Function                  | Output              | Description                              |
|---------------------------|---------------------|------------------------------------------|
| `directional_accuracy`    | `float`             | Fraction of non-FLAT signals correct     |
| `signal_frequency`        | `dict[str, float]`  | Proportion of LONG / SHORT / FLAT        |
| `average_confidence`      | `float`             | Mean confidence across all signals       |
| `long_short_distribution` | `dict[str, int]`    | Raw counts of each direction             |

---

## Replay Engine Contract

**Replay is orchestration infrastructure, not backtesting.**

---

### Scope

`src/replay/replay_engine.py` orchestrates deterministic sequential processing of historical
bars. It wires validation → features → signals → strategy into a single ordered pipeline.
It produces no execution decisions, tracks no portfolio state, and performs no PnL accounting.

### Processing Sequence (per bar)

```
bar → validate_bar() → rolling window → SIGNAL_REGISTRY → FeatureSignals
    → baseline_momentum.generate() → Signal → output list
```

### Rules

| Rule                                         | Enforcement                                       |
|----------------------------------------------|---------------------------------------------------|
| Input is historical bar list only            | No live feed, no broker connection                |
| Output is ordered list[Signal] only          | No orders, positions, cash, or PnL in output      |
| Invalid bars are skipped silently            | Replay remains deterministic on partial bad data  |
| No portfolio state maintained                | Window is rolling bar buffer only                 |
| No execution simulation                      | No fill logic, slippage, or order tracking        |
| Deterministic                                | Same bar list → same Signal list always           |
| Single-threaded sequential only              | No async, no multiprocessing, no threading        |

---

## Replay Observability Contract

**Observability must never influence replay behavior.**

---

### Scope

`src/observability/replay_logger.py` provides passive, append-only in-memory event recording
for replay runs. It records what happened — it cannot alter signals, features, or strategy outputs.

### Event Schema

```
ReplayEvent:
  timestamp:   datetime  — UTC-aware, aligned to bar being processed
  event_type:  str       — one of the canonical EVENT_* constants
  symbol:      str       — ticker associated with the event
  stage:       str       — source stage ("replay", "feature", "signal", "strategy")
  metadata:    dict      — flat key/value context, no nested objects
```

### Canonical Event Types

| Constant                       | Value                      | Emitted when                          |
|-------------------------------|----------------------------|---------------------------------------|
| `EVENT_INVALID_BAR_SKIPPED`   | `invalid_bar_skipped`      | Bar fails `bar_validator.py`          |
| `EVENT_FEATURE_GENERATION`    | `feature_generation`       | Feature value computed from window    |
| `EVENT_FEATURE_SIGNAL_CREATED`| `feature_signal_created`   | `FeatureSignal` object created        |
| `EVENT_STRATEGY_SIGNAL_CREATED`| `strategy_signal_created` | `Signal` emitted by strategy          |

### Rules

| Rule                                           | Enforcement                                      |
|------------------------------------------------|--------------------------------------------------|
| Logger is optional (`None` by default)         | `run()` behaves identically with or without logger|
| Events are append-only                         | No delete, update, or reorder methods on logger  |
| `events()` returns a copy                      | Internal list is never exposed directly          |
| Logger cannot modify signals or features       | Logger receives data after computation only      |
| Deterministic event ordering                   | Events appended in bar processing order          |
| No file I/O                                    | In-memory only at this stage                     |

---

## Execution Simulation Contract

**Simulation correctness precedes broker realism.**

---

### Scope

`src/execution/simulator.py` is a deterministic local simulation layer for replay validation.
It is not broker execution. It has no Alpaca integration, no network I/O, and no order routing.

### Fill Rules

| Signal    | Simulator Action                                 |
|-----------|--------------------------------------------------|
| LONG      | Open long at close price if flat; no-op if already long |
| SHORT     | Open short at close price if flat; no-op if already short |
| FLAT      | Close open position at close price; no-op if flat |

- Fills occur exactly at bar close price
- No slippage, no commissions, no partial fills
- Fixed unit quantity (1.0) — no sizing logic

### State Tracked

| Field           | Type              | Description                        |
|-----------------|-------------------|------------------------------------|
| `position`      | `Position \| None` | Current open position or None     |
| `realized_pnl`  | `float`           | Cumulative closed PnL              |
| `unrealized_pnl`| `float`           | Open position mark-to-market PnL  |
| `fills`         | `list[FillRecord]`| Ordered fill history               |

### Rules

| Rule                                     | Enforcement                                   |
|------------------------------------------|-----------------------------------------------|
| Input is StrategySignal only             | No feature data, no bar data, no raw prices   |
| Close price passed explicitly per bar    | No internal market data access                |
| Single-symbol only                       | No portfolio or multi-position logic          |
| No broker integration                    | Local in-memory state only                    |
| Deterministic                            | Same signal + price sequence → same state     |
| No leverage, margin, or risk engine      | Out of scope for this stage                   |

---

## Broker Abstraction Contract

**Broker layer is a translation layer only, not a strategy or risk engine.**

---

### Scope

`src/brokers/` provides an execution-agnostic broker interface and a paper-only implementation.
The broker layer translates StrategySignals into Order objects and delegates fill logic to
`ExecutionSimulator`. It does not implement strategy logic, risk control, or portfolio management.

### Signal → Order Mapping

| SignalDirection | OrderSide | Action                        |
|-----------------|-----------|-------------------------------|
| LONG            | BUY       | Open long via simulator       |
| SHORT           | SELL      | Open short via simulator      |
| FLAT            | SELL      | Close open position           |
| No-op (repeated)| —         | Order status → REJECTED       |

### Interface

`BrokerBase` (abstract) defines four methods all broker implementations must satisfy:

| Method               | Responsibility                                      |
|----------------------|-----------------------------------------------------|
| `submit_order`       | Translate signal → Order, execute via simulator     |
| `cancel_order`       | Cancel pending order by ID                          |
| `get_positions`      | Return current open positions as `list[Position]`   |
| `get_account_state`  | Return flat dict: realized_pnl, unrealized_pnl, etc.|

### Rules

| Rule                                          | Enforcement                                      |
|-----------------------------------------------|--------------------------------------------------|
| Broker interface is execution-agnostic        | `BrokerBase` has no simulator or API references  |
| `PaperBroker` is simulation-only              | No HTTP calls, no Alpaca SDK, no credentials     |
| `ExecutionSimulator` logic is unchanged       | Broker wraps simulator — never modifies it       |
| Alpaca adapter is a future drop-in            | Implements `BrokerBase` — no other changes needed|
| Deterministic                                 | Same signal + price → same Order state always    |

---

## Risk Engine Contract

**Risk decisions happen before execution, never after.**

---

### Scope

`src/risk/risk_engine.py` is a pre-execution signal filter. It receives a `StrategySignal`
and current `SimulatorState`, evaluates deterministic safety constraints, and returns a
`RiskDecision`. It never executes trades, never calls the broker, and never modifies signals.

### Execution Path

```
StrategySignal → RiskEngine.evaluate() → RiskDecision
    → if allowed: ExecutionSimulator.process() → PaperBroker
    → if blocked: signal discarded, reason logged
```

### Enforced Constraints

| Constraint              | Default          | Description                                      |
|-------------------------|------------------|--------------------------------------------------|
| Max position size       | 1.0              | Max absolute quantity in any direction           |
| Max daily loss          | -500.0           | Halt if realized PnL ≤ threshold                 |
| Max drawdown            | -1000.0          | Halt if peak-to-trough realized loss ≤ threshold |
| Max consecutive losses  | 4                | Halt after N consecutive losing closes           |
| Exposure cap            | 1.0              | Max directional quantity in either direction     |
| Cooldown window         | 60s              | Minimum seconds between accepted trades          |

### RiskDecision Schema

```
RiskDecision:
  allowed:       bool   — True if signal may proceed to execution
  reason:        str    — human-readable constraint label
  adjusted_size: float  — populated only when allowed=True
```

### Rules

| Rule                                           | Enforcement                                        |
|------------------------------------------------|----------------------------------------------------|
| FLAT signals always pass                       | Closing positions is never blocked                 |
| RiskEngine does not modify signals             | Signal object is read-only input                   |
| RiskEngine does not execute trades             | No simulator or broker calls inside evaluate()     |
| RiskEngine is the only layer that rejects trades| Strategy and replay layers never filter signals   |
| Deterministic                                  | Same signal + same state → same RiskDecision       |
| Minimal state                                  | Only last accepted timestamp and peak PnL tracked  |

---

## Backtest Orchestration Contract

**Orchestration is coordination, not intelligence.**

---

### Scope

`src/orchestration/backtest_runner.py` is the single entry point for full system runs.
It composes all subsystems in strict deterministic order without modifying any of them.
It introduces no trading logic, no risk rules, and no evaluation heuristics of its own.

### Execution Order (per bar, non-negotiable)

```
1. validate_bar()
2. accumulate rolling window
3. SIGNAL_REGISTRY → feature maps
4. FeatureSignal construction
5. momentum_strategy.generate() → StrategySignal
6. RiskEngine.evaluate() → RiskDecision
7. if allowed → ExecutionSimulator.process()
8. update_price() + equity snapshot
```

No step may be reordered. No step may be skipped.

### BacktestResult Schema

```
BacktestResult:
  signals:             list[Signal]       — all StrategySignals emitted
  trades:              list[FillRecord]   — all simulator fills
  equity_curve:        list[EquityPoint]  — realized + unrealized PnL per bar
  risk_events:         list[RiskEvent]    — all signals blocked by RiskEngine
  evaluation_metrics:  dict               — summary stats (pnl, frequency, confidence, etc.)
```

### Rules

| Rule                                           | Enforcement                                          |
|------------------------------------------------|------------------------------------------------------|
| BacktestRunner is the only full-run entry point| No other module runs the complete pipeline           |
| Subsystems are composed, never modified        | Runner calls existing APIs — no internal changes     |
| Deterministic and reproducible                 | Same bars → same BacktestResult always               |
| No broker calls                                | ExecutionSimulator used directly — no PaperBroker    |
| No file I/O                                    | In-memory only                                       |
| RiskEngine is injected — swappable             | Default RiskEngine used if none provided             |

---

## Paper Broker Contract (Alpaca)

**Broker layer is execution transport only, never logic.**

---

### Scope

`src/brokers/alpaca_paper_broker.py` is a real external API adapter for Alpaca's paper trading
endpoint. It is isolated from all simulation systems. It does not influence `BacktestRunner`,
`ReplayEngine`, `ExecutionSimulator`, or any strategy or risk layer.

### Environment Configuration

| Variable           | Required | Description                              |
|--------------------|----------|------------------------------------------|
| `ALPACA_API_KEY`   | Yes      | Alpaca API key (paper account)           |
| `ALPACA_SECRET_KEY`| Yes      | Alpaca secret key (paper account)        |
| `ALPACA_PAPER`     | Implicit | Paper endpoint hardcoded — always `true` |

**Live trading is disabled by default.**
The paper endpoint `https://paper-api.alpaca.markets` is hardcoded.
No live endpoint (`live-api.alpaca.markets`) is referenced anywhere in this file.
Missing credentials raise `EnvironmentError` immediately at construction.

### Signal → Alpaca Order Mapping

| SignalDirection | Alpaca Action                          |
|-----------------|----------------------------------------|
| LONG            | `MarketOrderRequest` side=BUY, qty=1   |
| SHORT           | `MarketOrderRequest` side=SELL, qty=1  |
| FLAT            | `close_position(symbol)` API call      |

### Rules

| Rule                                              | Enforcement                                         |
|---------------------------------------------------|-----------------------------------------------------|
| Paper endpoint only                               | URL hardcoded — no env override for live            |
| No ExecutionSimulator reference                   | Verified by AST import check in tests               |
| Drop-in compatible with BrokerBase                | Implements all 4 abstract methods                   |
| Fails safely on missing credentials               | EnvironmentError raised at `__init__`               |
| No strategy or risk logic                         | Adapter translates only — no decisions made         |
| All API interactions logged minimally             | `print` prefixed `[AlpacaPaperBroker]` per call     |
| AlpacaPaperBroker does not affect BacktestRunner  | BacktestRunner uses ExecutionSimulator directly      |
