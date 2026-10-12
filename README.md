# GLD Trading Platform

A staged, strictly layer-separated trading system for the GLD ETF, built in
stages with deterministic validation gates between them.

**Paper trading only.** There is no live-trading safety certification, no slippage
modelling in the broker, and no portfolio accounting beyond Alpaca being the source
of truth.

```bash
pip install -r requirements-dev.txt
cp .env.example .env
python -m pytest tests -q      # 112 passed
python src/main.py
```

---

## Why this repository looks the way it does

The hardest part of this project was not the strategy. It was keeping four layers
from reaching into each other:

```
features  →  signals  →  strategies  →  execution  →  risk
```

Most bugs during the build were **boundary violations**, not logic errors — a
strategy importing a broker, a feature reading a config value, a risk check
depending on which signal path produced the signal. The response was
`src/core/stage_gate_validator.py`, which parses the source with `ast` and refuses to
let a stage complete if a layer imports something it should not.

That validator is the most interesting file here, and the reason the rest of the
codebase can be trusted to be as separated as it claims.

## Architecture

| Layer | Module | Responsibility |
|---|---|---|
| features | `src/features/` | Pure numeric computation. Stateless functions, `list[dict]` bars in, `dict[str, float]` out. No I/O. |
| signals | `src/signals/` | Definitions only — name → feature function + params. No strategy or execution logic. |
| strategies | `src/strategies/` | Consumes `FeatureSignal`, emits `Signal`. Stateless and deterministic. |
| execution | `src/execution/` | Fills and positions. `ExecutionSimulator`, `FillRecord`, `SimulatorState`. |
| risk | `src/risk/` | `RiskEngine.evaluate()` → `RiskDecision`. Read-only; no execution logic. |
| brokers | `src/brokers/` | Translation layer only. `BrokerBase` ABC, `PaperBroker`, `AlpacaPaperBroker`. |
| runtime | `src/runtime/` | Mode routing. `ExecutionRouter` selects a backend and never mutates one. |
| portfolio | `src/portfolio/` | Reconciles internal state against Alpaca. **Alpaca is truth.** |
| core | `src/core/` | `StageGateValidator` — the architectural gate. |

### Two rules enforced mechanically

**1. Feature identity stability.** Any change to a feature's computation requires a
new versioned name (`momentum_v2`). Silent substitution of one version for another
is prohibited, because it silently invalidates historical backtests.

**2. Stage gates.** Before a stage counts as complete:

```
StageGateValidator.run(stage="14.3")
# -> {"status": "PASS"|"FAIL", "checks": {syntax, imports, api_contract, drift}, ...}
```

It runs `ast.parse` over `src/`, imports the public API to confirm it exists, checks
ten required exports, and then hunts for drift: forbidden symbols, cross-layer
imports under `src.execution`, `src.strategies`, `src.risk`, `src.brokers`,
`src.orchestration`, `src.runtime`, and renamed public functions.

### Reconciliation: Alpaca is truth

`src/portfolio/reconciler.py` detects six kinds of divergence between internal
state and what Alpaca reports:

`missing_fill` · `qty_mismatch` · `order_status_mismatch` · `stale_snapshot` ·
`unexpected_position` · `missing_position`

The function is pure and read-only. It returns the Alpaca snapshot **unchanged**.
Internal state is never allowed to overwrite the broker's view — the reconciler's
job is to report drift, not to resolve it by assuming itself right.

## Testing

```
$ python -m pytest tests -q
112 passed
```

Notable coverage: the runtime router's live-mode gates, the broker's credential
guard, replay determinism and event ordering, and the portfolio reconciler's six
drift detectors.

### A note on the credential-guard tests

Two of these tests only failed on the machine where this was built, because
`ALPACA_*_PAPER` were set at the Windows registry level and leaked into every
process. They now clear all four variable names with `monkeypatch`, so they are
hermetic. **A test whose result depends on ambient machine state is not a test.**

If you see "passes on my machine" failures in a trading repo, check your environment
before you check your code.

## Status and limitations

- Paper trading works end-to-end on Alpaca, including small notional trades.
- **No live-trading safety certification.** Do not point this at real money.
- **No slippage modelling in the broker.**
- **No portfolio accounting layer** beyond the reconciler reporting drift.
- The `BrokerConfig.base_url` passed to `AlpacaPaperBroker` was previously ignored,
  so LIVE mode silently used the paper endpoint. The broker now pins its endpoint
  explicitly via `url_override`.

## What I did vs. what the AI agents did

Built with AI coding agents. The developer designed the layer boundaries, wrote the
stage-gate concept, and specified the reconciler's "Alpaca is truth" invariant. The
agents wrote most of the implementation. The 13 failing tests in this repository at
the time of publication were a half-finished refactor, not a design problem — see
the commit history note below.

## History

This repository was published as a single squashed commit. The original history
contained a `.env` with live Alpaca credentials in commit `7b2e49c`; those keys have
been rotated and the squashed history never contains a `.env`. Squashing was the
cheapest way to guarantee that.

## Licence

MIT. No affiliation with Alpaca Markets or the SPDR Gold Shares Trust.
