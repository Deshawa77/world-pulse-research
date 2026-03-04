import { useState, useEffect, useCallback, useRef } from "react";
import { Bitcoin, TrendingUp, TrendingDown, Activity, BarChart3 } from "lucide-react";
import { getCryptoPulse, type CryptoItem } from "../services/api";

interface CryptoMarketPulseProps {
  className?: string;
  maxItems?: number;
  refreshInterval?: number;
}

export default function CryptoMarketPulse({ 
  className = "", 
  maxItems = 5,
  refreshInterval = 10000 
}: CryptoMarketPulseProps) {
  const [cryptoItems, setCryptoItems] = useState<CryptoItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<string>("");
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchCryptoData = useCallback(async () => {
    try {
      const data = await getCryptoPulse(maxItems);
      setCryptoItems(data.items);
      setLastUpdated(data.last_updated);
      setError(null);
    } catch (err) {
      setError("Failed to load crypto data");
      console.error("Error fetching crypto pulse:", err);
    } finally {
      setLoading(false);
    }
  }, [maxItems]);

  useEffect(() => {
    fetchCryptoData();
    intervalRef.current = setInterval(fetchCryptoData, refreshInterval);
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchCryptoData, refreshInterval]);

  const formatPrice = (price: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    }).format(price);
  };

  const formatMarketCap = (cap: number) => {
    if (cap >= 1e12) return `$${(cap / 1e12).toFixed(2)}T`;
    if (cap >= 1e9) return `$${(cap / 1e9).toFixed(2)}B`;
    if (cap >= 1e6) return `$${(cap / 1e6).toFixed(2)}M`;
    return `$${cap.toFixed(0)}`;
  };

  const formatVolume = (vol: number) => {
    if (vol >= 1e9) return `${(vol / 1e9).toFixed(2)}B`;
    if (vol >= 1e6) return `${(vol / 1e6).toFixed(2)}M`;
    return `${vol.toFixed(0)}`;
  };

  if (loading) {
    return (
      <div className={`crypto-market-pulse ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <Bitcoin className="w-5 h-5" style={{ color: "#f7931a" }} />
          <span style={titleStyle}>Crypto Market Pulse</span>
        </div>
        <div style={loadingStyle}>
          <div style={spinnerStyle} />
          <span style={loadingTextStyle}>Loading market data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={`crypto-market-pulse ${className}`} style={containerStyle}>
        <div style={headerStyle}>
          <Bitcoin className="w-5 h-5" style={{ color: "#f7931a" }} />
          <span style={titleStyle}>Crypto Market Pulse</span>
        </div>
        <div style={errorStyle}>{error}</div>
      </div>
    );
  }

  return (
    <div className={`crypto-market-pulse ${className}`} style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <Bitcoin className="w-5 h-5" style={{ color: "#f7931a" }} />
        <span style={titleStyle}>Crypto Market Pulse</span>
        <div style={liveIndicatorStyle}>
          <span style={liveDotStyle} />
          <span style={liveTextStyle}>LIVE</span>
        </div>
      </div>

      {/* Crypto Items */}
      <div style={itemsContainerStyle}>
        {cryptoItems.map((item, index) => (
          <div 
            key={item.id} 
            style={{
              ...itemStyle,
              animationDelay: `${index * 100}ms`
            }}
            className="crypto-item"
          >
            {/* Coin Info */}
            <div style={coinInfoStyle}>
              <div style={coinIconStyle}>
                <span style={coinSymbolStyle}>{item.symbol}</span>
              </div>
              <div style={coinDetailsStyle}>
                <span style={coinNameStyle}>{item.name}</span>
                <span style={coinIdStyle}>{item.coin_id}</span>
              </div>
            </div>

            {/* Price */}
            <div style={priceSectionStyle}>
              <span style={priceStyle}>{formatPrice(item.price_usd)}</span>
              <div style={changeStyle(item.change_percent >= 0)}>
                {item.change_percent >= 0 ? (
                  <TrendingUp className="w-3 h-3" />
                ) : (
                  <TrendingDown className="w-3 h-3" />
                )}
                <span>{item.change_percent >= 0 ? "+" : ""}{item.change_percent.toFixed(2)}%</span>
              </div>
            </div>

            {/* Stats */}
            <div style={statsStyle}>
              <div style={statItemStyle}>
                <BarChart3 className="w-3 h-3" style={{ color: "#888" }} />
                <span style={statValueStyle}>{formatMarketCap(item.market_cap)}</span>
              </div>
              <div style={statItemStyle}>
                <Activity className="w-3 h-3" style={{ color: "#888" }} />
                <span style={statValueStyle}>{formatVolume(item.volume_24h)}</span>
              </div>
            </div>

            {/* Sparkline */}
            <div style={sparklineContainerStyle}>
              <svg width="60" height="20" style={sparklineSvgStyle}>
                <polyline
                  fill="none"
                  stroke={item.change_percent >= 0 ? "#22c55e" : "#ef4444"}
                  strokeWidth="2"
                  points={item.sparkline.map((price, i) => 
                    `${(i / (item.sparkline.length - 1)) * 60},${20 - ((price - Math.min(...item.sparkline)) / (Math.max(...item.sparkline) - Math.min(...item.sparkline))) * 20}`
                  ).join(' ')}
                />
              </svg>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div style={footerStyle}>
        <span style={footerTextStyle}>
          {cryptoItems.length} assets • Updated {new Date(lastUpdated).toLocaleTimeString()}
        </span>
      </div>

      <style>{`
        @keyframes cryptoPulse {
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
        
        .crypto-item {
          animation: slideIn 0.3s ease forwards;
        }
        
        .crypto-item:hover {
          background: rgba(247, 147, 26, 0.1);
          border-color: rgba(247, 147, 26, 0.3);
        }
      `}</style>
    </div>
  );
}

// Styles
const containerStyle: React.CSSProperties = {
  background: "rgba(11, 18, 32, 0.7)",
  border: "1px solid rgba(247, 147, 26, 0.2)",
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
  marginBottom: "16px",
  paddingBottom: "12px",
  borderBottom: "1px solid rgba(247, 147, 26, 0.15)",
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
  background: "rgba(247, 147, 26, 0.15)",
  borderRadius: "20px",
  border: "1px solid rgba(247, 147, 26, 0.3)",
};

const liveDotStyle: React.CSSProperties = {
  width: "8px",
  height: "8px",
  background: "#f7931a",
  borderRadius: "50%",
  animation: "cryptoPulse 2s ease-in-out infinite",
};

const liveTextStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 700,
  color: "#f7931a",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
};

const itemsContainerStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  flex: 1,
  overflow: "auto",
};

const itemStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 100px 80px 60px",
  alignItems: "center",
  gap: "12px",
  padding: "10px 12px",
  background: "rgba(247, 147, 26, 0.03)",
  border: "1px solid rgba(247, 147, 26, 0.1)",
  borderRadius: "8px",
  transition: "all 0.3s ease",
  cursor: "pointer",
};

const coinInfoStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
};

const coinIconStyle: React.CSSProperties = {
  width: "32px",
  height: "32px",
  borderRadius: "50%",
  background: "rgba(247, 147, 26, 0.15)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  border: "1px solid rgba(247, 147, 26, 0.3)",
};

const coinSymbolStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 800,
  color: "#f7931a",
};

const coinDetailsStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
};

const coinNameStyle: React.CSSProperties = {
  fontSize: "13px",
  fontWeight: 600,
  color: "#e0f7ff",
};

const coinIdStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.5)",
  textTransform: "uppercase",
};

const priceSectionStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  alignItems: "flex-end",
};

const priceStyle: React.CSSProperties = {
  fontSize: "14px",
  fontWeight: 700,
  color: "#e0f7ff",
  fontFamily: "monospace",
};

const changeStyle = (isPositive: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: "4px",
  fontSize: "11px",
  fontWeight: 600,
  color: isPositive ? "#22c55e" : "#ef4444",
});

const statsStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const statItemStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.6)",
};

const statValueStyle: React.CSSProperties = {
  fontFamily: "monospace",
};

const sparklineContainerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const sparklineSvgStyle: React.CSSProperties = {
  overflow: "visible",
};

const footerStyle: React.CSSProperties = {
  marginTop: "12px",
  paddingTop: "12px",
  borderTop: "1px solid rgba(247, 147, 26, 0.1)",
  textAlign: "center",
};

const footerTextStyle: React.CSSProperties = {
  fontSize: "10px",
  color: "rgba(180, 230, 255, 0.4)",
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
  border: "2px solid rgba(247, 147, 26, 0.2)",
  borderTopColor: "#f7931a",
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
