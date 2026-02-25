import { useState, useEffect, useRef, useCallback } from "react";
import API, { API_HEADERS } from "../services/api";

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
}

interface UseSentinelOptions {
  threshold?: number; // Risk delta threshold to trigger activation
  pollInterval?: number; // Polling interval in ms
  enableVoice?: boolean; // Enable voice synthesis
}

export function useSentinel(options: UseSentinelOptions = {}) {
  const { threshold = 2.0, pollInterval = 5000, enableVoice = false } = options;

  const [data, setData] = useState<SentinelData | null>(null);
  const [isActive, setIsActive] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<string>("");
  
  const prevRiskRef = useRef<number | null>(null);
  const voiceSynthesisRef = useRef<SpeechSynthesisUtterance | null>(null);

  const fetchSentinelData = useCallback(async () => {
    try {
      const response = await API.get("/api/sentinel/latest", {
        headers: API_HEADERS,
      });
      
      const sentinelData: SentinelData = response.data;
      setData(sentinelData);
      setLastUpdate(new Date().toISOString());
      setError(null);

      // Check if we should activate based on risk delta
      const currentRisk = sentinelData.risk_score;
      const prevRisk = prevRiskRef.current;
      
      if (prevRisk !== null) {
        const delta = Math.abs(currentRisk - prevRisk);
        if (delta >= threshold) {
          setIsActive(true);
          
          // Voice synthesis if enabled
          if (enableVoice && window.speechSynthesis) {
            speakAnalysis(sentinelData.analysis_text);
          }
        }
      }
      
      prevRiskRef.current = currentRisk;
    } catch (err: any) {
      setError(err?.message || "Failed to fetch sentinel data");
      console.error("Sentinel fetch error:", err);
    } finally {
      setIsLoading(false);
    }
  }, [threshold, enableVoice]);

  const speakAnalysis = useCallback((text: string) => {
    if (!window.speechSynthesis) return;
    
    // Cancel any ongoing speech
    window.speechSynthesis.cancel();
    
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.9; // Slightly slower for clarity
    utterance.pitch = 1.0;
    utterance.volume = 0.8;
    
    // Try to find a calm, neutral voice
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

  const dismiss = useCallback(() => {
    setIsActive(false);
    // Stop any voice synthesis
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
  }, []);

  const refresh = useCallback(() => {
    setIsLoading(true);
    fetchSentinelData();
  }, [fetchSentinelData]);

  // Initial fetch and polling
  useEffect(() => {
    fetchSentinelData();
    
    const interval = setInterval(fetchSentinelData, pollInterval);
    return () => clearInterval(interval);
  }, [fetchSentinelData, pollInterval]);

  // Load voices when available
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
  };
}

export default useSentinel;
