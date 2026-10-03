"""Train and evaluate the person detector on HIT-UAV (person class only).

    python -m perception.train --model yolov8n.pt --epochs 50            # ~1 h on an 8 GB GPU
    python -m perception.train --eval-only --weights perception/weights/best.pt

Reports mAP50, precision and recall on the TEST split (579 images) and writes them to
perception/metrics.json, with how the model was trained (device, epochs, time). That file is
what goes in the README and deck, nothing else. Weights stay out of git (perception/weights/).
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

DATA = Path("data/hituav_person/data.yaml")
OUT = Path("perception/weights")
METRICS = Path("perception/metrics.json")


def evaluate(weights: str, imgsz: int, training: dict | None = None):
    from ultralytics import YOLO

    m = YOLO(weights).val(data=str(DATA), split="test", imgsz=imgsz, plots=False, verbose=False)
    metrics = {"dataset": "HIT-UAV person class (Suo et al. 2023, CC BY 4.0)", "split": "test (579 images)",
               "imgsz": imgsz, "mAP50": round(float(m.box.map50), 4), "mAP50_95": round(float(m.box.map), 4),
               "precision": round(float(m.box.mp), 4), "recall": round(float(m.box.mr), 4),
               "weights": weights}
    if training:
        metrics["training"] = training
    elif METRICS.exists():                      # --eval-only keeps the record of how it was trained
        metrics["training"] = json.loads(METRICS.read_text()).get("training")
    METRICS.write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    return metrics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="yolov8n.pt", help="yolov8n.pt | yolo11n.pt | yolov8s.pt, or a local path")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--weights", default=str(OUT / "best.pt"))
    a = ap.parse_args()

    if not DATA.exists():
        raise SystemExit(f"{DATA} missing — run: ./data/fetch.sh hituav")
    training = None
    if not a.eval_only:
        import torch
        from ultralytics import YOLO

        model = a.model
        if not Path(model).exists() and (OUT / model).exists():
            model = str(OUT / model)            # pre-downloaded starting weights
        t0 = time.time()
        yolo = YOLO(model)
        yolo.train(data=str(DATA), epochs=a.epochs, imgsz=a.imgsz, batch=a.batch, workers=a.workers,
                   seed=a.seed, deterministic=True, plots=False, project="runs", name="hituav_person",
                   exist_ok=True)
        OUT.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(yolo.trainer.save_dir) / "weights" / "best.pt", OUT / "best.pt")
        training = {"base": Path(a.model).name, "epochs": a.epochs, "imgsz": a.imgsz, "batch": a.batch,
                    "device": "cuda" if torch.cuda.is_available() else f"cpu ({torch.get_num_threads()} threads)",
                    "train_images": 2029, "wall_time_min": round((time.time() - t0) / 60, 1)}
    evaluate(a.weights, a.imgsz, training)


if __name__ == "__main__":
    main()
