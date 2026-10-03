"""Benchmark chart for the README and deck.

    python -m bench.plot bench/results/fastsim_100.csv     # -> bench/results/fastsim_100.png

Two panels, one measure each (never a dual axis): time-to-first-find per run, and the
share of victims found within 20 minutes. Colours: categorical slots 1-2 of the
docs palette (blue = Bayesian, orange = grid sweep).
"""
from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from sim.fastsim import T_MAX_S  # noqa: E402

COLORS = {"bayes": "#2a78d6", "grid": "#eb6834"}
LABELS = {"bayes": "Bayesian search", "grid": "Grid sweep"}
PRIORS = {"correct": "Prior as built", "wrong400": "Prior shifted 400 m"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def load(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["ttff_s"] = float(r["ttff_s"])
        r["frac_20min"] = float(r["frac_20min"])
    return rows


def main(path):
    rows = load(path)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    rng = np.random.default_rng(0)

    for k, prior in enumerate(PRIORS):
        for j, method in enumerate(COLORS):
            sel = [r for r in rows if r["prior"] == prior and r["method"] == method]
            t = np.array([r["ttff_s"] / 60 if not math.isnan(r["ttff_s"]) else T_MAX_S / 60 for r in sel])
            x = k + (j - 0.5) * 0.36
            ax1.scatter(x + rng.uniform(-0.1, 0.1, len(t)), t, s=12, color=COLORS[method], alpha=0.45,
                        linewidths=0, label=LABELS[method] if k == 0 else None)
            med = np.median(t)
            ax1.plot([x - 0.14, x + 0.14], [med, med], color=INK, lw=2, solid_capstyle="round")
            ax1.annotate(f"{med:.1f} min", (x + 0.15, med), va="center", fontsize=8, color=INK)

            frac = 100 * np.mean([r["frac_20min"] for r in sel])
            ax2.bar(x, frac, width=0.34, color=COLORS[method])
            ax2.annotate(f"{frac:.0f}%", (x, frac + 1.5), ha="center", fontsize=9, color=INK)

    ax1.axhline(T_MAX_S / 60, color=MUTED, lw=1, ls=(0, (2, 2)))
    ax1.annotate("no find in 60 min", (1.5, T_MAX_S / 60), xytext=(0, 4), textcoords="offset points",
                 ha="right", fontsize=8, color=MUTED)
    ax1.set_ylabel("Time to first find (min)", color=MUTED)
    ax1.set_title("Time to first find, one dot per scenario", loc="left", fontsize=11, color=INK)
    ax2.set_ylabel("Victims found within 20 min (%)", color=MUTED)
    ax2.set_ylim(0, 105)
    ax2.set_title("Share of victims found within 20 min", loc="left", fontsize=11, color=INK)

    for ax in (ax1, ax2):
        ax.set_facecolor("#fcfcfb")
        ax.set_xticks(range(len(PRIORS)), list(PRIORS.values()), color=INK)
        ax.tick_params(colors=MUTED, length=0)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

    n = len({r["seed"] for r in rows})
    fig.legend(loc="upper right", frameon=False, fontsize=9, markerscale=2)
    fig.suptitle(f"TRAAN fast 2D sim: {n} scenarios, same seeds for both methods", x=0.01, ha="left",
                 fontsize=12, color=INK, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = Path(path).with_suffix(".png")
    fig.savefig(out, facecolor=fig.get_facecolor())
    print(f"wrote {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "bench/results/fastsim_100.csv")
