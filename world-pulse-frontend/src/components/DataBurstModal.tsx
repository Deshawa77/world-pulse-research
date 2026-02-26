import { useEffect, useState } from "react";
import { X, TrendingUp, AlertCircle, Newspaper, Activity, Globe, Zap } from "lucide-react";
import TimeSeriesChart from "./TimeSeriesChart";
import RiskWaterfallChart from "./RiskWaterfallChart";

interface DataBurstModalProps {
  isOpen: boolean;
  onClose: () => void;
  region: string;
  riskScore: number;
  threatLevel: "stable" | "guarded" | "elevated" | "critical";
  countryData?: {
    alerts: Array<{
      id: string;
      title: string;
      severity: string;
      timestamp: string;
      source: string;
    }>;
    news: Array<{
      id: string;
      headline: string;
      sentiment: number;
      source: string;
      timestamp: string;
    }>;
    metrics: {
      riskHistory: Array<{ timestamp: string; value: number }>;
      sentimentTrend: Array<{ timestamp: string; value: number }>;
      volatilityIndex: number;
      eventCount: number;
    };
  };
}

export default function DataBurstModal({
  isOpen,
  onClose,
  region,
  riskScore,
  threatLevel,
  countryData,
}: DataBurstModalProps) {
  const [animationPhase, setAnimationPhase] = useState<"burst" | "settle" | "stable">("burst");
  const [activeTab, setActiveTab] = useState<"overview" | "alerts" | "news" | "metrics">("overview");

  useEffect(() => {
    if (isOpen) {
      setAnimationPhase("burst");
      const timer1 = setTimeout(() => setAnimationPhase("settle"), 600);
      const timer2 = setTimeout(() => setAnimationPhase("stable"), 1200);
      return () => {
        clearTimeout(timer1);
        clearTimeout(timer2);
      };
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const getThreatColor = () => {
    switch (threatLevel) {
      case "critical": return "#ff3366";
      case "elevated": return "#ff9500";
      case "guarded": return "#ffd600";
      default: return "#00e0ff";
    }
  };

  const threatColor = getThreatColor();

  return (
    <div className="data-burst-overlay" onClick={onClose}>
      <div
        className={`data-burst-modal ${animationPhase}`}
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "relative",
          background: "rgba(11, 18, 32, 0.98)",
          border: `2px solid ${threatColor}`,
          borderRadius: "20px",
          padding: "32px",
          maxWidth: "900px",
          width: "90%",
          maxHeight: "85vh",
          overflow: "auto",
          boxShadow: `
            0 0 100px ${threatColor}40,
            0 0 200px ${threatColor}20,
            inset 0 0 60px ${threatColor}10
          `,
        }}
      >
        {/* Data Burst Animation Effects */}
        <div className="burst-particles">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="burst-particle"
              style={{
                position: "absolute",
                width: "4px",
                height: "4px",
                background: threatColor,
                borderRadius: "50%",
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animation: `burst-particle-${i} 1.5s ease-out forwards`,
                animationDelay: `${i * 50}ms`,
                opacity: animationPhase === "burst" ? 1 : 0,
              }}
            />
          ))}
        </div>

        {/* Energy rings */}
        <div
          className="energy-ring ring-1"
          style={{
            position: "absolute",
            inset: "-20px",
            border: `1px solid ${threatColor}40`,
            borderRadius: "24px",
            animation: "energy-pulse 2s ease-in-out infinite",
          }}
        />
        <div
          className="energy-ring ring-2"
          style={{
            position: "absolute",
            inset: "-40px",
            border: `1px solid ${threatColor}20`,
            borderRadius: "32px",
            animation: "energy-pulse 2s ease-in-out infinite 0.5s",
          }}
        />

        {/* Header */}
        <div className="burst-header" style={{ display: "flex", alignItems: "center", gap: "16px", marginBottom: "24px" }}>
          <div
            className="region-icon"
            style={{
              width: "60px",
              height: "60px",
              borderRadius: "50%",
              background: `linear-gradient(135deg, ${threatColor}40, ${threatColor}20)`,
              border: `2px solid ${threatColor}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: `0 0 30px ${threatColor}60`,
            }}
          >
            <Globe size={28} color={threatColor} />
          </div>
          <div className="region-info" style={{ flex: 1 }}>
            <h2
              style={{
                margin: 0,
                fontSize: "28px",
                fontWeight: 800,
                color: "#fff",
                textTransform: "uppercase",
                letterSpacing: "2px",
                textShadow: `0 0 20px ${threatColor}`,
              }}
            >
              {region}
            </h2>
            <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "8px" }}>
              <span
                style={{
                  padding: "4px 12px",
                  background: `${threatColor}20`,
                  border: `1px solid ${threatColor}`,
                  borderRadius: "12px",
                  color: threatColor,
                  fontSize: "12px",
                  fontWeight: 700,
                  textTransform: "uppercase",
                }}
              >
                {threatLevel}
              </span>
              <span style={{ color: "rgba(255,255,255,0.6)", fontSize: "14px" }}>
                Risk Score: <strong style={{ color: threatColor }}>{riskScore.toFixed(1)}</strong>
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: `1px solid ${threatColor}50`,
              borderRadius: "8px",
              padding: "8px",
              color: threatColor,
              cursor: "pointer",
              transition: "all 0.2s",
            }}
          >
            <X size={24} />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="burst-tabs" style={{ display: "flex", gap: "8px", marginBottom: "24px", borderBottom: `1px solid ${threatColor}30`, paddingBottom: "16px" }}>
          {[
            { id: "overview", label: "Overview", icon: Activity },
            { id: "alerts", label: "Alerts", icon: AlertCircle },
            { id: "news", label: "News", icon: Newspaper },
            { id: "metrics", label: "Metrics", icon: TrendingUp },
          ].map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as any)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "10px 20px",
                  background: activeTab === tab.id ? `${threatColor}20` : "transparent",
                  border: `1px solid ${activeTab === tab.id ? threatColor : "transparent"}`,
                  borderRadius: "8px",
                  color: activeTab === tab.id ? threatColor : "rgba(255,255,255,0.6)",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.2s",
                  textTransform: "uppercase",
                  letterSpacing: "1px",
                }}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Content Area */}
        <div className="burst-content">
          {activeTab === "overview" && (
            <div className="overview-grid" style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "20px" }}>
              {/* Risk Trend Chart */}
              <div
                className="chart-card"
                style={{
                  background: "rgba(0,0,0,0.3)",
                  border: `1px solid ${threatColor}30`,
                  borderRadius: "12px",
                  padding: "20px",
                }}
              >
                <h3 style={{ margin: "0 0 16px 0", color: threatColor, fontSize: "14px", textTransform: "uppercase", letterSpacing: "1px" }}>
                  Risk Trend (24h)
                </h3>
                <TimeSeriesChart
                  title="Risk Trend"
                  series={[{
                    name: "Risk Score",
                    points: countryData?.metrics.riskHistory || [],
                    color: threatColor,
                  }]}
                />
              </div>

              {/* Key Metrics */}
              <div
                className="metrics-card"
                style={{
                  background: "rgba(0,0,0,0.3)",
                  border: `1px solid ${threatColor}30`,
                  borderRadius: "12px",
                  padding: "20px",
                }}
              >
                <h3 style={{ margin: "0 0 16px 0", color: threatColor, fontSize: "14px", textTransform: "uppercase", letterSpacing: "1px" }}>
                  Key Metrics
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "16px" }}>
                  <MetricBox
                    label="Volatility Index"
                    value={countryData?.metrics.volatilityIndex.toFixed(2) || "0.00"}
                    icon={Zap}
                    color={threatColor}
                  />
                  <MetricBox
                    label="Active Events"
                    value={String(countryData?.metrics.eventCount || 0)}
                    icon={AlertCircle}
                    color={threatColor}
                  />
                  <MetricBox
                    label="Sentiment"
                    value="+0.24"
                    icon={Activity}
                    color={threatColor}
                  />
                  <MetricBox
                    label="Trend"
                    value="Rising"
                    icon={TrendingUp}
                    color={threatColor}
                  />
                </div>
              </div>
            </div>
          )}

          {activeTab === "alerts" && (
            <div className="alerts-list" style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {countryData?.alerts.map((alert) => (
                <div
                  key={alert.id}
                  className="alert-item"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "16px",
                    padding: "16px 20px",
                    background: "rgba(255,51,102,0.1)",
                    border: "1px solid rgba(255,51,102,0.3)",
                    borderRadius: "12px",
                    transition: "all 0.2s",
                  }}
                >
                  <AlertCircle size={24} color="#ff3366" />
                  <div style={{ flex: 1 }}>
                    <h4 style={{ margin: "0 0 4px 0", color: "#fff", fontSize: "14px" }}>{alert.title}</h4>
                    <p style={{ margin: 0, color: "rgba(255,255,255,0.5)", fontSize: "12px" }}>
                      {alert.source} • {new Date(alert.timestamp).toLocaleString()}
                    </p>
                  </div>
                  <span
                    style={{
                      padding: "4px 12px",
                      background: "rgba(255,51,102,0.2)",
                      borderRadius: "8px",
                      color: "#ff3366",
                      fontSize: "11px",
                      fontWeight: 700,
                      textTransform: "uppercase",
                    }}
                  >
                    {alert.severity}
                  </span>
                </div>
              ))}
            </div>
          )}

          {activeTab === "news" && (
            <div className="news-grid" style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "16px" }}>
              {countryData?.news.map((item) => (
                <div
                  key={item.id}
                  className="news-card"
                  style={{
                    padding: "16px",
                    background: "rgba(0,0,0,0.3)",
                    border: `1px solid ${threatColor}20`,
                    borderRadius: "12px",
                    transition: "all 0.2s",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
                    <Newspaper size={16} color={threatColor} />
                    <span style={{ color: "rgba(255,255,255,0.5)", fontSize: "11px", textTransform: "uppercase" }}>
                      {item.source}
                    </span>
                  </div>
                  <h4 style={{ margin: "0 0 8px 0", color: "#fff", fontSize: "14px", lineHeight: 1.4 }}>
                    {item.headline}
                  </h4>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span
                      style={{
                        padding: "2px 8px",
                        background: item.sentiment > 0 ? "rgba(0,230,118,0.2)" : "rgba(255,51,102,0.2)",
                        borderRadius: "4px",
                        color: item.sentiment > 0 ? "#00e676" : "#ff3366",
                        fontSize: "11px",
                      }}
                    >
                      {item.sentiment > 0 ? "+" : ""}{item.sentiment.toFixed(2)}
                    </span>
                    <span style={{ color: "rgba(255,255,255,0.4)", fontSize: "11px" }}>
                      {new Date(item.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {activeTab === "metrics" && (
            <div className="metrics-detailed">
              <RiskWaterfallChart
                prevRisk={riskScore - 5}
                currentRisk={riskScore}
                items={[
                  { feature: "Geopolitical", delta: 2.5 },
                  { feature: "Economic", delta: 1.8 },
                  { feature: "Social", delta: 1.2 },
                  { feature: "Environmental", delta: 0.8 },
                  { feature: "Health", delta: 0.5 },
                ]}
                confidence={{ lower: riskScore - 2, upper: riskScore + 2 }}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricBox({ label, value, icon: Icon, color }: { label: string; value: string; icon: any; color: string }) {
  return (
    <div
      style={{
        padding: "16px",
        background: "rgba(0,0,0,0.2)",
        border: `1px solid ${color}30`,
        borderRadius: "10px",
        textAlign: "center",
      }}
    >
      <Icon size={20} color={color} style={{ marginBottom: "8px" }} />
      <div style={{ fontSize: "24px", fontWeight: 800, color: "#fff", marginBottom: "4px" }}>{value}</div>
      <div style={{ fontSize: "11px", color: "rgba(255,255,255,0.5)", textTransform: "uppercase", letterSpacing: "1px" }}>
        {label}
      </div>
    </div>
  );
}
