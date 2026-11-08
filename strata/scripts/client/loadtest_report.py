#!/usr/bin/env python3
"""Summarise the load test JSON + samplers into report-ready numbers."""
import glob
import json
import statistics
import sys

R = "/workspace/Strata/results/loadtest"
paths = sorted(glob.glob(R + "/loadtest-*.json"))
if not paths:
    print("no loadtest json")
    sys.exit(1)
d = json.load(open(paths[-1]))
print("file:", paths[-1])
print("started:", d.get("started"), " finished:", d.get("finished"), " wall:", d.get("total_wall_s"), "s")
print("health:", json.dumps(d.get("health")))
print("config:", json.dumps(d.get("config")))

def show_block(name, blk, keys=("clients", "requests", "ok", "failed", "success_rate_pct",
                               "wall_s", "rps", "aggregate_tok_s", "total_completion_tokens")):
    print("\n---- %s ----" % name)
    if isinstance(blk, list):
        for b in blk:
            print("  " + " ".join("%s=%s" % (k, b.get(k)) for k in keys))
            for sub in ("ttft_s", "decode_tok_s", "total_s", "completion_tokens"):
                if b.get(sub):
                    print("     %-15s %s" % (sub, json.dumps(b[sub])))
    elif isinstance(blk, dict):
        for k, v in blk.items():
            if not isinstance(v, dict):
                print("  %s = %s" % (k, v))
                continue
            if "ctx24000" in k:
                print("  %s ERROR: %s" % (k, json.dumps(v.get("errors"))[:300]))
                continue
            print("  %s: " % k + " ".join("%s=%s" % (kk, v.get(kk)) for kk in keys if kk in v))
            for sub in ("ttft_s", "decode_tok_s", "prefill_tok_s_median", "prompt_tokens_median"):
                if v.get(sub):
                    print("     %-24s %s" % (sub, json.dumps(v[sub])))

show_block("SWEEP (aggregate)", d.get("sweep"))
show_block("SUSTAINED", d.get("sustained"))
if d.get("sustained", {}).get("drift"):
    print("     drift:", json.dumps(d["sustained"]["drift"]))
show_block("LONG CONTEXT", d.get("longctx"))
show_block("VISION", d.get("vision"))
show_block("OVERLOAD", d.get("overload"))
if d.get("overload"):
    print("     status_counts:", json.dumps(d["overload"].get("status_counts")))

# ---- host resources
print("\n==== HOST RESOURCES ====")
import csv
rows = list(csv.DictReader(open(R + "/host-resources.csv")))
print("samples:", len(rows))

def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def stat(rs, key):
    v = sorted(x for x in (num(r.get(key)) for r in rs) if x is not None)
    if not v:
        return None
    return {"min": round(v[0], 2), "mean": round(sum(v) / len(v), 2),
            "p50": round(v[len(v) // 2], 2), "p95": round(v[int(0.95 * (len(v) - 1))], 2),
            "max": round(v[-1], 2)}

for gpu in ("0", "1"):
    rs = [r for r in rows if r.get("gpu_index") == gpu]
    if not rs:
        continue
    print("\nGPU %s %s (n=%d)" % (gpu, rs[0].get("gpu_name"), len(rs)))
    for k in ("gpu_util_pct", "vram_used_mib", "gpu_temp_c", "gpu_power_w",
              "sm_clock_mhz", "mem_clock_mhz"):
        s = stat(rs, k)
        if s:
            print("  %-18s min=%-9s mean=%-9s p50=%-9s p95=%-9s max=%-9s" % (
                k, s["min"], s["mean"], s["p50"], s["p95"], s["max"]))
print("\nCPU/RAM")
for k in ("cpu_load1", "cpu_load5", "ram_avail_kb", "ram_used_kb"):
    s = stat(rows, k)
    if s:
        if k.startswith("ram_"):
            g = lambda x: round(x / 1048576.0, 2)
            print("  %-18s min=%-9s mean=%-9s p50=%-9s max=%-9s (GiB %s/%s/%s)" % (
                k, s["min"], s["mean"], s["p50"], s["max"], g(s["min"]), g(s["mean"]), g(s["max"])))
        else:
            print("  %-18s min=%-9s mean=%-9s p50=%-9s p95=%-9s max=%-9s" % (
                k, s["min"], s["mean"], s["p50"], s["p95"], s["max"]))

# ---- server metrics
print("\n==== SERVER METRICS (sampled during the run) ====")
recs = []
for line in open(R + "/server-metrics.jsonl"):
    line = line.strip()
    if not line:
        continue
    try:
        j = json.loads(line)
    except Exception:
        continue
    if "error" not in j:
        recs.append(j)
print("samples:", len(recs))
for key in ("gpu_util", "gpu_power", "gpu_temp", "cpu", "ram_used"):
    v = sorted(x["hardware"][key] for x in recs
               if x.get("hardware") and x["hardware"].get(key) is not None)
    if v:
        print("  %-12s min=%.2f mean=%.2f p95=%.2f max=%.2f" % (
            key, v[0], sum(v) / len(v), v[int(0.95 * (len(v) - 1))], v[-1]))
tot_first = recs[0].get("totals") or {}
tot_last = recs[-1].get("totals") or {}
print("  totals first:", json.dumps(tot_first))
print("  totals last :", json.dumps(tot_last))
if tot_first.get("drafts_offered") and tot_last.get("drafts_offered") != tot_first.get("drafts_offered"):
    off = tot_last["drafts_offered"] - tot_first["drafts_offered"]
    acc = tot_last["drafts_accepted"] - tot_first["drafts_accepted"]
    print("  MTP during load: offered=%d accepted=%d acceptance=%.1f%%" % (off, acc, 100.0 * acc / off if off else 0))
eng = recs[-1].get("engine") or {}
print("  engine last:", json.dumps(eng))
