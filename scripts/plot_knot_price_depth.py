#!/usr/bin/env python3
"""
Plot Knot Resolver's NSEC3 price-to-proof-depth model.

Knot Resolver bounds the maximum closest-encloser proof search depth as:

    max_depth = floor(128 / price)

The figure visualizes this implementation model and marks the default downgrade
threshold at price > 51.
"""

import argparse
import os

import matplotlib.pyplot as plt


DEPTH_BUDGET = 128
KNOT_THRESHOLD = 51  # price > 51 => downgrade to insecure


plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 12,
    "legend.fontsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
})


def knot_max_depth(price: int) -> int:
    """Return Knot Resolver's maximum allowed proof depth for a given price."""
    return DEPTH_BUDGET // price


def plot_model(out_path: str, fig_width: float, fig_height: float) -> None:
    """Create the Knot price-depth model figure."""
    xs = list(range(1, DEPTH_BUDGET + 1))
    ys = [knot_max_depth(price) for price in xs]

    plt.figure(figsize=(fig_width, fig_height))

    plt.plot(xs, ys, linewidth=2.5)

    plt.xlabel("NSEC3 Price")
    plt.ylabel("Max. Proof Depth")

    plt.xlim(1, DEPTH_BUDGET)
    plt.ylim(0, DEPTH_BUDGET)

    plt.xticks(list(range(0, DEPTH_BUDGET + 1, 16)))
    plt.gca().set_xticks(list(range(0, DEPTH_BUDGET + 1, 4)), minor=True)
    plt.yticks(list(range(0, DEPTH_BUDGET + 1, 16)))
    plt.gca().set_yticks(list(range(0, DEPTH_BUDGET + 1, 4)), minor=True)

    plt.grid(True, which="major", linestyle=":", linewidth=0.7)
    plt.grid(True, which="minor", linestyle=":", linewidth=0.4)

    plt.axvline(KNOT_THRESHOLD, linestyle="--", linewidth=1.5)

    y_at_threshold = knot_max_depth(KNOT_THRESHOLD)
    plt.annotate(
        "Knot Default Downgrade Threshold\n(Price = 51)",
        xy=(KNOT_THRESHOLD, y_at_threshold),
        xytext=(KNOT_THRESHOLD + 10, min(DEPTH_BUDGET - 10, y_at_threshold + 35)),
        arrowprops=dict(arrowstyle="->", linewidth=1.0),
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="black", linewidth=0.8),
        fontsize=9,
        ha="left",
        va="center",
    )

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot Knot Resolver NSEC3 price-to-depth model."
    )
    parser.add_argument(
        "--out",
        default="figures/knot_price_depth_model.pdf",
        help="Output PDF file",
    )
    parser.add_argument("--fig-width", type=float, default=6.0)
    parser.add_argument("--fig-height", type=float, default=2.5)
    args = parser.parse_args()

    plot_model(args.out, args.fig_width, args.fig_height)
    print(f"Wrote figure: {args.out}")


if __name__ == "__main__":
    main()
