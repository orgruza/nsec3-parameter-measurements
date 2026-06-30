#!/usr/bin/env python3
"""
Plot the NSEC3 parameter distribution as complementary cumulative distribution
functions (CCDFs).

Input:
  results_all_merged.csv with NSEC3PARAM measurement results.

The script aggregates per domain by taking the maximum observed iteration count
and maximum observed salt length over all NSEC3PARAM rows with status == "ok".

Output:
  PDF figure showing the share of zones that meet or exceed a given salt length
  or iteration count.
"""

import argparse
import csv
import os
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt


plt.rcParams.update({
    "font.size": 11,
    "axes.labelsize": 12,
    "legend.fontsize": 11,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
})


def load_domain_maxima(csv_path: str) -> Tuple[List[int], List[int]]:
    """Return per-domain maximum iteration count and salt length."""
    max_iter: Dict[str, int] = {}
    max_salt: Dict[str, int] = {}

    with open(csv_path, newline="", encoding="utf-8", errors="replace") as infile:
        reader = csv.reader(infile)
        header = next(reader, None)

        if not header:
            raise RuntimeError("CSV file is empty or missing header")

        for row in reader:
            if len(row) < 10:
                continue

            domain = row[0].strip()
            status = row[1].strip()

            if status != "ok":
                continue

            try:
                iterations = int(row[7])
                salt_len = int(row[8])
            except ValueError:
                continue

            if domain not in max_iter or iterations > max_iter[domain]:
                max_iter[domain] = iterations

            if domain not in max_salt or salt_len > max_salt[domain]:
                max_salt[domain] = salt_len

    domains = set(max_iter) & set(max_salt)

    return (
        [max_iter[domain] for domain in domains],
        [max_salt[domain] for domain in domains],
    )


def compute_ccdf(values: List[int]) -> Tuple[List[int], List[float]]:
    """Compute CCDF: y(x) = share of zones with value >= x."""
    if not values:
        raise RuntimeError("No values provided for CCDF")

    counts: Dict[int, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1

    xs = sorted(counts)

    suffix = 0
    ge_counts: Dict[int, int] = {}
    for x in reversed(xs):
        suffix += counts[x]
        ge_counts[x] = suffix

    n = len(values)
    ys = [ge_counts[x] / n for x in xs]

    return xs, ys


def clip_xy(xs: List[int], ys: List[float], x_max: int) -> Tuple[List[int], List[float]]:
    """Clip plotted x/y pairs to x <= x_max."""
    clipped = [(x, y) for x, y in zip(xs, ys) if x <= x_max]
    if not clipped:
        return [], []
    x_clip, y_clip = zip(*clipped)
    return list(x_clip), list(y_clip)


def plot_ccdf(
    iter_vals: List[int],
    salt_vals: List[int],
    out_path: str,
    x_max: int,
) -> None:
    """Create the CCDF figure."""
    x_iter, y_iter = compute_ccdf(iter_vals)
    x_salt, y_salt = compute_ccdf(salt_vals)

    x_iter, y_iter = clip_xy(x_iter, y_iter, x_max)
    x_salt, y_salt = clip_xy(x_salt, y_salt, x_max)

    plt.figure(figsize=(6, 2.5))

    plt.plot(
        x_salt,
        y_salt,
        label="Salt Length",
        color="tab:blue",
        linewidth=2.5,
    )

    plt.plot(
        x_iter,
        y_iter,
        label="Iteration Count",
        color="tab:orange",
        linewidth=2.5,
    )

    plt.xlabel("Salt Length / Iteration Count")
    plt.ylabel("Share of Zones")

    plt.xlim(0, x_max)
    plt.ylim(0, 1)

    plt.legend(loc="best")
    plt.grid(True, linestyle=":", linewidth=0.5)

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, bbox_inches="tight")
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot NSEC3 salt-length and iteration-count CCDFs."
    )
    parser.add_argument("csv", help="NSEC3 measurement CSV")
    parser.add_argument(
        "--out",
        default="figures/nsec3_salt_iterations_ccdf.pdf",
        help="Output PDF file",
    )
    parser.add_argument(
        "--x-max",
        type=int,
        default=150,
        help="Maximum x-axis value shown in the plot",
    )

    args = parser.parse_args()

    iter_vals, salt_vals = load_domain_maxima(args.csv)

    print(f"Loaded {len(iter_vals)} NSEC3 domains")
    plot_ccdf(iter_vals, salt_vals, args.out, args.x_max)
    print(f"Wrote figure: {args.out}")


if __name__ == "__main__":
    main()
