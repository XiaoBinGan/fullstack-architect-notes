#!/usr/bin/env python3
"""Extract (expert-cache hit rate -> decode tok/s) pairs from the engine log, per round.

The engine writes one line per request:
  strata serve: prompt N tokens = ... , M generated in T ms (D tok/s), drafts accepted ...
  strata serve: decode expert cache hit rate: H% (hits/lookups); K more read by the GPU over PCIe (P% of all routed)
Straight-line pairing of those two lines gives the hit-rate/throughput relation.
"""
import re

LOG = "/workspace/Strata/strata-data/state/strata/launch/docker.engine.log"
date_rx = re.compile(r"2026-10-(2[0-9])")
gen_rx = re.compile(r"prompt (\d+) tokens = .*?, (\d+) generated in (\d+) ms \(([\d.]+) tok/s\)")
hit_rx = re.compile(r"decode expert cache hit rate: ([\d.]+)% \((\d+) hits / (\d+) lookups\); "
                    r"(\d+) more read by the GPU over PCIe or from another GPU \(([\d.]+)% of all (\d+) routed\)")

pairs = []
cur_gen = None
cur_date = None
for line in open(LOG, errors="replace"):
    m = date_rx.search(line)
    if m:
        cur_date = "10-" + m.group(1)
    g = gen_rx.search(line)
    if g:
        cur_gen = {"date": cur_date, "prompt": int(g.group(1)), "gen": int(g.group(2)),
                   "ms": int(g.group(3)), "tok_s": float(g.group(4))}
        continue
    h = hit_rx.search(line)
    if h and cur_gen:
        pairs.append({**cur_gen,
                      "hit": float(h.group(1)),
                      "hits": int(h.group(2)),
                      "lookups": int(h.group(3)),
                      "pcie_experts": int(h.group(4)),
                      "pcie_pct": float(h.group(5)),
                      "routed": int(h.group(6))})
        cur_gen = None

print("pairs:", len(pairs))
rounds = {}
for p in pairs:
    rounds.setdefault(p["date"], []).append(p)

for d in sorted(rounds):
    ps = rounds[d]
    print("\n=== log date %s: %d requests ===" % (d, len(ps)))
    print("  hit%%   decode tok/s   pcie%%   prompt   generated")
    for p in sorted(ps, key=lambda x: x["hit"]):
        print("  %5.1f   %8.1f     %5.2f   %6d   %6d" % (
            p["hit"], p["tok_s"], p["pcie_pct"], p["prompt"], p["gen"]))

# correlation over all
import statistics
if len(pairs) >= 4:
    hs = [p["hit"] for p in pairs]
    ts = [p["tok_s"] for p in pairs]
    n = len(pairs)
    mh, mt = sum(hs) / n, sum(ts) / n
    cov = sum((h - mh) * (t - mt) for h, t in zip(hs, ts)) / n
    sh = (sum((h - mh) ** 2 for h in hs) / n) ** 0.5
    st = (sum((t - mt) ** 2 for t in ts) / n) ** 0.5
    print("\nALL: n=%d  hit mean=%.1f%%  decode mean=%.1f tok/s  pearson r=%.3f" % (
        n, mh, mt, cov / (sh * st) if sh and st else 0))

import json
json.dump(pairs, open("/workspace/Strata/results-fullvram/hitrate-vs-decode.json", "w"), indent=1)
print("\nwrote /workspace/Strata/results-fullvram/hitrate-vs-decode.json")
