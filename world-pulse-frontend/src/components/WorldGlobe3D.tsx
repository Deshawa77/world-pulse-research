import { useEffect, useMemo, useRef, useState } from "react";

interface CountryRisk {
  country: string;
  countryCode: string;
  risk: number;
  lat: number;
  lng: number;
}

interface WorldGlobe3DProps {
  data: CountryRisk[];
  onCountryClick?: (country: CountryRisk) => void;
  autoRotate?: boolean;
  height?: number;
}

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

function getRiskColor(score: number): string {
  if (score >= 75) return "#ef4444";
  if (score >= 50) return "#fb923c";
  if (score >= 25) return "#facc15";
  return "#22c55e";
}

export default function WorldGlobe3D({
  data,
  onCountryClick,
  autoRotate = true,
  height = 500,
}: WorldGlobe3DProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const rotationRafRef = useRef<number | null>(null);
  const rotationLonRef = useRef(0);
  const [hoveredCountry, setHoveredCountry] = useState<CountryRisk | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  const plotted = useMemo(() => {
    return data.map((item) => {
      const safeRisk = clamp(Number(item.risk) || 0, 0, 100);
      const iso3 = (item.countryCode || item.country || "").toUpperCase().trim();

      return {
        ...item,
        risk: safeRisk,
        countryCode: iso3,
      };
    }).filter((item) => item.countryCode.length === 3);
  }, [data]);

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

        const locations = plotted.map((p) => p.countryCode);
        const sizes = plotted.map((p) => 3 + (p.risk / 100) * 8);
        const colors = plotted.map((p) => getRiskColor(p.risk));
        const texts = plotted.map((p) => `${p.country} | Risk ${p.risk.toFixed(1)}`);

        const trace = {
          type: "scattergeo",
          mode: "markers",
          locationmode: "ISO-3",
          locations,
          text: texts,
          customdata: plotted,
          hovertemplate: "%{text}<extra></extra>",
          marker: {
            size: sizes,
            sizemode: "diameter",
            color: colors,
            opacity: 0.85,
            line: { color: "rgba(0,0,0,0.35)", width: 1 },
          },
        };

        await Plotly.react(
          containerRef.current,
          [trace] as any,
          {
            margin: { l: 0, r: 0, b: 0, t: 0 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            geo: {
              projection: { type: "orthographic", rotation: { lon: rotationLonRef.current, lat: 0, roll: 0 } },
              showland: true,
              landcolor: "#1f3559",
              showocean: true,
              oceancolor: "#091321",
              showcountries: true,
              countrycolor: "rgba(149, 197, 255, 0.35)",
              showcoastlines: true,
              coastlinecolor: "rgba(134, 195, 255, 0.5)",
              bgcolor: "rgba(0,0,0,0)",
              showframe: false,
            },
          } as any,
          { displayModeBar: false, responsive: true }
        );

        setRenderError(null);
        const plotEl = containerRef.current as any;
        plotEl.removeAllListeners?.("plotly_hover");
        plotEl.removeAllListeners?.("plotly_unhover");
        plotEl.removeAllListeners?.("plotly_click");

        plotEl.on?.("plotly_hover", (evt: any) => {
          const point = evt?.points?.[0];
          if (!point?.customdata) return;
          setHoveredCountry(point.customdata as CountryRisk);
        });

        plotEl.on?.("plotly_unhover", () => {
          setHoveredCountry(null);
        });

        plotEl.on?.("plotly_click", (evt: any) => {
          const point = evt?.points?.[0];
          if (!point?.customdata || !onCountryClick) return;
          onCountryClick(point.customdata as CountryRisk);
        });
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
  }, [plotted, onCountryClick]);

  useEffect(() => {
    const step = async () => {
      if (!autoRotate || !plotlyRef.current || !containerRef.current) {
        rotationRafRef.current = requestAnimationFrame(step);
        return;
      }

      rotationLonRef.current = rotationLonRef.current + 0.25;
      try {
        await plotlyRef.current.relayout(containerRef.current, {
          "geo.projection.rotation.lon": rotationLonRef.current,
        });
      } catch {
        // Ignore transient relayout failures.
      }
      rotationRafRef.current = requestAnimationFrame(step);
    };

    rotationRafRef.current = requestAnimationFrame(step);

    return () => {
      if (rotationRafRef.current) {
        cancelAnimationFrame(rotationRafRef.current);
        rotationRafRef.current = null;
      }
      if (plotlyRef.current && containerRef.current) {
        try {
          plotlyRef.current.purge(containerRef.current);
        } catch {
          // no-op
        }
      }
    };
  }, [autoRotate]);

  return (
    <div style={{ position: "relative", width: "100%", height }}>
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

      {!renderError && plotted.length === 0 ? (
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

      {hoveredCountry ? (
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
