import { useEffect, useState, type FormEvent } from "react";
import { api, type CreateTaskBody } from "../api";
import type { Agent, AgentEvent, TaskSummary } from "../types";
import { StatusBadge } from "../App";

export function Home() {
  const pageSize = 8;
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [events, setEvents] = useState<(AgentEvent & { agent_id: string })[]>([]);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [profilerFilter, setProfilerFilter] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  const refresh = async () => {
    try {
      const [a, t] = await Promise.all([
        api.listAgents(),
        api.listTasks({
          q: query.trim(), status: statusFilter, profiler_type: profilerFilter,
          page, page_size: pageSize,
        }),
      ]);
      setAgents(a);
      setTasks(t.items);
      setTotal(t.total);
      if (t.items.length === 0 && page > 1 && t.total > 0) setPage(page - 1);
      // Merge each agent's audit trail into one recent-events feed.
      const perAgent = await Promise.all(
        a.map((ag) =>
          api
            .getAgentEvents(ag.id)
            .then((evs) => evs.map((e) => ({ ...e, agent_id: ag.id })))
            .catch(() => [])
        )
      );
      const merged = perAgent.flat().sort((x, y) => (x.created_at < y.created_at ? 1 : -1)).slice(0, 12);
      setEvents(merged);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, statusFilter, profilerFilter, page]);

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const resetPage = () => setPage(1);

  return (
    <div className="grid">
      <section className="card">
        <h2>Agents ({agents.filter((a) => a.online).length} 在线)</h2>
        <AgentTable agents={agents} />
      </section>
      <section className="card">
        <h2>新建采样</h2>
        <CreateForm agents={agents} onCreated={refresh} />
      </section>
      <section className="card span2">
        <h2>任务（共 {total} 条）</h2>
        <div className="task-filters">
          <input
            value={query}
            onChange={(e) => { setQuery(e.target.value); resetPage(); }}
            placeholder="搜索任务名称、ID或PID"
          />
          <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); resetPage(); }}>
            <option value="">全部状态</option>
            <option value="PENDING">PENDING</option>
            <option value="RUNNING">RUNNING</option>
            <option value="UPLOADING">UPLOADING</option>
            <option value="DONE">DONE</option>
            <option value="FAILED">FAILED</option>
          </select>
          <select value={profilerFilter} onChange={(e) => { setProfilerFilter(e.target.value); resetPage(); }}>
            <option value="">全部采集器</option>
            <option value="pyspy">py-spy</option>
            <option value="perf">perf</option>
            <option value="ebpf">eBPF</option>
          </select>
        </div>
        <TaskTable tasks={tasks} onChange={refresh} onRetried={() => setPage(1)} />
        <div className="pagination">
          <button className="ghost" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>上一页</button>
          <span className="muted">第 {page} / {totalPages} 页</span>
          <button className="ghost" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>下一页</button>
        </div>
      </section>
      <section className="card span2">
        <h2>Agent 审计日志</h2>
        <AuditTable events={events} />
      </section>
    </div>
  );
}

function AgentTable({ agents }: { agents: Agent[] }) {
  if (agents.length === 0) return <p className="muted">暂无 Agent，等待心跳…</p>;
  return (
    <table>
      <thead>
        <tr><th>状态</th><th>ID / 主机</th><th>IP</th><th>CPU%</th><th>RSS</th></tr>
      </thead>
      <tbody>
        {agents.map((a) => (
          <tr key={a.id}>
            <td><span className={`dot ${a.online ? "on" : "off"}`} />{a.online ? "在线" : "离线"}</td>
            <td>{a.id}<div className="muted">{a.hostname}</div></td>
            <td>{a.ip_addr}</td>
            <td>{a.self_stats?.cpu_pct ?? "-"}</td>
            <td>{a.self_stats?.rss_kb ? `${Math.round(a.self_stats.rss_kb / 1024)}MB` : "-"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CreateForm({ agents, onCreated }: { agents: Agent[]; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [pid, setPid] = useState("");
  const [duration, setDuration] = useState(10);
  const [freq, setFreq] = useState(99);
  const [profiler, setProfiler] = useState("pyspy");
  const [agentId, setAgentId] = useState("");
  const [continuous, setContinuous] = useState(false);
  const [slice, setSlice] = useState(10);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // Continuous mode is py-spy-based in this MVP.
  const effectiveProfiler = continuous ? "pyspy" : profiler;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const body: CreateTaskBody = {
        name: name.trim() || undefined,
        target_pid: effectiveProfiler === "ebpf" ? Number(pid) || 0 : Number(pid),
        duration_sec: duration,
        frequency_hz: freq,
        profiler_type: effectiveProfiler,
        mode: continuous ? "continuous" : "oneshot",
        slice_sec: slice,
        agent_id: agentId || null,
      };
      await api.createTask(body);
      setName("");
      setPid("");
      onCreated();
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit}>
      <label>任务名称（可选）</label>
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如 API CPU 排查" />
      <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <input type="checkbox" checked={continuous} style={{ width: "auto" }}
               onChange={(e) => setContinuous(e.target.checked)} />
        持续 Profiling（时间轴回看，py-spy）
      </label>
      <label>目标 PID{effectiveProfiler === "ebpf" ? "（留空/0 = 全系统）" : ""}</label>
      <input value={pid} onChange={(e) => setPid(e.target.value)}
             placeholder={effectiveProfiler === "ebpf" ? "0 = 全系统" : "例如 1234"}
             required={effectiveProfiler !== "ebpf"} />
      <div className="row">
        <div>
          <label>{continuous ? "会话时长 (秒)" : "时长 (秒)"}</label>
          <input type="number" value={duration} min={1} max={3600}
                 onChange={(e) => setDuration(Number(e.target.value))} />
        </div>
        {continuous ? (
          <div>
            <label>切片长度 (秒)</label>
            <input type="number" value={slice} min={1} max={60}
                   onChange={(e) => setSlice(Number(e.target.value))} />
          </div>
        ) : (
          <div>
            <label>采样率 (Hz)</label>
            <input type="number" value={freq} min={1} max={999}
                   onChange={(e) => setFreq(Number(e.target.value))} />
          </div>
        )}
      </div>
      <label>采集器{continuous ? "（持续模式固定 py-spy）" : ""}</label>
      <select value={effectiveProfiler} disabled={continuous}
              onChange={(e) => setProfiler(e.target.value)}>
        <option value="pyspy">py-spy（Python 语言级）</option>
        <option value="perf">perf（原生 CPU）</option>
        <option value="ebpf">eBPF（内核 syscall 延迟）</option>
      </select>
      <label>目标 Agent（留空=任意在线）</label>
      <select value={agentId} onChange={(e) => setAgentId(e.target.value)}>
        <option value="">任意</option>
        {agents.map((a) => (
          <option key={a.id} value={a.id}>{a.id} {a.online ? "" : "(离线)"}</option>
        ))}
      </select>
      <div style={{ marginTop: 12 }}>
        <button disabled={busy} type="submit">{busy ? "提交中…" : "下发采样任务"}</button>
      </div>
      {err && <p className="err" style={{ marginTop: 10 }}>{err}</p>}
    </form>
  );
}

function TaskTable({ tasks, onChange, onRetried }: {
  tasks: TaskSummary[];
  onChange: () => void;
  onRetried: () => void;
}) {
  const [actionErr, setActionErr] = useState("");
  if (tasks.length === 0) return <p className="muted">没有符合条件的任务。</p>;
  const del = async (tid: string) => {
    try {
      setActionErr("");
      await api.deleteTask(tid);
      onChange();
    } catch (e: any) {
      setActionErr(String(e.message || e));
    }
  };
  const retry = async (tid: string) => {
    try {
      setActionErr("");
      await api.retryTask(tid);
      onRetried();
      onChange();
    } catch (e: any) {
      setActionErr(String(e.message || e));
    }
  };
  return (
    <>
      {actionErr && <p className="err">{actionErr}</p>}
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>任务</th><th>PID</th><th>采集器</th><th>模式</th><th>采集状态</th>
              <th>分析状态</th><th>创建时间</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.tid}>
                <td>
                  <a href={`#/task/${t.tid}`}>{t.name || t.tid}</a>
                  {t.status === "FAILED" &&
                    <div className="failure-reason" title={t.status_reason}>{t.status_reason}</div>}
                </td>
                <td>{t.target_pid}</td>
                <td>{t.profiler_type}</td>
                <td>{t.mode === "continuous" ? "持续" : "单次"}</td>
                <td><StatusBadge status={t.status} /></td>
                <td><span className={`badge b-${t.analysis_status}`}>{t.analysis_status}</span></td>
                <td className="muted">{new Date(t.created_at).toLocaleString()}</td>
                <td><div className="actions">
                  {(t.status === "DONE" || t.status === "FAILED") &&
                    <button className="ghost" onClick={() => retry(t.tid)}>重试</button>}
                  <button className="ghost" onClick={() => del(t.tid)}>删除</button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function AuditTable({ events }: { events: (AgentEvent & { agent_id: string })[] }) {
  if (events.length === 0) return <p className="muted">暂无审计事件。</p>;
  const tone: Record<string, string> = { OFFLINE: "b-FAILED", RECOVER: "b-DONE", REGISTER: "b-RUNNING" };
  return (
    <table>
      <thead>
        <tr><th>时间</th><th>Agent</th><th>事件</th><th>详情</th></tr>
      </thead>
      <tbody>
        {events.map((e, i) => (
          <tr key={i}>
            <td className="muted">{new Date(e.created_at).toLocaleTimeString()}</td>
            <td>{e.agent_id}</td>
            <td><span className={`badge ${tone[e.event_type] || "b-NONE"}`}>{e.event_type}</span></td>
            <td className="muted">{e.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
