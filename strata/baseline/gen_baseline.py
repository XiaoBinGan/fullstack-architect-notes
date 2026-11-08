#!/usr/bin/env python3
"""把 baseline.json 渲染成 BASELINE.md 与 baseline.csv。

数据只有一份（baseline.json），文档和表格都是派生产物，
改数字只改 JSON，然后重跑一次：

    python3 gen_baseline.py

想校验仓库里的基线文档有没有被手改过：

    python3 gen_baseline.py --check
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "baseline.json"
OUT_MD = HERE / "BASELINE.md"
OUT_CSV = HERE / "baseline.csv"


def load() -> dict:
    return json.loads(SRC.read_text(encoding="utf-8"))


def esc(v: object) -> str:
    s = "" if v is None else str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def kv_table(rows: list[dict], head: tuple[str, str] = ("项", "值")) -> list[str]:
    out = [f"| {head[0]} | {head[1]} |", "| --- | --- |"]
    for r in rows:
        out.append(f"| {esc(r['item'])} | {esc(r['value'])} |")
    return out


def matrix(title: str, columns: list[dict], rows: list[dict]) -> list[str]:
    head = "| 指标 | " + " | ".join(esc(c["label"]) for c in columns) + " |"
    sep = "| --- | " + " | ".join("---" for _ in columns) + " |"
    out = [f"### {title}", "", head, sep]
    for r in rows:
        cells = [esc(r["values"].get(c["id"], "—")) for c in columns]
        out.append("| " + esc(r["item"]) + " | " + " | ".join(cells) + " |")
    notes = [(r["item"], r["note"]) for r in rows if r.get("note")]
    if notes:
        out += ["", "备注：", ""]
        for item, note in notes:
            out.append(f"- **{item}**：{note}")
    out.append("")
    return out


def grid(title: str, columns: list[str], rows: list[list[str]]) -> list[str]:
    out = [f"### {title}", "", "| " + " | ".join(esc(c) for c in columns) + " |",
           "| " + " | ".join("---" for _ in columns) + " |"]
    for r in rows:
        out.append("| " + " | ".join(esc(c) for c in r) + " |")
    out.append("")
    return out


def render(d: dict) -> str:
    out = [
        f"# {d['title']}",
        "",
        f"**{d['subtitle']}**　·　实测日期：{d['measured_at']}",
        "",
        "> 本文由 `gen_baseline.py` 从 `baseline.json` 渲染，数字只有一份来源，不手抄。",
        f"> 数字出处：{'、'.join(d['source']['articles'])}；{'；'.join(d['source']['reports'])}。",
        f"> {d['source']['warning']}",
        "",
        "## 零、测量口径（先看这个，否则下面的数字没法比）",
        "",
    ]
    out += kv_table(d["protocol"])
    out += ["", "## 一、硬件与环境", ""]
    out += kv_table(d["hardware"])

    cfgs = d["configs"]
    out += ["", "## 二、配置矩阵（同一台机器上的 7 种部署）", ""]
    out += matrix("配置对比", cfgs["columns"], cfgs["rows"])

    for sec in d["sections"]:
        out += ["", f"## {sec['title']}", ""]
        out += matrix(sec["title"].split("、", 1)[1] if "、" in sec["title"] else sec["title"], sec["columns"], sec["rows"])

    out += ["", "## 四、扫描类原始表", ""]
    for sw in d["sweeps"]:
        out += grid(sw["title"], sw["columns"], sw["rows"])

    const = d["constants"]
    out += ["", f"## {const['title']}", "", "```text", const["vram_formula"], "```", ""]
    out += kv_table(const["items"])
    rec = const["reconciliation"]
    out += ["", f"### {rec['title']}", ""]
    out += ["| " + " | ".join(rec["columns"]) + " |", "| " + " | ".join("---" for _ in rec["columns"]) + " |"]
    for r in rec["rows"]:
        out.append("| " + " | ".join(esc(c) for c in r) + " |")
    out.append("")

    mv = d["minimal_verification"]
    out += [f"## {mv['title']}", ""]
    for i, item in enumerate(mv["items"], 1):
        out.append(f"{i}. {item}")
    out += [
        "",
        "---",
        "",
        "## 复现方式",
        "",
        "```bash",
        "docker stop -t 30 ms_reranker7 ms_reranker8 ms_reranker9   # 释放 5090（可回滚）",
        "bash scripts/run_b3.sh                                    # B3 推荐配置",
        "python3 scripts/client/verify.py --out verify.json        # 冒烟",
        "bash scripts/run_loadtest.sh                              # 五类压测 ≈14 min",
        "python3 scripts/client/extract_numbers.py                 # 出表",
        "```",
        "",
        "> 脚本与校验和见 [`../scripts/MANIFEST.md`](../scripts/MANIFEST.md)。",
        "> 服务端 API key 与容器内网地址不在本仓库保留，复现时由 `scripts/03_run_container.sh` 现场生成。",
        "",
    ]
    return "\n".join(out)


def render_csv(d: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["section", "item", "column_id", "column_label", "value", "note"])

    for r in d["protocol"]:
        w.writerow(["protocol", r["item"], "", "", r["value"], ""])
    for r in d["hardware"]:
        w.writerow(["hardware", r["item"], "", "", r["value"], ""])

    cfgs = d["configs"]
    labels = {c["id"]: c["label"] for c in cfgs["columns"]}
    for r in cfgs["rows"]:
        for cid, val in r["values"].items():
            w.writerow(["configs", r["item"], cid, labels.get(cid, cid), val, ""])

    for sec in d["sections"]:
        labels = {c["id"]: c["label"] for c in sec["columns"]}
        for r in sec["rows"]:
            for cid, val in r["values"].items():
                w.writerow([sec["id"], r["item"], cid, labels.get(cid, cid), val, r.get("note", "")])

    for sw in d["sweeps"]:
        head = sw["columns"]
        for row in sw["rows"]:
            for col, val in zip(head, row):
                w.writerow([sw["id"], row[0], col, col, val, ""])

    for r in d["constants"]["items"]:
        w.writerow(["constants", r["item"], "", "", r["value"], r["note"]])
    w.writerow(["constants", "显存预算公式", "", "", d["constants"]["vram_formula"], ""])
    rec = d["constants"]["reconciliation"]
    for row in rec["rows"]:
        w.writerow(["constants.reconciliation", row[0], "", "", " / ".join(row[1:]), ""])
    for i, item in enumerate(d["minimal_verification"]["items"], 1):
        w.writerow(["minimal_verification", f"判断 {i}", "", "", item, ""])
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()

    d = load()
    md = render(d)
    csv_text = render_csv(d)

    if args.check:
        bad = []
        if not OUT_MD.exists() or OUT_MD.read_text(encoding="utf-8") != md:
            bad.append(OUT_MD.name)
        if not OUT_CSV.exists() or OUT_CSV.read_text(encoding="utf-8") != csv_text:
            bad.append(OUT_CSV.name)
        if bad:
            print("以下文件与 baseline.json 不一致，重跑 gen_baseline.py：" + "、".join(bad), file=sys.stderr)
            return 1
        print("OK：BASELINE.md / baseline.csv 与 baseline.json 一致")
        return 0

    OUT_MD.write_text(md, encoding="utf-8")
    OUT_CSV.write_text(csv_text, encoding="utf-8")
    rows = sum(len(s["rows"]) for s in d["sections"]) + sum(len(s["rows"]) for s in d["sweeps"])
    print(f"wrote {OUT_MD.name} / {OUT_CSV.name}（{len(d['sections'])} 个指标组，{rows} 行数据）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())