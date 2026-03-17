import { useState, useEffect, useCallback, useRef } from "react";
import { Heart, Activity, Shield, AlertCircle, Users, Syringe } from "lucide-react";
import { getHealthAlerts, type HealthAlertsData } from "../services/api";

interface HealthAlertStreamProps {
  className?: string;
  maxItems?: number;
  refreshInterval?: number;
}

export default function HealthAlertStream({ 
  className = "", 
  maxItems = 8,
  refreshInterval = 25000 
}: HealthAlertStreamProps) {
  const [data, setData] = useState<HealthAlertsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSeverity, setSelectedSeverity] = useState<"all" | "critical" | "elevated" | "guarded">("all");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await getHealthAlerts(maxItems);
      setData(result);
      setError(null);
    } catch (err) {
      setError("Failed to load health alerts");
      console.error("Error fetching health alerts:", err);
    } finally {
      setLoading(false);
    }
  }, [maxItems]);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, refreshInterval);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData, refreshInterval]);

  const filteredOutbreaks = selectedSeverity === "all" 
    ? data?.outbreaks || []
    : (data?.outbreaks || []).filter(o => o.severity === selectedSeverity);
  const broadenedContextCount = (data?.outbreaks || []).filter(o => Boolean(o.is_broadened_context) || o.context_tag === "older_30d").length;

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case "critical": return "#ef4444";
      case "elevated": return "#f59e0b";
      case "guarded": return "#22c55e";
      default: return "#888";
    }
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case "critical": return <AlertCircle className="w-4 h-4" />;
      case "elevated": return <Activity className="w-4 h-4" />;
      case "guarded": return <Shield className="w-4 h-4" />;
      default: return <Heart className="w-4 h-4" />;
    }
  };

  const formatNumber = (num?: number | null) => {
    if (num === null || num === undefined || Number.isNaN(num)) return "N/A";
    if (num >= 1e6) return `${(num / 1e6).toFixed(1)}M`;
    if (num >= 1e3) return `${(num / 1e3).toFixed(1)}K`;
    return num.toString();
  };

  if (loading) {
    return (
      <div className={`health-alert-stream ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <Heart className="w-5 h-5" style={{ color: "#ec4899" }} />
          <span style={titleStyle}>Health Alert Stream</span>
        </div>
        <div style={loadingStyle}>
          <div style={spinnerStyle} />
          <span style={loadingTextStyle}>Loading health data...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`health-alert-stream ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <Heart className="w-5 h-5" style={{ color: "#ec4899" }} />
          <span style={titleStyle}>Health Alert Stream</span>
        </div>
        <div style={errorStyle}>{error || "No data available"}</div>
      </div>
    );
  }

  return (
    <div className={`health-alert-stream ${className}`} style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <Heart className="w-5 h-5" style={{ color: "#ec4899" }} />
        <span style={titleStyle}>Health Alert Stream</span>
        <div style={liveIndicatorStyle}>
          <span style={liveDotStyle} />
          <span style={liveTextStyle}>LIVE</span>
        </div>
      </div>

      {/* Vaccination Stats */}
      <div style={vaccinationBarStyle}>
        <div style={vaccinationItemStyle}>
          <Syringe className="w-4 h-4" style={{ color: "#ec4899" }} />
          <div style={vaccinationContentStyle}>
            <span style={vaccinationValueStyle}>{data.vaccination.global_coverage.toFixed(1)}%</span>
            <span style={vaccinationLabelStyle}>Global Coverage</span>
          </div>
        </div>
        <div style={vaccinationDividerStyle} />
        <div style={vaccinationItemStyle}>
          <Users className="w-4 h-4" style={{ color: "#ec4899" }} />
          <div style={vaccinationContentStyle}>
            <span style={vaccinationValueStyle}>{formatNumber(data.vaccination.doses_administered)}</span>
            <span style={vaccinationLabelStyle}>Doses Given</span>
          </div>
        </div>
        <div style={vaccinationDividerStyle} />
        <div style={vaccinationItemStyle}>
          <Activity className="w-4 h-4" style={{ color: "#ec4899" }} />
          <div style={vaccinationContentStyle}>
            <span style={vaccinationValueStyle}>{data.total_active}</span>
            <span style={vaccinationLabelStyle}>Active Alerts</span>
          </div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div style={filterContainerStyle}>
        {(["all", "critical", "elevated", "guarded"] as const).map((severity) => (
          <button
            key={severity}
            onClick={() => setSelectedSeverity(severity)}
            style={filterButtonStyle(selectedSeverity === severity, getSeverityColor(severity))}
          >
            {severity === "all" ? "All" : severity.charAt(0).toUpperCase() + severity.slice(1)}
          </button>
        ))}
      </div>


      {broadenedContextCount > 0 ? (
        <div style={contextModeStyle}>
          Broadened context mode active: showing {broadenedContextCount} older health indicators (last 30 days).
        </div>
      ) : null}

      {/* Outbreaks List */}
      <div style={outbreaksContainerStyle}>
        {filteredOutbreaks.length === 0 ? (
          <div style={emptyStyle}>No active health alerts</div>
        ) : (
          filteredOutbreaks.map((outbreak, index) => (
            <div 
              key={outbreak.id} 
              style={{
                ...outbreakCardStyle,
                borderLeftColor: getSeverityColor(outbreak.severity),
                animationDelay: `${index * 100}ms`
              }}
              className="outbreak-card"
            >
              {/* Header */}
              <div style={outbreakHeaderStyle}>
                <div style={severityBadgeStyle(getSeverityColor(outbreak.severity))}>
                  {getSeverityIcon(outbreak.severity)}
                  <span style={{ textTransform: "uppercase", fontSize: "9px", fontWeight: 700 }}>
                    {outbreak.severity}
                  </span>
                </div>
                <span style={statusBadgeStyle(outbreak.status)}>
                  {outbreak.status}
                </span>
              </div>

              {/* Disease Info */}
              <div style={diseaseInfoStyle}>
                <span style={diseaseNameStyle}>{outbreak.disease}</span>
                <span style={diseaseTypeStyle}>{outbreak.type}</span>
              </div>

              {/* Location */}
              <div style={locationStyle}>
                <span style={locationIconStyle}>📍</span>
                <span style={locationTextStyle}>{outbreak.location}</span>
              </div>

              {/* Stats */}
              <div style={statsRowStyle}>
                <div style={statBoxStyle}>
                  <span style={statNumberStyle}>
                    {outbreak.indicator_value_raw ?? formatNumber(outbreak.indicator_value)}
                  </span>
                  <span style={statLabelStyle}>{outbreak.type === "indicator" ? "Indicator" : "Cases"}</span>
                </div>
                <div style={statBoxStyle}>
                  <span style={statNumberStyleRed}>{formatNumber(outbreak.deaths)}</span>
                  <span style={statLabelStyle}>{outbreak.type === "indicator" ? "Deaths (N/A)" : "Deaths"}</span>
                </div>
              </div>

              {/* Description */}
              <p style={descriptionStyle}>{outbreak.description}</p>

              {/* Footer */}
              <div style={outbreakFooterStyle}>
                <span style={sourceStyle}>Source: {outbreak.source}</span>
                <span style={timestampStyle}>
                  {new Date(outbreak.timestamp).toLocaleDateString()}
                  {outbreak.context_tag === "older_30d" || outbreak.is_broadened_context ? (
                    <span style={olderBadgeStyle}>Older 30d</span>
                  ) : null}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div style={footerStyle}>
        <span style={footerTextStyle}>
          Updated {new Date(data.last_updated).toLocaleTimeString()}
        </span>
      </div>

      <style>{`
        @keyframes healthPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.7; }
        }
        
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateX(-10px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        
        .outbreak-card {
          animation: slideIn 0.3s ease forwards;
        }
        
        .outbreak-card:hover {
          background: rgba(236, 72, 153, 0.08);
        }
      `}</style>
    </div>
  );
}

// Styles
const containerStyle: React.CSSProperties = {
  background: "rgba(11, 18, 32, 0.7)",
  border: "1px solid rgba(236, 72, 153, 0.2)",
  borderRadius: "12px",
  padding: "16px",
  backdropFilter: "blur(12px)",
  boxShadow: "0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
  height: "100%",
  display: "flex",
  flexDirection: "column",
};

const headerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  marginBottom: "12px",
  paddingBottom: "12px",
  borderBottom: "1px solid rgba(236, 72, 153, 0.15)",
};

const titleStyle: React.CSSProperties = {
  fontSize: "14px",
  fontWeight: 700,
  color: "#e0f7ff",
  textTransform: "uppercase",
  letterSpacing: "1px",
  flex: 1,
};

const liveIndicatorStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  padding: "4px 10px",
  background: "rgba(236, 72, 153, 0.15)",
  borderRadius: "20px",
  border: "1px solid rgba(236, 72, 153, 0.3)",
};

const liveDotStyle: React.CSSProperties = {
  width: "8px",
  height: "8px",
  background: "#ec4899",
  borderRadius: "50%",
  animation: "healthPulse 2s ease-in-out infinite",
};

const liveTextStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 700,
  color: "#ec4899",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const vaccinationBarStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "12px",
  background: "rgba(236, 72, 153, 0.08)",
  border: "1px solid rgba(236, 72, 153, 0.15)",
  borderRadius: "10px",
  marginBottom: "12px",
};

const vaccinationItemStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flex: 1,
};

const vaccinationContentStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
};

const vaccinationValueStyle: React.CSSProperties = {
  fontSize: "16px",
  fontWeight: 800,
  color: "#e0f7ff",
  fontFamily: "monospace",
};

const vaccinationLabelStyle: React.CSSProperties = {
  fontSize: "9px",
  color: "rgba(180, 230, 255, 0.6)",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const vaccinationDividerStyle: React.CSSProperties = {
  width: "1px",
  height: "30px",
  background: "rgba(236, 72, 153, 0.2)",
};

const filterContainerStyle: React.CSSProperties = {
  display: "flex",
  gap: "6px",
  marginBottom: "12px",
};

const filterButtonStyle = (isActive: boolean, color: string): React.CSSProperties => ({
  padding: "6px 12px",
  background: isActive ? `${color}25` : "rgba(255, 255, 255, 0.05)",
  border: `1px solid ${isActive ? color : "rgba(255, 255, 255, 0.1)"}`,
  borderRadius: "6px",
  color: isActive ? "#e0f7ff" : "rgba(180, 230, 255, 0.6)",
  fontSize: "10px",
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 0.2s ease",
  flex: 1,
});

const outbreaksContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "10px",
  flex: 1,
  overflow: "auto",
};

const outbreakCardStyle: React.CSSProperties = {
  padding: "14px",
  background: "rgba(236, 72, 153, 0.03)",
  border: "1px solid rgba(236, 72, 153, 0.1)",
  borderLeftWidth: "3px",
  borderRadius: "10px",
  transition: "all 0.3s ease",
};

const outbreakHeaderStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "10px",
};

const severityBadgeStyle = (color: string): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: "4px",
  padding: "4px 8px",
  background: `${color}20`,
  borderRadius: "4px",
  color: color,
});

const statusBadgeStyle = (status: string): React.CSSProperties => ({
  padding: "3px 8px",
  background: status === "active" ? "rgba(239, 68, 68, 0.2)" : "rgba(34, 197, 94, 0.2)",
  border: `1px solid ${status === "active" ? "rgba(239, 68, 68, 0.4)" : "rgba(34, 197, 94, 0.4)"}`,
  borderRadius: "4px",
  fontSize: "9px",
  fontWeight: 700,
  color: status === "active" ? "#ef4444" : "#22c55e",
  textTransform: "uppercase",
});

const diseaseInfoStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  marginBottom: "8px",
};

const diseaseNameStyle: React.CSSProperties = {
  fontSize: "14px",
  fontWeight: 700,
  color: "#e0f7ff",
};

const diseaseTypeStyle: React.CSSProperties = {
  padding: "2px 8px",
  background: "rgba(236, 72, 153, 0.15)",
  borderRadius: "4px",
  fontSize: "9px",
  color: "#ec4899",
  textTransform: "uppercase",
};

const locationStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  marginBottom: "10px",
};

const locationIconStyle: React.CSSProperties = {
  fontSize: "12px",
};

const locationTextStyle: React.CSSProperties = {
  fontSize: "12px",
  color: "rgba(180, 230, 255, 0.8)",
};

const statsRowStyle: React.CSSProperties = {
  display: "flex",
  gap: "12px",
  marginBottom: "10px",
};

const statBoxStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  padding: "8px 12px",
  background: "rgba(255, 255, 255, 0.05)",
  borderRadius: "6px",
  flex: 1,
};

const statNumberStyle: React.CSSProperties = {
  fontSize: "16px",
  fontWeight: 700,
  color: "#f59e0b",
  fontFamily: "monospace",
};

const statNumberStyleRed: React.CSSProperties = {
  fontSize: "16px",
  fontWeight: 700,
  color: "#ef4444",
  fontFamily: "monospace",
};

const statLabelStyle: React.CSSProperties = {
  fontSize: "9px",
  color: "rgba(180, 230, 255, 0.5)",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const descriptionStyle: React.CSSProperties = {
  fontSize: "11px",
  color: "rgba(180, 230, 255, 0.7)",
  lineHeight: 1.5,
  margin: "0 0 10px 0",
};

const contextModeStyle: React.CSSProperties = {
  marginBottom: "10px",
  padding: "8px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(56, 189, 248, 0.35)",
  background: "rgba(3, 37, 65, 0.35)",
  color: "rgba(186, 230, 253, 0.95)",
  fontSize: "11px",
  lineHeight: 1.35,
};

const olderBadgeStyle: React.CSSProperties = {
  marginLeft: "8px",
  padding: "2px 6px",
  borderRadius: "999px",
  border: "1px solid rgba(56, 189, 248, 0.45)",
  background: "rgba(2, 132, 199, 0.22)",
  color: "#bae6fd",
  fontSize: "9px",
  fontWeight: 700,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const outbreakFooterStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  paddingTop: "10px",
  borderTop: "1px solid rgba(236, 72, 153, 0.1)",
};

const sourceStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.5)",
};

const timestampStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.4)",
};

const footerStyle: React.CSSProperties = {
  marginTop: "12px",
  paddingTop: "12px",
  borderTop: "1px solid rgba(236, 72, 153, 0.1)",
  textAlign: "center",
};

const footerTextStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.4)",
};

const emptyStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "40px 20px",
  color: "rgba(180, 230, 255, 0.5)",
  fontSize: "12px",
  flex: 1,
};

const loadingStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  padding: "40px 20px",
  gap: "12px",
  flex: 1,
};

const spinnerStyle: React.CSSProperties = {
  width: "32px",
  height: "32px",
  border: "2px solid rgba(236, 72, 153, 0.2)",
  borderTopColor: "#ec4899",
  borderRadius: "50%",
  animation: "spin 1s linear infinite",
};

const loadingTextStyle: React.CSSProperties = {
  fontSize: "12px",
  color: "rgba(180, 230, 255, 0.6)",
};

const errorStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "30px 20px",
  color: "#ef4444",
  fontSize: "12px",
  flex: 1,
};

