import { useEffect, useState } from "react";
import { api } from "../api";
import type { Attribution, AttributionEngine } from "../types";

// AI smart attribution panel: runs the constrained tool-calling analyst on demand,
// shows the ranked root-cause findings, and — crucially — the verification report
// that independently re-checks every number against the raw profile.
export function AttributionPanel({ tid, initial, onCompleted }: {
  tid: string;
  initial: Attribution | null;
  onCompleted?: () => void | Promise<void>;
}) {
  const [attr, setAttr] = useState<Attribution | null>(initial);
  const [engine, setEngine] = useState<AttributionEngine>(initial?.engine === "deepseek" ? "deepseek" : "offline");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (initial) {
      setAttr(initial);
      setEngine(initial.engine === "deepseek" ? "deepseek" : "offline");
    }
  }, [initial]);

  const run = async () => {
    setBusy(true);
    setErr("");
    try {
      setAttr(await api.runAttribution(tid, engine));
      await onCompleted?.();
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const controls = (
    <div className="attr-controls">
      <label>
        归因方式
        <select
          value={engine}
          disabled={busy}
          onChange={(e) => setEngine(e.target.value as AttributionEngine)}
        >
          <option value="offline">离线归因（无外部请求）</option>
          <option value="deepseek">DeepSeek 归因（需要 API Key）</option>
        </select>
      </label>
      <button disabled={busy} onClick={run}>
        {busy ? "归因分析中…" : attr ? "按所选方式重新归因" : "运行智能归因"}
      </button>
    </div>
  );

  if (!attr) {
    return (
      <div>
        <p className="muted">
          离线归因在本机按固定规则分析热点；DeepSeek 只通过自定义只读工具访问 profile。
          两种方式都会对结论中的函数和自耗时比例进行独立校验。
        </p>
        {controls}
        {err && <p className="err" style={{ marginTop: 10 }}>{err}</p>}
      </div>
    );
  }

  const v = attr.verification;
  const engineLabel = attr.engine === "deepseek"
    ? `DeepSeek (${attr.model || "deepseek-chat"})`
    : "离线归因（确定性规则）";

  return (
    <div>
      <div className="attr-head">
        <span className={`badge ${attr.engine === "deepseek" ? "b-RUNNING" : "b-NONE"}`}>引擎：{engineLabel}</span>
        <span className={`badge ${v.failed === 0 ? "b-DONE" : "b-FAILED"}`}>
          校验 {v.verified}/{v.total_findings} 通过（{v.pass_rate}%）
        </span>
      </div>
      {controls}
      {err && <p className="err" style={{ marginTop: 10 }}>{err}</p>}

      <p style={{ marginTop: 10 }}><b>诊断：</b>{attr.summary}</p>

      <h3 style={{ marginTop: 14 }}>根因（按自耗时排序）</h3>
      <ol className="findings">
        {attr.findings.map((f, i) => {
          const chk = v.checks.find((c) => c.function === f.function);
          const ok = chk?.verdict === "pass";
          return (
            <li key={i}>
              <div>
                <code>{f.function}</code>
                <span className="muted"> — 自耗时 {f.self_pct}%</span>
                <span className={`badge ${ok ? "b-DONE" : "b-FAILED"}`} style={{ marginLeft: 8 }}>
                  {ok ? "已校验" : "校验未通过"}
                </span>
              </div>
              <div className="muted" style={{ marginTop: 2 }}>证据：{f.evidence}</div>
              <div style={{ marginTop: 2 }}>建议：{f.recommendation}</div>
              {chk && !ok && <div className="err" style={{ marginTop: 2 }}>校验：{chk.note}</div>}
            </li>
          );
        })}
      </ol>

      <details style={{ marginTop: 12 }}>
        <summary className="muted">校验报告 + 工具调用轨迹（防幻觉证据链）</summary>
        <h4 style={{ marginTop: 10 }}>逐条校验（容差 ±{v.tolerance_pct}%）</h4>
        <table>
          <thead><tr><th>函数</th><th>声明 %</th><th>实测 %</th><th>结论</th><th>说明</th></tr></thead>
          <tbody>
            {v.checks.map((c, i) => (
              <tr key={i}>
                <td><code>{c.function}</code></td>
                <td>{c.claimed_self_pct ?? "-"}</td>
                <td>{c.actual_self_pct ?? "-"}</td>
                <td><span className={`badge ${c.verdict === "pass" ? "b-DONE" : "b-FAILED"}`}>{c.verdict}</span></td>
                <td className="muted">{c.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <h4 style={{ marginTop: 10 }}>工具调用轨迹（归因引擎对 profile 的访问证据）</h4>
        <ul className="timeline">
          {attr.tool_trace.map((t, i) => (
            <li key={i}><code>{t.tool}</code> <span className="muted">{JSON.stringify(t.input)}</span></li>
          ))}
        </ul>
      </details>
    </div>
  );
}
