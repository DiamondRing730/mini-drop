import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { ComparisonFunction } from "../types";

export function ComparisonChart({ rows }: { rows: ComparisonFunction[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, "dark");
    const shown = [...rows].slice(0, 10).reverse();
    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 8, right: 55, top: 20, bottom: 30, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (items: any) => {
          const row = shown[items[0].dataIndex];
          return `${row.function}<br/>优化前 ${row.baseline_pct}%<br/>优化后 ${row.candidate_pct}%<br/>变化 ${row.delta_pct > 0 ? "+" : ""}${row.delta_pct}pp`;
        },
      },
      xAxis: { type: "value", name: "Δ self pp", axisLine: { show: true }, splitLine: { lineStyle: { color: "#343846" } } },
      yAxis: {
        type: "category",
        data: shown.map((r) => r.function.length > 30 ? `${r.function.slice(0, 29)}…` : r.function),
        axisLabel: { fontSize: 11 },
      },
      series: [{
        type: "bar",
        data: shown.map((row) => ({
          value: row.delta_pct,
          itemStyle: { color: row.status === "improved" ? "#22c55e" : row.status === "regressed" ? "#ef4444" : "#94a3b8" },
        })),
        label: {
          show: true,
          position: "right",
          formatter: (p: any) => `${p.value > 0 ? "+" : ""}${p.value}pp`,
          fontSize: 10,
        },
        markLine: { silent: true, symbol: "none", data: [{ xAxis: 0 }], lineStyle: { color: "#e5e7eb" } },
      }],
    });
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [rows]);

  return <div ref={ref} style={{ width: "100%", height: Math.max(260, Math.min(rows.length, 10) * 30) }} />;
}
