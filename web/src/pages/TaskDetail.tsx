import { useEffect, useState } from "react";
import { api } from "../api";
import type { TaskDetail as Task, TopN } from "../types";
import { StatusBadge } from "../App";
import { TopNChart } from "../components/TopNChart";

const TERMINAL = new Set(["DONE", "FAILED"]);

export function TaskDetail({ tid }: { tid: string }) {
  const [task, setTask] = useState<Task | null>(null);
  const [top, setTop] = useState<TopN | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const t = await api.getTask(tid);
        if (stop) return;
        setTask(t);
        // Once analysis is done, fetch the TopN json once.
        if (t.analysis_status === "DONE" && t.result_files.topn && !top) {
          try {
            setTop(await api.getTopN(tid, t.result_files.topn));
          } catch (e) {
            console.error(e);
          }
        }
        // Stop polling when both collection and analysis have settled.
        if (TERMINAL.has(t.status) && (t.analysis_status === "DONE" || t.analysis_status === "FAILED" || t.status === "FAILED")) {
          clearInterval(id);
        }
      } catch (e: any) {
        setError(String(e.message || e));
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      stop = true;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tid]);

  if (error) return <div><a className="back" href="#/">← 返回</a><p className="err">{error}</p></div>;
  if (!task) return <p className="muted">加载中…</p>;

  const flameName = task.result_files.flamegraph;
  return (
    <div>
      <p><a className="back" href="#/">← 返回任务列表</a></p>
      <div className="grid">
        <section className="card">
          <h2>基本信息</h2>
          <table>
            <tbody>
              <tr><th>任务 ID</th><td>{task.tid}</td></tr>
              <tr><th>名称</th><td>{task.name}</td></tr>
              <tr><th>目标 PID</th><td>{task.target_pid}</td></tr>
              <tr><th>采集器</th><td>{task.profiler_type}</td></tr>
              <tr><th>时长 / 采样率</th><td>{task.duration_sec}s @ {task.frequency_hz}Hz</td></tr>
              <tr><th>Agent</th><td>{task.agent_id || "-"}</td></tr>
              <tr><th>采集状态</th><td><StatusBadge status={task.status} /> <span className="muted">{task.status_reason}</span></td></tr>
              <tr><th>分析状态</th><td><span className={`badge b-${task.analysis_status}`}>{task.analysis_status}</span> <span className="muted">{task.analysis_reason}</span></td></tr>
            </tbody>
          </table>
          {task.error_message && <p className="err" style={{ marginTop: 10 }}>{task.error_message}</p>}
        </section>

        <section className="card">
          <h2>状态时间线</h2>
          <ul className="timeline">
            {task.transitions.map((tr, i) => (
              <li key={i}>
                <span className="muted">{new Date(tr.created_at).toLocaleTimeString()} </span>
                {tr.from_status ? `${tr.from_status} → ` : ""}<b>{tr.to_status}</b>
                <div className="muted">{tr.reason}</div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card span2">
          <h2>火焰图</h2>
          {flameName ? (
            <iframe className="flame" src={api.artifactUrl(task.tid, flameName)} title="flamegraph" />
          ) : (
            <p className="muted">分析完成后这里会显示火焰图…</p>
          )}
        </section>

        {top && (
          <section className="card span2">
            <h2>热点 Top{top.top.length}（共 {top.total_samples} 样本 / {top.unique_stacks} 条栈）</h2>
            <TopNChart data={top} />
          </section>
        )}
      </div>
    </div>
  );
}
