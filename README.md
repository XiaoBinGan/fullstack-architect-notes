# fullstack-architect-notes · 全栈架构师学习笔记

文章对应的**附件资料库**：正文留在订阅号/博客，仓库只存「能跑、能验、能复现」的东西——脚本、原始数据、基线数字、配置快照。

## 目录结构

```
fullstack-architect-notes/
├── strata/                  # Strata 三部曲（125B MoE 单卡部署 / 实测 / 实操）
│   ├── scripts/             # 脚本清单 + 全部脚本附件
│   │   ├── MANIFEST.md      # 清单（行数 / 作用 / sha256，自动生成）
│   │   ├── manifest.json    # 同一份清单的机器可读版
│   │   └── client/          # 压测与验证客户端
│   └── baseline/            # 基线数字（本机实测）
│       ├── BASELINE.md      # 人看的基线表
│       ├── baseline.csv     # Excel/BI 直接吃
│       └── baseline.json    # 单一数据源，改数字只改这里
└── <下一篇>.md 的附件目录按同样结构追加
```

## 附件约定

1. 每篇文章一个目录，目录内固定两个子目录：`scripts/`（脚本清单 + 脚本）、`baseline/` 或 `data/`（数字与原始数据）。
2. 清单与基线文档都由脚本生成，不手抄：
   - `strata/scripts/gen_manifest.py` → `MANIFEST.md` / `manifest.json`
   - `strata/baseline/gen_baseline.py` → `BASELINE.md` / `baseline.csv`
   - 两者都带 `--check`，clone 之后可校验附件未被改动。
3. 敏感信息（API key、内网地址）不入库，复现时现场生成。

## 快速开始

```bash
git clone git@github.com:XiaoBinGan/fullstack-architect-notes.git
cd fullstack-architect-notes/strata/scripts
python3 gen_manifest.py --check      # 校验脚本附件完整性
cd ../baseline && python3 gen_baseline.py --check
```

## 已有附件

| 文章 | 附件目录 | 内容 |
| --- | --- | --- |
| 单卡 5090 跑 125B 大模型 · 原理篇 / 实测篇 / 实操篇 | [`strata/`](strata/) | 18 个脚本（部署 / 压测 / 分析 / 验证）、7 种配置矩阵、官方基准 / 并发扫描 / 长上下文 / 硬件画像全套基线数字 |

---

公众号：**全栈架构师笔记**
