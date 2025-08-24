# iv_solver.py
from pricer import binomial_price
import numpy as np
import time

# Cache for warm-starting implied vol solves
# Format: {(expiry,strike,option): {"iv": float, "ts": float, "mid": float}}
_iv_cache = {}

def implied_vol_american_bisect(
    market_price, S, K, T, r, *,
    q=0.0, N=400, option='call',
    sigma_low=0.01, sigma_high=3.0,
    tol=1e-6, max_iter=100,
    expiry=None, cache_ttl=3.0
):
    """
    Robust implied volatility solver for American options using bisection.

    Arguments:
        market_price : float   observed option price (e.g. bid/ask mid)
        S            : float   spot price
        K            : float   strike price
        T            : float   time to expiry in years
        r            : float   risk-free rate
        q            : float   dividend yield
        N            : int     number of binomial steps
        option       : str     'call' or 'put'
        sigma_low/high : float initial search bracket for vol
        tol          : float   target precision in price
        max_iter     : int     max number of bisection steps
        expiry       : str     expiry (optional, used for caching)
        cache_ttl    : float   how many seconds to reuse cached IVs

    Returns:
        float IV in [0.0, ∞) if solved, or np.nan if no valid solution exists.
    """

    # --- 1) Basic price sanity check (intrinsic ≤ price ≤ cap) ---
    # For calls: intrinsic = max(S-K,0), cap = S (option ≤ spot).
    # For puts:  intrinsic = max(K-S,0), cap = K (option ≤ strike).
    intrinsic = max(S - K, 0.0) if option == 'call' else max(K - S, 0.0)
    cap       = S if option == 'call' else K
    if not (intrinsic - 1e-12 <= market_price <= cap + 1e-12):
        # If market price is nonsensical, stop early
        return np.nan

    # Build a cache key if expiry is given
    key = (expiry, float(K), option) if expiry is not None else None
    now = time.time()

    # --- 2) Warm-start from cache (recent IV solve) ---
    if key in _iv_cache and now - _iv_cache[key]["ts"] <= cache_ttl:
        iv_prev = _iv_cache[key]["iv"]
        # Tighten the bracket around the previous IV (faster convergence).
        # These widened bounds allow for small moves in IV without a full reset.
        sigma_low  = max(0.005, iv_prev * 0.5)
        sigma_high = min(5.0,  iv_prev * 1.5)

    # Helper: safe call to binomial pricer
    def price_at(sig):
        try:
            return binomial_price(S, K, T, r, sig, N, option, 'amer', q)
        except Exception:
            return np.nan

    # --- 3) Initial bracket test ---
    p_low  = price_at(sigma_low)
    p_high = price_at(sigma_high)
    good1 = (np.isfinite(p_low) and np.isfinite(p_high) and
             p_low <= market_price <= p_high)

    # --- 3b) Auto-widen if first bracket fails ---
    if not good1:
        sigma_low2, sigma_high2 = 0.02, 5.0
        p_low  = price_at(sigma_low2)
        p_high = price_at(sigma_high2)
        if not (np.isfinite(p_low) and np.isfinite(p_high) and
                p_low <= market_price <= p_high):
            # Still no valid bracket -> no solution
            return np.nan
        a, b = sigma_low2, sigma_high2
    else:
        a, b = sigma_low, sigma_high

    # --- 4) Bisection search loop ---
    for _ in range(max_iter):
        m  = 0.5 * (a + b)      # midpoint vol
        pm = price_at(m)        # model price at midpoint

        if not np.isfinite(pm):
            # If pricer fails mid-interval, shrink interval a bit and retry
            a = max(a, m * 0.9); b = min(b, m * 1.1)
            continue

        err = pm - market_price
        if abs(err) < tol or (b - a) < 1e-6:
            # Converged -> save to cache and return
            iv = m
            if key:
                _iv_cache[key] = {"iv": iv, "ts": now, "mid": market_price}
            return iv

        # Root location test: keep half interval containing the solution
        p_a = price_at(a)
        if not np.isfinite(p_a): 
            p_a = pm  # fallback if low-side price fails
        if (p_a - market_price) * err <= 0:
            b = m
        else:
            a = m

    # --- 5) Fallback (max_iter reached) ---
    iv = 0.5 * (a + b)
    if key:
        _iv_cache[key] = {"iv": iv, "ts": now, "mid": market_price}
    return iv
