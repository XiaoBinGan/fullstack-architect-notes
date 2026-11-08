#!/usr/bin/env python3
"""Full load test for the Strata server.

Stages
  sweep      : concurrency 1/2/4/8/16, fixed output, per-request latency + throughput
  sustained  : long sustained run at a fixed concurrency (default 4), stability + drift
  longctx    : long prompts (4K / 16K / 28K) under concurrency
  vision     : picture requests under concurrency
  overload   : burst far above the admission limit, to observe queuing / refusals

Every request records: client TTFT, total, decode tok/s, the engine's own timings,
HTTP status and error. Results go to <outdir>/loadtest-*.json.

Usage:
  loadtest.py <outdir> [--server URL] [--stages sweep,sustained,longctx,vision,overload]
              [--minutes N] [--out-tokens N]
"""
import argparse
import base64
import json
import os
import statistics
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import zlib

BASE = "http://127.0.0.1:8899"
KEY = ""
OUTDIR = "."

PROMPTS = [
    "Explain how a database index works, in about 150 words.",
    "Write a Python function that merges two sorted lists and explain its complexity.",
    "What are the trade-offs between replication and sharding in distributed databases?",
    "Summarize the CAP theorem and give one concrete system for each pair of guarantees.",
    "Describe how a transformer's attention mechanism works, step by step.",
    "Write a short technical note about why SSD wear levelling matters for databases.",
    "Explain what a Bloom filter is and when you would use one.",
    "Compare synchronous and asynchronous I/O in a server, with examples.",
    "What is the difference between a mutex and a semaphore? Give examples.",
    "Explain how TCP congestion control works at a high level.",
]


# --------------------------------------------------------------------------- HTTP
def stream_chat(content, max_tokens, timeout=1800):
    """One streaming request. Returns a record dict (never raises for HTTP errors)."""
    payload = {"model": "strata", "messages": [{"role": "user", "content": content}],
               "max_tokens": max_tokens, "reasoning_effort": "none", "stream": True}
    req = urllib.request.Request(BASE + "/v1/chat/completions",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json",
                                          "Authorization": "Bearer " + KEY}, method="POST")
    t0 = time.monotonic()
    first = None
    usage = None
    finish = None
    n_chunks = 0
    status = 200
    err = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            buf = b""
            for ch in r:
                buf += ch
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if not line.startswith(b"data:"):
                        continue
                    p = line[5:].strip()
                    if p == b"[DONE]":
                        continue
                    try:
                        j = json.loads(p)
                    except Exception:
                        continue
                    n_chunks += 1
                    if j.get("usage"):
                        usage = j["usage"]
                    for c in j.get("choices", []):
                        d = c.get("delta") or {}
                        if (d.get("content") or d.get("reasoning_content")) and first is None:
                            first = time.monotonic() - t0
                        if c.get("finish_reason"):
                            finish = c["finish_reason"]
    except urllib.error.HTTPError as e:
        status = e.code
        try:
            err = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            err = "http %d" % e.code
    except Exception as e:
        status = 0
        err = "%s: %s" % (type(e).__name__, e)
    total = time.monotonic() - t0
    ct = (usage or {}).get("completion_tokens")
    pt = (usage or {}).get("prompt_tokens")
    decode = ((ct - 1) / (total - first)) if (ct and first is not None and total > first) else None
    return {"status": status, "error": err, "ttft_s": first, "total_s": total,
            "completion_tokens": ct, "prompt_tokens": pt, "decode_tok_s": decode,
            "finish_reason": finish, "chunks": n_chunks}


def records(n_tokens, seed=1):
    unit = "record{:06d}: alpha beta gamma delta epsilon zeta eta theta.\n"
    target = n_tokens * 4
    out, size, i = [], 0, 0
    while size < target:
        s = unit.format(i + seed * 1000003)
        out.append(s)
        size += len(s)
        i += 1
    return "".join(out) + "\n\nSummarize the structure of these records."


def make_png(seed, w=800, h=600):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw.extend(((x * 255 // w + seed * 37) % 256,
                        (y * 255 // h + seed * 91) % 256,
                        (seed * 53 + (x + y) // 8) % 256))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6))
            + chunk(b"IEND", b""))


# ------------------------------------------------------------------- statistics
def pct(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def summarize(records_list, wall_s, clients):
    ok = [r for r in records_list if r["status"] == 200 and r["completion_tokens"]]
    bad = [r for r in records_list if not (r["status"] == 200 and r["completion_tokens"])]
    ttfts = [r["ttft_s"] for r in ok if r["ttft_s"] is not None]
    decs = [r["decode_tok_s"] for r in ok if r["decode_tok_s"]]
    tots = [r["total_s"] for r in ok]
    comps = [r["completion_tokens"] for r in ok]
    total_tokens = sum(comps)
    return {
        "clients": clients,
        "requests": len(records_list),
        "ok": len(ok),
        "failed": len(bad),
        "success_rate_pct": round(100.0 * len(ok) / len(records_list), 2) if records_list else None,
        "wall_s": round(wall_s, 2),
        "rps": round(len(records_list) / wall_s, 2) if wall_s else None,
        "aggregate_tok_s": round(total_tokens / wall_s, 2) if wall_s else None,
        "total_completion_tokens": total_tokens,
        "ttft_s": {"mean": round(statistics.mean(ttfts), 3) if ttfts else None,
                   "p50": round(pct(ttfts, 50), 3) if ttfts else None,
                   "p90": round(pct(ttfts, 90), 3) if ttfts else None,
                   "p95": round(pct(ttfts, 95), 3) if ttfts else None,
                   "p99": round(pct(ttfts, 99), 3) if ttfts else None,
                   "min": round(min(ttfts), 3) if ttfts else None,
                   "max": round(max(ttfts), 3) if ttfts else None},
        "decode_tok_s": {"mean": round(statistics.mean(decs), 2) if decs else None,
                         "p50": round(pct(decs, 50), 2) if decs else None,
                         "p95": round(pct(decs, 95), 2) if decs else None,
                         "min": round(min(decs), 2) if decs else None,
                         "max": round(max(decs), 2) if decs else None},
        "total_s": {"mean": round(statistics.mean(tots), 2) if tots else None,
                    "p50": round(pct(tots, 50), 2) if tots else None,
                    "p95": round(pct(tots, 95), 2) if tots else None,
                    "max": round(max(tots), 2) if tots else None},
        "completion_tokens": {"mean": round(statistics.mean(comps), 1) if comps else None,
                              "min": min(comps) if comps else None,
                              "max": max(comps) if comps else None},
        "errors": [{"status": r["status"], "error": r["error"]} for r in bad][:10],
    }


# ---------------------------------------------------------------------- stages
def run_round(clients, content_fn, out_tokens, timeout=1800):
    recs = []
    lock = threading.Lock()
    t0 = time.monotonic()

    def worker(i):
        try:
            r = stream_chat(content_fn(i), out_tokens, timeout=timeout)
        except Exception as e:
            r = {"status": 0, "error": "%s: %s" % (type(e).__name__, e),
                 "ttft_s": None, "total_s": 0, "completion_tokens": None,
                 "prompt_tokens": None, "decode_tok_s": None,
                 "finish_reason": None, "chunks": 0}
        with lock:
            recs.append(r)

    ths = [threading.Thread(target=worker, args=(i,)) for i in range(clients)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    wall = time.monotonic() - t0
    return recs, wall


def stage_sweep(args, results):
    print("\n" + "=" * 70)
    print("STAGE: concurrency sweep (out=%d tokens, rounds=%d)" % (args.out_tokens, args.rounds))
    print("=" * 70, flush=True)
    out = []
    for c in args.sweep_clients:
        allrecs = []
        walls = []
        for rep in range(args.rounds):
            recs, wall = run_round(c, lambda i: PROMPTS[(i + rep) % len(PROMPTS)],
                                   args.out_tokens)
            allrecs.extend(recs)
            walls.append(wall)
            s = summarize(recs, wall, c)
            print("  c=%-2d rep%d: rps=%.2f agg=%.1f tok/s ttft p50=%.3fs p95=%.3fs decode p50=%.1f"
                  % (c, rep, s["rps"] or 0, s["aggregate_tok_s"] or 0,
                     (s["ttft_s"]["p50"] or 0), (s["ttft_s"]["p95"] or 0),
                     (s["decode_tok_s"]["p50"] or 0)), flush=True)
        s = summarize(allrecs, sum(walls), c)
        s["rounds"] = args.rounds
        out.append(s)
        print("  => c=%-2d TOTAL: rps=%.2f agg=%.1f tok/s  ttft p50/p95/p99=%.2f/%.2f/%.2f s  "
              "decode p50=%.1f  ok=%d/%d"
              % (c, s["rps"], s["aggregate_tok_s"], s["ttft_s"]["p50"] or 0,
                 s["ttft_s"]["p95"] or 0, s["ttft_s"]["p99"] or 0,
                 s["decode_tok_s"]["p50"] or 0, s["ok"], s["requests"]), flush=True)
    results["sweep"] = out
    return out


def stage_sustained(args, results):
    print("\n" + "=" * 70)
    print("STAGE: sustained load, %d min at concurrency %d" % (args.minutes, args.sustained_clients))
    print("=" * 70, flush=True)
    stop_at = time.monotonic() + args.minutes * 60
    recs = []
    lock = threading.Lock()
    c = args.sustained_clients
    counter = {"n": 0}

    def worker(wid):
        i = 0
        while time.monotonic() < stop_at:
            r = stream_chat(PROMPTS[(wid + i) % len(PROMPTS)], args.out_tokens)
            r["worker"] = wid
            r["t"] = round(time.monotonic(), 3)
            with lock:
                recs.append(r)
                counter["n"] += 1
            i += 1

    t0 = time.monotonic()
    ths = [threading.Thread(target=worker, args=(i,)) for i in range(c)]
    for t in ths:
        t.start()
    last = 0
    while any(t.is_alive() for t in ths):
        time.sleep(15)
        el = time.monotonic() - t0
        if el - last >= 120:
            last = el
            with lock:
                done = len(recs)
                recent = [x for x in recs if x.get("ttft_s")][-40:]
            print("  [%4.0fs] requests=%d  recent ttft p50=%.3fs decode p50=%.1f"
                  % (el, done,
                     pct([x["ttft_s"] for x in recent], 50) or 0,
                     pct([x["decode_tok_s"] for x in recent if x["decode_tok_s"]], 50) or 0), flush=True)
    wall = time.monotonic() - t0
    s = summarize(recs, wall, c)
    s["duration_min"] = args.minutes
    results["sustained"] = s
    # drift: first half vs second half
    ok = [r for r in recs if r["status"] == 200 and r["ttft_s"]]
    if len(ok) >= 20:
        half = len(ok) // 2
        a, b = ok[:half], ok[half:]
        s["drift"] = {
            "ttft_p50_first_half": round(pct([x["ttft_s"] for x in a], 50), 3),
            "ttft_p50_second_half": round(pct([x["ttft_s"] for x in b], 50), 3),
            "decode_p50_first_half": round(pct([x["decode_tok_s"] for x in a if x["decode_tok_s"]], 50), 2),
            "decode_p50_second_half": round(pct([x["decode_tok_s"] for x in b if x["decode_tok_s"]], 50), 2),
        }
        print("  drift: ttft p50 %.3f -> %.3f s, decode p50 %.1f -> %.1f tok/s"
              % (s["drift"]["ttft_p50_first_half"], s["drift"]["ttft_p50_second_half"],
                 s["drift"]["decode_p50_first_half"] or 0, s["drift"]["decode_p50_second_half"] or 0), flush=True)
    print("  => %d requests, %d ok, %.2f rps, agg %.1f tok/s, ttft p50/p95/p99 = %.2f/%.2f/%.2f s"
          % (s["requests"], s["ok"], s["rps"], s["aggregate_tok_s"],
             s["ttft_s"]["p50"], s["ttft_s"]["p95"], s["ttft_s"]["p99"]), flush=True)
    return s


def stage_longctx(args, results):
    print("\n" + "=" * 70)
    print("STAGE: long context under concurrency")
    print("=" * 70, flush=True)
    out = {}
    for ntok, clients in ((4000, 1), (4000, 2), (16000, 1), (16000, 2), (24000, 1)):
        allrecs = []
        walls = []
        for rep in range(2):
            recs, wall = run_round(clients, lambda i, n=ntok, r=rep: records(n, seed=n + i + r * 7),
                                   128, timeout=1800)
            allrecs.extend(recs)
            walls.append(wall)
        s = summarize(allrecs, sum(walls), clients)
        pts = [r["prompt_tokens"] for r in allrecs if r.get("prompt_tokens")]
        s["prompt_tokens_median"] = pct(pts, 50) if pts else None
        s["prefill_tok_s_median"] = round(pct(
            [r["prompt_tokens"] / r["ttft_s"] for r in allrecs
             if r.get("prompt_tokens") and r.get("ttft_s")], 50) or 0, 0) if pts else None
        out["ctx%d_c%d" % (ntok, clients)] = s
        print("  ctx=%-5d c=%d: prompt~%s tok  ttft p50=%s s  prefill~%s tok/s  decode p50=%s  ok=%d/%d"
              % (ntok, clients, s["prompt_tokens_median"],
                 s["ttft_s"]["p50"], s["prefill_tok_s_median"],
                 s["decode_tok_s"]["p50"], s["ok"], s["requests"]), flush=True)
    results["longctx"] = out
    return out


def stage_vision(args, results):
    print("\n" + "=" * 70)
    print("STAGE: picture input under concurrency (CPU reader)")
    print("=" * 70, flush=True)
    out = {}
    Q = "Describe this picture in one short sentence."
    for clients in (1, 2):
        recs = []
        walls = []
        for rep in range(2):
            pngs = [base64.b64encode(make_png(seed=rep * 10 + i + clients * 100)).decode()
                    for i in range(clients)]
            r, wall = run_round(
                clients,
                lambda i, p=pngs: [{"type": "text", "text": Q},
                                   {"type": "image_url",
                                    "image_url": {"url": "data:image/png;base64," + p[i % len(p)]}}],
                64)
            recs.extend(r)
            walls.append(wall)
        s = summarize(recs, sum(walls), clients)
        out["c%d" % clients] = s
        print("  c=%d: ttft p50=%s s p95=%s s  decode p50=%s  ok=%d/%d"
              % (clients, s["ttft_s"]["p50"], s["ttft_s"]["p95"],
                 s["decode_tok_s"]["p50"], s["ok"], s["requests"]), flush=True)
    results["vision"] = out
    return out


def stage_overload(args, results):
    print("\n" + "=" * 70)
    print("STAGE: overload burst (32 simultaneous clients on a 1-slot server)")
    print("=" * 70, flush=True)
    recs, wall = run_round(32, lambda i: PROMPTS[i % len(PROMPTS)], 64, timeout=600)
    s = summarize(recs, wall, 32)
    statuses = {}
    for r in recs:
        statuses[str(r["status"])] = statuses.get(str(r["status"]), 0) + 1
    s["status_counts"] = statuses
    results["overload"] = s
    print("  %d requests in %.1fs: %s" % (s["requests"], wall, statuses), flush=True)
    print("  ttft p50/p95/p99/max = %s/%s/%s/%s s  ok=%d"
          % (s["ttft_s"]["p50"], s["ttft_s"]["p95"], s["ttft_s"]["p99"],
             s["ttft_s"]["max"], s["ok"]), flush=True)
    if s["errors"]:
        print("  errors:", json.dumps(s["errors"][:3]), flush=True)
    return s


# ------------------------------------------------------------------------ main
def main():
    global BASE, KEY, OUTDIR
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--server", default="http://127.0.0.1:8899")
    ap.add_argument("--keyfile", default="/workspace/Strata/logs/api-key.txt")
    ap.add_argument("--stages", default="sweep,sustained,longctx,vision,overload")
    ap.add_argument("--sweep-clients", default="1,2,4,8,16")
    ap.add_argument("--sustained-clients", type=int, default=4)
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--out-tokens", type=int, default=192)
    ap.add_argument("--rounds", type=int, default=2)
    a = ap.parse_args()

    BASE = a.server
    OUTDIR = a.outdir
    os.makedirs(OUTDIR, exist_ok=True)
    try:
        KEY = open(a.keyfile).read().strip()
    except OSError:
        KEY = ""

    a.sweep_clients = [int(x) for x in a.sweep_clients.split(",") if x.strip()]
    stages = [s.strip() for s in a.stages.split(",") if s.strip()]
    results = {"server": a.server, "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
               "config": {"out_tokens": a.out_tokens, "rounds": a.rounds,
                          "sweep_clients": a.sweep_clients,
                          "sustained_clients": a.sustained_clients,
                          "sustained_minutes": a.minutes}}

    health = None
    try:
        with urllib.request.urlopen(urllib.request.Request(
                BASE + "/health", headers={"Authorization": "Bearer " + KEY}), timeout=15) as r:
            health = json.loads(r.read())
    except Exception as e:
        print("health failed:", e)
    results["health"] = health
    print("health:", json.dumps(health), flush=True)

    t_all = time.monotonic()
    if "sweep" in stages:
        stage_sweep(a, results)
    if "sustained" in stages:
        stage_sustained(a, results)
    if "longctx" in stages:
        stage_longctx(a, results)
    if "vision" in stages:
        stage_vision(a, results)
    if "overload" in stages:
        stage_overload(a, results)

    results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    results["total_wall_s"] = round(time.monotonic() - t_all, 1)
    path = os.path.join(OUTDIR, "loadtest-%s.json" % time.strftime("%Y%m%d-%H%M%S"))
    json.dump(results, open(path, "w"), indent=1)
    print("\nDONE -> " + path, flush=True)


if __name__ == "__main__":
    main()
