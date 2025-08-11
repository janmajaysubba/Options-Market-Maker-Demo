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


def yearfrac(today: dt.date, expiry_str: str) -> float:
    e = dt.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    return max((e - today).days / 365.0, 1e-6)  # returns time to expiry in fraction of a year (calendar days/365)


def fetch_chain(ticker: str, expiry: str, kind: str = "calls") -> pd.DataFrame:  
    """
    Fetches and cleans the options chain for a specific expiry.
    
    Then, returns a DataFrame with columns: strike, mid, bid, ask, volume, open_interest.

    Notes:
    - Removes contracts with non-positive bid/ask prices.
    - Mid price is calculated as (bid + ask) / 2.
    """   
    tk = yf.Ticker(ticker)
    ch = tk.option_chain(expiry)
    tbl = ch.calls if kind == "calls" else ch.puts
    tbl = tbl[(tbl["bid"] > 0) & (tbl["ask"] > 0)].copy()
    tbl["mid"] = 0.5 * (tbl["bid"] + tbl["ask"])
    return tbl[["strike", "mid", "bid", "ask", "volume", "openInterest"]].rename(
        columns={"openInterest": "open_interest"}
    )

def cache_chain(df: pd.DataFrame, ticker: str, expiry: str, kind: str):   
    """
    Saves an options chain DataFrame to a local CSV file for later use.
    
    Then, returns the File path of the saved CSV file.
    """
    os.makedirs("data/cache", exist_ok=True)
    path = f"data/cache/{ticker}_{expiry}_{kind}.csv"
    df.to_csv(path, index=False)
    return path
