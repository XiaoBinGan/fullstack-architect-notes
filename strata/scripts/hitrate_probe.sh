#!/bin/bash
set -u
R=/workspace/Strata
PY=$R/data/terminal/current/python/bin/python3
K=$(cat $R/logs/api-key.txt)
echo "=== generate some load so per-request telemetry has hit_rate ==="
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -H "Authorization: Bearer $K" -H 'Content-Type: application/json' \
    -d '{"model":"strata","messages":[{"role":"user","content":"Explain how a B-tree index works in 120 words."}],"max_tokens":140,"reasoning_effort":"none"}' \
    http://127.0.0.1:8899/v1/chat/completions
done
echo "done"
echo
echo "=== per-request telemetry (hit_rate / pcie_share / decode) ==="
curl -s -H "Authorization: Bearer $K" http://127.0.0.1:8899/metrics | $PY -c '
import json,sys
d=json.load(sys.stdin)
print("engine:", json.dumps({k:d["engine"].get(k) for k in ("expert_slots","expert_cache_mib","context","kv")}))
rs=d.get("requests") or []
print("requests in telemetry:", len(rs))
hr=[]
for r in rs[:12]:
    if not isinstance(r, dict): continue
    hv=r.get("hit_rate")
    if hv is not None: hr.append(hv)
    print("  prompt=%-6s reused=%-6s out=%-4s decode=%-7s hit_rate=%-7s pcie_share=%s" % (
        r.get("prompt_tokens"), r.get("reused"), r.get("output_tokens"),
        r.get("decode_tok_s"), hv, r.get("pcie_share")))
if hr:
    hr=sorted(hr)
    print("hit_rate: n=%d min=%.3f p50=%.3f mean=%.3f max=%.3f" % (
        len(hr), hr[0], hr[len(hr)//2], sum(hr)/len(hr), hr[-1]))
'
echo
echo "=== Prometheus names that expose cache/pcie/throughput ==="
curl -s -H "Authorization: Bearer $K" -H "Accept: text/plain" http://127.0.0.1:8899/metrics \
  | grep -E "^(strata:|vllm:)" | grep -iE "hit|pcie|tok_s|expert|cache|spec" | head -20
echo
echo "=== /metrics prompts/cache counters ==="
curl -s -H "Authorization: Bearer $K" http://127.0.0.1:8899/metrics | $PY -c '
import json,sys
d=json.load(sys.stdin)
cc=d.get("conversation_cache") or {}
t=d.get("totals") or {}
print("totals:", json.dumps(t))
if t.get("prompt_tokens"):
    print("prompt tokens reused: %d / %d = %.1f%%" % (t.get("reused",0), t.get("prompt_tokens"),
          100.0*t.get("reused",0)/max(1,t.get("prompt_tokens"))))
'