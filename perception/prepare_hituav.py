"""Build the person-only HIT-UAV subset and the frame-replay index.

    python -m perception.prepare_hituav --src data/hit-uav --dst data/hituav_person

Expects the HIT-UAV YOLO layout: <src>/images/{train,val,test}/*.jpg and <src>/labels/{...}/*.txt,
classes 0 Person, 1 Car, 2 Bicycle, 3 OtherVehicle, 4 DontCare. Keeps class 0 only.
Writes <dst>/data.yaml for training and <dst>/replay_index.json (test frames with / without people).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

SPLITS = ("train", "val", "test")


def main(src: Path, dst: Path):
    index = {"person": [], "empty": []}
    for split in SPLITS:
        (dst / "images" / split).mkdir(parents=True, exist_ok=True)
        (dst / "labels" / split).mkdir(parents=True, exist_ok=True)
        imgs = sorted((src / "images" / split).glob("*.jpg"))
        if not imgs:
            raise SystemExit(f"no images in {src / 'images' / split} — run data/fetch.sh first")
        for img in imgs:
            lab = src / "labels" / split / (img.stem + ".txt")
            lines = [ln for ln in (lab.read_text().splitlines() if lab.exists() else []) if ln.split()[:1] == ["0"]]
            out_img = dst / "images" / split / img.name
            if not out_img.exists():
                try:
                    os.symlink(img.resolve(), out_img)
                except OSError:
                    shutil.copy2(img, out_img)
            (dst / "labels" / split / (img.stem + ".txt")).write_text("\n".join(lines) + ("\n" if lines else ""))
            if split == "test":
                index["person" if lines else "empty"].append(f"test/{img.name}")
        print(f"{split}: {len(imgs)} images")

    (dst / "data.yaml").write_text(
        f"path: {dst.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: person\n")
    (dst / "replay_index.json").write_text(json.dumps(index, indent=1))
    print(f"replay index: {len(index['person'])} person frames, {len(index['empty'])} empty frames")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=Path("data/hit-uav"))
    ap.add_argument("--dst", type=Path, default=Path("data/hituav_person"))
    a = ap.parse_args()
    main(a.src, a.dst)
