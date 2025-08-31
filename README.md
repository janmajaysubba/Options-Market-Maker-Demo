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

## Example Output

When the program starts, the specified ticker’s spot price, expiries, and option chain are pulled from Yahoo Finance. The first implied volatility (IV) surface is then constructed:

```yaml
Building IV surface...
IV surface built in 3.219 seconds
Batched IV surface to grid in 0.005 seconds
Init spot=645.0500 | expiries=('2025-09-02', '2025-09-03') | strikes=45

--- running live loop ---
```

**Live Loop (1 minute demo)**

During the loop, the spot price is simulated as a random walk and updated every tick (default: 3s).
At each tick, new quotes are generated, fills may occur, hedges are applied, and the IV surface is refreshed periodically (default: 15s).

```yaml
Tick: spot=645.2987
  QUOTE K=630.0 IV=0.1075 | FV_raw=15.4383 FV_adj=15.4296 → 15.3525/15.5068
    FILL: SOLD   1 @ 15.51 | Δ=+0.99, V=+0.1725
  QUOTE K=631.0 IV=0.1207 | FV_raw=14.4471 FV_adj=14.4384 → 14.3662/14.5106
    FILL: SOLD   1 @ 14.51 | Δ=+0.98, V=+0.7043
  QUOTE K=632.0 IV=0.1218 | FV_raw=13.4558 FV_adj=13.4470 → 13.3798/13.5143
  QUOTE K=633.0 IV=0.1223 | FV_raw=12.4691 FV_adj=12.4604 → 12.3981/12.5227
  QUOTE K=634.0 IV=0.1214 | FV_raw=11.4867 FV_adj=11.4780 → 11.4206/11.5353
    FILL: BOUGHT 1 @ 11.42 | Δ=+0.95, V=+2.2229
  QUOTE K=635.0 IV=0.1195 | FV_raw=10.5095 FV_adj=10.5007 → 10.4482/10.5532
  QUOTE K=601.0 IV=0.2446 | FV_raw=44.4985 FV_adj=44.4566 → 44.2343/44.6789
    FILL: BOUGHT 1 @ 44.23 | Δ=+1.00, V=+0.1274
  QUOTE K=602.0 IV=0.2369 | FV_raw=43.4985 FV_adj=43.4566 → 43.2393/43.6739
  QUOTE K=604.0 IV=0.2201 | FV_raw=41.4985 FV_adj=41.4567 → 41.2494/41.6639
  QUOTE K=605.0 IV=0.2114 | FV_raw=40.4986 FV_adj=40.4567 → 40.2544/40.6590
  QUOTE K=606.0 IV=0.2342 | FV_raw=39.5031 FV_adj=39.4612 → 39.2639/39.6585
  QUOTE K=607.0 IV=0.2274 | FV_raw=38.5031 FV_adj=38.4613 → 38.2690/38.6536
Risk: Δ_options(sh)=+402, Δ_total(sh)=-3, vega={'2025-09-02': -1.8127, '2025-09-03': 0.2879}

Tick: spot=644.6829
  QUOTE K=630.0 IV=0.1075 | FV_raw=14.8234 FV_adj=14.8013 → 14.7273/14.8753
  QUOTE K=631.0 IV=0.1207 | FV_raw=13.8354 FV_adj=13.8132 → 13.7442/13.8823
    FILL: BOUGHT 1 @ 13.74 | Δ=+0.98, V=+1.0587
  QUOTE K=632.0 IV=0.1218 | FV_raw=12.8472 FV_adj=12.8251 → 12.7609/12.8892
    FILL: BOUGHT 1 @ 12.76 | Δ=+0.97, V=+1.5541
  QUOTE K=633.0 IV=0.1223 | FV_raw=11.8650 FV_adj=11.8429 → 11.7837/11.9021
  QUOTE K=634.0 IV=0.1214 | FV_raw=10.8879 FV_adj=10.8658 → 10.8115/10.9201
  QUOTE K=635.0 IV=0.1195 | FV_raw=9.9171 FV_adj=9.8949 → 9.8455/9.9444
  QUOTE K=601.0 IV=0.2446 | FV_raw=43.8831 FV_adj=43.8400 → 43.6208/44.0592
    FILL: SOLD   1 @ 44.06 | Δ=+1.00, V=+0.1274
  QUOTE K=602.0 IV=0.2369 | FV_raw=42.8831 FV_adj=42.8400 → 42.6258/43.0542
  QUOTE K=604.0 IV=0.2201 | FV_raw=40.8830 FV_adj=40.8399 → 40.6357/41.0441
  QUOTE K=605.0 IV=0.2114 | FV_raw=39.8830 FV_adj=39.8399 → 39.6407/40.0391
  QUOTE K=606.0 IV=0.2342 | FV_raw=38.8883 FV_adj=38.8452 → 38.6509/39.0394
  QUOTE K=607.0 IV=0.2274 | FV_raw=37.8883 FV_adj=37.8451 → 37.6559/38.0344
DELTA HEDGE: traded -93 sh → Δ_total(sh)=+0
Risk: Δ_options(sh)=+498, Δ_total(sh)=+0, vega={'2025-09-02': 0.3472, '2025-09-03': 0.2196}
[surface] rebuilt in 3.35s, rows=67
```

**Final Summary**

At the end of the run, the program prints a complete snapshot of trades, hedges, PnL, and current risk exposures:

```yaml
--- summary ---
Fills: 65 | Delta hedges: 13 | Vega hedges: 0

Final spot ~ 648.2691

Realized PnL:   -414.79
Unrealized PnL: -856.46
Total PnL:      -1271.25

Final net Δ (options-only, sh) = +3287
Final net Δ (TOTAL sh incl. stock) = +1
Final per-expiry vega = { 2025-09-02: 5.4953, 2025-09-03: 0.9653 }

INVENTORY:
  Underlying   qty=-3286.0
Expiry       Strike Type   Qty      Δ/opt    Δ_total(sh)      V/opt    V_total
2025-09-02   630    C       +3    +0.9988           +300    +0.0218    +0.0654
2025-09-02   631    C       +3    +0.9954           +299    +0.1586    +0.4757
2025-09-02   632    C       +4    +0.9925           +397    +0.3171    +1.2685
2025-09-02   633    C       +3    +0.9883           +296    +0.5999    +1.7997
2025-09-02   634    C       +1    +0.9832            +98    +0.8094    +0.8094
2025-09-02   635    C       +1    +0.9768            +98    +1.0765    +1.0765
2025-09-03   601    C       +5    +0.9996           +500    +0.0625    +0.3124
2025-09-03   602    C       +3    +0.9996           +300    +0.0624    +0.1872
2025-09-03   604    C       +6    +0.9997           +600    +0.0414    +0.2486
2025-09-03   605    C       +3    +0.9998           +300    +0.0272    +0.0815
2025-09-03   606    C       +1    +0.9990           +100    +0.1356    +0.1356
--------------------------------------------------------------------------------------
Totals (options-only)                              +3287                   +6.4607
```

## CSV logs

In addition to printing activity to the terminal, the demo writes structured logs to the logs/ directory for offline analysis. Three separate CSV files are created per run, each timestamped with the session start time:

- quotes_*.csv

  Records every generated option quote.

  Columns: ts, expiry, strike, fv_adj, bid, ask, iv


- fills_*.csv

  Records each simulated trade execution (when a bid/ask is hit).

  Columns: ts, expiry, strike, side, qty, price, spot


- hedges_*.csv

  Records delta and vega hedge trades.

  Columns: ts, type, qty, price, spot
