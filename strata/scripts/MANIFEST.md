# Strata 脚本清单

> 本文件由 `gen_manifest.py` 自动生成，**不要手改**；改了脚本就重跑一次。
> 行数 / 字节数 / sha256 全部取自真实文件，clone 之后 `python3 gen_manifest.py --check` 可校验附件未被改动。

## 总览

- 脚本总数：**18**
- 代码行数合计：**1,985**
- 体积合计：**74.3 KB**
- 路径约定：脚本内写死了 `/workspace/Strata`（部署机的落地目录），换机器只需改 `env.sh` 里的 `STRATA_ROOT`。

## 部署（5）

| 脚本 | 行数 | 作用 | 关键参数 / 依赖 |
| --- | ---: | --- | --- |
| [`02_launch.sh`](02_launch.sh) | 32 | 下载引擎+模型并拉起服务（官方 CLI 路线） | --context 64k --vision cpu --parallel 1 --port 8899 --tune skip |
| [`03_run_container.sh`](03_run_container.sh) | 40 | 官方容器路线启动：随机 API key、seccomp=unconfined、只绑 GPU1 | 镜像 ghcr.nju.edu.cn/niko1221/strata:0.2.2-cuda13；--gpus device=1 |
| [`enable_vision.sh`](enable_vision.sh) | 47 | 开启视觉输入（CPU 读图器），首次多下约 0.9 GB 读图器文件 | VISION=cpu；带视觉编码器重启实测 254 s |
| [`env.sh`](env.sh) | 26 | 共享环境变量：把 HOME / XDG / TMPDIR / pip / HF 缓存全部收敛到 /workspace/Strata 内部 | 被 02_launch.sh 等 source；无参数 |
| [`rebind_port.sh`](rebind_port.sh) | 48 | 把端口从 127.0.0.1 重绑到 0.0.0.0，并顺带轮询 /health 判定就绪 | warm 重启实测 55 s；模型留在卷里不重下 |

## 压测（6）

| 脚本 | 行数 | 作用 | 关键参数 / 依赖 |
| --- | ---: | --- | --- |
| [`client/extract_numbers.py`](client/extract_numbers.py) | 55 | 把汇总结果直接打成 markdown 表格行，报告里的数字由它生成 | 输入：results/loadtest/ + longctx-supplement.json |
| [`client/loadtest.py`](client/loadtest.py) | 447 | 压测主程序，五个 stage 全在这里 | --stages sweep,sustained,longctx,vision,overload --sweep-clients 1,2,4,8,16 --sustained-clients 4 --minutes 10 --out-tokens 192 --rounds 2 |
| [`client/loadtest_report.py`](client/loadtest_report.py) | 123 | 把压测原始 json 汇总成可读报告 | 输入：results/loadtest/loadtest-*.json |
| [`client/metrics_sampler.py`](client/metrics_sampler.py) | 45 | 服务端 /metrics 采样，默认 5 s 一次，写 jsonl | 用法：metrics_sampler.py OUT.jsonl SECONDS INTERVAL |
| [`client/sampler.py`](client/sampler.py) | 90 | 宿主侧采样：GPU 利用率/显存/功耗/温度 + CPU + 内存，默认 2 s 一次 | 用法：sampler.py OUT.csv SECONDS INTERVAL |
| [`run_loadtest.sh`](run_loadtest.sh) | 37 | 五类压测一键跑：先起两个采样器，再跑 sweep/sustained/longctx/vision/overload | MINUTES=${MINUTES:-10}；采样器 2 s / 5 s 间隔 |

## 分析（5）

| 脚本 | 行数 | 作用 | 关键参数 / 依赖 |
| --- | ---: | --- | --- |
| [`bucket_stats.py`](bucket_stats.py) | 68 | 按命中率 / PCIe 溢出分桶统计 decode，坐实“1% 溢出掉 39%” | 输入：hitrate_vs_decode.py 的产物 |
| [`hitrate_probe.sh`](hitrate_probe.sh) | 49 | 先打几发请求，再把 /metrics 里的 per-request 遥测（hit_rate / pcie_share / decode）打印出来 | 依赖 /metrics 的 requests[] 字段 |
| [`hitrate_vs_decode.py`](hitrate_vs_decode.py) | 68 | 从引擎日志里抽「缓存命中率 ↔ decode 速度」配对样本 | 输入：engine.log；输出 (hit_rate, decode_tok_s) 序列 |
| [`inspect_format.py`](inspect_format.py) | 194 | 读 GGUF 头与元数据（量化档位、tensor 数、上下文长度） | 输入：GGUF 路径；纯标准库 |
| [`inspect_tensors.py`](inspect_tensors.py) | 142 | 按量化类型统计 tensor 数与参数量，验证“Q2_0 其实是混合精度” | 输入：GGUF 路径；输出分档表 |

## 验证（1）

| 脚本 | 行数 | 作用 | 关键参数 / 依赖 |
| --- | ---: | --- | --- |
| [`client/verify.py`](client/verify.py) | 215 | 冒烟验证：/health、/v1/models、completions、chat、图片输入五类探针 | --server --keyfile --out verify.json |

## 工具（1）

| 脚本 | 行数 | 作用 | 关键参数 / 依赖 |
| --- | ---: | --- | --- |
| [`gen_manifest.py`](gen_manifest.py) | 259 | 生成本清单（行数/字节/sha256 全部实测），--check 可校验附件未被改动 | python3 gen_manifest.py [--check] |

## 校验和

| 脚本 | sha256 |
| --- | --- |
| `02_launch.sh` | `e3bd14a5b7dfd63f6a3b973a23756b1c5d0f268c5bc517470e8065b7f1c10423` |
| `03_run_container.sh` | `c75a5b82d11c8bf2baf6756ae99f00b558ce42f2ea2081d15dca2718df245006` |
| `enable_vision.sh` | `af5a7bd7247fef79a270f602f812fe2703a6a3399844b2729b9f5d2269919e91` |
| `env.sh` | `fdfb445148be6cc07c11f87fb2bb76ca52e1d26019a4696a37b13a684dec10ba` |
| `rebind_port.sh` | `717fa908fb4f8cc10d76d9f7c299e436cebb4d1790907d049288b1fac0a7a210` |
| `client/extract_numbers.py` | `dbeecf72ef4fd382074ba06f3575e60d5105a4744a9a915e62c68c966d5838cc` |
| `client/loadtest.py` | `bf9dc9e98a41ffb1d9bf41e295dabc85fb3a5d04700fad118057dde335113049` |
| `client/loadtest_report.py` | `46ac1ac27f5c6b23b0ca6cbe20a920f03ba4d618bef206c562a09d81aaf39d3f` |
| `client/metrics_sampler.py` | `85ca4819b0a0eb1ee00a55956b694df32fdd6bbe0ba95dad0dcb4a8fda28c13d` |
| `client/sampler.py` | `2c0601b365e46be751cd8dcd2f159afffe16a89af6a3fe60d9d1e2ecd543d668` |
| `run_loadtest.sh` | `c914c75c3995edf906afea15982dcb06d1c276bba5af23f7418591d53e0b4f9e` |
| `bucket_stats.py` | `8ef7a14055c0ac9dc3625c11fd7163948b146831d3f9e76258253873ce3cbbef` |
| `hitrate_probe.sh` | `45ba8910bf8793b2865d5bcf8441af19200f27e5b5eb3d5e63c6d1f94cc98c26` |
| `hitrate_vs_decode.py` | `89a855b9ff81d0f4924dbf0c2615cf9c6cfcbc5d555c001b79629153b27faceb` |
| `inspect_format.py` | `76f1007d7cb98347064408e51a84cbe9bb4c666cf1356cebc46d7927f4c67ec9` |
| `inspect_tensors.py` | `d56e1b1a1e6186f5f226830f3f4069079cf689e3e5b92a57510501027107e12c` |
| `client/verify.py` | `691f2f8c9a87fa8f9724da8965b05316af166d2fa4d8669262335ca5688b0111` |
| `gen_manifest.py` | `96cf184b7cd0ef0a2db0f9d3181f92e8e24bee05807f86636eb05ee11e2084c4` |

## 复现顺序

```bash
bash 03_run_container.sh                 # 1) 起容器（或 02_launch.sh 走 CLI 路线）
bash 02_launch.sh                        # 2) 等就绪（轮询 /health，不要中途 kill）
python3 client/verify.py --out verify.json   # 3) 冒烟，五个接口全过才算装好
bash run_loadtest.sh                     # 4) 五类压测，约 14 分钟
python3 client/extract_numbers.py        # 5) 出表
bash hitrate_probe.sh                    # 6) 补命中率↔速度的配对样本
```
