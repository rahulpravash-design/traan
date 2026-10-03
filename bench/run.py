"""Benchmark: Bayesian search vs grid sweep in the fast 2D sim.

    python -m bench.run --runs 100            # writes bench/results/fastsim_<n>.csv
    python -m bench.run --runs 10 --out bench/results/scratch_10.csv
    python -m bench.run --runs 100 --methods bayes,bayes_cell,grid   # ablation: leg scoring vs cell greedy

Rules (CLAUDE.md): same seeds for both methods; a wrong-prior set with the prior shifted
400 m in a seeded random direction; report median time-to-first-find with IQR and the
share of victims found within 20 minutes. If Bayes does not win, the CSV says so.

Scenarios whose victims all sit inside a no-fly zone have nothing any method could find; they
stay in the CSV (n_victims = 0) but are left out of the summary, and the summary says how many.
"""
from __future__ import annotations

import argparse
import csv
import math
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from sim.fastsim import METHODS, T_MAX_S, run
from sim.scenario import make_scenario
from sim.terrain import DEM_PATH

WRONG_PRIOR_M = 400.0
TERRAIN = "srtm" if DEM_PATH.exists() else "synthetic"  # results differ by terrain; the CSV says which
RESULTS = Path(__file__).resolve().parent / "results"
FIELDS = ["seed", "method", "prior", "terrain", "n_victims", "n_unreachable", "ttff_s", "found_20min",
          "found_total", "frac_20min"]
PRIORS = ("correct", "wrong400")


def _one(seed, methods=("bayes", "grid")):
    scn = make_scenario(seed)
    ang = np.random.default_rng([seed, 400]).uniform(0, 2 * np.pi)
    shift = (WRONG_PRIOR_M * math.cos(ang), WRONG_PRIOR_M * math.sin(ang))
    rows = []
    for prior, shift_m in zip(PRIORS, (None, shift)):
        for method in methods:
            r = run(scn, method, shift_m=shift_m, prior_label=prior)
            rows.append({**r.__dict__, "terrain": TERRAIN, "frac_20min": round(r.frac_20min, 4)})  # NaN if none reachable
    return rows


def summarize(rows):
    """Per (prior, method): median/IQR time to first find, and the share of all reachable
    victims found within 20 min (pooled over runs)."""
    out = []
    methods = list(dict.fromkeys(r["method"] for r in rows))
    for prior in PRIORS:
        for method in methods:
            sel = [r for r in rows if r["prior"] == prior and r["method"] == method and int(r["n_victims"]) > 0]
            if not sel:
                continue
            # censored runs (nothing found in T_MAX) count as +inf so the median stays honest
            t = np.array([float(r["ttff_s"]) if not math.isnan(float(r["ttff_s"])) else np.inf for r in sel])
            q1, med, q3 = np.percentile(t, [25, 50, 75])
            frac = sum(int(r["found_20min"]) for r in sel) / sum(int(r["n_victims"]) for r in sel)
            out.append({"prior": prior, "method": method, "runs": len(sel), "median_ttff_s": med,
                        "iqr_s": (q1, q3), "pct_found_20min": 100 * frac,
                        "no_find_runs": int(np.isinf(t).sum())})
    return out


def _fmt(x):
    return f">{T_MAX_S:.0f}" if np.isinf(x) else f"{x:.0f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=100)
    ap.add_argument("--first-seed", type=int, default=0)
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--methods", default="bayes,grid", help=f"comma list from {list(METHODS)}")
    a = ap.parse_args()
    methods = tuple(a.methods.split(","))
    assert all(m in METHODS for m in methods), methods

    seeds = range(a.first_seed, a.first_seed + a.runs)
    with Pool(a.workers) as pool:
        rows = [r for chunk in pool.map(partial(_one, methods=methods), seeds) for r in chunk]

    out = a.out or RESULTS / f"fastsim_{a.runs}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"wrote {out}  ({len(rows)} rows, terrain={TERRAIN})")
    empty = len({r["seed"] for r in rows if r["n_victims"] == 0})
    unreach = sum(r["n_unreachable"] for r in rows if r["method"] == methods[0] and r["prior"] == PRIORS[0])
    print(f"{unreach} victims sat inside the no-fly zone (unscored); {empty} scenarios had none reachable (excluded)")
    print(f"{'prior':9} {'method':10} {'runs':>4} {'median TTFF s':>13} {'IQR s':>13} {'% found ≤20 min':>16} {'no find':>8}")
    for s in summarize(rows):
        print(f"{s['prior']:9} {s['method']:10} {s['runs']:>4} {_fmt(s['median_ttff_s']):>13} "
              f"{_fmt(s['iqr_s'][0]) + '–' + _fmt(s['iqr_s'][1]):>13} {s['pct_found_20min']:>15.1f}% {s['no_find_runs']:>8}")


if __name__ == "__main__":
    main()
