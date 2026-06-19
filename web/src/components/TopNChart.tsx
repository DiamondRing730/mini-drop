import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { TopN } from "../types";

/** Horizontal bar chart of the hottest functions by self-sample percentage. */
export function TopNChart({ data }: { data: TopN }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current, "dark");
    const rows = [...data.top].reverse(); // ECharts y-axis renders bottom-up
    chart.setOption({
      backgroundColor: "transparent",
      grid: { left: 8, right: 40, top: 10, bottom: 20, containLabel: true },
      tooltip: {
        trigger: "axis",
        formatter: (p: any) => {
          const d = p[0];
          const item = rows[d.dataIndex];
          return `${item.func}<br/>self: ${item.self} (${item.self_pct}%)`;
        },
      },
      xAxis: { type: "value", name: "self %" },
      yAxis: {
        type: "category",
        data: rows.map((r) => (r.func.length > 28 ? r.func.slice(0, 27) + "…" : r.func)),
        axisLabel: { fontSize: 11 },
      },
      series: [
        {
          type: "bar",
          data: rows.map((r) => r.self_pct),
          itemStyle: { color: "#ff6b35" },
          label: { show: true, position: "right", formatter: "{c}%", fontSize: 10 },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data]);

  return <div ref={ref} style={{ width: "100%", height: Math.max(220, data.top.length * 26) }} />;
}
