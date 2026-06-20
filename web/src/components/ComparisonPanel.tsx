import { useEffect, useState } from "react";
import { api } from "../api";
import type { PerformanceComparison, TaskDetail, TaskSummary } from "../types";
import { ComparisonChart } from "./ComparisonChart";

const verdictLabel: Record<PerformanceComparison["verdict"], string> = {
  hotspot_reduced: "主要热点占比下降",
  hotspot_increased: "主要热点占比上升",
  no_clear_change: "未发现明显变化",
  no_data: "无可比较数据",
};

export function ComparisonPanel({ candidate, onCompleted }: {
  candidate: TaskDetail;
  onCompleted?: () => void | Promise<void>;
}) {
  const [baselines, setBaselines] = useState<TaskSummary[]>([]);
  const [baselineTid, setBaselineTid] = useState("");
  const [comparison, setComparison] = useState<PerformanceComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.listTasks({ status: "DONE", profiler_type: candidate.profiler_type, page: 1, page_size: 100 })
      .then((page) => {
        const eligible = page.items.filter((task) => task.tid !== candidate.tid && task.analysis_status === "DONE");
        setBaselines(eligible);
        setBaselineTid((current) => current || eligible[0]?.tid || "");
      })
      .catch((e) => setErr(String(e.message || e)));
  }, [candidate.tid, candidate.profiler_type]);

  const run = async () => {
    if (!baselineTid) return;
    setBusy(true);
    setErr("");
    try {
      setComparison(await api.compareTasks(candidate.tid, baselineTid));
      await onCompleted?.();
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const badgeClass = comparison?.verdict === "hotspot_reduced" ? "b-DONE" :
    comparison?.verdict === "hotspot_increased" ? "b-FAILED" : "b-NONE";

  return (
    <div>
      <p className="muted">
        当前任务作为“优化后”，选择一个同采集器的已完成任务作为“优化前”。系统会比较真实profile、生成差分火焰图，并独立复算每个数值。
      </p>
      <div className="comparison-controls">
        <label>
          优化前（基线任务）
          <select value={baselineTid} disabled={busy} onChange={(e) => setBaselineTid(e.target.value)}>
            {baselines.length === 0 && <option value="">暂无可用基线任务</option>}
            {baselines.map((task) => (
              <option key={task.tid} value={task.tid}>
                {task.name || task.tid} · PID {task.target_pid} · {new Date(task.created_at).toLocaleString()}
              </option>
            ))}
          </select>
        </label>
        <div className="candidate-box">
          <span className="muted">优化后（当前任务）</span>
          <b>{candidate.name || candidate.tid}</b>
        </div>
        <button disabled={busy || !baselineTid} onClick={run}>{busy ? "正在复算…" : "生成可验证效果报告"}</button>
      </div>
      {err && <p className="err" style={{ marginTop: 10 }}>{err}</p>}

      {comparison && (
        <div className="comparison-result">
          <div className="attr-head">
            <span className={`badge ${badgeClass}`}>{verdictLabel[comparison.verdict]}</span>
            <span className="badge b-DONE">
              校验 {comparison.verification.verified}/{comparison.verification.total}（{comparison.verification.pass_rate}%）
            </span>
            <span className="badge b-NONE">置信度：{comparison.confidence}</span>
          </div>
          <p><b>效果结论：</b>{comparison.summary}</p>
          <p className="muted">
            样本：优化前 {comparison.baseline.total_samples}，优化后 {comparison.candidate.total_samples}；
            改善 {comparison.counts.improved} 项，恶化 {comparison.counts.regressed} 项，稳定 {comparison.counts.stable} 项。
          </p>

          <h3>热点占比差分</h3>
          <ComparisonChart rows={comparison.functions} />

          <h3>差分火焰图</h3>
          <img className="flame comparison-flame" src={api.artifactUrl(candidate.tid, comparison.artifacts.diff_flamegraph)} alt="优化前后差分火焰图" />

          <details style={{ marginTop: 12 }}>
            <summary className="muted">查看逐函数数据和独立校验</summary>
            <div className="table-scroll">
              <table>
                <thead><tr><th>函数</th><th>优化前</th><th>优化后</th><th>变化</th><th>状态</th><th>校验</th></tr></thead>
                <tbody>{comparison.functions.map((row) => {
                  const check = comparison.verification.checks.find((item) => item.function === row.function);
                  return <tr key={row.function}>
                    <td><code>{row.function}</code></td>
                    <td>{row.baseline_pct}%</td><td>{row.candidate_pct}%</td>
                    <td>{row.delta_pct > 0 ? "+" : ""}{row.delta_pct}pp</td>
                    <td>{row.status}</td>
                    <td><span className={`badge ${check?.verdict === "pass" ? "b-DONE" : "b-FAILED"}`}>{check?.verdict}</span></td>
                  </tr>;
                })}</tbody>
              </table>
            </div>
          </details>
          {comparison.limitations.map((note) => <p className="muted comparison-note" key={note}>注：{note}</p>)}
        </div>
      )}
    </div>
  );
}
