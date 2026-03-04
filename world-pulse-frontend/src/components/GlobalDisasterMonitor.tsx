import { useState, useEffect, useCallback, useRef } from "react";
import { AlertTriangle, MapPin, Activity, Wind, Waves, Thermometer } from "lucide-react";
import { getDisasterMonitor, type DisasterItem } from "../services/api";

interface GlobalDisasterMonitorProps {
  className?: string;
  maxItems?: number;
  refreshInterval?: number;
}

export default function GlobalDisasterMonitor({ 
  className = "", 
  maxItems = 10,
  refreshInterval = 15000 
}: GlobalDisasterMonitorProps) {
  const [disasterItems, setDisasterItems] = useState<DisasterItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const [selectedType, setSelectedType] = useState<"all" | "earthquake" | "weather">("all");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDisasterData = useCallback(async () => {
    try {
      const data = await getDisasterMonitor(maxItems);
      setDisasterItems(data.items);
      setLastUpdated(data.last_updated);
      setError(null);
    } catch (err) {
      setError("Failed to load disaster data");
      console.error("Error fetching disaster monitor:", err);
    } finally {
      setLoading(false);
    }
  }, [maxItems]);

  useEffect(() => {
    fetchDisasterData();
    intervalRef.current = setInterval(fetchDisasterData, refreshInterval);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchDisasterData, refreshInterval]);

  const filteredItems = selectedType === "all" 
    ? disasterItems 
    : disasterItems.filter(item => item.type === selectedType);

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
      case "critical": return "🔴";
      case "elevated": return "🟡";
      case "guarded": return "🟢";
      default: return "⚪";
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case "earthquake": return <Activity className="w-4 h-4" />;
      case "weather": return <Wind className="w-4 h-4" />;
      default: return <AlertTriangle className="w-4 h-4" />;
    }
  };

  const criticalCount = disasterItems.filter(i => i.severity === "critical").length;
  const elevatedCount = disasterItems.filter(i => i.severity === "elevated").length;

  if (loading) {
    return (
      <div className={`global-disaster-monitor ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <AlertTriangle className="w-5 h-5" style={{ color: "#ef4444" }} />
          <span style={titleStyle}>Global Disaster Monitor</span>
        </div>
        <div style={loadingStyle}>
          <div style={spinnerStyle} />
          <span style={loadingTextStyle}>Loading disaster alerts...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`global-disaster-monitor ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <AlertTriangle className="w-5 h-5" style={{ color: "#ef4444" }} />
          <span style={titleStyle}>Global Disaster Monitor</span>
        </div>
        <div style={errorStyle}>{error}</div>
      </div>
    );
  }

  return (
    <div className={`global-disaster-monitor ${className}`} style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <AlertTriangle className="w-5 h-5" style={{ color: "#ef4444" }} />
        <span style={titleStyle}>Global Disaster Monitor</span>
        <div style={liveIndicatorStyle}>
          <span style={liveDotStyle} />
          <span style={liveTextStyle}>LIVE</span>
        </div>
      </div>

      {/* Stats Bar */}
      <div style={statsBarStyle}>
        <div style={statBadgeStyle("#ef4444")}>
          <span style={statNumberStyle}>{criticalCount}</span>
          <span style={statLabelStyle}>Critical</span>
        </div>
        <div style={statBadgeStyle("#f59e0b")}>
          <span style={statNumberStyle}>{elevatedCount}</span>
          <span style={statLabelStyle}>Elevated</span>
        </div>
        <div style={statBadgeStyle("#22c55e")}>
          <span style={statNumberStyle}>{disasterItems.length - criticalCount - elevatedCount}</span>
          <span style={statLabelStyle}>Guarded</span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div style={filterContainerStyle}>
        {(["all", "earthquake", "weather"] as const).map((type) => (
          <button
            key={type}
            onClick={() => setSelectedType(type)}
            style={filterButtonStyle(selectedType === type)}
          >
            {type === "all" ? "All" : type === "earthquake" ? "🌍 Earthquakes" : "🌪️ Weather"}
          </button>
        ))}
      </div>

      {/* Disaster Items */}
      <div style={itemsContainerStyle}>
        {filteredItems.length === 0 ? (
          <div style={emptyStyle}>No active alerts</div>
        ) : (
          filteredItems.map((item, index) => (
            <div 
              key={item.id} 
              style={{
                ...itemStyle,
                borderLeftColor: getSeverityColor(item.severity),
                animationDelay: `${index * 100}ms`
              }}
              className="disaster-item"
            >
              {/* Icon & Type */}
              <div style={iconContainerStyle}>
                <div style={typeIconStyle(item.type)}>
                  {getTypeIcon(item.type)}
                </div>
                <div style={severityBadgeStyle()}>
                  {getSeverityIcon(item.severity)}
                </div>
              </div>

              {/* Content */}
              <div style={contentStyle}>
                <div style={titleRowStyle}>
                  <span style={itemTitleStyle}>{item.title}</span>
                  <span style={timestampStyle}>
                    {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                </div>

                <div style={locationStyle}>
                  <MapPin className="w-3 h-3" />
                  <span>{item.location}</span>
                </div>

                {/* Type-specific details */}
                {item.type === "earthquake" && (
                  <div style={detailsRowStyle}>
                    <span style={detailBadgeStyle}>Magnitude: {item.magnitude}</span>
                    <span style={detailBadgeStyle}>Depth: {item.depth_km}km</span>
                    {item.tsunami_risk && (
                      <span style={tsunamiBadgeStyle}>
                        <Waves className="w-3 h-3" />
                        Tsunami Risk
                      </span>
                    )}
                  </div>
                )}

                {item.type === "weather" && (
                  <div style={detailsRowStyle}>
                    {item.temperature !== undefined && (
                      <span style={detailBadgeStyle}>
                        <Thermometer className="w-3 h-3" />
                        {item.temperature}°C
                      </span>
                    )}
                    {item.wind_speed !== undefined && (
                      <span style={detailBadgeStyle}>
                        <Wind className="w-3 h-3" />
                        {item.wind_speed} km/h
                      </span>
                    )}
                  </div>
                )}

                {item.description && (
                  <p style={descriptionStyle}>{item.description}</p>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div style={footerStyle}>
        <span style={footerTextStyle}>
          {filteredItems.length} alerts • Updated {new Date(lastUpdated).toLocaleTimeString()}
        </span>
      </div>

      <style>{`
        @keyframes disasterPulse {
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
        
        .disaster-item {
          animation: slideIn 0.3s ease forwards;
        }
        
        .disaster-item:hover {
          background: rgba(239, 68, 68, 0.08);
        }
      `}</style>
    </div>
  );
}

// Styles
const containerStyle: React.CSSProperties = {
  background: "rgba(11, 18, 32, 0.7)",
  border: "1px solid rgba(239, 68, 68, 0.2)",
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
  borderBottom: "1px solid rgba(239, 68, 68, 0.15)",
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
  background: "rgba(239, 68, 68, 0.15)",
  borderRadius: "20px",
  border: "1px solid rgba(239, 68, 68, 0.3)",
};

const liveDotStyle: React.CSSProperties = {
  width: "8px",
  height: "8px",
  background: "#ef4444",
  borderRadius: "50%",
  animation: "disasterPulse 2s ease-in-out infinite",
};

const liveTextStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 700,
  color: "#ef4444",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const statsBarStyle: React.CSSProperties = {
  display: "flex",
  gap: "8px",
  marginBottom: "12px",
};

const statBadgeStyle = (color: string): React.CSSProperties => ({
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  padding: "6px 12px",
  background: `${color}15`,
  border: `1px solid ${color}40`,
  borderRadius: "8px",
  flex: 1,
});

const statNumberStyle: React.CSSProperties = {
  fontSize: "18px",
  fontWeight: 800,
  color: "#e0f7ff",
};

const statLabelStyle: React.CSSProperties = {
  fontSize: "9px",
  color: "rgba(180, 230, 255, 0.6)",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const filterContainerStyle: React.CSSProperties = {
  display: "flex",
  gap: "8px",
  marginBottom: "12px",
};

const filterButtonStyle = (isActive: boolean): React.CSSProperties => ({
  padding: "6px 12px",
  background: isActive ? "rgba(239, 68, 68, 0.2)" : "rgba(255, 255, 255, 0.05)",
  border: `1px solid ${isActive ? "rgba(239, 68, 68, 0.4)" : "rgba(255, 255, 255, 0.1)"}`,
  borderRadius: "6px",
  color: isActive ? "#e0f7ff" : "rgba(180, 230, 255, 0.6)",
  fontSize: "11px",
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 0.2s ease",
});

const itemsContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  flex: 1,
  overflow: "auto",
};

const itemStyle: React.CSSProperties = {
  display: "flex",
  gap: "12px",
  padding: "12px",
  background: "rgba(239, 68, 68, 0.03)",
  border: "1px solid rgba(239, 68, 68, 0.1)",
  borderLeftWidth: "3px",
  borderRadius: "8px",
  transition: "all 0.3s ease",
};

const iconContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "6px",
};

const typeIconStyle = (type: string): React.CSSProperties => ({
  width: "36px",
  height: "36px",
  borderRadius: "50%",
  background: type === "earthquake" ? "rgba(239, 68, 68, 0.15)" : "rgba(59, 130, 246, 0.15)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: type === "earthquake" ? "#ef4444" : "#3b82f6",
  border: `1px solid ${type === "earthquake" ? "rgba(239, 68, 68, 0.3)" : "rgba(59, 130, 246, 0.3)"}`,
});

const severityBadgeStyle = (): React.CSSProperties => ({
  fontSize: "12px",
});

const contentStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};

const titleRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const itemTitleStyle: React.CSSProperties = {
  fontSize: "13px",
  fontWeight: 600,
  color: "#e0f7ff",
};

const timestampStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.5)",
};

const locationStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
  fontSize: "11px",
  color: "rgba(180, 230, 255, 0.7)",
};

const detailsRowStyle: React.CSSProperties = {
  display: "flex",
  gap: "8px",
  flexWrap: "wrap",
};

const detailBadgeStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
  padding: "3px 8px",
  background: "rgba(255, 255, 255, 0.08)",
  borderRadius: "4px",
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.8)",
};

const tsunamiBadgeStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
  padding: "3px 8px",
  background: "rgba(239, 68, 68, 0.2)",
  border: "1px solid rgba(239, 68, 68, 0.4)",
  borderRadius: "4px",
  fontSize: "10px",
  color: "#ef4444",
  fontWeight: 600,
};

const descriptionStyle: React.CSSProperties = {
  fontSize: "11px",
  color: "rgba(180, 230, 255, 0.6)",
  lineHeight: 1.4,
  margin: 0,
};

const footerStyle: React.CSSProperties = {
  marginTop: "12px",
  paddingTop: "12px",
  borderTop: "1px solid rgba(239, 68, 68, 0.1)",
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
  border: "2px solid rgba(239, 68, 68, 0.2)",
  borderTopColor: "#ef4444",
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
