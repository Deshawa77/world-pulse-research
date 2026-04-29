import { startTransition, useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import {
  buildEventStreamAuthUrl,
  getInternetMapHistory,
  getInternetMapPlayback,
  getInternetMapSnapshot,
  getInternetMapStreamStatus,
  postInternetMapAlertAction,
  runInternetMapBacktest,
  runInternetMapMaintenance,
  runInternetMapStreamCycle,
  type InternetMapAlertActionPayload,
  type InternetMapCountry,
  type InternetMapCyberAttack,
  type InternetMapFlow,
  type InternetMapHistoryPoint,
  type InternetMapPlaybackFrame,
  type InternetMapShutdownAlert,
  type InternetMapSnapshot,
  type InternetMapStreamStatus,
} from "../services/api";
import "./Dashboard.css";
import "./InternetMap.css";
import "../components/futuristic-dashboard.css";

function formatNumber(value: number | undefined | null, digits = 1): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatCompact(value: number | undefined | null, digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return value.toLocaleString(undefined, { notation: "compact", maximumFractionDigits: digits });
}

function formatPercent(value: number | undefined | null, digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return `${value.toFixed(digits)}%`;
}

function formatRelativeTime(value: string | undefined | null): string {
  if (!value) return "--";
  const timestamp = new Date(value);
  if (!Number.isFinite(timestamp.getTime())) return value;
  const deltaMs = Date.now() - timestamp.getTime();
  const deltaSeconds = Math.max(0, Math.round(deltaMs / 1000));
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  if (deltaSeconds < 3600) return `${Math.round(deltaSeconds / 60)}m ago`;
  if (deltaSeconds < 86400) return `${Math.round(deltaSeconds / 3600)}h ago`;
  return `${Math.round(deltaSeconds / 86400)}d ago`;
}

function formatRemainingSeconds(value: number | undefined | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  if (value <= 0) return "breached";
  const seconds = Math.round(value);
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))}m left`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h left`;
  return `${Math.round(seconds / 86400)}d left`;
}

function statusTone(status: string | undefined): "stable" | "guarded" | "elevated" | "critical" {
  const text = String(status || "").toLowerCase();
  if (text.includes("shutdown") || text.includes("critical") || text.includes("attack") || text.includes("contested") || text.includes("escalated")) return "critical";
  if (text.includes("congested") || text.includes("volatile") || text.includes("degraded") || text.includes("high") || text.includes("stale")) return "elevated";
  if (text.includes("guarded") || text.includes("watch") || text.includes("limited") || text.includes("acknowledged") || text.includes("assigned") || text.includes("snoozed")) return "guarded";
  return "stable";
}

type GeoArcPoint = { lat: number; lon: number };

function flowStroke(flow: InternetMapFlow): string {
  if (flow.status === "contested") return "#ff7a59";
  if (flow.status === "degraded") return "#ffb347";
  return "#4ae3ff";
}

function toneColor(tone: "stable" | "guarded" | "elevated" | "critical"): string {
  if (tone === "critical") return "#ff7a59";
  if (tone === "elevated") return "#ff9d4d";
  if (tone === "guarded") return "#ffd166";
  return "#4ae3ff";
}

function stageMarkerSize(country: InternetMapCountry, selected = false): number {
  const base = Math.max(8, Math.min(24, 8 + country.packet_flow_gbps / 105));
  return selected ? base + 4 : base;
}

function wrapLongitude(value: number): number {
  let next = value;
  while (next > 180) next -= 360;
  while (next < -180) next += 360;
  return next;
}

function interpolateLongitude(start: number, end: number, progress: number): number {
  let delta = end - start;
  if (delta > 180) delta -= 360;
  if (delta < -180) delta += 360;
  return wrapLongitude(start + delta * progress);
}

function buildGeoArc(flow: InternetMapFlow, arcScale = 1): GeoArcPoint[] {
  const steps = 30;
  const distance = Math.hypot(flow.destination_lon - flow.origin_lon, flow.destination_lat - flow.origin_lat);
  const lift = Math.max(5, Math.min(18, distance * 0.16)) * Math.max(0.72, arcScale);
  return Array.from({ length: steps + 1 }, (_, index) => {
    const progress = index / steps;
    const lon = interpolateLongitude(flow.origin_lon, flow.destination_lon, progress);
    const baseLat = flow.origin_lat + (flow.destination_lat - flow.origin_lat) * progress;
    const lat = baseLat + Math.sin(Math.PI * progress) * lift;
    return { lat, lon };
  });
}

function flowLineWidth(flow: InternetMapFlow, selectedCountryCode: string): number {
  const emphasized = selectedCountryCode && (flow.origin === selectedCountryCode || flow.destination === selectedCountryCode);
  return Math.max(1.6, Math.min(6.4, 1.4 + flow.traffic_share * 4.2 + (emphasized ? 1.2 : 0)));
}

const LABEL_STAGE_WIDTH = 1000;
const LABEL_STAGE_HEIGHT = 540;
const LABEL_POSITIONS = [
  { value: "bottom center", dx: 0, dy: 22 },
  { value: "top center", dx: 0, dy: -22 },
  { value: "middle right", dx: 32, dy: 0 },
  { value: "middle left", dx: -32, dy: 0 },
  { value: "top right", dx: 28, dy: -18 },
  { value: "top left", dx: -28, dy: -18 },
  { value: "bottom right", dx: 28, dy: 18 },
  { value: "bottom left", dx: -28, dy: 18 },
] as const;

type MapFocusMode = "global" | "regional";

type MapProjectionContext = {
  viewMode: MapFocusMode;
  centerLat: number;
  centerLon: number;
  scale: number;
};

type LabelPlacement = {
  country: InternetMapCountry;
  textPosition: (typeof LABEL_POSITIONS)[number]["value"];
};

type LabelBox = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

type LabelCandidate = {
  country: InternetMapCountry;
  priority: number;
  point: { x: number; y: number };
  width: number;
  height: number;
};

function longitudeDelta(start: number, end: number): number {
  let delta = end - start;
  if (delta > 180) delta -= 360;
  if (delta < -180) delta += 360;
  return delta;
}

function approximateStagePoint(lat: number, lon: number, context: MapProjectionContext): { x: number; y: number } {
  if (context.viewMode === "regional") {
    const halfWidth = LABEL_STAGE_WIDTH / 2;
    const halfHeight = LABEL_STAGE_HEIGHT / 2;
    const lonSpan = Math.max(34, 180 / context.scale);
    const latSpan = Math.max(20, 90 / Math.max(1.1, context.scale * 0.92));
    return {
      x: halfWidth + (longitudeDelta(context.centerLon, lon) / lonSpan) * halfWidth,
      y: halfHeight - ((lat - context.centerLat) / latSpan) * halfHeight,
    };
  }

  return {
    x: ((wrapLongitude(lon) + 180) / 360) * LABEL_STAGE_WIDTH,
    y: ((90 - lat) / 180) * LABEL_STAGE_HEIGHT,
  };
}

function buildLabelBox(point: { x: number; y: number }, width: number, height: number, position: (typeof LABEL_POSITIONS)[number]): LabelBox {
  const centerX = point.x + position.dx;
  const centerY = point.y + position.dy;
  return {
    left: centerX - width / 2,
    right: centerX + width / 2,
    top: centerY - height / 2,
    bottom: centerY + height / 2,
  };
}

function boxesOverlap(left: LabelBox, right: LabelBox, padding = 6): boolean {
  return !(
    left.right + padding < right.left ||
    left.left > right.right + padding ||
    left.bottom + padding < right.top ||
    left.top > right.bottom + padding
  );
}

function buildCountryLabelPlacements(
  countries: InternetMapCountry[],
  options: {
    selectedCountryCode: string;
    rankedCountries: InternetMapCountry[];
    selectedFlowCountries: Set<string>;
    alertCountries: Set<string>;
    projectionContext: MapProjectionContext;
    maxLabels: number;
  },
): LabelPlacement[] {
  const rankedIndex = new Map(options.rankedCountries.map((country, index) => [country.country, index]));
  const candidates = countries
    .map((country) => {
      const point = approximateStagePoint(country.lat, country.lon, options.projectionContext);
      if (
        options.projectionContext.viewMode === "regional"
        && (point.x < -120 || point.x > LABEL_STAGE_WIDTH + 120 || point.y < -90 || point.y > LABEL_STAGE_HEIGHT + 90)
      ) {
        return null;
      }

      const severityScore = Math.max(country.shutdown_risk, country.attack_index, country.congestion_index);
      const packetScore = Math.min(42, country.packet_flow_gbps / 28);
      const rankedPosition = rankedIndex.get(country.country);
      let priority = severityScore + packetScore;
      if (country.country === options.selectedCountryCode) priority += 1000;
      if (options.selectedFlowCountries.has(country.country)) priority += 250;
      if (options.alertCountries.has(country.country)) priority += 180;
      if (typeof rankedPosition === "number") priority += Math.max(0, 120 - rankedPosition * 8);
      if (options.projectionContext.viewMode === "regional") {
        const regionalDistance = Math.hypot(
          longitudeDelta(options.projectionContext.centerLon, country.lon) / 36,
          (country.lat - options.projectionContext.centerLat) / 22,
        );
        priority += Math.max(0, 140 - regionalDistance * 42);
      }
      return {
        country,
        priority,
        point,
        width: Math.max(42, country.country.length * 8 + 18),
        height: 16,
      };
    })
    .filter((candidate): candidate is LabelCandidate => Boolean(candidate))
    .sort((left, right) => right.priority - left.priority);

  const chosen: Array<LabelPlacement & { box: LabelBox }> = [];

  for (const candidate of candidates) {
    for (const position of LABEL_POSITIONS) {
      const box = buildLabelBox(candidate.point, candidate.width, candidate.height, position);
      if (chosen.some((existing) => boxesOverlap(existing.box, box, candidate.country.country === options.selectedCountryCode ? 3 : 8))) {
        continue;
      }
      chosen.push({
        country: candidate.country,
        textPosition: position.value,
        box,
      });
      break;
    }
    if (chosen.length >= options.maxLabels) {
      break;
    }
  }

  return chosen.map(({ country, textPosition }) => ({ country, textPosition }));
}

function formatOpsStatus(status: string | undefined): string {
  const value = String(status || "new").replace(/_/g, " ").trim();
  return value ? value[0].toUpperCase() + value.slice(1) : "New";
}

function stageLabel(values: string[] | undefined): string {
  if (!values?.length) return "derived";
  return values.join(" + ");
}

function alertActionKey(payload: Pick<InternetMapAlertActionPayload, "alert_type" | "country" | "flow_id" | "action">): string {
  return `${payload.alert_type}:${payload.country || payload.flow_id || "unknown"}:${payload.action}`;
}

type StageFilterMode = "all" | "attack" | "shutdown" | "congestion";
type StageSelectionMode = "explore" | "select" | "lasso";

const STAGE_FILTER_OPTIONS: Array<{ value: StageFilterMode; label: string }> = [
  { value: "all", label: "All" },
  { value: "attack", label: "Attack" },
  { value: "shutdown", label: "Shutdown" },
  { value: "congestion", label: "Congestion" },
];

const STAGE_SELECTION_OPTIONS: Array<{ value: StageSelectionMode; label: string }> = [
  { value: "explore", label: "Explore" },
  { value: "select", label: "Box" },
  { value: "lasso", label: "Lasso" },
];

function clampIndex(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(value, max - 1));
}

function uniqueStrings(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function flowLabel(flow: InternetMapFlow): string {
  return `${flow.origin} to ${flow.destination}`;
}

function flowSourceLabel(flow: InternetMapFlow): string {
  const families = uniqueStrings(flow.source_families ?? []);
  return families.length ? families.join(" + ") : "derived";
}

function flowMatchesSourceFilter(families: string[] | undefined, selectedFamilies: ReadonlySet<string>): boolean {
  if (!selectedFamilies.size) return true;
  return (families ?? []).some((family) => selectedFamilies.has(family));
}

function alertMatchesSourceFilter(families: string[] | undefined, selectedFamilies: ReadonlySet<string>): boolean {
  if (!selectedFamilies.size) return true;
  return (families ?? []).some((family) => selectedFamilies.has(family));
}

function buildPlaybackFrame(snapshot: InternetMapSnapshot): InternetMapPlaybackFrame {
  return {
    run_id: snapshot.stream_status?.run_id ?? snapshot.generated_at,
    captured_at: snapshot.stream_status?.captured_at ?? snapshot.generated_at,
    generated_at: snapshot.generated_at,
    summary: snapshot.summary,
    countries: snapshot.countries,
    flows: snapshot.flows,
    cyber_attacks: snapshot.cyber_attacks,
    shutdown_alerts: snapshot.shutdown_alerts,
    top_corridors: snapshot.top_corridors,
    source_health: snapshot.source_health,
    generated_from: snapshot.generated_from,
    collector_summary: snapshot.collector_summary,
    stream_status: snapshot.stream_status,
  };
}

function appendPlaybackFrame(current: InternetMapPlaybackFrame[], frame: InternetMapPlaybackFrame, limit = 48): InternetMapPlaybackFrame[] {
  const next = [...current.filter((item) => item.run_id !== frame.run_id), frame];
  next.sort((left, right) => new Date(left.captured_at).getTime() - new Date(right.captured_at).getTime());
  return next.slice(-Math.max(1, limit));
}

function flowPriorityScore(
  flow: InternetMapFlow,
  options: {
    selectedCountryCode?: string;
    pinnedFlowId?: string;
    selectedFlowIds?: ReadonlySet<string>;
    attackFlowIds?: ReadonlySet<string>;
    shutdownCountries?: ReadonlySet<string>;
    stageFilter?: StageFilterMode;
  },
): number {
  let score = flow.congestion_index + flow.attack_index + flow.anomaly_score + (flow.packet_loss_pct * 8) + (flow.traffic_share * 100);
  if (flow.id === options.pinnedFlowId) score += 1000;
  if (options.selectedFlowIds?.has(flow.id)) score += 520;
  if (options.selectedCountryCode && (flow.origin === options.selectedCountryCode || flow.destination === options.selectedCountryCode)) score += 180;
  if (options.attackFlowIds?.has(flow.id)) score += 140;
  if (options.shutdownCountries?.has(flow.origin) || options.shutdownCountries?.has(flow.destination)) score += 110;
  if (options.stageFilter === "attack") score += flow.attack_index * 0.8;
  if (options.stageFilter === "shutdown" && (options.shutdownCountries?.has(flow.origin) || options.shutdownCountries?.has(flow.destination))) score += 120;
  if (options.stageFilter === "congestion") score += flow.congestion_index * 0.9;
  return score;
}

export default function InternetMap() {
  const [snapshot, setSnapshot] = useState<InternetMapSnapshot | null>(null);
  const [selectedCountryCode, setSelectedCountryCode] = useState("");
  const [mapFocusMode, setMapFocusMode] = useState<MapFocusMode>("global");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [history, setHistory] = useState<InternetMapHistoryPoint[]>([]);
  const [playbackFrames, setPlaybackFrames] = useState<InternetMapPlaybackFrame[]>([]);
  const [playbackMode, setPlaybackMode] = useState<"live" | "replay">("live");
  const [playbackIndex, setPlaybackIndex] = useState(0);
  const [playbackPlaying, setPlaybackPlaying] = useState(false);
  const [streamStatus, setStreamStatus] = useState<InternetMapStreamStatus | null>(null);
  const [streamConnected, setStreamConnected] = useState(false);
  const [pendingActionKey, setPendingActionKey] = useState("");
  const [stageMapError, setStageMapError] = useState("");
  const [pinnedFlowId, setPinnedFlowId] = useState("");
  const [selectedFlowIds, setSelectedFlowIds] = useState<string[]>([]);
  const [selectionMode, setSelectionMode] = useState<StageSelectionMode>("explore");
  const [stageFilter, setStageFilter] = useState<StageFilterMode>("all");
  const [selectedSourceFamilies, setSelectedSourceFamilies] = useState<string[]>([]);
  const [followLiveFocus, setFollowLiveFocus] = useState(true);
  const stageMapRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const isAdmin = typeof window !== "undefined" && window.localStorage.getItem("role") === "admin";
  const currentOperator = typeof window !== "undefined"
    ? (window.localStorage.getItem("name") || window.localStorage.getItem("email") || "console-operator")
    : "console-operator";

  const applySnapshot = useEffectEvent((next: InternetMapSnapshot, historyRows?: InternetMapHistoryPoint[], nextStreamStatus?: InternetMapStreamStatus | null) => {
    startTransition(() => {
      setSnapshot(next);
      setHistory(next.history?.length ? next.history : historyRows ?? []);
      setStreamStatus(next.stream_status ?? nextStreamStatus ?? null);
      setSelectedCountryCode((current) => {
        if (current && next.countries.some((country) => country.country === current)) return current;
        return next.countries[0]?.country ?? "";
      });
    });
  });

  const enterReplay = useEffectEvent((targetIndex?: number) => {
    if (!playbackFrames.length) return;
    const nextIndex = clampIndex(typeof targetIndex === "number" ? targetIndex : playbackFrames.length - 1, playbackFrames.length);
    setPlaybackMode("replay");
    setPlaybackPlaying(false);
    setPlaybackIndex(nextIndex);
  });

  const exitReplay = useEffectEvent(() => {
    setPlaybackMode("live");
    setPlaybackPlaying(false);
  });

  const loadSnapshot = useEffectEvent(async (background = false) => {
    if (background) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError("");
    try {
      const [next, replay, status, playback] = await Promise.all([
        getInternetMapSnapshot(),
        getInternetMapHistory(24).catch(() => null),
        getInternetMapStreamStatus(false, false).catch(() => null),
        getInternetMapPlayback(36).catch(() => null),
      ]);
      applySnapshot(next, replay?.items, status?.stream_status ?? null);
      const frames = playback?.frames?.length ? playback.frames : [buildPlaybackFrame(next)];
      startTransition(() => {
        setPlaybackFrames(frames);
        setPlaybackIndex((current) => clampIndex(current, frames.length));
      });
    } catch (reason: any) {
      setError(reason?.response?.data?.detail || "Failed to load internet map intelligence.");
    } finally {
      if (background) {
        setRefreshing(false);
      } else {
        setLoading(false);
      }
    }
  });

  const loadPlotly = useEffectEvent(async () => {
    if (plotlyRef.current) return plotlyRef.current;
    if (!plotlyLoadingRef.current) {
      plotlyLoadingRef.current = import("plotly.js-dist-min")
        .then((mod) => {
          plotlyRef.current = (mod as any).default ?? mod;
          return plotlyRef.current;
        })
        .catch((error) => {
          plotlyLoadingRef.current = null;
          throw error;
        });
    }
    return plotlyLoadingRef.current;
  });

  const handleCountrySelection = useEffectEvent((countryCode: string, focusMode: MapFocusMode = "regional") => {
    setSelectedCountryCode(countryCode);
    setMapFocusMode(focusMode);
  });

  const handleResetMapFocus = useEffectEvent(() => {
    setMapFocusMode("global");
  });

  const handleSourceFamilyToggle = useEffectEvent((family: string) => {
    setSelectedSourceFamilies((current) => current.includes(family) ? current.filter((item) => item !== family) : [...current, family]);
  });

  const handleFlowFocus = useEffectEvent((flow: InternetMapFlow, filter?: StageFilterMode) => {
    if (filter) setStageFilter(filter);
    setPinnedFlowId(flow.id);
    setSelectedFlowIds((current) => uniqueStrings([flow.id, ...current]).slice(0, 24));
    handleCountrySelection(selectedCountryCode === flow.origin ? flow.destination : flow.origin);
  });

  useEffect(() => {
    void loadSnapshot(false);
    const intervalId = window.setInterval(() => {
      void loadSnapshot(true);
    }, 30000);
    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    const stream = new EventSource(buildEventStreamAuthUrl("/api/internet-map/alerts/stream?mode=live&data_mode=online&poll_seconds=12"));
    const handleInternetMapEvent = (event: Event) => {
      try {
        const payload = JSON.parse(String((event as MessageEvent).data || "{}")) as InternetMapSnapshot;
        setStreamConnected(true);
        setNotice("Live internet-map stream connected.");
        applySnapshot(payload, payload.history, payload.stream_status ?? null);
        startTransition(() => {
          setPlaybackFrames((current) => appendPlaybackFrame(current, buildPlaybackFrame(payload), 48));
        });
      } catch {
        setStreamConnected(false);
      }
    };
    const handleHeartbeat = () => {
      setStreamConnected(true);
    };
    stream.addEventListener("internet_map", handleInternetMapEvent as EventListener);
    stream.addEventListener("heartbeat", handleHeartbeat as EventListener);
    stream.onerror = () => {
      setStreamConnected(false);
      setNotice("Live stream degraded. Falling back to scheduled refresh.");
    };
    return () => {
      stream.removeEventListener("internet_map", handleInternetMapEvent as EventListener);
      stream.removeEventListener("heartbeat", handleHeartbeat as EventListener);
      stream.close();
    };
  }, []);

  useEffect(() => {
    if (playbackMode !== "replay" || !playbackPlaying || playbackFrames.length < 2) return;
    const intervalId = window.setInterval(() => {
      setPlaybackIndex((current) => (current + 1) % playbackFrames.length);
    }, 1400);
    return () => window.clearInterval(intervalId);
  }, [playbackMode, playbackPlaying, playbackFrames.length]);

  const handleAlertAction = useEffectEvent(async (payload: InternetMapAlertActionPayload) => {
    const nextKey = alertActionKey(payload);
    setPendingActionKey(nextKey);
    try {
      const result = await postInternetMapAlertAction(payload);
      if (!result?.ok) {
        setNotice("Alert action could not be saved.");
        return;
      }
      if (payload.action === "assign") {
        setNotice(`Assigned ${payload.country || payload.flow_id || payload.alert_type} to ${result.assignee || payload.assignee || currentOperator}.`);
      } else if (payload.action === "false_positive") {
        setNotice(`False-positive feedback saved for ${payload.country || payload.flow_id || payload.alert_type}.`);
      } else {
        setNotice(`${formatOpsStatus(payload.action)} saved for ${payload.country || payload.flow_id || payload.alert_type}.`);
      }
      await loadSnapshot(true);
    } finally {
      setPendingActionKey("");
    }
  });

  const handleRunCycle = useEffectEvent(async () => {
    setRefreshing(true);
    try {
      await runInternetMapStreamCycle(true);
      await loadSnapshot(true);
      setNotice("Internet-map stream cycle refreshed.");
    } finally {
      setRefreshing(false);
    }
  });

  const handleRunBacktest = useEffectEvent(async () => {
    setRefreshing(true);
    try {
      await runInternetMapBacktest(30);
      await loadSnapshot(true);
      setNotice("Internet-map backtest refreshed.");
    } finally {
      setRefreshing(false);
    }
  });

  const handleRunMaintenance = useEffectEvent(async () => {
    setRefreshing(true);
    try {
      const result = await runInternetMapMaintenance(30, 30, 90);
      await loadSnapshot(true);
      const deleted = Number((result as any)?.local_deleted?.stream_history || 0) + Number((result as any)?.local_deleted?.backtest_history || 0) + Number((result as any)?.local_deleted?.collector_history || 0);
      setNotice(`Internet-map maintenance completed. Local files pruned: ${deleted}.`);
    } finally {
      setRefreshing(false);
    }
  });

  const activeFrame = playbackMode === "replay" && playbackFrames.length ? playbackFrames[clampIndex(playbackIndex, playbackFrames.length)] : null;
  const activeSummary = activeFrame?.summary ?? snapshot?.summary;
  const activeTimestamp = activeFrame?.captured_at ?? snapshot?.generated_at;
  const selectedSourceFamilySet = useMemo(() => new Set(selectedSourceFamilies), [selectedSourceFamilies]);
  const baseCountries = activeFrame?.countries ?? snapshot?.countries ?? [];
  const baseFlows = activeFrame?.flows ?? snapshot?.flows ?? [];
  const baseSourceHealth = activeFrame?.source_health?.length ? activeFrame.source_health : (snapshot?.source_health ?? []);
  const baseTopCorridors = activeFrame?.top_corridors?.length ? activeFrame.top_corridors : (snapshot?.top_corridors ?? []);
  const baseCyberAttacks = activeFrame?.cyber_attacks ?? snapshot?.cyber_attacks ?? [];
  const baseShutdownAlerts = activeFrame?.shutdown_alerts ?? snapshot?.shutdown_alerts ?? [];
  const sourceHealth = useMemo(
    () => selectedSourceFamilies.length ? baseSourceHealth.filter((source) => selectedSourceFamilySet.has(source.source_family || source.source)) : baseSourceHealth,
    [baseSourceHealth, selectedSourceFamilies, selectedSourceFamilySet],
  );
  const availableSourceFamilies = useMemo(() => uniqueStrings([
    ...baseSourceHealth.map((source) => source.source_family || source.source),
    ...baseFlows.flatMap((flow) => flow.source_families ?? []),
    ...baseCyberAttacks.flatMap((attack) => attack.source_families ?? []),
    ...baseShutdownAlerts.flatMap((alert) => alert.source_families ?? []),
  ]).sort((left, right) => left.localeCompare(right)), [baseSourceHealth, baseFlows, baseCyberAttacks, baseShutdownAlerts]);
  const cyberAttacks = useMemo(
    () => baseCyberAttacks.filter((attack) => alertMatchesSourceFilter(attack.source_families, selectedSourceFamilySet) && stageFilter !== "shutdown"),
    [baseCyberAttacks, selectedSourceFamilySet, stageFilter],
  );
  const shutdownAlerts = useMemo(
    () => baseShutdownAlerts.filter((alert) => alertMatchesSourceFilter(alert.source_families, selectedSourceFamilySet) && stageFilter !== "attack"),
    [baseShutdownAlerts, selectedSourceFamilySet, stageFilter],
  );
  const attackFlowIds = useMemo(() => new Set(cyberAttacks.map((attack) => attack.flow_id || attack.id).filter(Boolean)), [cyberAttacks]);
  const shutdownCountries = useMemo(() => new Set(shutdownAlerts.map((alert) => alert.country).filter(Boolean)), [shutdownAlerts]);
  const countries = baseCountries;
  const flows = useMemo(() => {
    const filtered = baseFlows.filter((flow) => {
      if (!flowMatchesSourceFilter(flow.source_families, selectedSourceFamilySet)) return false;
      if (stageFilter === "attack") return flow.attack_index >= 42 || attackFlowIds.has(flow.id) || (flow.hijack_suspect_score ?? 0) >= 0.45;
      if (stageFilter === "shutdown") return shutdownCountries.has(flow.origin) || shutdownCountries.has(flow.destination);
      if (stageFilter === "congestion") return flow.congestion_index >= 45 || flow.packet_loss_pct >= 2.2 || flow.reroute_factor >= 1.15;
      return true;
    });
    return filtered.length ? filtered : baseFlows.filter((flow) => !selectedSourceFamilies.length || flowMatchesSourceFilter(flow.source_families, selectedSourceFamilySet));
  }, [baseFlows, selectedSourceFamilySet, selectedSourceFamilies, stageFilter, attackFlowIds, shutdownCountries]);
  const topCorridors = useMemo(
    () => (baseTopCorridors.length ? baseTopCorridors : flows)
      .filter((flow) => !selectedSourceFamilies.length || flowMatchesSourceFilter(flow.source_families, selectedSourceFamilySet))
      .slice(0, 8),
    [baseTopCorridors, flows, selectedSourceFamilies, selectedSourceFamilySet],
  );
  const selectedCountry = useMemo(
    () => countries.find((country) => country.country === selectedCountryCode) ?? countries[0] ?? null,
    [countries, selectedCountryCode],
  );
  const selectedFlowSet = useMemo(() => new Set(selectedFlowIds), [selectedFlowIds]);
  const selectedFlows = useMemo(
    () => [...flows]
      .filter((flow) => flow.origin === selectedCountry?.country || flow.destination === selectedCountry?.country || selectedFlowSet.has(flow.id) || flow.id === pinnedFlowId)
      .sort((left, right) => flowPriorityScore(right, { selectedCountryCode: selectedCountry?.country, pinnedFlowId, selectedFlowIds: selectedFlowSet, attackFlowIds, shutdownCountries, stageFilter }) - flowPriorityScore(left, { selectedCountryCode: selectedCountry?.country, pinnedFlowId, selectedFlowIds: selectedFlowSet, attackFlowIds, shutdownCountries, stageFilter }))
      .slice(0, 6),
    [flows, selectedCountry, selectedFlowSet, pinnedFlowId, attackFlowIds, shutdownCountries, stageFilter],
  );
  const rankedCountries = useMemo(
    () => [...countries].sort((left, right) => Math.max(right.shutdown_risk, right.attack_index, right.congestion_index) - Math.max(left.shutdown_risk, left.attack_index, left.congestion_index)),
    [countries],
  );
  const replayRows = useMemo(() => [...history].slice(0, 8).reverse(), [history]);
  const playbackRunLookup = useMemo(() => new Map(playbackFrames.map((frame, index) => [frame.run_id, index])), [playbackFrames]);
  const replayAnalytics = snapshot?.replay_analytics;
  const backtestSummary = snapshot?.backtest_summary;
  const runtimeStatus = snapshot?.runtime_status;
  const opsReporting = snapshot?.ops_reporting;
  const isRegionalMapFocus = mapFocusMode === "regional" && Boolean(selectedCountry);

  useEffect(() => {
    if (playbackMode === "replay" && !playbackFrames.length) {
      setPlaybackMode("live");
      setPlaybackPlaying(false);
      setPlaybackIndex(0);
      return;
    }
    setPlaybackIndex((current) => clampIndex(current, playbackFrames.length));
  }, [playbackMode, playbackFrames.length]);

  useEffect(() => {
    setSelectedCountryCode((current) => {
      if (current && countries.some((country) => country.country === current)) return current;
      return countries[0]?.country ?? "";
    });
  }, [countries]);

  useEffect(() => {
    if (playbackMode !== "live" || !followLiveFocus || !snapshot) return;
    if (pinnedFlowId) {
      const pinned = snapshot.flows.find((flow) => flow.id === pinnedFlowId);
      if (pinned) {
        setSelectedCountryCode((current) => (current && (current === pinned.origin || current === pinned.destination)) ? current : pinned.origin);
        setMapFocusMode("regional");
        return;
      }
    }
    if (!selectedCountryCode) {
      const focusCountry = snapshot.shutdown_alerts[0]?.country || snapshot.cyber_attacks[0]?.origin || snapshot.countries[0]?.country;
      if (focusCountry) {
        setSelectedCountryCode(focusCountry);
        setMapFocusMode("regional");
      }
    }
  }, [snapshot?.generated_at, playbackMode, followLiveFocus, pinnedFlowId, selectedCountryCode]);

  useEffect(() => {
    if (playbackMode !== "replay") return;
    const frame = playbackFrames[clampIndex(playbackIndex, playbackFrames.length)];
    const focusCountry = frame?.shutdown_alerts?.[0]?.country || frame?.cyber_attacks?.[0]?.origin || frame?.flows?.[0]?.origin || frame?.countries?.[0]?.country;
    if (focusCountry) {
      setSelectedCountryCode((current) => current || focusCountry);
    }
  }, [playbackMode, playbackIndex, playbackFrames]);

  useEffect(() => {
    let cancelled = false;

    const renderStageMap = async () => {
      const mapNode = stageMapRef.current;
      if (!mapNode || (loading && !snapshot)) return;

      if (!countries.length) {
        setStageMapError("No country telemetry available.");
        if (plotlyRef.current) {
          try {
            plotlyRef.current.purge(mapNode);
          } catch {
            // Ignore purge issues during empty state transitions.
          }
        }
        return;
      }

      try {
        const Plotly = await loadPlotly();
        if (cancelled || !stageMapRef.current) return;

        const selectedCode = selectedCountry?.country ?? "";
        const isRegionalFocus = mapFocusMode === "regional" && Boolean(selectedCountry);
        const projectionContext: MapProjectionContext = {
          viewMode: isRegionalFocus ? "regional" : "global",
          centerLat: selectedCountry?.lat ?? 14,
          centerLon: selectedCountry?.lon ?? 18,
          scale: isRegionalFocus ? 2.35 : 1.12,
        };
        const selectedFlowCountries = new Set<string>();
        selectedFlows.forEach((flow) => {
          selectedFlowCountries.add(flow.origin);
          selectedFlowCountries.add(flow.destination);
        });
        const alertCountries = new Set<string>();
        cyberAttacks.slice(0, 6).forEach((attack) => {
          if (attack.origin) alertCountries.add(attack.origin);
          if (attack.target) alertCountries.add(attack.target);
        });
        shutdownAlerts.slice(0, 6).forEach((alert) => {
          if (alert.country) alertCountries.add(alert.country);
        });
        const labelPlacements = buildCountryLabelPlacements(countries, {
          selectedCountryCode: selectedCode,
          rankedCountries,
          selectedFlowCountries,
          alertCountries,
          projectionContext,
          maxLabels: isRegionalFocus ? 22 : 10,
        });

        const traces: any[] = [];
        const selectionHandleLon: number[] = [];
        const selectionHandleLat: number[] = [];
        const selectionHandleCustom: Array<[string, string, string]> = [];
        const rankedFlows = [...flows]
          .sort((left, right) => flowPriorityScore(right, { selectedCountryCode: selectedCode, pinnedFlowId, selectedFlowIds: selectedFlowSet, attackFlowIds, shutdownCountries, stageFilter }) - flowPriorityScore(left, { selectedCountryCode: selectedCode, pinnedFlowId, selectedFlowIds: selectedFlowSet, attackFlowIds, shutdownCountries, stageFilter }))
          .slice(0, selectionMode === "explore" ? (isRegionalFocus ? 28 : 18) : 36);

        rankedFlows.forEach((flow) => {
          const isPinned = flow.id === pinnedFlowId;
          const isSelectedFlow = selectedFlowSet.has(flow.id);
          const emphasized = !isRegionalFocus || isPinned || isSelectedFlow || flow.origin === selectedCode || flow.destination === selectedCode;
          const arc = buildGeoArc(flow, isPinned ? 1.32 : (isSelectedFlow ? 1.16 : 1));
          const midpoint = arc[Math.floor(arc.length / 2)];
          selectionHandleLon.push(midpoint.lon);
          selectionHandleLat.push(midpoint.lat);
          selectionHandleCustom.push([flow.id, flow.origin, flow.destination]);
          traces.push({
            type: "scattergeo",
            mode: "lines",
            lon: arc.map((point) => point.lon),
            lat: arc.map((point) => point.lat),
            text: arc.map(() => `${flowLabel(flow)}<br>Throughput ${formatNumber(flow.throughput_gbps, 1)} Gbps<br>Congestion ${formatPercent(flow.congestion_index, 0)}<br>Attack ${formatPercent(flow.attack_index, 0)}<br>Latency ${formatNumber(flow.latency_ms, 0)} ms<br>Packet loss ${formatNumber(flow.packet_loss_pct, 1)}%<br>Reroute ${formatNumber(flow.reroute_factor, 2)}x<br>Updates ${formatCompact(flow.route_update_count, 0)} / Withdrawals ${formatCompact(flow.withdrawn_prefix_count, 0)}<br>Sources ${flowSourceLabel(flow)}<br>Confidence ${formatPercent((flow.confidence_ratio ?? 0) * 100, 0)}`),
            hovertemplate: "%{text}<extra></extra>",
            customdata: arc.map(() => [flow.id, flow.origin, flow.destination]),
            line: {
              color: flowStroke(flow),
              width: Math.max(flowLineWidth(flow, selectedCode), isPinned ? 6.5 : (isSelectedFlow ? 5.2 : 0)),
            },
            opacity: isPinned ? 0.98 : (isSelectedFlow ? 0.9 : (emphasized ? 0.82 : 0.24)),
            name: "internet-flow",
            showlegend: false,
          });
        });

        if (selectionHandleLon.length) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lon: selectionHandleLon,
            lat: selectionHandleLat,
            customdata: selectionHandleCustom,
            hoverinfo: "skip",
            marker: {
              size: selectionHandleCustom.map(([flowId]) => flowId === pinnedFlowId ? 14 : (selectedFlowSet.has(flowId) ? 12 : 9)),
              color: selectionHandleCustom.map(([flowId]) => flowId === pinnedFlowId ? "rgba(255,255,255,0.44)" : "rgba(74,227,255,0.18)"),
              line: {
                color: "rgba(255,255,255,0.24)",
                width: 1,
              },
            },
            name: "corridor-handles",
            showlegend: false,
          });
        }

        traces.push({
          type: "scattergeo",
          mode: "markers",
          lon: countries.map((country) => country.lon),
          lat: countries.map((country) => country.lat),
          text: countries.map((country) => `${country.label}<br>${country.country}<br>Packet flow ${formatNumber(country.packet_flow_gbps, 1)} Gbps<br>Congestion ${formatPercent(country.congestion_index, 0)}<br>Attack ${formatPercent(country.attack_index, 0)}<br>Shutdown ${formatPercent(country.shutdown_risk, 0)}<br>Fixed reach ${formatPercent((country.fixed_reachability_ratio ?? 0) * 100, 0)} / Mobile reach ${formatPercent((country.mobile_reachability_ratio ?? 0) * 100, 0)}<br>Impacted users ${formatNumber(country.subscribers_impacted_m, 1)}M`),
          hovertemplate: "%{text}<extra></extra>",
          customdata: countries.map((country) => [country.country]),
          marker: {
            size: countries.map((country) => stageMarkerSize(country, country.country === selectedCode)),
            color: countries.map((country) => toneColor(statusTone(country.status))),
            opacity: 0.96,
            line: {
              color: "rgba(255,255,255,0.7)",
              width: 1.2,
            },
          },
          name: "country-hubs",
          showlegend: false,
        });

        if (labelPlacements.length && (isRegionalFocus || selectedFlowIds.length > 0 || pinnedFlowId)) {
          traces.push({
            type: "scattergeo",
            mode: "text",
            lon: labelPlacements.map(({ country }) => country.lon),
            lat: labelPlacements.map(({ country }) => country.lat),
            text: labelPlacements.map(({ country }) => country.country),
            textposition: labelPlacements.map(({ textPosition }) => textPosition),
            textfont: {
              color: "rgba(2,8,20,0.94)",
              size: 16,
              family: '"IBM Plex Sans", "Segoe UI", sans-serif',
            },
            hoverinfo: "skip",
            name: "country-label-halo",
            showlegend: false,
          });
        }

        if (labelPlacements.length) {
          traces.push({
            type: "scattergeo",
            mode: "text",
            lon: labelPlacements.map(({ country }) => country.lon),
            lat: labelPlacements.map(({ country }) => country.lat),
            text: labelPlacements.map(({ country }) => country.country),
            textposition: labelPlacements.map(({ textPosition }) => textPosition),
            textfont: {
              color: "rgba(234,249,255,0.9)",
              size: isRegionalFocus ? 12 : 11,
              family: '"IBM Plex Sans", "Segoe UI", sans-serif',
            },
            hoverinfo: "skip",
            customdata: labelPlacements.map(({ country }) => [country.country]),
            name: "country-labels",
            showlegend: false,
          });
        }

        if (selectedCountry) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lon: [selectedCountry.lon],
            lat: [selectedCountry.lat],
            hoverinfo: "skip",
            marker: {
              size: stageMarkerSize(selectedCountry, true) + 12,
              color: "rgba(0,0,0,0)",
              line: {
                color: "rgba(255,255,255,0.96)",
                width: 2,
              },
            },
            name: "selected-country",
            showlegend: false,
          });
        }

        await Plotly.react(
          stageMapRef.current,
          traces,
          {
            margin: { l: 0, r: 0, b: 0, t: 0 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            hovermode: "closest",
            hoverlabel: {
              bgcolor: "rgba(4, 13, 26, 0.96)",
              bordercolor: "rgba(103, 232, 249, 0.25)",
              font: { color: "#ecfbff", size: 11 },
              align: "left",
            },
            dragmode: selectionMode === "select" ? "select" : (selectionMode === "lasso" ? "lasso" : false),
            clickmode: "event+select",
            uirevision: `internet-map-stage-${projectionContext.viewMode}-${selectedCode || "global"}-${stageFilter}-${selectionMode}-${playbackMode}-${playbackIndex}`,
            geo: {
              domain: { x: [0.01, 0.99], y: [0.02, 0.99] },
              projection: { type: "natural earth", scale: projectionContext.scale },
              center: isRegionalFocus ? { lat: projectionContext.centerLat, lon: projectionContext.centerLon } : undefined,
              showframe: false,
              bgcolor: "rgba(0,0,0,0)",
              showland: true,
              landcolor: "rgba(15, 27, 43, 0.96)",
              showocean: true,
              oceancolor: "rgba(1, 8, 20, 0.98)",
              showcountries: true,
              countrycolor: "rgba(148,163,184,0.16)",
              showcoastlines: true,
              coastlinecolor: "rgba(103,232,249,0.16)",
              coastlinewidth: 0.8,
              showlakes: true,
              lakecolor: "rgba(1, 8, 20, 0.98)",
              lataxis: { showgrid: true, gridcolor: "rgba(148,163,184,0.08)", gridwidth: 0.4 },
              lonaxis: { showgrid: true, gridcolor: "rgba(148,163,184,0.08)", gridwidth: 0.4 },
            },
          } as any,
          { displayModeBar: false, displaylogo: false, responsive: true, scrollZoom: false },
        );

        const plotNode = stageMapRef.current as any;
        plotNode?.removeAllListeners?.("plotly_click");
        plotNode?.removeAllListeners?.("plotly_selected");
        plotNode?.on?.("plotly_click", (event: any) => {
          const point = event?.points?.[0];
          const custom = Array.isArray(point?.customdata) ? point.customdata : [];
          const traceName = String(point?.data?.name ?? "");

          if ((traceName === "country-hubs" || traceName === "country-labels") && custom[0]) {
            handleCountrySelection(String(custom[0]));
            return;
          }

          if ((traceName === "internet-flow" || traceName === "corridor-handles") && custom[0]) {
            const flow = flows.find((item) => item.id === String(custom[0]));
            if (flow) {
              handleFlowFocus(flow);
            }
          }
        });
        plotNode?.on?.("plotly_selected", (event: any) => {
          const selectedIds = uniqueStrings((event?.points ?? [])
            .filter((point: any) => String(point?.data?.name ?? "") === "corridor-handles")
            .map((point: any) => String(Array.isArray(point?.customdata) ? point.customdata[0] : "")));
          if (!selectedIds.length) return;
          setSelectedFlowIds(selectedIds);
          setPinnedFlowId((current) => current || selectedIds[0]);
        });

        setStageMapError("");
      } catch {
        if (!cancelled) {
          setStageMapError("Projected world map unavailable. Refresh and try again.");
        }
      }
    };

    void renderStageMap();

    return () => {
      cancelled = true;
      const plotNode = stageMapRef.current as any;
      plotNode?.removeAllListeners?.("plotly_click");
      plotNode?.removeAllListeners?.("plotly_selected");
    };
  }, [countries, flows, rankedCountries, selectedCountry?.country, selectedFlows, cyberAttacks, shutdownAlerts, mapFocusMode, loading, snapshot?.generated_at, pinnedFlowId, selectedFlowIds, selectionMode, stageFilter, playbackMode, playbackIndex]);

  const renderAlertActions = (alert: InternetMapCyberAttack | InternetMapShutdownAlert, alertType: "attack" | "shutdown") => {
    const country = alertType === "shutdown" ? (alert as InternetMapShutdownAlert).country : undefined;
    const flowId = alertType === "attack" ? ((alert as InternetMapCyberAttack).flow_id || alert.id) : undefined;
    const shared = {
      alert_type: alertType,
      country,
      flow_id: flowId,
      alert_id: alert.alert_id || alert.id,
      dedupe_key: alert.dedupe_key,
      severity: alert.severity,
    } satisfies Partial<InternetMapAlertActionPayload>;
    const opsStatus = formatOpsStatus(alert.ops_state?.status);
    const teamQueue = alert.ops_state?.team_queue ?? (alertType === "attack" ? "network-security" : "continuity-watch");
    const escalationDestination = alert.ops_state?.escalation_destination ?? (alertType === "attack" ? "security-command" : "regional-response-desk");
    const slaState = alert.ops_state?.sla_breached ? "SLA breached" : formatRemainingSeconds(alert.ops_state?.sla_remaining_sec);

    return (
      <div className="internet-map-action-row">
        <span className={`internet-map-status-pill tone-${statusTone(alert.ops_state?.status || alert.status)}`}>{opsStatus}</span>
        {alert.ops_state?.assignee ? <span className="internet-map-action-meta">Assigned to {alert.ops_state.assignee}</span> : null}
        <span className="internet-map-action-meta">Queue {teamQueue}</span>
        <span className="internet-map-action-meta">SLA {slaState}</span>
        <span className="internet-map-action-meta">Escalates to {escalationDestination}</span>
        {alert.ops_state?.false_positive_count ? <span className="internet-map-action-meta">Feedback flags {alert.ops_state.false_positive_count}</span> : null}
        <div className="internet-map-action-buttons">
          <button
            type="button"
            disabled={pendingActionKey === alertActionKey({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "acknowledge" })}
            onClick={() => void handleAlertAction({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "acknowledge" })}
          >
            Ack
          </button>
          <button
            type="button"
            disabled={pendingActionKey === alertActionKey({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "assign" })}
            onClick={() => void handleAlertAction({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "assign", assignee: currentOperator, assignment_reason: "Assigned from internet map console", team_queue: teamQueue, escalation_destination: escalationDestination, sla_hours: alertType === "attack" ? 2 : 4 })}
          >
            Assign Me
          </button>
          <button
            type="button"
            disabled={pendingActionKey === alertActionKey({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "snooze" })}
            onClick={() => void handleAlertAction({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "snooze", snooze_hours: 6 })}
          >
            Snooze 6h
          </button>
          <button
            type="button"
            disabled={pendingActionKey === alertActionKey({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "escalate" })}
            onClick={() => void handleAlertAction({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "escalate", team_queue: teamQueue, escalation_destination: escalationDestination, escalation_level: 2, sla_hours: 1 })}
          >
            Escalate
          </button>
          <button
            type="button"
            disabled={pendingActionKey === alertActionKey({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "false_positive" })}
            onClick={() => void handleAlertAction({ ...shared, alert_type: alertType, country, flow_id: flowId, action: "false_positive", false_positive_reason: "Console false-positive flag" })}
          >
            False Positive
          </button>
        </div>
      </div>
    );
  };

  return (
    <main className="wp-shell proposal-runtime-shell internet-map-page">
      <ConsoleNavigation
        title={<>REAL-TIME <span>INTERNET MAP</span></>}
        subtitle="Internet operations surface with persisted history, direct-source corridor overlays, SSE updates, and operator-safe governance labels across BGP, CDN, ISP, and cloud telemetry."
        rightSlot={
          <div className="internet-map-header-meta">
            <div>
              <span>{playbackMode === "replay" ? "Replay Frame" : "Last Update"}</span>
              <strong>{formatRelativeTime(activeTimestamp)}</strong>
            </div>
            <div>
              <span>Stage</span>
              <strong>{playbackMode === "replay" ? "Replay" : (streamConnected ? "Live SSE" : (streamStatus?.status ?? "Polling"))}</strong>
            </div>
            <div>
              <span>Source Stage</span>
              <strong>{activeSummary?.source_stage ?? snapshot?.summary.source_stage ?? "phase-1-derived"}</strong>
            </div>
            <div>
              <span>Cadence</span>
              <strong>{runtimeStatus?.cycle_interval_sec ?? snapshot?.refresh_interval_sec ?? 20}s</strong>
            </div>
            <div>
              <span>Queue Depth</span>
              <strong>{formatCompact(runtimeStatus?.queue_depth, 0)}</strong>
            </div>
            <div>
              <span>Last Cycle</span>
              <strong>{formatRelativeTime(runtimeStatus?.last_cycle_finished_at)}</strong>
            </div>
            <button type="button" onClick={() => void loadSnapshot(false)} disabled={loading || refreshing}>
              {refreshing ? "Refreshing" : "Refresh"}
            </button>
            {isAdmin ? (
              <>
                <button type="button" onClick={() => void handleRunCycle()} disabled={refreshing}>
                  {refreshing ? "Running" : "Run Cycle"}
                </button>
                <button type="button" onClick={() => void handleRunBacktest()} disabled={refreshing}>
                  {refreshing ? "Running" : "Run Backtest"}
                </button>
                <button type="button" onClick={() => void handleRunMaintenance()} disabled={refreshing}>
                  {refreshing ? "Running" : "Prune"}
                </button>
              </>
            ) : null}
          </div>
        }
        sectionTabs={[
          { label: "Overview", targetId: "internet-map-overview" },
          { label: "Network Stage", targetId: "internet-map-stage", badge: `${countries.length}` },
          { label: "Threat Feed", targetId: "internet-map-threat-feed", badge: `${cyberAttacks.length + shutdownAlerts.length}` },
          { label: "Ops & Replay", targetId: "internet-map-ops", badge: `${Math.max(history.length, playbackFrames.length)}` },
          { label: "Countries", targetId: "internet-map-countries", badge: `${rankedCountries.length}` },
        ]}
      />

      {error ? <div className="proposal-auth-error">{error}</div> : null}
      {notice ? <div className="internet-map-notice">{notice}</div> : null}

      <section id="internet-map-overview" className="internet-map-overview-grid">
        <article className="internet-map-panel internet-map-hero-panel">
          <span className="internet-map-eyebrow">Planetary flow watch</span>
          <h2>Track congestion, route pressure, shutdown risk, and operator actions on one globe-scale surface.</h2>
          <p>
            The internet map now overlays persisted replay history with direct BGP, CDN, ISP, and cloud exports, so congestion, route churn,
            shutdown risk, and operator actions are driven by measured telemetry instead of only inferred phase-one proxies.
          </p>
          <div className="internet-map-chip-row">
            <span>Source status: {activeSummary?.source_status ?? "loading"}</span>
            <span>Monitored prefixes: {formatCompact(activeSummary?.monitored_prefixes, 0)}</span>
            <span>Collector records: {formatCompact(snapshot?.collector_summary?.total_records, 0)}</span>
            <span>Replay points: {formatCompact(playbackFrames.length || history.length, 0)}</span>
            <span>Direct families: {formatCompact(snapshot?.collector_summary?.direct_families, 0)}</span>
          </div>
        </article>

        <article className="internet-map-panel internet-map-kpi-panel">
          <div className="internet-map-kpi-grid">
            <div className="internet-map-kpi-card"><span>Packet Volume</span><strong>{formatCompact(activeSummary?.global_packet_volume_gbps, 0)} Gbps</strong></div>
            <div className="internet-map-kpi-card"><span>Congestion Index</span><strong>{formatPercent(activeSummary?.global_congestion_index, 0)}</strong></div>
            <div className="internet-map-kpi-card"><span>Cyber Attack Index</span><strong>{formatPercent(activeSummary?.cyber_attack_index, 0)}</strong></div>
            <div className="internet-map-kpi-card"><span>Active Attack Paths</span><strong>{formatCompact(activeSummary?.active_attack_paths, 0)}</strong></div>
            <div className="internet-map-kpi-card"><span>Shutdown Alerts</span><strong>{formatCompact(activeSummary?.shutdown_alerts, 0)}</strong></div>
            <div className="internet-map-kpi-card"><span>Cycle Latency</span><strong>{formatNumber(streamStatus?.cycle_latency_ms, 0)} ms</strong></div>
          </div>
        </article>

        <article className="internet-map-panel internet-map-source-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Source health</span><h3>Telemetry posture</h3></div>
            <strong>{sourceHealth.length} families</strong>
          </div>
          <div className="internet-map-source-list">
            {sourceHealth.map((source) => (
              <div key={`${source.source}-${source.source_name || source.stage}`} className={`internet-map-source-card tone-${statusTone(source.status)}`}>
                <div className="internet-map-source-top">
                  <div><strong>{source.source}</strong><span>{source.stage}</span></div>
                  <b>{source.status}</b>
                </div>
                <div className="internet-map-source-metrics">
                  <span>Coverage {formatPercent(source.coverage_ratio * 100, 0)}</span>
                  <span>Confidence {formatPercent(source.confidence_ratio * 100, 0)}</span>
                  <span>Freshness {formatNumber(source.freshness_sec, 0)}s</span>
                  <span>{source.cache_hit ? "Warm cache" : "Fresh pull"}</span>
                  <span>{source.rate_limited ? "Rate-limited" : (source.auth_mode && source.auth_mode !== "none" ? `Auth ${source.auth_mode}` : "No auth")}</span>
                </div>
                <p>{source.detail || source.advisory}</p>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section id="internet-map-stage" className="internet-map-main-grid">
        <article className="internet-map-panel internet-map-stage-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Global stage</span><h3>Packet-flow visualization</h3></div>
            <div className="internet-map-stage-tools">
              <div className="internet-map-legend">
                <span><i className="stable" /> Stable</span>
                <span><i className="degraded" /> Degraded</span>
                <span><i className="critical" /> Contested</span>
              </div>
              <button
                type="button"
                className="internet-map-stage-toggle"
                disabled={!selectedCountry}
                onClick={() => {
                  if (isRegionalMapFocus) {
                    handleResetMapFocus();
                    return;
                  }
                  if (selectedCountry) {
                    handleCountrySelection(selectedCountry.country);
                  }
                }}
              >
                {isRegionalMapFocus ? "World View" : "Focus Selected"}
              </button>
            </div>
          </div>
          <div className="internet-map-stage-control-grid">
            <div className="internet-map-stage-control-group">
              <span className="internet-map-stage-control-label">Time</span>
              <div className="internet-map-stage-pill-row">
                <button type="button" className={`internet-map-stage-pill${playbackMode === "live" ? " is-active" : ""}`} onClick={() => exitReplay()}>
                  Live
                </button>
                <button type="button" className={`internet-map-stage-pill${playbackMode === "replay" ? " is-active" : ""}`} disabled={!playbackFrames.length} onClick={() => enterReplay()}>
                  Replay
                </button>
                <button type="button" className={`internet-map-stage-pill${playbackPlaying ? " is-active" : ""}`} disabled={playbackFrames.length < 2} onClick={() => {
                  if (playbackMode !== "replay") {
                    enterReplay(playbackFrames.length - 1);
                    return;
                  }
                  setPlaybackPlaying((current) => !current);
                }}>
                  {playbackPlaying ? "Pause" : "Play"}
                </button>
                <label className="internet-map-stage-checkbox">
                  <input type="checkbox" checked={followLiveFocus} onChange={(event) => setFollowLiveFocus(event.currentTarget.checked)} />
                  Follow live focus
                </label>
              </div>
            </div>
            <div className="internet-map-stage-control-group">
              <span className="internet-map-stage-control-label">Filter</span>
              <div className="internet-map-stage-pill-row">
                {STAGE_FILTER_OPTIONS.map((option) => (
                  <button key={option.value} type="button" className={`internet-map-stage-pill${stageFilter === option.value ? " is-active" : ""}`} onClick={() => setStageFilter(option.value)}>
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="internet-map-stage-control-group">
              <span className="internet-map-stage-control-label">Select</span>
              <div className="internet-map-stage-pill-row">
                {STAGE_SELECTION_OPTIONS.map((option) => (
                  <button key={option.value} type="button" className={`internet-map-stage-pill${selectionMode === option.value ? " is-active" : ""}`} onClick={() => {
                    setSelectionMode(option.value);
                    if (option.value === "explore") {
                      setSelectedFlowIds([]);
                    }
                  }}>
                    {option.label}
                  </button>
                ))}
                <button type="button" className="internet-map-stage-pill" onClick={() => { setSelectedFlowIds([]); setPinnedFlowId(""); }}>
                  Clear
                </button>
              </div>
            </div>
          </div>
          {playbackFrames.length ? (
            <div className="internet-map-stage-playback">
              <div className="internet-map-stage-pill-row">
                <button type="button" className="internet-map-stage-pill" disabled={playbackFrames.length < 2} onClick={() => enterReplay(clampIndex(playbackIndex - 1, playbackFrames.length))}>Prev</button>
                <button type="button" className="internet-map-stage-pill" disabled={playbackFrames.length < 2} onClick={() => enterReplay((clampIndex(playbackIndex, playbackFrames.length) + 1) % playbackFrames.length)}>Next</button>
              </div>
              <div className="internet-map-stage-slider">
                <input type="range" min={0} max={Math.max(0, playbackFrames.length - 1)} value={playbackMode === "replay" ? clampIndex(playbackIndex, playbackFrames.length) : Math.max(0, playbackFrames.length - 1)} onChange={(event) => enterReplay(Number(event.currentTarget.value))} />
                <span>{playbackMode === "replay" ? `Replay frame ${clampIndex(playbackIndex, playbackFrames.length) + 1} of ${playbackFrames.length}` : `Latest frame of ${playbackFrames.length}`}</span>
              </div>
            </div>
          ) : null}
          {availableSourceFamilies.length ? (
            <div className="internet-map-stage-source-row">
              <button type="button" className={`internet-map-stage-pill${selectedSourceFamilies.length === 0 ? " is-active" : ""}`} onClick={() => setSelectedSourceFamilies([])}>
                All sources
              </button>
              {availableSourceFamilies.map((family) => (
                <button key={family} type="button" className={`internet-map-stage-pill${selectedSourceFamilies.includes(family) ? " is-active" : ""}`} onClick={() => handleSourceFamilyToggle(family)}>
                  {family}
                </button>
              ))}
            </div>
          ) : null}
          <div className="internet-map-chip-row internet-map-chip-row-tight internet-map-stage-status-row">
            <span>{playbackMode === "replay" ? `Replay ${clampIndex(playbackIndex, playbackFrames.length) + 1}/${Math.max(1, playbackFrames.length)}` : (streamConnected ? "Live SSE" : "Live polling")}</span>
            <span>{selectedSourceFamilies.length ? `${selectedSourceFamilies.length} source filters` : "All source families"}</span>
            <span>{selectedFlowIds.length ? `${selectedFlowIds.length} selected corridors` : "No corridor selection"}</span>
            <span>{pinnedFlowId ? `Pinned corridor ${pinnedFlowId}` : "No pinned corridor"}</span>
          </div>
          <div className="internet-map-stage-canvas">
            {loading && !snapshot ? <div className="internet-map-loading">Loading map intelligence...</div> : null}
            {!loading && !snapshot ? <div className="internet-map-loading">No map snapshot available yet.</div> : null}
            {stageMapError && !loading ? <div className="internet-map-loading">{stageMapError}</div> : null}
            <div
              ref={stageMapRef}
              className={`internet-map-stage-map${(loading && !snapshot) || (!snapshot && !loading) || Boolean(stageMapError) ? " is-hidden" : ""}`}
              role="img"
              aria-label="Projected world map of internet country hubs and packet-flow corridors"
            />
          </div>
        </article>

        <article className="internet-map-panel internet-map-focus-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Country focus</span><h3>{selectedCountry?.label ?? "No country selected"}</h3></div>
            {selectedCountry ? <strong className={`internet-map-status-pill tone-${statusTone(selectedCountry.status)}`}>{selectedCountry.status}</strong> : null}
          </div>
          {selectedCountry ? (
            <>
              <div className="internet-map-chip-row internet-map-chip-row-tight">
                <span>{playbackMode === "replay" ? "Replay context" : "Live context"}</span>
                <span>{pinnedFlowId ? `Pinned ${pinnedFlowId}` : "No pinned corridor"}</span>
                <span>{selectionMode === "explore" ? "Click corridors to pin" : `Drag to ${selectionMode}`}</span>
              </div>
              <div className="internet-map-focus-grid">
                <div><span>Packet flow</span><strong>{formatNumber(selectedCountry.packet_flow_gbps, 1)} Gbps</strong></div>
                <div><span>Congestion</span><strong>{formatPercent(selectedCountry.congestion_index, 0)}</strong></div>
                <div><span>Attack index</span><strong>{formatPercent(selectedCountry.attack_index, 0)}</strong></div>
                <div><span>Shutdown risk</span><strong>{formatPercent(selectedCountry.shutdown_risk, 0)}</strong></div>
                <div><span>Confidence</span><strong>{formatPercent((selectedCountry.confidence_ratio ?? 0) * 100, 0)}</strong></div>
                <div><span>Freshness</span><strong>{formatNumber(selectedCountry.freshness_sec, 0)}s</strong></div>
                <div><span>Fixed reach</span><strong>{formatPercent((selectedCountry.fixed_reachability_ratio ?? 0) * 100, 0)}</strong></div>
                <div><span>Mobile reach</span><strong>{formatPercent((selectedCountry.mobile_reachability_ratio ?? 0) * 100, 0)}</strong></div>
                <div><span>Throughput drop</span><strong>{formatNumber(selectedCountry.throughput_drop_pct, 0)}%</strong></div>
                <div><span>Impacted users</span><strong>{formatNumber(selectedCountry.subscribers_impacted_m, 1)}M</strong></div>
              </div>
              <p className="internet-map-focus-copy">{selectedCountry.advisory}</p>
              <div className="internet-map-flow-list">
                {selectedFlows.map((flow) => (
                  <button key={flow.id} type="button" className={`internet-map-flow-card tone-${statusTone(flow.status)}${flow.id === pinnedFlowId || selectedFlowIds.includes(flow.id) ? " is-selected" : ""}`} onClick={() => handleFlowFocus(flow)}>
                    <div><strong>{flowLabel(flow)}</strong><span>{formatNumber(flow.throughput_gbps, 1)} Gbps ? {flowSourceLabel(flow)}</span></div>
                    <div><b>{formatPercent(flow.attack_index, 0)} attack</b><span>{formatNumber(flow.latency_ms, 0)} ms</span></div>
                    <div><b>{formatNumber(flow.withdrawn_prefix_count, 0)} withdrawals</b><span>Hijack {formatPercent((flow.hijack_suspect_score ?? 0) * 100, 0)}</span></div>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <div className="internet-map-loading">Select a country to inspect corridor detail.</div>
          )}
        </article>
      </section>

      <section id="internet-map-threat-feed" className="internet-map-threat-grid">
        <article className="internet-map-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Cyber attacks</span><h3>Active network pressure</h3></div>
            <strong>{cyberAttacks.length}</strong>
          </div>
          <div className="internet-map-event-list">
            {cyberAttacks.map((attack) => (
              <div key={attack.id} className={`internet-map-event-card tone-${statusTone(attack.status)}`}>
                <div className="internet-map-event-top"><strong>{attack.origin} to {attack.target}</strong><b>{attack.status}</b></div>
                <div className="internet-map-event-metrics">
                  <span>{attack.vector}</span>
                  <span>{formatNumber(attack.intensity_gbps, 1)} Gbps</span>
                  <span>{formatPercent(attack.attack_index, 0)}</span>
                  <span>Hijack {formatPercent((attack.hijack_suspect_score ?? 0) * 100, 0)}</span>
                </div>
                <p>Confidence {formatPercent(attack.confidence_ratio * 100, 0)}. Started {formatRelativeTime(attack.started_at)}. Corroboration {formatCompact(attack.attack_signal_count, 0)} signals.</p>
                <div className="internet-map-inline-actions">
                  <button type="button" className="internet-map-inline-button" onClick={() => {
                    setStageFilter("attack");
                    const attackFlow = flows.find((flow) => flow.id === (attack.flow_id || attack.id));
                    if (attackFlow) {
                      handleFlowFocus(attackFlow, "attack");
                      return;
                    }
                    handleCountrySelection(attack.origin);
                  }}>
                    Track on map
                  </button>
                </div>
                {renderAlertActions(attack, "attack")}
              </div>
            ))}
          </div>
        </article>

        <article className="internet-map-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Shutdown alerts</span><h3>Country continuity watch</h3></div>
            <strong>{shutdownAlerts.length}</strong>
          </div>
          <div className="internet-map-event-list">
            {shutdownAlerts.map((alert) => (
              <div key={alert.id} className={`internet-map-event-card tone-${statusTone(alert.severity)}`}>
                <div className="internet-map-event-top"><strong>{alert.label}</strong><b>{alert.status}</b></div>
                <div className="internet-map-event-metrics">
                  <span>{formatPercent(alert.shutdown_risk, 0)} risk</span>
                  <span>{formatNumber(alert.estimated_users_impacted_m, 1)}M impacted</span>
                  <span>{formatPercent(alert.confidence_ratio * 100, 0)} confidence</span>
                  <span>Avail {formatPercent((alert.subscriber_availability_ratio ?? 0) * 100, 0)}</span>
                </div>
                <p>{alert.reason} Corroboration {formatCompact(alert.shutdown_signal_count, 0)} signals.</p>
                <div className="internet-map-inline-actions">
                  <button type="button" className="internet-map-inline-button" onClick={() => {
                    setStageFilter("shutdown");
                    handleCountrySelection(alert.country);
                  }}>
                    Track on map
                  </button>
                </div>
                {renderAlertActions(alert, "shutdown")}
              </div>
            ))}
          </div>
        </article>

        <article className="internet-map-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Top corridors</span><h3>Congestion leadership board</h3></div>
            <strong>{topCorridors.length}</strong>
          </div>
          <div className="internet-map-corridor-table">
            {topCorridors.map((flow) => (
              <button key={flow.id} type="button" className={`internet-map-corridor-row tone-${statusTone(flow.status)}${flow.id === pinnedFlowId || selectedFlowIds.includes(flow.id) ? " is-selected" : ""}`} onClick={() => handleFlowFocus(flow, "congestion")}>
                <span>{flowLabel(flow)}</span>
                <strong>{formatPercent(flow.congestion_index, 0)}</strong>
                <span>{formatNumber(flow.throughput_gbps, 1)} Gbps</span>
                <span>{formatNumber(flow.packet_loss_pct, 1)}% loss</span>
              </button>
            ))}
          </div>
        </article>
      </section>

      <section id="internet-map-ops" className="internet-map-ops-grid">
        <article className="internet-map-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Stream runtime</span><h3>Delivery and persistence</h3></div>
            <strong>{streamStatus?.status ?? "idle"}</strong>
          </div>
          <div className="internet-map-runtime-grid">
            <div><span>Run ID</span><strong>{streamStatus?.run_id ?? runtimeStatus?.run_id ?? "not-ready"}</strong></div>
            <div><span>Collector records</span><strong>{formatCompact(snapshot?.collector_summary?.total_records, 0)}</strong></div>
            <div><span>Replay points</span><strong>{formatCompact(snapshot?.persistence?.history_points, 0)}</strong></div>
            <div><span>Stages</span><strong>{stageLabel(snapshot?.generated_from?.collector_stages)}</strong></div>
            <div><span>Scheduler</span><strong>{runtimeStatus?.scheduler_enabled ? "Enabled" : "Disabled"}</strong></div>
            <div><span>Cycle reason</span><strong>{runtimeStatus?.last_cycle_reason ?? "scheduled"}</strong></div>
            <div><span>Queue depth</span><strong>{formatCompact(runtimeStatus?.queue_depth, 0)}</strong></div>
            <div><span>Cycle count</span><strong>{formatCompact(runtimeStatus?.cycle_count, 0)}</strong></div>
          </div>
          <div className="internet-map-chip-row internet-map-chip-row-tight">
            <span>Latency {formatNumber(snapshot?.observability?.snapshot_build?.latency_ms, 0)} ms</span>
            <span>Cache TTL {formatNumber(snapshot?.observability?.snapshot_build?.cache_ttl_sec, 0)}s</span>
            <span>Stale families {formatCompact(snapshot?.collector_summary?.stale_families, 0)}</span>
            <span>Down families {formatCompact(snapshot?.collector_summary?.down_families, 0)}</span>
            <span>Warm families {formatCompact(snapshot?.collector_summary?.cache_hit_families, 0)}</span>
            <span>Rate-limited {formatCompact(snapshot?.collector_summary?.rate_limited_families, 0)}</span>
          </div>
        </article>

        <article className="internet-map-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Replay</span><h3>Recent incident windows</h3></div>
            <strong>{replayRows.length}</strong>
          </div>
          <div className="internet-map-chip-row internet-map-chip-row-tight">
            <span>Trend {replayAnalytics?.trend_direction ?? "steady"}</span>
            <span>Congestion delta {formatNumber(replayAnalytics?.congestion_delta, 1)}</span>
            <span>Attack delta {formatNumber(replayAnalytics?.attack_delta, 1)}</span>
            <span>Peak shutdowns {formatCompact(replayAnalytics?.peak_shutdown_alerts, 0)}</span>
          </div>
          <div className="internet-map-replay-list">
            {replayRows.map((item) => (
              <button key={item.run_id} type="button" className={`internet-map-replay-card internet-map-replay-button${playbackMode === "replay" && activeFrame?.run_id === item.run_id ? " is-selected" : ""}`} onClick={() => {
                const targetIndex = playbackRunLookup.get(item.run_id);
                if (typeof targetIndex === "number") {
                  enterReplay(targetIndex);
                }
              }}>
                <div className="internet-map-replay-top"><strong>{formatRelativeTime(item.captured_at)}</strong><span>{item.source_stage || item.source_status}</span></div>
                <div className="internet-map-replay-metrics">
                  <span>Congestion {formatPercent(item.global_congestion_index, 0)}</span>
                  <span>Attack {formatPercent(item.cyber_attack_index, 0)}</span>
                  <span>Paths {formatCompact(item.active_attack_paths, 0)}</span>
                  <span>Shutdowns {formatCompact(item.shutdown_alerts, 0)}</span>
                </div>
                <div className="internet-map-replay-bar"><i style={{ width: `${Math.max(10, Math.min(100, item.global_congestion_index))}%` }} /></div>
              </button>
            ))}
            {(replayAnalytics?.top_disrupted_countries ?? []).map((item) => (
              <div key={item.country} className="internet-map-replay-card">
                <div className="internet-map-replay-top"><strong>{item.label}</strong><span>{item.status}</span></div>
                <div className="internet-map-replay-metrics">
                  <span>Score {formatPercent(item.score, 0)}</span>
                  <span>Country {item.country}</span>
                </div>
              </div>
            ))}
          </div>
        </article>

        <article className="internet-map-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Governance</span><h3>Operator-safe provenance</h3></div>
            <strong>{snapshot?.governance?.browser_safe_payload ? "Browser Safe" : "Review"}</strong>
          </div>
          <div className="internet-map-governance-list">
            <div><span>Confidence method</span><strong>{snapshot?.governance?.confidence_method ?? "weighted"}</strong></div>
            <div><span>Raw telemetry</span><strong>{snapshot?.governance?.raw_payload_redacted ? "Redacted" : "Exposed"}</strong></div>
            <div><span>Operator feedback</span><strong>{snapshot?.governance?.operator_feedback_enabled ? "Enabled" : "Disabled"}</strong></div>
            <div><span>Assignments</span><strong>{snapshot?.governance?.assignment_enabled ? "Enabled" : "Disabled"}</strong></div>
            <div><span>Team queues</span><strong>{snapshot?.governance?.team_queue_enabled ? "Enabled" : "Disabled"}</strong></div>
            <div><span>SLA tracking</span><strong>{snapshot?.governance?.sla_tracking_enabled ? "Enabled" : "Disabled"}</strong></div>
            <div><span>Audit reporting</span><strong>{snapshot?.governance?.audit_reporting_enabled ? "Enabled" : "Disabled"}</strong></div>
            <div><span>Source stages</span><strong>{stageLabel(snapshot?.governance?.source_stages)}</strong></div>
            <div><span>Acknowledged</span><strong>{formatCompact(snapshot?.alert_ops_summary?.acknowledged, 0)}</strong></div>
            <div><span>Assigned</span><strong>{formatCompact(snapshot?.alert_ops_summary?.assigned, 0)}</strong></div>
            <div><span>SLA breaches</span><strong>{formatCompact(snapshot?.alert_ops_summary?.breached_sla_count, 0)}</strong></div>
            <div><span>Backtest precision</span><strong>{formatPercent(((backtestSummary?.overall?.feedback_adjusted_precision_proxy ?? backtestSummary?.overall?.precision_proxy ?? 0)) * 100, 0)}</strong></div>
            <div><span>Secret posture</span><strong>{snapshot?.governance?.secret_loading?.secret_file_loaded ? "Secret file" : (snapshot?.governance?.secret_loading?.dotenv_fallback_loaded ? "Dotenv fallback" : "Env only")}</strong></div>
            <div><span>Retention</span><strong>{formatNumber(snapshot?.retention_policy?.mongo_retention_days, 0)}d</strong></div>
          </div>
        </article>

        <article className="internet-map-panel">
          <div className="internet-map-panel-head">
            <div><span className="internet-map-eyebrow">Audit</span><h3>Queues, escalations, and operator load</h3></div>
            <strong>{formatCompact(opsReporting?.total_actions, 0)}</strong>
          </div>
          <div className="internet-map-replay-list">
            {(opsReporting?.team_queues ?? []).slice(0, 4).map((item) => (
              <div key={item.queue} className="internet-map-replay-card">
                <div className="internet-map-replay-top"><strong>{item.queue}</strong><span>Queue</span></div>
                <div className="internet-map-replay-metrics">
                  <span>Actions {formatCompact(item.count, 0)}</span>
                </div>
              </div>
            ))}
            {(opsReporting?.escalation_destinations ?? []).slice(0, 4).map((item) => (
              <div key={item.destination} className="internet-map-replay-card">
                <div className="internet-map-replay-top"><strong>{item.destination}</strong><span>Escalation</span></div>
                <div className="internet-map-replay-metrics">
                  <span>Count {formatCompact(item.count, 0)}</span>
                </div>
              </div>
            ))}
            {(opsReporting?.recent_actions ?? []).slice(0, 4).map((item) => (
              <div key={`${item.timestamp}-${item.dedupe_key}`} className="internet-map-replay-card">
                <div className="internet-map-replay-top"><strong>{item.owner}</strong><span>{item.action}</span></div>
                <div className="internet-map-replay-metrics">
                  <span>{item.team_queue ?? "unqueued"}</span>
                  <span>{item.escalation_destination ?? "no escalation"}</span>
                </div>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section id="internet-map-countries" className="internet-map-country-grid">
        {rankedCountries.map((country) => (
          <button
            key={country.country}
            type="button"
            className={`internet-map-country-card tone-${statusTone(country.status)}${country.country === selectedCountry?.country ? " is-selected" : ""}`}
            onClick={() => handleCountrySelection(country.country)}
          >
            <div className="internet-map-country-top">
              <div><span>{country.country}</span><strong>{country.label}</strong></div>
              <b>{country.status}</b>
            </div>
            <div className="internet-map-country-metrics">
              <span>Flow {formatNumber(country.packet_flow_gbps, 0)} Gbps</span>
              <span>Congestion {formatPercent(country.congestion_index, 0)}</span>
              <span>Attack {formatPercent(country.attack_index, 0)}</span>
              <span>Shutdown {formatPercent(country.shutdown_risk, 0)}</span>
            </div>
          </button>
        ))}
      </section>
    </main>
  );
}






















