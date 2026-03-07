import { useState, useEffect, useCallback, useRef } from "react";
import { 
  Volume2, VolumeX, Maximize2, Minimize2, Mic, ThumbsUp, ThumbsDown, Flag,
  Send, Download, Settings, Bell, TrendingUp, TrendingDown, Minus, 
  MessageSquare, X, Wifi, WifiOff, History,
  Globe, AlertTriangle
} from "lucide-react";

import TypewriterText from "./TypewriterText";
import PulseIndicator from "./PulseIndicator";
import HolographicAvatar from "./HolographicAvatar";
import WorldPulseCore from "./WorldPulseCore";
import MoodIndicator from "./MoodIndicator";
import useSentinel from "./useSentinel";
import TimeSeriesChart from "./TimeSeriesChart";
import "./components.css";
import "./sentinel-hologram.css";



interface SentinelAIProps {
  className?: string;
  onCountryQuery?: (country: string) => void;
}

export default function SentinelAI({ 
  className = "",
  onCountryQuery
}: SentinelAIProps) {
  const { 
    data, isLoading, error, isActive, submitFeedback,
    // Q&A
    qaHistory, isProcessingQA, askQuestion, clearQAHistory,
    // WebSocket
    wsConnected, wsReconnecting,
    // Voice
    isListening, startVoiceListening, stopVoiceListening,
    // Alerts
    alerts, activeAlerts, addAlert, removeAlert, toggleAlert, dismissAlert,
    // Export
    exportAnalysis,
    // Historical
    fetchHistoricalData,
    // Sensitivity
    sensitivity, customThreshold, updateSensitivity, updateCustomThreshold,
    // Memory
    conversationMemory
  } = useSentinel({ threshold: 0.1, enableWebSocket: true });

  const [expanded, setExpanded] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [showPredictive, setShowPredictive] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [feedbackState, setFeedbackState] = useState<"none" | "important" | "false">("none");
  const [reactivePulse, setReactivePulse] = useState(false);
  const prevThreatLevel = useRef<string | null>(null);
  
  // Q&A State
  const [questionInput, setQuestionInput] = useState("");
  const [showQA, setShowQA] = useState(false);
  const qaScrollRef = useRef<HTMLDivElement>(null);
  
  // Historical Data State
  const [historicalData, setHistoricalData] = useState<any>(null);
  const [showHistorical, setShowHistorical] = useState(false);
  
  // Settings State
  const [showSettings, setShowSettings] = useState(false);
  const [newAlertThreshold, setNewAlertThreshold] = useState(75);
  
  // Country Query State
  const [countryInput, setCountryInput] = useState("");



  // Voice synthesis with AI persona
  const speak = useCallback((text: string) => {
    if (!voiceEnabled || !window.speechSynthesis) return;
    
    window.speechSynthesis.cancel();
    setIsSpeaking(true);
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.pitch = 1.0;
    utterance.volume = 0.7;
    
    // Find AI voice
    const voices = window.speechSynthesis.getVoices();
    const aiVoice = voices.find(v => 
      v.name.toLowerCase().includes("google") || 
      v.name.toLowerCase().includes("samantha") ||
      v.name.toLowerCase().includes("fred") ||
      v.lang.startsWith("en-")
    );
    
    if (aiVoice) {
      utterance.voice = aiVoice;
    }
    
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    
    window.speechSynthesis.speak(utterance);
  }, [voiceEnabled]);

  // Speak when new analysis arrives
  useEffect(() => {
    if (data?.analysis_text && isActive && voiceEnabled) {
      speak(data.analysis_text);
    }
  }, [data?.analysis_text, isActive, voiceEnabled, speak]);

  // JARVIS-style threat colors
  const getThreatColor = (level: string) => {
    switch (level) {
      case "critical": return "#ff3366"; // Red
      case "elevated": return "#ff9500"; // Orange
      case "guarded": return "#ffd600"; // Yellow
      default: return "#00e0ff"; // Cyan for stable
    }
  };

  // Reactive expressions - trigger pulse when threat level changes
  useEffect(() => {
    if (data?.threat_level && prevThreatLevel.current !== null) {
      if (prevThreatLevel.current !== data.threat_level) {
        setReactivePulse(true);
        const timer = setTimeout(() => setReactivePulse(false), 800);
        return () => clearTimeout(timer);
      }
    }
    prevThreatLevel.current = data?.threat_level || null;
  }, [data?.threat_level]);

  // Auto-scroll Q&A to bottom
  useEffect(() => {
    if (qaScrollRef.current && showQA) {
      qaScrollRef.current.scrollTop = qaScrollRef.current.scrollHeight;
    }
  }, [qaHistory, showQA]);

  // Load historical data when expanded
  useEffect(() => {
    if (expanded && !historicalData) {
      fetchHistoricalData(7).then(setHistoricalData);
    }
  }, [expanded, historicalData, fetchHistoricalData]);


  // Handle feedback submission
  const handleFeedback = async (type: "important" | "false") => {
    if (!data) return;
    
    setFeedbackState(type);
    
    if (submitFeedback) {
      await submitFeedback({
        eventId: data.timestamp,
        feedbackType: type,
        threatLevel: data.threat_level,
        riskScore: data.risk_score,
        timestamp: new Date().toISOString(),
      });
    }
    
    setTimeout(() => setFeedbackState("none"), 3000);
  };

  // Handle Q&A submission
  const handleAskQuestion = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!questionInput.trim() || isProcessingQA) return;
    
    const question = questionInput.trim();
    setQuestionInput("");
    await askQuestion(question);
  };

  // Handle country query
  const handleCountryQuery = async () => {
    if (!countryInput.trim() || isProcessingQA) return;
    const countryRaw = countryInput.trim();
    const country = countryRaw.length <= 3 ? countryRaw.toUpperCase() : countryRaw;
    setCountryInput("");
    
    if (onCountryQuery) {
      onCountryQuery(country);
    }
    
    await askQuestion(`What's happening in ${country}?`, { country });
  };

  // Handle voice command with visual feedback
  const handleVoiceCommand = () => {
    if (isListening) {
      stopVoiceListening();
    } else {
      startVoiceListening();
    }
  };

  // Add new alert
  const handleAddAlert = () => {
    addAlert({
      threshold: newAlertThreshold,
      condition: "above",
      enabled: true,
    });
    setNewAlertThreshold(75);
  };

  // Get trend icon
  const getTrendIcon = (trend: string) => {
    switch (trend) {
      case "increasing": return <TrendingUp size={16} className="trend-up" />;
      case "decreasing": return <TrendingDown size={16} className="trend-down" />;
      default: return <Minus size={16} className="trend-stable" />;
    }
  };



  if (isLoading) {
    return (
      <div className={`sentinel-hologram ${className}`}>
        <div className="hologram-loading">
          <HolographicAvatar threatLevel="stable" />
          <span className="hologram-text">Initializing...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className={`sentinel-hologram ${className}`}>
        <div className="hologram-loading">
          <HolographicAvatar threatLevel="guarded" />
          <span className="hologram-text">Sentinel data stream unavailable</span>
        </div>
      </div>
    );
  }

  const threatColor = getThreatColor(data?.threat_level || "stable");
  const connectionLabel = wsConnected ? "Live stream connected" : wsReconnecting ? "Reconnecting stream" : "Offline stream";
  const lastUpdateLabel = data?.timestamp ? new Date(data.timestamp).toLocaleTimeString() : "Unknown";
  const activeSignalCount = (data?.active_domains?.length || data?.top_drivers?.length || 0) + (data?.multi_domain_signal ? 1 : 0);
  const leadDriver = data?.top_drivers?.[0]?.display_name || data?.top_drivers?.[0]?.feature || "Cross-domain signals";
  const trendSummary = data?.risk_trend === "increasing"
    ? "Global risk trend: rising"
    : data?.risk_trend === "decreasing"
      ? "Global risk trend: cooling"
      : "Global risk trend: stable";

  return (
    <>
      <div className={`sentinel-hologram ${isActive ? "active" : ""} ${reactivePulse ? "reactive-pulse" : ""} ${className}`}>
        {/* Connection Status */}
        <div className="sentinel-connection-status">
          {wsConnected ? (
            <Wifi size={12} className="status-connected" />
          ) : wsReconnecting ? (
            <WifiOff size={12} className="status-reconnecting" />
          ) : (
            <WifiOff size={12} className="status-disconnected" />
          )}
        </div>

        {/* Mood Indicator - Holographic Badge */}
        <div className="mood-indicator-container" style={{ marginBottom: "8px" }}>
          <MoodIndicator 
            threatLevel={data?.threat_level || "stable"} 
            size="medium"
            showAnimation={true}
          />
        </div>

        {/* Holographic Avatar - Face Projection (Gideon Style) */}
        <div className="hologram-container">
          <span className="holo-corner holo-corner-tl" />
          <span className="holo-corner holo-corner-tr" />
          <span className="holo-corner holo-corner-bl" />
          <span className="holo-corner holo-corner-br" />
          <div className="holo-reticle" />
          <WorldPulseCore
            className="sentinel-face-projection sentinel-world-pulse"
            isSpeaking={isSpeaking || isListening}
            isProcessing={isLoading || isProcessingQA}
            threatLevel={data?.threat_level || "stable"}
            riskScore={data?.risk_score || 0}
            riskTrend={data?.risk_trend || "stable"}
            signalCount={activeSignalCount}
          />
          
          {/* Voice indicator */}
          {(voiceEnabled || isListening) && (
            <div className={`voice-indicator ${isSpeaking || isListening ? "speaking" : ""}`}>
              <Mic size={12} />
              {isListening && <span className="listening-pulse" />}
            </div>
          )}
        </div>



        {/* Analysis Panel */}
        <div 
          className="hologram-panel"
          style={{ borderColor: threatColor }}
        >
          {/* Header */}
          <div className="hologram-header">
            <div className="hologram-header-copy">
              <span className="hologram-label">PREDICTIVE INTELLIGENCE</span>
              <span className="hologram-subtitle">Executive risk synthesis for cross-domain monitoring</span>
            </div>
            <div className="hologram-controls">
              <button 
                onClick={() => setShowQA(!showQA)}
                className={`hologram-btn ${showQA ? "active" : ""}`}
                title="Ask a question"
                aria-label="Toggle Q and A panel"
              >
                <MessageSquare size={14} />
                <span>Ask</span>
              </button>
              <button 
                onClick={() => setVoiceEnabled(!voiceEnabled)}
                className={`hologram-btn ${voiceEnabled ? "active" : ""}`}
                title={voiceEnabled ? "Mute" : "Enable voice"}
                aria-label={voiceEnabled ? "Disable voice output" : "Enable voice output"}
              >
                {voiceEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
                <span>{voiceEnabled ? "Audio" : "Voice"}</span>
              </button>
              <button 
                onClick={() => setExpanded(!expanded)}
                className="hologram-btn"
                aria-label={expanded ? "Collapse Sentinel panel" : "Expand Sentinel panel"}
              >
                {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                <span>{expanded ? "Close" : "Expand"}</span>
              </button>
            </div>
          </div>

          {activeAlerts.length > 0 && (
            <div className="sentinel-alert-rail">
              {activeAlerts.map((alert) => (
                <div key={alert.id} className="sentinel-alert-inline" style={{ borderColor: threatColor }}>
                  <div className="sentinel-alert-copy">
                    <AlertTriangle size={15} style={{ color: threatColor }} />
                    <span className="sentinel-alert-label">Alert</span>
                    <strong>Risk {alert.condition} {alert.threshold}</strong>
                  </div>
                  <button onClick={() => dismissAlert(alert.id)} aria-label="Dismiss risk alert">
                    <X size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="hologram-summary-grid">
            <div className="hologram-summary-card primary">
              <span className="summary-kicker">{trendSummary}</span>
              <strong>{(data?.risk_score || 0).toFixed(0)} / 100</strong>
              <span className="summary-detail">Primary driver: {leadDriver}</span>
            </div>
            <div className="hologram-summary-card">
              <span className="summary-kicker">24h change</span>
              <strong>{(data?.risk_delta || 0) > 0 ? "+" : ""}{(data?.risk_delta || 0).toFixed(1)}</strong>
              <span className="summary-detail">{connectionLabel}</span>
            </div>
            <div className="hologram-summary-card">
              <span className="summary-kicker">Live signals</span>
              <strong>{activeSignalCount}</strong>
              <span className="summary-detail">Confidence {((data?.confidence || 0) * 100).toFixed(0)}%</span>
            </div>
          </div>

          {/* Analysis Text */}
          <div className="hologram-body">
            <div className="hologram-analysis-header">
              <span className="analysis-kicker">Narrative assessment</span>
              <span className="analysis-state" style={{ color: threatColor }}>
                {(data?.threat_level || "stable").toUpperCase()}
              </span>
            </div>
            <TypewriterText 
              text={data?.analysis_text || ""} 
              speed={35}
              className="hologram-analysis"
            />
            
            {showPredictive && data?.risk_trend !== "stable" && (
              <div className="hologram-predictive">
                <TypewriterText 
                  text={`If current trajectory persists, systemic risk may remain ${data?.threat_level || "stable"} over the next 48-72 hours.`}
                  speed={35}
                  className="predictive-text"
                />
              </div>
            )}
          </div>


          {/* Quick Actions */}
          <div className="hologram-quick-actions">
            <button 
              className="quick-action-btn"
              onClick={() => setShowQA(true)}
            >
              <MessageSquare size={12} />
              Ask
            </button>
            <button 
              className="quick-action-btn"
              onClick={handleVoiceCommand}
              style={{ color: isListening ? "#ff3366" : undefined }}
            >
              <Mic size={12} />
              {isListening ? "Listening..." : "Voice"}
            </button>
            <button 
              className="quick-action-btn"
              onClick={() => exportAnalysis("json")}
            >
              <Download size={12} />
              Export
            </button>
            <button 
              className="quick-action-btn"
              onClick={() => setShowSettings(true)}
            >
              <Settings size={12} />
              Settings
            </button>
          </div>


          {/* Footer */}
          <div className="hologram-footer">
            <div className="hologram-status">
              <PulseIndicator threatLevel={data?.threat_level || "stable"} size="small" />
              <span style={{ color: threatColor }}>
                {(data?.threat_level || "stable").toUpperCase()}
              </span>
            </div>
            <span className="hologram-confidence">
              {((data?.confidence || 0) * 100).toFixed(0)}% confidence
            </span>
            <span className="hologram-confidence" title={connectionLabel}>
              {connectionLabel} | {lastUpdateLabel}
            </span>
          </div>


          {/* Predictive Toggle */}
          <button 
            className="hologram-toggle"
            onClick={() => setShowPredictive(!showPredictive)}
          >
            {showPredictive ? "Hide Outlook" : "Show Outlook"}
          </button>

          {/* Learning Feedback Loop */}
          <div className="feedback-panel">
            <div className="feedback-header">
              <Flag size={12} />
              <span>Was this analysis helpful?</span>
            </div>
            <div className="feedback-buttons">
              <button
                className={`feedback-btn ${feedbackState === "important" ? "active-important" : ""}`}
                onClick={() => handleFeedback("important")}
                disabled={feedbackState !== "none"}
              >
                <ThumbsUp size={14} />
                Important
              </button>
              <button
                className={`feedback-btn ${feedbackState === "false" ? "active-false" : ""}`}
                onClick={() => handleFeedback("false")}
                disabled={feedbackState !== "none"}
              >
                <ThumbsDown size={14} />
                False Alert
              </button>
            </div>
            {feedbackState !== "none" && (
              <div className="feedback-status">
                Feedback recorded. The predictive model will incorporate this input.
              </div>
            )}
          </div>

          {/* Memory Indicator */}
          {conversationMemory.length > 0 && (
            <div className="memory-indicator">
              <History size={10} />
              <span>{conversationMemory.length} interactions remembered</span>
            </div>
          )}
        </div>
      </div>

      {/* Q&A Panel */}
      {showQA && (
        <div className="sentinel-qa-panel">
          <div className="qa-header">
            <h4>Ask Predictive Intelligence</h4>
            <button onClick={() => setShowQA(false)}><X size={14} /></button>
          </div>
          <div className="qa-messages" ref={qaScrollRef}>
            {qaHistory.length === 0 ? (
              <div className="qa-empty">
                <p>Ask me about global risk, specific countries, or trends.</p>
                <div className="qa-suggestions">
                  <button onClick={() => askQuestion("What's driving the current risk score?")}>
                    What's driving risk?
                  </button>
                  <button onClick={() => askQuestion("Show me historical trends")}>
                    Historical trends
                  </button>
                  <button onClick={() => askQuestion("Which domains are most active?")}>
                    Active domains
                  </button>
                </div>
              </div>
            ) : (
              qaHistory.map((msg) => (
                <div key={msg.id} className={`qa-message ${msg.role}`}>
                  <div className="qa-bubble">
                    {msg.content}
                  </div>
                  <span className="qa-timestamp">
                    {new Date(msg.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))
            )}
            {isProcessingQA && (
              <div className="qa-message sentinel">
                <div className="qa-bubble processing">
                  <span className="processing-dot" />
                  <span className="processing-dot" />
                  <span className="processing-dot" />
                </div>
              </div>
            )}
          </div>
          <form className="qa-input-form" onSubmit={handleAskQuestion}>
            <input
              type="text"
              value={questionInput}
              onChange={(e) => setQuestionInput(e.target.value)}
              placeholder="Ask a question..."
              disabled={isProcessingQA}
            />
            <button type="submit" disabled={!questionInput.trim() || isProcessingQA}>
              <Send size={14} />
            </button>
          </form>
        </div>
      )}



      {/* Expanded Modal */}
      {expanded && data && (
        <div className="sentinel-modal-overlay" onClick={() => setExpanded(false)}>
          <div className="sentinel-modal holographic" onClick={e => e.stopPropagation()}>
            <div className="sentinel-modal-header">
              <div className="modal-avatar">
                <HolographicAvatar isSpeaking={isSpeaking} threatLevel={data?.threat_level || "stable"} />
              </div>
              <h2>Predictive Intelligence Analysis</h2>
              <div className="modal-header-actions">
                <button 
                  onClick={() => exportAnalysis("json")} 
                  className="hologram-btn"
                  title="Export analysis"
                >
                  <Download size={16} />
                </button>
                <button onClick={() => setExpanded(false)} className="hologram-btn">
                  <Minimize2 size={18} />
                </button>
              </div>
            </div>
            
            <div className="sentinel-modal-content">
              {/* Tab Navigation */}
              <div className="modal-tabs">
                <button 
                  className={!showHistorical ? "active" : ""} 
                  onClick={() => setShowHistorical(false)}
                >
                  Current
                </button>
                <button 
                  className={showHistorical ? "active" : ""} 
                  onClick={() => setShowHistorical(true)}
                >
                  Historical
                </button>
              </div>

              {!showHistorical ? (
                <>
                  <div className="analysis-section">
                    <h3>Current Assessment</h3>
                    <p className="analysis-text">{data?.analysis_text || ""}</p>
                  </div>

                  {/* Country Query Section */}
                  <div className="country-query-section">
                    <h3>Country Analysis</h3>
                    <form className="country-query-input" onSubmit={(e) => {
                      e.preventDefault();
                      void handleCountryQuery();
                    }}>
                      <Globe size={14} />
                      <input
                        type="text"
                        value={countryInput}
                        onChange={(e) => setCountryInput(e.target.value)}
                        placeholder="Enter country code (e.g., USA, CHN)..."
                      />
                      <button type="submit" disabled={!countryInput.trim() || isProcessingQA}>
                        Analyze
                      </button>
                    </form>
                  </div>

                  <div className="drivers-section">
                    <h3>Contributing Factors</h3>
                    <div className="drivers-chart">
                      {(data?.top_drivers || []).map((driver) => (
                        <div key={driver.feature} className="driver-bar-holo">
                          <span className="driver-name">{driver.display_name || driver.feature}</span>
                          <div className="driver-progress">
                            <div 
                              className="driver-fill" 
                              style={{ 
                                width: `${Math.min(driver.impact * 20, 100)}%`,
                                background: `linear-gradient(90deg, ${threatColor}88, ${threatColor})`
                              }}
                            />
                          </div>
                          <span className="driver-value">+{driver.impact.toFixed(1)}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="domains-section">
                    <h3>Active Domains</h3>
                    <div className="domain-pills">
                      {["Geopolitical", "Financial", "Behavioral", "Environmental", "Health"].map((domain) => (
                        <span 
                          key={domain}
                          className={`domain-pill ${data?.active_domains?.includes(domain.toLowerCase()) ? "active" : ""}`}
                          style={{
                            borderColor: data?.active_domains?.includes(domain.toLowerCase()) ? threatColor : undefined,
                            background: data?.active_domains?.includes(domain.toLowerCase()) ? `${threatColor}22` : undefined
                          }}
                        >
                          {domain}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="metrics-section">
                    <div className="holo-metric">
                      <span className="metric-label">Risk Score</span>
                      <span className="metric-value" style={{ color: threatColor }}>
                        {(data?.risk_score || 0).toFixed(1)}
                      </span>
                    </div>
                    <div className="holo-metric">
                      <span className="metric-label">24h Change</span>
                      <span className={`metric-value ${(data?.risk_delta || 0) > 0 ? "negative" : "positive"}`}>
                        {getTrendIcon(data?.risk_trend || "stable")}
                        {(data?.risk_delta || 0) > 0 ? "+" : ""}{(data?.risk_delta || 0).toFixed(1)}
                      </span>
                    </div>
                    <div className="holo-metric">
                      <span className="metric-label">Confidence</span>
                      <span className="metric-value">{((data?.confidence || 0) * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                </>
              ) : (
                <div className="historical-section">
                  <h3>Historical Comparison</h3>
                  {historicalData ? (
                    <div className="historical-comparison">
                      <div className="comparison-stats">
                        <div className="comparison-item">
                          <span className="comparison-label">Current</span>
                          <span className="comparison-value" style={{ color: threatColor }}>
                            {(data?.risk_score || 0).toFixed(1)}
                          </span>
                        </div>
                        <div className="comparison-item">
                          <span className="comparison-label">7 Days Ago</span>
                          <span className="comparison-value">
                            {historicalData.week_ago?.toFixed(1) || "N/A"}
                          </span>
                          {historicalData.week_change_pct !== undefined && (
                            <span className={`comparison-change ${historicalData.week_change_pct > 0 ? "negative" : "positive"}`}>
                              {historicalData.week_change_pct > 0 ? "+" : ""}{historicalData.week_change_pct.toFixed(1)}%
                            </span>
                          )}
                        </div>
                        <div className="comparison-item">
                          <span className="comparison-label">30 Days Ago</span>
                          <span className="comparison-value">
                            {historicalData.month_ago?.toFixed(1) || "N/A"}
                          </span>
                          {historicalData.month_change_pct !== undefined && (
                            <span className={`comparison-change ${historicalData.month_change_pct > 0 ? "negative" : "positive"}`}>
                              {historicalData.month_change_pct > 0 ? "+" : ""}{historicalData.month_change_pct.toFixed(1)}%
                            </span>
                          )}
                        </div>
                      </div>
                      
                      {/* Sentiment Trend Chart */}
                      {historicalData.trend_data && (
                        <div className="sentiment-trend-chart">
                          <h4>Risk Trend (30 Days)</h4>
                          <TimeSeriesChart
                            title="Risk Score Trend"
                            series={[{
                              name: "Risk Score",
                              points: historicalData.trend_data.map((d: any) => ({
                                timestamp: d.timestamp,
                                value: d.risk_score
                              })),
                              color: threatColor
                            }]}
                            className="sentinel-trend-chart"
                          />
                        </div>
                      )}

                    </div>
                  ) : (
                    <div className="historical-loading">Loading historical data...</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}


      {/* Settings Modal */}
      {showSettings && (
        <div className="sentinel-settings-overlay" onClick={() => setShowSettings(false)}>
          <div className="sentinel-settings-modal" onClick={e => e.stopPropagation()}>
            <div className="settings-header">
              <h3>Predictive Intelligence Settings</h3>
              <button onClick={() => setShowSettings(false)}><X size={18} /></button>
            </div>
            
            <div className="settings-content">
              {/* Sensitivity Settings */}
              <div className="settings-section">
                <h4>Alert Sensitivity</h4>
                <div className="sensitivity-options">
                  {(["low", "medium", "high"] as const).map((level) => (
                    <button
                      key={level}
                      className={`sensitivity-btn ${sensitivity === level ? "active" : ""}`}
                      onClick={() => updateSensitivity(level)}
                    >
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </button>
                  ))}
                </div>
                <p className="sensitivity-desc">
                  {sensitivity === "low" && "Fewer alerts, only significant changes"}
                  {sensitivity === "medium" && "Balanced alert frequency"}
                  {sensitivity === "high" && "More alerts, detect subtle changes"}
                </p>
              </div>

              {/* Custom Threshold */}
              <div className="settings-section">
                <h4>Custom Threshold</h4>
                <div className="threshold-input">
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={customThreshold}
                    onChange={(e) => updateCustomThreshold(Number(e.target.value))}
                  />
                  <span>risk points</span>
                </div>
              </div>

              {/* Alert Management */}
              <div className="settings-section">
                <h4>Active Alerts</h4>
                <div className="alerts-list">
                  {alerts.length === 0 ? (
                    <p className="no-alerts">No alerts configured</p>
                  ) : (
                    alerts.map(alert => (
                      <div key={alert.id} className={`alert-item ${alert.enabled ? "enabled" : "disabled"}`}>
                        <div className="alert-info">
                          <Bell size={14} />
                          <span>{alert.condition} {alert.threshold}</span>
                        </div>
                        <div className="alert-actions">
                          <button onClick={() => toggleAlert(alert.id)}>
                            {alert.enabled ? "Disable" : "Enable"}
                          </button>
                          <button onClick={() => removeAlert(alert.id)} className="remove-btn">
                            <X size={14} />
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
                
                {/* Add New Alert */}
                <div className="add-alert-form">
                  <h5>Add New Alert</h5>
                  <div className="add-alert-inputs">
                    <span>Alert when risk is</span>
                    <select 
                      value={newAlertThreshold} 
                      onChange={(e) => setNewAlertThreshold(Number(e.target.value))}
                    >
                      <option value={25}>above 25 (Low)</option>
                      <option value={50}>above 50 (Medium)</option>
                      <option value={75}>above 75 (High)</option>
                      <option value={90}>above 90 (Critical)</option>
                    </select>
                    <button onClick={handleAddAlert}>Add Alert</button>
                  </div>
                </div>
              </div>

              {/* Memory Management */}
              <div className="settings-section">
                <h4>Conversation Memory</h4>
                <p>{conversationMemory.length} interactions stored</p>
                <button 
                  className="clear-memory-btn"
                  onClick={clearQAHistory}
                >
                  Clear History
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

