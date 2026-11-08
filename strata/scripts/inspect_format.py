#!/usr/bin/env python3
"""Inspect the exact model file format Strata is using: GGUF header + metadata + tensors,
the Strata 'pack', and the MTP draft layer."""
import json
import os
import struct
import sys

BASE = "/workspace/Strata/strata-data/Strata-data"
GGUF_TYPE = {0: "u8", 1: "i8", 2: "u16", 3: "i16", 4: "u32", 5: "i32", 6: "f32", 7: "bool",
             8: "str", 9: "array", 10: "u64", 11: "i64", 12: "f64"}


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

    def i64(self):
        return struct.unpack("<q", self.raw(8))[0]

    def f32(self):
        return struct.unpack("<f", self.raw(4))[0]

    def f64(self):
        return struct.unpack("<d", self.raw(8))[0]

    def s(self):
        n = self.u64()
        return self.raw(n).decode("utf-8", "replace")

    def val(self, t):
        if t == 0:
            return self.raw(1)[0]
        if t == 1:
            return struct.unpack("<b", self.raw(1))[0]
        if t == 2:
            return struct.unpack("<H", self.raw(2))[0]
        if t == 3:
            return struct.unpack("<h", self.raw(2))[0]
        if t == 4:
            return self.u32()
        if t == 5:
            return struct.unpack("<i", self.raw(4))[0]
        if t == 6:
            return self.f32()
        if t == 7:
            return bool(self.raw(1)[0])
        if t == 8:
            return self.s()
        if t == 10:
            return self.u64()
        if t == 11:
            return self.i64()
        if t == 12:
            return self.f64()
        raise ValueError("type %d" % t)


def gguf(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        r = R(f)
        magic = r.raw(4)
        version = r.u32()
        n_tensors = r.u64()
        n_kv = r.u64()
        print("  file        : %s" % path)
        print("  size        : %d bytes (%.2f GiB)" % (size, size / 1073741824))
        print("  magic       : %r  -> %s" % (magic, "GGUF" if magic == b"GGUF" else "??"))
        print("  version     : %d" % version)
        print("  tensors     : %d" % n_tensors)
        print("  metadata kv : %d" % n_kv)
        md = {}
        for _ in range(n_kv):
            key = r.s()
            t = r.u32()
            if t == 9:  # array
                et = r.u32()
                n = r.u64()
                if et == 8:            # array of strings: read a few only
                    vals = []
                    for i in range(n):
                        v = r.s()
                        if i < 6:
                            vals.append(v)
                    md[key] = {"array_of": "str", "len": n, "sample": vals}
                elif et in (0, 1, 2, 3, 4, 5, 10, 11):  # numeric arrays: skip bytes
                    width = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 10: 8, 11: 8}[et]
                    r.raw(width * n)
                    md[key] = {"array_of": GGUF_TYPE[et], "len": n}
                elif et == 6:
                    r.raw(4 * n)
                    md[key] = {"array_of": "f32", "len": n}
                elif et == 7:
                    r.raw(n)
                    md[key] = {"array_of": "bool", "len": n}
                else:
                    raise ValueError("array elem type %d" % et)
            else:
                md[key] = r.val(t)
        return md, n_tensors, size


def show(md, keys=None, prefix=("general", "qwen", "strata", "split", "tokenizer")):
    print("  --- key metadata ---")
    for k in sorted(md):
        if keys and not any(k.startswith(p) for p in prefix):
            continue
        v = md[k]
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else repr(v)
        if len(s) > 160:
            s = s[:157] + "..."
        print("   %-42s = %s" % (k, s))


print("=" * 78)
print("MODEL FILES")
print("=" * 78)
for root, dirs, files in os.walk(BASE):
    for fn in sorted(files):
        p = os.path.join(root, fn)
        print("  %12d  %s" % (os.path.getsize(p), p.replace(BASE + "/", "")))

mdir = os.path.join(BASE, "models")
shards = []
for root, dirs, files in os.walk(mdir):
    for fn in sorted(files):
        if fn.endswith(".gguf"):
            shards.append(os.path.join(root, fn))
shards.sort()

for sh in shards:
    print()
    print("-" * 78)
    md, nt, size = gguf(sh)
    show(md)
    print("  --- quantization / architecture keys ---")
    for k in sorted(md):
        if any(x in k for x in ("quant", "expert", "block", "type", "arch", "name", "file_type",
                                "rope", "context", "embedding", "head", "layer")):
            v = md[k]
            s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else repr(v)
            if len(s) > 140:
                s = s[:137] + "..."
            print("   %-42s = %s" % (k, s))

print()
print("=" * 78)
print("STRATA PACK  (prepared by setup: /data/Strata-data/packs/q2_0)")
print("=" * 78)
pack = os.path.join(BASE, "packs", "q2_0")
if os.path.isdir(pack):
    tot = 0
    for root, dirs, files in os.walk(pack):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            sz = os.path.getsize(p)
            tot += sz
            print("  %12d  %s" % (sz, p.replace(pack + "/", "")))
    print("  total: %.2f GiB" % (tot / 1073741824))
    idx = os.path.join(pack, "index.txt")
    if os.path.exists(idx):
        lines = open(idx, "r", errors="replace").read().splitlines()
        print("  index.txt: %d lines, first 5:" % len(lines))
        for ln in lines[:5]:
            print("    " + ln[:140])

print()
print("=" * 78)
print("MTP DRAFT LAYER  (/data/Strata-data/mtp)")
print("=" * 78)
mtp = os.path.join(BASE, "mtp")
if os.path.isdir(mtp):
    for root, dirs, files in os.walk(mtp):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            print("  %12d  %s" % (os.path.getsize(p), p.replace(BASE + "/", "")))
    g = os.path.join(mtp, "mtp-q2_0.gguf")
    if os.path.exists(g):
        print()
        md2, nt2, _ = gguf(g)
        show(md2, prefix=("general", "mtp", "strata"))
