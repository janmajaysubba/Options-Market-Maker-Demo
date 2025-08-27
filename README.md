# Options-Market-Maker-Demo

This project implements a toy options market-making system in Python.



## Features
- Option pricing via Cox–Ross–Rubinstein binomial tree model 
- Implied volatility solver using the bisection method
- Fetch live option chain data from Yahoo Finance (yfinance)
- Batch IV computation across strikes and expiries with multiprocessing
- Inventory-aware quoting: bid/ask generation with configurable edge + inventory bias
- Risk tracking with real-time delta and vega exposures
- Dynamic hedging:
  - Delta hedging with underlying shares
  - Soft vega hedging using same-expiry ATM options
- Market-making loop that:
  - Simulates a small random move of the spot price every tick (default 3s)
  - Refreshes IV surface periodically (default 15s)
  - Updates quotes every tick (default 3s)
  - Simulates fills every tick (default 3s) with probabilistic execution
  - Updates risk exposures and applies hedges automatically after every fill
- Logging & persistence:
  - RiskBook state saved/reloaded across runs
  - Quotes, fills, and hedges exported to CSV for analysis

## Key Modules

# 1) pricer.py
- Implements the Cox–Ross–Rubinstein (CRR) binomial option pricer.
- Supports both American (early exercise) and European options.
- Uses vectorized backward induction for speed and numerical stability.
- Inputs: spot S, strike K, time-to-expiry T, risk-free rate r, dividend yield q, volatility σ.
- Outputs: fair option value.
- Does not compute Greeks directly, but serves as the pricing engine for other modules (e.g., risk_tracker.py) that derive Greeks.

# 2) iv_solver.py
- Solves for implied volatility using a robust bisection method.
- Guardrails:
  - Rejects prices outside theoretical bounds [intrinsic,cap].
  - Expands brackets when initial guesses fail.
- Soft caching: reuses last solved IVs per (expiry, strike) for faster warm starts.
- If convergence fails, falls back to midpoint volatility to avoid surface gaps.

# 3) batch_surface.py
- Pulls option chains and computes IVs in parallel across strikes and expiries.
- Contract filters:
  - Moneyness band (default 85–115% of spot).
  - Liquidity filter (skips options with spreads > 20% of mid).
- Builds a mini implied volatility surface (DataFrame grid: expiry × strike).
- Uses multiprocessing for performance on large chains.

# 4) live_data.py
- Handles live option chain retrieval from Yahoo Finance (yfinance).
- Functions include:
  - Fetching spot price of the underlying.
  - Fetching full option chain (calls + puts).
  - Converting raw Yahoo data into clean DataFrames for downstream modules.
- Ensures consistent and centralized access to underlying spot prices and option chain data, so all modules use the same snapshot of market data.
- Includes lightweight error handling for missing/illiquid strikes.

# 5) mm_quote.py
- Generates market-maker bid/ask quotes from pricer fair values.
- Adjustments applied:
  - Edge (absolute or relative).
  - Inventory biasing (skews mids based on net delta/vega).
- Outputs structured quote dictionaries / DataFrames for simulated execution.

# 6) risk_tracker.py
- Computes Greeks by bumping spot or vol slightly and re-calling pricer.py to numerically estimate delta and vega.
- Tracks risk exposures:
  - Net delta (options + underlying).
  - Net vega (per expiry).
- Maintains inventory book:
  - Option positions.
  - Underlying hedges.
- Computes PnL:
  - Realized PnL (executed trades).
  - Unrealized PnL (mark-to-market).
- Persists state in JSON files → enables simulation resume/replay.

# 7) mm_vega.py
- Implements soft vega hedging logic.
- Chooses ATM option in the same expiry for hedging (avoids cross-expiry risk).
- Keeps exposures within a configurable band (default ±5 vega per expiry).
- Partial hedging (fraction of excess) ensures smoother adjustments.

# 8) mm_loop_realtime.py
- The main orchestrator loop that ties all modules together.
- Responsibilities:
  - Refresh IV surface every 15s.
  - Simulate spot as a toy GBM random walk.
  - Quote a set of strikes/expiries.
  - Simulate random fills (probability-based).
  - Update risk tracker after trades.
  - Apply delta hedges when thresholds breached.
  - Apply soft vega hedges with ATM options.
- Logging & output:
  - Quotes, fills, hedges → CSV logs in logs/.
  - Console summary of per-expiry risk and PnL at the end.

## Limitations
- Fills are random (no real order flow).
- Spot is a toy random walk (not the actual market).
- Quotes are recomputed at fixed intervals; inventory bias is basic and not dynamically optimized.
- The option pricing model (assuming continuous dividend yield, not discrete) and the IV solving method used are accurate, but not fast enough. (Building IV surfaces for 2 epiries with 40-50 strikes takes around 2-4 secs on MacBook Air M2)
- Limited hedging logic: only basic delta-hedging and soft vega management are implemented
- No transaction costs, slippage, or latency modeling.

This project is intended as a research and educational experiment and is not yet suitable for live trading.

## Requirements
- NumPy
- Pandas
- yfinance

Install dependencies:
```bash
pip install numpy pandas yfinance
```
## Usage
Clone the repo and keep all `.py` modules in the same directory (default structure).
Then, to run the market-making loop:

```bash
python mm_loop_realtime.py
```

