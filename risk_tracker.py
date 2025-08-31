# risk_tracker.py
import json
from pricer import binomial_price

CONTRACT_MULT = 100  # US equity/ETF options -> 100 shares per contract

def _penny(x):
    # Round to 6 decimal places so saved numbers look clean and consistent.
    # Prevents tiny decimal errors like 0.30000000000000004.
    return float(round(float(x) + 1e-12, 6))

def delta(S, K, T, r, q, iv, N, option="call", bump_frac=0.01):
    """
    Returns option delta estimated by bumping the spot price up and down a little,
    then measuring how much the option price changes.
    (Numerical difference method)
    """
    h = max(1e-6, bump_frac * S)
    up = binomial_price(S+h, K, T, r, iv, N, option, "amer", q)
    dn = binomial_price(S-h, K, T, r, iv, N, option, "amer", q)
    return (up - dn) / (2*h)

def vega(S, K, T, r, q, iv, N, option="call", bump_vol=1e-4):
    """
    Returns option vega estimated by bumping the implied volatility up and down a little,
    then measuring how much the option price changes.
    (Numerical difference method)
    """

    up = binomial_price(S, K, T, r, iv+bump_vol, N, option, "amer", q)
    dn = binomial_price(S, K, T, r, iv-bump_vol, N, option, "amer", q)
    return (up - dn) / (2*bump_vol)

class RiskBook:
    """
    Tracks running exposures (delta, per-expiry vega), inventory, and PnL.
    Conventions:
      - option qty > 0  => you BOUGHT options (long)
      - option qty < 0  => you SOLD options (short)
      - Share hedges are handled separately via apply_share_hedge()
      - Prices are per option; CONTRACT_MULT converts to $ PnL.
    """
    def __init__(self):
        # Greeks (running exposures, per option units, aggregated across trades)
        self.net_delta = 0.0                    # scalar (across all expiries/strikes)
        self.net_vega  = {}                     # {expiry: vega exposure}

        # Positions
        # options keyed by (expiry, strike, option_type) -> {"qty": int, "avg": float}
        self.opt_pos = {}
        # underlying hedge position -> {"qty": float, "avg": float} (shares)
        self.under_pos = {"qty": 0.0, "avg": 0.0}

        # PnL (USD)
        self.realized_pnl = 0.0

    # ---- core risk updates (called on each option fill) ----
    def apply_fill(self, expiry, qty, S, K, T, r, q, iv, N, option="call"):
        """
        Record an option trade and update exposures + realized PnL (avg cost method).
          qty > 0 : buy (long more)
          qty < 0 : sell (short more)
        For this demo, trade_price is the model FV; replace with actual execution
        price when connected to a broker/exchange.
        Returns: (delta_per_option, vega_per_option) at the moment of the fill.
        """
        
        d = delta(S, K, T, r, q, iv, N, option)
        v = vega (S, K, T, r, q, iv, N, option)
        
        # Inventory accounting (average price carry)
        key = (expiry, float(K), option)
        pos = self.opt_pos.get(key, {"qty": 0, "avg": 0.0})

        # Demo-only: uses model FV as "trade" price.
        # In paper/live trading, pass the filled execution price instead.
        trade_price = binomial_price(S, K, T, r, iv, N, option, "amer", q)

        # Realized PnL for the closing portion; update average on the remainder
        new_qty = pos["qty"] + qty
        if pos["qty"] == 0 or (pos["qty"] > 0 and qty > 0) or (pos["qty"] < 0 and qty < 0):
            # Adding to existing side (or opening from flat): update average cost
            total_cost = pos["avg"] * pos["qty"] + trade_price * qty
            avg_new = total_cost / new_qty
            pos["qty"], pos["avg"] = new_qty, avg_new
        else:
            # Reducing/reversing: realize PnL on the amount that offsets
            close_qty = min(abs(qty), abs(pos["qty"])) * (1 if pos["qty"] > 0 else -1)
            # long position reduced by a sale => (sell - avg)
            # short position reduced by a buy  => (avg - buy)
            if pos["qty"] > 0:  # closing long with a sale
                self.realized_pnl += (trade_price - pos["avg"]) * (-close_qty) * CONTRACT_MULT
            else:               # closing short with a buy
                self.realized_pnl += (pos["avg"] - trade_price) * (close_qty) * CONTRACT_MULT

            remaining = pos["qty"] + qty
            if remaining == 0:
                pos["qty"], pos["avg"] = 0, 0.0
            else:
                # If flipping direction, the new side inherits current trade price as avg
                pos["qty"], pos["avg"] = remaining, trade_price

        self.opt_pos[key] = pos
        return d, v

    # ---- underlying hedge (shares) ----
    def apply_share_hedge(self, spot, qty_shares):
        """
        Records a hedge trade in the underlying and realize PnL on the portion that closes.
          qty_shares > 0 : buy shares
          qty_shares < 0 : sell shares
        """
        pos = self.under_pos
        if pos["qty"] == 0 or (pos["qty"] > 0 and qty_shares > 0) or (pos["qty"] < 0 and qty_shares < 0):
            # Adding to existing side (or opening): update average
            total_cost = pos["avg"] * pos["qty"] + spot * qty_shares
            pos["qty"] += qty_shares
            pos["avg"]  = total_cost / pos["qty"]
        else:
            # Reducing/closing: realize PnL on the closed portion
            close_qty = min(abs(qty_shares), abs(pos["qty"])) * (1 if pos["qty"] > 0 else -1)
            if pos["qty"] > 0:  # closing long shares by selling
                self.realized_pnl += (spot - pos["avg"]) * (-close_qty)
            else:               # closing short shares by buying
                self.realized_pnl += (pos["avg"] - spot) * (close_qty)
            remaining = pos["qty"] + qty_shares
            if remaining == 0:
                pos["qty"], pos["avg"] = 0.0, 0.0
            else:
                pos["qty"], pos["avg"] = remaining, spot

    # ---- mark to market (unrealized PnL) ----
    def mark_unrealized(self, spot, surface_piv, r, q, N):
        """
        Computes unrealized PnL using current spot and IVs from latest surface grid.
        - Options marked with binomial_price(spot, K, T, r, iv_from_surface, ...).
        - Underlying marked at 'spot'.
        Returns: float USD.
        """
        unreal = 0.0
        for (expiry, K, option), pos in self.opt_pos.items():
            if pos["qty"] == 0:
                continue
            # find IV for this (expiry, strike) on the surface; skip if missing
            try:
                iv = float(surface_piv.loc[expiry, float(K)])
            except Exception:
                continue
            T = _yearfrac(expiry)
            fv = binomial_price(spot, K, T, r, iv, N, option, "amer", q)
            unreal += (fv - pos["avg"]) * pos["qty"] * CONTRACT_MULT
        # underlying unrealized
        unreal += (spot - self.under_pos["avg"]) * self.under_pos["qty"]
        return unreal

    def revalue_exposures(self, spot, surface_piv, r, q, N):
        """
        Recomputes risk exposures (delta, vega) from current inventory using current market inputs.
    
        Why:
        - Incremental Greeks from trade time can drift as spot/IVs change.
        - This method ensures exposures reflect the latest spot and implied vol surface.
    
        Args:
            spot (float): Current underlying spot price
            surface_piv (pd.DataFrame): Pivoted implied vol surface [expiry x strike] -> IV
            r (float): Risk-free rate
            q (float): Dividend yield (continuous)
            N (int): Number of binomial steps for pricing/Greeks
    
        Notes:
            - Delta is tracked in *per-option units* here (not share equivalents).
            - Use self.net_delta * CONTRACT_MULT to convert options delta into shares.
            - Vega is stored per expiry (per-option per 1 vol point).
            - This does not touch realized PnL or positions; it only recalculates exposures.
        """
        net_delta_new = 0.0
        net_vega_new = {}

        # Loop through all open option positions
        for (expiry, K, option), pos in self.opt_pos.items():
            if pos["qty"] == 0:
                continue  # skip flat legs

            # Lookup IV from the surface for this expiry/strike
            try:
                iv = float(surface_piv.loc[expiry, float(K)])
            except Exception:
                #If IV missing for this node, skip (could fallback to cache later)
                continue

            # Time to expiry
            T = _yearfrac(expiry)

            # Per-option Greeks at current market
            d = delta(spot, K, T, r, q, iv, N, option)
            v = vega (spot, K, T, r, q, iv, N, option)

            # Aggregate across positions
            net_delta_new += pos["qty"] * d
            net_vega_new[expiry] = net_vega_new.get(expiry, 0.0) + pos["qty"] * v

        # Overwrite with revalued exposures
        self.net_delta = net_delta_new
        self.net_vega  = net_vega_new

    # ---- persistence (save/load risk state) ----
    def save(self, path="risk_state.json"):
        """Writes risk/positions/PnL to disk so the session can resume later."""
        data = {
            "net_delta": _penny(self.net_delta),
            "net_vega": {k: _penny(v) for k, v in self.net_vega.items()},
            "opt_pos": {f"{k[0]}|{k[1]}|{k[2]}": {"qty": pos["qty"], "avg": _penny(pos["avg"])}
                        for k, pos in self.opt_pos.items()},
            "under_pos": {"qty": _penny(self.under_pos["qty"]), "avg": _penny(self.under_pos["avg"])},
            "realized_pnl": _penny(self.realized_pnl),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path="risk_state.json"):
        """Loads a saved risk state if present; otherwise start fresh."""
        try:
            with open(path, "r") as f:
                d = json.load(f)
        except FileNotFoundError:
            return cls()
        rb = cls()
        rb.net_delta = float(d.get("net_delta", 0.0))
        rb.net_vega  = {k: float(v) for k, v in d.get("net_vega", {}).items()}
        for ks, pos in d.get("opt_pos", {}).items():
            ex, K, op = ks.split("|"); K = float(K)
            rb.opt_pos[(ex, K, op)] = {"qty": int(pos["qty"]), "avg": float(pos["avg"])}
        up = d.get("under_pos", {"qty": 0.0, "avg": 0.0})
        rb.under_pos = {"qty": float(up.get("qty", 0.0)), "avg": float(up.get("avg", 0.0))}
        rb.realized_pnl = float(d.get("realized_pnl", 0.0))
        return rb
    
    # ------ Strcuturing options and underlying positions to display inventory in the final summary ------
    
    def inventory_snapshot(
        self,
        include_greeks: bool = False,
        spot: float = None,
        surface_piv=None,
        r: float = None,
        q: float = None,
        N: int = None,
    ):
        """
        Returns inventory snapshot. Cheap by default (positions only).
        If include_greeks=True, also adds per-leg *current* Greeks using the provided market inputs.

        Returns dict with:
        - stock: {qty_shares, avg}
        - options: list of {expiry, strike, type, qty, avg}
        - per_expiry_vega: dict {expiry: vega_total}
        - net_delta_share_eq: options-only delta in share equivalents (Δ * 100 * contracts)
        - net_delta_units: options-only delta in per-option units
        - realized_pnl
        - (optional) options_with_greeks: list of { ... , delta_per_opt, delta_shares_total, vega_per_opt, vega_total }
        """
        # base snapshot (positions)
        opts = []
        for (expiry, K, option), pos in sorted(self.opt_pos.items(), key=lambda x: (x[0][0], x[0][1], x[0][2])):
            if pos["qty"] != 0:
                opts.append({
                    "expiry": expiry,
                    "strike": K,
                    "type": option,   # "call"/"put"
                    "qty": pos["qty"],
                    "avg": pos["avg"],
                })

        snap = {
            "stock": {"qty_shares": self.under_pos["qty"], "avg": self.under_pos["avg"]},
            "options": opts,
            "per_expiry_vega": {ex: v for ex, v in self.net_vega.items() if abs(v) > 1e-12},
            "net_delta_share_eq": self.net_delta * CONTRACT_MULT,
            "net_delta_units": self.net_delta,
            "realized_pnl": self.realized_pnl,
        }

        if not include_greeks:
            return snap

        # guard
        if any(v is None for v in (spot, surface_piv, r, q, N)):
            raise ValueError("include_greeks=True requires spot, surface_piv, r, q, N")

        legs = []
        for row in snap["options"]:
            ex, K, opt, qty = row["expiry"], float(row["strike"]), row["type"], row["qty"]
            # need IV from surface for this node; skip if missing
            try:
                iv = float(surface_piv.loc[ex, K])
            except Exception:
                continue
            T = _yearfrac(ex)
            d = delta(spot, K, T, r, q, iv, N, opt)
            v = vega (spot, K, T, r, q, iv, N, opt)
            legs.append({
                **row,
                "delta_per_opt": d,
                "delta_shares_total": d * qty * CONTRACT_MULT,
                "vega_per_opt": v,
                "vega_total": v * qty,
            })

        snap["options_with_greeks"] = legs
        return snap



    def format_inventory(self) -> str:
        """
        For console summaries.
        """
        s = []
        s.append("Inventory:")
        # Stock
        sh = self.under_pos["qty"]
        s.append(f"- Stock: {sh:+.0f} sh @ avg {self.under_pos['avg']:.2f}" if sh else "- Stock: 0 sh")

        # Options (group by expiry for readability)
        if any(pos["qty"] != 0 for pos in self.opt_pos.values()):
            # Build grouped lines
            by_exp = {}
            for (expiry, K, option), pos in self.opt_pos.items():
                if pos["qty"] == 0:
                    continue
                by_exp.setdefault(expiry, []).append((K, option, pos["qty"], pos["avg"]))
            for expiry in sorted(by_exp.keys()):
                s.append(f"- Options {expiry}:")
                for K, option, qty, avg in sorted(by_exp[expiry], key=lambda x: (x[0], x[1])):
                    opt_code = ("C" if option.lower().startswith("c") else "P")
                    s.append(f"    {int(K) if K.is_integer() else K}{opt_code:>2}  {qty:+d} @ {avg:.2f}")
        else:
            s.append("- Options: (none)")
    
    



# _yearfrac :
# Turns expiry dates 'YYYY-MM-DD' into model-ready year fractions (days/365).
# Ensures a tiny minimum (1e-6) so T never becomes 0, avoiding pricer errors.
import datetime as _dt
def _yearfrac(expiry_str: str) -> float:
    """Calendar year fraction from today to expiry (days/365)."""
    today = _dt.date.today()
    e = _dt.datetime.strptime(expiry_str, "%Y-%m-%d").date()
    return max((e - today).days / 365.0, 1e-6)
