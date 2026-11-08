#!/usr/bin/env python3
"""Sample the Strata server's own /metrics (JSON) during a load test."""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8899"
KEY = open("/workspace/Strata/logs/api-key.txt").read().strip()
out = sys.argv[1] if len(sys.argv) > 1 else "/workspace/Strata/results/loadtest/server-metrics.jsonl"
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 1800
interval = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
stopfile = out + ".stop"

f = open(out, "w")
t0 = time.time()
while time.time() - t0 < duration:
    try:
        if open(stopfile).read().strip() == "stop":
            break
    except OSError:
        pass
    try:
        req = urllib.request.Request(BASE + "/metrics",
                                     headers={"Authorization": "Bearer " + KEY})
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        rec = {
            "t": round(time.time() - t0, 1),
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "live": d.get("live"),
            "engine": {k: (d.get("engine") or {}).get(k) for k in
                       ("expert_slots", "expert_cache_mib", "vram_free_mib", "context", "kv")},
            "hardware": {k: (d.get("hardware") or {}).get(k) for k in
                         ("gpu_util", "gpu_mem_used", "gpu_temp", "gpu_power", "cpu",
                          "ram_used", "ram_total", "tok_s")},
            "totals": d.get("totals"),
        }
        f.write(json.dumps(rec) + "\n")
        f.flush()
    except Exception as e:
        f.write(json.dumps({"t": round(time.time() - t0, 1), "error": str(e)}) + "\n")
        f.flush()
    time.sleep(interval)
f.close()
