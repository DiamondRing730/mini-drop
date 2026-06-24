# Mini-Drop 进度

> 最后更新：基础闭环、三类采集、可停止/续建 Continuous Profiling、容器/PID 发现、智能归因与可验证性能优化闭环已实现并验证；当前进入交付收尾。

## 一句话状态

四个组件（web / server / agent / analyzer）+ Postgres 已用 `docker compose` 一键起，
端到端验证通过：建任务 → 状态机流转 → py-spy 采集 → 分析出火焰图 + 热点 → Web 展示。
单测 46 个全过、覆盖率约 80%；E2E 正常、坏 PID、Agent 离线恢复三条路径均为 `passed`。

## 已完成 ✅

| 模块 | 内容 | 验证 |
|---|---|---|
| **server** (FastAPI+PG) | 5 张表（含 `profile_chunks`）、任务状态机（每次迁移落库带 reason）、任务 CRUD/筛选分页/按原参数重试、产物清单与安全下载、优化前后 profile 差分与独立复算、Agent 心跳+原子领取（`FOR UPDATE SKIP LOCKED`）、30s 离线检测、审计日志、持续采样时间轴/窗口接口、JSON 结构化日志 | 单测 + 实跑 |
| **agent** (Python) | 5s 心跳线程 + 异常隔离 worker、perf（cpu-clock）、py-spy、bpftrace、/proc 自监控、持续 py-spy 切片、重启后自动接管未完成任务、产物写共享 volume | 实跑 |
| **analyzer** (Python) | 纯 Python stackcollapse + 火焰图 SVG、TopN、tree.json、eBPF 直方图解析、轮询领取 | 单测 + 实跑 |
| **web** (React+TS+ECharts) | 首页、任务搜索/筛选/分页、失败原因与一键重试、产物查看下载、任务/审计时间线、火焰图、TopN、eBPF 延迟分布、持续采样回放、离线/DeepSeek 归因选择与校验面板、函数差分图与红绿差分火焰图 | 构建通过 + 实跑 |
| **infra** | 各组件 Dockerfile、docker-compose（agent: privileged + pid:host）、4个可独立运行的演示场景（CPU优化前/后、数值循环、IO） | `compose up` + 4场景实跑通过 |
| **tests** | 单测：状态机 / API / analyzer / eBPF / continuous / attribution / profile comparison / 任务筛选分页 / 重试 / 产物下载 / 删除保护 / 重启接管；E2E：正常路径 + 坏 PID + Agent 离线恢复 | 单测 46/46、E2E 3/3，约 80% 覆盖 |

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
- ✅ **Continuous Profiling（扩展，真跑）**：有限时长 py-spy 会话按 slice 切片采集，40s 会话出 5 个切片；
  `GET /tasks/{tid}/timeline` 时间轴 + `GET /tasks/{tid}/window?from&to` **按任意窗口在线合并渲染火焰图**
  （实测子窗口=2 切片=1582 样本，全窗口=5 切片），Web 有时间轴拖选 + 窗口火焰图
- ✅ **主动停止/续建（真跑）**：真实持续任务通过心跳接收停止信号，在切片边界进入 `STOPPED`；续建生成新任务并保留旧时间轴。
- ✅ **容器/PID 发现（真跑）**：Agent 通过只读挂载的 Docker socket 发现 6 个容器及宿主 PID，页面可直接联动选择目标。
- ✅ **采集线程容错（真跑）**：运行中删除返回 409；worker 隔离单任务异常；Agent 重启后自动接管数据库中仍为 `RUNNING` 的未完成任务。
- ✅ **3 条 E2E**（WSL 原生 venv）→ **3 passed**（正常 / 坏PID / Agent 离线恢复）
- ✅ **任务管理增强（真跑）**：按名称/ID/PID 搜索、状态/采集器筛选和分页可用；真实 `e2e` 任务产物清单与下载大小一致；按原参数重试后采集/分析再次 `DONE`，生成 flamegraph/TopN/tree/原始 folded 共 4 个文件。
- ✅ **4个独立演示场景（真跑）**：`demo-before`、`demo-after`、`demo-numeric`、`demo-io` 均可单独切换负载、提交一个任务并等待分析 `DONE`；不会一次启动全部演示任务。
- ✅ **可验证性能优化闭环（真跑）**：相同CPU程序的朴素递归基线 `6c1a5ee9d687` 与 `lru_cache` 优化版 `a9ad226b192d` 均采到989个样本；`fib` 自耗时占比从74.22%降至0%，5/5差分数值独立复算通过，并生成红绿差分火焰图。
- ✅ **单测**：`pytest tests/unit` → **46 passed；覆盖率约 80%**（含 eBPF/flame/continuous/停止续建/容器发现/删除保护/重启接管/attribution/comparison/筛选分页/重试/产物下载）
- ✅ **Agent 离线恢复 + 审计日志**：停 agent → 30s 后 `online=false` 且写 `OFFLINE` 审计；重启 → 3s 内 `online=true` 且写 `RECOVER`。审计轨迹 `REGISTER→OFFLINE→RECOVER` 经新接口 `GET /api/v1/agents/{id}/events` 可见

## 当前能力边界

- Continuous Profiling 当前是 1–3600 秒的有限会话，支持主动停止与续建，但不是无限常驻服务；尚无自动保留/清理策略。
- 持续模式当前固定使用 py-spy；perf 持续采样属于可选增强。
- 窗口火焰图以切片为最小粒度，合并所有与窗口重叠的完整切片，因此窗口边缘精度取决于 `slice_sec`。
- E2E 在 Server 不可达时会被标记为 skipped；验收必须确认输出为 `3 passed`。

## 重要环境说明（踩坑记录）

- **Docker Hub 被污染**：本机直连 `auth.docker.io` 超时（解析到污染 IP）。已用镜像源
  `docker.m.daocloud.io` 拉取 4 个基础镜像（python:3.12-slim / node:20-alpine / nginx:alpine / postgres:14）
  并 retag 为标准名，之后 `docker compose build` 即走本地缓存。
  → **评审若在干净网络（Docker Hub 可达）则无需此步**；如在受限网络，需配置 registry mirror。
- **perf**：WSL 用软件事件 `cpu-clock`（硬件 PMU 不可用）。
- **py-spy 跨容器采集**：agent 容器 `privileged + pid:host`，通过 `docker inspect` 拿到目标容器宿主 PID 后采集，已验证可行。

## Git 提交历史（小步、说"为什么"）

```
feat(server):   continuous profiling chunks, timeline and window flamegraph
feat(agent):    continuous profiling slice loop
feat(web):      continuous profiling timeline and window replay
test:           continuous profiling unit tests
docs:           mark continuous profiling and e2e verified
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

1. **交付收口**：在干净 Ubuntu 22.04 上执行 clone → `make demo` → unit/E2E，保存完整结果。
2. **设计文档已按 9 页结构生成 Word（待本机检查并导出 PDF）**；继续完成 ≤15min 演示视频。
3. **智能归因已完成**：页面显式选择离线/DeepSeek、受限工具调用、可验证结论；离线基准
   见 `docs/attribution-evaluation.md`，DeepSeek 指标需配置密钥后显式运行。
4. （可选）无限常驻、数据保留策略、自然语言采集、perf 持续模式、前端打磨。

> ✅ 基础 MVP + 三项必做能力（py-spy / eBPF / Continuous Profiling）+ 3 条 E2E 均已完成并验证。
> 环境提示：WSL Ubuntu 可原生跑 `make` / `pytest`；镜像构建在 Windows 侧或配好 registry mirror 的网络下进行。
