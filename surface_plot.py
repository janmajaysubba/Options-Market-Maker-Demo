"""
For visualizing American option implied volatility (IV) grids.

Takes pivoted IV data (rows = expiries, columns = strikes) from to_grid() 
and generates either a heatmap or a 3D surface plot.
"""

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa  # Needed for 3D plotting backend


def plot_heatmap(piv, title="American IV Heatmap"):
    """
    Creates a 2D heatmap of implied volatility.

    Parameters:
        piv (DataFrame): Pivoted IV table from to_grid().
                         Rows = expiries, columns = strikes.
        title (str): Title of the plot.
    """
    plt.figure(figsize=(9, 6))

    # Display the IV values as a color-coded image
    plt.imshow(piv.values, aspect="auto", origin="lower")

    # X-axis: strikes (as integers, rotated for readability)
    plt.xticks(range(len(piv.columns)),
               [f"{c:.0f}" for c in piv.columns], rotation=90)

    # Y-axis: expiries (as strings)
    plt.yticks(range(len(piv.index)),
               [str(i) for i in piv.index])

    # Add color scale bar for IV values
    plt.colorbar(label="IV")

    plt.title(title)
    plt.tight_layout()
    plt.show()


def plot_surface_3d(piv, title="American IV Surface"):
    """
    Create a 3D surface plot of implied volatility.

    Parameters:
        piv (DataFrame): Pivoted IV table from to_grid().
                         Rows = expiries, columns = strikes.
        title (str): Title of the plot.
    """
    # Convert expiry (rows) and strike (cols) to meshgrid indices for plotting
    X, Y = np.meshgrid(np.arange(len(piv.columns)),
                       np.arange(len(piv.index)))
    Z = piv.values  # IV values

    # Create a 3D plot
    fig = plt.figure(figsize=(10, 7))
    ax = fig.add_subplot(111, projection='3d')

    # Plot the surface with no wireframe lines and smooth shading
    ax.plot_surface(X, Y, Z, linewidth=0, antialiased=True)

    # Label axes (indices correspond to strike & expiry positions in DataFrame)
    ax.set_title(title)
    ax.set_xlabel("Strike (index)")
    ax.set_ylabel("Expiry (index)")
    ax.set_zlabel("IV")

    plt.tight_layout()
    plt.show()
