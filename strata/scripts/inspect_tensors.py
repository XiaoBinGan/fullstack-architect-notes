#!/usr/bin/env python3
"""Tensor-level format breakdown of the GGUF shards: which ggml quant types, how many tensors each."""
import collections
import json
import os
import struct

BASE = "/workspace/Strata/strata-data/Strata-data/models/Q2_0"
SHARDS = [
    "Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00001-of-00002.gguf",
    "Qwen3.8-Flash-Next-GSQ-RCO-Q2_0-00002-of-00002.gguf",
]
# ggml_type -> (name, bits per weight or '')
GGML = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 8: "Q8_0", 9: "Q8_1",
    10: "Q2_K", 11: "Q3_K", 12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 15: "Q8_K",
    16: "IQ2_XXS", 17: "IQ2_XS", 18: "IQ3_XXS", 19: "IQ1_S", 20: "IQ4_NL", 21: "IQ3_S",
    22: "IQ2_S", 23: "IQ4_XS", 24: "I8", 25: "I16", 26: "I32", 27: "I64", 28: "F64",
    29: "IQ1_M", 30: "BF16", 31: "Q4_0_4_4", 32: "Q4_0_4_8", 33: "Q4_0_8_8",
    34: "TQ1_0", 35: "TQ2_0", 36: "IQ4_NL_4_4", 37: "IQ4_NL_4_8", 38: "IQ4_NL_8_8",
    39: "MXFP4", 40: "NVFP4", 41: "Q1_0", 42: "Q2_0",
}


class R:
    def __init__(self, f):
        self.f = f

    def raw(self, n):
        b = self.f.read(n)
        if len(b) != n:
            raise EOFError
        return b

    def u32(self):
        return struct.unpack("<I", self.raw(4))[0]

    def u64(self):
        return struct.unpack("<Q", self.raw(8))[0]

    def i32(self):
        return struct.unpack("<i", self.raw(4))[0]

    def i64(self):
        return struct.unpack("<q", self.raw(8))[0]

    def f32(self):
        return struct.unpack("<f", self.raw(4))[0]

    def s(self):
        n = self.u64()
        return self.raw(n).decode("utf-8", "replace")

    def val(self, t):
        if t == 0: return self.raw(1)[0]
        if t == 1: return struct.unpack("<b", self.raw(1))[0]
        if t == 2: return struct.unpack("<H", self.raw(2))[0]
        if t == 3: return struct.unpack("<h", self.raw(2))[0]
        if t == 4: return self.u32()
        if t == 5: return self.i32()
        if t == 6: return self.f32()
        if t == 7: return bool(self.raw(1)[0])
        if t == 8: return self.s()
        if t == 10: return self.u64()
        if t == 11: return self.i64()
        if t == 12: return struct.unpack("<d", self.raw(8))[0]
        raise ValueError(t)


def read(path):
    with open(path, "rb") as f:
        r = R(f)
        assert r.raw(4) == b"GGUF"
        ver = r.u32()
        nt = r.u64()
        nkv = r.u64()
        for _ in range(nkv):
            r.s()
            t = r.u32()
            if t == 9:
                et = r.u32()
                n = r.u64()
                width = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}.get(et)
                if et == 8:
                    for _ in range(n):
                        r.s()
                elif width:
                    r.raw(width * n)
                else:
                    raise ValueError("array elem %d" % et)
            else:
                r.val(t)
        tensors = []
        for _ in range(nt):
            name = r.s()
            nd = r.u32()
            dims = [r.u64() for _ in range(nd)]
            tt = r.u32()
            off = r.u64()
            ne = 1
            for d in dims:
                ne *= d
            tensors.append({"name": name, "dims": dims, "type": tt, "n": ne, "off": off})
        return ver, tensors


total = collections.Counter()
total_b = collections.Counter()
for sh in SHARDS:
    p = os.path.join(BASE, sh)
    print("=" * 80)
    print(sh, "(%.2f GiB)" % (os.path.getsize(p) / 1073741824))
    ver, ts = read(p)
    cnt = collections.Counter()
    bytes_by = collections.Counter()
    for t in ts:
        cnt[t["type"]] += 1
        # rough size: next tensor offset - this offset within the same type ordering is unreliable;
        # use element count with 0.5 byte/weight for the 2-bit types, 1 for Q8_0, 2 for F16, 4 for F32
        bytes_by[t["type"]] += t["n"]
    print("  tensors:", len(ts))
    print("  %-14s %-8s %-12s %s" % ("ggml type", "count", "elements", "example tensors"))
    for tt, c in cnt.most_common():
        ex = [t["name"] for t in ts if t["type"] == tt][:2]
        print("  %-14s %-8d %-12d %s" % (
            GGML.get(tt, "type%d" % tt), c, bytes_by[tt], ", ".join(ex)[:70]))
        total[GGML.get(tt, "type%d" % tt)] += c
        total_b[GGML.get(tt, "type%d" % tt)] += bytes_by[tt]
    # first 6 tensors detail
    print("  first tensors:")
    for t in ts[:6]:
        print("    %-52s dims=%-24s %s" % (t["name"][:52], t["dims"], GGML.get(t["type"], t["type"])))
    print()

print("=" * 80)
print("ALL SHARDS: tensors per quant type")
for k, v in total.most_common():
    print("  %-14s %d tensors" % (k, v))
print()
print("TOTAL elements per type:")
for k, v in total_b.most_common():
    print("  %-14s %d" % (k, v))
