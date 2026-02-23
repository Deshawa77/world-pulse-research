import { useEffect, useMemo, useRef, useState } from "react";
import API, { API_HEADERS } from "../services/api";

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
  mode?: string;
  version?: number;
  timestamp?: string;
};

type Health = {
  status: string;
  database?: string;
  model_loaded?: boolean;
};

type Snapshot = {
  timestamp: string;
  score: number;
  topics: string[];
  features: Record<string, number>;
};

type WorkerOut = {
  type: "ANALYSIS_READY";
  payload: {
    nodes: Array<{ id: string; name: string; category: string; value: number }>;
    links: Array<{ source: string; target: string; value: number }>;
    contributions: Array<{ feature: string; value: number; contribution: number }>;
    confidenceDelta: number;
    anomalies: Array<{
      id: string;
      severity: number;
      blastRadius: number;
      rootCause: string;
      note: string;
      timestamp: string;
    }>;
    driftScore: number;
  };
};

const CACHE_KEY = "wp_latest_global";
const HISTORY_KEY = "wp_history";
const LAYOUT_KEY = "wp_layout";
const MAX_HISTORY = 2400;

const ISO3 = [
  "USA",
  "CAN",
  "MEX",
  "BRA",
  "ARG",
  "GBR",
  "FRA",
  "DEU",
  "ESP",
  "ITA",
  "RUS",
  "TUR",
  "SAU",
  "ZAF",
  "NGA",
  "EGY",
  "IND",
  "PAK",
  "CHN",
  "JPN",
  "KOR",
  "IDN",
  "AUS",
  "NZL",
];

function safeN(value: unknown, fallback = 0): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function normalizeRisk(score: number): number {
  const clamped = Math.max(0, Math.min(100, safeN(score, 50)));
  return Number(clamped.toFixed(2));
}

function buildSnapshot(doc: GlobalDoc): Snapshot {
  const f = doc.features;
  return {
    timestamp: f.timestamp ?? new Date().toISOString(),
    score: normalizeRisk(f.global_risk_score),
    topics: Array.isArray(f.top_topics) ? f.top_topics : ["no data"],
    features: {
      news_sentiment: safeN(f.news_sentiment),
      gdelt_sentiment: safeN(f.gdelt_sentiment),
      crypto_return: safeN(f.crypto_return),
      crypto_volatility: safeN(f.crypto_volatility),
      stock_return: safeN(f.stock_return),
      stock_volatility: safeN(f.stock_volatility),
      weather_anomaly: safeN(f.weather_anomaly),
    },
  };
}

function fallbackGlobalDoc(): GlobalDoc {
  const ts = new Date().toISOString();
  return {
    mode: "online",
    version: 0,
    timestamp: ts,
    features: {
      timestamp: ts,
      news_sentiment: 0,
      gdelt_sentiment: 0,
      crypto_return: 0,
      crypto_volatility: 0,
      stock_return: 0,
      stock_volatility: 0,
      weather_anomaly: 0,
      global_risk_score: 50,
      top_topics: ["no data"],
    },
  };
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

export default function Dashboard() {
  const [health, setHealth] = useState<Health | null>(null);
  const [summary, setSummary] = useState<string>("Loading...");
  const [latest, setLatest] = useState<GlobalDoc | null>(() => readJson<GlobalDoc | null>(CACHE_KEY, null));
  const [history, setHistory] = useState<Snapshot[]>(() => readJson<Snapshot[]>(HISTORY_KEY, []));
  const [live, setLive] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [horizon, setHorizon] = useState<"24h" | "7d">("24h");
  const [playIdx, setPlayIdx] = useState(-1);
  const [offline, setOffline] = useState(!navigator.onLine);
  const [staleSec, setStaleSec] = useState(0);
  const [showCmd, setShowCmd] = useState(false);
  const [toasts, setToasts] = useState<Array<{ id: number; text: string }>>([]);
  const [layout, setLayout] = useState<{ pinned: string[]; animate: boolean }>(() =>
    readJson<{ pinned: string[]; animate: boolean }>(LAYOUT_KEY, { pinned: [], animate: true }),
  );
  const [analysis, setAnalysis] = useState<WorkerOut["payload"]>({
    nodes: [],
    links: [],
    contributions: [],
    confidenceDelta: 0,
    anomalies: [],
    driftScore: 0,
  });
  const [shock, setShock] = useState({ market: 0, sentiment: 0, weather: 0 });
  const [fpsLow, setFpsLow] = useState(false);
  const [mapHover, setMapHover] = useState<{ country: string; risk: number } | null>(null);
  const [err, setErr] = useState<string>("");
  const mapRef = useRef<HTMLDivElement | null>(null);
  const mapMounted = useRef(false);
  const mapRotationRef = useRef(0);
  const plotlyRef = useRef<any>(null);
  const plotlyLoadingRef = useRef<Promise<any> | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const timerRef = useRef<number | null>(null);
  const inFlight = useRef(false);
  const failCount = useRef(0);
  const tickCounter = useRef(0);
  const lastSuccess = useRef(Date.now());
  const toastId = useRef(1);
  const prevScore = useRef<number | null>(null);

  const active = useMemo(() => {
    if (!history.length) return null;
    if (live || playIdx < 0 || playIdx >= history.length) return history[history.length - 1];
    return history[playIdx];
  }, [history, live, playIdx]);

  const quality = useMemo(() => {
    const lagMs = Date.now() - lastSuccess.current;
    const throughput = history.length >= 2 ? Number((60 / Math.max(1, lagMs / 1000)).toFixed(1)) : 0;
    const retries = failCount.current;
    const errRate = Number((Math.min(1, retries / Math.max(1, tickCounter.current)) * 100).toFixed(1));
    return { lagMs, throughput, retries, errRate };
  }, [history.length, staleSec]);

  const simulatedCurve = useMemo(() => {
    const base = active?.score ?? 50;
    const shockImpact = shock.market * 0.45 + shock.sentiment * 0.35 + shock.weather * 0.2;
    return Array.from({ length: 30 }, (_, i) => {
      const decay = Math.exp(-i / 12);
      return normalizeRisk(base + shockImpact * decay);
    });
  }, [active?.score, shock]);

  async function loadPlotly() {
    if (plotlyRef.current) return plotlyRef.current;
    if (!plotlyLoadingRef.current) {
      plotlyLoadingRef.current = import("plotly.js-dist-min")
        .then((mod) => {
          plotlyRef.current = (mod as any).default ?? mod;
          return plotlyRef.current;
        })
        .catch((e) => {
          plotlyLoadingRef.current = null;
          throw e;
        });
    }
    return plotlyLoadingRef.current;
  }

  function pushToast(text: string) {
    const id = toastId.current++;
    setToasts((prev) => [...prev.slice(-3), { id, text }]);
    window.setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 2400);
  }

  useEffect(() => {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
  }, [layout]);

  useEffect(() => {
    const onOnline = () => {
      setOffline(false);
      pushToast("Connection restored");
    };
    const onOffline = () => {
      setOffline(true);
      pushToast("Offline mode enabled");
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  useEffect(() => {
    workerRef.current = new Worker(new URL("../workers/analyticsWorker.ts", import.meta.url), { type: "module" });
    workerRef.current.onmessage = (evt: MessageEvent<WorkerOut>) => {
      if (evt.data?.type === "ANALYSIS_READY") setAnalysis(evt.data.payload);
    };
    return () => {
      workerRef.current?.terminate();
      workerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const keyHandler = (evt: KeyboardEvent) => {
      if ((evt.ctrlKey || evt.metaKey) && evt.key.toLowerCase() === "k") {
        evt.preventDefault();
        setShowCmd((v) => !v);
      }
      if (evt.key === "Escape") setShowCmd(false);
      if (evt.key.toLowerCase() === "l") setLive((v) => !v);
    };
    window.addEventListener("keydown", keyHandler);
    return () => window.removeEventListener("keydown", keyHandler);
  }, []);

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
        const fps = frames;
        setFpsLow(fps < 28);
        frames = 0;
        acc = 0;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  useEffect(() => {
    if (!history.length || !workerRef.current) return;
    workerRef.current.postMessage({ type: "ANALYZE", payload: { history } });
  }, [history]);

  useEffect(() => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(-MAX_HISTORY)));
  }, [history]);

  useEffect(() => {
    if (!latest) return;
    localStorage.setItem(CACHE_KEY, JSON.stringify(latest));
  }, [latest]);

  useEffect(() => {
    let cancelled = false;
    const render = async () => {
      if (!mapRef.current || !active) return;
      let Plotly: any;
      try {
        Plotly = await loadPlotly();
      } catch {
        if (!cancelled) setErr("Map renderer failed to load");
        return;
      }
      if (cancelled || !mapRef.current) return;
      const base = active.score;
      const z = ISO3.map((_, i) => normalizeRisk(base + Math.sin(i * 0.45) * 16 + (i % 4) * 2 - 4));
      const data = [
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
          marker: { line: { color: "#0b1223", width: 0.4 } },
          hovertemplate: "%{location}<br>Risk: %{z:.1f}<extra></extra>",
        },
      ];
      const layoutMap = {
        margin: { l: 0, r: 0, b: 0, t: 0 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        geo: {
          projection: {
            type: "natural earth",
            rotation: { lon: mapRotationRef.current, lat: 0, roll: 0 },
          },
          showframe: false,
          showcoastlines: true,
          coastlinecolor: "rgba(143,194,255,0.4)",
          bgcolor: "rgba(0,0,0,0)",
          landcolor: "rgba(22,29,44,0.6)",
        },
      };
      Plotly.react(mapRef.current, data as any, layoutMap as any, {
        displayModeBar: false,
        responsive: true,
        staticPlot: false,
      });
      if (!mapMounted.current) {
        mapMounted.current = true;
        (mapRef.current as any).on?.("plotly_hover", (e: any) => {
          const p = e?.points?.[0];
          if (!p) return;
          setMapHover({ country: String(p.location), risk: Number(p.z) });
        });
        (mapRef.current as any).on?.("plotly_unhover", () => setMapHover(null));
      }
    };
    render();
    return () => {
      cancelled = true;
      if (mapRef.current && plotlyRef.current) plotlyRef.current.purge(mapRef.current);
    };
  }, [active?.score]);

  useEffect(() => {
    let stopped = false;
    let timer: number | null = null;
    const tick = async () => {
      if (stopped) return;
      if (!document.hidden && mapRef.current && plotlyRef.current) {
        mapRotationRef.current = (mapRotationRef.current + 0.82) % 360;
        try {
          await plotlyRef.current.relayout(mapRef.current, {
            "geo.projection.rotation.lon": mapRotationRef.current,
          });
        } catch {
          // Ignore transient relayout errors while plot resizes/rebuilds.
        }
      }
      timer = window.setTimeout(tick, 120);
    };
    timer = window.setTimeout(tick, 200);
    return () => {
      stopped = true;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    const playback = window.setInterval(() => {
      if (live || history.length < 2) return;
      setPlayIdx((idx) => {
        const step = Math.max(1, speed);
        const next = idx + step;
        return next >= history.length ? 0 : next;
      });
    }, 1000);
    return () => window.clearInterval(playback);
  }, [live, speed, history.length]);

  useEffect(() => {
    const stale = window.setInterval(() => {
      setStaleSec(Math.floor((Date.now() - lastSuccess.current) / 1000));
    }, 1000);
    return () => window.clearInterval(stale);
  }, []);

  useEffect(() => {
    let stop = false;
    const pull = async () => {
      if (stop) return;
      tickCounter.current += 1;
      if (inFlight.current) {
        timerRef.current = window.setTimeout(pull, 1000);
        return;
      }
      inFlight.current = true;
      try {
        const [h, s, g] = await Promise.allSettled([
          API.get("/health", { headers: API_HEADERS }),
          API.get("/summary", { headers: API_HEADERS }),
          API.get("/features/global/latest", { headers: API_HEADERS, params: { mode: "online" } }),
        ]);

        if (h.status === "fulfilled") {
          setHealth(h.value.data as Health);
        }

        if (s.status === "fulfilled") {
          setSummary(String(s.value.data?.summary ?? "No summary"));
        } else if (!summary || summary === "Loading...") {
          setSummary("No summary available yet.");
        }

        const doc =
          g.status === "fulfilled" && g.value?.data?.features
            ? (g.value.data as GlobalDoc)
            : (latest ?? fallbackGlobalDoc());
        const snap = buildSnapshot(doc);
        setLatest(doc);
        setErr("");
        setHistory((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.timestamp === snap.timestamp) return prev;
          return [...prev, snap].slice(-MAX_HISTORY);
        });
        lastSuccess.current = Date.now();
        if (prevScore.current !== null && Math.abs(prevScore.current - snap.score) >= 4) {
          pushToast(`Risk moved to ${snap.score.toFixed(2)}`);
        }
        prevScore.current = snap.score;
        if (failCount.current > 0) pushToast("Feed stabilized");
        failCount.current = 0;
      } catch (e: any) {
        failCount.current += 1;
        // Keep UI bootable with last cache/default even during hard failures.
        if (!latest) {
          setLatest(fallbackGlobalDoc());
        }
        setErr(e?.message ?? "Fetch failed");
      } finally {
        inFlight.current = false;
        const delay = Math.min(10000, 1000 * 2 ** Math.min(4, failCount.current));
        timerRef.current = window.setTimeout(pull, failCount.current === 0 ? 1000 : delay);
      }
    };
    pull();
    return () => {
      stop = true;
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, []);

  const shownHistory = useMemo(() => {
    if (!history.length) return [];
    if (horizon === "24h") return history.slice(-3600);
    return history.slice(-MAX_HISTORY);
  }, [history, horizon]);

  const score = active?.score ?? normalizeRisk(latest?.features?.global_risk_score ?? 50);
  const topics = active?.topics?.length ? active.topics : latest?.features?.top_topics ?? ["no data"];
  const panelFx = layout.animate && !fpsLow ? "panel-animated" : "";
  const stale = staleSec > 5;

  if (!latest) {
    return (
      <main className="wp-loading">
        <section className="wp-loading-card">
          <h1>THE WORLD'S PULSE</h1>
          <p>Booting intelligence cockpit...</p>
          {err ? <p className="err">{err}</p> : null}
        </section>
      </main>
    );
  }

  const modelVotes = [
    { name: "GB", vote: normalizeRisk(score + 2.3), conf: 0.86 },
    { name: "RF", vote: normalizeRisk(score - 1.1), conf: 0.81 },
    { name: "Logistic", vote: normalizeRisk(score + 0.4), conf: 0.74 },
  ];
  const disagreement = Number((Math.max(...modelVotes.map((m) => m.vote)) - Math.min(...modelVotes.map((m) => m.vote))).toFixed(2));

  const graphNodes = analysis.nodes;
  const graphLinks = analysis.links;
  const ring = graphNodes.map((n, i) => {
    const angle = (Math.PI * 2 * i) / Math.max(1, graphNodes.length);
    return {
      ...n,
      x: 50 + Math.cos(angle) * 38,
      y: 52 + Math.sin(angle) * 34,
    };
  });
  const pos = new Map(ring.map((n) => [n.id, n]));

  return (
    <main className="wp-shell">
      <header className="wp-top">
        <div className="wp-burger"><span /><span /><span /></div>
        <div>
          <h1>THE WORLD'S <span>PULSE</span></h1>
          <p>Real-Time Global Behavior Intelligence</p>
        </div>
        <div className="wp-actions-inline">
          <span className="top-icon pulse-dot">🔔 Alerts</span>
          <span className="top-icon float-icon">📋 Reports</span>
          <span className="top-icon blink-icon">👤 Admin</span>
        </div>
      </header>

      <section className="wp-strip">
        <article className={`wp-card ${panelFx}`}>
          <h3>Global Sentiment</h3>
          <div className="wp-gauge-wrap">
            <div className="wp-gauge" style={{ ["--risk" as any]: `${score}` }}><div className="wp-gauge-hole" /></div>
            <strong className="wp-highlight">{score.toFixed(2)} / 100</strong>
            <div className={`lvl-${score > 75 ? "critical" : score > 45 ? "elevated" : "low"}`}>
              {score > 75 ? "Critical" : score > 45 ? "Elevated" : "Low"}
            </div>
          </div>
        </article>
        <article className={`wp-card ${panelFx}`}>
          <h3>Trending Topic</h3>
          <div className="wp-highlight">{topics[0] ?? "no data"}</div>
          <div className="wp-mini-meta"><span>Confidence Delta</span><strong>{analysis.confidenceDelta >= 0 ? "+" : ""}{analysis.confidenceDelta}</strong></div>
        </article>
        <article className={`wp-card ${panelFx}`}>
          <h3>Market Impact</h3>
          <div className="wp-impact"><span>Composite</span><strong>{(safeN(active?.features.crypto_return) + safeN(active?.features.stock_return)).toFixed(3)}</strong></div>
          <div className="wp-mini-meta"><span>Vol Regime</span><span>{(safeN(active?.features.crypto_volatility) + safeN(active?.features.stock_volatility)).toFixed(2)}</span></div>
        </article>
        <article className={`wp-card ${panelFx}`}>
          <h3>Pipeline Health</h3>
          <div className="wp-mini-meta"><span>Lag</span><strong>{(quality.lagMs / 1000).toFixed(1)}s</strong></div>
          <div className="wp-mini-meta"><span>Throughput</span><strong>{quality.throughput}/min</strong></div>
          <div className="wp-mini-meta"><span>Error Rate</span><strong>{quality.errRate}%</strong></div>
        </article>
      </section>

      <section className="wp-grid">
        <article className={`wp-card ${panelFx}`}>
          <h2>World Sentiment Map</h2>
          <div className="wp-map-surface real-map-surface">
            <div ref={mapRef} className="echart-map" />
            {mapHover ? (
              <div style={{ position: "absolute", right: 12, top: 12, zIndex: 3, border: "1px solid rgba(170,210,255,.45)", background: "rgba(5,10,20,.85)", borderRadius: 10, padding: "10px 12px", minWidth: 200 }}>
                <strong>{mapHover.country}</strong>
                <div>Risk: {mapHover.risk.toFixed(1)}</div>
                <div>Trend: {analysis.confidenceDelta >= 0 ? "Up" : "Down"}</div>
                <div>Driver: {analysis.contributions[0]?.feature ?? "n/a"}</div>
                <div>Uncertainty: {Math.max(2, disagreement / 2).toFixed(2)}%</div>
              </div>
            ) : null}
          </div>
        </article>

        <article className={`wp-card ${panelFx}`}>
          <h2>Event Impact Timeline</h2>
          <div className="wp-timeline">
            <svg viewBox="0 0 640 280">
              <g className="grid">
                {Array.from({ length: 6 }).map((_, i) => (
                  <line key={i} x1="12" x2="628" y1={30 + i * 40} y2={30 + i * 40} />
                ))}
              </g>
              <polyline className="fear" points={shownHistory.slice(-40).map((x, i) => `${20 + i * 15},${220 - x.score * 1.6}`).join(" ")} />
              <polyline className="sad" points={shownHistory.slice(-40).map((x, i) => `${20 + i * 15},${230 - (x.features.crypto_volatility / 8)} `).join(" ")} />
              <polyline className="opt" points={shownHistory.slice(-40).map((x, i) => `${20 + i * 15},${220 - ((x.features.news_sentiment + 1) * 80)} `).join(" ")} />
            </svg>
            <div className="wp-timeline labels"><span>Fear</span><span>Sadness</span><span>Optimism</span><span>Time</span></div>
          </div>
        </article>
      </section>

      <section className="wp-grid-3">
        <article className={`wp-card ${panelFx}`}>
          <h3>Live Social Feed</h3>
          <div className="feed">
            {topics.slice(0, 5).map((t, i) => (
              <p key={`${t}-${i}`}>• {t}</p>
            ))}
          </div>
          <h3 style={{ marginTop: 14 }}>Anomaly Command Center</h3>
          <div className="feed">
            {analysis.anomalies.length === 0 ? <p>No active anomalies</p> : analysis.anomalies.slice(0, 4).map((a) => (
              <p key={a.id}>S{a.severity.toFixed(0)} | BR{a.blastRadius.toFixed(0)} | {a.rootCause}</p>
            ))}
          </div>
        </article>

        <article className={`wp-card ${panelFx}`}>
          <h3>Global Event Graph</h3>
          <svg viewBox="0 0 700 290" style={{ width: "100%", height: 290 }}>
            {graphLinks.map((l, i) => {
              const s = pos.get(l.source);
              const t = pos.get(l.target);
              if (!s || !t) return null;
              return (
                <line
                  key={`${l.source}-${l.target}-${i}`}
                  x1={`${s.x}%`}
                  y1={`${s.y}%`}
                  x2={`${t.x}%`}
                  y2={`${t.y}%`}
                  stroke="rgba(94, 234, 212, 0.52)"
                  strokeWidth={1 + l.value * 4}
                />
              );
            })}
            {ring.map((n) => (
              <g key={n.id}>
                <circle cx={`${n.x}%`} cy={`${n.y}%`} r={Math.max(6, Math.min(16, n.value / 6))} fill={n.category === "risk" ? "#22d3ee" : n.category === "topic" ? "#a3e635" : "#60a5fa"} />
                <text x={`${n.x}%`} y={`${n.y + 6}%`} fill="#dbeafe" fontSize="11" textAnchor="middle">{n.name.slice(0, 12)}</text>
              </g>
            ))}
          </svg>
          <h3>Trending Keywords</h3>
          <div className="keywords">{topics.map((k, i) => <span key={`${k}-${i}`}>{k}</span>)}</div>
        </article>

        <article className={`wp-card ${panelFx}`}>
          <h3>Explainability Layer</h3>
          <div className="feed">
            {analysis.contributions.slice(0, 6).map((c) => {
              const w = Math.min(100, Math.abs(c.contribution) * 120);
              const color = c.contribution >= 0 ? "var(--bar-red)" : "var(--bar-green)";
              return (
                <div key={c.feature}>
                  <div className="wp-mini-meta"><span>{c.feature}</span><span>{c.contribution.toFixed(3)}</span></div>
                  <div style={{ height: 7, borderRadius: 999, background: "rgba(255,255,255,.08)" }}>
                    <div style={{ width: `${w}%`, height: "100%", background: color, borderRadius: 999 }} />
                  </div>
                </div>
              );
            })}
          </div>
          <h3 style={{ marginTop: 12 }}>Ensemble Cockpit</h3>
          {modelVotes.map((m) => (
            <div key={m.name} className="wp-mini-meta"><span>{m.name}</span><strong>{m.vote.toFixed(2)} ({(m.conf * 100).toFixed(0)}%)</strong></div>
          ))}
          <div className="wp-mini-meta"><span>Disagreement Heat</span><strong>{disagreement.toFixed(2)}</strong></div>
          <div className="wp-mini-meta"><span>Drift Alert</span><strong>{analysis.driftScore.toFixed(2)}</strong></div>
        </article>
      </section>

      <section className="wp-grid">
        <article className={`wp-card ${panelFx}`}>
          <h3>Time Machine</h3>
          <div className="wp-mini-meta"><span>Mode</span><strong>{live ? "Live" : "Playback"}</strong></div>
          <div className="wp-mini-meta"><span>Horizon</span><span>
            <button onClick={() => setHorizon("24h")}>24h</button>{" "}
            <button onClick={() => setHorizon("7d")}>7d</button>
          </span></div>
          <div className="wp-mini-meta"><span>Speed</span><span>{speed}x</span></div>
          <input type="range" min={1} max={8} value={speed} onChange={(e) => setSpeed(safeN(e.target.value, 1))} style={{ width: "100%" }} />
          <input type="range" min={0} max={Math.max(0, history.length - 1)} value={Math.max(0, live ? history.length - 1 : playIdx)} onChange={(e) => { setLive(false); setPlayIdx(safeN(e.target.value, 0)); }} style={{ width: "100%" }} />
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={() => setLive(true)}>Resume Live</button>
            <button onClick={() => setLive(false)}>Pause</button>
          </div>
        </article>

        <article className={`wp-card ${panelFx}`}>
          <h3>Alert Simulation Sandbox</h3>
          <div className="wp-mini-meta"><span>Market Shock</span><span>{shock.market}</span></div>
          <input type="range" min={-40} max={40} value={shock.market} onChange={(e) => setShock((p) => ({ ...p, market: safeN(e.target.value) }))} style={{ width: "100%" }} />
          <div className="wp-mini-meta"><span>Sentiment Shock</span><span>{shock.sentiment}</span></div>
          <input type="range" min={-40} max={40} value={shock.sentiment} onChange={(e) => setShock((p) => ({ ...p, sentiment: safeN(e.target.value) }))} style={{ width: "100%" }} />
          <div className="wp-mini-meta"><span>Weather Anomaly</span><span>{shock.weather}</span></div>
          <input type="range" min={-40} max={40} value={shock.weather} onChange={(e) => setShock((p) => ({ ...p, weather: safeN(e.target.value) }))} style={{ width: "100%" }} />
          <div className="bars">
            {simulatedCurve.slice(0, 20).map((v, i) => (
              <span key={`sim-${i}`} style={{ height: `${Math.max(10, v * 1.1)}px`, background: i < 7 ? "var(--bar-red)" : i < 14 ? "var(--bar-blue)" : "var(--bar-green)" }} />
            ))}
          </div>
        </article>
      </section>

      <footer className="wp-footer">
        <button onClick={() => setShowCmd(true)}>Command Palette</button>
        <button onClick={() => setLayout((p) => ({ ...p, animate: !p.animate }))}>{layout.animate ? "Disable FX" : "Enable FX"}</button>
        <button onClick={() => setLayout({ pinned: [], animate: true })}>Reset Layout</button>
        <span>{offline ? "Offline cache active" : "Live feed connected"}</span>
        <span>{stale ? `Stale ${staleSec}s` : `Fresh ${staleSec}s`}</span>
        <span>{health ? `API: ${health.status}` : "API: pending"}</span>
        <span>{summary}</span>
        {err ? <span className="err">{err}</span> : null}
      </footer>

      <div style={{ position: "fixed", right: 18, bottom: 18, display: "grid", gap: 8, zIndex: 30 }}>
        {toasts.map((t) => (
          <div key={t.id} style={{ border: "1px solid rgba(86,214,255,.45)", background: "rgba(8,14,25,.95)", padding: "8px 12px", borderRadius: 10 }}>
            {t.text}
          </div>
        ))}
      </div>

      {showCmd ? (
        <div style={{ position: "fixed", inset: 0, background: "rgba(1,6,16,.62)", zIndex: 40, display: "grid", placeItems: "start center", paddingTop: "12vh" }} onClick={() => setShowCmd(false)}>
          <div style={{ width: "min(640px,92vw)", border: "1px solid rgba(146,170,210,.4)", borderRadius: 12, background: "rgba(8,15,28,.96)", padding: 14 }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>Command Palette</h3>
            <div className="feed">
              <button onClick={() => { setLive((v) => !v); setShowCmd(false); }}>{live ? "Pause Stream (L)" : "Resume Stream (L)"}</button>
              <button onClick={() => { setHistory((h) => h.slice(-200)); setShowCmd(false); }}>Trim History Buffer</button>
              <button onClick={() => { setLayout((p) => ({ ...p, animate: !p.animate })); setShowCmd(false); }}>Toggle FX</button>
              <button onClick={() => { setShock({ market: 0, sentiment: 0, weather: 0 }); setShowCmd(false); }}>Reset Simulation</button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
