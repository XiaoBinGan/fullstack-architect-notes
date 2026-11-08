#!/usr/bin/env python3
"""生成 strata 脚本清单（MANIFEST.md / manifest.json）。

用法：
    python3 gen_manifest.py                # 重新扫描本目录，覆盖写入清单
    python3 gen_manifest.py --check        # 只校验：现有清单与文件实际哈希不一致则退出码 1

清单里的行数 / 字节数 / sha256 全部来自真实文件，不手写，
所以任何人 clone 之后跑一遍就能验证附件有没有被改动过。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # strata/
OUT_MD = HERE / "MANIFEST.md"
OUT_JSON = HERE / "manifest.json"

# 人工撰写的“作用”字段：脚本名 -> (分组, 一句话作用, 关键参数/依赖)
META: dict[str, tuple[str, str, str]] = {
    "env.sh": (
        "部署",
        "共享环境变量：把 HOME / XDG / TMPDIR / pip / HF 缓存全部收敛到 /workspace/Strata 内部",
        "被 02_launch.sh 等 source；无参数",
    ),
    "02_launch.sh": (
        "部署",
        "下载引擎+模型并拉起服务（官方 CLI 路线）",
        "--context 64k --vision cpu --parallel 1 --port 8899 --tune skip",
    ),
    "03_run_container.sh": (
        "部署",
        "官方容器路线启动：随机 API key、seccomp=unconfined、只绑 GPU1",
        "镜像 ghcr.nju.edu.cn/niko1221/strata:0.2.2-cuda13；--gpus device=1",
    ),
    "rebind_port.sh": (
        "部署",
        "把端口从 127.0.0.1 重绑到 0.0.0.0，并顺带轮询 /health 判定就绪",
        "warm 重启实测 55 s；模型留在卷里不重下",
    ),
    "enable_vision.sh": (
        "部署",
        "开启视觉输入（CPU 读图器），首次多下约 0.9 GB 读图器文件",
        "VISION=cpu；带视觉编码器重启实测 254 s",
    ),
    "run_loadtest.sh": (
        "压测",
        "五类压测一键跑：先起两个采样器，再跑 sweep/sustained/longctx/vision/overload",
        "MINUTES=${MINUTES:-10}；采样器 2 s / 5 s 间隔",
    ),
    "hitrate_probe.sh": (
        "分析",
        "先打几发请求，再把 /metrics 里的 per-request 遥测（hit_rate / pcie_share / decode）打印出来",
        "依赖 /metrics 的 requests[] 字段",
    ),
    "inspect_format.py": (
        "分析",
        "读 GGUF 头与元数据（量化档位、tensor 数、上下文长度）",
        "输入：GGUF 路径；纯标准库",
    ),
    "inspect_tensors.py": (
        "分析",
        "按量化类型统计 tensor 数与参数量，验证“Q2_0 其实是混合精度”",
        "输入：GGUF 路径；输出分档表",
    ),
    "hitrate_vs_decode.py": (
        "分析",
        "从引擎日志里抽「缓存命中率 ↔ decode 速度」配对样本",
        "输入：engine.log；输出 (hit_rate, decode_tok_s) 序列",
    ),
    "bucket_stats.py": (
        "分析",
        "按命中率 / PCIe 溢出分桶统计 decode，坐实“1% 溢出掉 39%”",
        "输入：hitrate_vs_decode.py 的产物",
    ),
    "client/loadtest.py": (
        "压测",
        "压测主程序，五个 stage 全在这里",
        "--stages sweep,sustained,longctx,vision,overload --sweep-clients 1,2,4,8,16 "
        "--sustained-clients 4 --minutes 10 --out-tokens 192 --rounds 2",
    ),
    "client/sampler.py": (
        "压测",
        "宿主侧采样：GPU 利用率/显存/功耗/温度 + CPU + 内存，默认 2 s 一次",
        "用法：sampler.py OUT.csv SECONDS INTERVAL",
    ),
    "client/metrics_sampler.py": (
        "压测",
        "服务端 /metrics 采样，默认 5 s 一次，写 jsonl",
        "用法：metrics_sampler.py OUT.jsonl SECONDS INTERVAL",
    ),
    "client/loadtest_report.py": (
        "压测",
        "把压测原始 json 汇总成可读报告",
        "输入：results/loadtest/loadtest-*.json",
    ),
    "client/extract_numbers.py": (
        "压测",
        "把汇总结果直接打成 markdown 表格行，报告里的数字由它生成",
        "输入：results/loadtest/ + longctx-supplement.json",
    ),
    "client/verify.py": (
        "验证",
        "冒烟验证：/health、/v1/models、completions、chat、图片输入五类探针",
        "--server --keyfile --out verify.json",
    ),
    "gen_manifest.py": (
        "工具",
        "生成本清单（行数/字节/sha256 全部实测），--check 可校验附件未被改动",
        "python3 gen_manifest.py [--check]",
    ),
}

GROUPS = ["部署", "压测", "分析", "验证", "工具"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_lines(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return 0


def collect() -> list[dict]:
    rows = []
    for path in sorted(HERE.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"MANIFEST.md", "manifest.json"}:
            continue
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(HERE).as_posix()
        group, purpose, args = META.get(rel, ("未分类", "", ""))
        rows.append(
            {
                "path": rel,
                "group": group,
                "purpose": purpose,
                "usage": args,
                "lines": count_lines(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    rows.sort(key=lambda r: (GROUPS.index(r["group"]) if r["group"] in GROUPS else 99, r["path"]))
    return rows


def render_md(rows: list[dict]) -> str:
    total_lines = sum(r["lines"] for r in rows)
    total_bytes = sum(r["bytes"] for r in rows)
    out = [
        "# Strata 脚本清单",
        "",
        "> 本文件由 `gen_manifest.py` 自动生成，**不要手改**；改了脚本就重跑一次。",
        "> 行数 / 字节数 / sha256 全部取自真实文件，clone 之后 `python3 gen_manifest.py --check` 可校验附件未被改动。",
        "",
        "## 总览",
        "",
        f"- 脚本总数：**{len(rows)}**",
        f"- 代码行数合计：**{total_lines:,}**",
        f"- 体积合计：**{total_bytes / 1024:.1f} KB**",
        "- 路径约定：脚本内写死了 `/workspace/Strata`（部署机的落地目录），换机器只需改 `env.sh` 里的 `STRATA_ROOT`。",
        "",
    ]
    for group in GROUPS + ["未分类"]:
        bucket = [r for r in rows if r["group"] == group]
        if not bucket:
            continue
        out += [f"## {group}（{len(bucket)}）", "", "| 脚本 | 行数 | 作用 | 关键参数 / 依赖 |", "| --- | ---: | --- | --- |"]
        for r in bucket:
            out.append(
                f"| [`{r['path']}`]({r['path']}) | {r['lines']} | {r['purpose']} | {r['usage'] or '—'} |"
            )
        out.append("")
    out += [
        "## 校验和",
        "",
        "| 脚本 | sha256 |",
        "| --- | --- |",
    ]
    for r in rows:
        out.append(f"| `{r['path']}` | `{r['sha256']}` |")
    out += [
        "",
        "## 复现顺序",
        "",
        "```bash",
        "bash 03_run_container.sh                 # 1) 起容器（或 02_launch.sh 走 CLI 路线）",
        "bash 02_launch.sh                        # 2) 等就绪（轮询 /health，不要中途 kill）",
        "python3 client/verify.py --out verify.json   # 3) 冒烟，五个接口全过才算装好",
        "bash run_loadtest.sh                     # 4) 五类压测，约 14 分钟",
        "python3 client/extract_numbers.py        # 5) 出表",
        "bash hitrate_probe.sh                    # 6) 补命中率↔速度的配对样本",
        "```",
        "",
    ]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    args = ap.parse_args()

    rows = collect()

    if args.check:
        if not OUT_JSON.exists():
            print("manifest.json 不存在，先跑一次不带 --check 的生成", file=sys.stderr)
            return 1
        old = {r["path"]: r["sha256"] for r in json.loads(OUT_JSON.read_text(encoding="utf-8"))["scripts"]}
        new = {r["path"]: r["sha256"] for r in rows}
        bad = [p for p in sorted(set(old) | set(new)) if old.get(p) != new.get(p)]
        if bad:
            print("以下脚本与清单不一致：", file=sys.stderr)
            for p in bad:
                print(f"  {p}", file=sys.stderr)
            return 1
        print(f"OK：{len(new)} 个脚本与清单一致")
        return 0

    OUT_JSON.write_text(
        json.dumps(
            {
                "schema": "strata-script-manifest/v1",
                "base_dir": "/workspace/Strata",
                "script_count": len(rows),
                "total_lines": sum(r["lines"] for r in rows),
                "scripts": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    OUT_MD.write_text(render_md(rows), encoding="utf-8")
    print(f"wrote {OUT_MD.name} / {OUT_JSON.name}（{len(rows)} 个脚本，{sum(r['lines'] for r in rows)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
