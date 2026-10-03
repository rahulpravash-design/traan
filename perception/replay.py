"""Frame replay: stands in for a thermal camera until real footage exists.

When a simulated drone's footprint covers a victim's cell we hand the detector a HIT-UAV
test frame that contains a person; otherwise a person-free frame. Choice is seeded by
(scenario seed, drone, step) so a run replays identically. Label it "frame replay" on screen.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path("data/hituav_person")


class FrameReplay:
    def __init__(self, root: Path = ROOT, seed: int = 0):
        self.root = Path(root)
        idx = json.loads((self.root / "replay_index.json").read_text())
        self.person, self.empty = idx["person"], idx["empty"]
        self.seed = seed

    def pick(self, drone: str, step: int, victim_in_view: bool) -> str:
        pool = self.person if victim_in_view else self.empty
        rng = np.random.default_rng([self.seed, int(drone.lstrip("d") or 0), step])
        return pool[int(rng.integers(len(pool)))]

    def path(self, frame: str) -> Path:
        return self.root / "images" / frame
