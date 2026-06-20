import { useEffect, useState } from "react";
import { api } from "../api";
import type { Artifact, Attribution, EbpfDist, TaskDetail as Task, TimelineEntry, TopN } from "../types";
import { StatusBadge } from "../App";
import { TopNChart } from "../components/TopNChart";
import { EbpfChart } from "../components/EbpfChart";
import { TimelineChart } from "../components/TimelineChart";
import { AttributionPanel } from "../components/AttributionPanel";
import { ComparisonPanel } from "../components/ComparisonPanel";

const TERMINAL = new Set(["DONE", "FAILED"]);

export function TaskDetail({ tid }: { tid: string }) {
  const [task, setTask] = useState<Task | null>(null);
  const [top, setTop] = useState<TopN | null>(null);
  const [ebpf, setEbpf] = useState<EbpfDist | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [windowSrc, setWindowSrc] = useState("");
  const [attribution, setAttribution] = useState<Attribution | null>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [error, setError] = useState("");

  const refreshArtifacts = async () => {
    try {
      setArtifacts(await api.listArtifacts(tid));
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      try {
        const t = await api.getTask(tid);
        if (stop) return;
        setTask(t);
        await refreshArtifacts();
        // Once analysis is done, fetch the result artifact (TopN or eBPF) once.
        if (t.analysis_status === "DONE" && t.result_files.topn && !top) {
          try {
            setTop(await api.getTopN(tid, t.result_files.topn));
          } catch (e) {
            console.error(e);
          }
        }
        if (t.analysis_status === "DONE" && t.result_files.ebpf && !ebpf) {
          try {
            setEbpf(await api.getEbpf(tid, t.result_files.ebpf));
          } catch (e) {
            console.error(e);
          }
        }
        // If a prior attribution was stored, load it once so the panel shows it.
        if (t.result_files.attribution && !attribution) {
          try {
            setAttribution(await api.getAttribution(tid, t.result_files.attribution));
          } catch (e) {
            console.error(e);
          }
        }
        // Continuous sessions: refresh the slice timeline each tick.
        if (t.mode === "continuous") {
          try {
            setTimeline(await api.getTimeline(tid));
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
  const isEbpf = task.profiler_type === "ebpf";
  const isContinuous = task.mode === "continuous";
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

        {isContinuous ? (
          <section className="card span2">
            <h2>持续 Profiling 时间轴（{timeline.length} 个切片）</h2>
            {timeline.length ? (
              <>
                <TimelineChart chunks={timeline} onWindow={(f, t) => setWindowSrc(api.windowUrl(task.tid, f, t))} />
                <h3 style={{ marginTop: 12 }}>窗口火焰图</h3>
                {windowSrc ? (
                  <img className="flame" src={windowSrc} alt="所选时间窗口的火焰图" />
                ) : (
                  <p className="muted">在时间轴上拖动选择窗口，点"查看此窗口火焰图"即可回看任意时段。</p>
                )}
              </>
            ) : (
              <p className="muted">采集中，等待第一个时间切片…</p>
            )}
          </section>
        ) : isEbpf ? (
          <section className="card span2">
            <h2>eBPF 内核态延迟分布{ebpf ? `（${ebpf.total_events} 次 read/write）` : ""}</h2>
            {ebpf ? (
              <EbpfChart data={ebpf} />
            ) : (
              <p className="muted">分析完成后这里会显示 bpftrace 采集的系统调用延迟分布…</p>
            )}
          </section>
        ) : (
          <>
            <section className="card span2">
              <h2>火焰图</h2>
              {flameName ? (
                <img
                  className="flame"
                  src={api.artifactUrl(task.tid, flameName)}
                  alt={`${task.name || task.tid} 火焰图`}
                />
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

            {task.analysis_status === "DONE" && (
              <section className="card span2">
                <h2>🧪 可验证性能优化闭环</h2>
                <ComparisonPanel candidate={task} onCompleted={refreshArtifacts} />
              </section>
            )}

            {task.analysis_status === "DONE" && (
              <section className="card span2">
                <h2>🤖 智能归因（AI）</h2>
                <AttributionPanel tid={task.tid} initial={attribution} onCompleted={refreshArtifacts} />
              </section>
            )}
          </>
        )}

        <section className="card span2">
          <h2>任务产物（{artifacts.length} 个文件）</h2>
          {artifacts.length ? (
            <div className="table-scroll">
              <table>
                <thead><tr><th>类型</th><th>文件</th><th>大小</th><th>操作</th></tr></thead>
                <tbody>
                  {artifacts.map((artifact) => {
                    const viewable = artifact.content_type.startsWith("text/") ||
                      artifact.content_type.startsWith("image/") || artifact.content_type === "application/json";
                    return (
                      <tr key={artifact.path}>
                        <td>{artifact.logical_name || artifact.content_type}</td>
                        <td><code>{artifact.path}</code></td>
                        <td>{formatBytes(artifact.size_bytes)}</td>
                        <td><div className="actions">
                          {viewable &&
                            <a href={api.artifactUrl(task.tid, artifact.path)} target="_blank" rel="noreferrer">查看</a>}
                          <a href={api.artifactUrl(task.tid, artifact.path, true)}>下载</a>
                        </div></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <p className="muted">任务产物生成后会显示在这里。</p>}
        </section>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
