import { useState, useEffect, useRef, useCallback } from "react";
import API, { API_HEADERS, buildWebSocketAuthUrl } from "../services/api";

const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const deriveWebSocketUrl = (explicitUrl?: string) => {
  if (explicitUrl && explicitUrl.trim().length > 0) return explicitUrl;
  try {
    const parsed = new URL(API_URL);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    parsed.pathname = "/ws/sentinel";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "ws://127.0.0.1:8000/ws/sentinel";
  }
};

const normalizeWebSocketUrl = (url: string) => {
  const normalized = url.trim();
  try {
    const parsed = new URL(normalized);
    const isWsProtocol = parsed.protocol === "ws:" || parsed.protocol === "wss:";
    if (!isWsProtocol) return null;
    return parsed.toString();
  } catch {
    return null;
  }
};

// Type declarations for Web Speech API
declare global {
  interface Window {
    SpeechRecognition: new () => SpeechRecognition;
    webkitSpeechRecognition: new () => SpeechRecognition;
  }
}

interface SpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  [index: number]: SpeechRecognitionResult;
  length: number;
}

interface SpeechRecognitionResult {
  [index: number]: SpeechRecognitionAlternative;
  length: number;
  isFinal: boolean;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
}

interface SpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  start(): void;
  stop(): void;
}

export interface SentinelDriver {
  feature: string;
  impact: number;
  display_name?: string;
}

export interface SentinelData {
  timestamp: string;
  risk_score: number;
  risk_delta: number;
  risk_trend: "increasing" | "decreasing" | "stable";
  threat_level: "stable" | "guarded" | "elevated" | "critical";
  top_drivers: SentinelDriver[];
  multi_domain_signal: boolean;
  active_domains?: string[];
  confidence: number;
  analysis_text: string;
  historical_comparison?: HistoricalComparison;
}

export interface HistoricalComparison {
  current: number;
  week_ago: number;
  month_ago: number;
  week_change_pct: number;
  month_change_pct: number;
  trend_direction: "improving" | "worsening" | "stable";
}

export interface FeedbackData {
  eventId: string;
  feedbackType: "important" | "false";
  threatLevel: string;
  riskScore: number;
  timestamp: string;
  notes?: string;
}

export interface QAMessage {
  id: string;
  role: "user" | "sentinel";
  content: string;
  timestamp: string;
  context?: {
    country?: string;
    topic?: string;
  };
}

export interface AlertConfig {
  id: string;
  threshold: number;
  condition: "above" | "below";
  enabled: boolean;
  triggered?: boolean;
  lastTriggered?: string;
}

export interface VoiceCommand {
  command: string;
  action: string;
  confidence: number;
}

interface UseSentinelOptions {
  threshold?: number;
  pollInterval?: number;
  enableVoice?: boolean;
  enableWebSocket?: boolean;
  webSocketUrl?: string;
  maxHistory?: number;
}

export function useSentinel(options: UseSentinelOptions = {}) {
  const { 
    threshold = 2.0, 
    pollInterval = 5000, 
    enableVoice = false,
    enableWebSocket = true,
    webSocketUrl,
    maxHistory = 50
  } = options;

  const [data, setData] = useState<SentinelData | null>(null);
  const [isActive, setIsActive] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  
  // Q&A State
  const [qaHistory, setQaHistory] = useState<QAMessage[]>([]);
  const [isProcessingQA, setIsProcessingQA] = useState(false);
  
  // WebSocket State
  const [wsConnected, setWsConnected] = useState(false);
  const [wsReconnecting, setWsReconnecting] = useState(false);
  
  // Alert State
  const [alerts, setAlerts] = useState<AlertConfig[]>([]);
  const [activeAlerts, setActiveAlerts] = useState<AlertConfig[]>([]);
  
  // Voice Command State
  const [isListening, setIsListening] = useState(false);
  const [voiceCommands, setVoiceCommands] = useState<VoiceCommand[]>([]);
  const [lastVoiceCommand, setLastVoiceCommand] = useState<VoiceCommand | null>(null);
  
  // Sensitivity Settings
  const [sensitivity, setSensitivity] = useState<"low" | "medium" | "high">("medium");
  const [customThreshold, setCustomThreshold] = useState<number>(threshold);
  
  // Memory/History
  const [conversationMemory, setConversationMemory] = useState<QAMessage[]>([]);
  
  const prevRiskRef = useRef<number | null>(null);
  const voiceSynthesisRef = useRef<SpeechSynthesisUtterance | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const wsShouldReconnectRef = useRef(true);
  const wsConnectingRef = useRef(false);
  const isUnmountedRef = useRef(false);
  const MAX_RECONNECT_ATTEMPTS = 5; // Maximum reconnection attempts before giving up
  
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const mutedAlertUntilRef = useRef<Record<string, number>>({});
  const ALERT_MUTE_MS = 10 * 60 * 1000;
  const resolvedWebSocketUrl = deriveWebSocketUrl(webSocketUrl);

  const isAlertMuted = useCallback((id?: string, signature?: string) => {
    const now = Date.now();
    if (id) {
      const untilById = mutedAlertUntilRef.current[id];
      if (typeof untilById === "number" && untilById > now) return true;
    }
    if (signature) {
      const untilBySig = mutedAlertUntilRef.current[signature];
      if (typeof untilBySig === "number" && untilBySig > now) return true;
    }
    return false;
  }, []);

  // Load saved preferences
  useEffect(() => {
    const saved = localStorage.getItem("sentinel_preferences");
    if (saved) {
      try {
        const prefs = JSON.parse(saved);
        if (prefs.sensitivity) setSensitivity(prefs.sensitivity);
        if (prefs.customThreshold) setCustomThreshold(prefs.customThreshold);
        if (prefs.alerts) setAlerts(prefs.alerts);
        if (prefs.conversationMemory) setConversationMemory(prefs.conversationMemory);
      } catch (e) {
        console.error("Failed to load sentinel preferences:", e);
      }
    }
  }, []);

  // Save preferences
  useEffect(() => {
    const prefs = {
      sensitivity,
      customThreshold,
      alerts,
      conversationMemory: conversationMemory.slice(-20),
    };
    localStorage.setItem("sentinel_preferences", JSON.stringify(prefs));
  }, [sensitivity, customThreshold, alerts, conversationMemory]);

  const checkAlerts = useCallback((riskScore: number) => {
    const nowIso = new Date().toISOString();

    const triggered = alerts.filter((alert) => {
      if (!alert.enabled) return false;
      const shouldTrigger = alert.condition === "above" ? riskScore > alert.threshold : riskScore < alert.threshold;
      return shouldTrigger && !alert.triggered;
    });

    if (triggered.length > 0) {
      setActiveAlerts((prev) => {
        const existing = new Set(prev.map((a) => a.id));
        const next = [...prev];
        for (const alert of triggered) {
          const signature = `${alert.condition}-${alert.threshold}`;
          if (isAlertMuted(alert.id, signature)) {
            continue;
          }
          if (!existing.has(alert.id)) {
            next.push({ ...alert, triggered: true, lastTriggered: nowIso });
          }
        }
        return next;
      });
    }

    setAlerts((prev) =>
      prev.map((alert) => {
        if (!alert.enabled) return { ...alert, triggered: false };
        const shouldTrigger = alert.condition === "above" ? riskScore > alert.threshold : riskScore < alert.threshold;
        if (!shouldTrigger && alert.triggered) {
          return { ...alert, triggered: false };
        }
        if (shouldTrigger && !alert.triggered) {
          return { ...alert, triggered: true, lastTriggered: nowIso };
        }
        return alert;
      }),
    );
  }, [alerts, isAlertMuted]);

  const fetchSentinelData = useCallback(async () => {
    try {
      const response = await API.get("/api/sentinel/latest", {
        headers: API_HEADERS,
      });
      
      const sentinelData: SentinelData = response.data;
      setData(sentinelData);
      setLastUpdate(new Date().toISOString());
      setError(null);

      const currentRisk = sentinelData.risk_score;
      const prevRisk = prevRiskRef.current;
      
      if (prevRisk !== null) {
        const delta = Math.abs(currentRisk - prevRisk);
        const effectiveThreshold = sensitivity === "low" ? customThreshold * 1.5 : 
                                   sensitivity === "high" ? customThreshold * 0.5 : 
                                   customThreshold;
        
        if (delta >= effectiveThreshold) {
          setIsActive(true);
          
          if (enableVoice && window.speechSynthesis) {
            speakAnalysis(sentinelData.analysis_text);
          }
        }
      }
      
      checkAlerts(sentinelData.risk_score);
      
      prevRiskRef.current = currentRisk;
    } catch (err: any) {
      setError(err?.message || "Failed to fetch sentinel data");
      console.error("Sentinel fetch error:", err);
    } finally {
      setIsLoading(false);
    }
  }, [customThreshold, sensitivity, enableVoice, checkAlerts]);

  const speakAnalysis = useCallback((text: string) => {
    if (!window.speechSynthesis) return;
    
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9;
    utterance.pitch = 1.0;
    utterance.volume = 0.8;
    
    const voices = window.speechSynthesis.getVoices();
    const preferredVoice = voices.find(v => 
      v.name.includes("Google US English") || 
      v.name.includes("Samantha") ||
      v.name.includes("Daniel")
    );
    if (preferredVoice) {
      utterance.voice = preferredVoice;
    }
    
    voiceSynthesisRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, []);

  // WebSocket Connection
  const connectWebSocket = useCallback(() => {
    if (
      !enableWebSocket ||
      wsConnectingRef.current ||
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    const validWsUrl = normalizeWebSocketUrl(resolvedWebSocketUrl);
    if (!validWsUrl) {
      setWsConnected(false);
      setWsReconnecting(false);
      setError(`Invalid WebSocket URL: ${resolvedWebSocketUrl}`);
      console.warn("Sentinel WebSocket skipped due to invalid URL:", resolvedWebSocketUrl);
      return;
    }

    try {
      wsConnectingRef.current = true;
      const wsUrl = buildWebSocketAuthUrl(validWsUrl);
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        wsConnectingRef.current = false;
        setWsConnected(true);
        setWsReconnecting(false);
        setError(null);
        reconnectAttemptsRef.current = 0;
        console.log("Sentinel WebSocket connected");
      };
      
      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message.type === "sentinel_update") {
            setData(message.data);
            setLastUpdate(new Date().toISOString());
            checkAlerts(message.data.risk_score);
          } else if (message.type === "alert") {
            const incoming = message.alert as Partial<AlertConfig> | undefined;
            if (!incoming) return;

            const alertId = incoming.id || `${incoming.condition || "alert"}-${incoming.threshold || "na"}`;
            const signature = `${incoming.condition === "below" ? "below" : "above"}-${Number(incoming.threshold ?? 0)}`;
            if (isAlertMuted(alertId, signature)) return;

            setActiveAlerts((prev) => {
              if (prev.some((a) => a.id === alertId || `${a.condition}-${a.threshold}` === signature)) {
                return prev;
              }
              const normalized: AlertConfig = {
                id: alertId,
                threshold: Number(incoming.threshold ?? 0),
                condition: incoming.condition === "below" ? "below" : "above",
                enabled: incoming.enabled ?? true,
                triggered: true,
                lastTriggered: new Date().toISOString(),
              };
              return [...prev, normalized];
            });
          }
        } catch (e) {
          console.error("WebSocket message error:", e);
        }
      };
      
      ws.onclose = () => {
        wsConnectingRef.current = false;
        setWsConnected(false);
        
        // Check if we should reconnect and haven't exceeded max attempts
        if (enableWebSocket && wsShouldReconnectRef.current && !isUnmountedRef.current) {
          if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
            setWsReconnecting(true);
            reconnectAttemptsRef.current += 1;
            const reconnectDelay = Math.min(5000 * reconnectAttemptsRef.current, 30000);
            reconnectTimeoutRef.current = setTimeout(connectWebSocket, reconnectDelay);
          } else {
            // Max attempts reached - stop trying and set error
            console.warn(`Sentinel WebSocket: Max reconnection attempts (${MAX_RECONNECT_ATTEMPTS}) reached. Giving up.`);
            setWsReconnecting(false);
            setError("WebSocket connection failed after multiple attempts. Please refresh the page.");
          }
        }
      };
      
      ws.onerror = (error) => {
        // Don't call ws.close() here as it triggers onclose and creates a loop
        // Just log the error and let onclose handle cleanup
        console.error("WebSocket error:", error);
        wsConnectingRef.current = false;
      };
      
      wsRef.current = ws;
    } catch (err) {
      wsConnectingRef.current = false;
      console.error("Failed to connect WebSocket:", err);
    }
  }, [enableWebSocket, resolvedWebSocketUrl, checkAlerts, isAlertMuted]);

  const disconnectWebSocket = useCallback(() => {
    wsShouldReconnectRef.current = false;
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setWsConnected(false);
  }, []);

  // Q&A Functions
  const askQuestion = useCallback(async (question: string, context?: { country?: string; topic?: string }) => {
    setIsProcessingQA(true);
    
    const userMessage: QAMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      content: question,
      timestamp: new Date().toISOString(),
      context,
    };
    
    setQaHistory(prev => [...prev, userMessage]);
    setConversationMemory(prev => [...prev, userMessage].slice(-maxHistory));
    
    try {
      const response = await API.post("/api/sentinel/qa", {
        question,
        context,
        conversation_history: conversationMemory.slice(-10),
        current_risk: data?.risk_score,
      }, { headers: API_HEADERS });
      
      const sentinelMessage: QAMessage = {
        id: `${Date.now()}-sentinel`,
        role: "sentinel",
        content: response.data.answer || "I'm analyzing that for you...",
        timestamp: new Date().toISOString(),
        context,
      };
      
      setQaHistory(prev => [...prev, sentinelMessage]);
      setConversationMemory(prev => [...prev, sentinelMessage].slice(-maxHistory));
      
      if (enableVoice && response.data.answer) {
        speakAnalysis(response.data.answer);
      }
      
      return response.data;
    } catch (err: any) {
      const errorMessage: QAMessage = {
        id: `${Date.now()}-error`,
        role: "sentinel",
        content: "I'm having trouble processing your question. Please try again.",
        timestamp: new Date().toISOString(),
      };
      setQaHistory(prev => [...prev, errorMessage]);
      throw err;
    } finally {
      setIsProcessingQA(false);
    }
  }, [conversationMemory, data?.risk_score, enableVoice, maxHistory, speakAnalysis]);

  const clearQAHistory = useCallback(() => {
    setQaHistory([]);
  }, []);

  // Voice Commands
  const startVoiceListening = useCallback(() => {
    if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
      console.error("Speech recognition not supported");
      return;
    }
    
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    
    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    
    recognition.onresult = (event: SpeechRecognitionEvent) => {
      const transcript = event.results[0][0].transcript;
      const confidence = event.results[0][0].confidence;

      const command: VoiceCommand = {
        command: transcript,
        action: parseVoiceCommand(transcript),
        confidence,
      };
      
      setVoiceCommands(prev => [...prev, command].slice(-20));
      setLastVoiceCommand(command);
      
      executeVoiceCommand(command);
    };
    
    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      console.error("Speech recognition error:", event.error);
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, []);

  const stopVoiceListening = useCallback(() => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
    }
    setIsListening(false);
  }, []);

  const parseVoiceCommand = (transcript: string): string => {
    const lower = transcript.toLowerCase();
    if (lower.includes("what's happening in") || lower.includes("what is happening in")) {
      return "country_query";
    }
    if (lower.includes("show me") && lower.includes("trend")) {
      return "show_trends";
    }
    if (lower.includes("export") || lower.includes("save")) {
      return "export_analysis";
    }
    if (lower.includes("alert") || lower.includes("notify")) {
      return "set_alert";
    }
    if (lower.includes("refresh") || lower.includes("update")) {
      return "refresh";
    }
    return "unknown";
  };

  const executeVoiceCommand = (command: VoiceCommand) => {
    switch (command.action) {
      case "refresh":
        refresh();
        break;
      case "export_analysis":
        exportAnalysis();
        break;
    }
  };

  // Alert Management
  const addAlert = useCallback((config: Omit<AlertConfig, "id" | "triggered" | "lastTriggered">) => {
    const newAlert: AlertConfig = {
      ...config,
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      triggered: false,
    };
    setAlerts(prev => [...prev, newAlert]);
  }, []);

  const removeAlert = useCallback((id: string) => {
    setAlerts(prev => prev.filter(a => a.id !== id));
  }, []);

  const toggleAlert = useCallback((id: string) => {
    setAlerts(prev => prev.map(a => 
      a.id === id ? { ...a, enabled: !a.enabled, triggered: false } : a
    ));
  }, []);

  const dismissAlert = useCallback((id: string) => {
    const muteUntil = Date.now() + ALERT_MUTE_MS;
    setActiveAlerts((prev) => {
      const dismissed = prev.find((a) => a.id === id);
      mutedAlertUntilRef.current[id] = muteUntil;
      if (dismissed) {
        mutedAlertUntilRef.current[`${dismissed.condition}-${dismissed.threshold}`] = muteUntil;
      }
      return prev.filter((a) => a.id !== id);
    });
    setAlerts(prev => prev.map(a =>
      a.id === id ? { ...a, lastTriggered: new Date().toISOString() } : a
    ));
  }, []);

  // Export Function
  const exportAnalysis = useCallback(async (format: "json" | "pdf" = "json") => {
    if (!data) return null;
    
    const exportData = {
      timestamp: new Date().toISOString(),
      analysis: data,
      qa_history: qaHistory,
      conversation_memory: conversationMemory,
      export_format: format,
    };
    
    if (format === "json") {
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sentinel-analysis-${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      return { success: true, format: "json" };
    }
    
    return { success: false, format: "pdf", error: "PDF export not implemented" };
  }, [data, qaHistory, conversationMemory]);

  // Historical Data
  const fetchHistoricalData = useCallback(async (days: 7 | 30 = 7) => {
    try {
      const response = await API.get(`/api/sentinel/history?days=${days}`, {
        headers: API_HEADERS,
      });
      return response.data;
    } catch (err) {
      console.error("Failed to fetch historical data:", err);
      return null;
    }
  }, []);

  // Sensitivity
  const updateSensitivity = useCallback((newSensitivity: "low" | "medium" | "high") => {
    setSensitivity(newSensitivity);
  }, []);

  const updateCustomThreshold = useCallback((newThreshold: number) => {
    setCustomThreshold(newThreshold);
  }, []);

  const dismiss = useCallback(() => {
    setIsActive(false);
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, []);

  const refresh = useCallback(() => {
    setIsLoading(true);
    fetchSentinelData();
  }, [fetchSentinelData]);

  const submitFeedback = useCallback(async (feedback: FeedbackData) => {
    try {
      await API.post("/api/sentinel/feedback", feedback, {
        headers: API_HEADERS,
      });
      return true;
    } catch (err) {
      console.error("Failed to submit feedback:", err);
      return false;
    }
  }, []);

  // Effects
  useEffect(() => {
    fetchSentinelData();
    
    if (!enableWebSocket || !wsConnected) {
      const interval = setInterval(fetchSentinelData, pollInterval);
      return () => clearInterval(interval);
    }
  }, [fetchSentinelData, pollInterval, enableWebSocket, wsConnected]);

  // Track unmount to prevent state updates after unmount
  useEffect(() => {
    isUnmountedRef.current = false;
    return () => {
      isUnmountedRef.current = true;
      // Cleanup WebSocket on unmount
      wsShouldReconnectRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (enableWebSocket) {
      wsShouldReconnectRef.current = true;
      connectWebSocket();
      return () => disconnectWebSocket();
    }
  }, [enableWebSocket]);

  useEffect(() => {
    if (enableVoice && window.speechSynthesis) {
      window.speechSynthesis.onvoiceschanged = () => {
        // Voices loaded
      };
    }
  }, [enableVoice]);

  return {
    data,
    isActive,
    isLoading,
    error,
    lastUpdate,
    dismiss,
    refresh,
    submitFeedback,
    
    // Q&A
    qaHistory,
    isProcessingQA,
    askQuestion,
    clearQAHistory,
    
    // WebSocket
    wsConnected,
    wsReconnecting,
    connectWebSocket,
    disconnectWebSocket,
    
    // Voice
    isListening,
    voiceCommands,
    lastVoiceCommand,
    startVoiceListening,
    stopVoiceListening,
    
    // Alerts
    alerts,
    activeAlerts,
    addAlert,
    removeAlert,
    toggleAlert,
    dismissAlert,
    
    // Export
    exportAnalysis,
    
    // Historical
    fetchHistoricalData,
    
    // Sensitivity
    sensitivity,
    customThreshold,
    updateSensitivity,
    updateCustomThreshold,
    
    // Memory
    conversationMemory,
  };
}

export default useSentinel;

