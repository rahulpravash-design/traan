"""Cut the recorded Find-loop run into the 2:30 demo video (script: docs/PLAN.md).

    python docs/demo/make_video.py <recording.webm> <record.log> <out.mp4>

record.log is docs/demo/record.cjs's output ("<seconds> MARK pin / confirm ..."), used to cut at the
right moments. Captions say what is real and what is simulated (CLAUDE.md §7): PX4 SITL drones,
HIT-UAV thermal frame replay, and any speed-up.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import numpy as np
from moviepy import ColorClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
W, H = 1280, 720
BG, INK, MUTED, ACCENT, GOOD, ORANGE = "#fcfcfb", "#0b0b0b", "#52514e", "#2a78d6", "#008300", "#eb6834"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def card(lines, sub=None):
    """Full-screen title card. lines: [(text, size, bold, colour)]."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 12, H], fill=ACCENT)
    y = 150
    for text, size, bold, colour in lines:
        d.text((110, y), text, font=font(size, bold), fill=colour)
        y += int(size * 1.45)
    if sub:
        d.text((110, H - 90), sub, font=font(20), fill=MUTED)
    return np.array(img)


CAP_W = 900   # caption spans the map only, so the dashboard panel (Confirm / Reject) stays visible


def caption(text, small=None):
    """Lower-third caption bar (RGBA) over the map area."""
    img = Image.new("RGBA", (CAP_W, 92), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([16, 8, CAP_W - 8, 84], radius=12, fill=(11, 11, 11, 215))
    d.text((36, 18 if small else 32), text, font=font(24, True), fill="white")
    if small:
        d.text((36, 54), small, font=font(16), fill=(220, 220, 214))
    return np.array(img)


def with_caption(clip, text, small=None):
    bar = ImageClip(caption(text, small), transparent=True).with_duration(clip.duration).with_position((0, H - 100))
    return CompositeVideoClip([clip, bar], size=(W, H))


def still(arr, dur):
    return ImageClip(arr).with_duration(dur)


def fit(path, dur, title):
    """An image (chart) letterboxed onto the background with a title."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((60, 36), title, font=font(30, True), fill=INK)
    pic = Image.open(path).convert("RGB")
    pic.thumbnail((W - 120, H - 150))
    img.paste(pic, ((W - pic.width) // 2, 100))
    return still(np.array(img), dur)


def crosscheck_card():
    rows = list(csv.DictReader(open(ROOT / "bench/results/px4_check.csv")))
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((60, 40), "Same planner on PX4 SITL: does the fast sim hold up?", font=font(32, True), fill=INK)
    d.text((60, 92), "Time to first find, 3 scenarios, 3 PX4 drones (simulated seconds)", font=font(22), fill=MUTED)
    x = [80, 300, 560, 820, 1060]
    heads = ["Scenario", "Bayes · PX4", "Bayes · fast sim", "Grid · PX4", "Grid · fast sim"]
    for xi, h in zip(x, heads):
        d.text((xi, 170), h, font=font(22, True), fill=INK)
    by = {(r["seed"], r["method"]): r for r in rows}
    for i, seed in enumerate(sorted({r["seed"] for r in rows})):
        y = 230 + i * 62
        b, g = by[(seed, "bayes")], by[(seed, "grid")]
        vals = [seed, f"{float(b['ttff_s']):.0f} s", f"{float(b['fastsim_ttff_s']):.0f} s",
                f"{float(g['ttff_s']):.0f} s", f"{float(g['fastsim_ttff_s']):.0f} s"]
        cols = [INK, ACCENT, ACCENT, ORANGE, ORANGE]
        for xi, v, c in zip(x, vals, cols):
            d.text((xi, y), v, font=font(30, xi in (300, 820)), fill=c)
    d.text((80, 470), "PX4 within 7–11% of the fast sim in every run.", font=font(28, True), fill=INK)
    d.text((80, 515), "Bayesian search finds the first victim 7–10× sooner than a grid sweep.", font=font(28), fill=INK)
    d.text((80, 600), "Fast sim: 100 scenarios, real terrain + buildings. With a 400 m wrong prior Bayes still wins",
           font=font(20), fill=MUTED)
    d.text((80, 628), "80 of 100, but 4 runs find nobody in an hour vs 0 for the grid sweep. bench/results/*.csv",
           font=font(20), fill=MUTED)
    return still(np.array(img), 15)


def main(rec_path, log_path, out_path):
    marks = {}
    for line in open(log_path):
        m = re.match(r"\s*([\d.]+)\s+MARK (\w+)", line)
        if m and m.group(2) not in marks:
            marks[m.group(2)] = float(m.group(1))
    rec = VideoFileClip(rec_path)
    pin, confirm = marks["pin"], marks["confirm"]
    # record.cjs logs from its own start; the video starts at page creation, ~ the same instant
    t_pin = min(pin, rec.duration - 1)
    t_det = max(t_pin + 25, confirm - 7)          # pending card appears ~4-5 s before the click

    parts = [
        still(card([("TRAAN", 64, True, INK),
                    ("AI mission brain for drone search-and-rescue", 32, False, MUTED),
                    ("", 20, False, INK),
                    ("Landslide search today: 134.5 min to reach victims,", 34, True, INK),
                    ("2.2× the golden hour. In Wayanad it was done by hand.", 34, True, INK)],
                   sub="Team CTRL ALT ELITE · Smart India Hackathon 2026 · prototype, simulation only"), 15),
        with_caption(rec.subclipped(max(0, t_pin - 8), t_pin + 12),
                     "An alert comes in: the operator drops a pin near Ooty",
                     "Prior map from the pin, real SRTM terrain and building footprints"),
        with_caption(rec.subclipped(t_pin + 12, t_det).with_speed_scaled(final_duration=35),
                     "3 drones fly the planner's legs; searched cells fade",
                     "PX4 SITL drones (simulated) · PX4 at 4× · video sped up"),
        with_caption(rec.subclipped(t_det, min(rec.duration, t_det + 28)),
                     "Thermal frame → YOLOv8n flags a person → operator confirms",
                     "Thermal frame replay (HIT-UAV test set), not a live camera · test mAP50 0.900"),
    ]
    parts[-1] = concatenate_videoclips([parts[-1], still(parts[-1].get_frame(parts[-1].duration - 0.05), 30 - parts[-1].duration)]) \
        if parts[-1].duration < 30 else parts[-1]
    parts += [
        fit(ROOT / "bench/results/fastsim_100.png", 15, "Benchmark: Bayesian search vs grid sweep, 100 scenarios"),
        crosscheck_card(),
        still(card([("≈50% complete: 6 of 9 modules working", 40, True, INK),
                    ("Scenario · 3-drone PX4 fleet · Bayesian planner", 28, False, INK),
                    ("Thermal detection · Commander dashboard · Benchmark", 28, False, INK),
                    ("", 18, False, INK),
                    ("Next: comms-loss handling, ground robot + kit drop,", 30, True, ACCENT),
                    ("signed commands", 30, True, ACCENT),
                    ("", 18, False, INK),
                    ("github.com/rahulpravash-design/traan", 26, False, MUTED)],
                   sub="Data: NASA SRTM · Google Open Buildings · HIT-UAV (Suo et al. 2023, CC BY 4.0)"), 20),
    ]
    video = concatenate_videoclips([p.resized((W, H)) for p in parts], method="compose")
    video.write_videofile(out_path, fps=25, codec="libx264", bitrate="900k", audio=False,
                          preset="medium", ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"])
    print(f"wrote {out_path}: {video.duration:.1f} s")


if __name__ == "__main__":
    main(*sys.argv[1:4])
