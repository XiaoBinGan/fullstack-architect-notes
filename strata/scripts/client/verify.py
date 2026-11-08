#!/usr/bin/env python3
"""Inference verification: API surface, streaming, tools, Anthropic API, context.

Usage: verify.py [--server URL] [--keyfile PATH]
Writes JSON to /workspace/Strata/results/verify.json and prints a summary.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

results = {}


def call(base, key, path, payload=None, method=None, timeout=600, raw=False, headers_extra=None):
    url = base + path
    h = {"Content-Type": "application/json"}
    if key:
        h["Authorization"] = "Bearer " + key
    if headers_extra:
        h.update(headers_extra)
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=h, method=method or ("POST" if body else "GET"))
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            return r.status, (data if raw else data.decode("utf-8", "replace")), time.monotonic() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), time.monotonic() - t0


def stream_collect(base, key, payload, timeout=600):
    """Return (status, events, text pieces, reasoning pieces)."""
    url = base + "/v1/chat/completions"
    h = {"Content-Type": "application/json", "Authorization": "Bearer " + key}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=h, method="POST")
    content, reasoning, events = [], [], 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        status = r.status
        buf = b""
        for chunk in r:
            buf += chunk
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
                events += 1
                for ch in j.get("choices", []):
                    d = ch.get("delta") or {}
                    if d.get("content"):
                        content.append(d["content"])
                    if d.get("reasoning_content"):
                        reasoning.append(d["reasoning_content"])
    return status, events, "".join(content), "".join(reasoning)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:8899")
    ap.add_argument("--keyfile", default="/workspace/Strata/logs/api-key.txt")
    ap.add_argument("--out", default="/workspace/Strata/results/verify.json")
    a = ap.parse_args()
    base = a.server
    key = ""
    try:
        key = open(a.keyfile).read().strip()
    except OSError:
        pass

    print("=" * 60)
    st, body, dt = call(base, key, "/health", timeout=30)
    print("GET /health ->", st, "%.2fs" % dt)
    print(body[:800])
    results["health"] = {"status": st, "body": body[:2000], "s": round(dt, 3)}

    st, body, dt = call(base, key, "/v1/models", timeout=30)
    print("\nGET /v1/models ->", st)
    print(body[:800])
    results["models"] = {"status": st, "body": body[:2000]}

    st, body, dt = call(base, key, "/props", timeout=30)
    print("\nGET /props ->", st)
    print(body[:600])
    results["props"] = {"status": st, "body": body[:3000]}

    # 1. non-streaming chat
    payload = {"model": "strata",
               "messages": [{"role": "user", "content": "What is 84 * 3 / 2? Answer with the number only."}],
               "max_tokens": 64, "reasoning_effort": "none", "temperature": 0.0}
    st, body, dt = call(base, key, "/v1/chat/completions", payload)
    print("\nPOST /v1/chat/completions (non-stream) ->", st, "%.2fs" % dt)
    ok = False
    try:
        j = json.loads(body)
        txt = j["choices"][0]["message"]["content"]
        print("  answer:", repr(txt[:200]))
        print("  usage:", j.get("usage"))
        ok = "126" in txt
    except Exception as e:
        print("  parse err", e, body[:300])
    results["chat_nonstream"] = {"status": st, "ok": ok, "s": round(dt, 3), "body": body[:3000]}
    print("  correct(126):", ok)

    # 2. streaming with thinking
    payload = {"model": "strata",
               "messages": [{"role": "user", "content": "What is 84 * 3 / 2? Answer with the number only."}],
               "max_tokens": 256, "reasoning_effort": "high", "stream": True}
    t0 = time.monotonic()
    st, events, content, reasoning = stream_collect(base, key, payload)
    dt = time.monotonic() - t0
    print("\nPOST streaming, thinking=high -> status", st, "events", events, "%.2fs" % dt)
    print("  reasoning chars:", len(reasoning), " content:", repr(content[:200]))
    results["chat_stream_thinking"] = {
        "status": st, "events": events, "s": round(dt, 3),
        "reasoning_chars": len(reasoning), "content": content[:1000],
        "content_ok_126": "126" in content,
    }

    # 3. tool calling
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city",
            "parameters": {"type": "object",
                           "properties": {"city": {"type": "string", "description": "City name"}},
                           "required": ["city"]},
        },
    }]
    payload = {"model": "strata",
               "messages": [{"role": "user", "content": "What is the weather in Paris right now? Use the tool."}],
               "tools": tools, "tool_choice": "auto", "max_tokens": 256,
               "reasoning_effort": "none", "stream": False}
    st, body, dt = call(base, key, "/v1/chat/completions", payload)
    print("\nPOST tool call ->", st, "%.2fs" % dt)
    tc_ok = False
    try:
        j = json.loads(body)
        msg = j["choices"][0]["message"]
        tcs = msg.get("tool_calls") or []
        print("  tool_calls:", json.dumps(tcs)[:400])
        print("  content:", repr((msg.get("content") or "")[:200]))
        tc_ok = any((t.get("function") or {}).get("name") == "get_weather" for t in tcs)
    except Exception as e:
        print("  parse err", e, body[:400])
    results["tool_call"] = {"status": st, "ok": tc_ok, "s": round(dt, 3), "body": body[:3000]}
    print("  tool call correct:", tc_ok)

    # 4. Anthropic messages API
    payload = {"model": "strata", "max_tokens": 64,
               "messages": [{"role": "user", "content": "Say hello in five words."}]}
    st, body, dt = call(base, key, "/v1/messages", payload)
    print("\nPOST /v1/messages (Anthropic) ->", st, "%.2fs" % dt)
    try:
        j = json.loads(body)
        print("  content:", json.dumps(j.get("content"))[:300])
        print("  usage:", j.get("usage"))
    except Exception:
        print("  body:", body[:300])
    results["anthropic_messages"] = {"status": st, "s": round(dt, 3), "body": body[:3000]}

    # 5. long prompt (4K) sanity
    filler = "".join("record%06d: alpha beta gamma delta epsilon zeta eta theta.\n" % i for i in range(180))
    payload = {"model": "strata",
               "messages": [{"role": "user", "content": filler + "\nHow many records are listed? Reply with a number."}],
               "max_tokens": 64, "reasoning_effort": "none"}
    st, body, dt = call(base, key, "/v1/chat/completions", payload, timeout=900)
    print("\nPOST 4K-token prompt ->", st, "%.2fs" % dt)
    try:
        j = json.loads(body)
        print("  answer:", repr(j["choices"][0]["message"]["content"][:160]))
        print("  usage:", j.get("usage"))
    except Exception:
        print("  body:", body[:300])
    results["long_prompt_4k"] = {"status": st, "s": round(dt, 3), "body": body[:2000]}

    # 6. metrics endpoint
    st, body, dt = call(base, key, "/metrics", timeout=30)
    print("\nGET /metrics ->", st, "%.2fs" % dt, "len", len(body))
    results["metrics"] = {"status": st, "len": len(body), "sample": body[:1500]}
    try:
        j = json.loads(body)
        print("  keys:", list(j.keys())[:20])
    except Exception:
        pass

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(results, f, indent=1, ensure_ascii=False)
    print("\nwrote", a.out)
    checks = {
        "health": results["health"]["status"] == 200,
        "chat_nonstream": results["chat_nonstream"]["ok"],
        "stream_thinking": results["chat_stream_thinking"]["content_ok_126"],
        "tool_call": results["tool_call"]["ok"],
        "anthropic": results["anthropic_messages"]["status"] == 200,
    }
    print("\nSUMMARY:", json.dumps(checks))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
