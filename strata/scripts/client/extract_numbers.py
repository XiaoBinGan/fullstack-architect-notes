#!/usr/bin/env python3
"""Print exact load-test numbers as markdown-ready values."""
import glob
import json

R = "/workspace/Strata/results/loadtest"
d = json.load(open(sorted(glob.glob(R + "/loadtest-*.json"))[-1]))
sup = json.load(open(R + "/longctx-supplement.json"))

print("## SWEEP")
print("| c | requests | ok | rps | agg tok/s | TTFT p50 | p95 | p99 | decode p50 | decode p95 |")
print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
for b in d["sweep"]:
    print("| %d | %d | %d | %.2f | %.1f | %.2f | %.2f | %.2f | %.1f | %.1f |" % (
        b["clients"], b["requests"], b["ok"], b["rps"], b["aggregate_tok_s"],
        b["ttft_s"]["p50"], b["ttft_s"]["p95"], b["ttft_s"]["p99"],
        b["decode_tok_s"]["p50"], b["decode_tok_s"]["p95"]))

print("\n## SUSTAINED")
s = d["sustained"]
print(json.dumps({k: s[k] for k in ("clients", "requests", "ok", "failed", "success_rate_pct",
                                    "wall_s", "rps", "aggregate_tok_s",
                                    "total_completion_tokens")}, indent=1))
print("ttft:", json.dumps(s["ttft_s"]))
print("decode:", json.dumps(s["decode_tok_s"]))
print("total:", json.dumps(s["total_s"]))
print("completion_tokens:", json.dumps(s["completion_tokens"]))
print("drift:", json.dumps(s.get("drift")))

print("\n## LONG CONTEXT")
for k, v in d["longctx"].items():
    print("%-12s prompt~%-6s ttft p50=%-7s prefill~%-6s decode p50=%-7s ok=%d/%d" % (
        k, v.get("prompt_tokens_median"), v["ttft_s"].get("p50"),
        v.get("prefill_tok_s_median"), v["decode_tok_s"].get("p50"),
        v["ok"], v["requests"]))
print("-- supplementary --")
for k, v in sup.items():
    print("%-12s prompt~%-6s ttft p50=%-7s prefill~%-6s decode p50=%-7s ok=%d/%d" % (
        k, v.get("prompt_tokens_median"), v["ttft_s"].get("p50"),
        v.get("prefill_tok_s_median"), v["decode_tok_s"].get("p50"),
        v["ok"], v["requests"]))

print("\n## VISION under load")
for k, v in d["vision"].items():
    print("%-4s ttft p50=%-6s p95=%-6s decode p50=%-7s ok=%d/%d" % (
        k, v["ttft_s"]["p50"], v["ttft_s"]["p95"], v["decode_tok_s"]["p50"],
        v["ok"], v["requests"]))

print("\n## OVERLOAD")
o = d["overload"]
print(json.dumps({k: o[k] for k in ("clients", "requests", "ok", "failed",
                                    "success_rate_pct", "wall_s", "rps",
                                    "aggregate_tok_s", "status_counts")}, indent=1))
print("ttft:", json.dumps(o["ttft_s"]))
print("total:", json.dumps(o["total_s"]))
