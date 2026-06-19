import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import type { EbpfDist } from "../types";

/** eBPF syscall-latency distribution: a log2-bucket histogram + a per-process bar. */
export function EbpfChart({ data }: { data: EbpfDist }) {
  const histRef = useRef<HTMLDivElement>(null);
  const commRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!histRef.current) return;
    const chart = echarts.init(histRef.current, "dark");
    chart.setOption({
      backgroundColor: "transparent",
      title: { text: "read/write 系统调用延迟分布 (µs)", left: "center", textStyle: { fontSize: 13 } },
      grid: { left: 8, right: 16, top: 40, bottom: 60, containLabel: true },
      tooltip: { trigger: "axis" },
      xAxis: {
        type: "category",
        data: data.latency_us.map((b) => b.bucket),
        axisLabel: { rotate: 45, fontSize: 10 },
        name: "µs bucket",
      },
      yAxis: { type: "value", name: "count" },
      series: [{ type: "bar", data: data.latency_us.map((b) => b.count), itemStyle: { color: "#38bdf8" } }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data]);

  useEffect(() => {
    if (!commRef.current) return;
    const chart = echarts.init(commRef.current, "dark");
    const rows = [...data.by_comm].slice(0, 12).reverse();
    chart.setOption({
      backgroundColor: "transparent",
      title: { text: "按进程 (read/write 次数)", left: "center", textStyle: { fontSize: 13 } },
      grid: { left: 8, right: 40, top: 40, bottom: 20, containLabel: true },
      tooltip: { trigger: "axis" },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: rows.map((r) => r.comm), axisLabel: { fontSize: 11 } },
      series: [{ type: "bar", data: rows.map((r) => r.count), itemStyle: { color: "#ff6b35" },
        label: { show: true, position: "right", fontSize: 10 } }],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [data]);

  return (
    <div>
      <div ref={histRef} style={{ width: "100%", height: 320 }} />
      <div ref={commRef} style={{ width: "100%", height: Math.max(200, data.by_comm.slice(0, 12).length * 26 + 60) }} />
    </div>
  );
}
