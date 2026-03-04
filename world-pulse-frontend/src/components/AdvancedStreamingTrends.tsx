import { useEffect, useRef, useState } from "react";

type Point = {
  timestamp: string;
  value: number;
};

type Series = {
  name: string;
  points: Point[];
  color?: string;
  width?: number;
};

type Props = {
  title: string;
  series: Series[];
  anomalies?: Point[];
  thresholdBand?: { low: number; high: number };
  className?: string;
  height?: number;
  showLegend?: boolean;
  animated?: boolean;
};

export default function AdvancedStreamingTrends({
  title,
  series,
  anomalies = [],
  thresholdBand,
  className,
  height = 320,
  showLegend = true,
  animated = true,
}: Props) {
  const holderRef = useRef<HTMLDivElement | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [hoveredSeries] = useState<string | null>(null);
  const [anomalyPulse, setAnomalyPulse] = useState(false);

  // Pulse effect for anomalies
  useEffect(() => {
    if (anomalies.length === 0) return;
    
    const interval = setInterval(() => {
      setAnomalyPulse(prev => !prev);
    }, 800);
    
    return () => clearInterval(interval);
  }, [anomalies.length]);

  useEffect(() => {
    let closed = false;
    const render = async () => {
      if (!holderRef.current) return;
      const mod = await import("plotly.js-dist-min");
      const Plotly = (mod as any).default ?? mod;
      if (closed || !holderRef.current) return;

      // Cyberpunk neon color palette - maximum visibility
      const lineColors = [
        "#00f5ff", // Global Risk - electric cyan
        "#ff00ff", // News Sentiment - hot magenta  
        "#ff1744", // Crypto Volatility - neon crimson (very visible)
        "#ffab00", // Weather Anomaly - amber neon
      ];



      const traces: any[] = [];

      series.forEach((s, i) => {
        const baseColor = s.color ?? lineColors[i % lineColors.length];
        const isGlobalRisk = s.name.toLowerCase().includes("global risk");
        const hasAnomalies = anomalies.length > 0 && isGlobalRisk;
        
        // For Global Risk with anomalies, one continuous line with blinking end marker
        if (hasAnomalies && animated) {
          const lastPoint = s.points[s.points.length - 1];
          
          // One continuous straight line with enhanced glow
          traces.push({
            type: "scatter",
            mode: "lines",
            name: s.name,
            x: s.points.map((p) => p.timestamp),
            y: s.points.map((p) => p.value),
            line: {
              width: 5,
              color: baseColor,
              shape: "linear",
            },
            hovertemplate: `<b>${s.name}</b><br>Time: %{x}<br>Value: %{y:.2f}<extra></extra>`,
            showlegend: true,
            legendgroup: s.name,
          });
          
          // Secondary glow line
          traces.push({
            type: "scatter",
            mode: "lines",
            name: `${s.name} glow`,
            x: s.points.map((p) => p.timestamp),
            y: s.points.map((p) => p.value),
            line: {
              width: 12,
              color: baseColor,
              shape: "linear",
            },
            opacity: 0.15,
            hoverinfo: "skip",
            showlegend: false,
            legendgroup: s.name,
          });
          
          // Blinking marker at the end only
          traces.push({
            type: "scatter",
            mode: "markers",
            name: `${s.name} endpoint`,
            x: [lastPoint.timestamp],
            y: [lastPoint.value],
            marker: {
              size: anomalyPulse ? 18 : 12,
              color: anomalyPulse ? "#ff0040" : baseColor,
              symbol: "circle",
              line: {
                color: "#ffffff",
                width: 2,
              },
            },
            opacity: 1,
            hoverinfo: "skip",
            showlegend: false,
            legendgroup: s.name,
          });
        } else {
          // Regular trace - one straight solid line with glow effect
          const isHovered = hoveredSeries === s.name;
          const isDimmed = hoveredSeries && hoveredSeries !== s.name;
          const isCrypto = s.name.toLowerCase().includes("crypto");

          // Main line
          traces.push({
            type: "scatter",
            mode: "lines",
            name: s.name,
            x: s.points.map((p) => p.timestamp),
            y: s.points.map((p) => p.value),
            line: {
              width: isCrypto ? 6 : (isHovered ? 5 : 4),
              color: baseColor,
              shape: "linear",
            },
            opacity: isDimmed ? 0.3 : 1,
            hovertemplate: `<b>${s.name}</b><br>Time: %{x}<br>Value: %{y:.2f}<extra></extra>`,
          });

          // Glow effect line
          traces.push({
            type: "scatter",
            mode: "lines",
            name: `${s.name} glow`,
            x: s.points.map((p) => p.timestamp),
            y: s.points.map((p) => p.value),
            line: {
              width: isCrypto ? 14 : 10,
              color: baseColor,
              shape: "linear",
            },
            opacity: isDimmed ? 0.1 : 0.2,
            hoverinfo: "skip",
            showlegend: false,
          });

          // Data points for crypto (highly visible)
          if (isCrypto) {
            traces.push({
              type: "scatter",
              mode: "markers",
              name: `${s.name} points`,
              x: s.points.filter((_, idx) => idx % 5 === 0).map((p) => p.timestamp),
              y: s.points.filter((_, idx) => idx % 5 === 0).map((p) => p.value),
              marker: {
                size: 6,
                color: baseColor,
                symbol: "diamond",
                line: {
                  color: "#ffffff",
                  width: 1,
                },
              },
              opacity: 0.8,
              hoverinfo: "skip",
              showlegend: false,
            });
          }
        }


      });

      // Filter anomalies - only show recent ones (last 3 minutes) and make latest blink
      const now = new Date();
      const recentAnomalies = anomalies.filter(a => {
        const anomalyTime = new Date(a.timestamp);
        const diffMinutes = (now.getTime() - anomalyTime.getTime()) / (1000 * 60);
        return diffMinutes < 3; // Only show anomalies from last 3 minutes
      });

      // Add anomaly markers - only the latest one blinks
      if (recentAnomalies.length) {
        const latestAnomaly = recentAnomalies[recentAnomalies.length - 1];
        const olderAnomalies = recentAnomalies.slice(0, -1);
        
        // Older anomalies - static, smaller
        if (olderAnomalies.length) {
          traces.push({
            type: "scatter",
            mode: "markers",
            name: "Anomalies",
            x: olderAnomalies.map((a) => a.timestamp),
            y: olderAnomalies.map((a) => a.value),
            marker: {
              color: "#ff6b6b",
              size: 8,
              symbol: "triangle-up",
              opacity: 0.6,
            },
            hovertemplate: "<b>Anomaly</b><br>Time: %{x}<br>Risk: %{y:.1f}<extra></extra>",
          });
        }
        
        // Latest anomaly - blinking beacon effect
        traces.push({
          type: "scatter",
          mode: "markers",
          name: "⚠ LATEST",
          x: [latestAnomaly.timestamp],
          y: [latestAnomaly.value],
          marker: {
            color: anomalyPulse ? "#ff0040" : "#ff6b6b",
            size: anomalyPulse ? 20 : 14,
            symbol: "star",
            line: {
              color: anomalyPulse ? "#ffffff" : "#ff0040",
              width: anomalyPulse ? 3 : 2,
            },
            opacity: 1,
          },
          hovertemplate: "<b>⚠ LATEST ANOMALY</b><br>Time: %{x}<br>Risk: %{y:.1f}<extra></extra>",
        });
      }

      // Threshold band
      const shapes = thresholdBand
        ? [
            {
              type: "rect",
              xref: "paper",
              x0: 0,
              x1: 1,
              y0: thresholdBand.low,
              y1: thresholdBand.high,
              fillcolor: "rgba(0, 245, 255, 0.08)",
              line: { width: 0 },
              layer: "below",
            },
            {
              type: "line",
              xref: "paper",
              x0: 0,
              x1: 1,
              y0: thresholdBand.low,
              y1: thresholdBand.low,
              line: {
                color: "rgba(0, 245, 255, 0.4)",
                width: 1,
                dash: "dot",
              },
              layer: "below",
            },
            {
              type: "line",
              xref: "paper",
              x0: 0,
              x1: 1,
              y0: thresholdBand.high,
              y1: thresholdBand.high,
              line: {
                color: "rgba(0, 245, 255, 0.4)",
                width: 1,
                dash: "dot",
              },
              layer: "below",
            },
          ]
        : [];

      const layout: any = {
        title: {
          text: `<b>${title}</b>`,
          font: {
            color: "#00f5ff",
            size: 18,
            family: "Rajdhani, sans-serif",
          },
          x: 0.5,
          xanchor: "center",
        },
        margin: { l: 50, r: 20, b: 40, t: 60 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "#dbeafe", size: 11, family: "Rajdhani, sans-serif" },
        shapes,
        xaxis: {
          gridcolor: "rgba(0, 245, 255, 0.15)",
          linecolor: "rgba(0, 245, 255, 0.4)",
          tickfont: { color: "#a0d0e0", size: 10 },
          tickformat: "%H:%M",
          showgrid: true,
          gridwidth: 1,
          zeroline: false,
        },
        yaxis: {
          gridcolor: "rgba(0, 245, 255, 0.15)",
          linecolor: "rgba(0, 245, 255, 0.4)",
          tickfont: { color: "#a0d0e0", size: 10 },
          showgrid: true,
          gridwidth: 1,
          zeroline: false,
          range: [0, 100],
        },
        showlegend: showLegend,
        legend: {
          orientation: "h",
          yanchor: "bottom",
          y: 1.05,
          xanchor: "right",
          x: 1,
          font: { color: "#a0d0e0", size: 11 },
          bgcolor: "rgba(0,10,20,0.5)",
          bordercolor: "rgba(0, 245, 255, 0.3)",
          borderwidth: 1,
        },
        hovermode: "x unified",
        hoverlabel: {
          bgcolor: "rgba(5, 15, 30, 0.95)",
          bordercolor: "rgba(0, 245, 255, 0.6)",
          font: { color: "#ffffff", size: 12 },
        },
      };


      const config = {
        displayModeBar: false,
        responsive: true,
        staticPlot: false,
      };

      await Plotly.react(holderRef.current, traces, layout, config);
      setIsLoading(false);
    };

    render().catch(() => {
      setIsLoading(false);
    });

    return () => {
      closed = true;
    };
  }, [title, series, anomalies, thresholdBand, showLegend, hoveredSeries, anomalyPulse, animated]);

  return (
    <div className={`advanced-streaming-trends ${className ?? ""} ${animated ? "trends-animated" : ""}`}>
      <div className="trends-header">
        <div className="trends-title">
          <span className={`pulse-indicator ${anomalies.length > 0 ? "alert" : ""}`}></span>
          <h4>{title}</h4>
        </div>
        <div className="trends-status">
          {anomalies.length > 0 && (
            <span className="anomaly-badge">{anomalies.length} ANOMALIES</span>
          )}
          <span className="live-badge">LIVE</span>
          <span className="data-points">{series[0]?.points.length || 0} pts</span>
        </div>
      </div>
      
      <div className="trends-chart-container">
        {isLoading && (
          <div className="trends-loading">
            <div className="loading-spinner"></div>
            <span>Initializing stream...</span>
          </div>
        )}
        <div ref={holderRef} style={{ width: "100%", height }} />
      </div>

      <div className="trends-footer">
        <div className="trends-metrics">
          {series.slice(0, 3).map((s, i) => {
            const latest = s.points[s.points.length - 1]?.value ?? 0;
            const prev = s.points[s.points.length - 2]?.value ?? latest;
            const change = latest - prev;
            const colors = ["#00f5ff", "#ff00ff", "#39ff14"];
            const isAnomaly = anomalies.some(a => Math.abs(a.value - latest) < 5);
            
            return (
              <div key={s.name} className={`trend-metric ${isAnomaly ? "anomaly" : ""}`}>
                <span className="metric-name">{s.name}</span>
                <span className="metric-value" style={{ color: colors[i % colors.length] }}>
                  {latest.toFixed(1)}
                </span>
                <span className={`metric-change ${change >= 0 ? "up" : "down"}`}>
                  {change >= 0 ? "↑" : "↓"} {Math.abs(change).toFixed(2)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export { AdvancedStreamingTrends };
