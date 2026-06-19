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
| `web` | React + TS + ECharts | 建任务 / 看任务列表 / 看火焰图与热点 |
| `server` | Python FastAPI + PostgreSQL | 任务编排、任务状态机、Agent 心跳/离线、落库 |
| `agent` | Python | 心跳上报、领取任务、调用 perf/py-spy/bpftrace、上传产物 |
| `analyzer` | Python | 把折叠栈/原始数据转成火焰图 SVG + 热点 JSON |

## 任务状态机

```
PENDING ──► RUNNING ──► UPLOADING ──► DONE
   │           │            │
   └───────────┴────────────┴────────► FAILED
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
make demo          # docker compose up + 初始化 + 打开 http://localhost:8080
```

详见 [docs/](docs/)（设计文档随开发补全）。

## 开发状态

当前进度：**第一版最小闭环开发中**（建任务 → 心跳领取 → perf/py-spy 采集 → 火焰图展示）。
扩展能力（Continuous Profiling、eBPF、智能归因）随后迭代。
