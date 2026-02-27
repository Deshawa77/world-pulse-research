import { useState, useEffect, useCallback, useRef } from "react";
import { TrendingUp, Search, Zap, BarChart3, ArrowUpRight, ArrowDownRight, Minus } from "lucide-react";
import { getTrendsRadar, type TrendsRadarData } from "../services/api";

interface GoogleTrendsRadarProps {
  className?: string;
  maxItems?: number;
  refreshInterval?: number;
}

export default function GoogleTrendsRadar({ 
  className = "", 
  maxItems = 15,
  refreshInterval = 30000 
}: GoogleTrendsRadarProps) {
  const [data, setData] = useState<TrendsRadarData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await getTrendsRadar(maxItems);
      setData(result);
      setError(null);
    } catch (err) {
      setError("Failed to load trends data");
      console.error("Error fetching trends radar:", err);
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

  const categories = data ? ["all", ...new Set(data.trends.map(t => t.category))] : ["all"];

  const filteredTrends = selectedCategory === "all" 
    ? data?.trends || []
    : (data?.trends || []).filter(t => t.category === selectedCategory);

  const getTrendIcon = (direction: string) => {
    switch (direction) {
      case "rising": return <ArrowUpRight className="w-4 h-4" />;
      case "falling": return <ArrowDownRight className="w-4 h-4" />;
      default: return <Minus className="w-4 h-4" />;
    }
  };

  const getTrendColor = (direction: string) => {
    switch (direction) {
      case "rising": return "#22c55e";
      case "falling": return "#ef4444";
      default: return "#888";
    }
  };

  const getVelocityColor = (velocity: number) => {
    if (velocity > 8) return "#ef4444";
    if (velocity > 5) return "#f59e0b";
    if (velocity > 2) return "#22c55e";
    return "#888";
  };

  if (loading) {
    return (
      <div className={`google-trends-radar ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <TrendingUp className="w-5 h-5" style={{ color: "#8b5cf6" }} />
          <span style={titleStyle}>Google Trends Radar</span>
        </div>
        <div style={loadingStyle}>
          <div style={spinnerStyle} />
          <span style={loadingTextStyle}>Loading trends data...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`google-trends-radar ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <TrendingUp className="w-5 h-5" style={{ color: "#8b5cf6" }} />
          <span style={titleStyle}>Google Trends Radar</span>
        </div>
        <div style={errorStyle}>{error || "No data available"}</div>
      </div>
    );
  }

  return (
    <div className={`google-trends-radar ${className}`} style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <TrendingUp className="w-5 h-5" style={{ color: "#8b5cf6" }} />
        <span style={titleStyle}>Google Trends Radar</span>
        <div style={liveIndicatorStyle}>
          <span style={liveDotStyle} />
          <span style={liveTextStyle}>LIVE</span>
        </div>
      </div>

      {/* Summary Stats */}
      <div style={summaryBarStyle}>
        <div style={summaryItemStyle}>
          <span style={summaryValueStyle}>{data.summary.total_trending}</span>
          <span style={summaryLabelStyle}>Trending</span>
        </div>
        <div style={summaryDividerStyle} />
        <div style={summaryItemStyle}>
          <span style={{...summaryValueStyle, color: "#22c55e"}}>{data.summary.rising_topics}</span>
          <span style={summaryLabelStyle}>Rising</span>
        </div>
        <div style={summaryDividerStyle} />
        <div style={summaryItemStyle}>
          <span style={{...summaryValueStyle, color: "#ef4444"}}>{data.summary.breakout_topics}</span>
          <span style={summaryLabelStyle}>Breakout</span>
        </div>
        <div style={summaryDividerStyle} />
        <div style={summaryItemStyle}>
          <span style={summaryValueStyle}>{data.summary.top_category}</span>
          <span style={summaryLabelStyle}>Top Category</span>
        </div>
      </div>

      {/* Category Filter */}
      <div style={categoryFilterStyle}>
        {categories.map((category) => (
          <button
            key={category}
            onClick={() => setSelectedCategory(category)}
            style={categoryButtonStyle(selectedCategory === category)}
          >
            {category === "all" ? "All" : category}
          </button>
        ))}
      </div>

      {/* Trends List */}
      <div style={trendsContainerStyle}>
        {filteredTrends.length === 0 ? (
          <div style={emptyStyle}>No trending topics</div>
        ) : (
          filteredTrends.map((trend, index) => (
            <div 
              key={trend.id} 
              style={{
                ...trendCardStyle,
                animationDelay: `${index * 50}ms`
              }}
              className="trend-card"
            >
              {/* Rank & Breakout Badge */}
              <div style={rankSectionStyle}>
                <span style={rankStyle}>#{index + 1}</span>
                {trend.breakout && (
                  <div style={breakoutBadgeStyle}>
                    <Zap className="w-3 h-3" />
                  </div>
                )}
              </div>

              {/* Trend Info */}
              <div style={trendInfoStyle}>
                <div style={trendHeaderStyle}>
                  <span style={trendTopicStyle}>{trend.topic}</span>
                  <span style={categoryBadgeStyle}>{trend.category}</span>
                </div>
                
                {/* Related Queries */}
                <div style={queriesStyle}>
                  {trend.related_queries.slice(0, 2).map((query, i) => (
                    <span key={i} style={queryTagStyle}>
                      <Search className="w-3 h-3" />
                      {query}
                    </span>
                  ))}
                </div>
              </div>

              {/* Metrics */}
              <div style={metricsStyle}>
                <div style={interestBarContainerStyle}>
                  <div style={interestBarStyle(trend.interest_score)}>
                    <span style={interestScoreStyle}>{trend.interest_score}</span>
                  </div>
                </div>
                
                <div style={velocityRowStyle}>
                  <div style={velocityBadgeStyle(getVelocityColor(trend.velocity))}>
                    <BarChart3 className="w-3 h-3" />
                    <span>{trend.velocity.toFixed(1)}</span>
                  </div>
                  
                  <div style={directionBadgeStyle(getTrendColor(trend.trend_direction))}>
                    {getTrendIcon(trend.trend_direction)}
                    <span style={{ textTransform: "capitalize", fontSize: "9px" }}>
                      {trend.trend_direction}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer */}
      <div style={footerStyle}>
        <span style={footerTextStyle}>
          {filteredTrends.length} topics • Updated {new Date(data.last_updated).toLocaleTimeString()}
        </span>
      </div>

      <style>{`
        @keyframes trendsPulse {
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
        
        @keyframes breakoutGlow {
          0%, 100% { box-shadow: 0 0 5px rgba(239, 68, 68, 0.5); }
          50% { box-shadow: 0 0 20px rgba(239, 68, 68, 0.8); }
        }
        
        .trend-card {
          animation: slideIn 0.3s ease forwards;
        }
        
        .trend-card:hover {
          background: rgba(139, 92, 246, 0.08);
          border-color: rgba(139, 92, 246, 0.3);
        }
      `}</style>
    </div>
  );
}

// Styles
const containerStyle: React.CSSProperties = {
  background: "rgba(11, 18, 32, 0.7)",
  border: "1px solid rgba(139, 92, 246, 0.2)",
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
  borderBottom: "1px solid rgba(139, 92, 246, 0.15)",
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
  background: "rgba(139, 92, 246, 0.15)",
  borderRadius: "20px",
  border: "1px solid rgba(139, 92, 246, 0.3)",
};

const liveDotStyle: React.CSSProperties = {
  width: "8px",
  height: "8px",
  background: "#8b5cf6",
  borderRadius: "50%",
  animation: "trendsPulse 2s ease-in-out infinite",
};

const liveTextStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 700,
  color: "#8b5cf6",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const summaryBarStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "12px",
  background: "rgba(139, 92, 246, 0.08)",
  border: "1px solid rgba(139, 92, 246, 0.15)",
  borderRadius: "10px",
  marginBottom: "12px",
};

const summaryItemStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  flex: 1,
};

const summaryValueStyle: React.CSSProperties = {
  fontSize: "18px",
  fontWeight: 800,
  color: "#e0f7ff",
  fontFamily: "monospace",
};

const summaryLabelStyle: React.CSSProperties = {
  fontSize: "9px",
  color: "rgba(180, 230, 255, 0.6)",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const summaryDividerStyle: React.CSSProperties = {
  width: "1px",
  height: "30px",
  background: "rgba(139, 92, 246, 0.2)",
};

const categoryFilterStyle: React.CSSProperties = {
  display: "flex",
  gap: "6px",
  marginBottom: "12px",
  flexWrap: "wrap",
};


const categoryButtonStyle = (isActive: boolean): React.CSSProperties => ({
  padding: "6px 12px",
  background: isActive ? "rgba(139, 92, 246, 0.2)" : "rgba(255, 255, 255, 0.05)",
  border: `1px solid ${isActive ? "rgba(139, 92, 246, 0.4)" : "rgba(255, 255, 255, 0.1)"}`,
  borderRadius: "6px",
  color: isActive ? "#e0f7ff" : "rgba(180, 230, 255, 0.6)",
  fontSize: "10px",
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 0.2s ease",
});


const trendsContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  flex: 1,
  overflow: "auto",
};

const trendCardStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "50px 1fr 100px",
  alignItems: "center",
  gap: "12px",
  padding: "12px",
  background: "rgba(139, 92, 246, 0.03)",
  border: "1px solid rgba(139, 92, 246, 0.1)",
  borderRadius: "10px",
  transition: "all 0.3s ease",
};

const rankSectionStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "4px",
};

const rankStyle: React.CSSProperties = {
  fontSize: "14px",
  fontWeight: 800,
  color: "rgba(180, 230, 255, 0.5)",
};

const breakoutBadgeStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: "24px",
  height: "24px",
  background: "rgba(239, 68, 68, 0.2)",
  border: "1px solid rgba(239, 68, 68, 0.4)",
  borderRadius: "50%",
  color: "#ef4444",
  animation: "breakoutGlow 2s ease-in-out infinite",
};

const trendInfoStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
  minWidth: 0,
};

const trendHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flexWrap: "wrap",
};

const trendTopicStyle: React.CSSProperties = {
  fontSize: "13px",
  fontWeight: 700,
  color: "#e0f7ff",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const categoryBadgeStyle: React.CSSProperties = {
  padding: "2px 8px",
  background: "rgba(139, 92, 246, 0.15)",
  borderRadius: "4px",
  fontSize: "9px",
  color: "#8b5cf6",
  textTransform: "uppercase",
  whiteSpace: "nowrap",
};

const queriesStyle: React.CSSProperties = {
  display: "flex",
  gap: "6px",
  flexWrap: "wrap",
};

const queryTagStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
  padding: "3px 8px",
  background: "rgba(255, 255, 255, 0.05)",
  borderRadius: "4px",
  fontSize: "9px",
  color: "rgba(180, 230, 255, 0.6)",
};

const metricsStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const interestBarContainerStyle: React.CSSProperties = {
  width: "100%",
  height: "24px",
  background: "rgba(255, 255, 255, 0.05)",
  borderRadius: "4px",
  overflow: "hidden",
  position: "relative",
};

const interestBarStyle = (score: number): React.CSSProperties => ({
  width: `${score}%`,
  height: "100%",
  background: `linear-gradient(90deg, rgba(139, 92, 246, 0.3) 0%, rgba(139, 92, 246, 0.6) 100%)`,
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  paddingRight: "8px",
  transition: "width 0.5s ease",
});

const interestScoreStyle: React.CSSProperties = {
  fontSize: "11px",
  fontWeight: 700,
  color: "#e0f7ff",
  fontFamily: "monospace",
};

const velocityRowStyle: React.CSSProperties = {
  display: "flex",
  gap: "6px",
};

const velocityBadgeStyle = (color: string): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: "4px",
  padding: "3px 8px",
  background: `${color}20`,
  borderRadius: "4px",
  fontSize: "10px",
  fontWeight: 600,
  color: color,
  flex: 1,
  justifyContent: "center",
});

const directionBadgeStyle = (color: string): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: "4px",
  padding: "3px 8px",
  background: `${color}20`,
  borderRadius: "4px",
  fontSize: "10px",
  fontWeight: 600,
  color: color,
  flex: 1,
  justifyContent: "center",
});

const footerStyle: React.CSSProperties = {
  marginTop: "12px",
  paddingTop: "12px",
  borderTop: "1px solid rgba(139, 92, 246, 0.1)",
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
  border: "2px solid rgba(139, 92, 246, 0.2)",
  borderTopColor: "#8b5cf6",
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
