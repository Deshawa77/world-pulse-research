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

interface WorldGlobe3DProps {
  data: CountryRisk[];
  onCountryClick?: (country: CountryRisk) => void;
  autoRotate?: boolean;
  rotationSpeed?: number;
  height?: CSSProperties["height"];
  showActivityDots?: boolean;
  eventMarkers?: GlobeEventMarker[];
  visualPreset?: "default" | "introCinematic";
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

function buildMissilePath(fromLat: number, fromLng: number, toLat: number, toLng: number, steps = 42) {
  const pathLat: number[] = [];
  const pathLon: number[] = [];
  for (let i = 0; i < steps; i++) {
    const t = i / (steps - 1);
    const arcHeight = Math.sin(Math.PI * t) * 8;
    pathLat.push(fromLat + (toLat - fromLat) * t + arcHeight);
    pathLon.push(fromLng + (toLng - fromLng) * t);
  }
  return { pathLat, pathLon };
}

export default function WorldGlobe3D({
  data,
  onCountryClick,
  autoRotate = true,
  rotationSpeed = 0.25,
  height = 500,
  showActivityDots = true,
  eventMarkers = [],
  visualPreset = "default",
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
              size: plotted.map((p) => 3 + (p.risk / 100) * 8),
              sizemode: "diameter",
              color: plotted.map((p) => getRiskColor(p.risk)),
              opacity: 0.85,
              line: { color: "rgba(0,0,0,0.35)", width: 1 },
            },
            showlegend: false,
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

        await Plotly.react(
          containerRef.current,
          traces as any,
          {
            margin: { l: 0, r: 0, b: 0, t: 0 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            geo: {
              projection: { type: "orthographic", rotation: { lon: rotationLonRef.current, lat: 0, roll: 0 } },
              showland: true,
              landcolor: visualPreset === "introCinematic" ? "#080f1f" : "#1f3559",
              showocean: true,
              oceancolor: visualPreset === "introCinematic" ? "#020714" : "#091321",
              showcountries: true,
              countrycolor: visualPreset === "introCinematic" ? "rgba(125, 182, 245, 0.22)" : "rgba(149, 197, 255, 0.35)",
              showcoastlines: true,
              coastlinecolor: visualPreset === "introCinematic" ? "rgba(109, 186, 255, 0.68)" : "rgba(134, 195, 255, 0.5)",
              coastlinewidth: visualPreset === "introCinematic" ? 1.1 : 1,
              bgcolor: "rgba(0,0,0,0)",
              showframe: false,
            },
          } as any,
          { displayModeBar: false, responsive: true, scrollZoom: false, staticPlot: false }
        );

        setRenderError(null);
        const plotEl = containerRef.current as any;
        plotEl.removeAllListeners?.("plotly_hover");
        plotEl.removeAllListeners?.("plotly_unhover");
        plotEl.removeAllListeners?.("plotly_click");

        if (showActivityDots) {
          plotEl.on?.("plotly_hover", (evt: any) => {
            const point = evt?.points?.[0];
            if (!point?.customdata || !point?.customdata?.countryCode) return;
            setHoveredCountry(point.customdata as CountryRisk);
          });

          plotEl.on?.("plotly_unhover", () => {
            setHoveredCountry(null);
          });

          plotEl.on?.("plotly_click", (evt: any) => {
            const point = evt?.points?.[0];
            if (!point?.customdata || !onCountryClick || !point?.customdata?.countryCode) return;
            onCountryClick(point.customdata as CountryRisk);
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
  }, [plotted, normalizedEvents, onCountryClick, showActivityDots, visualPreset]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (!plotlyRef.current || !containerRef.current) return;

      if (autoRotate) {
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
  }, [autoRotate, rotationSpeed]);

  return (
    <div style={{ position: "relative", width: "100%", height }}>
      {visualPreset === "introCinematic" ? (
        <div
          style={{
            position: "absolute",
            inset: "10% 10% 14% 10%",
            borderRadius: "50%",
            pointerEvents: "none",
            background:
              "radial-gradient(circle at 22% 38%, rgba(93, 193, 255, 0.6), rgba(45, 114, 213, 0.22) 34%, rgba(5, 12, 28, 0) 62%)",
            filter: "blur(12px)",
            mixBlendMode: "screen",
          }}
        />
      ) : null}
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

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

      {!renderError && plotted.length === 0 && showActivityDots && !normalizedEvents.length ? (
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

      {showActivityDots && hoveredCountry ? (
        <div
          style={{
            position: "absolute",
            top: 10,
            left: 10,
            background: "rgba(0, 0, 0, 0.8)",
            border: `1px solid ${getRiskColor(hoveredCountry.risk)}`,
            borderRadius: 8,
            padding: 10,
            color: "#fff",
            fontSize: 12,
            zIndex: 10,
            backdropFilter: "blur(8px)",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 4 }}>{hoveredCountry.country}</div>
          <div>Risk: {hoveredCountry.risk.toFixed(1)}</div>
        </div>
      ) : null}
    </div>
  );
}
