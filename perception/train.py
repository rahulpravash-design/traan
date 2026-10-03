"""Train and evaluate the person detector on HIT-UAV (person class only).

    python -m perception.train --model yolov8n.pt --epochs 50            # ~1 h on an 8 GB GPU
    python -m perception.train --eval-only --weights perception/weights/best.pt

Reports mAP50, precision and recall on the TEST split (579 images) and writes them to
perception/metrics.json — that file is what goes in the README and deck, nothing else.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

DATA = Path("data/hituav_person/data.yaml")
OUT = Path("perception/weights")


def evaluate(weights: str, imgsz: int):
    from ultralytics import YOLO

    m = YOLO(weights).val(data=str(DATA), split="test", imgsz=imgsz, verbose=False)
    metrics = {"weights": weights, "split": "test", "imgsz": imgsz,
               "mAP50": round(float(m.box.map50), 4), "mAP50_95": round(float(m.box.map), 4),
               "precision": round(float(m.box.mp), 4), "recall": round(float(m.box.mr), 4)}
    Path("perception/metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolov8n.pt", help="yolov8n.pt | yolo11n.pt | yolov8s.pt")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--weights", default=str(OUT / "best.pt"))
    a = ap.parse_args()

    if not DATA.exists():
        raise SystemExit(f"{DATA} missing — run: python -m perception.prepare_hituav")
    if not a.eval_only:
        from ultralytics import YOLO

        r = YOLO(a.model).train(data=str(DATA), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch,
                                seed=a.seed, deterministic=True, project="runs", name="hituav_person")
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(r.save_dir) / "weights" / "best.pt", OUT / "best.pt")
    evaluate(a.weights, a.imgsz)


if __name__ == "__main__":
    main()
