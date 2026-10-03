import numpy as np

from planner.allocate import assign
from planner.baseline import lawnmower
from planner.bayes import bayes_update, on_confirmed_find, pod_from_sweep, top_cells
from planner.nofly import DEFAULT_ZONES, nofly_mask, route
from planner.prior import build_prior, shift_prior
from planner.service import Planner
from sim.scenario import make_scenario


def test_koopman_pod():
    assert abs(pod_from_sweep(50, 25, 625) - (1 - np.exp(-2))) < 1e-12


def test_bayes_update_moves_mass_out_of_searched_cells():
    P = np.full((80, 80), 1 / 6400)
    searched = np.zeros((80, 80), bool)
    searched[:10] = True
    Q = bayes_update(P, searched, 0.8)
    assert abs(Q.sum() - 1) < 1e-12
    assert Q[searched].max() < P[searched].min() < Q[~searched].min()


def test_confirmed_find_resolves_cell():
    P = build_prior((1000, 1000))
    Q = on_confirmed_find(P, 40, 40)
    assert Q[40, 40] == 0 and abs(Q.sum() - 1) < 1e-12


def test_prior_peaks_near_alert_and_has_floor():
    P = build_prior((500, 1500))
    r, c = np.unravel_index(P.argmax(), P.shape)
    assert abs(c - 20) <= 2 and abs(r - 20) <= 2
    assert P.min() > 0 and abs(P.sum() - 1) < 1e-12


def test_shift_prior_moves_peak():
    P = build_prior((1000, 1000))
    Q = shift_prior(P, 400, 0)
    (r0, c0), (r1, c1) = np.unravel_index(P.argmax(), P.shape), np.unravel_index(Q.argmax(), Q.shape)
    assert c1 - c0 == 16 and r1 == r0


def test_assign_respects_claims_and_nofly():
    P = np.zeros((80, 80))
    P[40, 40] = 1.0
    P[10, 10] = 0.5
    blocked = np.zeros((80, 80), bool)
    assert assign(P, (1000, 1000), [], blocked) == (40, 40)
    assert assign(P, (1000, 1000), [(40, 40)], blocked) != (40, 40)
    blocked[40, 40] = True
    assert assign(P, (1000, 1000), [], blocked) != (40, 40)


def test_route_avoids_nofly():
    z = DEFAULT_ZONES[0]
    a, b = (z.x0 - 100, (z.y0 + z.y1) / 2), (z.x1 + 100, (z.y0 + z.y1) / 2)
    assert z.segment_hits(a, b)
    pts = [a] + route(a, b)
    assert len(pts) > 2
    assert not any(z.segment_hits(p, q) for p, q in zip(pts[:-1], pts[1:]))


def test_lawnmower_never_enters_nofly():
    for wps in lawnmower(3, start_xy=(1000, 0)):
        for p, q in zip(wps[:-1], wps[1:]):
            assert not any(z.segment_hits(p, q) for z in DEFAULT_ZONES)


def test_planner_never_targets_nofly_and_emits_contract_map_update():
    scn = make_scenario(3)
    pl = Planner(3)
    pl.set_prior(scn.observable())
    nf = nofly_mask()
    for i in range(3):
        pl.next_route(i, (1000.0, 0.0))
        assert not nf[pl.targets[i]]
    mu = pl.map_update()
    assert mu["type"] == "map_update" and mu["version"] >= 1
    assert all(len(t) == 3 for t in mu["top_cells"])
    assert mu["top_cells"] == sorted(mu["top_cells"], key=lambda t: -t[2])
    assert top_cells(pl.P, 5)[0][:2] == mu["top_cells"][0][:2]
