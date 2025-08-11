# Options-Implied-Volatility-Surface

This project computes **American option implied volatilities** across multiple strikes and expiries using a **binomial pricing model** and visualizes the results as both a **heatmap** and a **3D surface**.

It is designed for learning, experimentation, and as a stepping stone toward building more advanced **options market-making simulations**.


## Features
- **American option pricing** via Cox–Ross–Rubinstein (binomial) model
- **Bisection method** IV solver for any given market option price
- Fetch **live option chain data** from Yahoo Finance (`yfinance`)
- Batch IV computation across strikes and expiries
- Visualization as both:
  - **Heatmap** (expiry vs. strike)
  - **3D surface plot** for volatility term/moneyness structure

## Limitations
- Assumes constant volatility and interest rates over the option’s life.
- Dividends modeled as continuous yield (q) — discrete dividends not supported.
- Binomial parameters may cause unstable probabilities for very short maturities or extreme inputs.
- Accuracy depends on the number of steps N — too low is inaccurate, too high is slow.
- IV solving uses a numerical method (bisection) — results depend on tolerance and step settings.
- Uses Yahoo Finance data, which may have delays or occasional missing fields.

## Requirements
- NumPy
- Pandas
- Matplotlib
- yfinance

Install dependencies:
```bash
pip install numpy pandas matplotlib yfinance
