import { useEffect, useRef, useState, useMemo } from "react";
import * as echarts from "echarts";

interface HistoricalDataPoint {
  timestamp: string;
  score: number;
  features: Record<string, number>;
}

interface HistoricalPlaybackProps {
  data: HistoricalDataPoint[];
  height?: number;
  onFrameChange?: (frame: HistoricalDataPoint | null, index: number) => void;
  onPlaybackStateChange?: (isPlaying: boolean) => void;
}

export default function HistoricalPlayback({
  data,
  height = 400,
  onFrameChange,
  onPlaybackStateChange,
}: HistoricalPlaybackProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1000); // ms per step
  const [currentIndex, setCurrentIndex] = useState(0);
  const playbackRef = useRef<number | null>(null);

  // Calculate time range from data
  const timeRange = useMemo(() => {
    if (!data || data.length === 0) return { start: "", end: "", days: 0 };
    const start = new Date(data[0].timestamp);
    const end = new Date(data[data.length - 1].timestamp);
    const days = Math.floor((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24));
    return {
      start: start.toISOString().split("T")[0],
      end: end.toISOString().split("T")[0],
      days,
    };
  }, [data]);

  // Current data point
  const currentData = data[currentIndex];

  useEffect(() => {
    if (!onFrameChange) return;
    if (!data.length) {
      onFrameChange(null, 0);
      return;
    }
    onFrameChange(currentData ?? null, currentIndex);
  }, [onFrameChange, currentData, currentIndex, data.length]);

  useEffect(() => {
    if (!onPlaybackStateChange) return;
    onPlaybackStateChange(isPlaying);
  }, [onPlaybackStateChange, isPlaying]);

  // Playback controls
  useEffect(() => {
    if (isPlaying && currentIndex < data.length - 1) {
      playbackRef.current = window.setTimeout(() => {
        setCurrentIndex((prev) => prev + 1);
      }, playbackSpeed);
    } else if (isPlaying && currentIndex >= data.length - 1) {
      setIsPlaying(false);
      setCurrentIndex(0);
    }

    return () => {
      if (playbackRef.current) {
        clearTimeout(playbackRef.current);
      }
    };
  }, [isPlaying, currentIndex, data.length, playbackSpeed]);

  // Initialize chart
  useEffect(() => {
    if (!chartRef.current) return;

    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }

    const chart = chartInstanceRef.current;

    const option: echarts.EChartsOption = {
      tooltip: {
        trigger: "axis",
        formatter: (params: any) => {
          const point = params[0];
          return `<strong>${new Date(point.axisValue).toLocaleString()}</strong><br/>Risk Score: ${point.value.toFixed(2)}`;
        },
      },
      grid: {
        left: "50px",
        right: "20px",
        top: "40px",
        bottom: "60px",
      },
      xAxis: {
        type: "category",
        data: data.map((d) => d.timestamp),
        axisLabel: {
          rotate: 45,
          color: "#888",
          fontSize: 10,
          formatter: (value: string) => {
            const date = new Date(value);
            return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:00`;
          },
        },
        axisLine: {
          lineStyle: { color: "#333" },
        },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: {
          color: "#888",
        },
        splitLine: {
          lineStyle: { color: "rgba(255,255,255,0.1)" },
        },
      },
      visualMap: {
        show: false,
        pieces: [
          { gt: 0, lte: 40, color: "#22c55e" },
          { gt: 40, lte: 70, color: "#facc15" },
          { gt: 70, color: "#ef4444" },
        ],
      },
      series: [
        {
          name: "Risk Score",
          type: "line",
          data: data.map((d) => d.score),
          smooth: true,
          symbol: "circle",
          symbolSize: (_value: number, param: any) => {
            return param.dataIndex === currentIndex ? 12 : 4;
          },
          lineStyle: {
            width: 2,
          },
          itemStyle: {
            color: (params: any) => {
              const score = params.value;
              if (score > 70) return "#ef4444";
              if (score > 40) return "#facc15";
              return "#22c55e";
            },
          },
          markLine: {
            silent: true,
            data: [
              { yAxis: 70, lineStyle: { color: "#ef4444", type: "dashed" }, label: { formatter: "Critical" } },
              { yAxis: 40, lineStyle: { color: "#22c55e", type: "dashed" }, label: { formatter: "Safe" } },
            ],
          },
          markPoint: currentData ? {
            data: [
              {
                name: "Current",
                coord: [currentIndex, currentData.score],
                value: currentData.score.toFixed(1),
                itemStyle: {
                  color: "#00d4ff",
                },
              },
            ],
          } : undefined,
        },
      ],
    };

    chart.setOption(option);

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [data, currentIndex, currentData]);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCurrentIndex(parseInt(e.target.value, 10));
  };

  const handlePlayPause = () => {
    setIsPlaying(!isPlaying);
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentIndex(0);
  };

  const skipToStart = () => {
    setCurrentIndex(0);
  };

  const skipToEnd = () => {
    setCurrentIndex(data.length - 1);
  };

  if (!data || data.length === 0) {
    return (
      <div style={{ 
        height, 
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center",
        color: "#888",
        background: "rgba(0,0,0,0.3)",
        borderRadius: "8px"
      }}>
        No historical data available
      </div>
    );
  }

  return (
    <div style={{ width: "100%" }}>
      {/* Playback Controls */}
      <div style={{ 
        display: "flex", 
        alignItems: "center", 
        gap: "12px", 
        marginBottom: "16px",
        padding: "12px",
        background: "rgba(0,0,0,0.3)",
        borderRadius: "8px",
      }}>
        {/* Play/Pause Button */}
        <button
          onClick={handlePlayPause}
          style={{
            background: isPlaying ? "rgba(239,68,68,0.3)" : "rgba(34,197,94,0.3)",
            border: `1px solid ${isPlaying ? "rgba(239,68,68,0.5)" : "rgba(34,197,94,0.5)"}`,
            color: isPlaying ? "#ef4444" : "#22c55e",
            padding: "8px 16px",
            borderRadius: "6px",
            cursor: "pointer",
            fontSize: "14px",
            fontWeight: "bold",
          }}
        >
          {isPlaying ? "⏸ Pause" : "▶ Play"}
        </button>

        {/* Skip Buttons */}
        <button
          onClick={skipToStart}
          style={{
            background: "rgba(100,100,100,0.3)",
            border: "1px solid rgba(100,100,100,0.5)",
            color: "#aaa",
            padding: "8px 12px",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          ⏮
        </button>
        <button
          onClick={handleReset}
          style={{
            background: "rgba(100,100,100,0.3)",
            border: "1px solid rgba(100,100,100,0.5)",
            color: "#aaa",
            padding: "8px 12px",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          ↺
        </button>
        <button
          onClick={skipToEnd}
          style={{
            background: "rgba(100,100,100,0.3)",
            border: "1px solid rgba(100,100,100,0.5)",
            color: "#aaa",
            padding: "8px 12px",
            borderRadius: "6px",
            cursor: "pointer",
          }}
        >
          ⏭
        </button>

        {/* Timeline Slider */}
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: "12px" }}>
          <span style={{ color: "#888", fontSize: "12px", whiteSpace: "nowrap" }}>
            {timeRange.start}
          </span>
          <input
            type="range"
            min={0}
            max={data.length - 1}
            value={currentIndex}
            onChange={handleSliderChange}
            style={{
              flex: 1,
              height: "6px",
              background: `linear-gradient(to right, #00d4ff 0%, #00d4ff ${(currentIndex / (data.length - 1)) * 100}%, #333 ${(currentIndex / (data.length - 1)) * 100}%, #333 100%)`,
              borderRadius: "3px",
              cursor: "pointer",
            }}
          />
          <span style={{ color: "#888", fontSize: "12px", whiteSpace: "nowrap" }}>
            {timeRange.end}
          </span>
        </div>

        {/* Speed Control */}
        <select
          value={playbackSpeed}
          onChange={(e) => setPlaybackSpeed(parseInt(e.target.value, 10))}
          style={{
            background: "rgba(0,0,0,0.5)",
            border: "1px solid #333",
            color: "#aaa",
            padding: "6px 10px",
            borderRadius: "4px",
            cursor: "pointer",
          }}
        >
          <option value={500}>0.5x</option>
          <option value={1000}>1x</option>
          <option value={2000}>2x</option>
          <option value={5000}>5x</option>
        </select>
      </div>

      {/* Current State Display */}
      <div style={{ 
        display: "flex", 
        gap: "16px", 
        marginBottom: "12px",
        padding: "12px",
        background: "rgba(0,0,0,0.2)",
        borderRadius: "8px",
      }}>
        <div>
          <div style={{ color: "#888", fontSize: "11px", marginBottom: "4px" }}>Current Time</div>
          <div style={{ color: "#00d4ff", fontWeight: "bold" }}>
            {currentData ? new Date(currentData.timestamp).toLocaleString() : "N/A"}
          </div>
        </div>
        <div>
          <div style={{ color: "#888", fontSize: "11px", marginBottom: "4px" }}>Risk Score</div>
          <div style={{ 
            color: currentData && currentData.score > 70 ? "#ef4444" : currentData && currentData.score > 40 ? "#facc15" : "#22c55e",
            fontWeight: "bold",
            fontSize: "18px"
          }}>
            {currentData ? currentData.score.toFixed(2) : "N/A"}
          </div>
        </div>
        <div>
          <div style={{ color: "#888", fontSize: "11px", marginBottom: "4px" }}>Period Average</div>
          <div style={{ color: "#aaa", fontWeight: "bold" }}>
            {(data.slice(0, currentIndex + 1).reduce((sum, d) => sum + d.score, 0) / (currentIndex + 1)).toFixed(1)}
          </div>
        </div>
        <div>
          <div style={{ color: "#888", fontSize: "11px", marginBottom: "4px" }}>Data Points</div>
          <div style={{ color: "#aaa", fontWeight: "bold" }}>
            {currentIndex + 1} / {data.length}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div ref={chartRef} style={{ width: "100%", height: height - 180 }} />

      {/* Legend */}
      <div style={{ 
        display: "flex", 
        justifyContent: "center", 
        gap: "24px", 
        marginTop: "8px",
        fontSize: "12px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{ width: "12px", height: "12px", background: "#22c55e", borderRadius: "2px" }} />
          <span style={{ color: "#888" }}>Low Risk (0-40)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{ width: "12px", height: "12px", background: "#facc15", borderRadius: "2px" }} />
          <span style={{ color: "#888" }}>Medium Risk (40-70)</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{ width: "12px", height: "12px", background: "#ef4444", borderRadius: "2px" }} />
          <span style={{ color: "#888" }}>High Risk (70-100)</span>
        </div>
      </div>
    </div>
  );
}
