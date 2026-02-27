import { useState, useEffect, useCallback, useRef } from "react";
import { DollarSign, TrendingUp, TrendingDown, Percent, Briefcase, Landmark } from "lucide-react";
import { getEconomicIndicators, type EconomicIndicatorsData } from "../services/api";

interface EconomicIndicatorsFeedProps {
  className?: string;
  refreshInterval?: number;
}

export default function EconomicIndicatorsFeed({ 
  className = "", 
  refreshInterval = 20000 
}: EconomicIndicatorsFeedProps) {
  const [data, setData] = useState<EconomicIndicatorsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"currencies" | "indicators" | "releases">("currencies");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await getEconomicIndicators();
      setData(result);
      setError(null);
    } catch (err) {
      setError("Failed to load economic data");
      console.error("Error fetching economic indicators:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(fetchData, refreshInterval);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData, refreshInterval]);

  const getChangeColor = (change: number) => {
    return change >= 0 ? "#22c55e" : "#ef4444";
  };

  const getChangeIcon = (change: number) => {
    return change >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />;
  };

  if (loading) {
    return (
      <div className={`economic-indicators-feed ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <DollarSign className="w-5 h-5" style={{ color: "#22c55e" }} />
          <span style={titleStyle}>Economic Indicators</span>
        </div>
        <div style={loadingStyle}>
          <div style={spinnerStyle} />
          <span style={loadingTextStyle}>Loading economic data...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`economic-indicators-feed ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <DollarSign className="w-5 h-5" style={{ color: "#22c55e" }} />
          <span style={titleStyle}>Economic Indicators</span>
        </div>
        <div style={errorStyle}>{error || "No data available"}</div>
      </div>
    );
  }

  return (
    <div className={`economic-indicators-feed ${className}`} style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <DollarSign className="w-5 h-5" style={{ color: "#22c55e" }} />
        <span style={titleStyle}>Economic Indicators</span>
        <div style={liveIndicatorStyle}>
          <span style={liveDotStyle} />
          <span style={liveTextStyle}>LIVE</span>
        </div>
      </div>

      {/* Tabs */}
      <div style={tabsContainerStyle}>
        {(["currencies", "indicators", "releases"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={tabButtonStyle(activeTab === tab)}
          >
            {tab === "currencies" ? "💱 Currencies" : tab === "indicators" ? "📊 Key Metrics" : "📈 Releases"}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={contentStyle}>
        {activeTab === "currencies" && (
          <div style={currenciesContainerStyle}>
            {data.currency_rates.map((rate, index) => (
              <div key={rate.pair} style={{...currencyCardStyle, animationDelay: `${index * 100}ms`}} className="currency-card">
                <div style={currencyHeaderStyle}>
                  <span style={currencyPairStyle}>{rate.pair}</span>
                  <div style={changeBadgeStyle(getChangeColor(rate.change_24h))}>
                    {getChangeIcon(rate.change_24h)}
                    <span>{rate.change_percent >= 0 ? "+" : ""}{rate.change_percent.toFixed(2)}%</span>
                  </div>
                </div>
                <div style={rateValueStyle}>{rate.rate.toFixed(4)}</div>
                <div style={rateChangeStyle(getChangeColor(rate.change_24h))}>
                  {rate.change_24h >= 0 ? "+" : ""}{rate.change_24h.toFixed(4)}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "indicators" && (
          <div style={indicatorsContainerStyle}>
            {Object.entries(data.key_indicators).map(([key, indicator], index) => (
              <div key={key} style={{...indicatorCardStyle, animationDelay: `${index * 100}ms`}} className="indicator-card">
                <div style={indicatorIconStyle}>
                  {key === "interest_rate" ? <Landmark className="w-5 h-5" /> : 
                   key === "inflation_rate" ? <Percent className="w-5 h-5" /> : 
                   <Briefcase className="w-5 h-5" />}
                </div>
                <div style={indicatorContentStyle}>
                  <div style={indicatorLabelStyle}>
                    {key === "interest_rate" ? "Interest Rate" : 
                     key === "inflation_rate" ? "Inflation Rate" : 
                     "Unemployment"}
                  </div>
                  <div style={indicatorValueStyle}>
                    {indicator.value.toFixed(2)}%
                    <span style={indicatorChangeStyle(getChangeColor(indicator.change))}>
                      {indicator.change >= 0 ? " +" : " "}{indicator.change.toFixed(2)}%
                    </span>
                  </div>
                  <div style={indicatorSourceStyle}>{indicator.source}</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === "releases" && (
          <div style={releasesContainerStyle}>
            {data.economic_releases.length === 0 ? (
              <div style={emptyStyle}>No recent economic releases</div>
            ) : (
              data.economic_releases.map((release, index) => (
                <div key={release.id} style={{...releaseItemStyle, animationDelay: `${index * 100}ms`}} className="release-item">
                  <div style={releaseHeaderStyle}>
                    <span style={releaseIndicatorStyle}>{release.indicator}</span>
                    <span style={releaseDateStyle}>
                      {new Date(release.date).toLocaleDateString()}
                    </span>
                  </div>
                  <div style={releaseValueStyle}>{release.value.toFixed(2)}</div>
                </div>
              ))
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div style={footerStyle}>
        <span style={footerTextStyle}>
          Updated {new Date(data.last_updated).toLocaleTimeString()}
        </span>
      </div>

      <style>{`
        @keyframes economicPulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.7; }
        }
        
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        
        .currency-card, .indicator-card, .release-item {
          animation: slideIn 0.3s ease forwards;
        }
        
        .currency-card:hover {
          background: rgba(34, 197, 94, 0.1);
          border-color: rgba(34, 197, 94, 0.3);
        }
        
        .indicator-card:hover {
          background: rgba(34, 197, 94, 0.08);
        }
        
        .release-item:hover {
          background: rgba(34, 197, 94, 0.08);
        }
      `}</style>
    </div>
  );
}

// Styles
const containerStyle: React.CSSProperties = {
  background: "rgba(11, 18, 32, 0.7)",
  border: "1px solid rgba(34, 197, 94, 0.2)",
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
  borderBottom: "1px solid rgba(34, 197, 94, 0.15)",
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
  background: "rgba(34, 197, 94, 0.15)",
  borderRadius: "20px",
  border: "1px solid rgba(34, 197, 94, 0.3)",
};

const liveDotStyle: React.CSSProperties = {
  width: "8px",
  height: "8px",
  background: "#22c55e",
  borderRadius: "50%",
  animation: "economicPulse 2s ease-in-out infinite",
};

const liveTextStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 700,
  color: "#22c55e",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const tabsContainerStyle: React.CSSProperties = {
  display: "flex",
  gap: "8px",
  marginBottom: "12px",
};

const tabButtonStyle = (isActive: boolean): React.CSSProperties => ({
  padding: "8px 14px",
  background: isActive ? "rgba(34, 197, 94, 0.2)" : "rgba(255, 255, 255, 0.05)",
  border: `1px solid ${isActive ? "rgba(34, 197, 94, 0.4)" : "rgba(255, 255, 255, 0.1)"}`,
  borderRadius: "8px",
  color: isActive ? "#e0f7ff" : "rgba(180, 230, 255, 0.6)",
  fontSize: "12px",
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 0.2s ease",
  flex: 1,
});

const contentStyle: React.CSSProperties = {
  flex: 1,
  overflow: "auto",
};

const currenciesContainerStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(2, 1fr)",
  gap: "10px",
};

const currencyCardStyle: React.CSSProperties = {
  padding: "14px",
  background: "rgba(34, 197, 94, 0.05)",
  border: "1px solid rgba(34, 197, 94, 0.15)",
  borderRadius: "10px",
  transition: "all 0.3s ease",
};

const currencyHeaderStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "8px",
};

const currencyPairStyle: React.CSSProperties = {
  fontSize: "13px",
  fontWeight: 700,
  color: "#e0f7ff",
};

const changeBadgeStyle = (color: string): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: "3px",
  padding: "3px 8px",
  background: `${color}20`,
  borderRadius: "4px",
  fontSize: "10px",
  fontWeight: 600,
  color: color,
});

const rateValueStyle: React.CSSProperties = {
  fontSize: "20px",
  fontWeight: 800,
  color: "#e0f7ff",
  fontFamily: "monospace",
};

const rateChangeStyle = (color: string): React.CSSProperties => ({
  fontSize: "11px",
  color: color,
  marginTop: "4px",
});

const indicatorsContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const indicatorCardStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "14px",
  padding: "14px",
  background: "rgba(34, 197, 94, 0.05)",
  border: "1px solid rgba(34, 197, 94, 0.1)",
  borderRadius: "10px",
  transition: "all 0.3s ease",
};

const indicatorIconStyle: React.CSSProperties = {
  width: "44px",
  height: "44px",
  borderRadius: "10px",
  background: "rgba(34, 197, 94, 0.15)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: "#22c55e",
};

const indicatorContentStyle: React.CSSProperties = {
  flex: 1,
};

const indicatorLabelStyle: React.CSSProperties = {
  fontSize: "12px",
  color: "rgba(180, 230, 255, 0.7)",
  marginBottom: "4px",
};

const indicatorValueStyle: React.CSSProperties = {
  fontSize: "22px",
  fontWeight: 800,
  color: "#e0f7ff",
  fontFamily: "monospace",
  display: "flex",
  alignItems: "center",
  gap: "8px",
};

const indicatorChangeStyle = (color: string): React.CSSProperties => ({
  fontSize: "13px",
  color: color,
  fontWeight: 600,
});

const indicatorSourceStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.5)",
  marginTop: "2px",
};

const releasesContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const releaseItemStyle: React.CSSProperties = {
  padding: "12px",
  background: "rgba(34, 197, 94, 0.05)",
  border: "1px solid rgba(34, 197, 94, 0.1)",
  borderRadius: "8px",
  transition: "all 0.3s ease",
};

const releaseHeaderStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  marginBottom: "6px",
};

const releaseIndicatorStyle: React.CSSProperties = {
  fontSize: "12px",
  fontWeight: 600,
  color: "#e0f7ff",
};

const releaseDateStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.5)",
};

const releaseValueStyle: React.CSSProperties = {
  fontSize: "18px",
  fontWeight: 700,
  color: "#22c55e",
  fontFamily: "monospace",
};

const footerStyle: React.CSSProperties = {
  marginTop: "12px",
  paddingTop: "12px",
  borderTop: "1px solid rgba(34, 197, 94, 0.1)",
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
  border: "2px solid rgba(34, 197, 94, 0.2)",
  borderTopColor: "#22c55e",
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
