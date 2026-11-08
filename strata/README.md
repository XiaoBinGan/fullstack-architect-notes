# Strata 附件（125B MoE · 单卡 RTX 5090）

对应文章：《单卡5090跑125B 大模型》三部曲——原理篇 / 实测篇 / 实操篇。

## 这里有什么

| 路径 | 内容 |
| --- | --- |
| [`scripts/MANIFEST.md`](scripts/MANIFEST.md) | 脚本清单：18 个脚本，按部署 / 压测 / 分析 / 验证分组，附行数、作用、关键参数、sha256 |
| [`scripts/manifest.json`](scripts/manifest.json) | 同一份清单的机器可读版 |
| [`scripts/`](scripts/scripts/) | 脚本正文（`client/` 下是压测与验证客户端） |
| [`baseline/BASELINE.md`](baseline/BASELINE.md) | 本机基线数字：启动耗时、官方基准、并发扫描、长上下文、图片输入、硬件画像、三层效率、工程常数 |
| [`baseline/baseline.csv`](baseline/baseline.csv) | 同一批数字的长表，Excel / BI 直接用 |
| [`baseline/baseline.json`](baseline/baseline.json) | 单一数据源 |

## 机器与版本（所有数字的前提）

- GPU：**RTX 5090 32 GB**（另一张 4090 被 vLLM 常驻，未参与）
- CPU：Xeon Gold 5218 ×2（无 AVX512-BF16 → 专家核走 AVX-2）
- 内存 125.6 GiB / PCIe **Gen3 ×16**（实测 13.9 GB/s，本轮主要瓶颈）
- 引擎：Strata **0.2.2** / engine 0.1.47-linux-x86_64-cuda-cuda13
- 模型：**Qwen3.8-Flash-Next Q2_0**，125B 级 MoE，48 层 × 512 专家 = 24,576 槽
- 部署：容器 + `seccomp=unconfined`，B3 推荐配置 = 64K / `parallel=1` / `VISION=gpu`

## 三条最该记住的数字

1. **每 1 GiB 专家缓存 ≈ +6.53 tok/s**（线性，不递减）——显存换速度是可以算的。
2. **PCIe 溢出 0 → 0.5% 就掉 39% decode**——成本在流水线气泡，不在带宽。
3. **18 GB 显存之差 = +82% 吞吐**——同机被别的服务挤占，比换硬件更致命。

## 复现顺序

```bash
bash scripts/03_run_container.sh                 # 起容器（或 02_launch.sh 走 CLI 路线）
bash scripts/02_launch.sh                        # 等就绪，轮询 /health
python3 scripts/client/verify.py --out verify.json
bash scripts/run_loadtest.sh                     # 五类压测 ≈14 min
python3 scripts/client/extract_numbers.py        # 出表
bash scripts/hitrate_probe.sh                     # 命中率 ↔ 速度配对样本
```

脚本内路径写死 `/workspace/Strata`，换机器改 `scripts/env.sh` 的 `STRATA_ROOT` 即可。
