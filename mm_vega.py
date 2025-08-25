# mm_vega.py
"""
Same-expiry vega hedging helpers.

Goal:
- Pick an ATM-ish instrument in a given expiry from the IV surface.
- Trade just enough of that option to gently pull the per-expiry vega back
  toward a tolerance band (soft hedge, not a hard zero).

Notes on units:
- risk_tracker.vega(...) returns vega *per option* (price change for +1.00
  absolute vol). US equity options clear in contracts of 100 options, so we
  multiply by CONTRACT_MULT to get *per contract* vega.
"""

import numpy as np
import math
from risk_tracker import vega  # uses the binomial pricer under the hood

CONTRACT_MULT = 100  # 1 contract = 100 options (US equity/ETF standard)


def pick_atm_strike_iv(piv, expiry, spot):
    """
    Finds the ATM strike closest to the spot for a given expiry from the IV surface grid.

    Parameters
    ----------
    piv : pandas.DataFrame
        IV grid with rows = expiry strings ('YYYY-MM-DD'), columns = strikes,
        and cells = implied vol (float). Produced by batch_surface.to_grid().
    expiry : str
        Expiry key ('YYYY-MM-DD') that must exist in `piv.index`.
    spot : float
        Current underlying price. We pick the strike closest to this.

    Returns
    -------
    (K, iv) : tuple[float, float]
        K is the chosen strike (closest to `spot` among columns with finite IV),
        iv is the implied vol at (expiry, K).
        Returns (None, None) if expiry is missing or no finite IVs exist.

    Rationale
    ---------
    We hedge vega with an ATM option in the *same expiry* because ATM options
    typically have the largest vega and minimize cross-maturity basis risk.
    """
    if expiry not in piv.index:
        return None, None

    # Keep only strikes with a real (finite) IV value in this expiry.
    cols = [k for k in piv.columns if np.isfinite(piv.loc[expiry, k])]
    if not cols:
        return None, None

    # Choose the strike whose distance to spot is minimal → “ATM-ish”.
    K = min(cols, key=lambda k: abs(k - spot))
    return float(K), float(piv.loc[expiry, K])


def vega_hedge(
    book, expiry, spot, T, r, q, piv, N=300, *,
    option="call",
    vega_band=5.0,        # keep |vega_exp| within this band (per +1.00 vol unit)
    hedge_fraction=0.5,   # hedge only a fraction (e.g., 50%) of the excess vega
    max_contracts=10      # never trade more than this many contracts in one action
):
    """
    Softly reduces per-expiry vega toward a tolerance band using an ATM option
    in the SAME expiry.

    Parameters
    ----------
    book : RiskBook
        The risk book instance with net_vega per expiry and apply_fill(...).
    expiry : str
        'YYYY-MM-DD' expiry to hedge.
    spot, T, r, q : float
        Underlier price, time-to-expiry (years), risk-free rate, dividend yield.
    piv : pandas.DataFrame
        IV surface grid (from batch_surface.to_grid()) used to pick ATM vol.
    N : int
        Binomial steps (passed through to the pricer via risk_tracker.vega()).
    option : {"call","put"}
        Which option type to use for the hedge.
    vega_band : float
        Acceptable absolute vega range; e.g., ±5 means we aim to keep
        |vega| ≤ 5 (per +1.00 vol, per book).
    hedge_fraction : float
        Only neutralize this fraction of the excess (prevents oscillation).
    max_contracts : int
        Safety cap on contracts traded in one hedging action.

    Returns
    -------
    (qty_executed, hedge_vega_per_contract) : tuple[int, float]
        qty_executed > 0 means BUY contracts, < 0 means SELL contracts.
        hedge_vega_per_contract is the vega per 1.00 vol for one contract.
        Returns (0, 0.0) if no action was needed or possible.

    How it works
    ------------
    1) Reads current per-expiry vega exposure from the book.
    2) If |vega| ≤ band → does nothing.
    3) Else, picks an ATM strike & IV in this expiry from the surface.
    4) Compute vega per contract (per 1.00 vol) for that ATM instrument.
    5) Compute a target change = -sign(vega) * fraction * (|vega|-band).
       (If we're long vega, we SELL some; if short vega, we BUY some.)
    6) Converts target change into number of contracts.
    7) Then applys the fill to update the book.
    """
    # 1) current vega exposure in this expiry (per +1.00 vol, for the whole book)
    vega_exp = book.net_vega.get(expiry, 0.0)
    excess = abs(vega_exp) - vega_band
    if excess <= 0:
        return 0, 0.0  # already inside the band

    # 2) choose an ATM strike & IV to hedge with (same expiry)
    K, iv = pick_atm_strike_iv(piv, expiry, spot)
    if K is None or iv is None:
        print(f"  SKIP: No ATM IV found for vega hedge in {expiry}")
        return 0, 0.0

    # 3) compute vega per CONTRACT (risk_tracker.vega returns per option → ×100)
    v_per_opt = vega(spot, K, T, r, q, iv, N, option=option)  # per +1.00 vol, per option
    v_per_contract = v_per_opt * CONTRACT_MULT                 # per +1.00 vol, per contract

    # Guard against numerically tiny vegas (ill-posed hedge size).
    if abs(v_per_contract) < 1e-6:
        return 0, 0.0

    # 4) target change in book vega (per +1.00 vol):
    #    If vega_exp > 0 (long vega), target_change < 0 → SELL to reduce vega.
    #    If vega_exp < 0 (short vega), target_change > 0 → BUY  to add vega.
    target_change = -np.sign(vega_exp) * hedge_fraction * excess

    # 5) contracts needed ≈ (target_change / vega_per_contract)
    qty_float = target_change / v_per_contract

    # Round to nearest int and apply safety cap.
    # Keeps direction via np.sign and avoids trading more than max_contracts.
    qty = int(np.sign(qty_float) * min(max_contracts, math.floor(abs(qty_float) + 0.5)))
    if qty == 0:
        return 0, v_per_contract

    # 6) Apply the hedge as a "fill" to update running risk.
    # Convention: qty>0 means BUY contracts, qty<0 means SELL contracts.
    book.apply_fill(expiry, qty, spot, K, T, r, q, iv, N, option=option)

    return qty, v_per_contract
#mm_vega.py
import numpy as np
import math
from risk_tracker import vega   # uses binomial pricer (pricer.py) under the hood

CONTRACT_MULT = 100  # US equity option

def pick_atm_strike_iv(piv, expiry, spot):
    """
    Chooses the strike in this expiry whose IV is finite and closest to spot.
    `piv` is your surface grid (rows=expiry strings, cols=strikes).
    Returns (K, iv) or (None, None) if not found.
    """
    if expiry not in piv.index:
        return None, None
    # keep finite IVs only
    cols = [k for k in piv.columns if np.isfinite(piv.loc[expiry, k])]
    if not cols:
        return None, None
    # pick strike closest to spot
    K = min(cols, key=lambda k: abs(k - spot))
    return float(K), float(piv.loc[expiry, K])

def vega_hedge(book, expiry, spot, T, r, q, piv, N=300,
                    option="call",
                    vega_band=5.0,        # keep |vega_exp| within this band (per 1.00 vol unit)
                    hedge_fraction=0.5,   # only hedge part of the excess
                    max_contracts=10):    # cap per hedge action
    """
    Softly reducs per-expiry vega toward a band using an ATM option in the SAME expiry.
    - vega_band: tolerance (e.g., ±5 'vega' units per 1.00 vol)
    - hedge_fraction: hedge only a fraction of the excess (e.g., 50%)
    - max_contracts: safety cap
    Returns (qty_executed, hedge_vega_per_contract) or (0, 0.0) if no action.
    """
    # current vega exposure in this expiry
    vega_exp = book.net_vega.get(expiry, 0.0)
    excess = abs(vega_exp) - vega_band
    if excess <= 0:
        return 0, 0.0  # already inside the band

    # choose an ATM strike & IV to hedge with
    K, iv = pick_atm_strike_iv(piv, expiry, spot)
    if K is None or iv is None:
        print(f"  SKIP: No ATM IV found for vega hedge in {expiry}")
        return 0, 0.0

    # compute vega per CONTRACT 
    v_per_opt = vega(spot, K, T, r, q, iv, N, option=option)      # per 1.00 vol
    v_per_contract = v_per_opt * CONTRACT_MULT

    if abs(v_per_contract) < 1e-6:
        return 0, 0.0  # avoid dividing by tiny numbers

    # target change: reduce a fraction of the excess, with correct sign
    target_change = -np.sign(vega_exp) * hedge_fraction * excess  # desired vega change (per 1.00 vol)
    # convert to contracts
    qty_float = target_change / v_per_contract
    # round to an integer number of contracts and cap
    qty = int(np.sign(qty_float) * min(max_contracts, math.floor(abs(qty_float) + 0.5)))
    if qty == 0:
        return 0, v_per_contract

    # Convention: qty>0 means BUY 1 contract, qty<0 means SELL 1 (matches your fixed loop)
    # Apply the fill to update book risk
    book.apply_fill(expiry, qty, spot, K, T, r, q, iv, N, option=option)
    return qty, v_per_contract
