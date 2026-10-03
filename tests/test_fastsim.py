import math

from sim.fastsim import run
from sim.scenario import make_scenario


def test_scenario_is_deterministic_and_truth_is_separate():
    a, b = make_scenario(5), make_scenario(5)
    assert (a.victims_xy == b.victims_xy).all() and a.pings == b.pings
    assert "victims_xy" not in a.observable()


def test_runs_are_reproducible():
    scn = make_scenario(2)
    r1, r2 = run(scn, "bayes", t_max=900), run(scn, "bayes", t_max=900)
    assert r1 == r2


def test_both_methods_produce_results():
    scn = make_scenario(1)
    for m in ("bayes", "grid"):
        r = run(scn, m, t_max=1200)
        assert r.n_victims >= 3 and 0 <= r.found_20min <= r.found_total <= r.n_victims
        assert math.isnan(r.ttff_s) or 0 < r.ttff_s <= 1200
