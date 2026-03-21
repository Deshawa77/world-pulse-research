import { useEffect, useRef, useMemo } from "react";
import * as echarts from "echarts";

interface CorrelationData {
  features: Record<string, number>;
  timestamp: string;
}

interface RiskCorrelationMatrixProps {
  data: CorrelationData[];
  height?: number;
}

const FEATURE_DEFS = [
  { key: "news_sentiment", label: "News Sentiment" },
  { key: "gdelt_sentiment", label: "GDELT Sentiment" },
  { key: "direct_behavior_score", label: "Direct Behavior" },
  { key: "contextual_pressure_score", label: "Context Pressure" },
  { key: "evidence_quality_score", label: "Evidence Quality" },
  { key: "narrative_velocity_score", label: "Narrative Velocity" },
  { key: "coordination_risk_score", label: "Coordination Risk" },
  { key: "mobility_disruption_score", label: "Mobility Disruption" },
  { key: "logistics_stress_score", label: "Logistics Stress" },
  { key: "household_stress_score", label: "Household Stress" },
  { key: "energy_stress_score", label: "Energy Stress" },
  { key: "global_risk_score", label: "Global Risk" },
];

const FEATURE_KEYS = FEATURE_DEFS.map((item) => item.key);
const FEATURE_LABELS: Record<string, string> = Object.fromEntries(FEATURE_DEFS.map((item) => [item.key, item.label]));

export default function RiskCorrelationMatrix({ data, height = 400 }: RiskCorrelationMatrixProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);
  // Calculate correlation matrix
  const correlationMatrix = useMemo(() => {
    if (!data || data.length < 2) return null;

    const featureData: Record<string, number[]> = {};
    FEATURE_KEYS.forEach((key) => {
      featureData[key] = [];
    });

    // Extract feature values
    data.forEach((d) => {
      FEATURE_KEYS.forEach((key) => {
        const features = d.features as Record<string, number>;
        const value = features[key] ?? 0;
        featureData[key].push(typeof value === "number" ? value : 0);
      });
    });

    // Calculate correlation matrix
    const matrix: number[][] = [];
    for (let i = 0; i < FEATURE_KEYS.length; i++) {
      const row: number[] = [];
      for (let j = 0; j < FEATURE_KEYS.length; j++) {
        const correlation = calculateCorrelation(
          featureData[FEATURE_KEYS[i]],
          featureData[FEATURE_KEYS[j]]
        );
        row.push(correlation);
      }
      matrix.push(row);
    }

    return matrix;
  }, [data]);

  function calculateCorrelation(x: number[], y: number[]): number {
    if (x.length !== y.length || x.length === 0) return Number.NaN;

    const n = x.length;
    const sumX = x.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumXY = x.reduce((total, xi, i) => total + xi * y[i], 0);
    const sumX2 = x.reduce((total, xi) => total + xi * xi, 0);
    const sumY2 = y.reduce((total, yi) => total + yi * yi, 0);

    const numerator = n * sumXY - sumX * sumY;
    const denominator = Math.sqrt(
      (n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY)
    );

    if (denominator === 0) return Number.NaN;
    return numerator / denominator;
  }

  useEffect(() => {
    if (!chartRef.current || !correlationMatrix) return;

    // Initialize chart
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }

    const chart = chartInstanceRef.current;

    // Prepare heatmap data
    const heatmapData: [number, number, number][] = [];
    for (let i = 0; i < FEATURE_KEYS.length; i++) {
      for (let j = 0; j < FEATURE_KEYS.length; j++) {
        heatmapData.push([j, i, correlationMatrix[i][j]]);
      }
    }

    const option: echarts.EChartsOption = {
      tooltip: {
        position: "top",
        formatter: (params: any) => {
          const xLabel = FEATURE_LABELS[FEATURE_KEYS[params.data[1]]];
          const yLabel = FEATURE_LABELS[FEATURE_KEYS[params.data[0]]];
          const corr = params.data[2];
          if (!Number.isFinite(corr)) {
            return `<strong>${xLabel}</strong> vs <strong>${yLabel}</strong><br/>Correlation: N/A (insufficient variance)`;
          }
          return `<strong>${xLabel}</strong> vs <strong>${yLabel}</strong><br/>Correlation: ${corr.toFixed(3)}`;
        },
      },
      grid: {
        left: "120px",
        right: "20px",
        top: "20px",
        bottom: "80px",
      },
      xAxis: {
        type: "category",
        data: FEATURE_KEYS.map((k) => FEATURE_LABELS[k]),
        axisLabel: {
          rotate: 45,
          color: "#888",
          fontSize: 10,
        },
        axisLine: {
          lineStyle: {
            color: "#333",
          },
        },
      },
      yAxis: {
        type: "category",
        data: FEATURE_KEYS.map((k) => FEATURE_LABELS[k]),
        axisLabel: {
          color: "#888",
          fontSize: 10,
        },
        axisLine: {
          lineStyle: {
            color: "#333",
          },
        },
      },
      visualMap: {
        min: -1,
        max: 1,
        calculable: true,
        orient: "horizontal",
        left: "center",
        bottom: "0px",
        inRange: {
          color: ["#ef4444", "#facc15", "#22c55e", "#facc15", "#ef4444"],
        },
        textStyle: {
          color: "#888",
        },
      },
      series: [
        {
          type: "heatmap",
          data: heatmapData,
          label: {
            show: true,
            formatter: (params: any) => {
              const corr = params.data[2];
              return Number.isFinite(corr) ? corr.toFixed(2) : "N/A";
            },
            color: "#fff",
            fontSize: 9,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(0, 0, 0, 0.5)",
            },
          },
        },
      ],
    };

    chart.setOption(option);

    // Handle resize
    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [correlationMatrix]);

  // Find strongest correlations
  const strongestCorrelations = useMemo(() => {
    if (!correlationMatrix) return [];

    const correlations: { feature1: string; feature2: string; value: number }[] = [];
    for (let i = 0; i < FEATURE_KEYS.length; i++) {
      for (let j = i + 1; j < FEATURE_KEYS.length; j++) {
        correlations.push({
          feature1: FEATURE_LABELS[FEATURE_KEYS[i]],
          feature2: FEATURE_LABELS[FEATURE_KEYS[j]],
          value: correlationMatrix[i][j],
        });
      }
    }

    return correlations
      .filter((corr) => Number.isFinite(corr.value))
      .sort((a, b) => Math.abs(b.value) - Math.abs(a.value))
      .slice(0, 5);
  }, [correlationMatrix]);

  return (
    <div style={{ width: "100%", height }}>
      <div ref={chartRef} style={{ width: "100%", height: "70%" }} />
      
      {/* Strongest correlations list */}
      <div
        style={{
          padding: "12px",
          background: "rgba(0, 0, 0, 0.3)",
          borderRadius: "8px",
          marginTop: "8px",
        }}
      >
        <div style={{ color: "#888", fontSize: "12px", marginBottom: "8px" }}>
          Strongest Correlations
        </div>
        {strongestCorrelations.map((corr, idx) => (
          <div
            key={idx}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "4px 0",
              fontSize: "11px",
              color: "#aaa",
              borderBottom: idx < strongestCorrelations.length - 1 ? "1px solid rgba(255,255,255,0.1)" : "none",
            }}
          >
            <span>
              {corr.feature1} ↔ {corr.feature2}
            </span>
            <span
              style={{
                color: corr.value > 0 ? "#22c55e" : "#ef4444",
                fontWeight: "bold",
              }}
            >
              {corr.value > 0 ? "+" : ""}
              {corr.value.toFixed(3)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
