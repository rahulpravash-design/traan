"""Pick the detector's confidence threshold from data, and record it in perception/metrics.json.

    python -m perception.operating_point

The replay mapper hands the detector one test frame per "look": a frame with a person when a
victim is in the footprint, a person-free frame otherwise. So what matters in the loop is
frame-level: P(top person score >= t | person frame) is the probability of detection per pass,
and P(top score >= t | empty frame) is the false-alarm rate per look. This sweeps t over the
HIT-UAV test frames and picks the lowest threshold whose frame recall is still >= TARGET_RECALL
(the fast sim's POD_TRUE), so live detections and the benchmark assume the same POD.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from perception.train import METRICS
from sim.fastsim import POD_TRUE

INDEX = Path("data/hituav_person/replay_index.json")
IMAGES = Path("data/hituav_person/images")
WEIGHTS = "perception/weights/best.pt"
TARGET_RECALL = POD_TRUE
SWEEP = np.round(np.arange(0.30, 0.81, 0.05), 2)


def top_scores(model, frames):
    out = []
    for f in frames:
        r = model.predict(str(IMAGES / f), conf=0.1, imgsz=640, verbose=False)[0]
        out.append(float(r.boxes.conf.max()) if len(r.boxes) else 0.0)
    return np.array(out)


def main():
    from ultralytics import YOLO

    idx = json.loads(INDEX.read_text())
    model = YOLO(WEIGHTS)
    p, e = top_scores(model, idx["person"]), top_scores(model, idx["empty"])
    table = [{"conf_min": float(t), "frame_recall": round(float(np.mean(p >= t)), 3),
              "false_alarm_per_empty_frame": round(float(np.mean(e >= t)), 3)} for t in SWEEP]
    ok = [row for row in table if row["frame_recall"] >= TARGET_RECALL - 1e-9]
    chosen = max(ok, key=lambda row: row["conf_min"]) if ok else table[0]
    metrics = json.loads(METRICS.read_text()) if METRICS.exists() else {}
    metrics["operating_point"] = {**chosen, "target_recall": TARGET_RECALL,
                                  "frames": {"person": len(p), "empty": len(e)}, "sweep": table}
    METRICS.write_text(json.dumps(metrics, indent=2) + "\n")
    for row in table:
        mark = "  <- chosen" if row is chosen else ""
        print(f"conf>={row['conf_min']:.2f}  frame recall {row['frame_recall']:.3f}  "
              f"false alarms/empty frame {row['false_alarm_per_empty_frame']:.3f}{mark}")


if __name__ == "__main__":
    main()
