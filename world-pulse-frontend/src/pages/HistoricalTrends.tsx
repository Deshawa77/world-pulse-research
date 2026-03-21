import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import ConsoleNavigation from "../components/ConsoleNavigation";
import predictionService, { type PredictionLog, type HistoricalDataPoint } from "../services/predictionService";

type DateRange = "24h" | "7d" | "30d" | "90d" | "custom";

type ComparisonEvent = {
  id: string;
  name: string;
  date: string;
  riskScore: number;
  sentiment: number;
  directBehavior: number;
  contextualPressure: number;
  evidenceQuality: number;
  logisticsStress: number;
  householdStress: number;
  energyStress: number;
  topics: string[];
  selected: boolean;
};

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function safeN(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export default function HistoricalTrends() {
  const navigate = useNavigate();
  const token = localStorage.getItem("token");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [historicalData, setHistoricalData] = useState<HistoricalDataPoint[]>([]);
  const [, setPredictionLogs] = useState<PredictionLog[]>([]);

  const [dateRange, setDateRange] = useState<DateRange>("7d");
  const [customStartDate, setCustomStartDate] = useState<string>("");
  const [customEndDate, setCustomEndDate] = useState<string>("");
  const [comparisonEvents, setComparisonEvents] = useState<ComparisonEvent[]>([]);
  const [selectedMetrics, setSelectedMetrics] = useState<string[]>([
    "risk_score",
    "news_sentiment",
    "contextual_pressure_score",
    "logistics_stress_score",
  ]);
  const [exportFormat, setExportFormat] = useState<"csv" | "json" | "png">("csv");

  const timelineChartRef = useRef<HTMLDivElement | null>(null);
  const comparisonChartRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);

  useEffect(() => {
    if (!token) {
      navigate("/login");
      return;
    }
    loadPlotly().then(() => loadData());
  }, [token, navigate, dateRange]);

  async function loadPlotly() {
    if (plotlyRef.current) return plotlyRef.current;
    if (!plotlyLoadingRef.current) {
      plotlyLoadingRef.current = import("plotly.js-dist-min")
        .then((mod) => {
          plotlyRef.current = (mod as any).default ?? mod;
          return plotlyRef.current;
        })
        .catch((e) => {
          plotlyLoadingRef.current = null;
          throw e;
        });
    }
    return plotlyLoadingRef.current;
  }

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      // Calculate date range
      const endDate = new Date();
      const startDate = new Date();

      switch (dateRange) {
        case "24h":
          startDate.setHours(startDate.getHours() - 24);
          break;
        case "7d":
          startDate.setDate(startDate.getDate() - 7);
          break;
        case "30d":
          startDate.setDate(startDate.getDate() - 30);
          break;
        case "90d":
          startDate.setDate(startDate.getDate() - 90);
          break;
        case "custom":
          if (customStartDate && customEndDate) {
            startDate.setTime(new Date(customStartDate).getTime());
            endDate.setTime(new Date(customEndDate).getTime());
          }
          break;
      }

      const [logs, realHistory] = await Promise.all([
        predictionService.getPredictionLogs(1000),
        predictionService.getHistoricalData(startDate.toISOString(), endDate.toISOString(), 2000),
      ]);
      setPredictionLogs(logs);
      setHistoricalData(realHistory);

      const events: ComparisonEvent[] = realHistory
        .filter((_, idx) => idx % 10 === 0)
        .slice(0, 8)
        .map((point, idx) => ({
          id: `evt-${idx}-${point.timestamp}`,
          name: `${point.top_topics?.[0] || "Signal"} ${idx + 1}`,
          date: point.timestamp,
          riskScore: safeN(point.risk_score),
          sentiment: safeN(point.news_sentiment),
          directBehavior: safeN(point.direct_behavior_score),
          contextualPressure: safeN(point.contextual_pressure_score),
          evidenceQuality: safeN(point.evidence_quality_score),
          logisticsStress: safeN(point.logistics_stress_score),
          householdStress: safeN(point.household_stress_score),
          energyStress: safeN(point.energy_stress_score),
          topics: point.top_topics ?? [],
          selected: idx < 2,
        }));

      setComparisonEvents(events);
    } catch (err: any) {
      setError(err?.message || "Failed to load historical data");
    } finally {
      setLoading(false);
    }
  }

  // Render Timeline Chart
  useEffect(() => {
    if (!timelineChartRef.current || !historicalData.length || !plotlyRef.current) return;

    const timestamps = historicalData.map((d) => formatDate(d.timestamp));

    const traces: any[] = [];

    if (selectedMetrics.includes("risk_score")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => d.risk_score),
        type: "scatter",
        mode: "lines",
        name: "Risk Score",
        line: { color: "#ef4444", width: 3 },
        fill: "tozeroy",
        fillcolor: "rgba(239, 68, 68, 0.1)",
      });
    }

    if (selectedMetrics.includes("news_sentiment")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => d.news_sentiment),
        type: "scatter",
        mode: "lines",
        name: "News Sentiment",
        line: { color: "#22d3ee", width: 2 },
        yaxis: "y2",
      });
    }

    if (selectedMetrics.includes("gdelt_sentiment")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => d.gdelt_sentiment),
        type: "scatter",
        mode: "lines",
        name: "GDELT Sentiment",
        line: { color: "#a3e635", width: 2 },
        yaxis: "y2",
      });
    }

    if (selectedMetrics.includes("crypto_return")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => d.crypto_return),
        type: "scatter",
        mode: "lines",
        name: "Crypto Return",
        line: { color: "#f472b6", width: 2, dash: "dash" },
        yaxis: "y3",
      });
    }

    if (selectedMetrics.includes("stock_return")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => d.stock_return),
        type: "scatter",
        mode: "lines",
        name: "Stock Return",
        line: { color: "#60a5fa", width: 2, dash: "dash" },
        yaxis: "y3",
      });
    }

    if (selectedMetrics.includes("direct_behavior_score")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => safeN(d.direct_behavior_score)),
        type: "scatter",
        mode: "lines",
        name: "Direct Behavior",
        line: { color: "#22c55e", width: 2 },
        yaxis: "y4",
      });
    }

    if (selectedMetrics.includes("contextual_pressure_score")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => safeN(d.contextual_pressure_score)),
        type: "scatter",
        mode: "lines",
        name: "Context Pressure",
        line: { color: "#f59e0b", width: 2 },
        yaxis: "y4",
      });
    }

    if (selectedMetrics.includes("evidence_quality_score")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => safeN(d.evidence_quality_score)),
        type: "scatter",
        mode: "lines",
        name: "Evidence Quality",
        line: { color: "#10b981", width: 2, dash: "dot" },
        yaxis: "y4",
      });
    }

    if (selectedMetrics.includes("logistics_stress_score")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => safeN(d.logistics_stress_score)),
        type: "scatter",
        mode: "lines",
        name: "Logistics Stress",
        line: { color: "#eab308", width: 2 },
        yaxis: "y4",
      });
    }

    if (selectedMetrics.includes("household_stress_score")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => safeN(d.household_stress_score)),
        type: "scatter",
        mode: "lines",
        name: "Household Stress",
        line: { color: "#fb7185", width: 2 },
        yaxis: "y4",
      });
    }

    if (selectedMetrics.includes("energy_stress_score")) {
      traces.push({
        x: timestamps,
        y: historicalData.map((d) => safeN(d.energy_stress_score)),
        type: "scatter",
        mode: "lines",
        name: "Energy Stress",
        line: { color: "#84cc16", width: 2, dash: "dot" },
        yaxis: "y4",
      });
    }

    const layout = {
      title: {
        text: "Sentiment Timeline",
        font: { color: "#e7efff", size: 18 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#9fb0cf" },
      xaxis: {
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
        title: "Time",
      },
      yaxis: {
        title: "Risk Score",
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#ef4444" },
        range: [0, 100],
        side: "left",
      },
      yaxis2: {
        title: "Sentiment",
        overlaying: "y",
        side: "right",
        range: [-100, 100],
        tickfont: { color: "#22d3ee" },
        showgrid: false,
      },
      yaxis3: {
        title: "Return %",
        overlaying: "y",
        side: "right",
        position: 0.95,
        range: [-50, 50],
        tickfont: { color: "#f472b6" },
        showgrid: false,
      },
      yaxis4: {
        title: "Behavior / Stress",
        overlaying: "y",
        side: "right",
        position: 0.88,
        range: [0, 1],
        tickfont: { color: "#22c55e" },
        showgrid: false,
      },
      legend: {
        font: { color: "#9fb0cf" },
        x: 0.02,
        y: 0.98,
      },
      margin: { t: 60, r: 80, b: 60, l: 60 },
      hovermode: "x unified",
    };

    plotlyRef.current.newPlot(timelineChartRef.current, traces, layout, {
      displayModeBar: true,
      displaylogo: false,
      modeBarButtonsToRemove: ["lasso2d", "select2d"],
      responsive: true,
    });
  }, [historicalData, selectedMetrics]);

  // Render Comparison Chart
  useEffect(() => {
    if (!comparisonChartRef.current || !comparisonEvents.length || !plotlyRef.current) return;

    const selectedEvents = comparisonEvents.filter((e) => e.selected);

    if (selectedEvents.length < 2) {
      plotlyRef.current.purge(comparisonChartRef.current);
      return;
    }

    const data = [
      {
        type: "bar",
        x: selectedEvents.map((e) => e.name),
        y: selectedEvents.map((e) => e.riskScore),
        name: "Risk Score",
        marker: { color: "#ef4444" },
      },
      {
        type: "bar",
        x: selectedEvents.map((e) => e.name),
        y: selectedEvents.map((e) => e.contextualPressure),
        name: "Context Pressure",
        marker: { color: "#f59e0b" },
      },
      {
        type: "bar",
        x: selectedEvents.map((e) => e.name),
        y: selectedEvents.map((e) => e.logisticsStress),
        name: "Logistics Stress",
        marker: { color: "#eab308" },
      },
    ];

    const layout = {
      title: {
        text: "Event Comparison",
        font: { color: "#e7efff", size: 18 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: "#9fb0cf" },
      barmode: "group",
      xaxis: {
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
      },
      yaxis: {
        title: "Score",
        gridcolor: "rgba(146,170,210,0.2)",
        tickfont: { color: "#9fb0cf" },
      },
      legend: {
        font: { color: "#9fb0cf" },
        x: 0.02,
        y: 0.98,
      },
      margin: { t: 60, r: 30, b: 60, l: 60 },
    };

    plotlyRef.current.newPlot(comparisonChartRef.current, data, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [comparisonEvents]);

  const toggleEventSelection = (eventId: string) => {
    setComparisonEvents((events) =>
      events.map((e) => (e.id === eventId ? { ...e, selected: !e.selected } : e))
    );
  };

  const toggleMetric = (metric: string) => {
    setSelectedMetrics((metrics) =>
      metrics.includes(metric)
        ? metrics.filter((m) => m !== metric)
        : [...metrics, metric]
    );
  };

  const handleExport = async () => {
    try {
      if (exportFormat === "png") {
        // Export chart as PNG
        if (timelineChartRef.current && plotlyRef.current) {
          plotlyRef.current.downloadImage(timelineChartRef.current, {
            format: "png",
            width: 1200,
            height: 600,
            filename: `world-pulse-timeline-${new Date().toISOString().split("T")[0]}`,
          });
        }
      } else {
        // Export data as CSV or JSON
        const dataStr =
          exportFormat === "json"
            ? JSON.stringify(historicalData, null, 2)
            : convertToCSV(historicalData);

        const blob = new Blob([dataStr], {
          type: exportFormat === "json" ? "application/json" : "text/csv",
        });

        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `world-pulse-data-${new Date().toISOString().split("T")[0]}.${exportFormat}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
      }
    } catch (err: any) {
      setError(`Export failed: ${err.message}`);
    }
  };

  const convertToCSV = (data: HistoricalDataPoint[]): string => {
    if (!data.length) return "";

    const headers = Object.keys(data[0]).join(",");
    const rows = data.map((row) =>
      Object.values(row)
        .map((val) => (Array.isArray(val) ? `"${val.join(";")}"` : val))
        .join(",")
    );

    return [headers, ...rows].join("\n");
  };

  const stats = useMemo(() => {
    if (!historicalData.length) return null;

    const riskScores = historicalData.map((d) => d.risk_score);
    const sentiments = historicalData.map((d) => d.news_sentiment);
    const contextual = historicalData.map((d) => safeN(d.contextual_pressure_score));
    const logistics = historicalData.map((d) => safeN(d.logistics_stress_score));
    const evidence = historicalData.map((d) => safeN(d.evidence_quality_score));

    return {
      avgRisk: riskScores.reduce((a, b) => a + b, 0) / riskScores.length,
      maxRisk: Math.max(...riskScores),
      minRisk: Math.min(...riskScores),
      avgSentiment: sentiments.reduce((a, b) => a + b, 0) / sentiments.length,
      avgContextualPressure: contextual.reduce((a, b) => a + b, 0) / contextual.length,
      avgLogisticsStress: logistics.reduce((a, b) => a + b, 0) / logistics.length,
      avgEvidenceQuality: evidence.reduce((a, b) => a + b, 0) / evidence.length,
      dataPoints: historicalData.length,
    };
  }, [historicalData]);

  if (loading) {
    return (
      <main className="wp-loading">
        <section className="wp-loading-card">
          <h1>HISTORICAL TRENDS</h1>
          <p>Loading historical data...</p>
          {error && <p className="err">{error}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="wp-shell">
      <ConsoleNavigation
        title={<>HISTORICAL <span>TRENDS</span></>}
        subtitle="Deep dive into past events, signal shifts, and sentiment patterns."
        sectionTabs={[
          { label: "Date Range", targetId: "historical-range" },
          { label: "Timeline", targetId: "historical-timeline" },
          { label: "Comparison", targetId: "historical-comparison" },
          { label: "Data Table", targetId: "historical-table" },
        ]}
      />

      {/* Date Range & Stats */}
      <section id="historical-range" className="wp-strip">
        <article className="wp-card date-range-card">
          <h3>Date Range</h3>
          <div className="date-range-buttons">
            {(["24h", "7d", "30d", "90d"] as DateRange[]).map((range) => (
              <button
                key={range}
                className={dateRange === range ? "active" : ""}
                onClick={() => setDateRange(range)}
              >
                {range === "24h" && "24 Hours"}
                {range === "7d" && "7 Days"}
                {range === "30d" && "30 Days"}
                {range === "90d" && "90 Days"}
              </button>
            ))}
            <button
              className={dateRange === "custom" ? "active" : ""}
              onClick={() => setDateRange("custom")}
            >
              Custom
            </button>
          </div>

          {dateRange === "custom" && (
            <div className="custom-date-inputs">
              <input
                type="datetime-local"
                value={customStartDate}
                onChange={(e) => setCustomStartDate(e.target.value)}
                placeholder="Start Date"
              />
              <input
                type="datetime-local"
                value={customEndDate}
                onChange={(e) => setCustomEndDate(e.target.value)}
                placeholder="End Date"
              />
              <button onClick={loadData}>Apply</button>
            </div>
          )}
        </article>

        <article className="wp-card stat-card">
          <h3>Average Risk</h3>
          <strong className="wp-highlight">{stats?.avgRisk.toFixed(1) || "0.0"}</strong>
          <div className="stat-range">
            Range: {stats?.minRisk.toFixed(0) || "0"} - {stats?.maxRisk.toFixed(0) || "0"}
          </div>
        </article>

        <article className="wp-card stat-card">
          <h3>Avg Sentiment</h3>
          <strong className="wp-highlight">{stats?.avgSentiment.toFixed(1) || "0.0"}</strong>
          <div
            className={`sentiment-indicator ${
              (stats?.avgSentiment || 0) > 0 ? "positive" : "negative"
            }`}
          >
            {(stats?.avgSentiment || 0) > 0 ? "↗ Positive" : "↘ Negative"}
          </div>
        </article>

        <article className="wp-card stat-card">
          <h3>Data Points</h3>
          <strong className="wp-highlight">{stats?.dataPoints || 0}</strong>
          <div className="stat-range">Records analyzed</div>
        </article>
      </section>

      {/* Timeline Chart */}
      <section id="historical-timeline" className="wp-grid">
        <article className="wp-card panel-animated chart-card">
          <div className="chart-header">
            <h2>Sentiment Timeline</h2>
            <div className="metric-toggles">
              {[
                { key: "risk_score", label: "Risk", color: "#ef4444" },
                { key: "news_sentiment", label: "News", color: "#22d3ee" },
                { key: "gdelt_sentiment", label: "GDELT", color: "#a3e635" },
                { key: "crypto_return", label: "Crypto", color: "#f472b6" },
                { key: "stock_return", label: "Stock", color: "#60a5fa" },
                { key: "direct_behavior_score", label: "Behavior", color: "#22c55e" },
                { key: "contextual_pressure_score", label: "Context", color: "#f59e0b" },
                { key: "evidence_quality_score", label: "Evidence", color: "#10b981" },
                { key: "logistics_stress_score", label: "Logistics", color: "#eab308" },
                { key: "household_stress_score", label: "Household", color: "#fb7185" },
                { key: "energy_stress_score", label: "Energy", color: "#84cc16" },
              ].map((metric) => (
                <button
                  key={metric.key}
                  className={`metric-toggle ${selectedMetrics.includes(metric.key) ? "active" : ""}`}
                  onClick={() => toggleMetric(metric.key)}
                  style={{ borderColor: metric.color }}
                >
                  <span className="dot" style={{ background: metric.color }} />
                  {metric.label}
                </button>
              ))}
            </div>
          </div>
          <div ref={timelineChartRef} className="timeline-chart" />
        </article>

        <article className="wp-card panel-animated">
          <h3>Export Data</h3>
          <div className="export-section">
            <div className="export-format">
              <label>Format:</label>
              <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value as any)}>
                <option value="csv">CSV</option>
                <option value="json">JSON</option>
                <option value="png">PNG Chart</option>
              </select>
            </div>
            <button className="export-btn" onClick={handleExport}>
              📥 Download {exportFormat.toUpperCase()}
            </button>
          </div>

          <h3 style={{ marginTop: 20 }}>Quick Stats</h3>
          <div className="quick-stats">
            <div className="stat-row">
              <span>Peak Risk Time</span>
              <strong>
                {historicalData.length
                  ? formatDate(
                      historicalData.reduce((max, d) => (d.risk_score > max.risk_score ? d : max), historicalData[0]).timestamp
                    )
                  : "N/A"}
              </strong>
            </div>
            <div className="stat-row">
              <span>Lowest Risk Time</span>
              <strong>
                {historicalData.length
                  ? formatDate(
                      historicalData.reduce((min, d) => (d.risk_score < min.risk_score ? d : min), historicalData[0]).timestamp
                    )
                  : "N/A"}
              </strong>
            </div>
            <div className="stat-row">
              <span>Volatility</span>
              <strong>
                {historicalData.length
                  ? (
                      Math.sqrt(
                        historicalData.reduce((sum, d) => sum + Math.pow(d.risk_score - (stats?.avgRisk || 0), 2), 0) /
                          historicalData.length
                      ).toFixed(2)
                    )
                  : "0.00"}
              </strong>
            </div>
            <div className="stat-row">
              <span>Avg Context Pressure</span>
              <strong>{stats?.avgContextualPressure.toFixed(2) || "0.00"}</strong>
            </div>
            <div className="stat-row">
              <span>Avg Logistics Stress</span>
              <strong>{stats?.avgLogisticsStress.toFixed(2) || "0.00"}</strong>
            </div>
            <div className="stat-row">
              <span>Avg Evidence Quality</span>
              <strong>{stats?.avgEvidenceQuality.toFixed(2) || "0.00"}</strong>
            </div>
          </div>
        </article>
      </section>

      {/* Event Comparison */}
      <section id="historical-comparison" className="wp-grid">
        <article className="wp-card panel-animated">
          <h2>Compare Past Events</h2>
          <div className="events-list">
            {comparisonEvents.map((event) => (
              <div
                key={event.id}
                className={`event-item ${event.selected ? "selected" : ""}`}
                onClick={() => toggleEventSelection(event.id)}
              >
                <div className="event-checkbox">{event.selected && "✓"}</div>
                <div className="event-info">
                  <div className="event-name">{event.name}</div>
                  <div className="event-date">{formatDate(event.date)}</div>
                  <div className="event-metrics">
                    <span className="risk-badge">Risk: {event.riskScore.toFixed(1)}</span>
                    <span className="sentiment-badge">
                      Sentiment: {event.sentiment > 0 ? "+" : ""}
                      {event.sentiment.toFixed(1)}
                    </span>
                    <span className="sentiment-badge">Context: {event.contextualPressure.toFixed(2)}</span>
                    <span className="sentiment-badge">Logistics: {event.logisticsStress.toFixed(2)}</span>
                  </div>
                  <div className="event-topics">
                    {event.topics.map((topic) => (
                      <span key={topic} className="topic-tag">
                        {topic}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
          <div className="comparison-summary">
            {comparisonEvents.filter((e) => e.selected).length} events selected for comparison
          </div>
        </article>

        <article className="wp-card panel-animated chart-card">
          <h2>Event Comparison Chart</h2>
          {comparisonEvents.filter((e) => e.selected).length >= 2 ? (
            <div ref={comparisonChartRef} className="comparison-chart" />
          ) : (
            <div className="comparison-placeholder">
              <p>Select at least 2 events to compare</p>
            </div>
          )}
        </article>
      </section>

      {/* Data Table */}
      <section id="historical-table" className="wp-grid">
        <article className="wp-card panel-animated data-table-card">
          <h2>Detailed Data Log</h2>
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Risk Score</th>
                  <th>News Sent.</th>
                  <th>GDELT Sent.</th>
                  <th>Crypto</th>
                  <th>Stock</th>
                  <th>Weather</th>
                  <th>Direct Behavior</th>
                  <th>Context Pressure</th>
                  <th>Evidence Quality</th>
                  <th>Narrative Velocity</th>
                  <th>Coordination Risk</th>
                  <th>Logistics Stress</th>
                  <th>Household Stress</th>
                  <th>Energy Stress</th>
                </tr>
              </thead>
              <tbody>
                {historicalData.slice(0, 20).map((row, idx) => (
                  <tr key={idx}>
                    <td>{formatDate(row.timestamp)}</td>
                    <td className={row.risk_score > 75 ? "high-risk" : row.risk_score > 45 ? "med-risk" : "low-risk"}>
                      {row.risk_score.toFixed(1)}
                    </td>
                    <td>{row.news_sentiment.toFixed(1)}</td>
                    <td>{row.gdelt_sentiment.toFixed(1)}</td>
                    <td>{row.crypto_return.toFixed(1)}%</td>
                    <td>{row.stock_return.toFixed(1)}%</td>
                    <td>{row.weather_anomaly.toFixed(1)}</td>
                    <td>{safeN(row.direct_behavior_score).toFixed(2)}</td>
                    <td>{safeN(row.contextual_pressure_score).toFixed(2)}</td>
                    <td>{safeN(row.evidence_quality_score).toFixed(2)}</td>
                    <td>{safeN(row.narrative_velocity_score).toFixed(2)}</td>
                    <td>{safeN(row.coordination_risk_score).toFixed(2)}</td>
                    <td>{safeN(row.logistics_stress_score).toFixed(2)}</td>
                    <td>{safeN(row.household_stress_score).toFixed(2)}</td>
                    <td>{safeN(row.energy_stress_score).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {historicalData.length > 20 && (
            <div className="table-footer">Showing 20 of {historicalData.length} records</div>
          )}
        </article>
      </section>

      <footer className="wp-footer">
        <button onClick={loadData}>Refresh Data</button>
        <button onClick={() => navigate("/dashboard")}>Back to Dashboard</button>
        <button onClick={() => navigate("/trend-prediction")}>Trend Predictions</button>
        <span>Last updated: {new Date().toLocaleTimeString()}</span>
        {error && <span className="err">{error}</span>}
      </footer>
    </main>
  );
}
