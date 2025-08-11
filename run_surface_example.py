"""
End-to-end example script for building and plotting an American Option
Implied Volatility (IV) surface.

Steps performed:
1. Fetches available option expiries for the given ticker.
2. Computes American IVs for a subset of expiries (using binomial pricer + IV solver).
3. Transforms the data into a grid format.
4. Plots the results as both a heatmap and a 3D surface.
"""

from live_data import list_expiries            # Fetch list of option expirations
from batch_surface import build_surface, to_grid  # Batch IV computation + pivoting
from surface_plot import plot_heatmap, plot_surface_3d  # Plotting utilities

# ----------------------
# User-configurable settings
# ----------------------
ticker = "SPY"     # Underlying ticker symbol (AAPL, TSLA, etc.)
kind   = "calls"   # Option type: "calls" or "puts"
r, q, N = 0.04, 0.00, 300  # Risk-free rate, continous dividend yield, binomial steps

# ----------------------
# Step 1: Select expiries
# ----------------------
# Get all expiries for the ticker and take only the first 3 for faster demo runtime
expiries = list_expiries(ticker)[:3]

# ----------------------
# Step 2: Build the IV surface data
# ----------------------
# Computes IVs for each expiry/strike combo in the given expiries list
surf_df = build_surface(ticker, expiries, kind=kind, r=r, q=q, N=N)

# Convert long-format DataFrame → 2D grid (rows=expiry, cols=strike, values=IV)
piv = to_grid(surf_df)

# ----------------------
# Step 3: Plot results
# ----------------------
# Plot as a heatmap (expiry vs. strike, colored by IV)
plot_heatmap(piv, title=f"{ticker} American IV Heatmap")

# Plot as a 3D surface for more visual insight
plot_surface_3d(piv, title=f"{ticker} American IV Surface")
