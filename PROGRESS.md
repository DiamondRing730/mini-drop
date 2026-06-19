# Mini-Drop 进度

> 最后更新：第一版最小闭环（建任务 → 心跳领取 → perf/py-spy 采集 → 火焰图展示）**已端到端跑通并验证**。

## 一句话状态

四个组件（web / server / agent / analyzer）+ Postgres 已用 `docker compose` 一键起，
端到端验证通过：建任务 → 状态机流转 → py-spy 采集 → 分析出火焰图 + 热点 → Web 展示。
单测 16 个全过、覆盖率 79%。

## 已完成 ✅

| 模块 | 内容 | 验证 |
|---|---|---|
| **server** (FastAPI+PG) | 4 张表、任务状态机（每次迁移落库带 reason）、任务 CRUD、Agent 心跳+原子领取（`FOR UPDATE SKIP LOCKED`）、30s 离线检测、审计日志、analyzer 内部接口、JSON 结构化日志 | 单测 + 实跑 |
| **agent** (Python) | 5s 心跳线程 + worker 线程（采集不阻塞心跳）、perf 采集器（cpu-clock 软件事件、独立进程组超时 killpg）、py-spy 采集器、/proc 自监控 PidStats、产物写共享 volume | 实跑 |
| **analyzer** (Python) | 纯 Python 实现 stackcollapse + 火焰图 SVG 渲染（无需 perl/FlameGraph 脚本）、TopN 热点、tree.json、轮询领取 | 单测 + 实跑 |
| **web** (React+TS+ECharts) | 首页（Agent 列表 + 任务列表 + 新建采样）、任务详情（状态时间线 + 火焰图 iframe + TopN ECharts）、2s 轮询、hash 路由 | 构建通过 + 实跑 |
| **infra** | 各组件 Dockerfile、docker-compose（agent: privileged + pid:host）、Makefile（`make demo`）、demo 工作负载 | `compose up` 通过 |
| **tests** | 单测：状态机 / API(TestClient over SQLite) / analyzer；E2E：正常路径 + 坏 PID + Agent 离线恢复 | 单测 16/16 过，79% 覆盖 |

## 实跑验证结果（本机 WSL2 Ubuntu-22.04 + Docker Desktop）

- ✅ `docker compose up` 起全栈：postgres healthy、server healthy、agent 在线心跳（上报 rss/cpu/io）
- ✅ **正常路径**：py-spy 采集 demo 进程，状态机
  `None→PENDING→RUNNING→UPLOADING→DONE`（每步带 reason）+ analysis `DONE`
- ✅ **火焰图 + 热点**：791 样本，TopN 准确命中负载热点（`fib` 58.9%+17.7%、`warm_path`、`crunch_numbers`，含 file:line）
- ✅ **异常路径（坏 PID）**：target_pid=999999 → 任务 `FAILED`，reason=`target pid 999999 does not exist`
- ✅ **Web**：`http://localhost:8080` 返回 200（nginx 反代 /api 到 server），新增 Agent 审计日志面板
- ✅ **eBPF 采集器（扩展，真跑）**：bpftrace 抓 read/write syscall 延迟分布；一次采集 **130,333** 个事件，
  现场 `dd` 制造 IO 后 `dd` 进程出现在 by_comm 第 2（7470 次），延迟直方图（log2 桶）正常；已修跨 CPU `nsecs` 下溢。
  Web 用独立的 ECharts 分布图展示（区别于火焰图）
- ✅ **Continuous Profiling（扩展，真跑）**：常驻 py-spy 按 slice 切片采集，40s 会话出 5 个切片；
  `GET /tasks/{tid}/timeline` 时间轴 + `GET /tasks/{tid}/window?from&to` **按任意窗口在线合并渲染火焰图**
  （实测子窗口=2 切片=1582 样本，全窗口=5 切片），Web 有时间轴拖选 + 窗口火焰图
- ✅ **3 条 E2E**（WSL 原生 venv）→ **3 passed**（正常 / 坏PID / Agent 离线恢复）
- ✅ **单测**：`pytest tests/unit`（WSL Ubuntu 原生 venv）→ **21 passed；覆盖率 79%**（含 eBPF/flame/continuous）
- ✅ **Agent 离线恢复 + 审计日志**：停 agent → 30s 后 `online=false` 且写 `OFFLINE` 审计；重启 → 3s 内 `online=true` 且写 `RECOVER`。审计轨迹 `REGISTER→OFFLINE→RECOVER` 经新接口 `GET /api/v1/agents/{id}/events` 可见
- ℹ️ 3 条 E2E 用例（正常/坏PID/离线恢复）均已写好（`tests/e2e/`）；正常+坏PID+离线恢复均已手动实跑通过。pytest 形式待在带 pip 的 Python/容器里跑一遍

## 重要环境说明（踩坑记录）

- **Docker Hub 被污染**：本机直连 `auth.docker.io` 超时（解析到污染 IP）。已用镜像源
  `docker.m.daocloud.io` 拉取 4 个基础镜像（python:3.12-slim / node:20-alpine / nginx:alpine / postgres:14）
  并 retag 为标准名，之后 `docker compose build` 即走本地缓存。
  → **评审若在干净网络（Docker Hub 可达）则无需此步**；如在受限网络，需配置 registry mirror。
- **perf**：WSL 用软件事件 `cpu-clock`（硬件 PMU 不可用）。
- **py-spy 跨容器采集**：agent 容器 `privileged + pid:host`，通过 `docker inspect` 拿到目标容器宿主 PID 后采集，已验证可行。

## Git 提交历史（小步、说"为什么"）

```
test:  unit suite (state machine, API, analyzer) + 3 e2e paths
feat(infra):    dockerfiles, compose topology and one-command make demo
feat(web):      React+TS UI for create/list/detail with live polling and flamegraph
feat(analyzer): pure-Python folded-stack -> flamegraph SVG + TopN hotspots
feat(agent):    py-spy language-level collector + worker wiring
feat(agent):    heartbeat loop + perf collector with process-group timeout
feat(server):   background offline detector and app wiring
feat(server):   agent heartbeat with atomic task claim, result + analysis APIs
feat(server):   task create/list/detail/soft-delete + artifact download
feat(server):   data model + task state machine with reasoned transitions
chore:          scaffold repo with README, gitignore and LF normalization
```

## 下一步（按优先级）

1. **智能归因（加分，强烈推荐）**：结构化喂 LLM、LLM 只能调自定义工具、产可验证结论 + 评测报告。
2. **设计文档（≤10页）+ 演示视频（≤15min）**。
3. （可选）自然语言采集；perf 持续模式；前端打磨。

> ✅ 基础 MVP + 三项必做扩展（py-spy / eBPF / Continuous Profiling）+ 3 条 E2E 均已完成并验证。
> 环境提示：WSL Ubuntu 可原生跑 `make` / `pytest`；镜像构建在 Windows 侧或配好 registry mirror 的网络下进行。
