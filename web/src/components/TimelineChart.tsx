import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";
import type { TimelineEntry } from "../types";

/**
 * Continuous-profiling timeline: samples per slice over wall-clock time, with a draggable
 * window (dataZoom). "查看此窗口火焰图" renders the flamegraph for the selected [from,to].
 */
export function TimelineChart({
  chunks,
  onWindow,
}: {
  chunks: TimelineEntry[];
  onWindow: (from: number, to: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const [range, setRange] = useState<[number, number] | null>(null);

  useEffect(() => {
    if (!ref.current || chunks.length === 0) return;
    const chart = chartRef.current ?? echarts.init(ref.current, "dark");
    chartRef.current = chart;

    const points = chunks.map((c) => [Math.round(((c.start_ts + c.end_ts) / 2) * 1000), c.samples]);
    const minTs = chunks[0].start_ts;
    const maxTs = chunks[chunks.length - 1].end_ts;

    chart.setOption({
      backgroundColor: "transparent",
      tooltip: { trigger: "axis", formatter: (p: any) => `${new Date(p[0].value[0]).toLocaleTimeString()}<br/>${p[0].value[1]} samples` },
      grid: { left: 8, right: 16, top: 16, bottom: 70, containLabel: true },
      xAxis: { type: "time", name: "time" },
      yAxis: { type: "value", name: "samples/slice" },
      dataZoom: [
        { type: "slider", xAxisIndex: 0, height: 28, bottom: 16 },
        { type: "inside", xAxisIndex: 0 },
      ],
      series: [{ type: "bar", data: points, itemStyle: { color: "#a78bfa" }, barMaxWidth: 24 }],
    });

    const readRange = () => {
      const opt: any = chart.getOption();
      const dz = opt.dataZoom?.[0] ?? {};
      const fromMs = dz.startValue ?? minTs * 1000;
      const toMs = dz.endValue ?? maxTs * 1000;
      setRange([Math.floor(fromMs / 1000), Math.ceil(toMs / 1000)]);
    };
    chart.off("dataZoom");
    chart.on("dataZoom", readRange);
    readRange();

    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [chunks]);

  useEffect(() => () => chartRef.current?.dispose(), []);

  const fmt = (s: number) => new Date(s * 1000).toLocaleTimeString();
  return (
    <div>
      <div ref={ref} style={{ width: "100%", height: 240 }} />
      <div className="row" style={{ alignItems: "center", marginTop: 8 }}>
        <span className="muted">
          选中窗口：{range ? `${fmt(range[0])} – ${fmt(range[1])}` : "全部"}
        </span>
        <button
          style={{ flex: "0 0 auto" }}
          onClick={() => range && onWindow(range[0], range[1])}
        >
          查看此窗口火焰图
        </button>
      </div>
    </div>
  );
}
