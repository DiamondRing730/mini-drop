import { useEffect, useState, type FormEvent } from "react";
import { api, type CreateTaskBody } from "../api";
import type { Agent, AgentEvent, TaskSummary } from "../types";
import { StatusBadge } from "../App";

export function Home() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tasks, setTasks] = useState<TaskSummary[]>([]);
  const [events, setEvents] = useState<(AgentEvent & { agent_id: string })[]>([]);

  const refresh = async () => {
    try {
      const [a, t] = await Promise.all([api.listAgents(), api.listTasks()]);
      setAgents(a);
      setTasks(t);
      // Merge each agent's audit trail into one recent-events feed.
      const perAgent = await Promise.all(
        a.map((ag) => api.getAgentEvents(ag.id).then((evs) => evs.map((e) => ({ ...e, agent_id: ag.id }))).catch(() => []))
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
  }, []);

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
        <h2>任务 ({tasks.length})</h2>
        <TaskTable tasks={tasks} onChange={refresh} />
      </section>
      <section className="card span2">
        <h2>Agent 审计日志</h2>
        <AuditTable events={events} />
      </section>
    </div>
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
  const [pid, setPid] = useState("");
  const [duration, setDuration] = useState(10);
  const [freq, setFreq] = useState(99);
  const [profiler, setProfiler] = useState("pyspy");
  const [agentId, setAgentId] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr("");
    setBusy(true);
    try {
      const body: CreateTaskBody = {
        target_pid: Number(pid),
        duration_sec: duration,
        frequency_hz: freq,
        profiler_type: profiler,
        agent_id: agentId || null,
      };
      await api.createTask(body);
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
      <label>目标 PID</label>
      <input value={pid} onChange={(e) => setPid(e.target.value)} placeholder="例如 1234" required />
      <div className="row">
        <div>
          <label>时长 (秒)</label>
          <input type="number" value={duration} min={1} max={600}
                 onChange={(e) => setDuration(Number(e.target.value))} />
        </div>
        <div>
          <label>采样率 (Hz)</label>
          <input type="number" value={freq} min={1} max={999}
                 onChange={(e) => setFreq(Number(e.target.value))} />
        </div>
      </div>
      <label>采集器</label>
      <select value={profiler} onChange={(e) => setProfiler(e.target.value)}>
        <option value="pyspy">py-spy（Python 语言级）</option>
        <option value="perf">perf（原生 CPU）</option>
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

function TaskTable({ tasks, onChange }: { tasks: TaskSummary[]; onChange: () => void }) {
  if (tasks.length === 0) return <p className="muted">还没有任务，去左侧新建一个。</p>;
  const del = async (tid: string) => {
    await api.deleteTask(tid);
    onChange();
  };
  return (
    <table>
      <thead>
        <tr>
          <th>任务</th><th>PID</th><th>采集器</th><th>采集状态</th>
          <th>分析状态</th><th>创建时间</th><th></th>
        </tr>
      </thead>
      <tbody>
        {tasks.map((t) => (
          <tr key={t.tid}>
            <td><a href={`#/task/${t.tid}`}>{t.name || t.tid}</a></td>
            <td>{t.target_pid}</td>
            <td>{t.profiler_type}</td>
            <td><StatusBadge status={t.status} /></td>
            <td><span className={`badge b-${t.analysis_status}`}>{t.analysis_status}</span></td>
            <td className="muted">{new Date(t.created_at).toLocaleString()}</td>
            <td><button className="ghost" onClick={() => del(t.tid)}>删除</button></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
