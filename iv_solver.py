"""
American option implied volatility solver using the bisection method.

This uses the CRR binomial pricer from pricer.py to back out the volatility
that makes the model price match a given market price.
"""

from pricer import binomial_price
import numpy as np

def implied_vol_american_bisect(market_price, S, K, T, r,
                                q=0.0, N=400, option='call',
                                sigma_low=1e-4, sigma_high=5.0,
                                tol=1e-6, max_iter=100):
    """
    Solves for implied volatility (sigma) using bisection method.

    Arguments:
        market_price (float): Observed option price (mid, last, etc.).
        S (float): Spot price of the underlying.
        K (float): Strike price.
        T (float): Time to expiry in years (calendar days / 365).
        r (float): Risk-free rate (annualized, continuous compounding).
        q (float): Continuous dividend yield.
        N (int): Number of steps in the binomial tree.
        option (str): 'call' or 'put'.
        sigma_low, sigma_high (float): Initial bracket for volatility.
        tol (float): Convergence tolerance for price matching.
        max_iter (int): Max iterations before giving up.

    Returns Implied volatility, or np.nan if the market price is outside the possible model price range given the bracket.
    """

    # Price helper for a given volatility
    def price_at(sig):
        return binomial_price(S, K, T, r, sig, N, option, 'amer', q)

    # Prices at the initial volatility bracket edges
    p_low  = price_at(sigma_low)
    p_high = price_at(sigma_high)

    # If market price is outside model's possible range → no solution
    if market_price < p_low - 1e-12 or market_price > p_high + 1e-12:
        return np.nan

    # Bisection loop: shrink the volatility interval until convergence
    a, b = sigma_low, sigma_high
    for _ in range(max_iter):
        m   = 0.5 * (a + b)   # midpoint volatility
        pm  = price_at(m)     # model price at midpoint vol
        err = pm - market_price

        # If close enough in price or bracket is tiny, stop
        if abs(err) < tol or (b - a) < 1e-6:
            return m

        # Decide which half of the bracket contains the solution
        if (p_low - market_price) * err <= 0:
            b = m
        else:
            a = m
            p_low = pm

    # Return midpoint if max_iter hit without full convergence
    return 0.5 * (a + b)
