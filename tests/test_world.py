import numpy as np

from sim.world import (CELL_M, N_CELLS, SIZE_M, cell_to_latlon, cell_to_xy, corners_latlon, latlon_to_cell,
                       xy_to_cell)


def test_grid_constants():
    assert (N_CELLS, CELL_M, SIZE_M) == (80, 25.0, 2000.0)


def test_row0_is_north():
    lat_n, _ = cell_to_latlon(0, 40)
    lat_s, _ = cell_to_latlon(79, 40)
    assert lat_n > lat_s


def test_cell_roundtrip():
    for r, c in [(0, 0), (79, 79), (31, 44), (10, 70)]:
        assert tuple(int(v) for v in latlon_to_cell(*cell_to_latlon(r, c))) == (r, c)
        assert tuple(int(v) for v in xy_to_cell(*cell_to_xy(r, c))) == (r, c)


def test_grid_is_2km_and_centred_on_ooty():
    c = corners_latlon()
    lat_mid = (c["nw"][0] + c["sw"][0]) / 2
    lon_mid = (c["nw"][1] + c["ne"][1]) / 2
    assert abs(lat_mid - 11.41) < 1e-3 and abs(lon_mid - 76.70) < 1e-3
    height_m = (c["nw"][0] - c["sw"][0]) * 110_600
    assert abs(height_m - 2000) < 20
    assert np.isfinite(list(c.values())).all()
