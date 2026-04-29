import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";

interface CountryRisk {
  country: string;
  countryCode: string;
  risk: number;
  lat: number;
  lng: number;
}

type EventKind = "generic" | "wave" | "volcano" | "earthquake" | "war" | "missile";

export interface GlobeEventMarker {
  id: string;
  name: string;
  category: string;
  lat: number;
  lng: number;
  probability: number;
  icon?: string;
  color?: string;
  kind?: EventKind;
}

export interface GlobeFlowArc {
  id: string;
  fromCountry?: string;
  toCountry?: string;
  fromLat: number;
  fromLng: number;
  toLat: number;
  toLng: number;
  intensity?: number;
  label?: string;
  category?: string;
  color?: string;
}

export interface GlobeCountryDetail {
  label?: string;
  riskBand?: string;
  confidence?: number;
  alerts?: number;
  hazards?: number;
  corridors?: number;
  trend?: string;
  advisory?: string;
  pressure?: number;
}

interface WorldGlobe3DProps {
  data: CountryRisk[];
  onCountryClick?: (country: CountryRisk) => void;
  onCountryHover?: (country: CountryRisk | null) => void;
  onFlowArcClick?: (arc: GlobeFlowArc) => void;
  autoRotate?: boolean;
  rotationSpeed?: number;
  height?: CSSProperties["height"];
  showActivityDots?: boolean;
  eventMarkers?: GlobeEventMarker[];
  flowArcs?: GlobeFlowArc[];
  countryDetails?: Record<string, GlobeCountryDetail>;
  labeledCountryCodes?: string[];
  showRiskLegend?: boolean;
  visualPreset?: "default" | "introCinematic";
  projectionType?: "orthographic" | "natural earth" | "equirectangular";
  projectionScale?: number;
  fillCountriesByRisk?: boolean;
}

type PulseTrace = {
  traceIndex: number;
  baseSizes: number[];
  amplitude: number;
  speed: number;
  phaseOffset: number;
};

type MissileAnim = {
  traceIndex: number;
  pathLat: number[];
  pathLon: number[];
  phase: number;
  speed: number;
};

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

function getRiskColor(score: number): string {
  if (score >= 75) return "#ef4444";
  if (score >= 50) return "#fb923c";
  if (score >= 25) return "#facc15";
  return "#22c55e";
}

function detectKind(event: GlobeEventMarker): EventKind {
  if (event.kind) return event.kind;
  const text = `${event.name} ${event.category}`.toLowerCase();
  if (text.includes("volcan")) return "volcano";
  if (text.includes("earthquake")) return "earthquake";
  if (text.includes("tsunami") || text.includes("flood") || text.includes("hurricane") || text.includes("cyclone") || text.includes("typhoon") || text.includes("ocean")) return "wave";
  if (text.includes("missile")) return "missile";
  if (text.includes("war") || text.includes("terror") || text.includes("coup") || text.includes("riot") || text.includes("protest") || text.includes("conflict")) return "war";
  return "generic";
}

function getEventColor(kind: EventKind, probability: number): string {
  if (kind === "volcano") return "#ff7a45";
  if (kind === "earthquake") return "#ffd166";
  if (kind === "wave") return "#4cc9f0";
  if (kind === "war") return "#ff4d6d";
  if (kind === "missile") return "#f94144";
  if (probability >= 85) return "#ff6b6b";
  if (probability >= 70) return "#ff9f43";
  if (probability >= 55) return "#feca57";
  return "#1dd1a1";
}

function markerSymbolForKind(kind: EventKind): string {
  if (kind === "volcano") return "triangle-up";
  if (kind === "earthquake") return "x";
  if (kind === "wave") return "circle-open";
  if (kind === "war") return "cross";
  if (kind === "missile") return "triangle-right";
  return "circle";
}

function buildArcPath(fromLat: number, fromLng: number, toLat: number, toLng: number, steps = 42, arcLift = 8) {
  const pathLat: number[] = [];
  const pathLon: number[] = [];
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    const arcHeight = Math.sin(Math.PI * t) * arcLift;
    pathLat.push(fromLat + (toLat - fromLat) * t + arcHeight);
    pathLon.push(fromLng + (toLng - fromLng) * t);
  }
  return { pathLat, pathLon };
}

function buildMissilePath(fromLat: number, fromLng: number, toLat: number, toLng: number, steps = 42) {
  return buildArcPath(fromLat, fromLng, toLat, toLng, steps, 8);
}

function getArcColor(intensity: number): string {
  if (intensity >= 80) return "rgba(255, 126, 95, 0.88)";
  if (intensity >= 60) return "rgba(255, 193, 85, 0.82)";
  if (intensity >= 40) return "rgba(74, 227, 255, 0.72)";
  return "rgba(114, 241, 210, 0.58)";
}

function textPositionForCountry(country: CountryRisk, index: number): string {
  const positions = ["top left", "top right", "bottom left", "bottom right", "top center", "bottom center"];
  const eastBias = country.lng > 60 ? 1 : country.lng < -60 ? 0 : index % positions.length;
  return positions[eastBias];
}

function formatMaybePercent(value: number | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "--";
  return `${Math.round(value)}%`;
}

export default function WorldGlobe3D({
  data,
  onCountryClick,
  onCountryHover,
  onFlowArcClick,
  autoRotate = true,
  rotationSpeed = 0.25,
  height = 500,
  showActivityDots = true,
  eventMarkers = [],
  flowArcs = [],
  countryDetails,
  labeledCountryCodes = [],
  showRiskLegend = false,
  visualPreset = "default",
  projectionType = "orthographic",
  projectionScale,
  fillCountriesByRisk = false,
}: WorldGlobe3DProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const rotationLonRef = useRef(0);
  const pulseStepRef = useRef(0);
  const pulseTracesRef = useRef<PulseTrace[]>([]);
  const missileAnimRef = useRef<MissileAnim[]>([]);

  const [hoveredCountry, setHoveredCountry] = useState<CountryRisk | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const plotted = useMemo(() => {
    return data
      .map((item) => ({
        ...item,
        risk: clamp(Number(item.risk) || 0, 0, 100),
        countryCode: (item.countryCode || item.country || "").toUpperCase().trim(),
      }))
      .filter((item) => item.countryCode.length === 3);
  }, [data]);

  const normalizedEvents = useMemo(() => {
    return eventMarkers.map((event) => {
      const probability = clamp(Number(event.probability) || 0, 0, 100);
      const kind = detectKind(event);
      return {
        ...event,
        probability,
        kind,
        color: event.color || getEventColor(kind, probability),
      };
    });
  }, [eventMarkers]);

  const normalizedFlowArcs = useMemo(() => {
    return flowArcs
      .map((item) => ({
        ...item,
        intensity: clamp(Number(item.intensity) || 0, 0, 100),
      }))
      .filter((item) => (
        Number.isFinite(item.fromLat)
        && Number.isFinite(item.fromLng)
        && Number.isFinite(item.toLat)
        && Number.isFinite(item.toLng)
      ));
  }, [flowArcs]);

  const labelCountries = useMemo(() => {
    if (!labeledCountryCodes.length) return [];
    const wanted = new Set(labeledCountryCodes.map((item) => item.toUpperCase()));
    return plotted.filter((item) => wanted.has(item.countryCode)).slice(0, 8);
  }, [labeledCountryCodes, plotted]);

  const interactiveCountries = showActivityDots || fillCountriesByRisk;
  const interactiveArcs = normalizedFlowArcs.length > 0 && typeof onFlowArcClick === "function";
  const computedProjectionScale = projectionScale ?? (projectionType === "equirectangular" ? 1.12 : projectionType === "natural earth" ? 1.28 : 1);

  useEffect(() => {
    onCountryHover?.(hoveredCountry);
  }, [hoveredCountry, onCountryHover]);

  useEffect(() => {
    let stopped = false;

    const loadPlotly = async () => {
      if (plotlyRef.current) return plotlyRef.current;
      if (!plotlyLoadingRef.current) {
        plotlyLoadingRef.current = import("plotly.js-dist-min").then((mod) => {
          plotlyRef.current = (mod as any).default ?? mod;
          return plotlyRef.current;
        });
      }
      return plotlyLoadingRef.current;
    };

    const draw = async () => {
      if (!containerRef.current) return;
      try {
        const Plotly = await loadPlotly();
        if (stopped || !containerRef.current) return;

        const traces: any[] = [];
        pulseTracesRef.current = [];
        missileAnimRef.current = [];

        const isIntroPreset = visualPreset === "introCinematic";

        if (isIntroPreset) {
          // Keep the intro globe clean: only the globe itself, coastlines, and atmosphere.
        }

        if (fillCountriesByRisk && plotted.length) {
          traces.push({
            type: "choropleth",
            locationmode: "ISO-3",
            locations: plotted.map((p) => p.countryCode),
            z: plotted.map((p) => p.risk),
            zmin: 0,
            zmax: 100,
            text: plotted.map((p) => `${p.countryCode} | Risk ${p.risk.toFixed(1)}`),
            customdata: plotted,
            hovertemplate: "%{customdata.countryCode}<br/>Risk %{z:.1f}<extra></extra>",
            colorscale: [
              [0, "#0f3d33"],
              [0.25, "#22c55e"],
              [0.5, "#facc15"],
              [0.75, "#fb923c"],
              [1, "#ef4444"],
            ],
            showscale: false,
            marker: {
              line: {
                color: visualPreset === "introCinematic" ? "rgba(125, 182, 245, 0.28)" : "rgba(158, 211, 255, 0.48)",
                width: visualPreset === "introCinematic" ? 0.45 : 0.7,
              },
            },
          });
        }

        if (showActivityDots) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            locationmode: "ISO-3",
            locations: plotted.map((p) => p.countryCode),
            text: plotted.map((p) => `${p.country} | Risk ${p.risk.toFixed(1)}`),
            customdata: plotted,
            hovertemplate: "%{text}<extra></extra>",
            marker: {
              size: plotted.map((p) => (fillCountriesByRisk ? 2 + (p.risk / 100) * 4 : 3 + (p.risk / 100) * 8)),
              sizemode: "diameter",
              color: plotted.map((p) => getRiskColor(p.risk)),
              opacity: fillCountriesByRisk ? 0.62 : 0.85,
              line: { color: "rgba(0,0,0,0.35)", width: 1 },
            },
            showlegend: false,
          });
        }

        if (normalizedFlowArcs.length) {
          normalizedFlowArcs.slice(0, 12).forEach((arc, index) => {
            const lift = 2.8 + (arc.intensity / 100) * 3.8;
            const width = 1 + (arc.intensity / 100) * 3.2;
            const { pathLat, pathLon } = buildArcPath(arc.fromLat, arc.fromLng, arc.toLat, arc.toLng, 34, lift);
            const arcCustomData = pathLat.map(() => arc);
            traces.push({
              type: "scattergeo",
              mode: "lines",
              lat: pathLat,
              lon: pathLon,
              customdata: arcCustomData,
              text: arc.label || `${arc.fromCountry || "?"} -> ${arc.toCountry || "?"}`,
              hovertemplate: "%{text}<br/>Flow intensity: " + arc.intensity.toFixed(0) + "%<extra></extra>",
              line: {
                color: arc.color || getArcColor(arc.intensity),
                width,
              },
              opacity: projectionType === "orthographic" ? 0.72 : 0.84,
              showlegend: false,
            });

            const midpointIndex = Math.floor(pathLat.length / 2);
            traces.push({
              type: "scattergeo",
              mode: "markers",
              lat: [pathLat[midpointIndex]],
              lon: [pathLon[midpointIndex]],
              customdata: [arc],
              text: [arc.label || `${arc.fromCountry || "?"} -> ${arc.toCountry || "?"}`],
              hovertemplate: "%{text}<br/>Flow intensity: " + arc.intensity.toFixed(0) + "%<extra></extra>",
              marker: {
                size: 3 + (arc.intensity / 100) * 5,
                color: arc.color || getArcColor(arc.intensity),
                opacity: 0.78,
                line: { color: "rgba(255,255,255,0.22)", width: 0.6 },
              },
              showlegend: false,
            });

            if (index < 6 && projectionType !== "orthographic") {
              traces.push({
                type: "scattergeo",
                mode: "text",
                lat: [pathLat[midpointIndex] + (index % 2 === 0 ? 1.4 : -1.4)],
                lon: [pathLon[midpointIndex]],
                customdata: [arc],
                text: [arc.fromCountry && arc.toCountry ? `${arc.fromCountry}-${arc.toCountry}` : arc.label || "Flow"],
                textfont: {
                  size: 10,
                  color: "rgba(216, 237, 245, 0.76)",
                },
                hoverinfo: "skip",
                showlegend: false,
              });
            }
          });
        }

        if (normalizedEvents.length) {
          const coreSizes = normalizedEvents.map((e) => 6 + (e.probability / 100) * 6);
          const coreTraceIndex = traces.length;
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lat: normalizedEvents.map((e) => e.lat),
            lon: normalizedEvents.map((e) => e.lng),
            customdata: normalizedEvents.map((e) => [e.name, e.category, e.probability]),
            hovertemplate: "%{customdata[0]}<br/>%{customdata[1]}<br/>Probability: %{customdata[2]}%<extra></extra>",
            marker: {
              size: coreSizes,
              color: normalizedEvents.map((e) => e.color),
              symbol: normalizedEvents.map((e) => markerSymbolForKind(e.kind)),
              opacity: 0.9,
              line: { color: "rgba(6, 14, 30, 0.8)", width: 1 },
            },
            showlegend: false,
          });
          pulseTracesRef.current.push({ traceIndex: coreTraceIndex, baseSizes: coreSizes, amplitude: 1.2, speed: 0.08, phaseOffset: 0 });

          const waveEvents = normalizedEvents.filter((e) => e.kind === "wave");
          if (waveEvents.length) {
            const waveSizes = waveEvents.map(() => 16);
            const waveTraceIndex = traces.length;
            traces.push({
              type: "scattergeo",
              mode: "markers",
              lat: waveEvents.map((e) => e.lat),
              lon: waveEvents.map((e) => e.lng),
              hoverinfo: "skip",
              marker: {
                size: waveSizes,
                color: "rgba(0,0,0,0)",
                symbol: "circle-open",
                line: { color: "rgba(76, 201, 240, 0.85)", width: 1.6 },
              },
              showlegend: false,
            });
            pulseTracesRef.current.push({ traceIndex: waveTraceIndex, baseSizes: waveSizes, amplitude: 4.8, speed: 0.06, phaseOffset: 1.1 });
          }

          const volcanoEvents = normalizedEvents.filter((e) => e.kind === "volcano");
          if (volcanoEvents.length) {
            const plumeLat: number[] = [];
            const plumeLon: number[] = [];
            volcanoEvents.forEach((e) => {
              plumeLat.push(e.lat + 1.2, e.lat + 2.6);
              plumeLon.push(e.lng, e.lng + 0.8);
            });
            const plumeSizes = plumeLat.map(() => 8);
            const plumeTraceIndex = traces.length;
            traces.push({
              type: "scattergeo",
              mode: "markers",
              lat: plumeLat,
              lon: plumeLon,
              hoverinfo: "skip",
              marker: {
                size: plumeSizes,
                color: "rgba(255, 146, 43, 0.9)",
                symbol: "triangle-up",
                line: { color: "rgba(120, 40, 10, 0.8)", width: 0.8 },
              },
              showlegend: false,
            });
            pulseTracesRef.current.push({ traceIndex: plumeTraceIndex, baseSizes: plumeSizes, amplitude: 2.6, speed: 0.12, phaseOffset: 0.7 });
          }

          const quakeEvents = normalizedEvents.filter((e) => e.kind === "earthquake");
          if (quakeEvents.length) {
            const quakeSizes = quakeEvents.map(() => 18);
            const quakeTraceIndex = traces.length;
            traces.push({
              type: "scattergeo",
              mode: "markers",
              lat: quakeEvents.map((e) => e.lat),
              lon: quakeEvents.map((e) => e.lng),
              hoverinfo: "skip",
              marker: {
                size: quakeSizes,
                color: "rgba(0,0,0,0)",
                symbol: "circle-open",
                line: { color: "rgba(255, 209, 102, 0.85)", width: 1.8 },
              },
              showlegend: false,
            });
            pulseTracesRef.current.push({ traceIndex: quakeTraceIndex, baseSizes: quakeSizes, amplitude: 5.5, speed: 0.11, phaseOffset: 2.3 });
          }

          const warEvents = normalizedEvents.filter((e) => e.kind === "war");
          if (warEvents.length) {
            const lineLat: number[] = [];
            const lineLon: number[] = [];
            warEvents.forEach((e) => {
              lineLat.push(e.lat - 1.1, e.lat + 1.1, null as any);
              lineLon.push(e.lng - 1.1, e.lng + 1.1, null as any);
              lineLat.push(e.lat - 1.1, e.lat + 1.1, null as any);
              lineLon.push(e.lng + 1.1, e.lng - 1.1, null as any);
            });
            traces.push({
              type: "scattergeo",
              mode: "lines",
              lat: lineLat,
              lon: lineLon,
              hoverinfo: "skip",
              line: { color: "rgba(255, 77, 109, 0.6)", width: 1.2 },
              showlegend: false,
            });
          }

          const missileEvents = normalizedEvents.filter((e) => e.kind === "missile" || e.kind === "war").slice(0, 6);
          missileEvents.forEach((event, index) => {
            const targetLat = clamp(event.lat + (index % 2 === 0 ? 9 : -7), -60, 75);
            const targetLng = event.lng + (index % 2 === 0 ? 18 : -16);
            const { pathLat, pathLon } = buildMissilePath(event.lat, event.lng, targetLat, targetLng);

            traces.push({
              type: "scattergeo",
              mode: "lines",
              lat: pathLat,
              lon: pathLon,
              hoverinfo: "skip",
              line: { color: "rgba(249, 65, 68, 0.42)", width: 1.5 },
              showlegend: false,
            });

            const headTraceIndex = traces.length;
            traces.push({
              type: "scattergeo",
              mode: "markers",
              lat: [pathLat[0]],
              lon: [pathLon[0]],
              hoverinfo: "skip",
              marker: {
                size: 7,
                color: "#ff9f1c",
                symbol: "diamond",
                line: { color: "rgba(255,255,255,0.6)", width: 0.6 },
              },
              showlegend: false,
            });

            missileAnimRef.current.push({
              traceIndex: headTraceIndex,
              pathLat,
              pathLon,
              phase: index * 4,
              speed: 0.35 + (index % 3) * 0.06,
            });
          });
        }

        if (!traces.length) {
          traces.push({
            type: "scattergeo",
            mode: "markers",
            lat: [0],
            lon: [0],
            hoverinfo: "skip",
            marker: { size: 0, opacity: 0 },
            showlegend: false,
          });
        }

        if (labelCountries.length && projectionType !== "orthographic") {
          traces.push({
            type: "scattergeo",
            mode: "text",
            lat: labelCountries.map((item) => item.lat),
            lon: labelCountries.map((item) => item.lng),
            text: labelCountries.map((item) => item.countryCode),
            textposition: labelCountries.map((item, index) => textPositionForCountry(item, index)),
            textfont: {
              size: 10,
              color: "rgba(231, 244, 248, 0.86)",
            },
            hoverinfo: "skip",
            showlegend: false,
          });
        }

        await Plotly.react(
          containerRef.current,
          traces as any,
          {
            margin: { l: 0, r: 0, b: 0, t: 0 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            geo: {
              projection: projectionType === "orthographic"
                ? { type: projectionType, rotation: { lon: rotationLonRef.current, lat: 0, roll: 0 } }
                : { type: projectionType, scale: computedProjectionScale },
              showland: true,
              landcolor: fillCountriesByRisk ? "#16324d" : visualPreset === "introCinematic" ? "#080f1f" : "#1f3559",
              showocean: true,
              oceancolor: visualPreset === "introCinematic" ? "#020714" : "#091321",
              showcountries: true,
              countrycolor: visualPreset === "introCinematic" ? "rgba(125, 182, 245, 0.22)" : "rgba(149, 197, 255, 0.35)",
              showcoastlines: true,
              coastlinecolor: visualPreset === "introCinematic" ? "rgba(109, 186, 255, 0.68)" : "rgba(134, 195, 255, 0.5)",
              coastlinewidth: visualPreset === "introCinematic" ? 1.1 : 1,
              bgcolor: "rgba(0,0,0,0)",
              showframe: false,
              lataxis: projectionType === "orthographic" ? undefined : { range: [-58, 84] },
              lonaxis: projectionType === "orthographic" ? undefined : { range: [-180, 180] },
            },
          } as any,
          { displayModeBar: false, responsive: true, scrollZoom: false, staticPlot: false }
        );

        setRenderError(null);
        const plotEl = containerRef.current as any;
        plotEl.removeAllListeners?.("plotly_hover");
        plotEl.removeAllListeners?.("plotly_unhover");
        plotEl.removeAllListeners?.("plotly_click");

        if (interactiveCountries || interactiveArcs) {
          if (interactiveCountries) {
            plotEl.on?.("plotly_hover", (evt: any) => {
              const point = evt?.points?.[0];
              if (!point?.customdata || !point?.customdata?.countryCode) return;
              setHoveredCountry(point.customdata as CountryRisk);
            });
          }
          plotEl.on?.("plotly_unhover", () => {
            setHoveredCountry(null);
          });
          plotEl.on?.("plotly_click", (evt: any) => {
            const point = evt?.points?.[0];
            const customdata = point?.customdata;
            if (customdata?.countryCode && onCountryClick) {
              onCountryClick(customdata as CountryRisk);
              return;
            }
            if (customdata?.id && customdata?.fromLat !== undefined && customdata?.toLat !== undefined && onFlowArcClick) {
              onFlowArcClick(customdata as GlobeFlowArc);
            }
          });
        } else {
          setHoveredCountry(null);
        }
      } catch (err) {
        const message = err instanceof Error ? err.message : "Failed to render globe";
        setRenderError(message);
      }
    };

    draw();

    return () => {
      stopped = true;
      if (containerRef.current) {
        const plotEl = containerRef.current as any;
        plotEl.removeAllListeners?.("plotly_hover");
        plotEl.removeAllListeners?.("plotly_unhover");
        plotEl.removeAllListeners?.("plotly_click");
      }
    };
  }, [plotted, normalizedEvents, normalizedFlowArcs, labelCountries, onCountryClick, onFlowArcClick, showActivityDots, visualPreset, projectionType, computedProjectionScale, fillCountriesByRisk, interactiveCountries, interactiveArcs]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!plotlyRef.current || !containerRef.current) return;

      if (autoRotate && projectionType === "orthographic") {
        rotationLonRef.current += rotationSpeed;
        try {
          void plotlyRef.current.relayout(containerRef.current, {
            "geo.projection.rotation.lon": rotationLonRef.current,
          });
        } catch {
          // Ignore transient relayout failures.
        }
      }

      pulseStepRef.current += 0.08;

      for (const pulseTrace of pulseTracesRef.current) {
        const sizes = pulseTrace.baseSizes.map((base, idx) => {
          const phase = Math.sin(pulseStepRef.current * pulseTrace.speed * 10 + idx * 0.65 + pulseTrace.phaseOffset);
          return base + phase * pulseTrace.amplitude;
        });

        try {
          void plotlyRef.current.restyle(
            containerRef.current,
            { "marker.size": [sizes] },
            [pulseTrace.traceIndex]
          );
        } catch {
          // Ignore transient restyle failures.
        }
      }

      for (const missile of missileAnimRef.current) {
        missile.phase += missile.speed;
        const pathLen = missile.pathLat.length;
        const idx = Math.floor(missile.phase) % pathLen;

        try {
          void plotlyRef.current.restyle(
            containerRef.current,
            {
              lat: [[missile.pathLat[idx]]],
              lon: [[missile.pathLon[idx]]],
            },
            [missile.traceIndex]
          );
        } catch {
          // Ignore transient restyle failures.
        }
      }
    }, 80);

    return () => {
      window.clearInterval(timer);
      if (plotlyRef.current && containerRef.current) {
        try {
          plotlyRef.current.purge(containerRef.current);
        } catch {
          // no-op
        }
      }
    };
  }, [autoRotate, rotationSpeed, projectionType]);

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      {visualPreset === "introCinematic" || projectionType !== "orthographic" ? (
        <div
          style={{
            position: "absolute",
            inset: projectionType === "orthographic" ? "10% 10% 14% 10%" : "8% 4% 10% 4%",
            borderRadius: projectionType === "orthographic" ? "50%" : "1.2rem",
            pointerEvents: "none",
            background:
              projectionType === "orthographic"
                ? "radial-gradient(circle at 22% 38%, rgba(93, 193, 255, 0.6), rgba(45, 114, 213, 0.22) 34%, rgba(5, 12, 28, 0) 62%)"
                : "radial-gradient(circle at 12% 18%, rgba(76, 201, 240, 0.26), rgba(76, 201, 240, 0) 28%), radial-gradient(circle at 82% 16%, rgba(255, 159, 67, 0.14), rgba(255, 159, 67, 0) 22%), linear-gradient(180deg, rgba(255,255,255,0.02), rgba(0,0,0,0.08))",
            filter: "blur(12px)",
            mixBlendMode: "screen",
          }}
        />
      ) : null}
      {projectionType !== "orthographic" ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            background: "linear-gradient(180deg, rgba(4, 18, 31, 0.12), rgba(4, 18, 31, 0) 14%, rgba(4, 18, 31, 0) 74%, rgba(4, 18, 31, 0.18) 100%)",
          }}
        />
      ) : null}
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {showRiskLegend ? (
        <div
          style={{
            position: "absolute",
            left: 12,
            bottom: 12,
            display: "grid",
            gap: 8,
            padding: "10px 12px",
            borderRadius: 12,
            border: "1px solid rgba(116, 157, 178, 0.18)",
            background: "rgba(6, 17, 26, 0.84)",
            color: "rgba(228, 241, 246, 0.88)",
            fontSize: 11,
            backdropFilter: "blur(10px)",
            zIndex: 9,
          }}
        >
          <div style={{ textTransform: "uppercase", letterSpacing: "0.12em", color: "rgba(171, 215, 224, 0.72)" }}>
            Country risk legend
          </div>
          <div
            style={{
              width: 168,
              height: 8,
              borderRadius: 999,
              background: "linear-gradient(90deg, #22c55e 0%, #facc15 45%, #fb923c 72%, #ef4444 100%)",
              boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.08)",
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8, color: "rgba(206, 225, 231, 0.74)" }}>
            <span>Stable</span>
            <span>Guarded</span>
            <span>Elevated</span>
            <span>Critical</span>
          </div>
        </div>
      ) : null}

      {renderError ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#ff8888",
            fontSize: "12px",
            background: "rgba(10, 10, 15, 0.65)",
            textAlign: "center",
            padding: "12px",
          }}
        >
          3D globe render failed: {renderError}
        </div>
      ) : null}

      {!renderError && plotted.length === 0 && !normalizedEvents.length ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#9fb3d9",
            fontSize: "12px",
            textAlign: "center",
            pointerEvents: "none",
          }}
        >
          Waiting for risk-map data...
        </div>
      ) : null}

      {interactiveCountries && hoveredCountry ? (
        <div
          style={{
            position: "absolute",
            top: 10,
            left: 10,
            minWidth: 220,
            background: "rgba(0, 0, 0, 0.82)",
            border: `1px solid ${getRiskColor(hoveredCountry.risk)}`,
            borderRadius: 12,
            padding: 12,
            color: "#fff",
            fontSize: 12,
            zIndex: 10,
            backdropFilter: "blur(8px)",
            boxShadow: "0 18px 40px rgba(0, 0, 0, 0.28)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10, alignItems: "baseline" }}>
            <div style={{ fontWeight: 700, marginBottom: 2 }}>{countryDetails?.[hoveredCountry.countryCode]?.label || hoveredCountry.countryCode}</div>
            <div style={{ color: getRiskColor(hoveredCountry.risk), fontWeight: 700 }}>{Math.round(hoveredCountry.risk)}%</div>
          </div>
          <div style={{ color: "rgba(214, 231, 238, 0.78)", marginBottom: 8 }}>
            {countryDetails?.[hoveredCountry.countryCode]?.riskBand || "Country risk"} / {countryDetails?.[hoveredCountry.countryCode]?.trend || "monitoring"}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 6 }}>
            <div>Confidence {formatMaybePercent(countryDetails?.[hoveredCountry.countryCode]?.confidence)}</div>
            <div>Pressure {formatMaybePercent(countryDetails?.[hoveredCountry.countryCode]?.pressure)}</div>
            <div>Alerts {countryDetails?.[hoveredCountry.countryCode]?.alerts ?? 0}</div>
            <div>Hazards {countryDetails?.[hoveredCountry.countryCode]?.hazards ?? 0}</div>
            <div>Corridors {countryDetails?.[hoveredCountry.countryCode]?.corridors ?? 0}</div>
            <div>Risk {hoveredCountry.risk.toFixed(1)}</div>
          </div>
          {countryDetails?.[hoveredCountry.countryCode]?.advisory ? (
            <div style={{ marginTop: 8, color: "rgba(225, 239, 244, 0.84)", lineHeight: 1.4 }}>
              {countryDetails[hoveredCountry.countryCode]?.advisory}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
