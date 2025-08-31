# mm_loop_realtime.py
"""
A 60-second market-making loop with:
- IV mini-surface build (and periodic refresh)
- Per-interval (gated) quoting & toy fills
- RiskBook updates (delta, per-expiry vega)
- Delta share hedges + soft same-expiry vega hedges
- CSV logs for quotes/fills/hedges
- End-of-run PnL snapshot + RiskBook persistence

Uses inventory-aware quoting from mm_quote.make_inventory_aware_quotes()
so quotes automatically bias based on the current inventory risk.
"""

import csv, os, time, math
import numpy as np

import live_data, batch_surface
from mm_quote import make_inventory_aware_quotes   # import quoting logic (fair value + inventory adjustment + bid/ask)
from risk_tracker import RiskBook                  # class with PnL + persistence
from mm_vega import vega_hedge                     # same-expiry “soft” vega hedger

# -------- Cadence / logging --------
SURF_REFRESH_SEC   = 15.0     # rebuild IV surface every 15s
FILL_INTERVAL_SEC  = 3.0      # run a "tick" (fills/quotes/spot move) every 3s

# -------- Config --------
TICKER   = "SPY"
KIND     = "calls"            # or "puts"
OPTION   = "call" if KIND == "calls" else "put"
R, Q     = 0.04, 0.00

EDGE_ABS = 0.02               # $0.02 min edge per side
EDGE_BPS = 50                 # 50 bps of FV per side

CONTRACT_MULT = 100
DELTA_HEDGE_THRESHOLD_SHARES = 50    # hedge when |Δ| > 50 shares

RUN_SECONDS = 60

# Toy fill probabilities
PROB_LIFT_ASK = 0.10          # someone lifts your ask -> you SELL (qty=-1)
PROB_HIT_BID  = 0.20          # someone hits your bid  -> you BUY  (qty=+1)

# Soft vega hedge params
VEGA_BAND       = 5.0         # keep per-expiry vega within ±band (per 1.00 vol)
VEGA_HEDGE_FRAC = 0.5         # only hedge a fraction of the excess
VEGA_MAX_CNTR   = 5           # cap contracts per hedge action

# Binomial steps
N_BASE     = 300
N_EXPIRIES = 2                # first 2 expiries

# Spot random walk params (toy)
SPOT_ANNUAL_VOL = 0.15        # 15% annualized


# ---------- small helpers ----------

def adaptive_steps(T):
    """Scale binomial steps with maturity to keep runtime reasonable."""
    return min(500, max(150, int(400 * T)))

def simulate_spot_rw(spot, dt_years, vol_annual):
    """Simulate a small random move (1 minute price step) in the spot price.
   Uses a simplified Geometric Brownian Motion step (no drift),
   so the spot just jitters up and down realistically without trending."""

    z = np.random.randn()
    step = math.exp(vol_annual * math.sqrt(dt_years) * z)
    return spot * step

def open_logs():
    """Create CSV writers for quotes/fills/hedges (simple audit trail)."""
    os.makedirs("logs", exist_ok=True)
    ts = int(time.time())
    qf = open(f"logs/quotes_{ts}.csv", "a", newline="")
    ff = open(f"logs/fills_{ts}.csv",  "a", newline=""
    )
    hf = open(f"logs/hedges_{ts}.csv", "a", newline="")
    qwriter = csv.writer(qf); qwriter.writerow(["ts","expiry","strike","fv_adj","bid","ask","iv"])
    fwriter = csv.writer(ff); fwriter.writerow(["ts","expiry","strike","side","qty","price","spot"])
    hwriter = csv.writer(hf); hwriter.writerow(["ts","type","qty","price","spot"])
    return qf, ff, hf, qwriter, fwriter, hwriter


# ---------- main loop ----------

def main():
    qf = ff = hf = None
    try:
        # ---------- Initial context ----------
        spot0    = live_data.fetch_spot(TICKER)
        expiries = list(live_data.list_expiries(TICKER))[:N_EXPIRIES]

        print("Building IV surface...")
        t0 = time.time()
        surf_df  = batch_surface.build_surface(TICKER, expiries, kind=KIND, r=R, q=Q, N=N_BASE)
        t1 = time.time()
        print(f"IV surface built in {t1 - t0:.3f} seconds")

        piv = batch_surface.to_grid(surf_df)
        t2 = time.time()
        print(f"Batched IV surface to grid in {t2 - t1:.3f} seconds")

        if piv.empty or np.isnan(piv.values).all():
            print("No IVs solved — widen filters or check data.")
            return

        print(f"Init spot={spot0:.4f} | expiries={tuple(piv.index)} | strikes={len(piv.columns)}")

        # RiskBook (load previous state if present) + logs
        book = RiskBook.load("risk_state.json")
        qf, ff, hf, qwriter, fwriter, hwriter = open_logs()

        # Counters
        fills_count   = 0
        vega_hedges   = 0
        delta_hedges  = 0

        # For demo readability: only quote the first 6 strikes per expiry (finite IVs).
        # The surface still contains all strikes in the moneyness band.
        usable_by_expiry = {}
        for ex in piv.index:
            usable = [(k, piv.loc[ex, k]) for k in piv.columns if np.isfinite(piv.loc[ex, k])]
            usable_by_expiry[ex] = usable[:6]  # sample to keep printouts readable

        # Time loop setup
        t_end   = time.time() + RUN_SECONDS
        spot    = float(spot0)
        dt_year = 1.0 / (252 * 390)  
        # Time step in years: assume 252 trading days/year and 390 minutes/day.
        # so each loop iteration ≈ 1 trading minute of calendar time.
        # Used for scaling volatility in the spot random walk.

        last_fill_time  = time.time()
        last_build_time = time.time()

        print("\n--- running live loop ---")
        while time.time() < t_end:
            now = time.time()

            # ---- periodic surface refresh (cadence) ----
            if now - last_build_time >= SURF_REFRESH_SEC:
                t_start = time.time()
                new_df  = batch_surface.build_surface(TICKER, expiries, kind=KIND, r=R, q=Q, N=N_BASE)
                new_piv = batch_surface.to_grid(new_df)
                if not new_piv.empty and not np.isnan(new_piv.values).all():
                    piv = new_piv
                    # refresh the set of usable strikes after a rebuild
                    usable_by_expiry = {}
                    for ex in piv.index:
                        usable = [(k, piv.loc[ex, k]) for k in piv.columns if np.isfinite(piv.loc[ex, k])]
                        usable_by_expiry[ex] = usable[:6]
                    print(f"[surface] rebuilt in {time.time()-t_start:.2f}s, rows={len(new_df)}")
                last_build_time = now

            # ---- cadence gate: ensure we only run one "trading tick" every FILL_INTERVAL_SEC seconds ----

            if now - last_fill_time < FILL_INTERVAL_SEC:
                continue
            last_fill_time = now

            # 1) spot move
            spot = simulate_spot_rw(spot, dt_year, SPOT_ANNUAL_VOL)
            print(f"\nTick: spot={spot:.4f}")

            # 2) quote each expiry (uses cached surface IVs)
            for ex in piv.index:
                T = live_data.yearfrac(ex)
                N_local = adaptive_steps(T)
                usable = usable_by_expiry.get(ex, [])
                if not usable:
                    continue

                for K, iv in usable:
                    # inventory-aware quoting in one call:
                    # returns (fv_raw, fv_adj, (bid, ask))
                    fv_raw, fv_adj, (bid, ask) = make_inventory_aware_quotes(
                        book, ex,
                        S=spot, K=K, T=T, r=R, q=Q, iv=iv, N=N_local, option=OPTION,
                        edge_abs=EDGE_ABS, edge_bps=EDGE_BPS,
                        k_delta=1e-4, k_vega=1e-2, bias_cap=1.00
                    )

                    # skip pathological outcomes
                    if not (np.isfinite(fv_adj) and np.isfinite(bid) and np.isfinite(ask)):
                        continue
                    if bid >= ask or fv_adj < 0.02:
                        continue

                    # log the quote
                    qwriter.writerow([time.time(), ex, float(K), float(fv_adj), float(bid), float(ask), float(iv)])
                    print(f"  QUOTE K={K:.1f} IV={iv:.4f} | FV_raw={fv_raw:.4f} FV_adj={fv_adj:.4f} → {bid:.4f}/{ask:.4f}")

                    # 3) toy fills
                    r = np.random.rand()
                    if r < PROB_LIFT_ASK:
                        qty = -1   # SELL 1 (short option)
                        price = ask
                        d, v = book.apply_fill(ex, qty, spot, K, T, R, Q, iv, N_local, option=OPTION)
                        fills_count += 1
                        fwriter.writerow([time.time(), ex, float(K), "SELL", qty, float(price), float(spot)])
                        print(f"    FILL: SOLD   1 @ {price:.2f} | Δ={d:+.2f}, V={v:+.4f}")
                    elif r < PROB_LIFT_ASK + PROB_HIT_BID:
                        qty = +1   # BUY 1 (long option)
                        price = bid
                        d, v = book.apply_fill(ex, qty, spot, K, T, R, Q, iv, N_local, option=OPTION)
                        fills_count += 1
                        fwriter.writerow([time.time(), ex, float(K), "BUY", qty, float(price), float(spot)])
                        print(f"    FILL: BOUGHT 1 @ {price:.2f} | Δ={d:+.2f}, V={v:+.4f}")
            
            # Revalue Greek exposures using current spot + latest surface before hedging
            book.revalue_exposures(spot, piv, r=R, q=Q, N=N_BASE)
            
            # 4) vega hedge (same-expiry ATM) if outside band
            for ex in piv.index:
                T = live_data.yearfrac(ex)
                N_local = adaptive_steps(T)
                qty_vh, _ = vega_hedge(
                    book, expiry=ex, spot=spot, T=T, r=R, q=Q, piv=piv, N=N_local,
                    option=OPTION, vega_band=VEGA_BAND,
                    hedge_fraction=VEGA_HEDGE_FRAC, max_contracts=VEGA_MAX_CNTR
                )
                if qty_vh != 0:
                    vega_hedges += 1
                    print(f"  VEGA HEDGE: {('BUY' if qty_vh>0 else 'SELL')} {abs(qty_vh)} x ATM {ex} "
                            f"(new vega={book.net_vega.get(ex,0.0):+.4f})")
                    hwriter.writerow([time.time(), "VEGA", qty_vh, float(spot), float(spot)])
            
            # Revalue Greek exposures (which may have changed due to vega hedging)
            book.revalue_exposures(spot, piv, r=R, q=Q, N=N_BASE)
            
            # 5) delta hedge (in shares) if exposure too large
            net_delta_total_sh = book.net_delta * CONTRACT_MULT + book.under_pos['qty']
            if abs(net_delta_total_sh) > DELTA_HEDGE_THRESHOLD_SHARES:
                hedge_shares = -int(round(net_delta_total_sh))
                book.apply_share_hedge(spot, hedge_shares)
                delta_hedges += 1
                hwriter.writerow([time.time(), 'DELTA', hedge_shares, float(spot), float(spot)])
                print(f"DELTA HEDGE: traded {hedge_shares:+d} sh → "
                    f"Δ_total(sh)={book.net_delta*CONTRACT_MULT + book.under_pos['qty']:+.0f}")
            
            print(f"Risk: Δ_options(sh)={book.net_delta*CONTRACT_MULT:+.0f}, "
                f"Δ_total(sh)={book.net_delta*CONTRACT_MULT + book.under_pos['qty']:+.0f}, "
                f"vega={ {ex: round(book.net_vega.get(ex,0.0),4) for ex in piv.index} }")


        # ---------- end loop ----------

    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    finally:
        # end-of-run snapshot & persistence
        try:
            if 'piv' in locals():
                unreal = book.mark_unrealized(spot, piv, r=R, q=Q, N=N_BASE)
            else:
                unreal = 0.0
        except Exception:
            unreal = 0.0

        if 'fills_count' in locals():
            print("\n--- summary ---")
            print(f"Fills: {fills_count} | Delta hedges: {delta_hedges} | Vega hedges: {vega_hedges}")
            print(f"\nFinal spot ~ {spot:.4f}")
            print(f"\nRealized PnL:   {getattr(book,'realized_pnl',0.0):+.2f}")
            print(f"Unrealized PnL: {unreal:+.2f}")
            print(f"Total PnL:      {getattr(book,'realized_pnl',0.0) + unreal:+.2f}")
            print(f"\nFinal net Δ (options-only, sh) = {book.net_delta*CONTRACT_MULT:+.0f}")
            print(f"Final net Δ (TOTAL sh incl. stock) = {book.net_delta*CONTRACT_MULT + book.under_pos['qty']:+.0f}")
            print(f"Final per-expiry vega = {{ {', '.join([f'{k}: {round(v,4)}' for k,v in book.net_vega.items()])} }}")

        
        snap = book.inventory_snapshot(include_greeks=True,
                               spot=spot, surface_piv=piv,
                               r=R, q=Q, N=N_BASE)
        rows = snap.get("options_with_greeks", [])

        print("\nInventory:")

        # print stock first
        sh = book.under_pos["qty"]
        if sh:
            print(f"  Underlying   qty={sh}")

        # table header
        print(f"{'Expiry':<12} {'Strike':<6} {'Type':<4} {'Qty':>5} {'Δ/opt':>10} {'Δ_total(sh)':>14} {'V/opt':>10} {'V_total':>10}")

        opts_delta_sh_sum = 0.0
        opts_vega_sum = 0.0
        
        # table rows
        for r_ in rows:
            opt_code = "C" if r_["type"].lower().startswith("c") else "P"
            strike_lbl = int(r_["strike"]) if float(r_["strike"]).is_integer() else r_["strike"]
            
            # accumulate totals
            opts_delta_sh_sum += r_["delta_shares_total"]
            opts_vega_sum     += r_["vega_total"]
            
            print(f"{r_['expiry']:<12} {strike_lbl:<6} {opt_code:<4} "
                f"{r_['qty']:>+5d} {r_['delta_per_opt']:>+10.4f} {r_['delta_shares_total']:>+14.0f} "
                f"{r_['vega_per_opt']:>+10.4f} {r_['vega_total']:>+10.4f}")

        # Totals row(s)
        print("-" * 86)
        print(f"{'Totals (options-only)':<24} "
            f"{'':>5} {'':>10} {opts_delta_sh_sum:>+14.0f} {'':>10} {opts_vega_sum:>+14.4f}")
    
        # persist risk state and close logs
        try:
            book.save("risk_state.json")
        except Exception:
            pass
        for f in (qf, ff, hf):
            try: f.close()
            except: pass


if __name__ == "__main__":
    main()
