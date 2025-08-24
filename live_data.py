"""
live_data.py 
------------
Functions for fetching and caching live market data for stocks and options
using Yahoo Finance (via yfinance library).

This script provides:
- Spot price retrieval
- Expiry date listing
- Time-to-expiry calculation
- Options chain retrieval (calls or puts)
- Local CSV caching for offline use
"""

import os, time
import numpy as np
import pandas as pd
import datetime as dt
import yfinance as yf


def fetch_spot(ticker: str) -> float:
    tk = yf.Ticker(ticker)
    # returns last close price; for intraday price you can use tk.fast_info.last_price if you want
    hist = tk.history(period="1d")
    if len(hist) == 0:
        raise RuntimeError("No price history returned.")
    return float(hist["Close"].iloc[-1])


def list_expiries(ticker: str):
    return yf.Ticker(ticker).options  # returns a list of available option expiry dates for the ticker in 'YYYY-MM-DD' format


def yearfrac(expiry_str: str) -> float:
    today = dt.date.today()
    e = dt.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    return max((e - today).days / 365.0, 1e-6)  # returns time to expiry in fraction of a year (calendar days/365)



def fetch_chain(
    ticker: str,
    expiry: str,
    kind: str = "calls",
    n: int | None = None,     # <- NEW: symmetric window around ATM
    spot: float | None = None # <- NEW: optional spot override
) -> pd.DataFrame:
    """
    Fetches and cleans the option chain for a specific expiry.

    Returns columns: ['strike','mid','bid','ask','volume','open_interest'].

    - Drops rows with non-positive bid/ask.
    - mid = (bid + ask) / 2
    - If n is None -> returns full cleaned chain (sorted by strike).
    - If n is given -> returns n strikes below ATM, ATM, n above (≈ 2n+1 rows, clipped at edges).
    """
    tk = yf.Ticker(ticker)
    ch = tk.option_chain(expiry)
    tbl = ch.calls if kind == "calls" else ch.puts

    # Clean table + mid
    tbl = tbl[(tbl["bid"] > 0) & (tbl["ask"] > 0)].copy()
    tbl["mid"] = 0.5 * (tbl["bid"] + tbl["ask"])
    tbl = tbl[["strike", "mid", "bid", "ask", "volume", "openInterest"]].rename(
        columns={"openInterest": "open_interest"}
    ).sort_values("strike").reset_index(drop=True)

    if n is None:
        return tbl  # returns the full clean options table
    
    # Finding the spot price to determine the ATM strike
    if spot is None:
        hist = tk.history(period="1d")
        if len(hist):
            spot = float(hist["Close"].iloc[-1])
        else:
            # fallback: uses median strike as rough ATM if spot lookup fails
            spot = float(tbl["strike"].median())

    # Finds the ATM row and slices symmetrically
    atm_idx = (tbl["strike"] - spot).abs().idxmin()
    lo = max(atm_idx - n, 0)
    hi = min(atm_idx + n + 1, len(tbl))  # +1 to include upper bound

    return tbl.iloc[lo:hi].reset_index(drop=True)


def cache_chain(df: pd.DataFrame, ticker: str, expiry: str, kind: str):   
    """
    Saves an options chain DataFrame to a local CSV file for later use.
    
    Then, returns the File path of the saved CSV file.
    """
    os.makedirs("data/cache", exist_ok=True)
    path = f"data/cache/{ticker}_{expiry}_{kind}.csv"
    df.to_csv(path, index=False)
    return path
