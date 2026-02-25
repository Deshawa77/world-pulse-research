import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
  postAlertAction,
  type CountryDrilldownData,
  type GovernanceData,
  type LiveCommandFeed,
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

const ISO3 = ["USA", "CAN", "MEX", "BRA", "ARG", "GBR", "FRA", "DEU", "ESP", "ITA", "IND", "CHN", "JPN", "AUS", "ZAF"];
const HISTORY_KEY = "wp_v2_history";
const LAYOUT_KEY = "wp_v2_layout";
const EVENTS_KEY = "wp_v2_events";
const MAX_HISTORY = 1200;

type PanelKey = "risk" | "map" | "stream" | "ops" | "governance";

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

export default function Dashboard() {
  const navigate = useNavigate();
  const [history, setHistory] = useState<Snapshot[]>(() => readJson(HISTORY_KEY, [] as Snapshot[]));
  const [liveFeed, setLiveFeed] = useState<LiveCommandFeed>({
    incidents: ["Bootstrapping command center..."],
    ingestionHeartbeatSec: 1,
    modelDrift: 0,
    lastUpdated: new Date().toISOString(),
  });
  const [governance, setGovernance] = useState<GovernanceData>({
    models: [],
    disagreement: [],
    calibrationTrend: [],
  });
  const [connectionState, setConnectionState] = useState<ConnectionState>("connecting");
  const [panelOrder, setPanelOrder] = useState<PanelKey[]>(() =>
    readJson<PanelKey[]>(LAYOUT_KEY, ["risk", "map", "stream", "ops", "governance"]),
  );
  const [preset, setPreset] = useState<"analyst" | "ops" | "executive">("analyst");
  const [fullPanel, setFullPanel] = useState<PanelKey | null>(null);
  const [fpsLow, setFpsLow] = useState(false);
  const [selectedCountry, setSelectedCountry] = useState<string | null>(null);
  const [countryData, setCountryData] = useState<CountryDrilldownData | null>(null);
  const [countryLoading, setCountryLoading] = useState(false);
  const [operatorEvents, setOperatorEvents] = useState<OperatorEvent[]>(() => readJson(EVENTS_KEY, [] as OperatorEvent[]));
  const [mapHover, setMapHover] = useState<{ country: string; risk: number } | null>(null);
  const [retries, setRetries] = useState(0);
  const [errorText, setErrorText] = useState("");
  const [lastKnownGood, setLastKnownGood] = useState<Snapshot | null>(null);
  const panelUpdated = useRef<Record<PanelKey, number>>({
    risk: Date.now(),
    map: Date.now(),
    stream: Date.now(),
    ops: Date.now(),
    governance: Date.now(),
  });
  const dragRef = useRef<PanelKey | null>(null);
  const retriesRef = useRef(0);
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapMounted = useRef(false);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);

  const active = history[history.length - 1] ?? null;
  const riskDelta = active && lastKnownGood ? active.score - lastKnownGood.score : 0;
  const stalePanels = useMemo(() => {
    const now = Date.now();
    return {
      risk: now - panelUpdated.current.risk > 12_000,
      map: now - panelUpdated.current.map > 12_000,
      stream: now - panelUpdated.current.stream > 12_000,
      ops: now - panelUpdated.current.ops > 30_000,
      governance: now - panelUpdated.current.governance > 60_000,
    };
  }, [history.length, operatorEvents.length, governance.calibrationTrend.length, liveFeed.lastUpdated]);

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
  }, [history]);

  useEffect(() => {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(panelOrder));
  }, [panelOrder]);

  useEffect(() => {
    localStorage.setItem(EVENTS_KEY, JSON.stringify(operatorEvents.slice(-200)));
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
    let dead = false;
    let timer = 0;
    const pull = async () => {
      if (dead) return;
      setConnectionState((prev) => (prev === "connected" ? "connected" : retriesRef.current > 0 ? "reconnecting" : "connecting"));
      try {
        const [live, gov, global] = await Promise.all([
          getLiveCommandFeed(),
          getGovernanceData(),
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
          panelUpdated.current.risk = Date.now();
          panelUpdated.current.stream = Date.now();
          panelUpdated.current.map = Date.now();
          setLastKnownGood(snap);
        }
        setLiveFeed(live);
        setGovernance(gov);
        panelUpdated.current.governance = Date.now();
        setConnectionState("connected");
        retriesRef.current = 0;
        setRetries(0);
        setErrorText("");
      } catch (e: any) {
        retriesRef.current += 1;
        setRetries(retriesRef.current);
        setConnectionState((prev) => (prev === "disconnected" ? "disconnected" : "reconnecting"));
        setErrorText(String(e?.message ?? "feed error"));
        if (retriesRef.current > 3) {
          setConnectionState("disconnected");
        }
      } finally {
        const delay = retriesRef.current > 0 ? Math.min(15_000, 2000 * (retriesRef.current + 1)) : 2000;
        timer = window.setTimeout(pull, delay);
      }
    };
    pull();
    return () => {
      dead = true;
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
      if (!mapRef.current || !active) return;
      try {
        const Plotly = await loadPlotly();
        if (stopped || !mapRef.current) return;
        const base = active.score;
        const z = ISO3.map((_, i) => normalizeRisk(base + Math.sin(i / 2) * 12 + (i % 3) * 3));
        await Plotly.react(
          mapRef.current,
          [
            {
              type: "choropleth",
              locationmode: "ISO-3",
              locations: ISO3,
              z,
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
            const country = String(p.location);
            setSelectedCountry(country);
          });
          (mapRef.current as any).on?.("plotly_unhover", () => setMapHover(null));
        }
      } catch {
        setErrorText("Map rendering unavailable");
      }
    };
    drawMap();
    return () => {
      stopped = true;
    };
  }, [active?.score]);

  useEffect(() => {
    if (!selectedCountry) return;
    let closed = false;
    setCountryLoading(true);
    getCountryDrilldown(selectedCountry).then((data) => {
      if (closed) return;
      setCountryData(data);
      panelUpdated.current.map = Date.now();
      setCountryLoading(false);
    });
    return () => {
      closed = true;
    };
  }, [selectedCountry, liveFeed.lastUpdated]);

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
    () =>
      history
        .slice(-120)
        .filter((h) => h.score > 75 || h.score < 28)
        .map((h) => ({ timestamp: h.timestamp, value: h.score })),
    [history],
  );

  const topTopics = active?.topics?.slice(0, 5) ?? [];

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
        action: action === "acknowledge" ? "acknowledge" : action === "snooze" ? "snooze" : "assign",
        owner,
        comment,
      });
    }
  };

  const applyPreset = (next: "analyst" | "ops" | "executive") => {
    setPreset(next);
    if (next === "analyst") setPanelOrder(["risk", "stream", "map", "governance", "ops"]);
    if (next === "ops") setPanelOrder(["map", "ops", "risk", "stream", "governance"]);
    if (next === "executive") setPanelOrder(["risk", "governance", "map", "stream", "ops"]);
  };

  const reorderPanels = (from: PanelKey, to: PanelKey) => {
    if (from === to) return;
    setPanelOrder((prev) => {
      const next = [...prev];
      const fromIdx = next.indexOf(from);
      const toIdx = next.indexOf(to);
      if (fromIdx < 0 || toIdx < 0) return prev;
      next.splice(fromIdx, 1);
      next.splice(toIdx, 0, from);
      return next;
    });
  };

  const panelNode = (key: PanelKey) => {
    const wrap = (title: string, content: ReactNode) => (
      <article
        className={`wp-card panel-frame ${fpsLow ? "" : "panel-animated"} ${fullPanel === key ? "panel-fullscreen" : ""}`}
        draggable
        onDragStart={() => {
          dragRef.current = key;
        }}
        onDragOver={(e) => e.preventDefault()}
        onDrop={() => {
          if (dragRef.current) reorderPanels(dragRef.current, key);
        }}
        style={{ resize: "both", overflow: "auto" }}
      >
        <div className="panel-head">
          <h3>{title}</h3>
          <div>
            <button onClick={() => setFullPanel((prev) => (prev === key ? null : key))}>{fullPanel === key ? "Exit Full" : "Full"}</button>
          </div>
        </div>
        {stalePanels[key] ? <div className="panel-stale">stale</div> : null}
        {content}
      </article>
    );

    if (key === "risk") {
      return wrap(
        "Global Risk",
        <>
          <div className="wp-highlight">{(active?.score ?? 50).toFixed(2)} / 100</div>
          <div className="wp-mini-meta"><span>Last-known-good delta</span><strong>{riskDelta >= 0 ? "+" : ""}{riskDelta.toFixed(2)}</strong></div>
          <div className="wp-mini-meta"><span>Topics</span><span>{topTopics.join(", ") || "none"}</span></div>
          <div className="wp-mini-meta"><span>Connection</span><strong>{connectionState}</strong></div>
        </>,
      );
    }
    if (key === "map") {
      return wrap(
        "Map Intelligence",
        <>
          <div className="wp-map-surface">
            <div ref={mapRef} className="echart-map" />
            {mapHover ? (
              <div className="map-hover-box">
                <strong>{mapHover.country}</strong>
                <span>Risk {mapHover.risk.toFixed(1)}</span>
              </div>
            ) : null}
          </div>
          <p>Click a country on map for drilldown.</p>
        </>,
      );
    }
    if (key === "stream") {
      return wrap(
        "Streaming Trends",
        <TimeSeriesChart title="Real-time feature stream" series={riskSeries} anomalies={anomalyMarks} thresholdBand={{ low: 35, high: 75 }} />,
      );
    }
    if (key === "ops") {
      return wrap(
        "Operator Workflow",
        <EventLog events={operatorEvents} />,
      );
    }
    return wrap("Model Governance", <ModelGovernance data={governance} />);
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
          <h3>Preset</h3>
          <div className="wp-mini-meta"><span>Current</span><strong>{preset}</strong></div>
          <div style={{ display: "flex", gap: 6 }}>
            <button onClick={() => applyPreset("analyst")}>Analyst</button>
            <button onClick={() => applyPreset("ops")}>Ops</button>
            <button onClick={() => applyPreset("executive")}>Executive</button>
          </div>
        </article>
        <article className="wp-card">
          <h3>Reliability</h3>
          <div className="wp-mini-meta"><span>Feed state</span><strong>{connectionState}</strong></div>
          <div className="wp-mini-meta"><span>Retries</span><strong>{retries}</strong></div>
          {errorText ? <div className="map-fallback-error">{errorText}</div> : null}
        </article>
        <article className="wp-card">
          <h3>Ingestion</h3>
          <div className="wp-mini-meta"><span>Heartbeat</span><strong>{liveFeed.ingestionHeartbeatSec.toFixed(1)}s</strong></div>
          <div className="wp-mini-meta"><span>Drift badge</span><strong>{liveFeed.modelDrift.toFixed(2)}</strong></div>
        </article>
        <article className="wp-card">
          <h3>Commands</h3>
          <div className="feed">
            <button onClick={() => addEvent("acknowledge", "global ack")}>Acknowledge</button>
            <button onClick={() => addEvent("snooze", "15m snooze")}>Snooze</button>
            <button onClick={() => addEvent("assign", "escalated", "analyst-1")}>Assign</button>
          </div>
        </article>
      </section>

      <section className="dashboard-grid-layout">
        {panelOrder.map((k) => (
          <div key={k} className={`grid-item ${fullPanel && fullPanel !== k ? "grid-item-hidden" : ""}`}>
            {panelNode(k)}
          </div>
        ))}
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
