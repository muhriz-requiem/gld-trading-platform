📒 GLD Trading Platform — Personal Development Notes

✔ What I built so far



I built a full modular trading system:



Data ingestion (Alpaca)

Feature engineering (basic quant signals)

Strategy layer (momentum baseline)

Signal pipeline separation (feature → signal → strategy → execution)

Backtesting engine

Execution simulator

Risk management engine

Paper trading broker (Alpaca)

Runtime routing system

Logging + observability

✔ What finally works

Paper trading works on Alpaca

Notional trading ($50 style trades) works

System executes signals end-to-end

Orders are accepted and processed correctly

⚠ Issues I had to fix along the way

Alpaca API field mismatches (unrealized\_pl missing)

Constructor mismatch in broker/router

Notional vs qty trading confusion

PowerShell execution policy blocking venv activation

Market-closed order delays causing confusion

Duplicate config logic across runtime + broker layers

🧠 Key design insight I learned



The hardest part was NOT strategy — it was:



clean separation between:

signal generation

execution layer

broker API constraints



Most bugs came from boundary violations.



💡 Current system limitation

No live trading safety certification yet

No real portfolio accounting layer (Alpaca is source of truth)

No slippage modeling in broker

No cloud deployment yet

🚀 Next steps (when continuing later)

Improve execution reliability layer

Add cloud deployment option

Add proper portfolio state sync engine

Add multi-symbol support (optional future stage)

🧭 Mental model going forward



Think in stages, not features:



Each stage = isolated, testable subsystem



Never:



mix execution + strategy logic

modify multiple layers at once

refactor everything at once

