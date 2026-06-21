# Mini-Drop

一个简化版的 Linux 按需性能采集与可视化分析平台。用户在 Web 上指定目标进程
PID / 采样时长 / 采样率，平台把采集任务下发到 Agent，用 `perf` / `py-spy` / `bpftrace`
采集运行时性能数据，由 Analyzer 生成火焰图、热点、延迟分布，最后在 Web 上展示并给出
（可选）AI 归因结论。

## 架构

```
┌────────────┐   REST/JSON    ┌─────────────────┐
│  web       │ ─────────────► │  server          │  ← 任务编排 / 状态机 / 落库
│ (React TS) │ ◄───────────── │  (FastAPI + PG)  │
└────────────┘   poll 1~3s    └───┬─────────┬────┘
                                  │ heartbeat│ 共享 volume
                                  ▼ 领任务   ▼ /data/artifacts
                            ┌──────────┐  ┌──────────────┐
                            │  agent   │  │  analyzer     │
                            │ (Python) │  │  (Python)     │
                            │ perf     │  │ folded → SVG  │
                            │ py-spy   │  │ TopN 热点      │
                            │ bpftrace │  └──────────────┘
                            └──────────┘
```

四个组件：

| 组件 | 语言 | 职责 |
|---|---|---|
| `web` | React + TS + ECharts | 建任务、搜索筛选分页、失败任务重试、产物查看下载、状态/审计时间线、火焰图、热点、eBPF 延迟分布、持续采样回放 |
| `server` | Python FastAPI + PostgreSQL | 任务编排、状态机、Agent 心跳/离线、审计、持续采样切片索引 |
| `agent` | Python | 心跳、领取任务、调用 perf/py-spy/bpftrace、持续切片、上传产物 |
| `analyzer` | Python | 折叠栈/原始数据转火焰图 SVG、热点 JSON 和 eBPF 分布 JSON |

## 任务状态机

```
PENDING ──► RUNNING ──► UPLOADING ──► DONE
   │           │            │
   ├───────────┴────────────┴────────► FAILED
   └───────────┴────────────┴────────► STOPPED（持续任务主动停止）
```

**每一次状态迁移都会落库到 `task_state_transition` 表并带 `reason` 字段**，Web 端轮询实时可见。

Agent 每 5s 心跳；Server 超过 30s 未收到心跳判定离线；Agent 离线/恢复都会写
`agent_event` 审计日志。

## 运行要求

- Linux 内核（开发与演示均在 **WSL2 Ubuntu 22.04 / kernel 6.6** 上验证）
- Docker + Docker Compose v2/v5
- Agent 容器需要 `privileged` + `pid: host` 才能 `perf`/`py-spy` 采集宿主进程
- `perf_event_paranoid` 建议 ≤ 1（WSL 下用软件事件 `cpu-clock`，已规避硬件 PMU 限制）

## 快速开始

```bash
# 在 Ubuntu 22.04 / WSL2 上
git clone <repo> && cd mini-drop
make demo-before   # 只运行未优化CPU基线并等待任务完成
```

独立演示入口：

```bash
make demo-before   # 未缓存递归 fib（优化前）
make demo-after    # 相同程序使用 lru_cache（优化后）
make demo-numeric  # 数值循环热点
make demo-io       # eBPF read/write 延迟
```

每条命令只创建一个任务。优化闭环演示依次运行 `demo-before`、`demo-after`，然后在
优化后任务中选择优化前任务进行比较。完整说明见
[docs/demo-scenarios.md](docs/demo-scenarios.md)。

测试命令：

```bash
make unit          # 单元测试
make e2e           # 需要先启动完整服务栈；预期 3 passed
```

当前 E2E 用例覆盖正常采集、非法 PID、Agent 离线与恢复。若 Server 不可达，测试文件会
被 pytest 标记为 skipped，因此验收时必须确认输出为 `3 passed`，不能只看退出码。

设计文档将在 `docs/` 中随最终交付补齐。

## 已实现能力

- 按需 perf / py-spy / eBPF 采集与可视化。
- `PENDING → RUNNING → UPLOADING → DONE / FAILED` 状态迁移审计。
- Agent 5 秒心跳、30 秒离线检测及离线/恢复审计。
- py-spy 持续采样：按时间切片、时间轴展示、选择窗口后在线合并火焰图。
- 持续任务可主动停止并续建；旧任务的切片和时间轴完整保留。
- Agent 自动发现 Docker 容器及宿主 PID，页面可直接联动选择采样目标。
- 智能归因：页面可显式选择离线归因或 DeepSeek；两者共享只读工具和独立校验器。
- 可验证性能优化闭环：选择优化前/后任务，生成函数差分、红绿差分火焰图和独立复算报告；
  方法与边界见 [docs/optimization-loop.md](docs/optimization-loop.md)。
- 任务列表支持名称/ID/PID 搜索、状态/采集器筛选、分页和失败原因展示。
- 已结束任务可按原参数一键重试；详情页可列出、查看和下载原始及分析产物。
- 44 条单元测试用例、3 条端到端测试用例；最近完整单测覆盖率约 80%。归因基准见
  [docs/attribution-evaluation.md](docs/attribution-evaluation.md)。

Continuous Profiling 当前实现为**可主动停止的有限时长会话**：会话时长 1–3600 秒、
切片时长 1–60 秒，仅支持 py-spy。停止在当前切片结束后生效；续建会创建新任务，旧会话
仍可独立回放。窗口回放以切片为最小粒度，边缘会包含与所选窗口重叠的完整切片。
无限常驻、自动保留策略和 perf 持续模式属于后续增强。

## 开发状态

基础能力、必做扩展（Continuous Profiling、eBPF、语言级 py-spy）和智能归因已实现。
智能归因默认离线运行；如需 DeepSeek，在 `.env` 配置 `DEEPSEEK_API_KEY` 后从页面选择
“DeepSeek 归因”。系统不会自动调用外部模型，也不会在失败时静默切换引擎。

当前进入交付收尾阶段：干净环境复现、完整设计文档和演示视频。自然语言采集仍为未实现
的可选加分项。
