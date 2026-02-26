import { useState, useEffect, useCallback, useRef } from "react";
import { Volume2, VolumeX, Maximize2, Minimize2, Mic, ThumbsUp, ThumbsDown, Flag } from "lucide-react";
import TypewriterText from "./TypewriterText";
import PulseIndicator from "./PulseIndicator";
import HolographicAvatar from "./HolographicAvatar";
import MoodIndicator from "./MoodIndicator";
import useSentinel from "./useSentinel";
import "./components.css";
import "./sentinel-hologram.css";


interface SentinelAIProps {
  className?: string;
}

export default function SentinelAI({ 
  className = ""
}: SentinelAIProps) {
  const { data, isLoading, error, isActive, submitFeedback } = useSentinel({ threshold: 0.1 });

  const [expanded, setExpanded] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  const [showPredictive, setShowPredictive] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [feedbackState, setFeedbackState] = useState<"none" | "important" | "false">("none");
  const [reactivePulse, setReactivePulse] = useState(false);
  const prevThreatLevel = useRef<string | null>(null);


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
    
    // Reset after 3 seconds
    setTimeout(() => setFeedbackState("none"), 3000);
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
    return null;
  }

  const threatColor = getThreatColor(data.threat_level);

  return (
    <>
      <div className={`sentinel-hologram ${isActive ? "active" : ""} ${reactivePulse ? "reactive-pulse" : ""} ${className}`}>
        {/* Mood Indicator - Holographic Badge */}
        <div className="mood-indicator-container" style={{ marginBottom: "8px" }}>
          <MoodIndicator 
            threatLevel={data.threat_level} 
            size="medium"
            showAnimation={true}
          />
        </div>

        {/* Holographic Avatar - JARVIS Style */}
        <div className="hologram-container">
          <HolographicAvatar 
            isSpeaking={isSpeaking} 
            threatLevel={data.threat_level}
          />
          
          {/* Voice indicator */}
          {voiceEnabled && (
            <div className={`voice-indicator ${isSpeaking ? "speaking" : ""}`}>
              <Mic size={12} />
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
            <span className="hologram-label">SENTINEL AI</span>
            <div className="hologram-controls">
              <button 
                onClick={() => setVoiceEnabled(!voiceEnabled)}
                className={`hologram-btn ${voiceEnabled ? "active" : ""}`}
                title={voiceEnabled ? "Mute" : "Enable voice"}
              >
                {voiceEnabled ? <Volume2 size={14} /> : <VolumeX size={14} />}
              </button>
              <button 
                onClick={() => setExpanded(!expanded)}
                className="hologram-btn"
              >
                {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
              </button>
            </div>
          </div>

          {/* Analysis Text */}
          <div className="hologram-body">
            <TypewriterText 
              text={data.analysis_text} 
              speed={35}
              className="hologram-analysis"
            />
            
            {showPredictive && data.risk_trend !== "stable" && (
              <div className="hologram-predictive">
                <TypewriterText 
                  text={`If current trajectory persists, systemic risk may remain ${data.threat_level} over the next 48–72 hours.`}
                  speed={35}
                  className="predictive-text"
                />
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="hologram-footer">
            <div className="hologram-status">
              <PulseIndicator threatLevel={data.threat_level} size="small" />
              <span style={{ color: threatColor }}>
                {data.threat_level.toUpperCase()}
              </span>
            </div>
            <span className="hologram-confidence">
              {(data.confidence * 100).toFixed(0)}% confidence
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
                Feedback recorded. Sentinel AI will learn from this input.
              </div>
            )}
          </div>
        </div>
      </div>


      {/* Expanded Modal */}
      {expanded && (
        <div className="sentinel-modal-overlay" onClick={() => setExpanded(false)}>
          <div className="sentinel-modal holographic" onClick={e => e.stopPropagation()}>
            <div className="sentinel-modal-header">
              <div className="modal-avatar">
                <HolographicAvatar isSpeaking={isSpeaking} threatLevel={data.threat_level} />
              </div>
              <h2>Sentinel Analysis</h2>
              <button onClick={() => setExpanded(false)} className="hologram-btn">
                <Minimize2 size={18} />
              </button>
            </div>
            
            <div className="sentinel-modal-content">
              <div className="analysis-section">
                <h3>Current Assessment</h3>
                <p className="analysis-text">{data.analysis_text}</p>
              </div>

              <div className="drivers-section">
                <h3>Contributing Factors</h3>
                <div className="drivers-chart">
                  {data.top_drivers.map((driver) => (
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
                      className={`domain-pill ${data.active_domains?.includes(domain.toLowerCase()) ? "active" : ""}`}
                      style={{
                        borderColor: data.active_domains?.includes(domain.toLowerCase()) ? threatColor : undefined,
                        background: data.active_domains?.includes(domain.toLowerCase()) ? `${threatColor}22` : undefined
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
                    {data.risk_score.toFixed(1)}
                  </span>
                </div>
                <div className="holo-metric">
                  <span className="metric-label">24h Change</span>
                  <span className={`metric-value ${data.risk_delta > 0 ? "negative" : "positive"}`}>
                    {data.risk_delta > 0 ? "+" : ""}{data.risk_delta.toFixed(1)}
                  </span>
                </div>
                <div className="holo-metric">
                  <span className="metric-label">Trend</span>
                  <span className="metric-value">{data.risk_trend}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
