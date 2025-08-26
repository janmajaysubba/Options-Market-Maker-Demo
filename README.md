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
- Matplotlib
- yfinance

Install dependencies:
```bash
pip install numpy pandas matplotlib yfinance
