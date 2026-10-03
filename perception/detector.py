"""Swappable person detector.

Everything outside this file talks to `Detector`, never to Ultralytics directly. Ultralytics
YOLOv8/11 is AGPL-3.0: fine for the hackathon, but it clashes with OEM licensing, so keep it
behind this interface and swap in an Apache-2.0 model (e.g. an RT-DETR / YOLOX export) later.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Box:
    conf: float
    xyxy: tuple[float, float, float, float]  # pixels (label oracle: normalised 0-1)


class Detector(Protocol):
    name: str

    def detect(self, image_path: str) -> list[Box]: ...


class UltralyticsDetector:
    name = "yolo"

    def __init__(self, weights: str, conf: float = 0.25, imgsz: int = 640):
        from ultralytics import YOLO  # AGPL-3.0, optional dependency

        self.model, self.conf, self.imgsz = YOLO(weights), conf, imgsz

    def detect(self, image_path):
        r = self.model.predict(image_path, conf=self.conf, imgsz=self.imgsz, verbose=False)[0]
        return [Box(float(c), tuple(map(float, b))) for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]


class LabelOracleDetector:
    """Reads the HIT-UAV ground-truth label next to the frame. FOR PIPELINE TESTING ONLY —
    it is not a detector and its output must never be shown as model performance."""

    name = "label-oracle"

    def detect(self, image_path):
        p = Path(image_path)
        label = p.parent.parent.parent / "labels" / p.parent.name / (p.stem + ".txt")
        if not label.exists():
            return []
        boxes = []
        for line in label.read_text().split("\n"):
            parts = line.split()
            if parts and parts[0] == "0":
                _, cx, cy, w, h = map(float, parts[:5])
                boxes.append(Box(0.9, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)))
        return boxes


def load_detector() -> Detector:
    weights = os.environ.get("TRAAN_WEIGHTS", "perception/weights/best.pt")
    if os.environ.get("TRAAN_DETECTOR", "yolo") == "yolo" and Path(weights).exists():
        return UltralyticsDetector(weights)
    return LabelOracleDetector()
