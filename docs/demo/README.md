# Demo video

**Current cut (2:30):** https://claude.ai/artifact/M85fGSSw6ac5yXEnF12hbk. It's private until the owner
shares it from the page's Share menu. It was recorded on 3 Oct 2026 from a real run: 3 PX4 SITL drones,
YOLOv8n on replayed HIT-UAV frames, and a scripted operator.

## Re-recording it

1. Start the stack, with PX4 at 4× so the search fits the video:
   ```bash
   PX4_SIM_SPEED_FACTOR=4 PX4_DIR=~/PX4-Autopilot ./fleet/px4_sitl.sh 3
   uvicorn api.main:app --port 8000 &
   uvicorn perception.service:app --port 8001 &          # YOLO; needs perception/weights/best.pt
   (cd dashboard && npm run dev) &
   python -m sim.replay_mapper --seed 1 --wait-for-pin &  # victims hidden; the operator drops the pin
   python -m fleet.run --drones 3 &
   ```
2. Write the scenario for the scripted operator (where to drop the pin; where the victims are, so it can
   tell real detections from false alarms):
   ```bash
   python -c "import json; from sim.scenario import make_scenario; from sim.fastsim import reachable_victims; \
   from sim.world import xy_to_latlon as ll; s=make_scenario(1); v,_=reachable_victims(s); \
   json.dump({'alert':[float(x) for x in ll(*s.alert_xy)],'victims':[[float(x) for x in ll(*s.victims_xy[k])] for k,_ in v],'max_s':480}, open('scn1.json','w'))"
   ```
3. Record, then cut:
   ```bash
   NODE_PATH=$(npm root -g) node docs/demo/record.cjs rec scn1.json | tee record.log   # needs: npm i -g playwright
   pip install moviepy imageio-ffmpeg
   python docs/demo/make_video.py rec/*.webm record.log traan_demo.mp4
   ```

The captions follow CLAUDE.md §7: they say "PX4 SITL" and "thermal frame replay", and they state every speed-up.
