# Architecture

---

## Feature Kernel Scope

**Stage 4 is infrastructure for feature correctness, not alpha generation.**

---

### Scope

Stage 4 is restricted to a minimal, deterministic feature core.
Its sole purpose is to produce reliable, validated numeric features from validated bar data.
No strategy logic, no signal generation, and no alpha research belongs here.

---

### Allowed Features (Initial)

| Feature            | Description                                              |
|--------------------|----------------------------------------------------------|
| Log return         | `ln(c[t] / c[t-1])` — single-period log return          |
| Rolling volatility | Std dev of log returns over a rolling window             |
| Simple momentum    | `c[t] / c[t-n] - 1` — n-period price momentum           |

No other features may be added to Stage 4 without an explicit scope extension decision.

---

### Prohibited in Stage 4

- ML models of any kind
- Regime detection or classification
- Multi-asset or cross-asset features
- External data sources (macro, sentiment, alternatives)
- Strategy logic or signal generation
- Any stateful computation that persists across calls

---

### Feature Requirements

All Stage 4 feature functions must:

- Accept only validated bar input (`list[dict]` passed through `bar_validator.py`)
- Be stateless — no instance variables, no external state, no caching inside the function
- Return a flat `dict[str, float]` — no nested objects, no NaNs, no raw OHLCV fields
- Be unit-testable in isolation with synthetic bar input
- Raise `ValueError` if the input window is too short to compute the feature

---

### Feature Identity Stability Rule

Feature names and definitions are permanent once implemented.

- Every feature must have a stable semantic definition locked at the time of implementation
- Feature output key names must never be changed after first use
- Any modification to computation logic requires a new versioned name (e.g. `momentum_v2`)
- The original versioned function must be preserved — not overwritten
- Backtests must explicitly declare the feature version set used at the time of the run
- Silent substitution of one feature version for another is prohibited

This rule exists to prevent silent backtest divergence across development iterations.

---

### Stage 4 Boundary Rule

| Allowed                                      | Prohibited                          |
|----------------------------------------------|-------------------------------------|
| Log return, rolling volatility, momentum     | ML models                           |
| Stateless pure functions                     | Regime detection                    |
| Flat numeric output                          | Multi-asset features                |
| Validated bar input only                     | External data sources               |
| Independent unit tests per feature           | Strategy or signal logic            |
| Versioned feature names on modification      | Silent redefinition of feature keys |

---

## Signal Composition Constraints

**Stage 5 is deterministic signal translation only, not alpha research.**

---

### Purpose

Stage 5 has exactly one responsibility: convert `FeatureSignal` objects into `StrategySignal`
(`src.contracts.signal.Signal`) objects using deterministic, stateless rules.

No portfolio construction, no execution logic, and no cross-asset aggregation belongs here.

---

### Allowed Operations

| Operation                   | Description                                                       |
|-----------------------------|-------------------------------------------------------------------|
| Threshold-based rules       | e.g. `if momentum_v1 > 0.02 → direction = LONG`                  |
| Linear feature combinations | Weighted sum of feature values to derive confidence score         |
| Simple deterministic mappings | Fixed lookup or conditional logic on feature values             |

All allowed operations must be:
- Stateless — no memory of prior signals or bars
- Deterministic — same `FeatureSignal` input always produces the same `StrategySignal`
- Single-symbol — one `StrategySignal` per symbol per timestamp, no cross-asset logic

---

### Prohibited Operations

- ML models of any kind (classification, regression, neural networks)
- Reinforcement learning or any adaptive policy
- Optimisation loops (grid search, gradient descent, parameter fitting)
- Cross-asset or portfolio-level construction
- Order sizing, position sizing, or risk weighting
- Any operation that reads from or writes to external state

---

### Output Contract

- Each strategy must produce exactly **one** `StrategySignal` per symbol per timestamp
- Multiple signals for the same symbol at the same timestamp is a contract violation
- Output type is exclusively `src.contracts.signal.Signal`
- `FeatureSignal` must never appear in strategy output or be passed downstream of Stage 5

---

### Stage 5 Boundary Rule

| Allowed                                         | Prohibited                              |
|-------------------------------------------------|-----------------------------------------|
| FeatureSignal → StrategySignal conversion       | ML or adaptive models                   |
| Threshold and linear mapping logic              | Reinforcement learning                  |
| Stateless deterministic functions               | Optimisation loops                      |
| Single StrategySignal per symbol per timestamp  | Cross-asset aggregation                 |
| Import from `src.signals` and `src.contracts`   | Order or position sizing logic          |
|                                                 | Direct feature function calls           |
|                                                 | Raw bar data access                     |

---

## Runtime Execution Model

**Subsystems do not know execution mode. Only the router does.**

---

### Execution Modes

| Mode       | Backend                  | Default | Notes                                          |
|------------|--------------------------|---------|------------------------------------------------|
| BACKTEST   | BacktestRunner + Simulator| ✅ Yes  | Deterministic, local, no external calls        |
| PAPER      | AlpacaPaperBroker        | No      | Requires ALPACA_API_KEY_PAPER + ALPACA_SECRET_KEY_PAPER |
| LIVE       | AlpacaPaperBroker        | ❌ No   | Disabled by default — requires explicit gate   |

### LIVE Mode Safety Gate

LIVE mode requires ALL of the following to be true simultaneously:
- `STRICT_MODE=false`
- `ALLOW_LIVE_TRADING=true`

If either condition fails → `RuntimeError` raised immediately. No fallback. No partial execution.

### Environment Variables

| Variable                       | Default     | Description                                   |
|--------------------------------|-------------|-----------------------------------------------|
| `RUNTIME_MODE`                 | `backtest`  | Active execution mode                         |
| `SYMBOL`                       | `GLD`       | Trading symbol                                |
| `STRICT_MODE`                  | `true`      | Disables LIVE mode entirely when true         |
| `ALLOW_LIVE_TRADING`           | `false`     | Must be explicitly `true` to unlock LIVE      |
| `ALPACA_API_KEY_PAPER`         | —           | Paper key, read only via `load_broker_config()` |
| `ALPACA_SECRET_KEY_PAPER`      | —           | Paper secret, read only via `load_broker_config()` |

> **Retired.** `ALPACA_PAPER_ENABLED` was removed. It populated two duplicate config
> fields (`paper_broker_enabled`, `alpaca_enabled`) that no subsystem ever read, and
> it contradicted the credential contract above. Credential access now goes through
> a single `load_broker_config()`.
>
> **Known gap.** LIVE mode still routes to `AlpacaPaperBroker`, which pins its
> endpoint to paper via `url_override`. This system has no live execution path at all.

### Routing Rules (ExecutionRouter)

```
RUNTIME_MODE=backtest → BacktestRunner()
RUNTIME_MODE=paper    → AlpacaPaperBroker()
RUNTIME_MODE=live     → RuntimeError (default)
                      → AlpacaPaperBroker() ONLY if STRICT_MODE=false AND ALLOW_LIVE_TRADING=true
```

### Architectural Rules

| Rule                                                  | Enforcement                                  |
|-------------------------------------------------------|----------------------------------------------|
| LIVE is never the default                             | Default env resolves to BACKTEST             |
| No subsystem receives RuntimeMode                     | Router injects backend — mode is not passed  |
| Router does not modify backends                       | get_backend() instantiates only              |
| main.py contains no trading logic                     | Entry point delegates entirely to router     |
| Each get_backend() call returns a fresh instance      | No shared mutable state across calls         |
