import { useEffect, useRef, useMemo, useState } from "react";
import * as echarts from "echarts";

interface TrendDataPoint {
  timestamp: string;
  news_sentiment: number;
  gdelt_sentiment: number;
  momentum?: number;
  acceleration?: number;
}

interface SentimentTrendAnalyzerProps {
  data: TrendDataPoint[];
  height?: number;
}

export default function SentimentTrendAnalyzer({ data, height = 350 }: SentimentTrendAnalyzerProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);
  const [selectedMetric, setSelectedMetric] = useState<"news_sentiment" | "gdelt_sentiment" | "momentum">("news_sentiment");

  // Calculate momentum and acceleration
  const processedData = useMemo(() => {
    if (!data || data.length < 3) return data || [];

    const processed: TrendDataPoint[] = data.map((d, idx) => ({
      ...d,
      momentum: idx > 0 ? d.news_sentiment - data[idx - 1].news_sentiment : 0,
      acceleration: idx > 1 
        ? (d.news_sentiment - data[idx - 1].news_sentiment) - (data[idx - 1].news_sentiment - data[idx - 2].news_sentiment)
        : 0,
    }));

    return processed;
  }, [data]);

  // Determine trend direction
  const trendAnalysis = useMemo(() => {
    if (!processedData || processedData.length < 5) {
      return { direction: "neutral", strength: 0, prediction: "stable" };
    }

    const recent = processedData.slice(-5);
    const avgMomentum = recent.reduce((sum, d) => sum + (d.momentum || 0), 0) / recent.length;
    const avgAcceleration = recent.reduce((sum, d) => sum + (d.acceleration || 0), 0) / recent.length;

    let direction = "neutral";
    let strength = Math.abs(avgMomentum);
    let prediction = "stable";

    if (avgMomentum > 0.05) {
      direction = "bullish";
      prediction = avgAcceleration > 0 ? "accelerating_up" : "slowing_up";
    } else if (avgMomentum < -0.05) {
      direction = "bearish";
      prediction = avgAcceleration < 0 ? "accelerating_down" : "slowing_down";
    }

    return { direction, strength, prediction };
  }, [processedData]);

  useEffect(() => {
    if (!chartRef.current || !processedData || processedData.length === 0) return;

    // Initialize chart
    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }

    const chart = chartInstanceRef.current;

    const timestamps = processedData.map(d => {
      const date = new Date(d.timestamp);
      return date.toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit" });
    });

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(0, 0, 0, 0.8)",
        borderColor: "#333",
        textStyle: { color: "#fff" },
        formatter: (params: any) => {
          const idx = params[0].dataIndex;
          const d = processedData[idx];
          let html = `<strong>${params[0].axisValue}</strong><br/>`;
          html += `News Sentiment: ${d.news_sentiment.toFixed(3)}<br/>`;
          html += `GDELT Sentiment: ${d.gdelt_sentiment.toFixed(3)}<br/>`;
          if (d.momentum !== undefined) {
            html += `Momentum: ${d.momentum.toFixed(3)}<br/>`;
          }
          if (d.acceleration !== undefined) {
            html += `Acceleration: ${d.acceleration.toFixed(3)}`;
          }
          return html;
        },
      },
      legend: {
        data: ["News Sentiment", "GDELT Sentiment", "Momentum"],
        textStyle: { color: "#888" },
        top: 0,
      },
      grid: {
        left: "3%",
        right: "4%",
        bottom: "3%",
        top: "30%",
        containLabel: true,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: timestamps,
        axisLabel: { color: "#888", fontSize: 10 },
        axisLine: { lineStyle: { color: "#333" } },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#888" },
        splitLine: { lineStyle: { color: "#222" } },
      },
      series: [
        {
          name: "News Sentiment",
          type: "line",
          data: processedData.map(d => d.news_sentiment),
          smooth: true,
          lineStyle: { width: 2, color: "#3b82f6" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(59, 130, 246, 0.3)" },
              { offset: 1, color: "rgba(59, 130, 246, 0)" },
            ]),
          },
          showSymbol: false,
        },
        {
          name: "GDELT Sentiment",
          type: "line",
          data: processedData.map(d => d.gdelt_sentiment),
          smooth: true,
          lineStyle: { width: 2, color: "#8b5cf6" },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: "rgba(139, 92, 246, 0.3)" },
              { offset: 1, color: "rgba(139, 92, 246, 0)" },
            ]),
          },
          showSymbol: false,
        },
        {
          name: "Momentum",
          type: "bar",
          data: processedData.map(d => d.momentum || 0),
          itemStyle: {
            color: (params: any) => {
              return params.data >= 0 ? "rgba(34, 197, 94, 0.6)" : "rgba(239, 68, 68, 0.6)";
            },
          },
          barWidth: "30%",
        },
      ],
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [processedData, selectedMetric]);

  // Get trend indicator styles
  const getTrendIndicator = () => {
    switch (trendAnalysis.direction) {
      case "bullish":
        return { color: "#22c55e", icon: "↑", label: "Bullish" };
      case "bearish":
        return { color: "#ef4444", icon: "↓", label: "Bearish" };
      default:
        return { color: "#facc15", icon: "→", label: "Neutral" };
    }
  };

  const indicator = getTrendIndicator();

  return (
    <div style={{ width: "100%", height }}>
      {/* Controls */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "12px" }}>
        {(["news_sentiment", "gdelt_sentiment", "momentum"] as const).map((metric) => (
          <button
            key={metric}
            onClick={() => setSelectedMetric(metric)}
            style={{
              padding: "6px 12px",
              borderRadius: "4px",
              border: "none",
              cursor: "pointer",
              fontSize: "11px",
              background: selectedMetric === metric ? "#3b82f6" : "#333",
              color: selectedMetric === metric ? "#fff" : "#888",
              transition: "all 0.2s",
            }}
          >
            {metric === "news_sentiment" ? "News" : metric === "gdelt_sentiment" ? "GDELT" : "Momentum"}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div ref={chartRef} style={{ width: "100%", height: "55%" }} />

      {/* Analysis Panel */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "8px",
          marginTop: "12px",
        }}
      >
        <div
          style={{
            padding: "10px",
            background: "rgba(0, 0, 0, 0.3)",
            borderRadius: "6px",
            textAlign: "center",
          }}
        >
          <div style={{ color: "#888", fontSize: "10px", marginBottom: "4px" }}>Trend Direction</div>
          <div style={{ color: indicator.color, fontSize: "16px", fontWeight: "bold" }}>
            {indicator.icon} {indicator.label}
          </div>
        </div>

        <div
          style={{
            padding: "10px",
            background: "rgba(0, 0, 0, 0.3)",
            borderRadius: "6px",
            textAlign: "center",
          }}
        >
          <div style={{ color: "#888", fontSize: "10px", marginBottom: "4px" }}>Momentum Strength</div>
          <div style={{ color: "#fff", fontSize: "16px", fontWeight: "bold" }}>
            {(trendAnalysis.strength * 100).toFixed(1)}%
          </div>
        </div>

        <div
          style={{
            padding: "10px",
            background: "rgba(0, 0, 0, 0.3)",
            borderRadius: "6px",
            textAlign: "center",
          }}
        >
          <div style={{ color: "#888", fontSize: "10px", marginBottom: "4px" }}>Prediction</div>
          <div style={{ color: "#60a5fa", fontSize: "12px", fontWeight: "bold", textTransform: "capitalize" }}>
            {trendAnalysis.prediction.replace("_", " ")}
          </div>
        </div>
      </div>

      {/* Current values */}
      {processedData.length > 0 && (
        <div
          style={{
            marginTop: "12px",
            padding: "8px",
            background: "rgba(0, 0, 0, 0.2)",
            borderRadius: "4px",
            display: "flex",
            justifyContent: "space-between",
            fontSize: "11px",
          }}
        >
          <span style={{ color: "#3b82f6" }}>News: {processedData[processedData.length - 1]?.news_sentiment.toFixed(3)}</span>
          <span style={{ color: "#8b5cf6" }}>GDELT: {processedData[processedData.length - 1]?.gdelt_sentiment.toFixed(3)}</span>
          <span style={{ color: "#22c55e" }}>Momentum: {processedData[processedData.length - 1]?.momentum?.toFixed(3) || "0.000"}</span>
        </div>
      )}
    </div>
  );
}
