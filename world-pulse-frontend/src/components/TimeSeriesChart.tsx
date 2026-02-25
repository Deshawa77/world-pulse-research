import { useEffect, useRef } from "react";

type Point = {
  timestamp: string;
  value: number;
};

type Series = {
  name: string;
  points: Point[];
  color?: string;
};

type Props = {
  title: string;
  series: Series[];
  anomalies?: Point[];
  thresholdBand?: { low: number; high: number };
  className?: string;
};

export default function TimeSeriesChart({ title, series, anomalies = [], thresholdBand, className }: Props) {
  const holderRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let closed = false;
    const render = async () => {
      if (!holderRef.current) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed || !holderRef.current) return;

      const traces: any[] = series.map((s, i) => ({
        type: "scatter",
        mode: "lines",
        name: s.name,
        x: s.points.map((p) => p.timestamp),
        y: s.points.map((p) => p.value),
        line: { width: 2, color: s.color ?? ["#56d6ff", "#a3e635", "#f59e0b"][i % 3] },
      }));

      if (anomalies.length) {
        traces.push({
          type: "scatter",
          mode: "markers",
          name: "Anomalies",
          x: anomalies.map((a) => a.timestamp),
          y: anomalies.map((a) => a.value),
          marker: { color: "#ef4444", size: 8, symbol: "x" },
        });
      }

      const shapes = thresholdBand
        ? [
            {
              type: "rect",
              xref: "paper",
              x0: 0,
              x1: 1,
              y0: thresholdBand.low,
              y1: thresholdBand.high,
              fillcolor: "rgba(86,214,255,0.1)",
              line: { width: 0 },
            },
          ]
        : [];

      Plotly.react(
        holderRef.current,
        traces as any,
        {
          title,
          margin: { l: 36, r: 12, b: 26, t: 36 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: { color: "#dbeafe", size: 11 },
          shapes,
        } as any,
        { displayModeBar: false, responsive: true },
      );
    };
    render().catch(() => {
      // Keep panel usable if chart renderer fails.
    });
    return () => {
      closed = true;
    };
  }, [title, series, anomalies, thresholdBand]);

  return <div ref={holderRef} className={className ?? ""} style={{ width: "100%", height: 220 }} />;
}
