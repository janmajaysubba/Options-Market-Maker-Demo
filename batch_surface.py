"""
Batch American implied volatilities across strikes and expiries
using pricer.py (binomial model) + iv_solver.py (bisection method).
"""

import datetime as dt
import numpy as np
import pandas as pd

from live_data import fetch_spot, fetch_chain, list_expiries, yearfrac
from iv_solver import implied_vol_american_bisect


def batch_iv_for_expiry(ticker, expiry, kind="calls",
                        r=0.04, q=0.0, N=400,
                        moneyness_min=0.7, moneyness_max=1.3):
    """
    Computes implied vols for all strikes of a single expiry (American options).

    Parameters:
        ticker (str): Ticker symbol (e.g., "AAPL").
        expiry (str): Expiration date string 'YYYY-MM-DD'.
        kind (str): "calls" or "puts".
        r (float): Risk-free rate (continuous compounding).
        q (float): Continuous dividend yield.
        N (int): Number of binomial steps (higher = more accurate).
        moneyness_min, moneyness_max (float): Strike/Spot bounds to filter strikes.
    
    Returns:
        DataFrame with columns ['expiry','strike','mid','iv'].
        Filters to strikes in the moneyness band and drops NaNs.
    """
    # Get the current spot price
    S = fetch_spot(ticker)

    # Fetch the option chain for this expiry & type
    chain = fetch_chain(ticker, expiry, kind)

    # Filter strikes to the moneyness range (e.g., 70%-130% of spot)
    mny = chain["strike"] / S
    chain = chain[(mny >= moneyness_min) & (mny <= moneyness_max)].copy()

    # Convert expiry date string to time-to-expiry in years
    T = yearfrac(dt.date.today(), expiry)

    ivs = []
    # Loop through each strike and compute IV via American bisection solver
    for _, row in chain.iterrows():
        K = float(row["strike"])
        mp = float(row["mid"])
        iv = implied_vol_american_bisect(
            mp, S, K, T, r, q=q, N=N,
            option=("call" if kind == "calls" else "put")
        )
        ivs.append(iv)

    # Build output DataFrame
    out = pd.DataFrame({
        "expiry": expiry,
        "strike": chain["strike"].values,
        "mid":    chain["mid"].values,
        "iv":     ivs
    })

    # Drop any rows with NaN IVs (failed solve or illiquid strikes)
    return out.dropna()


def build_surface(ticker, expiries, kind="calls", r=0.04, q=0.0, N=400):
    """
    Compute American IVs for multiple expiries and stack into one long DataFrame.

    Parameters:
        ticker (str): Ticker symbol.
        expiries (list[str]): List of expiry date strings.
        kind (str): "calls" or "puts".
        r, q, N: Same as in batch_iv_for_expiry.

    Returns:
        Long-format DataFrame ['expiry','strike','iv'].
    """
    frames = []
    for ex in expiries:
        df = batch_iv_for_expiry(ticker, ex, kind=kind, r=r, q=q, N=N)
        if len(df):
            # Keep only necessary columns for surface plotting
            frames.append(df[["expiry", "strike", "iv"]])

    if not frames:
        # No data found — return empty DataFrame
        return pd.DataFrame(columns=["expiry", "strike", "iv"])

    # Stack results from all expiries
    return pd.concat(frames, ignore_index=True)


def to_grid(df):
    """
    Converts long-format IV table into a 2D grid for surface plotting.

    Parameters:
        df (DataFrame): Must have 'expiry', 'strike', 'iv'.

    Returns:
        DataFrame where rows = expiries, columns = strikes, values = IVs.
        Missing values appear as NaN.
    """
    piv = df.pivot_table(index="expiry", columns="strike", values="iv")
    # Sort by expiry (rows) and strike (columns) for cleaner plots
    return piv.sort_index().sort_index(axis=1)
