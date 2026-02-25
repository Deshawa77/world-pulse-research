import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import CommandCenterHeader from "../components/CommandCenterHeader";
import CountryDrilldown from "../components/CountryDrilldown";
import EventLog, { type OperatorEvent } from "../components/EventLog";
import ModelGovernance from "../components/ModelGovernance";
import TimeSeriesChart from "../components/TimeSeriesChart";
import API, {
  API_HEADERS,
  getCountryDrilldown,
  getGovernanceData,
  getLiveCommandFeed,
  getRiskMap,
  postAlertAction,
  type CountryDrilldownData,
  type GovernanceData,
  type LiveCommandFeed,
  type RiskMapPoint,
} from "../services/api";

type Features = {
  news_sentiment: number;
  gdelt_sentiment: number;
  crypto_return: number;
  crypto_volatility: number;
  stock_return: number;
  stock_volatility: number;
  weather_anomaly: number;
  global_risk_score: number;
  top_topics: string[];
  timestamp: string;
};

type GlobalDoc = {
  features: Features;
};

type Snapshot = {
  timestamp: string;
  score: number;
  features: Record<string, number>;
  topics: string[];
};

type ConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected";
type PanelKey = "risk" | "map" | "stream" | "ops" | "governance";

const HISTORY_KEY = "wp_v3_history";
const EVENTS_KEY = "wp_v3_events";
const MAX_HISTORY = 1200;

function safeN(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeRisk(score: number): number {
  const clamped = Math.max(0, Math.min(100, safeN(score, 50)));
  return Number(clamped.toFixed(2));
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function buildSnapshot(doc: GlobalDoc): Snapshot {
  return {
    timestamp: doc.features.timestamp ?? new Date().toISOString(),
    score: normalizeRisk(doc.features.global_risk_score),
    features: {
      news_sentiment: safeN(doc.features.news_sentiment),
      gdelt_sentiment: safeN(doc.features.gdelt_sentiment),
      crypto_return: safeN(doc.features.crypto_return),
      crypto_volatility: safeN(doc.features.crypto_volatility),
      stock_return: safeN(doc.features.stock_return),
      stock_volatility: safeN(doc.features.stock_volatility),
      weather_anomaly: safeN(doc.features.weather_anomaly),
    },
    topics: Array.isArray(doc.features.top_topics) ? doc.features.top_topics : ["no data"],
  };
}

function staleFor(msSinceUpdate: number, thresholdMs: number): boolean {
  return msSinceUpdate > thresholdMs;
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [history, setHistory] = useState<Snapshot[]>(() => readJson(HISTORY_KEY, [] as Snapshot[]));
  const [liveFeed, setLiveFeed] = useState<LiveCommandFeed>({
    incidents: [],
    ingestionHeartbeatSec: 0,
    modelDrift: 0,
    lastUpdated: new Date().toISOString(),
  });
  const [governance, setGovernance] = useState<GovernanceData>({ models: [], disagreement: [], calibrationTrend: [] });
  const [riskMap, setRiskMap] = useState<RiskMapPoint[]>([]);
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [fpsLow, setFpsLow] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [countryData, setCountryData] = useState<CountryDrilldownData | null>(null);
  const [countryLoading, setCountryLoading] = useState(false);
  const [operatorEvents, setOperatorEvents] = useState<OperatorEvent[]>(() => readJson(EVENTS_KEY, [] as OperatorEvent[]));
  const [mapHover, setMapHover] = useState<{ country: string; risk: number } | null>(null);
  const [errorText, setErrorText] = useState("");
  const [lastKnownGood, setLastKnownGood] = useState<Snapshot | null>(null);
  const [retries, setRetries] = useState(0);
  const [activePreset, setActivePreset] = useState<"analyst" | "ops" | "executive">("analyst");

  const panelUpdated = useRef<Record<PanelKey, number>>({
    risk: Date.now(),
    map: Date.now(),
    stream: Date.now(),
    ops: Date.now(),
    governance: Date.now(),
  });
  const retriesRef = useRef(0);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapMounted = useRef(false);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);

  const active = history[history.length - 1] ?? null;
  const riskDelta = active && lastKnownGood ? active.score - lastKnownGood.score : 0;
  const panelStale = useMemo(() => {
    const now = Date.now();
    return {
      risk: staleFor(now - panelUpdated.current.risk, 12000),
      map: staleFor(now - panelUpdated.current.map, 12000),
      stream: staleFor(now - panelUpdated.current.stream, 12000),
      ops: staleFor(now - panelUpdated.current.ops, 30000),
      governance: staleFor(now - panelUpdated.current.governance, 60000),
    };
  }, [history.length, operatorEvents.length, governance.calibrationTrend.length, riskMap.length]);

  const topTopics = active?.topics?.slice(0, 5) ?? [];
  const riskSeries = useMemo(
    () => [
      {
        name: "Global risk",
        points: history.slice(-120).map((h) => ({ timestamp: h.timestamp, value: h.score })),
      },
      {
        name: "Sentiment",
        points: history.slice(-120).map((h) => ({ timestamp: h.timestamp, value: (h.features.news_sentiment + 1) * 40 })),
      },
    ],
    [history],
  );
  const anomalyMarks = useMemo(
    () => history.slice(-120).filter((h) => h.score > 75 || h.score < 25).map((h) => ({ timestamp: h.timestamp, value: h.score })),
    [history],
  );

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
  }, [history]);

  useEffect(() => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify(operatorEvents.slice(0, 200)));
  }, [operatorEvents]);

  useEffect(() => {
    let raf = 0;
    let prev = performance.now();
    let frames = 0;
    let acc = 0;
    const loop = (now: number) => {
      frames += 1;
      acc += now - prev;
      prev = now;
      if (acc >= 1000) {
        setFpsLow(frames < 28);
        frames = 0;
        acc = 0;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    let stop = false;
    let timer = 0;
    const pull = async () => {
      if (stop) return;
      setConnectionState(retriesRef.current > 0 ? "reconnecting" : "connecting");
      try {
        const [live, gov, mapRows, global] = await Promise.all([
          getLiveCommandFeed(),
          getGovernanceData(),
          getRiskMap(),
          API.get("/features/global/latest", { headers: API_HEADERS, params: { mode: "online" } }),
        ]);

        const features = global.data?.features;
        if (features) {
          const snap = buildSnapshot({ features } as GlobalDoc);
          setHistory((prev) => {
            const last = prev[prev.length - 1];
            if (last?.timestamp === snap.timestamp) return prev;
            return [...prev, snap].slice(-MAX_HISTORY);
          });
          setLastKnownGood(snap);
          panelUpdated.current.risk = Date.now();
          panelUpdated.current.stream = Date.now();
        }

        setLiveFeed(live);
        setGovernance(gov);
        setRiskMap(mapRows);
        panelUpdated.current.map = Date.now();
        panelUpdated.current.governance = Date.now();
        setErrorText("");
        retriesRef.current = 0;
        setRetries(0);
        setConnectionState("connected");
      } catch (e: any) {
        retriesRef.current += 1;
        setRetries(retriesRef.current);
        setConnectionState(retriesRef.current > 3 ? "disconnected" : "reconnecting");
        setErrorText(String(e?.message ?? "Failed to refresh dashboard feed"));
      } finally {
        const delay = retriesRef.current > 0 ? Math.min(15000, 2000 * (retriesRef.current + 1)) : 2000;
        timer = window.setTimeout(pull, delay);
      }
    };
    pull();
    return () => {
      stop = true;
      window.clearTimeout(timer);
    };
  }, []);

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

    const drawMap = async () => {
      if (!mapRef.current || riskMap.length === 0) return;
      try {
        const Plotly = await loadPlotly();
        if (stopped || !mapRef.current) return;
        await Plotly.react(
          mapRef.current,
          [
            {
              type: "choropleth",
              locationmode: "ISO-3",
              locations: riskMap.map((r) => r.country),
              z: riskMap.map((r) => normalizeRisk(r.risk)),
              zmin: 0,
              zmax: 100,
              colorscale: [
                [0, "#22c55e"],
                [0.4, "#facc15"],
                [0.7, "#fb923c"],
                [1, "#ef4444"],
              ],
              hovertemplate: "%{location}<br>Risk: %{z:.1f}<extra></extra>",
            },
          ] as any,
          {
            margin: { l: 0, r: 0, b: 0, t: 0 },
            paper_bgcolor: "rgba(0,0,0,0)",
            plot_bgcolor: "rgba(0,0,0,0)",
            geo: { projection: { type: "natural earth" }, showframe: false, bgcolor: "rgba(0,0,0,0)" },
          } as any,
          { displayModeBar: false, responsive: true },
        );

        if (!mapMounted.current) {
          mapMounted.current = true;
          (mapRef.current as any).on?.("plotly_hover", (e: any) => {
            const p = e?.points?.[0];
            if (!p) return;
            setMapHover({ country: String(p.location), risk: Number(p.z) });
          });
          (mapRef.current as any).on?.("plotly_click", (e: any) => {
            const p = e?.points?.[0];
            if (!p?.location) return;
            setSelectedCountry(String(p.location));
          });
          (mapRef.current as any).on?.("plotly_unhover", () => setMapHover(null));
        }
      } catch {
        setErrorText("Unable to render map");
      }
    };
    drawMap();
    return () => {
      stopped = true;
    };
  }, [riskMap]);

  useEffect(() => {
    if (!selectedCountry) return;
    let closed = false;
    setCountryLoading(true);
    getCountryDrilldown(selectedCountry)
      .then((data) => {
        if (closed) return;
        setCountryData(data);
        panelUpdated.current.map = Date.now();
      })
      .catch(() => {
        if (!closed) setCountryData(null);
      })
      .finally(() => {
        if (!closed) setCountryLoading(false);
      });
    return () => {
      closed = true;
    };
  }, [selectedCountry, liveFeed.lastUpdated]);

  const addEvent = async (action: OperatorEvent["action"], comment?: string, owner = "ops-team") => {
    const evt: OperatorEvent = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      timestamp: new Date().toISOString(),
      actor: owner,
      action,
      comment,
    };
    setOperatorEvents((prev) => [evt, ...prev].slice(0, 200));
    panelUpdated.current.ops = Date.now();
    if (selectedCountry) {
      await postAlertAction({
        country: selectedCountry,
        action: action === "assign" ? "assign" : action,
        owner,
        comment,
      });
    }
  };

  return (
    <main className={`wp-shell dashboard-v2 ${fpsLow ? "motion-low" : "motion-rich"}`}>
      <div className="parallax-grid" />
      <header className="wp-top">
        <div className="wp-burger"><span /><span /><span /></div>
        <div>
          <h1>THE WORLD'S <span>PULSE</span></h1>
          <p>Operational Intelligence Dashboard</p>
        </div>
        <div className="wp-actions-inline">
          <button onClick={() => navigate("/trend-prediction")}>Predictions</button>
          <button onClick={() => navigate("/historical-trends")}>Historical</button>
          <button onClick={() => navigate("/scenario")}>Scenario Studio</button>
        </div>
      </header>

      <CommandCenterHeader
        incidents={liveFeed.incidents}
        ingestionHeartbeatSec={liveFeed.ingestionHeartbeatSec}
        modelDrift={liveFeed.modelDrift}
        connectionState={connectionState}
        lastUpdated={liveFeed.lastUpdated}
      />

      <section className="wp-strip">
        <article className="wp-card">
          <h3>Layout</h3>
          <div className="wp-mini-meta"><span>Preset</span><strong>{activePreset}</strong></div>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={() => setActivePreset("analyst")}>Analyst</button>
            <button onClick={() => setActivePreset("ops")}>Ops</button>
            <button onClick={() => setActivePreset("executive")}>Executive</button>
          </div>
        </article>
        <article className="wp-card">
          <h3>Reliability</h3>
          <div className="wp-mini-meta"><span>Feed</span><strong>{connectionState}</strong></div>
          <div className="wp-mini-meta"><span>Retries</span><strong>{retries}</strong></div>
          {errorText ? <div className="map-fallback-error">{errorText}</div> : null}
        </article>
        <article className="wp-card">
          <h3>Global Risk</h3>
          <strong className="wp-highlight">{(active?.score ?? 50).toFixed(2)} / 100</strong>
          <div className="wp-mini-meta"><span>Last-known-good delta</span><strong>{riskDelta >= 0 ? "+" : ""}{riskDelta.toFixed(2)}</strong></div>
        </article>
        <article className="wp-card">
          <h3>Commands</h3>
          <div className="feed">
            <button onClick={() => addEvent("acknowledge", "global acknowledge")}>Acknowledge</button>
            <button onClick={() => addEvent("snooze", "15m snooze")}>Snooze</button>
            <button onClick={() => addEvent("assign", "escalated", "analyst-1")}>Assign</button>
          </div>
        </article>
      </section>

      <section className="dashboard-grid-layout">
        <article className={`wp-card panel-frame ${fpsLow ? "" : "panel-animated"}`}>
          <div className="panel-head"><h3>Map Intelligence</h3></div>
          {panelStale.map ? <div className="panel-stale">stale</div> : null}
          <div className="wp-map-surface">
            <div ref={mapRef} className="echart-map" />
            {mapHover ? (
              <div className="map-hover-box">
                <strong>{mapHover.country}</strong>
                <span>Risk {mapHover.risk.toFixed(1)}</span>
              </div>
            ) : null}
          </div>
          <p>Click country on map for drilldown.</p>
        </article>

        <article className={`wp-card panel-frame ${fpsLow ? "" : "panel-animated"}`}>
          <div className="panel-head"><h3>Streaming Trends</h3></div>
          {panelStale.stream ? <div className="panel-stale">stale</div> : null}
          <TimeSeriesChart title="Real-time feature stream" series={riskSeries} anomalies={anomalyMarks} thresholdBand={{ low: 35, high: 75 }} />
          <div className="wp-mini-meta"><span>Top topics</span><span>{topTopics.join(", ") || "none"}</span></div>
        </article>

        <article className={`wp-card panel-frame ${fpsLow ? "" : "panel-animated"}`}>
          <div className="panel-head"><h3>Operator Workflow</h3></div>
          {panelStale.ops ? <div className="panel-stale">stale</div> : null}
          <EventLog events={operatorEvents} />
        </article>

        <article className={`wp-card panel-frame ${fpsLow ? "" : "panel-animated"}`}>
          <div className="panel-head"><h3>Model Governance</h3></div>
          {panelStale.governance ? <div className="panel-stale">stale</div> : null}
          <ModelGovernance data={governance} />
        </article>
      </section>

      <CountryDrilldown
        open={Boolean(selectedCountry)}
        loading={countryLoading}
        data={countryData}
        events={operatorEvents}
        onClose={() => setSelectedCountry(null)}
        onAcknowledge={(comment) => {
          void addEvent("acknowledge", comment);
        }}
        onSnooze={(comment) => {
          void addEvent("snooze", comment);
        }}
        onAssign={(owner, comment) => {
          void addEvent("assign", comment, owner);
        }}
      />
    </main>
  );
}
