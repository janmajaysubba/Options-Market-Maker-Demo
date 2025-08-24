# pricer.py
import numpy as np

def binomial_price(S, K, T, r, sigma, N=400, option="call", style="amer", q=0.0):
    """
    CRR (Cox–Ross–Rubinstein) binomial option pricer.

    Parameters
    ----------
    S : float
        Spot price of the underlying.
    K : float
        Strike price.
    T : float
        Time to expiry in years (calendar/365).
    r : float
        Risk-free rate (continuous compounding, annualized).
    sigma : float
        Volatility (annualized).
    N : int, default 400
        Number of steps in the binomial tree.
    option : {"call","put"}, default "call"
        Option type.
    style : {"amer","euro"}, default "amer"
        Exercise style: American allows early exercise.
    q : float, default 0.0
        Continuous dividend yield.

    Returns
    -------
    float
        Model price of the option.

    Notes
    -----
    - Uses CRR parameters: u = exp(sigma*sqrt(dt)), d = 1/u.
    - Risk-neutral probability uses continuos dividend yield q.
    - Vectorized backward induction; early-exercise handled per layer for American style.
    - If T <= 0, returns intrinsic value.
    """
    # Instant expiry → intrinsic payoff
    if T <= 0:
        if option == "call":
            return float(max(S - K, 0.0))
        else:
            return float(max(K - S, 0.0))

    # One step size
    dt = T / N

    # CRR up/down multipliers
    u  = np.exp(sigma * np.sqrt(dt))
    d  = 1.0 / u

    # Risk-neutral probability with continuos dividend yield q
    p  = (np.exp((r - q) * dt) - d) / (u - d)

    # Numerical guard: keeps p strictly inside (0,1) to avoid edge blow-ups
    if p <= 0.0 or p >= 1.0:
        p = min(1.0 - 1e-12, max(1e-12, p))

    # One-step discount factor
    disc = np.exp(-r * dt)

    # Precompute powers u^j and d^(N-j) for all terminal nodes (vectorized)
    j = np.arange(N + 1)
    u_pows = np.power(u, j, dtype=float)
    d_pows = np.power(d, N - j, dtype=float)

    # Terminal stock prices: S * u^j * d^(N-j)
    ST = S * (u_pows * d_pows)

    # Terminal payoffs
    if option == "call":
        V = np.maximum(ST - K, 0.0)
    else:
        V = np.maximum(K - ST, 0.0)

    # Backward induction (overwrites V in place)
    for i in range(N - 1, -1, -1):
        # Continuation value at layer i from layer i+1
        V[:i+1] = disc * (p * V[1:i+2] + (1.0 - p) * V[:i+1])

        if style == "amer":
            # Early exercise check at layer i:
            # Stock at node (i,j) = S * u^j * d^(i-j)
            # We reuse precomputed u_pows[:i+1] and get d^(i-j) via:
            # d^(i-j) = d^(N-j) / d^(N-i)
            d_layer = np.power(d, N - i)          # scalar d^(N-i)
            S_nodes = S * (u_pows[:i+1] * (d_pows[:i+1] / d_layer))

            # Replace continuation value with intrinsic if exercising is better
            if option == "call":
                V[:i+1] = np.maximum(V[:i+1], S_nodes - K)
            else:
                V[:i+1] = np.maximum(V[:i+1], K - S_nodes)

    # Root node value = option price
    return float(V[0])
