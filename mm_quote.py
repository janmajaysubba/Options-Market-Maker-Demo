# mm_quote.py
from pricer import binomial_price

CONTRACT_MULT = 100  # US equity/ETF options

def fair_value(S, K, T, r, q, iv, N=300, option="call"):
    """
    Compute the theoretical (fair) option value using your binomial pricer.
    This is the *unbiased* model mid you will shift based on inventory.
    """
    return binomial_price(S, K, T, r, iv, N, option, "amer", q)


def make_quotes(fv, edge_abs=0.02, edge_bps=50):
    """
    Turn a fair value into two-sided quotes with a symmetric edge.
    edge = max(edge_abs, edge_bps * fv).
    Returns (bid, ask).
    """
    edge = max(edge_abs, (edge_bps / 10000.0) * fv)
    bid = max(0.01, fv - edge)  # floor at a cent so we never quote negative
    ask = max(bid + 0.01, fv + edge)  # keep ask > bid by at least a cent
    return bid, ask


# ---------------- inventory-aware quoting ----------------

def inventory_bias(book, expiry, k_delta=1e-4, k_vega=1e-2):
    """
    Compute a price *shift* ($) to apply to the model fair value
    based on current inventory exposures.

    Positive exposure -> positive bias -> LOWER your quoted mid (encourages selling).
    (We subtract this bias from FV before quoting.)

    Args:
      book: your RiskBook instance
      expiry: expiry string for per-expiry vega
      k_delta: dollar shift per 1 share of net delta exposure
      k_vega : dollar shift per 1.00 vega unit (per 1.00 vol) in this expiry

    Returns:
      bias (float, $). You’ll subtract this from FV.
    """
    net_delta_sh = book.net_delta * CONTRACT_MULT           # convert Δ (per option) to shares notionally
    net_vega_exp = book.net_vega.get(expiry, 0.0)           # per-expiry vega exposure

    # linear penalty (simple, stable). tweak k_* to taste.
    return k_delta * net_delta_sh + k_vega * net_vega_exp


def make_inventory_aware_quotes(
    book, expiry, *,
    S, K, T, r, q, iv, N=300, option="call",
    edge_abs=0.02, edge_bps=50,
    k_delta=1e-4, k_vega=1e-2,
    bias_cap=1.00
):
    """
    Convenience: price -> apply inventory bias -> produce two-sided quotes.

    Steps:
      1) fair_value = binomial_price(...)
      2) bias = inventory_bias(book, expiry, k_delta, k_vega)
      3) fv_biased = max(0.01, fair_value - clamp(bias))
      4) (bid, ask) = make_quotes(fv_biased, ...)

    Args:
      book, expiry: RiskBook + which expiry’s vega to look at
      S, K, T, r, q, iv, N, option: pricing inputs
      edge_abs, edge_bps: quoting edge parameters
      k_delta, k_vega: sensitivity of your mid to inventory
      bias_cap: absolute cap on $ shift from inventory

    Returns:
      fv_raw, fv_biased, (bid, ask)
    """
    # 1) model fair value (unbiased)
    fv_raw = fair_value(S, K, T, r, q, iv, N=N, option=option)

    # 2) compute inventory-driven bias (cap for safety)
    b = inventory_bias(book, expiry, k_delta=k_delta, k_vega=k_vega)
    if bias_cap is not None:
        b = max(-bias_cap, min(bias_cap, b))  # clamp to ±bias_cap

    # 3) apply bias: subtract to push mid in the direction that encourages unloading risk
    fv_biased = max(0.01, fv_raw - b)

    # 4) turn biased mid into quotes
    bid, ask = make_quotes(fv_biased, edge_abs=edge_abs, edge_bps=edge_bps)
    return fv_raw, fv_biased, (bid, ask)
