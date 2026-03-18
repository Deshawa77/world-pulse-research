import { useMemo } from "react";

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

type NormalizedPoint = Point & { time: number };

const CHART_HEIGHT = 280;
const CHART_WIDTH = 720;
const PADDING = { top: 28, right: 18, bottom: 34, left: 42 };
const SERIES_COLORS = ["#22d3ee", "#34d399", "#f59e0b", "#f472b6"];

function normalizePoints(points: Point[]): NormalizedPoint[] {
  const rows = points
    .map((point) => ({
      timestamp: point.timestamp,
      value: Number(point.value),
      time: new Date(point.timestamp).getTime(),
    }))
    .filter((point) => Number.isFinite(point.value) && Number.isFinite(point.time))
    .sort((left, right) => left.time - right.time);

  if (rows.length >= 2) return rows;
  if (rows.length === 1) {
    return [
      { ...rows[0], time: rows[0].time - 60 * 60 * 1000, timestamp: new Date(rows[0].time - 60 * 60 * 1000).toISOString() },
      rows[0],
    ];
  }

  const now = Date.now();
  return [
    { timestamp: new Date(now - 60 * 60 * 1000).toISOString(), value: 50, time: now - 60 * 60 * 1000 },
    { timestamp: new Date(now).toISOString(), value: 50, time: now },
  ];
}

function formatTickLabel(time: number, detailed: boolean): string {
  const date = new Date(time);
  if (detailed) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function pathFromPoints(points: Array<{ x: number; y: number }>): string {
  if (!points.length) return "";
  return points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
}

export default function TimeSeriesChart({ title, series, anomalies = [], thresholdBand, className }: Props) {
  const model = useMemo(() => {
    const normalizedSeries = series.map((entry, index) => ({
      name: entry.name,
      color: entry.color ?? SERIES_COLORS[index % SERIES_COLORS.length],
      points: normalizePoints(entry.points ?? []),
    }));

    const allPoints = normalizedSeries.flatMap((entry) => entry.points);
    const anomalyPoints = anomalies
      .map((point) => ({ ...point, time: new Date(point.timestamp).getTime() }))
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.value));

    const minTime = Math.min(...allPoints.map((point) => point.time));
    const maxTime = Math.max(...allPoints.map((point) => point.time));
    const timeSpan = Math.max(maxTime - minTime, 1);

    const values = [...allPoints.map((point) => point.value), ...anomalyPoints.map((point) => point.value)];
    const rawMin = values.length ? Math.min(...values) : 50;
    const rawMax = values.length ? Math.max(...values) : 50;
    const spread = Math.max(rawMax - rawMin, 1);
    const minValue = Math.max(0, rawMin - Math.max(3, spread * 0.25));
    const maxValue = Math.min(100, rawMax + Math.max(3, spread * 0.25));
    const valueSpan = Math.max(maxValue - minValue, 1);

    const innerWidth = CHART_WIDTH - PADDING.left - PADDING.right;
    const innerHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;

    const scaleX = (time: number) => PADDING.left + ((time - minTime) / timeSpan) * innerWidth;
    const scaleY = (value: number) => PADDING.top + (1 - (value - minValue) / valueSpan) * innerHeight;

    const yTicks = Array.from({ length: 5 }, (_, index) => {
      const value = minValue + (valueSpan / 4) * index;
      return { value, y: scaleY(value) };
    });

    const detailedTicks = new Set(allPoints.map((point) => new Date(point.time).toDateString())).size <= 1;
    const xTicks = Array.from({ length: 4 }, (_, index) => {
      const time = minTime + (timeSpan / 3) * index;
      return { time, x: scaleX(time), label: formatTickLabel(time, detailedTicks) };
    });

    const plotTop = PADDING.top;
    const plotBottom = CHART_HEIGHT - PADDING.bottom;
    const clampedThresholdTop = thresholdBand ? Math.max(plotTop, Math.min(plotBottom, scaleY(thresholdBand.high))) : null;
    const clampedThresholdBottom = thresholdBand ? Math.max(plotTop, Math.min(plotBottom, scaleY(thresholdBand.low))) : null;
    const showThresholdBand = thresholdBand
      ? thresholdBand.high >= minValue && thresholdBand.low <= maxValue && clampedThresholdBottom !== null && clampedThresholdTop !== null && clampedThresholdBottom > clampedThresholdTop
      : false;

    return {
      normalizedSeries: normalizedSeries.map((entry) => ({
        ...entry,
        scaled: entry.points.map((point) => ({ ...point, x: scaleX(point.time), y: scaleY(point.value) })),
      })),
      anomalyPoints: anomalyPoints.map((point) => ({ ...point, x: scaleX(point.time), y: scaleY(point.value) })),
      yTicks,
      xTicks,
      thresholdTop: clampedThresholdTop,
      thresholdBottom: clampedThresholdBottom,
      showThresholdBand,
      innerWidth,
      innerHeight,
    };
  }, [anomalies, series, thresholdBand]);

  const showLegend = model.normalizedSeries.length + (model.anomalyPoints.length ? 1 : 0) > 1;

  return (
    <div className={className} style={{ width: "100%" }}>
      {showLegend ? (
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap", marginBottom: 12, color: "#dbeafe", fontSize: 12 }}>
          {model.normalizedSeries.map((entry) => (
            <span key={entry.name} style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 22, height: 3, borderRadius: 999, background: entry.color }} />
              {entry.name}
            </span>
          ))}
          {model.anomalyPoints.length ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <span style={{ color: "#ff5d4d", fontWeight: 700, fontSize: 16, lineHeight: 1 }}>?</span>
              Anomalies
            </span>
          ) : null}
        </div>
      ) : null}

      <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} style={{ width: "100%", height: CHART_HEIGHT, display: "block" }} aria-label={title}>
        <rect x="0" y="0" width={CHART_WIDTH} height={CHART_HEIGHT} rx="18" fill="rgba(6, 12, 24, 0.28)" />

        {model.showThresholdBand && model.thresholdTop !== null && model.thresholdBottom !== null ? (
          <>
            <rect
              x={PADDING.left}
              y={model.thresholdTop}
              width={model.innerWidth}
              height={Math.max(0, model.thresholdBottom - model.thresholdTop)}
              fill="rgba(34, 211, 238, 0.08)"
            />
            <line x1={PADDING.left} x2={CHART_WIDTH - PADDING.right} y1={model.thresholdTop} y2={model.thresholdTop} stroke="rgba(125, 211, 252, 0.22)" strokeDasharray="4 4" />
            <line x1={PADDING.left} x2={CHART_WIDTH - PADDING.right} y1={model.thresholdBottom} y2={model.thresholdBottom} stroke="rgba(125, 211, 252, 0.22)" strokeDasharray="4 4" />
          </>
        ) : null}

        {model.yTicks.map((tick) => (
          <g key={`y-${tick.value}`}>
            <line x1={PADDING.left} x2={CHART_WIDTH - PADDING.right} y1={tick.y} y2={tick.y} stroke="rgba(71, 85, 105, 0.22)" />
            <text x={PADDING.left - 8} y={tick.y + 4} fill="#94a3b8" fontSize="11" textAnchor="end">{tick.value.toFixed(0)}</text>
          </g>
        ))}

        {model.xTicks.map((tick) => (
          <g key={`x-${tick.time}`}>
            <line x1={tick.x} x2={tick.x} y1={PADDING.top} y2={CHART_HEIGHT - PADDING.bottom} stroke="rgba(71, 85, 105, 0.14)" />
            <text x={tick.x} y={CHART_HEIGHT - 10} fill="#94a3b8" fontSize="11" textAnchor="middle">{tick.label}</text>
          </g>
        ))}

        {model.normalizedSeries.map((entry) => (
          <g key={entry.name}>
            <path d={pathFromPoints(entry.scaled)} fill="none" stroke={entry.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
            {entry.scaled.map((point, index) => (
              <circle key={`${entry.name}-${index}`} cx={point.x} cy={point.y} r="4" fill={entry.color} />
            ))}
          </g>
        ))}

        {model.anomalyPoints.map((point, index) => (
          <g key={`anomaly-${index}`} transform={`translate(${point.x}, ${point.y})`}>
            <line x1={-5} x2={5} y1={-5} y2={5} stroke="#ff5d4d" strokeWidth="3" strokeLinecap="round" />
            <line x1={-5} x2={5} y1={5} y2={-5} stroke="#ff5d4d" strokeWidth="3" strokeLinecap="round" />
          </g>
        ))}
      </svg>
    </div>
  );
}
