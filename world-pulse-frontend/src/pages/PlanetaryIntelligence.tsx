import { startTransition, useDeferredValue, useEffect, useEffectEvent, useRef, useState } from "react";
import ConsoleNavigation from "../components/ConsoleNavigation";
import WorldGlobe3D, {
  type GlobeCountryDetail,
  type GlobeEventMarker,
  type GlobeFlowArc,
} from "../components/WorldGlobe3D";
import {
  getPlanetaryAlertDetail,
  getPlanetaryBehaviorNormalizedSignals,
  getPlanetaryBehaviorOperatorSurface,
  getPlanetaryBehaviorSourceEvents,
  getPlanetaryCalibrationReport,
  getPlanetaryCommandLayer,
  getPlanetaryCorrelationChainDetail,
  getPlanetaryCorrelationChains,
  getPlanetaryCorridorDetail,
  getPlanetaryCountryFusionDetail,
  getPlanetaryCountryFusionSnapshots,
  getPlanetaryDisasterCommand,
  getPlanetaryEntityProfile,
  getPlanetaryFusionTimeline,
  getPlanetaryGraphEntities,
  getPlanetaryGraphRelationships,
  getPlanetaryGraphSummary,
  getPlanetaryOverview,
  getPlanetaryReplayMapFrames,
  getPlanetaryRuntimeStatus,
  postPlanetaryAlertAction,
  postPlanetaryRuntimeMaterialize,
  type PlanetaryAlertActionPayload,
  type PlanetaryAlertDetailResponse,
  type PlanetaryAlertEvent,
  type PlanetaryBehaviorOperatorSurfaceResponse,
  type PlanetaryCalibrationReportResponse,
  type PlanetaryCommandLayerResponse,
  type PlanetaryCorrelationChain,
  type PlanetaryCorrelationChainDetailResponse,
  type PlanetaryCorridorSnapshot,
  type PlanetaryCorridorDetailResponse,
  type PlanetaryCountryFusionDetailResponse,
  type PlanetaryCountryFusionSnapshot,
  type PlanetaryCountrySnapshot,
  type PlanetaryDisasterCommandSurfaceResponse,
  type PlanetaryEntityProfileResponse,
  type PlanetaryEvidenceSummary,
  type PlanetaryFusionTimelineFrame,
  type PlanetaryGraphSummaryResponse,
  type PlanetaryHazardForecast,
  type PlanetaryNormalizedSignal,
  type PlanetaryOperatorEvent,
  type PlanetaryOverviewResponse,
  type PlanetaryMapReplayFrame,
  type PlanetaryRuntimeManifest,
  type PlanetaryRuntimeStatus,
  type PlanetaryRuntimeStatusResponse,
  type PlanetarySourceEvent,
  type PlanetaryWorldEntity,
  type PlanetaryWorldRelationship,
} from "../services/api";
import "./Dashboard.css";
import "./PlanetaryIntelligence.css";
import "../components/futuristic-dashboard.css";

function safeNumber(value: number | undefined | null, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeRatio(value: number | undefined | null): number {
  const numeric = safeNumber(value, 0);
  if (numeric > 1) {
    return Math.max(0, Math.min(1, numeric / 100));
  }
  return Math.max(0, Math.min(1, numeric));
}

function formatNumber(value: number | undefined | null, digits = 1): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPercent(value: number | undefined | null, digits = 0): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return `${(normalizeRatio(value) * 100).toFixed(digits)}%`;
}

function formatSigned(value: number | undefined | null, digits = 1): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

function formatRelativeTime(value: string | undefined | null): string {
  if (!value) return "--";
  const stamp = new Date(value);
  if (!Number.isFinite(stamp.getTime())) return value;
  const deltaSec = Math.max(0, Math.round((Date.now() - stamp.getTime()) / 1000));
  if (deltaSec < 60) return `${deltaSec}s ago`;
  if (deltaSec < 3600) return `${Math.round(deltaSec / 60)}m ago`;
  if (deltaSec < 86400) return `${Math.round(deltaSec / 3600)}h ago`;
  return `${Math.round(deltaSec / 86400)}d ago`;
}

function timestampMs(value: string | undefined | null): number {
  if (!value) return Number.NaN;
  const stamp = new Date(value);
  return stamp.getTime();
}

function closestReplayFrame(
  frames: PlanetaryMapReplayFrame[],
  target: PlanetaryFusionTimelineFrame | null,
): PlanetaryMapReplayFrame | null {
  if (!frames.length) return null;
  if (!target) return frames[0] || null;
  const targetMs = timestampMs(target.frame_timestamp);
  const targetCountry = normalizeCountryCode(target.country);
  let best: PlanetaryMapReplayFrame | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (const frame of frames) {
    const candidateMs = timestampMs(frame.frame_timestamp || frame.captured_at);
    const candidateCountryCodes = new Set(
      (frame.countries || [])
        .map((item) => normalizeCountryCode(item.country))
        .filter(Boolean),
    );
    const sameCountry = targetCountry ? candidateCountryCodes.has(targetCountry) : false;
    const distance = Number.isFinite(targetMs) && Number.isFinite(candidateMs)
      ? Math.abs(candidateMs - targetMs)
      : Number.POSITIVE_INFINITY;
    const weightedDistance = sameCountry ? distance * 0.5 : distance;
    if (!best || weightedDistance < bestDistance) {
      best = frame;
      bestDistance = weightedDistance;
    }
  }
  return best || frames[0] || null;
}

function hasRenderableOverviewData(overview: PlanetaryOverviewResponse | null | undefined): boolean {
  if (!overview) return false;
  return Boolean(
    (overview.country_snapshots || []).length
    || (overview.corridor_snapshots || []).length
    || (overview.hazard_forecasts || []).length
    || (overview.alert_events || []).length
    || (overview.world_entities || []).length
    || (overview.world_relationships || []).length,
  );
}

const PLANETARY_OVERVIEW_CACHE_KEY = "planetary_console_overview_cache_v1";

function loadCachedPlanetaryOverview(): PlanetaryOverviewResponse | null {
  try {
    const raw = window.localStorage.getItem(PLANETARY_OVERVIEW_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed as PlanetaryOverviewResponse : null;
  } catch {
    return null;
  }
}

function storeCachedPlanetaryOverview(payload: PlanetaryOverviewResponse | null | undefined): void {
  if (!payload || !hasRenderableOverviewData(payload)) return;
  try {
    window.localStorage.setItem(PLANETARY_OVERVIEW_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Cache write best-effort only.
  }
}

function formatCountdown(value: string | undefined | null): string {
  if (!value) return "--";
  const stamp = new Date(value);
  if (!Number.isFinite(stamp.getTime())) return value;
  const deltaSec = Math.round((stamp.getTime() - Date.now()) / 1000);
  const absSec = Math.abs(deltaSec);
  const suffix = deltaSec >= 0 ? "from now" : "late";
  if (absSec < 60) return `${absSec}s ${suffix}`;
  if (absSec < 3600) return `${Math.round(absSec / 60)}m ${suffix}`;
  if (absSec < 86400) return `${Math.round(absSec / 3600)}h ${suffix}`;
  return `${Math.round(absSec / 86400)}d ${suffix}`;
}

function titleCase(value: string | undefined | null): string {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim();
}

function geographyLabel(event: { geography?: Record<string, unknown> } | undefined): string {
  const geography = event?.geography ?? {};
  const country = String(geography.country || geography.from_country || "").trim();
  const region = String(geography.region || "").trim();
  const origin = String(geography.origin || "").trim();
  const destination = String(geography.destination || geography.to_country || "").trim();
  if (origin && destination) return `${origin} -> ${destination}`;
  if (country && region) return `${country} / ${region}`;
  if (country) return country;
  if (region) return region;
  return String(geography.scope || "global");
}

function toneClassFromRatio(value: number | undefined | null): string {
  const ratio = normalizeRatio(value);
  if (ratio >= 0.75) return "is-critical";
  if (ratio >= 0.55) return "is-elevated";
  if (ratio >= 0.35) return "is-guarded";
  return "is-stable";
}

function runtimeToneClass(status: string | undefined): string {
  const text = String(status || "").toLowerCase();
  if (text.includes("error") || text.includes("critical") || text.includes("down")) return "is-critical";
  if (text.includes("degraded") || text.includes("stale") || text.includes("warn")) return "is-elevated";
  if (text.includes("limited") || text.includes("guard")) return "is-guarded";
  return "is-stable";
}

function compactLabel(value: string | undefined | null, max = 18): string {
  const text = String(value || "").trim();
  if (!text) return "--";
  return text.length > max ? `${text.slice(0, max - 3)}...` : text;
}

function buildMiniTrendPath(values: number[], width = 300, height = 110): string {
  if (!values.length) return "";
  const step = values.length > 1 ? width / (values.length - 1) : width;
  return values
    .map((value, index) => {
      const x = index * step;
      const y = height - (normalizeRatio(value) * height);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}

function severityLabelFromRatio(value: number | undefined | null): string {
  const ratio = normalizeRatio(value);
  if (ratio >= 0.75) return "critical";
  if (ratio >= 0.55) return "elevated";
  if (ratio >= 0.35) return "guarded";
  return "stable";
}

function alertCountry(alert: PlanetaryAlertEvent | undefined): string | undefined {
  const geography = (alert?.geography || {}) as Record<string, unknown>;
  return String(geography.country || geography.origin || geography["target"] || "").trim().toUpperCase() || undefined;
}

function recordText(record: Record<string, unknown> | undefined | null, key: string): string | undefined {
  const value = record?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function recordBoolean(record: Record<string, unknown> | undefined | null, key: string): boolean {
  return Boolean(record?.[key]);
}

function recordNumber(record: Record<string, unknown> | undefined | null, key: string, fallback = 0): number {
  return safeNumber(Number(record?.[key]), fallback);
}

function alertOpsStatus(alert: PlanetaryAlertEvent): string {
  return recordText(alert.ops_state, "status") || String(alert.status || "active");
}

function alertQueue(alert: PlanetaryAlertEvent): string {
  return recordText(alert.assignment, "team") || recordText(alert.ops_state, "team_queue") || "planetary-ops";
}

function alertOwner(alert: PlanetaryAlertEvent): string {
  return recordText(alert.assignment, "owner") || recordText(alert.ops_state, "assignee") || "unassigned";
}

function relationMatchesQuery(item: PlanetaryWorldRelationship, query: string): boolean {
  if (!query) return true;
  const evidence = (item.supporting_evidence_refs || [])
    .map((entry) => JSON.stringify(entry))
    .join(" ")
    .toLowerCase();
  const haystack = `${item.relationship_id} ${item.relationship_type} ${item.source_entity_id} ${item.target_entity_id} ${evidence}`.toLowerCase();
  return haystack.includes(query);
}

function renderMetricCard(label: string, value: string, detail: string, toneClass: string) {
  return (
    <article className={`planetary-metric-card ${toneClass}`}>
      <div className="planetary-metric-card__topline">
        <span className="planetary-metric-card__label">{label}</span>
        <span className="planetary-metric-card__pulse" aria-hidden="true" />
      </div>
      <strong className="planetary-metric-card__value">{value}</strong>
      <p className="planetary-metric-card__detail">{detail}</p>
    </article>
  );
}

type InvestigationDrawerData =
  | { kind: "country"; title: string; payload: PlanetaryCountryFusionDetailResponse }
  | { kind: "chain"; title: string; payload: PlanetaryCorrelationChainDetailResponse }
  | { kind: "alert"; title: string; payload: PlanetaryAlertDetailResponse }
  | { kind: "corridor"; title: string; payload: PlanetaryCorridorDetailResponse }
  | { kind: "entity"; title: string; payload: PlanetaryEntityProfileResponse };

function investigationEvidenceSummary(drawer: InvestigationDrawerData | null): PlanetaryEvidenceSummary | undefined {
  return drawer?.payload.evidence_summary;
}

function investigationProvenance(drawer: InvestigationDrawerData | null): Array<Record<string, unknown>> {
  if (!drawer) return [];
  if (drawer.kind === "entity") return drawer.payload.entity?.provenance_refs || [];
  return drawer.payload.provenance_refs || [];
}

function investigationAlerts(drawer: InvestigationDrawerData | null): PlanetaryAlertEvent[] {
  if (!drawer) return [];
  if (drawer.kind === "country" || drawer.kind === "chain" || drawer.kind === "corridor") return drawer.payload.supporting_alerts || [];
  if (drawer.kind === "alert") return drawer.payload.alert ? [drawer.payload.alert] : [];
  return drawer.payload.related_alerts || [];
}

function investigationSignals(drawer: InvestigationDrawerData | null): PlanetaryNormalizedSignal[] {
  if (!drawer || drawer.kind === "entity") return [];
  return drawer.payload.supporting_signals || [];
}

function investigationSourceEvents(drawer: InvestigationDrawerData | null): PlanetarySourceEvent[] {
  if (!drawer || drawer.kind === "entity") return [];
  return drawer.payload.supporting_source_events || [];
}

function investigationEntities(drawer: InvestigationDrawerData | null): PlanetaryWorldEntity[] {
  if (!drawer) return [];
  if (drawer.kind === "entity") {
    return [drawer.payload.entity, ...(drawer.payload.neighborhood_entities || [])].filter(Boolean) as PlanetaryWorldEntity[];
  }
  return drawer.payload.related_entities || [];
}

function investigationRelationships(drawer: InvestigationDrawerData | null): PlanetaryWorldRelationship[] {
  if (!drawer) return [];
  return drawer.kind === "entity" ? drawer.payload.neighborhood_relationships || [] : drawer.payload.related_relationships || [];
}

function investigationTimeline(drawer: InvestigationDrawerData | null): PlanetaryFusionTimelineFrame[] {
  if (!drawer) return [];
  return drawer.kind === "entity" ? drawer.payload.related_timeline || [] : drawer.payload.supporting_timeline || [];
}

function investigationHazards(drawer: InvestigationDrawerData | null): PlanetaryHazardForecast[] {
  if (!drawer) return [];
  return drawer.kind === "entity" ? drawer.payload.related_hazard_forecasts || [] : drawer.payload.supporting_hazard_forecasts || [];
}

function investigationCorridors(drawer: InvestigationDrawerData | null): PlanetaryCorridorSnapshot[] {
  if (!drawer) return [];
  return drawer.kind === "entity" ? drawer.payload.related_corridors || [] : drawer.payload.supporting_corridors || [];
}

function investigationCorrelationChains(drawer: InvestigationDrawerData | null): PlanetaryCorrelationChain[] {
  if (!drawer) return [];
  if (drawer.kind === "country") return drawer.payload.related_correlation_chains || [];
  if (drawer.kind === "chain") return drawer.payload.correlation_chain ? [drawer.payload.correlation_chain] : [];
  if (drawer.kind === "alert" || drawer.kind === "corridor") return drawer.payload.related_correlation_chains || [];
  return drawer.payload.related_correlation_chains || [];
}

function operatorEventSummary(item: PlanetaryOperatorEvent): string {
  const parts = [titleCase(item.action), item.actor || "", item.assignee ? `-> ${item.assignee}` : "", item.team_queue ? `@ ${item.team_queue}` : ""].filter(Boolean);
  return parts.join(" ");
}

type HeroLayerKey = "behavior" | "hazards" | "corridors" | "alerts" | "graph";

const HERO_LAYER_OPTIONS: Array<{ key: HeroLayerKey; label: string }> = [
  { key: "behavior", label: "Behavior" },
  { key: "hazards", label: "Hazards" },
  { key: "corridors", label: "Internet corridors" },
  { key: "alerts", label: "Alerts" },
  { key: "graph", label: "Graph influence" },
];

const PLANETARY_COUNTRY_COORDS: Record<string, { lat: number; lng: number }> = {
  USA: { lat: 39.8, lng: -98.6 },
  CAN: { lat: 56.1, lng: -106.3 },
  MEX: { lat: 23.6, lng: -102.6 },
  BRA: { lat: -14.2, lng: -51.9 },
  ARG: { lat: -38.4, lng: -63.6 },
  CHL: { lat: -35.7, lng: -71.5 },
  COL: { lat: 4.6, lng: -74.1 },
  PER: { lat: -9.2, lng: -75.0 },
  VEN: { lat: 6.4, lng: -66.6 },
  GBR: { lat: 55.4, lng: -3.4 },
  FRA: { lat: 46.2, lng: 2.2 },
  DEU: { lat: 51.2, lng: 10.4 },
  ESP: { lat: 40.4, lng: -3.7 },
  ITA: { lat: 42.8, lng: 12.5 },
  POL: { lat: 52.1, lng: 19.4 },
  NLD: { lat: 52.1, lng: 5.3 },
  SWE: { lat: 60.1, lng: 18.6 },
  NOR: { lat: 60.5, lng: 8.5 },
  FIN: { lat: 64.5, lng: 26.0 },
  UKR: { lat: 48.4, lng: 31.2 },
  TUR: { lat: 38.9, lng: 35.2 },
  RUS: { lat: 61.5, lng: 105.3 },
  CHN: { lat: 35.9, lng: 104.2 },
  IND: { lat: 20.6, lng: 78.9 },
  JPN: { lat: 36.2, lng: 138.3 },
  KOR: { lat: 36.5, lng: 127.9 },
  PAK: { lat: 30.4, lng: 69.3 },
  BGD: { lat: 23.7, lng: 90.4 },
  LKA: { lat: 7.9, lng: 80.7 },
  MMR: { lat: 21.2, lng: 96.0 },
  THA: { lat: 15.9, lng: 100.9 },
  VNM: { lat: 14.1, lng: 108.3 },
  PHL: { lat: 12.9, lng: 121.8 },
  IDN: { lat: -0.8, lng: 113.9 },
  AUS: { lat: -25.3, lng: 133.8 },
  NZL: { lat: -41.5, lng: 172.8 },
  ZAF: { lat: -30.6, lng: 22.9 },
  NGA: { lat: 9.1, lng: 8.7 },
  EGY: { lat: 26.8, lng: 30.8 },
  ETH: { lat: 9.1, lng: 40.5 },
  KEN: { lat: 0.0, lng: 37.9 },
  GHA: { lat: 7.9, lng: -1.0 },
  MAR: { lat: 31.8, lng: -7.1 },
  TUN: { lat: 34.0, lng: 9.6 },
  DZA: { lat: 28.0, lng: 1.7 },
  SAU: { lat: 23.9, lng: 45.1 },
  ARE: { lat: 24.3, lng: 54.4 },
  QAT: { lat: 25.3, lng: 51.2 },
  KWT: { lat: 29.3, lng: 47.5 },
  ISR: { lat: 31.0, lng: 34.8 },
  IRQ: { lat: 33.2, lng: 43.7 },
  IRN: { lat: 32.4, lng: 53.7 },
};

const PLANETARY_REGION_COORDS: Array<{ match: string; lat: number; lng: number }> = [
  { match: "north america", lat: 45, lng: -100 },
  { match: "south america", lat: -15, lng: -60 },
  { match: "europe", lat: 51, lng: 14 },
  { match: "middle east", lat: 29, lng: 45 },
  { match: "asia", lat: 29, lng: 102 },
  { match: "southeast asia", lat: 11, lng: 105 },
  { match: "africa", lat: 2, lng: 20 },
  { match: "oceania", lat: -24, lng: 135 },
  { match: "global", lat: 0, lng: 0 },
];

const PLANETARY_COUNTRY_LABELS: Record<string, string> = {
  USA: "United States",
  CAN: "Canada",
  MEX: "Mexico",
  BRA: "Brazil",
  ARG: "Argentina",
  CHL: "Chile",
  COL: "Colombia",
  PER: "Peru",
  VEN: "Venezuela",
  GBR: "United Kingdom",
  FRA: "France",
  DEU: "Germany",
  ESP: "Spain",
  ITA: "Italy",
  POL: "Poland",
  NLD: "Netherlands",
  SWE: "Sweden",
  NOR: "Norway",
  FIN: "Finland",
  UKR: "Ukraine",
  TUR: "Turkey",
  RUS: "Russia",
  CHN: "China",
  IND: "India",
  JPN: "Japan",
  KOR: "South Korea",
  PAK: "Pakistan",
  BGD: "Bangladesh",
  LKA: "Sri Lanka",
  MMR: "Myanmar",
  THA: "Thailand",
  VNM: "Vietnam",
  PHL: "Philippines",
  IDN: "Indonesia",
  AUS: "Australia",
  NZL: "New Zealand",
  ZAF: "South Africa",
  NGA: "Nigeria",
  EGY: "Egypt",
  ETH: "Ethiopia",
  KEN: "Kenya",
  GHA: "Ghana",
  MAR: "Morocco",
  TUN: "Tunisia",
  DZA: "Algeria",
  SAU: "Saudi Arabia",
  ARE: "United Arab Emirates",
  QAT: "Qatar",
  KWT: "Kuwait",
  ISR: "Israel",
  IRQ: "Iraq",
  IRN: "Iran",
};

const PLANETARY_COUNTRY_SEARCH_ALIASES: Record<string, string> = Object.entries(PLANETARY_COUNTRY_LABELS).reduce<Record<string, string>>((acc, [code, label]) => {
  const canonical = label.toLowerCase();
  acc[canonical] = code;
  acc[canonical.replace(/\./g, "")] = code;
  acc[canonical.replace(/\s+/g, "")] = code;
  acc[code.toLowerCase()] = code;
  return acc;
}, {
  "united states of america": "USA",
  "america": "USA",
  "us": "USA",
  "usa": "USA",
  "uk": "GBR",
  "britain": "GBR",
  "england": "GBR",
  "uae": "ARE",
  "southkorea": "KOR",
  "korea": "KOR",
  "russia": "RUS",
  "sri lanka": "LKA",
});

function normalizeCountryCode(value: string | undefined | null): string {
  const normalized = String(value || "").toUpperCase().replace(/[^A-Z]/g, "");
  return normalized.length === 3 ? normalized : "";
}

function countryDisplayLabel(code: string | undefined | null): string {
  const normalized = normalizeCountryCode(code);
  return PLANETARY_COUNTRY_LABELS[normalized] || normalized || String(code || "").trim() || "--";
}

function resolveCountrySearchCode(query: string | undefined | null): string {
  const raw = String(query || "").trim();
  if (!raw) return "";
  const normalizedCode = normalizeCountryCode(raw);
  if (normalizedCode) return normalizedCode;
  const compact = raw.toLowerCase().replace(/\./g, "").replace(/\s+/g, " ").trim();
  const compactNoSpace = compact.replace(/\s+/g, "");
  return PLANETARY_COUNTRY_SEARCH_ALIASES[compact] || PLANETARY_COUNTRY_SEARCH_ALIASES[compactNoSpace] || "";
}

function entityCountryCode(item: PlanetaryWorldEntity | undefined | null): string {
  if (!item) return "";
  const entityIdMatch = String(item.entity_id || "").match(/country:([A-Z]{3})/i);
  if (entityIdMatch?.[1]) return normalizeCountryCode(entityIdMatch[1]);
  return normalizeCountryCode(
    String(item.geography?.country || "")
    || String(item.canonical_name || "")
    || String(item.aliases?.[0] || ""),
  );
}

function toMapScore(value: number | undefined | null): number {
  return Math.round(normalizeRatio(value) * 100);
}

function resolvePlanetaryMarkerPoint(country: string | undefined | null, region?: string | undefined | null): { lat: number; lng: number; countryCode?: string } | null {
  const countryCode = normalizeCountryCode(country);
  if (countryCode && PLANETARY_COUNTRY_COORDS[countryCode]) {
    return { ...PLANETARY_COUNTRY_COORDS[countryCode], countryCode };
  }
  const regionText = String(region || "").toLowerCase();
  const regionMatch = PLANETARY_REGION_COORDS.find((item) => regionText.includes(item.match));
  if (regionMatch) {
    return { lat: regionMatch.lat, lng: regionMatch.lng, countryCode: countryCode || undefined };
  }
  return null;
}

function hazardKind(value: string | undefined | null): GlobeEventMarker["kind"] {
  const text = String(value || "").toLowerCase();
  if (text.includes("earthquake") || text.includes("seismic")) return "earthquake";
  if (text.includes("wildfire") || text.includes("volcano")) return "volcano";
  if (text.includes("cyclone") || text.includes("flood") || text.includes("storm") || text.includes("ocean")) return "wave";
  if (text.includes("conflict")) return "war";
  return "generic";
}

function alertMarkerKind(alertType: string | undefined | null, summary: string | undefined | null): GlobeEventMarker["kind"] {
  const text = `${alertType || ""} ${summary || ""}`.toLowerCase();
  if (text.includes("shutdown") || text.includes("routing") || text.includes("ddos") || text.includes("cyber")) return "missile";
  if (text.includes("conflict") || text.includes("unrest") || text.includes("riot") || text.includes("protest")) return "war";
  if (text.includes("earthquake")) return "earthquake";
  if (text.includes("flood") || text.includes("cyclone") || text.includes("storm")) return "wave";
  return "generic";
}

function spreadHeroMarkers<T extends { lat: number; lng: number }>(items: T[]): T[] {
  const offsets: Array<[number, number]> = [
    [0, 0],
    [1.1, 1.0],
    [-1.1, 1.0],
    [1.2, -1.0],
    [-1.2, -1.0],
    [0, 1.6],
    [0, -1.6],
    [1.8, 0],
    [-1.8, 0],
  ];
  const seen = new Map<string, number>();
  return items.map((item) => {
    const key = `${Math.round(item.lat * 2) / 2}:${Math.round(item.lng * 2) / 2}`;
    const index = seen.get(key) || 0;
    seen.set(key, index + 1);
    if (index === 0) return item;
    const [latOffset, lngOffset] = offsets[index % offsets.length];
    return {
      ...item,
      lat: item.lat + latOffset,
      lng: item.lng + lngOffset,
    };
  });
}

function pickDistributedHotspots<T extends { country?: string; probability: number }>(items: T[], limit = 5): T[] {
  const usedCountries = new Set<string>();
  const selected: T[] = [];
  for (const item of items) {
    const key = normalizeCountryCode(item.country);
    if (key && usedCountries.has(key)) continue;
    if (key) usedCountries.add(key);
    selected.push(item);
    if (selected.length >= limit) break;
  }
  return selected;
}

function pickLabelCountryCodes(countries: Array<{ countryCode: string; lat: number; lng: number }>, limit = 8): string[] {
  const chosen: Array<{ countryCode: string; lat: number; lng: number }> = [];
  for (const item of countries) {
    const farEnough = chosen.every((existing) => (
      Math.hypot((item.lat - existing.lat) * 1.1, (item.lng - existing.lng) * 0.45) >= 18
    ));
    if (!farEnough) continue;
    chosen.push(item);
    if (chosen.length >= limit) break;
  }
  return chosen.map((item) => item.countryCode);
}

function corridorIntensity(corridor: PlanetaryCorridorSnapshot): number {
  const flow = corridor.flow_metrics || {};
  return Math.max(
    toMapScore(corridor.severity_score),
    toMapScore(Number(flow.anomaly_score ?? 0)),
    toMapScore(Number(flow.attack_index ?? 0)),
    toMapScore(Number(flow.congestion_index ?? 0)),
  );
}

export default function PlanetaryIntelligence() {
  const [overview, setOverview] = useState<PlanetaryOverviewResponse | null>(() => loadCachedPlanetaryOverview());
  const [behaviorSignals, setBehaviorSignals] = useState<PlanetaryNormalizedSignal[]>([]);
  const [behaviorSourceEvents, setBehaviorSourceEvents] = useState<PlanetarySourceEvent[]>([]);
  const [graphEntities, setGraphEntities] = useState<PlanetaryWorldEntity[]>([]);
  const [graphRelationships, setGraphRelationships] = useState<PlanetaryWorldRelationship[]>([]);
  const [countryFusionSnapshots, setCountryFusionSnapshots] = useState<PlanetaryCountryFusionSnapshot[]>([]);
  const [fusionTimeline, setFusionTimeline] = useState<PlanetaryFusionTimelineFrame[]>([]);
  const [mapReplayFrames, setMapReplayFrames] = useState<PlanetaryMapReplayFrame[]>([]);
  const [correlationChains, setCorrelationChains] = useState<PlanetaryCorrelationChain[]>([]);
  const [calibrationReport, setCalibrationReport] = useState<PlanetaryCalibrationReportResponse | null>(null);
  const [behaviorSurface, setBehaviorSurface] = useState<PlanetaryBehaviorOperatorSurfaceResponse | null>(null);
  const [graphSummary, setGraphSummary] = useState<PlanetaryGraphSummaryResponse | null>(null);
  const [disasterCommand, setDisasterCommand] = useState<PlanetaryDisasterCommandSurfaceResponse | null>(null);
  const [commandLayer, setCommandLayer] = useState<PlanetaryCommandLayerResponse | null>(null);
  const [runtimeStatus, setRuntimeStatus] = useState<PlanetaryRuntimeStatusResponse | null>(null);
  const [drawerData, setDrawerData] = useState<InvestigationDrawerData | null>(null);
  const [drawerLabel, setDrawerLabel] = useState("Investigation drawer");
  const [drawerLoading, setDrawerLoading] = useState(false);
  const [drawerError, setDrawerError] = useState<string | null>(null);
  const [selectedChainId, setSelectedChainId] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [pendingAlertActionKey, setPendingAlertActionKey] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entityQuery, setEntityQuery] = useState("");
  const [heroFocusedCountryCode, setHeroFocusedCountryCode] = useState("");
  const [heroHoveredCountryCode, setHeroHoveredCountryCode] = useState("");
  const [heroMapQuery, setHeroMapQuery] = useState("");
  const [heroProjectionMode, setHeroProjectionMode] = useState<"command" | "cinematic">("command");
  const [heroLayerVisibility, setHeroLayerVisibility] = useState<Record<HeroLayerKey, boolean>>({
    behavior: true,
    hazards: true,
    corridors: true,
    alerts: true,
    graph: true,
  });
  const [selectedTimelineFrameId, setSelectedTimelineFrameId] = useState("");
  const [selectedMapReplayFrameId, setSelectedMapReplayFrameId] = useState("");
  const [timelineReplayActive, setTimelineReplayActive] = useState(false);
  const deferredEntityQuery = useDeferredValue(entityQuery.trim().toLowerCase());
  const currentOperator = localStorage.getItem("name") || localStorage.getItem("email") || "planetary-operator";
  const loadGenerationRef = useRef(0);

  const loadSupplementalConsole = useEffectEvent(async (refresh = false, generation = loadGenerationRef.current) => {
    const settled = await Promise.allSettled([
      getPlanetaryBehaviorNormalizedSignals(18, refresh),
      getPlanetaryBehaviorSourceEvents(18, refresh),
      getPlanetaryGraphEntities(18, refresh),
      getPlanetaryGraphRelationships(18, refresh),
      getPlanetaryCountryFusionSnapshots(18, refresh),
      getPlanetaryFusionTimeline(18, refresh),
      getPlanetaryReplayMapFrames(36, refresh),
      getPlanetaryCorrelationChains(12, refresh),
      getPlanetaryCalibrationReport(refresh),
      getPlanetaryBehaviorOperatorSurface(refresh),
      getPlanetaryGraphSummary(refresh),
      getPlanetaryDisasterCommand(refresh),
      getPlanetaryCommandLayer(refresh),
      getPlanetaryRuntimeStatus(refresh),
    ]);

    if (generation !== loadGenerationRef.current) return;

    const [
      nextBehaviorSignals,
      nextBehaviorEvents,
      nextGraphEntities,
      nextGraphRelationships,
      nextCountryFusionSnapshots,
      nextFusionTimeline,
      nextMapReplayFrames,
      nextCorrelationChains,
      nextCalibrationReport,
      nextBehaviorSurface,
      nextGraphSummary,
      nextDisasterCommand,
      nextCommandLayer,
      nextRuntimeStatus,
    ] = settled;

    startTransition(() => {
      if (nextBehaviorSignals.status === "fulfilled") {
        setBehaviorSignals(nextBehaviorSignals.value.normalized_signals || []);
      }
      if (nextBehaviorEvents.status === "fulfilled") {
        setBehaviorSourceEvents(nextBehaviorEvents.value.source_events || []);
      }
      if (nextGraphEntities.status === "fulfilled") {
        setGraphEntities(nextGraphEntities.value.world_entities || []);
      }
      if (nextGraphRelationships.status === "fulfilled") {
        setGraphRelationships(nextGraphRelationships.value.world_relationships || []);
      }
      if (nextCountryFusionSnapshots.status === "fulfilled") {
        setCountryFusionSnapshots(nextCountryFusionSnapshots.value.country_fusion_snapshots || []);
      }
      if (nextFusionTimeline.status === "fulfilled") {
        const nextTimeline = nextFusionTimeline.value.fusion_timeline || [];
        setFusionTimeline(nextTimeline);
        setSelectedTimelineFrameId((previous) => (
          previous && nextTimeline.some((item) => item.frame_id === previous)
            ? previous
            : nextTimeline[0]?.frame_id || ""
        ));
      }
      if (nextMapReplayFrames.status === "fulfilled") {
        const nextFrames = nextMapReplayFrames.value.replay_frames || [];
        setMapReplayFrames(nextFrames);
        setSelectedMapReplayFrameId((previous) => (
          previous && nextFrames.some((item) => item.frame_id === previous)
            ? previous
            : nextFrames[0]?.frame_id || ""
        ));
      }
      if (nextCorrelationChains.status === "fulfilled") {
        const nextChains = nextCorrelationChains.value.correlation_chains || [];
        setCorrelationChains(nextChains);
        setSelectedChainId((previous) => (
          previous && nextChains.some((item) => item.chain_id === previous)
            ? previous
            : nextChains[0]?.chain_id || ""
        ));
      }
      if (nextCalibrationReport.status === "fulfilled") {
        setCalibrationReport(nextCalibrationReport.value);
      }
      if (nextBehaviorSurface.status === "fulfilled") {
        setBehaviorSurface(nextBehaviorSurface.value);
      }
      if (nextGraphSummary.status === "fulfilled") {
        setGraphSummary(nextGraphSummary.value);
      }
      if (nextDisasterCommand.status === "fulfilled") {
        setDisasterCommand(nextDisasterCommand.value);
      }
      if (nextCommandLayer.status === "fulfilled") {
        setCommandLayer(nextCommandLayer.value);
      }
      if (nextRuntimeStatus.status === "fulfilled") {
        setRuntimeStatus(nextRuntimeStatus.value);
      }
    });
  });

  const loadConsole = useEffectEvent(async (refresh = false) => {
    const generation = loadGenerationRef.current + 1;
    loadGenerationRef.current = generation;
    if (refresh || overview) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    void getPlanetaryRuntimeStatus(refresh)
      .then((nextRuntimeStatus) => {
        if (generation !== loadGenerationRef.current) return;
        startTransition(() => {
          setRuntimeStatus(nextRuntimeStatus);
        });
        if (!hasRenderableOverviewData(overview) && (nextRuntimeStatus.behavior_surface || nextRuntimeStatus.command_layer)) {
          setLoading(false);
        }
      })
      .catch(() => undefined);

    try {
      let nextOverview = await getPlanetaryOverview(refresh);
      if (!hasRenderableOverviewData(nextOverview)) {
        await postPlanetaryRuntimeMaterialize(refresh, false);
        nextOverview = await getPlanetaryOverview(true);
      }
      if (generation !== loadGenerationRef.current) return;
      startTransition(() => {
        setOverview(nextOverview);
      });
      storeCachedPlanetaryOverview(nextOverview);
      if (refresh || !overview) {
        void loadSupplementalConsole(refresh, generation);
      }
    } catch (loadError) {
      if (generation === loadGenerationRef.current) {
        setError(loadError instanceof Error ? loadError.message : "Failed to load planetary intelligence console.");
      }
    } finally {
      if (generation === loadGenerationRef.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  });

  const openCountryInvestigation = useEffectEvent(async (country: string) => {
    const normalizedCountry = normalizeCountryCode(country) || country;
    setHeroFocusedCountryCode(normalizedCountry);
    setDrawerLabel(`${country} fusion evidence`);
    setDrawerLoading(true);
    setDrawerError(null);
    try {
      const payload = await getPlanetaryCountryFusionDetail(country);
      setDrawerData({ kind: "country", title: `${country} fusion evidence`, payload });
    } catch (drawerLoadError) {
      setDrawerData(null);
      setDrawerError(drawerLoadError instanceof Error ? drawerLoadError.message : "Failed to load country fusion detail.");
    } finally {
      setDrawerLoading(false);
    }
  });

  const openChainInvestigation = useEffectEvent(async (chainId: string) => {
    setDrawerLabel(`${chainId} correlation chain`);
    setDrawerLoading(true);
    setDrawerError(null);
    try {
      const payload = await getPlanetaryCorrelationChainDetail(chainId);
      setDrawerData({ kind: "chain", title: titleCase(payload.correlation_chain?.chain_type || chainId), payload });
      setSelectedChainId(chainId);
    } catch (drawerLoadError) {
      setDrawerData(null);
      setDrawerError(drawerLoadError instanceof Error ? drawerLoadError.message : "Failed to load correlation-chain detail.");
    } finally {
      setDrawerLoading(false);
    }
  });

  const openAlertInvestigation = useEffectEvent(async (alertId: string) => {
    setDrawerLabel(`${alertId} alert evidence`);
    setDrawerLoading(true);
    setDrawerError(null);
    try {
      const payload = await getPlanetaryAlertDetail(alertId);
      const alertCountryCode = normalizeCountryCode(alertCountry(payload.alert || undefined));
      if (alertCountryCode) {
        setHeroFocusedCountryCode(alertCountryCode);
      }
      setDrawerData({ kind: "alert", title: titleCase(payload.alert?.alert_type || alertId), payload });
    } catch (drawerLoadError) {
      setDrawerData(null);
      setDrawerError(drawerLoadError instanceof Error ? drawerLoadError.message : "Failed to load alert evidence.");
    } finally {
      setDrawerLoading(false);
    }
  });

  const openCorridorInvestigation = useEffectEvent(async (corridorId: string) => {
    setDrawerLabel(`${corridorId} corridor evidence`);
    setDrawerLoading(true);
    setDrawerError(null);
    try {
      const payload = await getPlanetaryCorridorDetail(corridorId);
      const primaryCountry = payload.country_scope?.[0] || "";
      if (primaryCountry) {
        setHeroFocusedCountryCode(primaryCountry);
      }
      setDrawerData({
        kind: "corridor",
        title: payload.corridor_snapshot
          ? `${payload.corridor_snapshot.from_region?.country || "UNK"} -> ${payload.corridor_snapshot.to_region?.country || "UNK"}`
          : corridorId,
        payload,
      });
    } catch (drawerLoadError) {
      setDrawerData(null);
      setDrawerError(drawerLoadError instanceof Error ? drawerLoadError.message : "Failed to load corridor evidence.");
    } finally {
      setDrawerLoading(false);
    }
  });

  const openEntityInvestigation = useEffectEvent(async (entityQueryValue: string, entityType?: string) => {
    setDrawerLabel(`${entityQueryValue} entity profile`);
    setDrawerLoading(true);
    setDrawerError(null);
    try {
      const payload = await getPlanetaryEntityProfile(entityQueryValue, false, entityType);
      setDrawerData({ kind: "entity", title: payload.entity?.canonical_name || entityQueryValue, payload });
    } catch (drawerLoadError) {
      setDrawerData(null);
      setDrawerError(drawerLoadError instanceof Error ? drawerLoadError.message : "Failed to load entity profile.");
    } finally {
      setDrawerLoading(false);
    }
  });

  const refreshCurrentDrawer = useEffectEvent(async () => {
    if (!drawerData) return;
    if (drawerData.kind === "country") {
      await openCountryInvestigation(drawerData.payload.country);
      return;
    }
    if (drawerData.kind === "chain") {
      await openChainInvestigation(drawerData.payload.chain_id);
      return;
    }
    if (drawerData.kind === "alert") {
      await openAlertInvestigation(drawerData.payload.alert_id);
      return;
    }
    if (drawerData.kind === "corridor") {
      await openCorridorInvestigation(drawerData.payload.corridor_id);
      return;
    }
    await openEntityInvestigation(drawerData.payload.entity?.entity_id || drawerData.payload.query, drawerData.payload.entity?.entity_type);
  });

  const handleAlertAction = useEffectEvent(async (alert: PlanetaryAlertEvent, action: PlanetaryAlertActionPayload["action"]) => {
    const actionKey = `${alert.alert_id}:${action}`;
    setPendingAlertActionKey(actionKey);
    setNotice(null);
    try {
      const payload: PlanetaryAlertActionPayload = {
        alert_type: alert.alert_type,
        action,
        alert_id: alert.alert_id,
        dedupe_key: alert.dedupe_key,
        country: alertCountry(alert),
        region: String(alert.geography?.region || "").trim() || undefined,
        severity: severityLabelFromRatio(alert.severity_score),
        owner: currentOperator,
        assignee: action === "assign" ? currentOperator : undefined,
        assignment_reason: action === "assign" ? "Assigned from planetary console" : undefined,
        team_queue: action === "assign" ? String(alert.assignment?.team || "planetary-ops") : undefined,
        snooze_hours: action === "snooze" ? 6 : undefined,
        false_positive_reason: action === "false_positive" ? "Planetary console false-positive flag" : undefined,
        comment: action === "acknowledge" ? "Acknowledged from planetary console" : undefined,
      };
      const result = await postPlanetaryAlertAction(payload);
      setNotice(
        action === "assign"
          ? `Assigned ${alert.alert_id} to ${result.assignee || currentOperator}.`
          : action === "snooze"
            ? `Snoozed ${alert.alert_id} until ${result.snoozed_until || "later"}.`
            : action === "false_positive"
              ? `Marked ${alert.alert_id} as false positive.`
              : `Acknowledged ${alert.alert_id}.`,
      );
      await loadConsole(true);
      await refreshCurrentDrawer();
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : "Failed to update planetary alert state.");
    } finally {
      setPendingAlertActionKey(null);
    }
  });

  const toggleHeroLayer = (layer: HeroLayerKey) => {
    setHeroLayerVisibility((previous) => ({ ...previous, [layer]: !previous[layer] }));
  };

  const jumpToCountry = () => {
    const resolvedCountry = resolveCountrySearchCode(heroMapQuery);
    if (!resolvedCountry) {
      setNotice(`No country match found for "${heroMapQuery.trim()}".`);
      return;
    }
    setHeroFocusedCountryCode(resolvedCountry);
    setTimelineReplayActive(false);
    setNotice(`Map focus moved to ${countryDisplayLabel(resolvedCountry)}.`);
  };

  useEffect(() => {
    void loadConsole(false);
    const intervalId = window.setInterval(() => {
      void loadConsole(false);
    }, 90000);
    return () => window.clearInterval(intervalId);
  }, [loadConsole]);

  const summary = overview?.global_summary;
  const behaviorSnapshot = overview?.behavior_global_snapshot;
  const signalStore = overview?.behavior_signal_store;
  const graphSnapshot = overview?.graph_snapshot;
  const fusionStore = overview?.fusion_store;
  const alertOpsSummary = overview?.alert_ops_summary;
  const runtimeManifest = (runtimeStatus?.manifest || null) as PlanetaryRuntimeManifest | null;
  const runtimeBehaviorSurface = runtimeStatus?.behavior_surface || null;
  const runtimeCommandLayer = runtimeStatus?.command_layer || null;
  const behaviorDeck = behaviorSurface || runtimeBehaviorSurface || null;
  const graphAnalytics = graphSummary || null;
  const disasterDeck = disasterCommand || null;
  const commandDeck = commandLayer || runtimeCommandLayer || null;
  const countrySnapshots = overview?.country_snapshots || [];
  const corridorSnapshots = overview?.corridor_snapshots || [];
  const hazardForecasts = overview?.hazard_forecasts || [];
  const allEntities = graphEntities.length ? graphEntities : overview?.world_entities || [];
  const allRelationships = graphRelationships.length ? graphRelationships : overview?.world_relationships || [];
  const allAlertEvents = overview?.alert_events || [];
  const alertEvents = [...allAlertEvents]
    .sort((left, right) => safeNumber(right.severity_score) - safeNumber(left.severity_score))
    .slice(0, 6);
  const runtimeStatuses = overview?.runtime_status || [];
  const replayFrames = overview?.replay_frames || [];
  const replayFrameItems = mapReplayFrames.slice(0, 36);
  const allCountryFusionSnapshots = countryFusionSnapshots.length ? countryFusionSnapshots : overview?.country_fusion_snapshots || [];
  const fusedCountries = allCountryFusionSnapshots.slice(0, 6);
  const timelineFramesAll = fusionTimeline.length ? fusionTimeline : overview?.fusion_timeline || [];
  const timelineItems = timelineFramesAll.slice(0, 8);
  const chains = correlationChains.length ? correlationChains : overview?.correlation_chains || [];
  const selectedTimelineFrame = timelineItems.find((item) => item.frame_id === selectedTimelineFrameId) || timelineItems[0] || null;
  const selectedMapReplayFrame = replayFrameItems.find((item) => item.frame_id === selectedMapReplayFrameId)
    || closestReplayFrame(replayFrameItems, selectedTimelineFrame)
    || replayFrameItems[0]
    || null;
  const activeMapReplayFrame = timelineReplayActive ? selectedMapReplayFrame : null;
  const selectedChain = chains.find((item) => item.chain_id === selectedChainId) || chains[0] || null;
  const selectedChainStages = (selectedChain?.stages || []).slice(0, 6);
  const filteredEntities = allEntities
    .filter((item) => {
      if (!deferredEntityQuery) return true;
      const aliases = (item.aliases || []).join(" ").toLowerCase();
      const haystack = `${item.entity_id} ${item.entity_type} ${item.canonical_name} ${aliases} ${geographyLabel(item)}`.toLowerCase();
      return haystack.includes(deferredEntityQuery);
    })
    .slice(0, 8);
  const filteredRelationships = allRelationships
    .filter((item) => relationMatchesQuery(item, deferredEntityQuery))
    .slice(0, 8);
  const entityTypeCounts = allEntities.reduce<Record<string, number>>((acc, item) => {
    const key = item.entity_type || "unknown";
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const graphFocusTypes = [
    { label: "Countries", value: entityTypeCounts.country || graphAnalytics?.entity_type_counts?.country || 0 },
    { label: "Events", value: entityTypeCounts.named_event || graphAnalytics?.entity_type_counts?.named_event || 0 },
    { label: "Organizations", value: entityTypeCounts.organization || graphAnalytics?.entity_type_counts?.organization || 0 },
    { label: "Narratives", value: entityTypeCounts.narrative_topic || graphAnalytics?.entity_type_counts?.narrative_topic || 0 },
  ].filter((item) => item.value > 0);
  const rankedSignals = [...behaviorSignals]
    .sort((left, right) => safeNumber(right.severity_score) - safeNumber(left.severity_score))
    .slice(0, 6);
  const evidenceFeed = [...behaviorSourceEvents].slice(0, 6);
  const queueBreakdown = alertOpsSummary?.queue_breakdown || [];
  const runtimeBootstrapReady = Boolean(runtimeBehaviorSurface || runtimeCommandLayer);
  const canRenderConsole = Boolean(hasRenderableOverviewData(overview) || runtimeBootstrapReady);
  const refreshedLabel = overview
    ? formatRelativeTime(overview.generated_at)
    : runtimeManifest?.captured_at
      ? formatRelativeTime(runtimeManifest.captured_at)
      : "Awaiting first sync";
  const qualityGateMessage = summary?.quality_gate?.message
    || (runtimeBootstrapReady
      ? "Runtime-backed planetary snapshot is visible while deep overview layers finish loading."
      : "Cross-system posture steady");
  const overviewCountryCount = countrySnapshots.length || safeNumber(runtimeManifest?.behavior_country_count, 0) || safeNumber((behaviorDeck as { top_countries?: unknown[] } | null)?.top_countries?.length, 0);
  const overviewCorridorCount = corridorSnapshots.length;
  const overviewHazardCount = hazardForecasts.length || safeNumber(runtimeManifest?.disaster_focus_count, 0);
  const overviewAlertCount = allAlertEvents.length || safeNumber(commandDeck?.incident_watchlist?.length, 0);
  const heroCountBadges = [
    { label: "Countries", value: overviewCountryCount },
    { label: "Corridors", value: overviewCorridorCount },
    { label: "Hazards", value: overviewHazardCount },
    { label: "Alerts", value: overviewAlertCount },
  ];
  const calibrationDisaster = (calibrationReport?.disaster_likelihood || {}) as Record<string, unknown>;
  const calibrationBehavior = (calibrationReport?.behavior_thresholds || {}) as Record<string, unknown>;
  const calibrationFusion = (calibrationReport?.fusion_scoring || {}) as Record<string, unknown>;
  const calibrationBacktests = (calibrationReport?.backtests || {}) as Record<string, unknown>;
  const commandTheaters = (commandDeck?.theaters || []).slice(0, 6);
  const commandWatchlist = (commandDeck?.incident_watchlist || []).slice(0, 6);
  const graphTopEntities = (graphAnalytics?.top_entities || []).slice(0, 4);
  const disasterTopRegions = (disasterDeck?.top_regions || []).slice(0, 4);
  const graphNeighborhoodNodes = filteredEntities.slice(0, 6).map((item, index, collection) => {
    const angle = (Math.PI * 2 * index) / Math.max(collection.length, 1);
    return {
      ...item,
      left: 50 + Math.cos(angle) * 32,
      top: 50 + Math.sin(angle) * 28,
    };
  });
  const graphNodeIndex = new Map(graphNeighborhoodNodes.map((item) => [item.entity_id, item]));
  const graphNeighborhoodLinks = filteredRelationships
    .filter((item) => graphNodeIndex.has(item.source_entity_id) && graphNodeIndex.has(item.target_entity_id))
    .slice(0, 8);
  const commandOverlaySeries = commandTheaters.slice(0, 6).map((item) => normalizeRatio(item.overall_pressure));
  const commandOverlayPath = buildMiniTrendPath(commandOverlaySeries);
  const replayAlertIds = new Set((timelineReplayActive ? selectedTimelineFrame?.alert_refs : []) || []);
  const replayChainIds = new Set((timelineReplayActive ? selectedTimelineFrame?.chain_refs : []) || []);
  const replaySnapshotRefs = new Set((timelineReplayActive ? selectedTimelineFrame?.snapshot_refs : []) || []);
  const replayCountryCodes = new Set<string>();
  if (activeMapReplayFrame) {
    (activeMapReplayFrame.countries || []).forEach((item) => {
      const code = normalizeCountryCode(item.country);
      if (code) replayCountryCodes.add(code);
    });
  } else if (timelineReplayActive && selectedTimelineFrame?.country) {
    const replayCountry = normalizeCountryCode(selectedTimelineFrame.country);
    if (replayCountry) replayCountryCodes.add(replayCountry);
  }
  if (!activeMapReplayFrame) {
    allCountryFusionSnapshots
      .filter((item) => replaySnapshotRefs.has(String(item.fusion_id || "")))
      .forEach((item) => {
        const code = normalizeCountryCode(item.country);
        if (code) replayCountryCodes.add(code);
      });
    chains
      .filter((item) => replayChainIds.has(item.chain_id))
      .forEach((item) => {
        const code = normalizeCountryCode(item.country);
        if (code) replayCountryCodes.add(code);
      });
    allAlertEvents
      .filter((item) => replayAlertIds.has(item.alert_id))
      .forEach((item) => {
        const code = normalizeCountryCode(alertCountry(item));
        if (code) replayCountryCodes.add(code);
      });
    corridorSnapshots
      .filter((item) => replaySnapshotRefs.has(String(item.corridor_id || "")))
      .forEach((item) => {
        const fromCode = normalizeCountryCode(item.from_region?.country);
        const toCode = normalizeCountryCode(item.to_region?.country);
        if (fromCode) replayCountryCodes.add(fromCode);
        if (toCode) replayCountryCodes.add(toCode);
      });
  }
  const replayCountryFilter = timelineReplayActive && replayCountryCodes.size ? replayCountryCodes : null;
  const graphInfluenceCodes = new Set(
    graphTopEntities
      .map((item) => entityCountryCode(item as PlanetaryWorldEntity))
      .filter(Boolean),
  );
  const liveHeroCountryIndex = new Map<string, { country: string; countryCode: string; risk: number; lat: number; lng: number }>();
  const mergeHeroCountry = (country: string | undefined | null, value: number | undefined | null) => {
    const countryCode = normalizeCountryCode(country);
    if (!countryCode) return;
    const point = PLANETARY_COUNTRY_COORDS[countryCode];
    if (!point) return;
    const risk = toMapScore(value);
    const existing = liveHeroCountryIndex.get(countryCode);
    if (!existing || risk > existing.risk) {
      liveHeroCountryIndex.set(countryCode, {
        country: countryCode,
        countryCode,
        risk,
        lat: point.lat,
        lng: point.lng,
      });
    }
  };
  countrySnapshots.forEach((item) => mergeHeroCountry(item.country, item.display_risk ?? item.raw_risk_score ?? item.confidence_ratio));
  allCountryFusionSnapshots.forEach((item) => mergeHeroCountry(item.country, item.fused_score));
  commandTheaters.forEach((item) => mergeHeroCountry(item.country, item.overall_pressure));
  hazardForecasts.forEach((item) => mergeHeroCountry(item.country, Math.max(safeNumber(item.likelihood), safeNumber(item.severity_score))));
  allAlertEvents.forEach((item) => mergeHeroCountry(alertCountry(item), item.severity_score));
  const liveHeroGlobeCountriesBase = [...liveHeroCountryIndex.values()]
    .sort((left, right) => right.risk - left.risk)
    .slice(0, 36);
  const replayHeroGlobeCountriesBase = (activeMapReplayFrame?.countries || [])
    .map((item) => {
      const countryCode = normalizeCountryCode(item.country);
      if (!countryCode) return null;
      const point = PLANETARY_COUNTRY_COORDS[countryCode];
      if (!point) return null;
      return {
        country: countryCode,
        countryCode,
        risk: toMapScore(item.fused_score),
        lat: point.lat,
        lng: point.lng,
      };
    })
    .filter(Boolean) as Array<{ country: string; countryCode: string; risk: number; lat: number; lng: number }>;
  const heroGlobeCountriesBase = replayHeroGlobeCountriesBase.length ? replayHeroGlobeCountriesBase : liveHeroGlobeCountriesBase;
  const heroGlobeCountries = (
    heroLayerVisibility.behavior
      ? (replayHeroGlobeCountriesBase.length
        ? replayHeroGlobeCountriesBase
        : heroGlobeCountriesBase.filter((item) => !replayCountryFilter || replayCountryFilter.has(item.countryCode)))
      : []
  ).slice(0, replayCountryFilter ? 18 : 24);
  const liveHeroHazardMarkersBase = hazardForecasts
    .map((item) => {
      const point = resolvePlanetaryMarkerPoint(item.country, item.region);
      if (!point) return null;
      const probability = Math.max(toMapScore(item.likelihood), toMapScore(item.severity_score));
      return {
        id: item.forecast_id,
        name: `${titleCase(item.hazard_type)} ${normalizeCountryCode(item.country) || item.region || "forecast"}`.trim(),
        category: "Hazard forecast",
        lat: point.lat,
        lng: point.lng,
        probability,
        kind: hazardKind(item.hazard_type),
        country: point.countryCode || normalizeCountryCode(item.country),
        detail: `Likelihood ${formatPercent(item.likelihood, 0)} / Severity ${formatPercent(item.severity_score, 0)}`,
      };
    })
    .filter(Boolean) as Array<GlobeEventMarker & { country?: string; detail: string }>;
  const liveHeroAlertMarkersBase = allAlertEvents
    .map((item) => {
      const country = alertCountry(item);
      const point = resolvePlanetaryMarkerPoint(country, String(item.geography?.region || ""));
      if (!point) return null;
      return {
        id: item.alert_id,
        name: titleCase(item.alert_type),
        category: geographyLabel(item),
        lat: point.lat,
        lng: point.lng,
        probability: toMapScore(item.severity_score),
        kind: alertMarkerKind(item.alert_type, item.summary),
        country: point.countryCode || country,
        alertId: item.alert_id,
        detail: item.summary || "Investigate alert evidence and queue posture.",
      };
    })
    .filter(Boolean) as Array<GlobeEventMarker & { country?: string; alertId?: string; detail: string }>;
  const replayHotspotRows = activeMapReplayFrame?.hotspots || [];
  const replayHeroHazardMarkersBase = replayHotspotRows
    .filter((item) => item.kind === "hazard")
    .map((item) => {
      const point = resolvePlanetaryMarkerPoint(item.country, item.region);
      if (!point) return null;
      return {
        id: item.marker_id,
        name: item.label || "Hazard",
        category: item.region || "Hazard forecast",
        lat: point.lat,
        lng: point.lng,
        probability: Math.max(toMapScore(item.likelihood), toMapScore(item.severity_score)),
        kind: hazardKind(item.label),
        country: point.countryCode || normalizeCountryCode(item.country),
        detail: `Likelihood ${formatPercent(item.likelihood, 0)} / Severity ${formatPercent(item.severity_score, 0)}`,
      };
    })
    .filter(Boolean) as Array<GlobeEventMarker & { country?: string; detail: string }>;
  const replayHeroAlertMarkersBase = replayHotspotRows
    .filter((item) => item.kind === "alert")
    .map((item) => {
      const point = resolvePlanetaryMarkerPoint(item.country, item.region);
      if (!point) return null;
      return {
        id: item.marker_id,
        name: item.label || "Alert",
        category: item.region || "Alert",
        lat: point.lat,
        lng: point.lng,
        probability: toMapScore(item.severity_score),
        kind: alertMarkerKind(item.label, item.region),
        country: point.countryCode || normalizeCountryCode(item.country),
        alertId: item.marker_id,
        detail: item.region || "Investigate replayed alert evidence.",
      };
    })
    .filter(Boolean) as Array<GlobeEventMarker & { country?: string; alertId?: string; detail: string }>;
  const heroHazardMarkersBase = replayHeroHazardMarkersBase.length ? replayHeroHazardMarkersBase : liveHeroHazardMarkersBase;
  const heroAlertMarkersBase = replayHeroAlertMarkersBase.length ? replayHeroAlertMarkersBase : liveHeroAlertMarkersBase;
  const liveHeroFlowArcsBase = corridorSnapshots
    .map((item) => {
      const fromCountry = normalizeCountryCode(item.from_region?.country);
      const toCountry = normalizeCountryCode(item.to_region?.country);
      const fromPoint = fromCountry ? PLANETARY_COUNTRY_COORDS[fromCountry] : null;
      const toPoint = toCountry ? PLANETARY_COUNTRY_COORDS[toCountry] : null;
      if (!fromPoint || !toPoint) return null;
      return {
        id: item.corridor_id,
        fromCountry,
        toCountry,
        fromLat: fromPoint.lat,
        fromLng: fromPoint.lng,
        toLat: toPoint.lat,
        toLng: toPoint.lng,
        intensity: corridorIntensity(item),
        label: `${fromCountry} -> ${toCountry}`,
        category: "Corridor flow",
      };
    })
    .filter(Boolean)
    .sort((left, right) => safeNumber(right?.intensity) - safeNumber(left?.intensity))
    .slice(0, 12) as GlobeFlowArc[];
  const replayHeroFlowArcsBase = (activeMapReplayFrame?.corridors || [])
    .map((item) => {
      const fromCountry = normalizeCountryCode((item as { from_country?: string }).from_country);
      const toCountry = normalizeCountryCode((item as { to_country?: string }).to_country);
      const fromPoint = fromCountry ? PLANETARY_COUNTRY_COORDS[fromCountry] : null;
      const toPoint = toCountry ? PLANETARY_COUNTRY_COORDS[toCountry] : null;
      if (!fromPoint || !toPoint) return null;
      return {
        id: item.corridor_id,
        fromCountry,
        toCountry,
        fromLat: fromPoint.lat,
        fromLng: fromPoint.lng,
        toLat: toPoint.lat,
        toLng: toPoint.lng,
        intensity: toMapScore(item.severity_score),
        label: `${fromCountry} -> ${toCountry}`,
        category: "Replay corridor",
      };
    })
    .filter(Boolean)
    .slice(0, 12) as GlobeFlowArc[];
  const heroFlowArcsBase = replayHeroFlowArcsBase.length ? replayHeroFlowArcsBase : liveHeroFlowArcsBase;
  const heroHazardMarkers = heroLayerVisibility.hazards
    ? spreadHeroMarkers(heroHazardMarkersBase.filter((item) => !replayCountryFilter || replayCountryFilter.has(String(item.country || ""))))
    : [];
  const heroAlertMarkers = heroLayerVisibility.alerts
    ? spreadHeroMarkers(heroAlertMarkersBase.filter((item) => !replayCountryFilter || replayCountryFilter.has(String(item.country || "")) || replayAlertIds.has(String(item.alertId || ""))))
    : [];
  const heroFlowArcs = heroLayerVisibility.corridors
    ? heroFlowArcsBase.filter((item) => (
      !replayCountryFilter
      || replayCountryFilter.has(String(item.fromCountry || ""))
      || replayCountryFilter.has(String(item.toCountry || ""))
    ))
    : [];
  const heroGlobeEvents = [...heroHazardMarkers, ...heroAlertMarkers]
    .sort((left, right) => right.probability - left.probability)
    .slice(0, 14);
  const heroHotspots = pickDistributedHotspots([...heroHazardMarkers, ...heroAlertMarkers]
    .sort((left, right) => right.probability - left.probability)
    .slice(0, 10), 5);
  const graphLayerCountries = heroGlobeCountriesBase
    .filter((item) => graphInfluenceCodes.has(item.countryCode) || replayCountryFilter?.has(item.countryCode));
  const heroLabelCountryCodes = heroLayerVisibility.graph
    ? pickLabelCountryCodes(graphLayerCountries.length ? graphLayerCountries : heroGlobeCountriesBase, 8)
    : [];
  const heroLeadCountry = [...replayCountryCodes][0]
    || activeMapReplayFrame?.countries?.[0]?.country
    || commandTheaters[0]?.country
    || heroGlobeCountriesBase[0]?.countryCode
    || countrySnapshots[0]?.country
    || "GLOBAL";
  const countryAlertCounts = allAlertEvents.reduce<Record<string, number>>((acc, item) => {
    const key = normalizeCountryCode(alertCountry(item));
    if (!key) return acc;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const countryHazardCounts = hazardForecasts.reduce<Record<string, number>>((acc, item) => {
    const key = normalizeCountryCode(item.country);
    if (!key) return acc;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const countryCorridorCounts = corridorSnapshots.reduce<Record<string, number>>((acc, item) => {
    const fromKey = normalizeCountryCode(item.from_region?.country);
    const toKey = normalizeCountryCode(item.to_region?.country);
    if (fromKey) acc[fromKey] = (acc[fromKey] || 0) + 1;
    if (toKey) acc[toKey] = (acc[toKey] || 0) + 1;
    return acc;
  }, {});
  const replayCountryAlertCounts = (activeMapReplayFrame?.hotspots || []).reduce<Record<string, number>>((acc, item) => {
    if (item.kind !== "alert") return acc;
    const key = normalizeCountryCode(item.country);
    if (!key) return acc;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const replayCountryHazardCounts = (activeMapReplayFrame?.hotspots || []).reduce<Record<string, number>>((acc, item) => {
    if (item.kind !== "hazard") return acc;
    const key = normalizeCountryCode(item.country);
    if (!key) return acc;
    acc[key] = (acc[key] || 0) + 1;
    return acc;
  }, {});
  const replayCountryCorridorCounts = (activeMapReplayFrame?.corridors || []).reduce<Record<string, number>>((acc, item) => {
    const fromKey = normalizeCountryCode((item as { from_country?: string }).from_country);
    const toKey = normalizeCountryCode((item as { to_country?: string }).to_country);
    if (fromKey) acc[fromKey] = (acc[fromKey] || 0) + 1;
    if (toKey) acc[toKey] = (acc[toKey] || 0) + 1;
    return acc;
  }, {});
  const activeCountryAlertCounts = activeMapReplayFrame ? replayCountryAlertCounts : countryAlertCounts;
  const activeCountryHazardCounts = activeMapReplayFrame ? replayCountryHazardCounts : countryHazardCounts;
  const activeCountryCorridorCounts = activeMapReplayFrame ? replayCountryCorridorCounts : countryCorridorCounts;
  const heroCountryDetails = heroGlobeCountriesBase.reduce<Record<string, GlobeCountryDetail>>((acc, item) => {
    const snapshot = countrySnapshots.find((entry) => normalizeCountryCode(entry.country) === item.countryCode);
    const fusion = allCountryFusionSnapshots.find((entry) => normalizeCountryCode(entry.country) === item.countryCode);
    const theater = (commandDeck?.theaters || []).find((entry) => normalizeCountryCode(entry.country) === item.countryCode);
    acc[item.countryCode] = {
      label: countryDisplayLabel(item.countryCode),
      riskBand: titleCase(fusion?.fusion_band || snapshot?.risk_band || "monitored"),
      confidence: toMapScore(fusion?.confidence_ratio ?? snapshot?.confidence_ratio ?? 0),
      alerts: activeCountryAlertCounts[item.countryCode] || 0,
      hazards: activeCountryHazardCounts[item.countryCode] || 0,
      corridors: activeCountryCorridorCounts[item.countryCode] || 0,
      trend: titleCase(snapshot?.risk_trend_direction || "watch"),
      advisory: theater?.recommended_action || fusion?.recommended_action || snapshot?.advisory || "Inspect fusion evidence and operator queue posture.",
      pressure: toMapScore(fusion?.fused_score ?? theater?.overall_pressure ?? snapshot?.display_risk ?? snapshot?.raw_risk_score ?? 0),
    };
    return acc;
  }, {});
  const heroMapSearchOptions = Object.entries(PLANETARY_COUNTRY_LABELS)
    .filter(([code]) => heroCountryDetails[code] || PLANETARY_COUNTRY_COORDS[code])
    .map(([code, label]) => ({ code, label }));
  const heroActiveCountryCode = heroHoveredCountryCode || heroFocusedCountryCode || normalizeCountryCode(heroLeadCountry);
  const focusedReplayCountry = (activeMapReplayFrame?.countries || []).find((item) => normalizeCountryCode(item.country) === heroActiveCountryCode) || null;
  const focusedCountrySnapshot = countrySnapshots.find((item) => normalizeCountryCode(item.country) === heroActiveCountryCode) || null;
  const focusedFusionSnapshot = allCountryFusionSnapshots.find((item) => normalizeCountryCode(item.country) === heroActiveCountryCode) || null;
  const focusedTheater = (commandDeck?.theaters || []).find((item) => normalizeCountryCode(item.country) === heroActiveCountryCode) || null;
  const focusedAlerts = allAlertEvents.filter((item) => normalizeCountryCode(alertCountry(item)) === heroActiveCountryCode);
  const focusedHazards = hazardForecasts.filter((item) => normalizeCountryCode(item.country) === heroActiveCountryCode);
  const focusedCorridors = corridorSnapshots.filter((item) => (
    normalizeCountryCode(item.from_region?.country) === heroActiveCountryCode
    || normalizeCountryCode(item.to_region?.country) === heroActiveCountryCode
  ));
  const focusedPressureScore = focusedReplayCountry?.fused_score ?? focusedFusionSnapshot?.fused_score ?? focusedTheater?.overall_pressure ?? focusedCountrySnapshot?.display_risk ?? focusedCountrySnapshot?.raw_risk_score ?? 0;
  const focusedConfidence = focusedReplayCountry?.confidence_ratio ?? focusedFusionSnapshot?.confidence_ratio ?? focusedCountrySnapshot?.confidence_ratio ?? 0;
  const focusedBehaviorScore = safeNumber(
    Number(
      focusedReplayCountry?.subsystem_scores?.behavior
      ?? focusedReplayCountry?.subsystem_scores?.context
      ?? focusedFusionSnapshot?.subsystem_scores?.behavior
      ?? focusedFusionSnapshot?.subsystem_scores?.context
      ?? focusedCountrySnapshot?.signal_scores?.behavior
      ?? behaviorSnapshot?.global_behavior_index
      ?? 0,
    ),
  );
  const focusedInfrastructureScore = safeNumber(
    Number(
      focusedReplayCountry?.subsystem_scores?.internet
      ?? focusedReplayCountry?.subsystem_scores?.infrastructure
      ?? focusedFusionSnapshot?.subsystem_scores?.internet
      ?? focusedFusionSnapshot?.subsystem_scores?.infrastructure
      ?? focusedTheater?.fusion_risk
      ?? summary?.infrastructure_fragility_score
      ?? 0,
    ),
  );
  const focusedFocusLabel = heroActiveCountryCode ? countryDisplayLabel(heroActiveCountryCode) : "GLOBAL";
  const focusedAdvisory = focusedReplayCountry?.recommended_action || focusedTheater?.recommended_action || focusedFusionSnapshot?.recommended_action || focusedCountrySnapshot?.advisory || "Inspect fusion evidence, alerts, and corridor stress for the active map focus.";
  const focusedStateVector = Object.entries((focusedFusionSnapshot?.state_vector || focusedReplayCountry?.subsystem_scores || focusedFusionSnapshot?.subsystem_scores || {})).slice(0, 4);
  const heroProjectionType = heroProjectionMode === "command" ? "natural earth" : "orthographic";
  const heroProjectionScale = heroProjectionMode === "command" ? 1.34 : 0.98;
  const heroProjectionCaption = heroProjectionMode === "command"
    ? "Flat command-map mode keeps corridors, hazards, and country risk in one operational plane."
    : "Cinematic globe mode emphasizes global theater posture with a curved-earth lens.";
  const replaySliderUsesStoredFrames = replayFrameItems.length > 0;
  const replaySliderMax = Math.max((replaySliderUsesStoredFrames ? replayFrameItems.length : timelineItems.length) - 1, 0);
  const replaySliderValue = replaySliderUsesStoredFrames
    ? Math.max(0, replayFrameItems.findIndex((item) => item.frame_id === selectedMapReplayFrameId))
    : Math.max(0, timelineItems.findIndex((item) => item.frame_id === selectedTimelineFrameId));

  useEffect(() => {
    if (!selectedTimelineFrameId && timelineItems[0]?.frame_id) {
      setSelectedTimelineFrameId(timelineItems[0].frame_id);
    }
  }, [selectedTimelineFrameId, timelineItems]);

  useEffect(() => {
    if (!selectedMapReplayFrameId && replayFrameItems[0]?.frame_id) {
      setSelectedMapReplayFrameId(replayFrameItems[0].frame_id);
      return;
    }
    if (!timelineReplayActive) {
      return;
    }
    const nextFrame = closestReplayFrame(replayFrameItems, selectedTimelineFrame);
    if (nextFrame?.frame_id && nextFrame.frame_id !== selectedMapReplayFrameId) {
      setSelectedMapReplayFrameId(nextFrame.frame_id);
    }
  }, [selectedMapReplayFrameId, replayFrameItems, selectedTimelineFrame, timelineReplayActive]);

  useEffect(() => {
    const replayCountry = activeMapReplayFrame?.countries?.[0]?.country || selectedTimelineFrame?.country;
    if (timelineReplayActive && replayCountry) {
      const countryCode = normalizeCountryCode(replayCountry);
      if (countryCode) {
        setHeroFocusedCountryCode(countryCode);
      }
    }
  }, [timelineReplayActive, activeMapReplayFrame?.frame_id, activeMapReplayFrame?.countries, selectedTimelineFrame?.frame_id, selectedTimelineFrame?.country]);

  const runtimeMaterializationStats = [
    { label: "Behavior runtime", value: runtimeManifest?.behavior_country_count || runtimeBehaviorSurface?.top_countries?.length || 0, detail: `${runtimeManifest?.behavior_replay_count || runtimeBehaviorSurface?.replay_frames?.length || 0} replay frames` },
    { label: "Command theaters", value: runtimeManifest?.command_theater_count || runtimeCommandLayer?.theaters?.length || 0, detail: `${runtimeManifest?.command_watchlist_count || runtimeCommandLayer?.incident_watchlist?.length || 0} watchlist items` },
    { label: "Graph focus", value: runtimeManifest?.graph_focus_count || runtimeCommandLayer?.graph_command_focus?.length || 0, detail: `${runtimeManifest?.disaster_focus_count || runtimeCommandLayer?.disaster_command_focus?.length || 0} disaster focus lanes` },
  ];
  const drawerOpen = Boolean(drawerData || drawerLoading || drawerError);
  const drawerSummary = investigationEvidenceSummary(drawerData);
  const drawerAlerts = investigationAlerts(drawerData).slice(0, 6);
  const drawerSignals = investigationSignals(drawerData).slice(0, 8);
  const drawerSourceEvents = investigationSourceEvents(drawerData).slice(0, 8);
  const drawerEntities = investigationEntities(drawerData).slice(0, 8);
  const drawerRelationships = investigationRelationships(drawerData).slice(0, 8);
  const drawerTimeline = investigationTimeline(drawerData).slice(0, 8);
  const drawerHazards = investigationHazards(drawerData).slice(0, 6);
  const drawerCorridors = investigationCorridors(drawerData).slice(0, 6);
  const drawerChains = investigationCorrelationChains(drawerData).slice(0, 6);
  const drawerProvenance = investigationProvenance(drawerData).slice(0, 8);
  const drawerPrimaryAlert = drawerAlerts[0] || null;
  const drawerSubsystemScores = Object.entries(drawerSummary?.subsystem_scores || {}).slice(0, 6);
  const drawerStateVector = Object.entries(drawerSummary?.state_vector || {}).slice(0, 6);
  const drawerHistory = (drawerData?.payload.operator_history || []).slice(0, 8);

  return (
    <div className={`wp-page planetary-console${drawerOpen ? " planetary-console--drawer-open" : ""}`}>
      <ConsoleNavigation
        title={<>Planetary Intelligence Console</>}
        subtitle="Cross-system behavior, disaster, internet, and graph intelligence fused into one operator surface."
        rightSlot={
          <div className="planetary-console__header-actions">
            <div className="planetary-console__stamp">
              <span>Updated {refreshedLabel}</span>
              <strong>{runtimeManifest?.contract_version || overview?.contract_version || "phase-0.2"}</strong>
            </div>
            <button
              type="button"
              className="planetary-console__refresh"
              onClick={() => void loadConsole(true)}
              disabled={refreshing}
            >
              {refreshing ? "Refreshing..." : "Refresh live view"}
            </button>
          </div>
        }
        sectionTabs={[
          { label: "Overview", targetId: "planetary-overview", badge: String(overviewCountryCount || 0) },
          { label: "Command", targetId: "planetary-command", badge: String(commandTheaters.length || safeNumber(runtimeManifest?.command_theater_count, 0) || 0) },
          { label: "Fusion", targetId: "planetary-fusion", badge: String(fusedCountries.length || 0) },
          { label: "Behavior", targetId: "planetary-behavior", badge: String(rankedSignals.length || safeNumber(runtimeManifest?.behavior_replay_count, 0) || 0) },
          { label: "Timeline", targetId: "planetary-timeline", badge: String(timelineItems.length || 0) },
          { label: "Graph", targetId: "planetary-graph", badge: String(filteredEntities.length || safeNumber(runtimeManifest?.graph_focus_count, 0) || 0) },
          { label: "Runtime", targetId: "planetary-runtime", badge: String(runtimeStatuses.length || 0) },
        ]}
        sectionRightSlot={
          <div className="planetary-console__section-meta">
            <span className={`planetary-badge ${summary?.quality_gate?.active ? "is-critical" : "is-stable"}`}>
              {summary?.quality_gate?.active ? "Quality gate active" : "Quality gate open"}
            </span>
            <span className="planetary-badge">
              Behavior store {signalStore?.source_event_count || 0}/{signalStore?.normalized_signal_count || 0}
            </span>
            <span className="planetary-badge">
              Fusion {fusionStore?.country_fusion_count || 0}/{fusionStore?.correlation_chain_count || 0}
            </span>
            <span className="planetary-badge">
              Graph {graphSnapshot?.world_entity_count || 0}/{graphSnapshot?.world_relationship_count || 0}
            </span>
            <span className="planetary-badge">
              Command {commandDeck?.incident_watchlist?.length || 0}/{commandDeck?.theaters?.length || safeNumber(runtimeManifest?.command_theater_count, 0)}
            </span>
            <span className="planetary-badge">
              Ops {alertOpsSummary?.active_queue_count || 0} active
            </span>
          </div>
        }
      />

      <main className="planetary-console__main">
        {error ? (
          <section className="planetary-console__error">
            <strong>Console degraded.</strong>
            <span>{error}</span>
          </section>
        ) : null}

        {!canRenderConsole && loading ? (
          <section className="planetary-console__loading-panel">
            <div className="planetary-console__loading-orb" />
            <div>
              <strong>Building planetary console snapshot</strong>
              <p>Aggregating behavior, disaster, internet, and graph layers into one operator-ready view.</p>
            </div>
          </section>
        ) : null}

        {canRenderConsole ? (
          <>
            {notice ? (
              <section className="planetary-console__notice">
                <strong>Operator update</strong>
                <span>{notice}</span>
              </section>
            ) : null}

            <section id="planetary-overview" className="planetary-console__hero">
              <div className="planetary-console__hero-map-panel">
                <div className="planetary-panel__header planetary-console__hero-map-header">
                  <div>
                    <span className="planetary-panel__eyebrow">World state canvas</span>
                    <h3>Live planetary world map</h3>
                  </div>
                  <div className="planetary-chip-cloud">
                    <span className="planetary-badge">Countries {heroGlobeCountries.length}</span>
                    <span className="planetary-badge">Hotspots {heroGlobeEvents.length}</span>
                    <span className={`planetary-badge ${timelineReplayActive ? "is-elevated" : "is-stable"}`}>
                      {timelineReplayActive ? "Replay active" : "Live mode"}
                    </span>
                    <span className={`planetary-badge ${toneClassFromRatio(summary?.global_stress_level)}`}>
                      Lead theater {heroLeadCountry}
                    </span>
                  </div>
                </div>
                <div className="planetary-console__hero-map-toolbar">
                  <div className="planetary-console__hero-map-toolbar-group">
                    <span className="planetary-console__eyebrow">Layers</span>
                    <div className="planetary-chip-cloud">
                      {HERO_LAYER_OPTIONS.map((item) => (
                        <button
                          key={item.key}
                          type="button"
                          className={`planetary-console__toggle ${heroLayerVisibility[item.key] ? "is-active" : ""}`}
                          onClick={() => toggleHeroLayer(item.key)}
                        >
                          {item.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div className="planetary-console__hero-map-toolbar-group">
                    <span className="planetary-console__eyebrow">Projection</span>
                    <div className="planetary-chip-cloud">
                      <button
                        type="button"
                        className={`planetary-console__toggle ${heroProjectionMode === "command" ? "is-active" : ""}`}
                        onClick={() => setHeroProjectionMode("command")}
                      >
                        Command map
                      </button>
                      <button
                        type="button"
                        className={`planetary-console__toggle ${heroProjectionMode === "cinematic" ? "is-active" : ""}`}
                        onClick={() => setHeroProjectionMode("cinematic")}
                      >
                        Cinematic globe
                      </button>
                    </div>
                  </div>
                  <form
                    className="planetary-console__hero-map-search"
                    onSubmit={(event) => {
                      event.preventDefault();
                      jumpToCountry();
                    }}
                  >
                    <label className="planetary-console__search">
                      <span>Search + jump</span>
                      <input
                        type="search"
                        list="planetary-country-search-options"
                        value={heroMapQuery}
                        onChange={(event) => setHeroMapQuery(event.target.value)}
                        placeholder="Ukraine, India, Turkey, USA..."
                      />
                    </label>
                    <datalist id="planetary-country-search-options">
                      {heroMapSearchOptions.map((item) => (
                        <option key={`map-search:${item.code}`} value={item.label} />
                      ))}
                    </datalist>
                    <button type="submit" className="planetary-link-button">Jump</button>
                  </form>
                </div>
                <div className="planetary-console__hero-replay-strip">
                  <div>
                    <span className="planetary-console__eyebrow">Fusion replay</span>
                    <strong>
                      {activeMapReplayFrame
                        ? "Stored map frame"
                        : selectedTimelineFrame
                          ? titleCase(selectedTimelineFrame.frame_type)
                          : "Awaiting timeline"}
                    </strong>
                    <p>
                      {timelineReplayActive
                        ? activeMapReplayFrame?.summary || selectedTimelineFrame?.summary || "Replay scope is driving the map."
                        : "Scrub the fusion timeline to replay country stress, corridor arcs, and hotspot markers."}
                    </p>
                  </div>
                  <div className="planetary-console__hero-replay-controls">
                    <button
                      type="button"
                      className={`planetary-console__toggle ${!timelineReplayActive ? "is-active" : ""}`}
                      onClick={() => setTimelineReplayActive(false)}
                    >
                      Live
                    </button>
                    <button
                      type="button"
                      className={`planetary-console__toggle ${timelineReplayActive ? "is-active" : ""}`}
                      onClick={() => setTimelineReplayActive(Boolean(selectedTimelineFrame))}
                      disabled={!selectedTimelineFrame}
                    >
                      Replay
                    </button>
                    <input
                      className="planetary-console__hero-replay-slider"
                      type="range"
                      min={0}
                      max={replaySliderMax}
                      step={1}
                      value={replaySliderValue}
                      disabled={replaySliderMax <= 0}
                      onChange={(event) => {
                        const nextIndex = Number(event.target.value);
                        if (replaySliderUsesStoredFrames) {
                          const nextFrame = replayFrameItems[nextIndex];
                          if (!nextFrame) return;
                          setSelectedMapReplayFrameId(nextFrame.frame_id);
                        } else {
                          const nextFrame = timelineItems[nextIndex];
                          if (!nextFrame) return;
                          setSelectedTimelineFrameId(nextFrame.frame_id);
                        }
                        setTimelineReplayActive(true);
                      }}
                    />
                    <span className="planetary-badge">
                      {activeMapReplayFrame?.countries?.[0]?.country || selectedTimelineFrame?.country || "GLOBAL"} {activeMapReplayFrame ? formatRelativeTime(activeMapReplayFrame.frame_timestamp) : selectedTimelineFrame ? formatRelativeTime(selectedTimelineFrame.frame_timestamp) : ""}
                    </span>
                  </div>
                </div>
                <div className="planetary-console__hero-globe-frame">
                  <WorldGlobe3D
                    data={heroGlobeCountries}
                    eventMarkers={heroGlobeEvents}
                    flowArcs={heroFlowArcs}
                    countryDetails={heroCountryDetails}
                    labeledCountryCodes={heroLabelCountryCodes}
                    showRiskLegend
                    height={720}
                    autoRotate={heroProjectionMode === "cinematic"}
                    showActivityDots={false}
                    projectionType={heroProjectionType}
                    projectionScale={heroProjectionScale}
                    fillCountriesByRisk={heroLayerVisibility.behavior}
                    onCountryHover={(country) => setHeroHoveredCountryCode(country?.countryCode || "")}
                    onCountryClick={(country) => void openCountryInvestigation(country.countryCode || country.country)}
                    onFlowArcClick={(arc) => void openCorridorInvestigation(arc.id)}
                  />
                  <div className="planetary-console__hero-globe-caption">
                    <span>{heroProjectionCaption}</span>
                    <span>Click any country or corridor arc to open evidence in the investigation drawer.</span>
                  </div>
                </div>
                <div className="planetary-console__hero-map-footer">
                  <div className="planetary-console__hero-hotspots">
                    {heroHotspots.map((item) => (
                      <button
                        key={`hotspot:${item.id}`}
                        type="button"
                        className={`planetary-console__hero-hotspot ${toneClassFromRatio(item.probability / 100)}`}
                        onClick={() => {
                          const alertId = typeof (item as { alertId?: unknown }).alertId === "string"
                            ? ((item as { alertId?: string }).alertId || "")
                            : "";
                          const countryCode = typeof (item as { country?: unknown }).country === "string"
                            ? ((item as { country?: string }).country || "")
                            : "";
                          if (alertId) {
                            setHeroFocusedCountryCode(countryCode);
                            void openAlertInvestigation(alertId);
                            return;
                          }
                          if (countryCode) {
                            setHeroFocusedCountryCode(countryCode);
                            void openCountryInvestigation(countryCode);
                          }
                        }}
                      >
                        <strong>{item.name}</strong>
                        <span>{item.detail}</span>
                        <span>{item.category}</span>
                      </button>
                    ))}
                  </div>
                  <div className="planetary-console__hero-theater-strip">
                    {commandTheaters.slice(0, 4).map((item) => (
                      <button
                        key={`hero-theater:${item.country}`}
                        type="button"
                        className={`planetary-console__hero-theater ${toneClassFromRatio(item.overall_pressure)}`}
                        onClick={() => {
                          setHeroFocusedCountryCode(normalizeCountryCode(item.country) || item.country);
                          void openCountryInvestigation(item.country);
                        }}
                      >
                        <div className="planetary-console__hero-theater-topline">
                          <strong>{item.country}</strong>
                          <span>{formatPercent(item.overall_pressure, 0)}</span>
                        </div>
                        <p>{item.recommended_action || "Open country evidence and operator workflow."}</p>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
              <div className="planetary-console__hero-side">
                <div className="planetary-console__hero-copy planetary-console__hero-copy--brief">
                  <span className="planetary-console__eyebrow">Planetary operations spine</span>
                  <h2>One map-first console for global stress, disruption, hazards, and link analysis.</h2>
                  <p>{qualityGateMessage}</p>
                  <div className="planetary-console__hero-brief-list">
                    <article className="planetary-console__hero-brief-item">
                      <span>Primary focus</span>
                      <strong>{focusedFocusLabel}</strong>
                      <p>
                        Risk {formatPercent(focusedPressureScore, 0)} / Confidence {formatPercent(focusedConfidence, 0)} /{" "}
                        {titleCase(focusedCountrySnapshot?.risk_trend_direction || focusedFusionSnapshot?.fusion_band || "watch")}
                      </p>
                    </article>
                    <article className="planetary-console__hero-brief-item">
                      <span>Lead corridor</span>
                      <strong>{heroFlowArcs[0]?.label || "No corridor spike selected"}</strong>
                      <p>
                        {heroFlowArcs[0]
                          ? `Flow intensity ${formatPercent((heroFlowArcs[0]?.intensity || 0) / 100, 0)} across the current top infrastructure path.`
                          : "Waiting for corridor replay or direct corridor telemetry."}
                      </p>
                    </article>
                    <article className="planetary-console__hero-brief-item">
                      <span>Runtime cadence</span>
                      <strong>{formatRelativeTime(runtimeManifest?.captured_at)}</strong>
                      <p>
                        {runtimeStatus?.status || "Unknown"} scheduler / {formatNumber(Number(runtimeManifest?.behavior_replay_count ?? 0), 0)} behavior frames /{" "}
                        {formatNumber(Number(runtimeManifest?.map_replay_frame_count ?? 0), 0)} stored map frames
                      </p>
                    </article>
                  </div>
                  <div className="planetary-console__count-strip">
                    {heroCountBadges.map((item) => (
                      <div key={item.label} className="planetary-console__count-pill">
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                      </div>
                    ))}
                  </div>
                  <div className="planetary-console__dimension-strip">
                    {(summary?.top_contributing_dimensions || []).map((item) => (
                      <span key={item.metric} className={`planetary-badge ${toneClassFromRatio(item.value)}`}>
                        {titleCase(item.metric)} {formatPercent(item.value, 0)}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="planetary-console__hero-side-grid">
                  <div className="planetary-console__hero-card">
                    <span>Focus pressure mix</span>
                    <strong>{formatPercent(focusedBehaviorScore, 0)}</strong>
                    <p>
                      Behavior {formatPercent(focusedBehaviorScore, 0)} / Infrastructure {formatPercent(focusedInfrastructureScore, 0)}
                    </p>
                    <div className="planetary-chip-cloud">
                      {focusedStateVector.length ? focusedStateVector.map(([key, value]) => (
                        <span key={key} className={`planetary-badge ${toneClassFromRatio(Number(value))}`}>
                          {titleCase(key)} {formatPercent(Number(value), 0)}
                        </span>
                      )) : (
                        <span className="planetary-badge">Global mood {formatNumber(behaviorSnapshot?.global_mood_score, 1)}</span>
                      )}
                    </div>
                  </div>
                  <div className="planetary-console__hero-card">
                    <span>Linked activity</span>
                    <strong>{focusedAlerts.length + focusedHazards.length + focusedCorridors.length}</strong>
                    <p>
                      {focusedAlerts.length} alerts / {focusedHazards.length} hazards / {focusedCorridors.length} active corridors
                    </p>
                    <div className="planetary-chip-cloud">
                      <span className="planetary-badge">Lead theater {focusedTheater ? formatPercent(focusedTheater.overall_pressure, 0) : "--"}</span>
                      <span className="planetary-badge">Global mood {formatNumber(behaviorSnapshot?.global_mood_score, 1)}</span>
                    </div>
                  </div>
                  <div className="planetary-console__hero-card">
                    <span>Command posture</span>
                    <strong>{focusedTheater ? formatPercent(focusedTheater.overall_pressure, 0) : formatNumber(commandWatchlist.length, 0)}</strong>
                    <p>{focusedAdvisory}</p>
                    <div className="planetary-chip-cloud">
                      <span className="planetary-badge">{formatNumber(alertOpsSummary?.active_queue_count, 0)} queues</span>
                      <span className="planetary-badge">{formatNumber(runtimeManifest?.command_watchlist_count, 0)} tracked incidents</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section className="planetary-console__metric-grid planetary-console__metric-grid--brief">
              {renderMetricCard(
                "Global stress",
                formatPercent(summary?.global_stress_level, 0),
                `Confidence ${formatPercent(summary?.confidence_ratio, 0)}`,
                toneClassFromRatio(summary?.global_stress_level),
              )}
              {renderMetricCard(
                "Conflict escalation",
                formatPercent(summary?.conflict_escalation_probability, 0),
                "Correlated from behavior, hazard, and infrastructure strain.",
                toneClassFromRatio(summary?.conflict_escalation_probability),
              )}
              {renderMetricCard(
                "Economic panic",
                formatPercent(summary?.economic_panic_indicator, 0),
                "Household, energy, food, and FX pressure combined.",
                toneClassFromRatio(summary?.economic_panic_indicator),
              )}
              {renderMetricCard(
                "Migration pressure",
                formatPercent(summary?.migration_pressure_index, 0),
                "Mobility disruption, logistics strain, and coordination risk.",
                toneClassFromRatio(summary?.migration_pressure_index),
              )}
              {renderMetricCard(
                "Infrastructure fragility",
                formatPercent(summary?.infrastructure_fragility_score, 0),
                "Internet congestion, shutdown pressure, and cyber posture.",
                toneClassFromRatio(summary?.infrastructure_fragility_score),
              )}
            </section>

            <section className="planetary-console__two-column">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Alert board</span>
                    <h3>Highest pressure alerts</h3>
                  </div>
                  <span className="planetary-badge">{alertEvents.length} active slice</span>
                </div>
                <div className="planetary-list">
                  {alertEvents.map((item: PlanetaryAlertEvent) => {
                    const status = alertOpsStatus(item);
                    const queue = alertQueue(item);
                    const owner = alertOwner(item);
                    const snoozedUntil = recordText(item.ops_state, "snoozed_until");
                    const slaDueAt = recordText(item.sla_state, "due_at");
                    const slaBreached = recordBoolean(item.sla_state, "breached");
                    return (
                      <article key={item.alert_id} className={`planetary-list-card planetary-click-card ${toneClassFromRatio(item.severity_score)}`} role="button" tabIndex={0} onClick={() => void openAlertInvestigation(item.alert_id)}>
                        <div className="planetary-list-card__topline">
                          <strong>{titleCase(item.alert_type)}</strong>
                          <span>{geographyLabel(item)}</span>
                        </div>
                        <p>{item.summary}</p>
                        <div className="planetary-list-card__meta">
                          <span>Severity {formatPercent(item.severity_score, 0)}</span>
                          <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                          <span>{formatRelativeTime(item.generated_at)}</span>
                          <span className={`planetary-badge ${runtimeToneClass(status)}`}>{titleCase(status)}</span>
                        </div>
                        <div className="planetary-chip-cloud">
                          <span className="planetary-badge">Queue {queue}</span>
                          <span className="planetary-badge">Owner {owner}</span>
                          {snoozedUntil ? <span className="planetary-badge">Snooze {formatCountdown(snoozedUntil)}</span> : null}
                          {slaDueAt ? (
                            <span className={`planetary-badge ${slaBreached ? "is-critical" : "is-guarded"}`}>
                              SLA {formatCountdown(slaDueAt)}
                            </span>
                          ) : null}
                        </div>
                        <div className="planetary-alert-actions">
                          <button type="button" className="planetary-alert-action" disabled={pendingAlertActionKey === `${item.alert_id}:acknowledge`} onClick={(event) => { event.stopPropagation(); void handleAlertAction(item, "acknowledge"); }}>
                            {pendingAlertActionKey === `${item.alert_id}:acknowledge` ? "Working..." : "Acknowledge"}
                          </button>
                          <button type="button" className="planetary-alert-action" disabled={pendingAlertActionKey === `${item.alert_id}:assign`} onClick={(event) => { event.stopPropagation(); void handleAlertAction(item, "assign"); }}>
                            {pendingAlertActionKey === `${item.alert_id}:assign` ? "Working..." : "Assign to me"}
                          </button>
                          <button type="button" className="planetary-alert-action" disabled={pendingAlertActionKey === `${item.alert_id}:snooze`} onClick={(event) => { event.stopPropagation(); void handleAlertAction(item, "snooze"); }}>
                            {pendingAlertActionKey === `${item.alert_id}:snooze` ? "Working..." : "Snooze 6h"}
                          </button>
                          <button type="button" className="planetary-alert-action is-danger" disabled={pendingAlertActionKey === `${item.alert_id}:false_positive`} onClick={(event) => { event.stopPropagation(); void handleAlertAction(item, "false_positive"); }}>
                            {pendingAlertActionKey === `${item.alert_id}:false_positive` ? "Working..." : "False positive"}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Persistence spine</span>
                    <h3>Shared storage posture</h3>
                  </div>
                  <span className="planetary-badge">{signalStore?.mode || overview?.mode || "runtime-backed"}</span>
                </div>
                <div className="planetary-console__manifest-grid">
                  <div className="planetary-console__manifest-card">
                    <span>Source events</span>
                    <strong>{signalStore?.source_event_count || 0}</strong>
                    <p>{Object.keys(signalStore?.source_families || {}).length} source families</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Normalized signals</span>
                    <strong>{signalStore?.normalized_signal_count || 0}</strong>
                    <p>{Object.keys(signalStore?.signal_types || {}).length} signal types</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>World entities</span>
                    <strong>{graphSnapshot?.world_entity_count || 0}</strong>
                    <p>{Object.keys(graphSnapshot?.entity_types || {}).length} entity classes</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Relationships</span>
                    <strong>{graphSnapshot?.world_relationship_count || 0}</strong>
                    <p>{Object.keys(graphSnapshot?.relationship_types || {}).length} relationship classes</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Fusion frames</span>
                    <strong>{fusionStore?.timeline_frame_count || 0}</strong>
                    <p>{Object.keys(fusionStore?.frame_types || {}).length} frame types</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Correlation chains</span>
                    <strong>{fusionStore?.correlation_chain_count || 0}</strong>
                    <p>{Object.keys(fusionStore?.chain_types || {}).length} chain families</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Active queues</span>
                    <strong>{alertOpsSummary?.active_queue_count || 0}</strong>
                    <p>{queueBreakdown.length} active routing queues</p>
                  </div>
                </div>
              </article>
            </section>

            <section id="planetary-command" className="planetary-console__two-column planetary-console__section-grid planetary-console__section-grid--command">
              <article className="planetary-panel planetary-panel--span-two">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Global command layer</span>
                    <h3>Priority theaters</h3>
                  </div>
                  <span className="planetary-badge">{commandTheaters.length} theaters</span>
                </div>
                <div className="planetary-country-grid">
                  {commandTheaters.map((item) => (
                    <article key={item.country} className={`planetary-country-card ${toneClassFromRatio(item.overall_pressure)}`}>
                      <div className="planetary-country-card__topline">
                        <strong>{item.country}</strong>
                        <span>{formatPercent(item.overall_pressure, 0)}</span>
                      </div>
                      <div className="planetary-country-card__signals">
                        <span>Fusion {formatPercent(item.fusion_risk, 0)}</span>
                        <span>Alerts {item.alerts}</span>
                        <span>Hazards {item.hazards}</span>
                        <span>Chains {item.chains}</span>
                      </div>
                      <p>{item.recommended_action || "Investigate local evidence and operator queue posture."}</p>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Incident watchlist</span>
                    <h3>Command incidents</h3>
                  </div>
                </div>
                <div className="planetary-list">
                  {commandWatchlist.map((item) => (
                    <article key={`${item.kind}:${item.id || item.label}`} className={`planetary-list-card ${toneClassFromRatio(item.severity_score)}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{item.label || item.id}</strong>
                        <span>{item.country || "GLOBAL"}</span>
                      </div>
                      <p>{item.recommended_action || "Inspect evidence and assign an operator."}</p>
                      <div className="planetary-list-card__meta">
                        <span>{titleCase(item.kind)}</span>
                        <span>Severity {formatPercent(item.severity_score, 0)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                      </div>
                    </article>
                  ))}
                </div>
                <div className="planetary-chip-cloud">
                  {Object.entries(commandDeck?.replay_readiness || {}).map(([key, value]) => (
                    <span key={key} className="planetary-badge">
                      {titleCase(key)} {String(value)}
                    </span>
                  ))}
                </div>
              </article>
            </section>

            <section className="planetary-console__two-column planetary-console__section-grid planetary-console__section-grid--briefing">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Command overlays</span>
                    <h3>Theater map overlays</h3>
                  </div>
                  <span className="planetary-badge">{commandTheaters.length} active overlays</span>
                </div>
                <div className="planetary-overlay-shell">
                  <svg viewBox="0 0 320 110" preserveAspectRatio="none" className="planetary-overlay-chart">
                    <path d="M 0 104 L 320 104" className="planetary-overlay-chart__gridline" />
                    <path d="M 0 56 L 320 56" className="planetary-overlay-chart__gridline is-mid" />
                    {commandOverlayPath ? <path d={commandOverlayPath} className="planetary-overlay-chart__line" /> : null}
                  </svg>
                  <div className="planetary-overlay-map">
                    {commandTheaters.slice(0, 6).map((item, index) => (
                      <button
                        key={`overlay:${item.country}`}
                        type="button"
                        className={`planetary-overlay-node ${toneClassFromRatio(item.overall_pressure)}`}
                        style={{ left: `${12 + (index % 3) * 30}%`, top: `${18 + Math.floor(index / 3) * 36}%` }}
                        onClick={() => void openCountryInvestigation(item.country)}
                      >
                        <strong>{item.country}</strong>
                        <span>{formatPercent(item.overall_pressure, 0)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Runtime cadence</span>
                    <h3>Self-refresh posture</h3>
                  </div>
                  <span className={`planetary-badge ${runtimeToneClass(runtimeStatus?.status)}`}>{runtimeStatus?.status || "unknown"}</span>
                </div>
                <div className="planetary-console__manifest-grid planetary-console__manifest-grid--compact">
                  {runtimeMaterializationStats.map((item) => (
                    <div key={item.label} className="planetary-console__manifest-card">
                      <span>{item.label}</span>
                      <strong>{item.value}</strong>
                      <p>{item.detail}</p>
                    </div>
                  ))}
                </div>
                <div className="planetary-chip-cloud">
                  <span className="planetary-badge">Every {formatNumber(runtimeStatus?.interval_seconds, 0)}s</span>
                  <span className="planetary-badge">Source refresh {formatNumber(runtimeStatus?.source_refresh_interval_seconds, 0)}s</span>
                  <span className="planetary-badge">Backtests {formatNumber(runtimeStatus?.backtest_interval_seconds, 0)}s</span>
                  <span className="planetary-badge">Last completed {formatRelativeTime(runtimeStatus?.last_completed_at || runtimeManifest?.captured_at)}</span>
                </div>
              </article>
            </section>

            <section className="planetary-console__three-column">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Knowledge graph</span>
                    <h3>Graph command focus</h3>
                  </div>
                </div>
                <div className="planetary-list">
                  {graphTopEntities.map((item) => (
                    <article key={item.entity_id} className={`planetary-list-card ${toneClassFromRatio(item.current_risk_score ?? item.confidence_ratio)}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{item.canonical_name || item.entity_id}</strong>
                        <span>{titleCase(item.entity_type)}</span>
                      </div>
                      <div className="planetary-list-card__meta">
                        <span>Degree {formatNumber(item.relationship_degree, 0)}</span>
                        <span>Risk {formatNumber(item.current_risk_score, 1)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Disaster command</span>
                    <h3>Forecast theaters</h3>
                  </div>
                </div>
                <div className="planetary-list">
                  {disasterTopRegions.map((item) => (
                    <article key={String(item.forecast_id || `${item.country}:${item.region}`)} className={`planetary-list-card ${toneClassFromRatio((item.severity_score as number | undefined) ?? (item.likelihood as number | undefined))}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(String(item.hazard_type || "hazard"))}</strong>
                        <span>{String(item.country || "GLOBAL")} / {String(item.region || "--")}</span>
                      </div>
                      <div className="planetary-list-card__meta">
                        <span>Likelihood {formatPercent(item.likelihood as number | undefined, 0)}</span>
                        <span>Severity {formatPercent(item.severity_score as number | undefined, 0)}</span>
                        <span>Horizon {formatNumber(item.forecast_horizon as number | undefined, 0)}h</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Validation posture</span>
                    <h3>Replay and calibration</h3>
                  </div>
                </div>
                <div className="planetary-chip-cloud">
                  {Object.entries(commandDeck?.validation_summary || {}).map(([key, value]) => (
                    <span key={key} className="planetary-badge">
                      {titleCase(key)} {typeof value === "object" ? JSON.stringify(value) : String(value)}
                    </span>
                  ))}
                </div>
                <div className="planetary-chip-cloud">
                  {Object.entries(disasterDeck?.hazard_counts || {}).map(([key, value]) => (
                    <span key={key} className="planetary-badge is-guarded">
                      {titleCase(key)} {String(value)}
                    </span>
                  ))}
                </div>
              </article>
            </section>

            <section id="planetary-fusion" className="planetary-console__two-column">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Fusion layer</span>
                    <h3>Country fusion ladder</h3>
                  </div>
                  <span className="planetary-badge">{fusedCountries.length} fused countries</span>
                </div>
                <div className="planetary-fusion-grid">
                  {fusedCountries.length ? fusedCountries.map((item: PlanetaryCountryFusionSnapshot) => (
                    <article key={item.fusion_id} className={`planetary-fusion-card planetary-click-card ${toneClassFromRatio(item.fused_score)}`} role="button" tabIndex={0} onClick={() => void openCountryInvestigation(item.country)}>
                      <div className="planetary-list-card__topline">
                        <strong>{item.country}</strong>
                        <span>{titleCase(item.fusion_band)}</span>
                      </div>
                      <div className="planetary-fusion-card__score">{formatPercent(item.fused_score, 0)}</div>
                      <div className="planetary-bar-track">
                        <div className={`planetary-bar-fill ${toneClassFromRatio(item.fused_score)}`} style={{ width: `${normalizeRatio(item.fused_score) * 100}%` }} />
                      </div>
                      <div className="planetary-list-card__meta">
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>Signals {item.signal_count || 0}</span>
                        <span>Alerts {(item.related_alert_ids || []).length}</span>
                      </div>
                      <div className="planetary-bar-list">
                        {Object.entries(item.state_vector || {}).slice(0, 4).map(([key, value]) => (
                          <div key={`${item.fusion_id}:${key}`} className="planetary-bar-row">
                            <span>{titleCase(key)}</span>
                            <div className="planetary-bar-track is-compact">
                              <div className={`planetary-bar-fill ${toneClassFromRatio(value)}`} style={{ width: `${normalizeRatio(value) * 100}%` }} />
                            </div>
                            <strong>{formatPercent(value, 0)}</strong>
                          </div>
                        ))}
                      </div>
                      <p>{item.recommended_action || "Track reinforcing behavior, hazard, and infrastructure signals."}</p>
                    </article>
                  )) : <div className="planetary-console__empty">Fusion snapshots will appear after the next persisted planetary batch.</div>}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Correlation chains</span>
                    <h3>Cross-system escalation paths</h3>
                  </div>
                  <span className="planetary-badge">{chains.length} active chains</span>
                </div>
                <div className="planetary-chain-list">
                  {chains.length ? chains.map((item) => (
                    <button key={item.chain_id} type="button" className={`planetary-chain-button ${item.chain_id === selectedChain?.chain_id ? "is-selected" : ""} ${toneClassFromRatio(Math.max(safeNumber(item.likelihood), safeNumber(item.confidence_ratio)))}`} onClick={() => { setSelectedChainId(item.chain_id); void openChainInvestigation(item.chain_id); }}>
                      <div className="planetary-list-card__topline">
                        <strong>{item.country || "GLOBAL"}</strong>
                        <span>{titleCase(item.chain_type)}</span>
                      </div>
                      <p>{item.summary}</p>
                      <div className="planetary-list-card__meta">
                        <span>Likelihood {formatPercent(item.likelihood, 0)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>{formatRelativeTime(item.timestamp)}</span>
                      </div>
                    </button>
                  )) : <div className="planetary-console__empty">No correlation chains available yet.</div>}
                </div>
                {selectedChain ? (
                  <article className={`planetary-chain-detail ${toneClassFromRatio(Math.max(safeNumber(selectedChain.likelihood), safeNumber(selectedChain.confidence_ratio)))}`}>
                    <div className="planetary-panel__header">
                      <div>
                        <span className="planetary-panel__eyebrow">Selected chain</span>
                        <h3>{titleCase(selectedChain.chain_type)}</h3>
                      </div>
                      <span className="planetary-badge">{selectedChain.country || "GLOBAL"}</span>
                    </div>
                    <p>{selectedChain.recommended_action || selectedChain.summary}</p>
                    <div className="planetary-bar-list">
                      {selectedChainStages.map((stage) => (
                        <div key={`${selectedChain.chain_id}:${stage.stage}:${stage.metric}`} className="planetary-bar-row">
                          <span>{titleCase(stage.stage)} / {titleCase(stage.metric)}</span>
                          <div className="planetary-bar-track is-compact">
                            <div className={`planetary-bar-fill ${toneClassFromRatio(stage.value)}`} style={{ width: `${normalizeRatio(stage.value) * 100}%` }} />
                          </div>
                          <strong>{formatPercent(stage.value, 0)}</strong>
                        </div>
                      ))}
                    </div>
                    <div className="planetary-chip-cloud">
                      {(selectedChain.entity_refs || []).slice(0, 5).map((item) => (
                        <span key={item} className="planetary-badge">{item}</span>
                      ))}
                      {(selectedChain.alert_refs || []).slice(0, 4).map((item) => (
                        <span key={item} className="planetary-badge is-guarded">{item}</span>
                      ))}
                    </div>
                  </article>
                ) : null}
              </article>
            </section>

            <section id="planetary-behavior" className="planetary-console__three-column">
              <article className="planetary-panel planetary-panel--span-two">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Behavior watch</span>
                    <h3>Country stress deck</h3>
                  </div>
                  <span className="planetary-badge">Top {countrySnapshots.length}</span>
                </div>
                <div className="planetary-country-grid">
                  {countrySnapshots.slice(0, 6).map((item: PlanetaryCountrySnapshot) => (
                    <article key={item.country} className={`planetary-country-card planetary-click-card ${toneClassFromRatio(item.raw_risk_score)}`} role="button" tabIndex={0} onClick={() => void openCountryInvestigation(item.country)}>
                      <div className="planetary-country-card__topline">
                        <strong>{item.country}</strong>
                        <span>{item.risk_band || "unknown"}</span>
                      </div>
                      <div className="planetary-country-card__score">
                        {formatNumber(item.display_risk ?? item.raw_risk_score, 1)}
                      </div>
                      <div className="planetary-country-card__meta">
                        <span>Delta 24h {formatSigned(item.risk_delta_24h, 1)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                      </div>
                      <p>{item.advisory || "Monitor country conditions for fast-moving change."}</p>
                      <div className="planetary-country-card__signals">
                        <span>Behavior {formatPercent(item.signal_scores?.direct_behavior_score, 0)}</span>
                        <span>Context {formatPercent(item.signal_scores?.contextual_pressure_score, 0)}</span>
                        <span>Coordination {formatPercent(item.signal_scores?.coordination_risk_score, 0)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Global behavior</span>
                    <h3>Behavior control card</h3>
                  </div>
                </div>
                <div className="planetary-console__behavior-kpis">
                  <div>
                    <span>Stress</span>
                    <strong>{formatPercent(behaviorSnapshot?.global_stress_level, 0)}</strong>
                  </div>
                  <div>
                    <span>Disruption</span>
                    <strong>{formatPercent(behaviorSnapshot?.global_disruption_index, 0)}</strong>
                  </div>
                  <div>
                    <span>Economic</span>
                    <strong>{formatPercent(behaviorSnapshot?.global_economic_stress_index, 0)}</strong>
                  </div>
                  <div>
                    <span>Migration</span>
                    <strong>{formatPercent(behaviorSnapshot?.migration_pressure_index, 0)}</strong>
                  </div>
                </div>
                <div className="planetary-chip-cloud">
                  {(behaviorSnapshot?.top_stressed_countries || []).slice(0, 6).map((item) => (
                    <span key={item.country} className={`planetary-badge ${toneClassFromRatio(item.display_risk)}`}>
                      {item.country} {formatNumber(item.display_risk, 1)}
                    </span>
                  ))}
                  {Object.entries(behaviorDeck?.source_health?.normalized_signal_families || {}).slice(0, 4).map(([key, value]) => (
                    <span key={key} className="planetary-badge is-guarded">
                      {titleCase(key)} {String(value)}
                    </span>
                  ))}
                </div>
              </article>
            </section>

            <section className="planetary-console__two-column planetary-console__section-grid planetary-console__section-grid--overlays">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Normalized feed</span>
                    <h3>Recent behavior signals</h3>
                  </div>
                  <span className="planetary-badge">{rankedSignals.length} signals</span>
                </div>
                <div className="planetary-list">
                  {rankedSignals.map((item) => (
                    <article key={item.signal_id} className={`planetary-list-card ${toneClassFromRatio(item.severity_score)}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.signal_type)}</strong>
                        <span>{geographyLabel(item)}</span>
                      </div>
                      <p>
                        {titleCase(item.metric_name)} at {formatNumber(item.metric_value, 1)} from {titleCase(item.source_family)}
                      </p>
                      <div className="planetary-list-card__meta">
                        <span>Severity {formatPercent(item.severity_score, 0)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>{formatRelativeTime(item.timestamp)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Evidence feed</span>
                    <h3>Recent source events</h3>
                  </div>
                  <span className="planetary-badge">{evidenceFeed.length} events</span>
                </div>
                <div className="planetary-list">
                  {evidenceFeed.map((item) => (
                    <article key={item.event_id} className={`planetary-list-card ${toneClassFromRatio(item.confidence_ratio)}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.event_type || item.metric_name)}</strong>
                        <span>{geographyLabel(item)}</span>
                      </div>
                      <p>
                        {titleCase(item.metric_name)} from {titleCase(item.source_family)} measured at {formatNumber(item.metric_value, 1)}
                      </p>
                      <div className="planetary-list-card__meta">
                        <span>Freshness {formatNumber(item.freshness_sec, 0)}s</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>{formatRelativeTime(item.ingested_at || item.timestamp)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>
            </section>

            <section id="planetary-network" className="planetary-console__two-column planetary-console__section-grid planetary-console__section-grid--network">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Network corridors</span>
                    <h3>Cross-border infrastructure strain</h3>
                  </div>
                  <span className="planetary-badge">{corridorSnapshots.length} corridors</span>
                </div>
                  <div className="planetary-list">
                    {corridorSnapshots.map((item) => (
                    <article key={item.corridor_id} className={`planetary-list-card planetary-click-card ${toneClassFromRatio(item.severity_score)}`} role="button" tabIndex={0} onClick={() => void openCorridorInvestigation(item.corridor_id)}>
                      <div className="planetary-list-card__topline">
                        <strong>{(item.from_region?.country || "UNK")}{" -> "}{(item.to_region?.country || "UNK")}</strong>
                        <span>{item.corridor_id}</span>
                      </div>
                      <p>
                        Throughput {formatNumber(item.flow_metrics?.throughput_gbps, 1)} Gbps / Latency {formatNumber(item.flow_metrics?.latency_ms, 0)} ms / Packet loss {formatNumber(item.flow_metrics?.packet_loss_pct, 1)}%
                      </p>
                      <div className="planetary-list-card__meta">
                        <span>Anomaly {formatPercent(item.flow_metrics?.anomaly_score, 0)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>{formatRelativeTime(item.generated_at)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Hazard theatre</span>
                    <h3>Forecast hotspots</h3>
                  </div>
                  <span className="planetary-badge">{hazardForecasts.length} forecasts</span>
                </div>
                <div className="planetary-list">
                  {hazardForecasts.map((item) => (
                    <article key={item.forecast_id} className={`planetary-list-card ${toneClassFromRatio(Math.max(safeNumber(item.severity_score), safeNumber(item.likelihood)))}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.hazard_type)}</strong>
                        <span>{item.country} / {item.region}</span>
                      </div>
                      <p>{item.recommended_action || "Inspect supporting forecast signals and prepare regional response."}</p>
                      <div className="planetary-list-card__meta">
                        <span>Likelihood {formatPercent(item.likelihood, 0)}</span>
                        <span>Severity {formatPercent(item.severity_score, 0)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>
            </section>

            <section id="planetary-timeline" className="planetary-console__two-column planetary-console__section-grid planetary-console__section-grid--timeline">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Fusion timeline</span>
                    <h3>Incident trend board</h3>
                  </div>
                  <span className="planetary-badge">{timelineItems.length} timeline frames</span>
                </div>
                <div className="planetary-timeline-list">
                  {timelineItems.length ? timelineItems.map((item) => (
                    <article
                      key={item.frame_id}
                      className={`planetary-timeline-card planetary-click-card ${item.frame_id === selectedTimelineFrameId ? "is-selected" : ""} ${toneClassFromRatio(item.severity_score ?? item.confidence_ratio)}`}
                      role="button"
                      tabIndex={0}
                      onClick={() => {
                        setSelectedTimelineFrameId(item.frame_id);
                        const replayFrame = closestReplayFrame(replayFrameItems, item);
                        if (replayFrame?.frame_id) {
                          setSelectedMapReplayFrameId(replayFrame.frame_id);
                        }
                        setTimelineReplayActive(true);
                      }}
                    >
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.frame_type)}</strong>
                        <span>{item.country || "GLOBAL"}</span>
                      </div>
                      <p>{item.summary}</p>
                      <div className="planetary-bar-track">
                        <div className={`planetary-bar-fill ${toneClassFromRatio(item.severity_score ?? item.confidence_ratio)}`} style={{ width: `${normalizeRatio(item.severity_score ?? item.confidence_ratio) * 100}%` }} />
                      </div>
                      <div className="planetary-list-card__meta">
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>Severity {formatPercent(item.severity_score, 0)}</span>
                        <span>{formatRelativeTime(item.frame_timestamp)}</span>
                      </div>
                      <div className="planetary-chip-cloud">
                        {(item.subsystems || []).slice(0, 4).map((entry) => (
                          <span key={`${item.frame_id}:${entry}`} className="planetary-badge">{titleCase(entry)}</span>
                        ))}
                        {(item.chain_refs || []).slice(0, 2).map((entry) => (
                          <button key={`${item.frame_id}:${entry}`} type="button" className="planetary-link-button" onClick={() => { setSelectedChainId(entry); void openChainInvestigation(entry); }}>
                            Open {entry}
                          </button>
                        ))}
                      </div>
                    </article>
                  )) : <div className="planetary-console__empty">Timeline frames will appear after the next fusion write.</div>}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Replay strip</span>
                    <h3>Recent incident frames</h3>
                  </div>
                  <span className="planetary-badge">{replayFrames.length} replay frames</span>
                </div>
                <div className="planetary-list">
                  {replayFrames.map((item) => (
                    <article key={item.frame_id} className="planetary-list-card is-guarded">
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.frame_type)}</strong>
                        <span>{formatRelativeTime(item.frame_timestamp)}</span>
                      </div>
                      <p>{(item.snapshot_refs || []).slice(0, 4).join(" / ") || "Snapshot references unavailable"}</p>
                      <div className="planetary-list-card__meta">
                        <span>{(item.alert_refs || []).length} alerts</span>
                        <span>{Object.keys(item.source_health_summary || {}).length} source health markers</span>
                      </div>
                      <div className="planetary-chip-cloud">
                        {(item.alert_refs || []).slice(0, 4).map((entry) => (
                          <span key={`${item.frame_id}:${entry}`} className="planetary-badge is-guarded">{entry}</span>
                        ))}
                      </div>
                    </article>
                  ))}
                </div>
              </article>
            </section>

            <section id="planetary-graph" className="planetary-console__two-column planetary-console__section-grid planetary-console__section-grid--graph">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Graph layer</span>
                    <h3>World entities</h3>
                  </div>
                  <label className="planetary-console__search">
                    <span>Search</span>
                    <input
                      type="search"
                      value={entityQuery}
                      onChange={(event) => setEntityQuery(event.target.value)}
                      placeholder="country, event, organization, narrative, or relationship"
                    />
                  </label>
                </div>
                <div className="planetary-chip-cloud">
                  {graphFocusTypes.map((item) => (
                    <span key={item.label} className="planetary-badge">
                      {item.label} {item.value}
                    </span>
                  ))}
                </div>
                <div className="planetary-entity-grid">
                  {filteredEntities.map((item) => (
                    <article key={item.entity_id} className={`planetary-entity-card planetary-click-card ${toneClassFromRatio(item.confidence_ratio)}`} role="button" tabIndex={0} onClick={() => void openEntityInvestigation(item.entity_id, item.entity_type)}>
                      <div className="planetary-entity-card__topline">
                        <strong>{item.canonical_name}</strong>
                        <span>{titleCase(item.entity_type)}</span>
                      </div>
                      <p>{item.entity_id}</p>
                      <div className="planetary-list-card__meta">
                        <span>{geographyLabel(item)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        {typeof item.current_risk_score === "number" ? <span>Risk {formatNumber(item.current_risk_score, 1)}</span> : null}
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Graph layer</span>
                    <h3>Relationship watch</h3>
                  </div>
                  <span className="planetary-badge">{filteredRelationships.length} links</span>
                </div>
                <div className="planetary-graph-neighborhood">
                  <div className="planetary-graph-neighborhood__canvas">
                    {graphNeighborhoodLinks.map((item) => {
                      const source = graphNodeIndex.get(item.source_entity_id);
                      const target = graphNodeIndex.get(item.target_entity_id);
                      if (!source || !target) return null;
                      const left = Math.min(source.left, target.left);
                      const top = Math.min(source.top, target.top);
                      const width = Math.abs(target.left - source.left);
                      const height = Math.abs(target.top - source.top);
                      return (
                        <span
                          key={item.relationship_id}
                          className={`planetary-graph-neighborhood__edge ${toneClassFromRatio(item.strength_score)}`}
                          style={{
                            left: `${left}%`,
                            top: `${top}%`,
                            width: `${Math.max(width, 6)}%`,
                            height: `${Math.max(height, 6)}%`,
                          }}
                        />
                      );
                    })}
                    {graphNeighborhoodNodes.map((item) => (
                      <button
                        key={`node:${item.entity_id}`}
                        type="button"
                        className={`planetary-graph-neighborhood__node ${toneClassFromRatio(item.current_risk_score ?? item.confidence_ratio)}`}
                        style={{ left: `${item.left}%`, top: `${item.top}%` }}
                        onClick={() => void openEntityInvestigation(item.entity_id, item.entity_type)}
                      >
                        <strong>{compactLabel(item.canonical_name, 16)}</strong>
                        <span>{titleCase(item.entity_type)}</span>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="planetary-list">
                  {filteredRelationships.map((item) => (
                    <article key={item.relationship_id} className={`planetary-list-card planetary-click-card ${toneClassFromRatio(item.strength_score)}`} role="button" tabIndex={0} onClick={() => void openEntityInvestigation(item.source_entity_id)}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.relationship_type)}</strong>
                        <span>{formatPercent(item.strength_score, 0)}</span>
                      </div>
                      <p>{item.source_entity_id}{" -> "}{item.target_entity_id}</p>
                      <div className="planetary-list-card__meta">
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        <span>{geographyLabel(item)}</span>
                        <span>{formatRelativeTime(item.timestamp)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>
            </section>

            <section id="planetary-runtime" className="planetary-console__two-column planetary-console__section-grid planetary-console__section-grid--runtime">
              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Runtime mesh</span>
                    <h3>Platform runtimes</h3>
                  </div>
                  <span className="planetary-badge">{runtimeStatuses.length} workers</span>
                </div>
                <div className="planetary-chip-cloud">
                  <span className={`planetary-badge ${runtimeToneClass(runtimeStatus?.status)}`}>Scheduler {runtimeStatus?.status || "unknown"}</span>
                  <span className="planetary-badge">Cycles {formatNumber(runtimeStatus?.cycle_count, 0)}</span>
                  <span className="planetary-badge">Run {compactLabel(runtimeStatus?.last_run_id || runtimeManifest?.run_id, 20)}</span>
                  <span className="planetary-badge">Manifest {formatRelativeTime(runtimeManifest?.captured_at)}</span>
                </div>
                <div className="planetary-list">
                  {runtimeStatuses.map((item: PlanetaryRuntimeStatus) => (
                    <article key={item.runtime_name} className={`planetary-list-card ${runtimeToneClass(item.status)}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.runtime_name)}</strong>
                        <span>{item.status}</span>
                      </div>
                      <p>Queue depth {formatNumber(item.queue_depth, 0)} / Cycle latency {formatNumber(item.cycle_latency_ms, 0)} ms / Cache hit {formatPercent(item.cache_hit_ratio, 0)}</p>
                      <div className="planetary-list-card__meta">
                        <span>Freshness {formatNumber(item.freshness_sec, 0)}s</span>
                        <span>Last success {formatRelativeTime(item.last_success_at || item.generated_at)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </article>

              <article className="planetary-panel">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Operator workflow</span>
                    <h3>Alert queue posture</h3>
                  </div>
                  <span className="planetary-badge">{alertOpsSummary?.active_queue_count || 0} active queues</span>
                </div>
                <div className="planetary-console__manifest-grid planetary-console__manifest-grid--compact">
                  <div className="planetary-console__manifest-card">
                    <span>Hazard alignment</span>
                    <strong>{formatPercent(recordNumber(calibrationBacktests, "hazard_chain_alignment_rate"), 0)}</strong>
                    <p>{recordNumber(calibrationDisaster, "high_likelihood_count", 0)} high-likelihood hazard windows</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Behavior alignment</span>
                    <strong>{formatPercent(recordNumber(calibrationBacktests, "behavior_signal_alignment_rate"), 0)}</strong>
                    <p>{formatPercent(recordNumber(calibrationBehavior, "alignment_rate"), 0)} replay-backed signal alignment</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Fusion corroboration</span>
                    <strong>{formatPercent(recordNumber(calibrationBacktests, "fusion_alert_corroboration_rate"), 0)}</strong>
                    <p>{recordText(calibrationFusion, "recommendation") || "Fusion calibration recommendation pending."}</p>
                  </div>
                </div>
                <div className="planetary-console__ops-grid">
                  <div className="planetary-console__manifest-card">
                    <span>Acknowledged</span>
                    <strong>{alertOpsSummary?.acknowledged || 0}</strong>
                    <p>Alerts with a live acknowledgement state.</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Assigned</span>
                    <strong>{alertOpsSummary?.assigned || 0}</strong>
                    <p>Alerts routed to an operator or queue owner.</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Snoozed</span>
                    <strong>{alertOpsSummary?.snoozed_active || 0}</strong>
                    <p>Alerts intentionally suppressed for re-check.</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>False positives</span>
                    <strong>{alertOpsSummary?.false_positive_flags || 0}</strong>
                    <p>Operator feedback registered against noisy alerts.</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>SLA breaches</span>
                    <strong>{alertOpsSummary?.breached_sla_count || 0}</strong>
                    <p>Queues that need attention now.</p>
                  </div>
                  <div className="planetary-console__manifest-card">
                    <span>Suppressed</span>
                    <strong>{alertOpsSummary?.suppressed_by_snooze || 0}</strong>
                    <p>Alerts currently hidden by active snoozes.</p>
                  </div>
                </div>
                <div className="planetary-list">
                  {queueBreakdown.length ? queueBreakdown.map((item) => (
                    <article key={item.queue} className="planetary-list-card is-guarded">
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.queue)}</strong>
                        <span>{item.count} alerts</span>
                      </div>
                      <p>Queue load for this planetary routing lane.</p>
                    </article>
                  )) : (
                    <article className="planetary-list-card is-stable">
                      <div className="planetary-list-card__topline">
                        <strong>Queue routing calm</strong>
                        <span>0 active lanes</span>
                      </div>
                      <p>Operator queues will appear here as alerts are acknowledged, assigned, or snoozed.</p>
                    </article>
                  )}
                </div>
              </article>
            </section>
          </>
        ) : null}
      </main>
      {drawerOpen ? (
        <aside className="planetary-console__drawer">
          <div className="planetary-console__drawer-header">
            <div>
              <span className="planetary-panel__eyebrow">Investigation drawer</span>
              <h3>{drawerData?.title || drawerLabel}</h3>
              <p>
                {drawerData?.kind === "country"
                  ? `Country-level fusion evidence for ${drawerData.payload.country}`
                  : drawerData?.kind === "chain"
                    ? drawerData.payload.correlation_chain?.summary || "Cross-system chain evidence"
                    : drawerData?.kind === "alert"
                      ? drawerData.payload.alert?.summary || "Alert evidence and operator workflow"
                      : drawerData?.kind === "corridor"
                        ? `${drawerData.payload.corridor_snapshot?.from_region?.country || "UNK"} -> ${drawerData.payload.corridor_snapshot?.to_region?.country || "UNK"} corridor evidence`
                      : drawerData?.kind === "entity"
                        ? `${titleCase(drawerData.payload.entity?.entity_type)} profile${drawerData.payload.matched_alias ? ` via ${drawerData.payload.matched_alias}` : ""}`
                        : "Loading the latest supporting evidence and operator workflow history."}
              </p>
            </div>
            <button type="button" className="planetary-console__drawer-close" onClick={() => { setDrawerData(null); setDrawerError(null); setDrawerLoading(false); }}>
              Close
            </button>
          </div>
          {drawerLoading ? (
            <div className="planetary-console__drawer-loading">
              <div className="planetary-console__loading-orb" />
              <span>Loading the latest planetary evidence slice...</span>
            </div>
          ) : null}
          {drawerError ? (
            <section className="planetary-console__error">
              <strong>Investigation unavailable.</strong>
              <span>{drawerError}</span>
            </section>
          ) : null}
          {drawerData ? (
            <div className="planetary-console__drawer-body">
              <div className="planetary-console__drawer-grid">
                <div className="planetary-console__manifest-card">
                  <span>Confidence</span>
                  <strong>{formatPercent(drawerSummary?.confidence_ratio, 0)}</strong>
                  <p>{drawerData.payload.contract_version}</p>
                </div>
                <div className="planetary-console__manifest-card">
                  <span>Freshness</span>
                  <strong>{formatNumber(drawerSummary?.freshness_sec, 0)}s</strong>
                  <p>{formatRelativeTime(drawerData.payload.generated_at)}</p>
                </div>
                <div className="planetary-console__manifest-card">
                  <span>Signals</span>
                  <strong>{drawerSummary?.signal_count || drawerSignals.length}</strong>
                  <p>{drawerSummary?.source_event_count || drawerSourceEvents.length} source events</p>
                </div>
                <div className="planetary-console__manifest-card">
                  <span>Graph context</span>
                  <strong>{drawerSummary?.entity_count || drawerEntities.length}</strong>
                  <p>{drawerSummary?.relationship_count || drawerRelationships.length} linked relationships</p>
                </div>
              </div>

              {drawerPrimaryAlert ? (
                <section className="planetary-panel planetary-console__drawer-section">
                  <div className="planetary-panel__header">
                    <div>
                      <span className="planetary-panel__eyebrow">Operator controls</span>
                      <h3>{titleCase(drawerPrimaryAlert.alert_type)}</h3>
                    </div>
                    <span className={`planetary-badge ${toneClassFromRatio(drawerPrimaryAlert.severity_score)}`}>{drawerPrimaryAlert.alert_id}</span>
                  </div>
                  <p>{drawerPrimaryAlert.summary}</p>
                  <div className="planetary-alert-actions">
                    <button type="button" className="planetary-alert-action" disabled={pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:acknowledge`} onClick={() => void handleAlertAction(drawerPrimaryAlert, "acknowledge")}>
                      {pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:acknowledge` ? "Working..." : "Acknowledge"}
                    </button>
                    <button type="button" className="planetary-alert-action" disabled={pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:assign`} onClick={() => void handleAlertAction(drawerPrimaryAlert, "assign")}>
                      {pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:assign` ? "Working..." : "Assign to me"}
                    </button>
                    <button type="button" className="planetary-alert-action" disabled={pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:snooze`} onClick={() => void handleAlertAction(drawerPrimaryAlert, "snooze")}>
                      {pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:snooze` ? "Working..." : "Snooze 6h"}
                    </button>
                    <button type="button" className="planetary-alert-action is-danger" disabled={pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:false_positive`} onClick={() => void handleAlertAction(drawerPrimaryAlert, "false_positive")}>
                      {pendingAlertActionKey === `${drawerPrimaryAlert.alert_id}:false_positive` ? "Working..." : "False positive"}
                    </button>
                  </div>
                </section>
              ) : null}

              {drawerSubsystemScores.length || drawerStateVector.length ? (
                <section className="planetary-panel planetary-console__drawer-section">
                  <div className="planetary-panel__header">
                    <div>
                      <span className="planetary-panel__eyebrow">Subsystem breakdown</span>
                      <h3>Evidence scoring</h3>
                    </div>
                    <span className="planetary-badge">{drawerSubsystemScores.length + drawerStateVector.length} lanes</span>
                  </div>
                  <div className="planetary-bar-list">
                    {drawerSubsystemScores.map(([key, value]) => (
                      <div key={key} className="planetary-bar-row">
                        <span>{titleCase(key)}</span>
                        <div className="planetary-bar-track is-compact">
                          <div className={`planetary-bar-fill ${toneClassFromRatio(value)}`} style={{ width: `${normalizeRatio(value) * 100}%` }} />
                        </div>
                        <strong>{formatPercent(value, 0)}</strong>
                      </div>
                    ))}
                    {drawerStateVector.map(([key, value]) => (
                      <div key={`state:${key}`} className="planetary-bar-row">
                        <span>{titleCase(key)}</span>
                        <div className="planetary-bar-track is-compact">
                          <div className={`planetary-bar-fill ${toneClassFromRatio(value)}`} style={{ width: `${normalizeRatio(value) * 100}%` }} />
                        </div>
                        <strong>{formatPercent(value, 0)}</strong>
                      </div>
                    ))}
                  </div>
                </section>
              ) : null}

              {drawerProvenance.length ? (
                <section className="planetary-panel planetary-console__drawer-section">
                  <div className="planetary-panel__header">
                    <div>
                      <span className="planetary-panel__eyebrow">Provenance</span>
                      <h3>Supporting references</h3>
                    </div>
                    <span className="planetary-badge">{drawerProvenance.length} refs</span>
                  </div>
                  <div className="planetary-chip-cloud">
                    {drawerProvenance.map((item, index) => (
                      <span key={`prov:${index}`} className="planetary-badge">
                        {recordText(item, "source_name") || recordText(item, "source_family") || recordText(item, "subsystem") || recordText(item, "scope") || `ref ${index + 1}`}
                      </span>
                    ))}
                  </div>
                </section>
              ) : null}

              {drawerChains.length ? (
                <section className="planetary-panel planetary-console__drawer-section">
                  <div className="planetary-panel__header">
                    <div>
                      <span className="planetary-panel__eyebrow">Correlation paths</span>
                      <h3>Linked escalation chains</h3>
                    </div>
                    <span className="planetary-badge">{drawerChains.length} chains</span>
                  </div>
                  <div className="planetary-list">
                    {drawerChains.map((item) => (
                      <article key={item.chain_id} className={`planetary-list-card planetary-click-card ${toneClassFromRatio(Math.max(safeNumber(item.likelihood), safeNumber(item.confidence_ratio)))}`} role="button" tabIndex={0} onClick={() => void openChainInvestigation(item.chain_id)}>
                        <div className="planetary-list-card__topline">
                          <strong>{titleCase(item.chain_type)}</strong>
                          <span>{item.country || "GLOBAL"}</span>
                        </div>
                        <p>{item.summary}</p>
                        <div className="planetary-list-card__meta">
                          <span>Likelihood {formatPercent(item.likelihood, 0)}</span>
                          <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <section className="planetary-panel planetary-console__drawer-section">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Evidence feed</span>
                    <h3>Signals and source events</h3>
                  </div>
                  <span className="planetary-badge">{drawerSignals.length + drawerSourceEvents.length} records</span>
                </div>
                <div className="planetary-list">
                  {drawerSignals.map((item) => (
                    <article key={item.signal_id} className={`planetary-list-card ${toneClassFromRatio(item.severity_score)}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.signal_type)}</strong>
                        <span>{geographyLabel(item)}</span>
                      </div>
                      <p>{titleCase(item.metric_name)} from {titleCase(item.source_family)} at {formatNumber(item.metric_value, 1)}</p>
                      <div className="planetary-list-card__meta">
                        <span>Severity {formatPercent(item.severity_score, 0)}</span>
                        <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                      </div>
                    </article>
                  ))}
                  {drawerSourceEvents.map((item) => (
                    <article key={item.event_id} className={`planetary-list-card ${toneClassFromRatio(item.confidence_ratio)}`}>
                      <div className="planetary-list-card__topline">
                        <strong>{titleCase(item.event_type || item.metric_name)}</strong>
                        <span>{geographyLabel(item)}</span>
                      </div>
                      <p>{titleCase(item.metric_name)} from {titleCase(item.source_family)}</p>
                      <div className="planetary-list-card__meta">
                        <span>Freshness {formatNumber(item.freshness_sec, 0)}s</span>
                        <span>{formatRelativeTime(item.ingested_at || item.timestamp)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>

              {drawerEntities.length || drawerRelationships.length ? (
                <section className="planetary-panel planetary-console__drawer-section">
                  <div className="planetary-panel__header">
                    <div>
                      <span className="planetary-panel__eyebrow">Graph neighborhood</span>
                      <h3>Entities and relationships</h3>
                    </div>
                    <span className="planetary-badge">{drawerEntities.length}/{drawerRelationships.length}</span>
                  </div>
                  <div className="planetary-list">
                    {drawerEntities.map((item) => (
                      <article key={item.entity_id} className={`planetary-list-card planetary-click-card ${toneClassFromRatio(item.confidence_ratio)}`} role="button" tabIndex={0} onClick={() => void openEntityInvestigation(item.entity_id, item.entity_type)}>
                        <div className="planetary-list-card__topline">
                          <strong>{item.canonical_name}</strong>
                          <span>{titleCase(item.entity_type)}</span>
                        </div>
                        <p>{item.entity_id}</p>
                        <div className="planetary-list-card__meta">
                          <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                          <span>{geographyLabel(item)}</span>
                        </div>
                      </article>
                    ))}
                    {drawerRelationships.map((item) => (
                      <article key={item.relationship_id} className={`planetary-list-card ${toneClassFromRatio(item.strength_score)}`}>
                        <div className="planetary-list-card__topline">
                          <strong>{titleCase(item.relationship_type)}</strong>
                          <span>{formatPercent(item.strength_score, 0)}</span>
                        </div>
                        <p>{item.source_entity_id}{" -> "}{item.target_entity_id}</p>
                        <div className="planetary-list-card__meta">
                          <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                          <span>{formatRelativeTime(item.timestamp)}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              {drawerHazards.length || drawerCorridors.length || drawerTimeline.length ? (
                <section className="planetary-panel planetary-console__drawer-section">
                  <div className="planetary-panel__header">
                    <div>
                      <span className="planetary-panel__eyebrow">Operational context</span>
                      <h3>Hazards, corridors, and timeline</h3>
                    </div>
                    <span className="planetary-badge">{drawerHazards.length + drawerCorridors.length + drawerTimeline.length} records</span>
                  </div>
                  <div className="planetary-list">
                    {drawerHazards.map((item) => (
                      <article key={item.forecast_id} className={`planetary-list-card ${toneClassFromRatio(Math.max(safeNumber(item.severity_score), safeNumber(item.likelihood)))}`}>
                        <div className="planetary-list-card__topline">
                          <strong>{titleCase(item.hazard_type)}</strong>
                          <span>{item.country}</span>
                        </div>
                        <p>{item.recommended_action}</p>
                        <div className="planetary-list-card__meta">
                          <span>Likelihood {formatPercent(item.likelihood, 0)}</span>
                          <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                        </div>
                      </article>
                    ))}
                    {drawerCorridors.map((item) => (
                      <article key={item.corridor_id} className={`planetary-list-card planetary-click-card ${toneClassFromRatio(item.severity_score)}`} role="button" tabIndex={0} onClick={() => void openCorridorInvestigation(item.corridor_id)}>
                        <div className="planetary-list-card__topline">
                          <strong>{(item.from_region?.country || "UNK")}{" -> "}{(item.to_region?.country || "UNK")}</strong>
                          <span>{item.corridor_id}</span>
                        </div>
                        <p>Latency {formatNumber(item.flow_metrics?.latency_ms, 0)} ms / Packet loss {formatNumber(item.flow_metrics?.packet_loss_pct, 1)}%</p>
                        <div className="planetary-list-card__meta">
                          <span>Anomaly {formatPercent(item.flow_metrics?.anomaly_score, 0)}</span>
                          <span>{formatRelativeTime(item.generated_at)}</span>
                        </div>
                      </article>
                    ))}
                    {drawerTimeline.map((item) => (
                      <article key={item.frame_id} className={`planetary-list-card ${toneClassFromRatio(item.severity_score ?? item.confidence_ratio)}`}>
                        <div className="planetary-list-card__topline">
                          <strong>{titleCase(item.frame_type)}</strong>
                          <span>{item.country || "GLOBAL"}</span>
                        </div>
                        <p>{item.summary}</p>
                        <div className="planetary-list-card__meta">
                          <span>Confidence {formatPercent(item.confidence_ratio, 0)}</span>
                          <span>{formatRelativeTime(item.frame_timestamp)}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <section className="planetary-panel planetary-console__drawer-section">
                <div className="planetary-panel__header">
                  <div>
                    <span className="planetary-panel__eyebrow">Operator history</span>
                    <h3>Recent workflow actions</h3>
                  </div>
                  <span className="planetary-badge">{drawerHistory.length} actions</span>
                </div>
                <div className="planetary-list">
                  {drawerHistory.length ? drawerHistory.map((item, index) => (
                    <article key={`${item.timestamp}:${index}`} className="planetary-list-card is-guarded">
                      <div className="planetary-list-card__topline">
                        <strong>{operatorEventSummary(item) || "Operator action"}</strong>
                        <span>{formatRelativeTime(item.timestamp)}</span>
                      </div>
                      <p>{item.comment || item.status || item.alert_id || item.dedupe_key || "No comment provided."}</p>
                      <div className="planetary-list-card__meta">
                        <span>{item.country || item.chain_id || "global"}</span>
                        {item.snoozed_until ? <span>Snooze {formatCountdown(item.snoozed_until)}</span> : null}
                        {item.sla_due_at ? <span>SLA {formatCountdown(item.sla_due_at)}</span> : null}
                      </div>
                    </article>
                  )) : (
                    <div className="planetary-console__empty">Operator actions will appear here after alerts are acknowledged, assigned, snoozed, or marked false positive.</div>
                  )}
                </div>
              </section>
            </div>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}









