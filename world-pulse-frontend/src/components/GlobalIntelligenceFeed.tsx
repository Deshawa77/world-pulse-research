import { useState, useEffect, useCallback, useRef } from "react";

import {

  Globe,

  TrendingUp,

  AlertCircle,

  Clock,

  ExternalLink,

  X,

  ChevronRight,

  Newspaper,

  Shield,

  Cloud,

  Users,

  Cpu,

  Target,

} from "lucide-react";



import { getGlobalIntelligenceFeed, type IntelligenceFeedItem } from "../services/api";



interface GlobalIntelligenceFeedProps {

  className?: string;

  maxRows?: number;

  refreshInterval?: number;

  selectedCountry?: string | null;

  onClearCountry?: () => void;

  onVisibleItemsChange?: (items: IntelligenceFeedItem[]) => void;

}



const categoryIcons: Record<string, React.ReactNode> = {

  political: <Shield className="w-4 h-4" />,

  economic: <TrendingUp className="w-4 h-4" />,

  social: <Users className="w-4 h-4" />,

  security: <AlertCircle className="w-4 h-4" />,

  environment: <Cloud className="w-4 h-4" />,

  technology: <Cpu className="w-4 h-4" />,

};



function parseFeedTimestamp(value: string): Date | null {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const compactMatch = raw.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z$/);
  const normalized = compactMatch
    ? `${compactMatch[1]}-${compactMatch[2]}-${compactMatch[3]}T${compactMatch[4]}:${compactMatch[5]}:${compactMatch[6]}Z`
    : raw;
  const parsed = new Date(normalized);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

function computeFeedFreshness(item: IntelligenceFeedItem): number {
  const timestamp = parseFeedTimestamp(item.timestamp);
  const now = Date.now();
  const ageHours = timestamp ? Math.max((now - timestamp.getTime()) / 3600000, 0) : 48;
  if (ageHours <= 1) return 1;
  if (ageHours <= 6) return 0.88;
  if (ageHours <= 24) return 0.72;
  if (ageHours <= 72) return 0.55;
  return 0.35;
}

function computeFeedRelevance(item: IntelligenceFeedItem, selectedCountry: string | null): number {
  const recencyScore = computeFeedFreshness(item);
  const countryBoost = selectedCountry && item.country === selectedCountry ? 0.22 : 0;
  const backendScore = Math.max(0, Math.min(Number(item.relevance_score ?? 0), 1));
  const riskScore = Math.max(0, Math.min(item.risk_score / 100, 1));
  return backendScore * 0.45 + recencyScore * 0.45 + riskScore * 0.1 + countryBoost;
}

function selectVisibleFeedItems(items: IntelligenceFeedItem[], maxRows: number, selectedCountry: string | null): IntelligenceFeedItem[] {
  const ranked = [...items].sort((left, right) => {
    const relevanceDelta = computeFeedRelevance(right, selectedCountry) - computeFeedRelevance(left, selectedCountry);
    if (Math.abs(relevanceDelta) > 0.001) {
      return relevanceDelta;
    }
    return (parseFeedTimestamp(right.timestamp)?.getTime() ?? 0) - (parseFeedTimestamp(left.timestamp)?.getTime() ?? 0);
  });

  if (selectedCountry) {
    return ranked.slice(0, maxRows);
  }

  const visible: IntelligenceFeedItem[] = [];
  const seenCountries = new Set<string>();

  for (const item of ranked) {
    if (seenCountries.has(item.country)) {
      continue;
    }
    visible.push(item);
    seenCountries.add(item.country);
    if (visible.length >= maxRows) {
      return visible;
    }
  }

  for (const item of ranked) {
    if (visible.some((existing) => existing.id === item.id)) {
      continue;
    }
    visible.push(item);
    if (visible.length >= maxRows) {
      break;
    }
  }

  return visible;
}

export default function GlobalIntelligenceFeed({

  className = "",

  maxRows = 3,

  refreshInterval = 5000,

  selectedCountry = null,

  onClearCountry,

  onVisibleItemsChange,

}: GlobalIntelligenceFeedProps) {

  const [feedItems, setFeedItems] = useState<IntelligenceFeedItem[]>([]);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const [selectedItem, setSelectedItem] = useState<IntelligenceFeedItem | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);

  const [animatingItems, setAnimatingItems] = useState<Set<string>>(new Set());

  const timeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null);

  const mountedRef = useRef(true);

  const fetchSequenceRef = useRef(0);

  const prevItemsRef = useRef<IntelligenceFeedItem[]>([]);



  useEffect(() => {

    mountedRef.current = true;

    return () => {

      mountedRef.current = false;

      if (timeoutRef.current) {

        window.clearTimeout(timeoutRef.current);

        timeoutRef.current = null;

      }

    };

  }, []);



  const fetchFeed = useCallback(async () => {
    const sequence = ++fetchSequenceRef.current;

    try {
      const data = await getGlobalIntelligenceFeed({
        country: selectedCountry,
        // This panel renders only a few rows; oversized limits can make the backend
        // spend too long inferring countries from recent headlines.
        limit: selectedCountry
          ? Math.max(maxRows * 2, 12)
          : Math.max(maxRows * 4, 20),
      });
      if (!mountedRef.current || fetchSequenceRef.current !== sequence) {
        return;
      }
      const scoped = selectedCountry
        ? data.filter((item) => item.country === selectedCountry)
        : data;
      const visible = selectVisibleFeedItems(scoped, maxRows, selectedCountry);
      const newAnimating = new Set<string>();

      visible.forEach((item, index) => {

        const existing = prevItemsRef.current.find((prev) => prev.id === item.id);

        if (!existing && index < maxRows) {

          newAnimating.add(item.id);

        }

      });



      if (newAnimating.size > 0) {

        setAnimatingItems(newAnimating);

        window.setTimeout(() => {
          if (mountedRef.current && fetchSequenceRef.current === sequence) {
            setAnimatingItems(new Set());
          }
        }, 600);

      }



      prevItemsRef.current = visible;

      setFeedItems(visible);

      onVisibleItemsChange?.(visible);

      setError(null);

    } catch (err) {

      console.error("Error fetching intelligence feed:", err);

      if (!mountedRef.current || fetchSequenceRef.current !== sequence) {
        return;
      }

      if (prevItemsRef.current.length === 0) {
        setError("Failed to load intelligence feed");
        onVisibleItemsChange?.([]);
      }

    } finally {

      if (mountedRef.current && fetchSequenceRef.current === sequence) {
        setLoading(false);
      }

    }

  }, [maxRows, onVisibleItemsChange, selectedCountry]);



  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      await fetchFeed();
      if (cancelled) {
        return;
      }
      timeoutRef.current = window.setTimeout(() => {
        void run();
      }, refreshInterval);
    };

    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    setLoading(true);
    void run();

    return () => {
      cancelled = true;

      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }

    };

  }, [fetchFeed, refreshInterval]);



  useEffect(() => {

    if (!selectedItem) return;

    const stillVisible = feedItems.some((item) => item.id === selectedItem.id);

    if (!stillVisible) {

      setIsModalOpen(false);

      setSelectedItem(null);

    }

  }, [feedItems, selectedItem]);



  const handleRowClick = (item: IntelligenceFeedItem) => {

    setSelectedItem(item);

    setIsModalOpen(true);

  };



  const closeModal = () => {

    setIsModalOpen(false);

    setTimeout(() => setSelectedItem(null), 300);

  };



  const getRiskColor = (score: number) => {

    if (score >= 75) return "#ff4757";

    if (score >= 50) return "#ff6b6b";

    if (score >= 25) return "#ffe66d";

    return "#2ecc71";

  };



  const getRiskLabel = (score: number) => {

    if (score >= 75) return "Critical";

    if (score >= 50) return "Elevated";

    if (score >= 25) return "Guarded";

    return "Stable";

  };



  const formatTime = (timestamp: string) => {

    const date = parseFeedTimestamp(timestamp);

    if (!date) return "Unknown time";

    const now = new Date();

    const diff = Math.floor((now.getTime() - date.getTime()) / 1000);



    if (diff < 60) return "Just now";

    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;

    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;

    return date.toLocaleDateString();

  };



  const title = selectedCountry

    ? `Country Intelligence Feed (${selectedCountry})`

    : "Global Intelligence Feed";



  if (loading) {

    return (

      <div className={`global-intelligence-feed ${className}`} style={containerStyle}>

        <div style={headerStyle}>

          <Globe className="w-5 h-5" style={{ color: "#00e0ff" }} />

          <span style={titleStyle}>{title}</span>

        </div>

        <div style={loadingStyle}>

          <div style={spinnerStyle} />

          <span style={loadingTextStyle}>Loading intelligence data...</span>

        </div>

      </div>

    );

  }



  if (error) {

    return (

      <div className={`global-intelligence-feed ${className}`} style={containerStyle}>

        <div style={headerStyle}>

          <Globe className="w-5 h-5" style={{ color: "#00e0ff" }} />

          <span style={titleStyle}>{title}</span>

        </div>

        <div style={errorStyle}>

          <AlertCircle className="w-5 h-5" style={{ color: "#ff4757" }} />

          <span style={errorTextStyle}>{error}</span>

        </div>

      </div>

    );

  }



  return (

    <>

      <div className={`global-intelligence-feed ${className}`} style={containerStyle}>

        <div style={headerStyle}>

          <Globe className="w-5 h-5" style={{ color: "#00e0ff" }} />

          <span style={titleStyle}>{title}</span>

          {selectedCountry ? (

            <button onClick={onClearCountry} style={focusResetButtonStyle}>

              <Target className="w-4 h-4" />

              Clear Focus

            </button>

          ) : null}

          <div style={liveIndicatorStyle}>

            <span style={liveDotStyle} />

            <span style={liveTextStyle}>LIVE</span>

          </div>

        </div>



        <div style={feedContainerStyle}>

          {feedItems.length === 0 ? (

            <div style={emptyStateStyle}>

              <AlertCircle className="w-5 h-5" style={{ color: "#f97316" }} />

              <span>

                {selectedCountry

                  ? `No latest country-specific headlines for ${selectedCountry}.`

                  : "No intelligence feed items available."}

              </span>

            </div>

          ) : null}



          {feedItems.map((item, index) => {

            const isAnimating = animatingItems.has(item.id);

            const delay = `${index * 200}ms`;

            const rowAnimationStyle: React.CSSProperties = isAnimating

              ? {

                  animation: `hologramPop 0.6s ${delay} cubic-bezier(0.34, 1.56, 0.64, 1) forwards, glowPulse 2s ${delay} ease-in-out`,

                }

              : {};



            return (

              <div

                key={item.id}

                onClick={() => handleRowClick(item)}

                style={{

                  ...rowStyle,

                  ...(isAnimating ? rowAnimationStyle : {}),

                  borderLeftColor: getRiskColor(item.risk_score),

                }}

                className="intelligence-row"

              >

                <div style={countrySectionStyle}>

                  <div style={flagContainerStyle}>

                    <span style={flagStyle}>{getCountryFlag(item.country)}</span>

                  </div>

                  <div style={countryInfoStyle}>

                    <span style={countryCodeStyle}>{item.country}</span>

                    <span style={countryNameStyle}>{item.country_name}</span>

                  </div>

                </div>



                <div style={contentSectionStyle}>

                  <div style={headlineStyle}>

                    <span style={categoryIconStyle} title={item.category}>

                      {categoryIcons[item.category] || <Newspaper className="w-4 h-4" />}

                    </span>

                    <span style={headlineTextStyle}>{item.headline}</span>

                  </div>

                  <p style={summaryStyle}>{item.summary}</p>

                </div>



                <div style={metaSectionStyle}>

                  <div style={riskBadgeStyle(getRiskColor(item.risk_score))}>

                    <span style={riskScoreStyle}>{Math.round(item.risk_score)}</span>

                    <span style={riskLabelStyle}>{getRiskLabel(item.risk_score)}</span>

                  </div>

                  <div style={timeStyle}>

                    <Clock className="w-3 h-3" />

                    <span>{formatTime(item.timestamp)}</span>

                  </div>

                  <div style={sourceStyle}>

                    <span>via {item.source}</span>

                  </div>

                </div>



                <div style={clickIndicatorStyle}>

                  <ChevronRight className="w-4 h-4" />

                </div>

              </div>

            );

          })}

        </div>



        <div style={footerStyle}>

          <span style={footerTextStyle}>

            {selectedCountry

              ? `Showing ${feedItems.length} latest headline(s) for ${selectedCountry} | Auto-refresh ${refreshInterval / 1000}s`

              : `Showing ${feedItems.length} latest global rows | Auto-refresh ${refreshInterval / 1000}s`}

          </span>

        </div>

      </div>



      {isModalOpen && selectedItem && (

        <div style={modalOverlayStyle} onClick={closeModal}>

          <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>

            <div style={modalHeaderStyle}>

              <div style={modalHeaderLeftStyle}>

                <span style={modalFlagStyle}>{getCountryFlag(selectedItem.country)}</span>

                <div>

                  <h2 style={modalTitleStyle}>{selectedItem.country_name}</h2>

                  <span style={modalSubtitleStyle}>{selectedItem.country} | {selectedItem.category}</span>

                </div>

              </div>

              <button onClick={closeModal} style={closeButtonStyle}>

                <X className="w-5 h-5" />

              </button>

            </div>



            <div style={riskBannerStyle(getRiskColor(selectedItem.risk_score))}>

              <AlertCircle className="w-5 h-5" />

              <div>

                <span style={riskBannerScoreStyle}>{Math.round(selectedItem.risk_score)}</span>

                <span style={riskBannerLabelStyle}>Risk Score: {getRiskLabel(selectedItem.risk_score)}</span>

              </div>

            </div>



            <div style={modalBodyStyle}>

              <h3 style={articleHeadlineStyle}>{selectedItem.headline}</h3>

              <div style={articleMetaStyle}>

                <span style={articleSourceStyle}>

                  <Newspaper className="w-4 h-4" />

                  Source: {selectedItem.source}

                </span>

                <span style={articleTimeStyle}>

                  <Clock className="w-4 h-4" />

                  {(parseFeedTimestamp(selectedItem.timestamp) ?? new Date()).toLocaleString()}

                </span>

              </div>

              <div style={articleContentStyle}>

                {selectedItem.full_article.split("\n\n").map((paragraph, idx) => (

                  <p key={idx} style={paragraphStyle}>{paragraph}</p>

                ))}

              </div>

            </div>



            <div style={modalFooterStyle}>

              <a href={selectedItem.source_url} target="_blank" rel="noopener noreferrer" style={sourceLinkStyle}>

                <ExternalLink className="w-4 h-4" />

                Visit Source Website

              </a>

              <button onClick={closeModal} style={closeModalButtonStyle}>

                Close

              </button>

            </div>

          </div>

        </div>

      )}



      <style>{`

        @keyframes hologramPop {

          0% { opacity: 0; transform: translateY(20px) scale(0.95); }

          50% { opacity: 1; transform: translateY(-5px) scale(1.02); }

          100% { opacity: 1; transform: translateY(0) scale(1); }

        }

        @keyframes glowPulse {

          0%, 100% { box-shadow: 0 0 5px rgba(255, 71, 87, 0.25); }

          50% { box-shadow: 0 0 18px rgba(255, 71, 87, 0.45), 0 0 30px rgba(255, 71, 87, 0.25); }

        }

        @keyframes livePulse {

          0%, 100% { opacity: 1; transform: scale(1); }

          50% { opacity: 0.5; transform: scale(1.2); }

        }

        .intelligence-row { will-change: transform, opacity; }

        .intelligence-row:hover {

          transform: translateX(4px) scale(1.01);

          background: rgba(255, 71, 87, 0.08);

          border-color: rgba(255, 71, 87, 0.35);

        }

      `}</style>

    </>

  );

}



function getCountryFlag(countryCode: string): string {

  const codePoints = countryCode

    .toUpperCase()

    .slice(0, 2)

    .split("")

    .map((char) => 127397 + char.charCodeAt(0));

  return String.fromCodePoint(...codePoints);

}



const containerStyle: React.CSSProperties = {

  background: "rgba(11, 18, 32, 0.7)",

  border: "1px solid rgba(0, 224, 255, 0.2)",

  borderRadius: "12px",

  padding: "16px",

  backdropFilter: "blur(12px)",

  boxShadow: "0 8px 32px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.05)",

};



const headerStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "10px",

  marginBottom: "16px",

  paddingBottom: "12px",

  borderBottom: "1px solid rgba(0, 224, 255, 0.15)",

};



const titleStyle: React.CSSProperties = {

  fontSize: "13px",

  fontWeight: 700,

  color: "#e0f7ff",

  textTransform: "uppercase",

  letterSpacing: "1px",

  flex: 1,

};



const focusResetButtonStyle: React.CSSProperties = {

  display: "inline-flex",

  alignItems: "center",

  gap: "6px",

  border: "1px solid rgba(255, 71, 87, 0.45)",

  background: "rgba(255, 71, 87, 0.12)",

  color: "#ffd3d8",

  borderRadius: "8px",

  padding: "4px 10px",

  fontSize: "11px",

  fontWeight: 700,

  cursor: "pointer",

};



const liveIndicatorStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "6px",

  padding: "4px 10px",

  background: "rgba(46, 204, 113, 0.15)",

  borderRadius: "20px",

  border: "1px solid rgba(46, 204, 113, 0.3)",

};



const liveDotStyle: React.CSSProperties = {

  width: "8px",

  height: "8px",

  background: "#2ecc71",

  borderRadius: "50%",

  animation: "livePulse 1.5s ease-in-out infinite",

};



const liveTextStyle: React.CSSProperties = {

  fontSize: "10px",

  fontWeight: 700,

  color: "#2ecc71",

  textTransform: "uppercase",

  letterSpacing: "0.5px",

};



const feedContainerStyle: React.CSSProperties = {

  display: "flex",

  flexDirection: "column",

  gap: "10px",

};



const emptyStateStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "8px",

  padding: "14px",

  borderRadius: "8px",

  border: "1px solid rgba(249, 115, 22, 0.25)",

  background: "rgba(249, 115, 22, 0.08)",

  color: "#ffd2a8",

  fontSize: "12px",

};



const rowStyle: React.CSSProperties = {

  display: "grid",

  gridTemplateColumns: "120px 1fr 140px 30px",

  alignItems: "center",

  gap: "12px",

  padding: "14px 16px",

  background: "rgba(0, 224, 255, 0.03)",

  border: "1px solid rgba(0, 224, 255, 0.1)",

  borderLeftWidth: "4px",

  borderRadius: "10px",

  cursor: "pointer",

  transition: "all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",

  position: "relative",

  overflow: "hidden",

};



const countrySectionStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "10px",

};



const flagContainerStyle: React.CSSProperties = {

  width: "36px",

  height: "36px",

  borderRadius: "50%",

  background: "rgba(0, 224, 255, 0.1)",

  display: "flex",

  alignItems: "center",

  justifyContent: "center",

  border: "1px solid rgba(0, 224, 255, 0.2)",

};



const flagStyle: React.CSSProperties = {

  fontSize: "20px",

  lineHeight: 1,

};



const countryInfoStyle: React.CSSProperties = {

  display: "flex",

  flexDirection: "column",

};



const countryCodeStyle: React.CSSProperties = {

  fontSize: "12px",

  fontWeight: 700,

  color: "#00e0ff",

};



const countryNameStyle: React.CSSProperties = {

  fontSize: "10px",

  color: "rgba(180, 230, 255, 0.6)",

  maxWidth: "70px",

  overflow: "hidden",

  textOverflow: "ellipsis",

  whiteSpace: "nowrap",

};



const contentSectionStyle: React.CSSProperties = {

  display: "flex",

  flexDirection: "column",

  gap: "6px",

  minWidth: 0,

};



const headlineStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "8px",

};



const categoryIconStyle: React.CSSProperties = {

  color: "#00e0ff",

  flexShrink: 0,

};



const headlineTextStyle: React.CSSProperties = {

  fontSize: "13px",

  fontWeight: 600,

  color: "#e0f7ff",

  lineHeight: 1.4,

  overflow: "hidden",

  textOverflow: "ellipsis",

  display: "-webkit-box",

  WebkitLineClamp: 2,

  WebkitBoxOrient: "vertical",

};



const summaryStyle: React.CSSProperties = {

  fontSize: "11px",

  color: "rgba(180, 230, 255, 0.7)",

  lineHeight: 1.5,

  overflow: "hidden",

  textOverflow: "ellipsis",

  display: "-webkit-box",

  WebkitLineClamp: 2,

  WebkitBoxOrient: "vertical",

};



const metaSectionStyle: React.CSSProperties = {

  display: "flex",

  flexDirection: "column",

  alignItems: "flex-end",

  gap: "6px",

};



const riskBadgeStyle = (color: string): React.CSSProperties => ({

  display: "flex",

  alignItems: "center",

  gap: "6px",

  padding: "4px 10px",

  background: `${color}20`,

  border: `1px solid ${color}60`,

  borderRadius: "6px",

});



const riskScoreStyle: React.CSSProperties = {

  fontSize: "14px",

  fontWeight: 800,

  color: "inherit",

};



const riskLabelStyle: React.CSSProperties = {

  fontSize: "10px",

  fontWeight: 600,

  textTransform: "uppercase",

  letterSpacing: "0.5px",

  color: "inherit",

};



const timeStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "4px",

  fontSize: "10px",

  color: "rgba(180, 230, 255, 0.5)",

};



const sourceStyle: React.CSSProperties = {

  fontSize: "9px",

  color: "rgba(180, 230, 255, 0.4)",

  fontStyle: "italic",

};



const clickIndicatorStyle: React.CSSProperties = {

  color: "rgba(0, 224, 255, 0.4)",

  transition: "all 0.3s ease",

};



const footerStyle: React.CSSProperties = {

  marginTop: "12px",

  paddingTop: "12px",

  borderTop: "1px solid rgba(0, 224, 255, 0.1)",

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

};



const spinnerStyle: React.CSSProperties = {

  width: "32px",

  height: "32px",

  border: "2px solid rgba(0, 224, 255, 0.2)",

  borderTopColor: "#00e0ff",

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

  gap: "8px",

  padding: "30px 20px",

  color: "#ff4757",

  fontSize: "12px",

};



const errorTextStyle: React.CSSProperties = {

  color: "#ff4757",

};



const modalOverlayStyle: React.CSSProperties = {

  position: "fixed",

  top: 0,

  left: 0,

  right: 0,

  bottom: 0,

  background: "rgba(0, 0, 0, 0.8)",

  backdropFilter: "blur(8px)",

  display: "flex",

  alignItems: "center",

  justifyContent: "center",

  zIndex: 1000,

  padding: "20px",

  animation: "fadeIn 0.3s ease",

};



const modalContentStyle: React.CSSProperties = {

  background: "rgba(11, 18, 32, 0.95)",

  border: "1px solid rgba(0, 224, 255, 0.3)",

  borderRadius: "16px",

  width: "100%",

  maxWidth: "700px",

  maxHeight: "90vh",

  overflow: "hidden",

  display: "flex",

  flexDirection: "column",

  boxShadow: "0 25px 50px rgba(0, 0, 0, 0.5), 0 0 100px rgba(0, 224, 255, 0.1)",

  animation: "slideUp 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",

};



const modalHeaderStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  justifyContent: "space-between",

  padding: "20px 24px",

  borderBottom: "1px solid rgba(0, 224, 255, 0.15)",

  background: "rgba(0, 224, 255, 0.05)",

};



const modalHeaderLeftStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "12px",

};



const modalFlagStyle: React.CSSProperties = {

  fontSize: "40px",

  lineHeight: 1,

};



const modalTitleStyle: React.CSSProperties = {

  fontSize: "20px",

  fontWeight: 700,

  color: "#e0f7ff",

  margin: 0,

};



const modalSubtitleStyle: React.CSSProperties = {

  fontSize: "12px",

  color: "rgba(180, 230, 255, 0.6)",

  textTransform: "uppercase",

  letterSpacing: "1px",

};



const closeButtonStyle: React.CSSProperties = {

  background: "rgba(255, 71, 87, 0.1)",

  border: "1px solid rgba(255, 71, 87, 0.3)",

  borderRadius: "8px",

  padding: "8px",

  color: "#ff4757",

  cursor: "pointer",

  transition: "all 0.3s ease",

  display: "flex",

  alignItems: "center",

  justifyContent: "center",

};



const riskBannerStyle = (color: string): React.CSSProperties => ({

  display: "flex",

  alignItems: "center",

  gap: "12px",

  padding: "16px 24px",

  background: `${color}15`,

  borderBottom: `1px solid ${color}40`,

  color,

});



const riskBannerScoreStyle: React.CSSProperties = {

  fontSize: "28px",

  fontWeight: 800,

  marginRight: "8px",

};



const riskBannerLabelStyle: React.CSSProperties = {

  fontSize: "14px",

  fontWeight: 600,

  textTransform: "uppercase",

  letterSpacing: "1px",

};



const modalBodyStyle: React.CSSProperties = {

  padding: "24px",

  overflowY: "auto",

  flex: 1,

};



const articleHeadlineStyle: React.CSSProperties = {

  fontSize: "22px",

  fontWeight: 700,

  color: "#e0f7ff",

  lineHeight: 1.4,

  marginBottom: "16px",

};



const articleMetaStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "20px",

  marginBottom: "20px",

  paddingBottom: "16px",

  borderBottom: "1px solid rgba(0, 224, 255, 0.1)",

};



const articleSourceStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "6px",

  fontSize: "13px",

  color: "#00e0ff",

  fontWeight: 600,

};



const articleTimeStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "6px",

  fontSize: "13px",

  color: "rgba(180, 230, 255, 0.6)",

};



const articleContentStyle: React.CSSProperties = {

  display: "flex",

  flexDirection: "column",

  gap: "16px",

};



const paragraphStyle: React.CSSProperties = {

  fontSize: "15px",

  lineHeight: 1.8,

  color: "rgba(224, 247, 255, 0.9)",

  margin: 0,

};



const modalFooterStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  justifyContent: "space-between",

  padding: "20px 24px",

  borderTop: "1px solid rgba(0, 224, 255, 0.15)",

  background: "rgba(0, 224, 255, 0.03)",

};



const sourceLinkStyle: React.CSSProperties = {

  display: "flex",

  alignItems: "center",

  gap: "8px",

  padding: "10px 18px",

  background: "rgba(0, 224, 255, 0.1)",

  border: "1px solid rgba(0, 224, 255, 0.3)",

  borderRadius: "8px",

  color: "#00e0ff",

  fontSize: "13px",

  fontWeight: 600,

  textDecoration: "none",

  transition: "all 0.3s ease",

};



const closeModalButtonStyle: React.CSSProperties = {

  padding: "10px 20px",

  background: "rgba(255, 71, 87, 0.1)",

  border: "1px solid rgba(255, 71, 87, 0.3)",

  borderRadius: "8px",

  color: "#ff4757",

  fontSize: "13px",

  fontWeight: 600,

  cursor: "pointer",

  transition: "all 0.3s ease",

};
