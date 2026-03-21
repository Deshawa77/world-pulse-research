import { useState, useEffect, useMemo, useRef } from "react";
import * as echarts from "echarts";

interface CountryData {
  country: string;
  countryCode: string;
  risk: number;
  features: Record<string, number>;
  timestamp: string;
}

interface CountryComparisonProps {
  countries: CountryData[];
  height?: number;
}

const toNumberOr = (value: unknown, fallback = 0): number => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
};

type MetricDefinition = {
  key: string;
  label: string;
  format: (value: number) => string;
  signed: boolean;
};

const METRICS: MetricDefinition[] = [
  { key: "news_sentiment", label: "News Sentiment", format: (v: number) => v.toFixed(2), signed: true },
  { key: "gdelt_sentiment", label: "GDELT Sentiment", format: (v: number) => v.toFixed(2), signed: true },
  { key: "crypto_return", label: "Crypto Return", format: (v: number) => `${(v * 100).toFixed(1)}%`, signed: true },
  { key: "crypto_volatility", label: "Crypto Volatility", format: (v: number) => v.toFixed(2), signed: false },
  { key: "stock_return", label: "Stock Return", format: (v: number) => `${(v * 100).toFixed(1)}%`, signed: true },
  { key: "stock_volatility", label: "Stock Volatility", format: (v: number) => v.toFixed(2), signed: false },
  { key: "weather_anomaly", label: "Weather Anomaly", format: (v: number) => v.toFixed(2), signed: false },
];

function toNiceUpperBound(value: number, floor: number = 1): number {
  const safe = Math.max(Math.abs(value), floor);
  const exponent = Math.floor(Math.log10(safe));
  const magnitude = 10 ** exponent;
  const normalized = safe / magnitude;

  if (normalized <= 1) return magnitude;
  if (normalized <= 2) return 2 * magnitude;
  if (normalized <= 5) return 5 * magnitude;
  return 10 * magnitude;
}

function getMetricValue(country: CountryData | undefined, metricKey: string): number {
  return toNumberOr(country?.features?.[metricKey], 0);
}

function buildRadarIndicator(
  metric: MetricDefinition,
  country1Data?: CountryData,
  country2Data?: CountryData,
): { name: string; min: number; max: number } {
  const valueA = getMetricValue(country1Data, metric.key);
  const valueB = getMetricValue(country2Data, metric.key);

  if (metric.signed) {
    const maxAbs = Math.max(Math.abs(valueA), Math.abs(valueB));
    const bound = toNiceUpperBound(maxAbs * 1.25, 1);
    return { name: metric.label, min: -bound, max: bound };
  }

  const maxValue = Math.max(valueA, valueB);
  const upper = toNiceUpperBound(maxValue * 1.25, 1);
  return { name: metric.label, min: 0, max: upper };
}

export default function CountryComparison({ countries, height = 500 }: CountryComparisonProps) {
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [chartType, setChartType] = useState<"radar" | "bar">("radar");

  const availableCountries = useMemo(() => {
    const unique = new Map<string, CountryData>();
    countries.forEach((c) => {
      if (!unique.has(c.countryCode) || new Date(c.timestamp) > new Date(unique.get(c.countryCode)!.timestamp)) {
        unique.set(c.countryCode, c);
      }
    });
    return Array.from(unique.values());
  }, [countries]);

  useEffect(() => {
    if (availableCountries.length >= 2 && selectedCountries.length === 0) {
      setSelectedCountries([availableCountries[0].countryCode, availableCountries[1].countryCode]);
    }
  }, [availableCountries, selectedCountries.length]);

  const getCountryData = (code: string): CountryData | undefined => {
    return countries.filter((c) => c.countryCode === code).sort((a, b) => 
      new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )[0];
  };

  const country1Data = getCountryData(selectedCountries[0]);
  const country2Data = getCountryData(selectedCountries[1]);

  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current || !country1Data || !country2Data) return;

    if (!chartInstanceRef.current) {
      chartInstanceRef.current = echarts.init(chartRef.current);
    }

    const chart = chartInstanceRef.current;

    if (chartType === "radar") {
      const option: echarts.EChartsOption = {
        backgroundColor: "#13233f",
        textStyle: { color: "#d6e4ff" },
        tooltip: {
          backgroundColor: "rgba(12, 31, 56, 0.96)",
          borderColor: "rgba(96, 165, 250, 0.45)",
          borderWidth: 1,
          textStyle: { color: "#eaf3ff" },
        },
        legend: {
          data: [country1Data?.country || "Country 1", country2Data?.country || "Country 2"],
          textStyle: { color: "#d6e4ff" },
          bottom: 0,
          itemWidth: 14,
          itemHeight: 10,
        },
        radar: {
          indicator: METRICS.map((m) => buildRadarIndicator(m, country1Data, country2Data)),
          shape: "polygon",
          splitNumber: 4,
          axisLine: {
            lineStyle: { color: "rgba(148,163,184,0.3)" },
          },
          axisName: {
            color: "#c4d7ff",
            fontSize: 11,
          },
          splitLine: {
            lineStyle: { color: "rgba(148,163,184,0.24)" },
          },
          splitArea: {
            show: true,
            areaStyle: {
              color: ["rgba(19,30,49,0.55)", "rgba(19,30,49,0.28)"],
            },
          },
        },
        series: [
          {
            name: "Country Comparison",
            type: "radar",
            data: [
              {
                value: METRICS.map((m) => getMetricValue(country1Data, m.key)),
                name: country1Data?.country || "Country 1",
                lineStyle: { color: "#38bdf8", width: 3 },
                areaStyle: { color: "rgba(56,189,248,0.24)" },
                itemStyle: { color: "#00d4ff", borderColor: "#0b1730", borderWidth: 1 },
              },
              {
                value: METRICS.map((m) => getMetricValue(country2Data, m.key)),
                name: country2Data?.country || "Country 2",
                lineStyle: { color: "#f59e0b", width: 3 },
                areaStyle: { color: "rgba(245,158,11,0.18)" },
                itemStyle: { color: "#fbbf24", borderColor: "#0b1730", borderWidth: 1 },
              },
            ],
          },
        ],
      };
      chart.setOption(option);
    } else {
      const option: echarts.EChartsOption = {
        backgroundColor: "#13233f",
        textStyle: { color: "#d6e4ff" },
        tooltip: {
          trigger: "axis",
          backgroundColor: "rgba(12, 31, 56, 0.96)",
          borderColor: "rgba(96, 165, 250, 0.45)",
          borderWidth: 1,
          textStyle: { color: "#eaf3ff" },
        },
        legend: {
          data: [country1Data?.country || "Country 1", country2Data?.country || "Country 2"],
          textStyle: { color: "#d6e4ff" },
          bottom: 0,
          itemWidth: 14,
          itemHeight: 10,
        },
        grid: {
          left: "3%",
          right: "4%",
          bottom: "15%",
          top: "10%",
          containLabel: true,
        },
        xAxis: {
          type: "category",
          data: METRICS.map((m) => m.label),
          axisLabel: { color: "#d6e4ff", fontSize: 11, rotate: 28 },
          axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.45)" } },
        },
        yAxis: {
          type: "value",
          axisLabel: { color: "#d6e4ff", fontSize: 11 },
          axisLine: { lineStyle: { color: "rgba(148, 163, 184, 0.45)" } },
          splitLine: { lineStyle: { color: "rgba(148,163,184,0.24)" } },
        },
        series: [
          {
            name: country1Data?.country || "Country 1",
            type: "bar",
            data: METRICS.map((m) => getMetricValue(country1Data, m.key)),
            itemStyle: { color: "#38bdf8", borderRadius: [6, 6, 0, 0] },
            barMaxWidth: 32,
          },
          {
            name: country2Data?.country || "Country 2",
            type: "bar",
            data: METRICS.map((m) => getMetricValue(country2Data, m.key)),
            itemStyle: { color: "#fbbf24", borderRadius: [6, 6, 0, 0] },
            barMaxWidth: 32,
          },
        ],
      };
      chart.setOption(option);
    }

    const handleResize = () => chart.resize();
    window.addEventListener("resize", handleResize);
    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, [country1Data, country2Data, chartType]);

  const getRiskColor = (risk: number) => {
    if (risk > 70) return "#ef4444";
    if (risk > 40) return "#facc15";
    return "#22c55e";
  };

  const country1Risk = toNumberOr(country1Data?.risk);
  const country2Risk = toNumberOr(country2Data?.risk);

  if (!countries || countries.length === 0) {
    return (
      <div style={{ 
        height, 
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center",
        color: "#d6e4ff",
        background: "rgba(19, 30, 49, 0.72)",
        border: "1px solid rgba(96, 165, 250, 0.28)",
        borderRadius: "8px"
      }}>
        No country data available
      </div>
    );
  }

  return (
    <div style={{ width: "100%" }}>
      <div style={{ 
        display: "flex", 
        gap: "16px", 
        marginBottom: "16px",
        padding: "12px",
        background: "rgba(19, 30, 49, 0.72)",
        border: "1px solid rgba(96, 165, 250, 0.22)",
        borderRadius: "8px",
        alignItems: "center",
        flexWrap: "wrap",
      }}>
        <div style={{ color: "#c4d7ff", fontSize: "12px" }}>Compare:</div>
        
        <select
          value={selectedCountries[0] || ""}
          onChange={(e) => setSelectedCountries([e.target.value, selectedCountries[1] || ""])}
          style={{
            background: "rgba(19, 30, 49, 0.82)",
            border: "1px solid rgba(56,189,248,0.45)",
            color: "#d6e4ff",
            padding: "8px 12px",
            borderRadius: "6px",
            cursor: "pointer",
            minWidth: "150px",
          }}
        >
          <option value="">Select Country</option>
          {availableCountries.map((c) => (
            <option key={c.countryCode} value={c.countryCode} disabled={c.countryCode === selectedCountries[1]}>
              {c.country} ({c.countryCode})
            </option>
          ))}
        </select>

        <span style={{ color: "#c4d7ff" }}>vs</span>

        <select
          value={selectedCountries[1] || ""}
          onChange={(e) => setSelectedCountries([selectedCountries[0] || "", e.target.value])}
          style={{
            background: "rgba(19, 30, 49, 0.82)",
            border: "1px solid rgba(251,191,36,0.45)",
            color: "#d6e4ff",
            padding: "8px 12px",
            borderRadius: "6px",
            cursor: "pointer",
            minWidth: "150px",
          }}
        >
          <option value="">Select Country</option>
          {availableCountries.map((c) => (
            <option key={c.countryCode} value={c.countryCode} disabled={c.countryCode === selectedCountries[0]}>
              {c.country} ({c.countryCode})
            </option>
          ))}
        </select>

        <div style={{ flex: 1 }} />

        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={() => setChartType("radar")}
            style={{
              background: chartType === "radar" ? "rgba(56,189,248,0.22)" : "rgba(30,41,59,0.74)",
              border: `1px solid ${chartType === "radar" ? "rgba(56,189,248,0.6)" : "rgba(148,163,184,0.35)"}`,
              color: chartType === "radar" ? "#d6e4ff" : "#9fb0cf",
              padding: "6px 12px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "12px",
            }}
          >
            Radar
          </button>
          <button
            onClick={() => setChartType("bar")}
            style={{
              background: chartType === "bar" ? "rgba(56,189,248,0.22)" : "rgba(30,41,59,0.74)",
              border: `1px solid ${chartType === "bar" ? "rgba(56,189,248,0.6)" : "rgba(148,163,184,0.35)"}`,
              color: chartType === "bar" ? "#d6e4ff" : "#9fb0cf",
              padding: "6px 12px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "12px",
            }}
          >
            Bar
          </button>
        </div>
      </div>

      {country1Data && country2Data && (
        <div style={{ 
          display: "grid", 
          gridTemplateColumns: "1fr 1fr", 
          gap: "16px", 
          marginBottom: "16px" 
        }}>
          <div style={{ 
            padding: "16px", 
            background: "rgba(0,212,255,0.1)", 
            border: "1px solid rgba(0,212,255,0.3)",
            borderRadius: "8px" 
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h4 style={{ color: "#00d4ff", margin: 0 }}>{country1Data.country}</h4>
              <span style={{ 
                color: getRiskColor(country1Risk), 
                fontWeight: "bold", 
                fontSize: "20px" 
              }}>
                {country1Risk.toFixed(1)}
              </span>
            </div>
            <div style={{ fontSize: "11px", color: "#888", marginBottom: "8px" }}>
              Last updated: {new Date(country1Data.timestamp).toLocaleString()}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              {METRICS.slice(0, 4).map((m) => (
                <div key={m.key} style={{ fontSize: "11px" }}>
                  <span style={{ color: "#888" }}>{m.label}: </span>
                  <span style={{ color: "#aaa" }}>{m.format(country1Data.features?.[m.key] ?? 0)}</span>
                </div>
              ))}
            </div>
          </div>

          <div style={{ 
            padding: "16px", 
            background: "rgba(255,105,180,0.1)", 
            border: "1px solid rgba(255,105,180,0.3)",
            borderRadius: "8px" 
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h4 style={{ color: "#ff69b4", margin: 0 }}>{country2Data.country}</h4>
              <span style={{ 
                color: getRiskColor(country2Risk), 
                fontWeight: "bold", 
                fontSize: "20px" 
              }}>
                {country2Risk.toFixed(1)}
              </span>
            </div>
            <div style={{ fontSize: "11px", color: "#888", marginBottom: "8px" }}>
              Last updated: {new Date(country2Data.timestamp).toLocaleString()}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
              {METRICS.slice(0, 4).map((m) => (
                <div key={m.key} style={{ fontSize: "11px" }}>
                  <span style={{ color: "#888" }}>{m.label}: </span>
                  <span style={{ color: "#aaa" }}>{m.format(country2Data.features?.[m.key] ?? 0)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      <div ref={chartRef} style={{ width: "100%", height: height - 250 }} />

      <div style={{ 
        display: "flex", 
        justifyContent: "center", 
        gap: "24px", 
        marginTop: "8px",
        fontSize: "12px",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{ width: "12px", height: "12px", background: "#38bdf8", borderRadius: "2px" }} />
          <span style={{ color: "#c4d7ff" }}>{country1Data?.country || "Country 1"}</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{ width: "12px", height: "12px", background: "#fbbf24", borderRadius: "2px" }} />
          <span style={{ color: "#c4d7ff" }}>{country2Data?.country || "Country 2"}</span>
        </div>
      </div>
    </div>
  );
}

