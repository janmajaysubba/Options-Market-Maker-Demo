# batch_surface.py
import datetime as dt
import numpy as np
import pandas as pd
from multiprocessing import Pool, cpu_count

from live_data import fetch_spot, fetch_chain, list_expiries, yearfrac
from iv_solver import implied_vol_american_bisect

# --- internal worker for multiprocessing ---
def _solve_one(args):
    """
    Worker-friendly wrapper (must be top-level for pickling).
    Unpacks args and calls the robust IV solver.
    """
    S, K, mp, T, r, q, N, option, expiry = args
    return implied_vol_american_bisect(
        mp, S, K, T, r, q=q, N=N, option=option, expiry=expiry
    )

def batch_iv_for_expiry(ticker, expiry, kind="calls",
                        r=0.04, q=0.0, N=400,
                        moneyness_min=0.85, moneyness_max=1.15,
                        max_workers=None):
    """
    Compute implied volatilities for a single expiry in parallel.

    Steps
    -----
    1) Pull and clean the option chain (bid/ask > 0, compute mid).
    2) Filter out wide-spread quotes (spread <= 20% of mid).
    3) Keep a moneyness band (strike/spot in [moneyness_min, moneyness_max]).
    4) Solve American IV for each remaining strike using bisection (parallelized).

    Parameters
    ----------
    ticker : str
        Underlying symbol, e.g. "SPY".
    expiry : str
        Expiry date "YYYY-MM-DD".
    kind : {"calls","puts"}, default "calls"
        Which side of the chain to process.
    r : float, default 0.04
        Risk-free rate (cont. comp.).
    q : float, default 0.0
        Dividend yield (cont. comp.).
    N : int, default 400
        Binomial steps for pricing.
    moneyness_min, moneyness_max : float
        Keep strikes with strike/spot in this closed interval.
    max_workers : int or None
        Process count for Pool(). If None, auto-choose 2..8.

    Returns
    -------
    DataFrame
        Columns: ["expiry","strike","mid","iv"] after filtering and cleaning.
        Rows with failed IV solves (NaN) are dropped; IVs are sanity-banded.
    """
    # Spot for moneyness and intrinsic caps
    S = fetch_spot(ticker)

    # Cleaned chain with mid price (fetch_chain handles bid/ask>0 etc.)
    chain = fetch_chain(ticker, expiry, kind)

    # --- spread/liquidity guard (skip noisy/wide quotes) ---
    chain["spread"] = (chain["ask"] - chain["bid"]) / chain["mid"]
    chain = chain[(chain["spread"] <= 0.20)].copy()  # ≤ 20% of mid

    # --- moneyness filter (keep strikes near spot for stable solves) ---
    mny = chain["strike"] / S
    chain = chain[(mny >= moneyness_min) & (mny <= moneyness_max)].copy()
    if len(chain) == 0:
        return pd.DataFrame(columns=["expiry","strike","mid","iv"])

    # Time to expiry (years) and option type string for the solver
    T = yearfrac(expiry)
    option = "call" if kind == "calls" else "put"

    # Prepare argument tuples for workers
    args = [(S, float(K), float(mp), T, r, q, N, option, expiry)
            for K, mp in zip(chain["strike"].values, chain["mid"].values)]

    # --- parallel map over strikes ---
    if max_workers is None:
        # be conservative; CPU-bound but pricing is fairly light now
        max_workers = max(2, min(8, cpu_count()))
    with Pool(processes=max_workers) as pool:
        ivs = pool.map(_solve_one, args)

    # Assemble result frame
    out = pd.DataFrame({
        "expiry": expiry,
        "strike": chain["strike"].values,
        "mid":    chain["mid"].values,
        "iv":     ivs
    })

    # Basic clean: drop failed solves and keep a sane IV band
    out = out.dropna()
    out = out[(out["iv"] >= 0.01) & (out["iv"] <= 3.0)]
    return out

def build_surface(ticker, expiries, kind="calls", r=0.04, q=0.0, N=400, **kwargs):
    """
    Loop over a list of expiries and stack all per-expiry IV tables.

    Returns a long-format DataFrame with columns ["expiry","strike","iv"].
    Extra kwargs are forwarded to batch_iv_for_expiry (e.g., moneyness filters).
    """
    frames = []
    for ex in expiries:
        df = batch_iv_for_expiry(ticker, ex, kind=kind, r=r, q=q, N=N, **kwargs)
        if len(df):
            frames.append(df[["expiry","strike","iv"]])
    if not frames:
        return pd.DataFrame(columns=["expiry","strike","iv"])
    return pd.concat(frames, ignore_index=True)

def to_grid(df):
    """
    Pivot long-format IV table to a surface grid:
    rows = expiries, columns = strikes, values = IV.

    Sorted both by row index (expiry) and columns (strike) for tidy plotting.
    """
    piv = df.pivot_table(index="expiry", columns="strike", values="iv")
    return piv.sort_index().sort_index(axis=1)
