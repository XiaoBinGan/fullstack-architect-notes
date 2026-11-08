#!/usr/bin/env python3
"""Resource sampler for the Strata run: GPU + CPU + RAM, one CSV row per GPU per interval.

Runs on the HOST (not in the container) so nvidia-smi and /proc are the host's.
Usage: sampler.py OUTFILE [DURATION_S] [INTERVAL_S]
A file "<OUTFILE>.stop" makes it exit early.
"""
import csv
import os
import subprocess
import sys
import time

out = sys.argv[1] if len(sys.argv) > 1 else "/workspace/Strata/results/resources.csv"
duration = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0
interval = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
stopfile = out + ".stop"

FIELDS = [
    "index", "name", "utilization.gpu", "utilization.memory",
    "memory.used", "memory.total", "temperature.gpu", "power.draw", "power.limit",
    "clocks.sm", "clocks.mem", "pcie.link.gen.current", "pcie.link.width.current",
]
GPU_QUERY = ",".join(FIELDS)


def gpu_rows():
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=" + GPU_QUERY, "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10)
        rows = []
        for ln in r.stdout.strip().splitlines():
            if ln.strip():
                rows.append([c.strip() for c in ln.split(",")])
        return rows
    except Exception:
        return []


def meminfo():
    d = {}
    try:
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            d[k.strip()] = int(v.strip().split()[0])
    except Exception:
        pass
    return d


def loadavg():
    try:
        a = open("/proc/loadavg").read().split()
        return float(a[0]), float(a[1]), float(a[2])
    except Exception:
        return 0.0, 0.0, 0.0


def main():
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    header = ["ts", "elapsed", "gpu_index", "gpu_name", "gpu_util_pct", "gpu_mem_util_pct",
              "vram_used_mib", "vram_total_mib", "gpu_temp_c", "gpu_power_w", "gpu_power_limit_w",
              "sm_clock_mhz", "mem_clock_mhz", "pcie_gen", "pcie_width",
              "cpu_load1", "cpu_load5", "cpu_load15", "ram_total_kb", "ram_avail_kb", "ram_used_kb"]
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        f.flush()
        t0 = time.time()
        while time.time() - t0 < duration:
            if os.path.exists(stopfile):
                break
            el = round(time.time() - t0, 1)
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            m = meminfo()
            total = m.get("MemTotal", 0)
            avail = m.get("MemAvailable", 0)
            used = total - avail
            l1, l5, l15 = loadavg()
            for row in gpu_rows():
                w.writerow([ts, el] + row[:13] + [l1, l5, l15, total, avail, used])
            f.flush()
            time.sleep(interval)
    if os.path.exists(stopfile):
        os.remove(stopfile)


if __name__ == "__main__":
    main()
