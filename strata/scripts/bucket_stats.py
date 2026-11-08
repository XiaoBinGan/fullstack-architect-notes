#!/usr/bin/env python3
"""Bucket the (hit-rate, pcie%, decode) pairs by round, to get article-ready numbers."""
import json
import statistics

pairs = json.load(open("/workspace/Strata/results-fullvram/hitrate-vs-decode.json"))
print("total pairs:", len(pairs))


def buckets(ps, key, edges):
    out = []
    for lo, hi in zip(edges, edges[1:]):
        sel = [p for p in ps if lo <= p[key] < hi]
        if not sel:
            continue
        ts = sorted(p["tok_s"] for p in sel)
        out.append({"range": "%g-%g" % (lo, hi), "n": len(sel),
                    "decode_p50": round(ts[len(ts) // 2], 1),
                    "decode_mean": round(sum(ts) / len(ts), 1),
                    "decode_min": round(ts[0], 1), "decode_max": round(ts[-1], 1)})
    return out


def only_192(ps):
    """Requests that generated ~192-256 tokens: comparable decode measurements."""
    return [p for p in ps if 150 <= p["gen"] <= 260]


print("\n================ ALL requests, decode tok/s by expert-cache hit rate ================")
for b in buckets(pairs, "hit", [30, 50, 60, 70, 80, 90, 95, 99, 101]):
    print("  hit %-7s n=%-5d decode p50=%-7s mean=%-7s range=%s..%s" % (
        b["range"] + "%", b["n"], b["decode_p50"], b["decode_mean"],
        b["decode_min"], b["decode_max"]))

print("\n================ decode tok/s by PCIe spill share ================")
for b in buckets(pairs, "pcie_pct", [0, 0.5, 1, 2, 3, 5, 10, 20, 30]):
    print("  pcie %-7s n=%-5d decode p50=%-7s mean=%-7s range=%s..%s" % (
        b["range"] + "%", b["n"], b["decode_p50"], b["decode_mean"],
        b["decode_min"], b["decode_max"]))

print("\n================ by round (log date) ================")
by = {}
for p in pairs:
    by.setdefault(p["date"], []).append(p)
for d in sorted(by):
    ps = only_192(by[d]) or by[d]
    hs = sorted(p["hit"] for p in ps)
    ts = sorted(p["tok_s"] for p in ps)
    pcie = sorted(p["pcie_pct"] for p in ps)
    print("  %s  n=%-5d hit p50=%.1f%%  decode p50=%.1f tok/s  pcie p50=%.2f%%  decode range %.0f..%.0f"
          % (d, len(ps), hs[len(hs) // 2], ts[len(ts) // 2], pcie[len(pcie) // 2], ts[0], ts[-1]))

print("\n================ energy / efficiency derived ================")
# round1 / round2 host sampler numbers (from rsum)
data = [
    ("round1 shared", 13759, 7625, 5784, 66.0, 140.55, 229.66),
    ("round2 exclusive", 31879, 25747, 19530, 99.6, 256.2, 336.66),
]
print("  %-18s %-10s %-11s %-8s %-8s %-11s %-10s %-12s" % (
    "round", "engine MiB", "cache MiB", "slots", "hit %", "decode tok/s", "power W", "tok/s per W"))
for name, eng, cache, slots, hit, dec, pwr in data:
    print("  %-18s %-10d %-11d %-8d %-8.1f %-11.1f %-10.1f %-12.3f" % (
        name, eng, cache, slots, hit, dec, pwr, dec / pwr))
print()
print("  fixed overhead (engine VRAM - expert cache): round1 = %d MiB, round2 = %d MiB"
      % (13759 - 7625, 31879 - 25747))
print("  marginal: +%d MiB cache -> +%.1f tok/s (%.2f tok/s per GiB)"
      % (25747 - 7625, 256.2 - 140.55, (256.2 - 140.55) / ((25747 - 7625) / 1024.0)))
