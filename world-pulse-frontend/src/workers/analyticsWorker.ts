type FeatureSnapshot = {
  timestamp: string;
  score: number;
  topics: string[];
  features: Record<string, number>;
};

type WorkerIn = {
  type: "ANALYZE";
  payload: {
    history: FeatureSnapshot[];
  };
};

type Node = {
  id: string;
  name: string;
  category: string;
  value: number;
};

type Link = {
  source: string;
  target: string;
  value: number;
};

type Contribution = {
  feature: string;
  value: number;
  contribution: number;
};

type Anomaly = {
  id: string;
  severity: number;
  blastRadius: number;
  rootCause: string;
  note: string;
  timestamp: string;
};

type WorkerOut = {
  type: "ANALYSIS_READY";
  payload: {
    nodes: Node[];
    links: Link[];
    contributions: Contribution[];
    confidenceDelta: number;
    anomalies: Anomaly[];
    driftScore: number;
  };
};

const FEATURE_WEIGHTS: Record<string, number> = {
  news_sentiment: -0.24,
  gdelt_sentiment: -0.18,
  crypto_return: -0.10,
  crypto_volatility: 0.28,
  stock_return: -0.12,
  stock_volatility: 0.26,
  weather_anomaly: 0.10,
};

function safeN(value: unknown, fallback = 0): number {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return n;
}

function buildGraph(history: FeatureSnapshot[]) {
  const topicCounts = new Map<string, number>();
  for (const row of history.slice(-50)) {
    for (const topic of row.topics.slice(0, 6)) {
      topicCounts.set(topic, (topicCounts.get(topic) ?? 0) + 1);
    }
  }

  const topTopics = [...topicCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([name, count]) => ({ name, count }));

  const nodes: Node[] = [
    { id: "risk", name: "Global Risk", category: "risk", value: 100 },
    { id: "market", name: "Markets", category: "domain", value: 70 },
    { id: "news", name: "News", category: "domain", value: 65 },
    { id: "region", name: "Regions", category: "domain", value: 55 },
  ];

  const links: Link[] = [
    { source: "risk", target: "market", value: 0.7 },
    { source: "risk", target: "news", value: 0.8 },
    { source: "risk", target: "region", value: 0.5 },
  ];

  for (const t of topTopics) {
    const id = `topic:${t.name}`;
    nodes.push({ id, name: t.name, category: "topic", value: 20 + t.count * 5 });
    links.push({ source: "news", target: id, value: Math.min(1, t.count / 12) });
    links.push({ source: "risk", target: id, value: Math.min(1, t.count / 14) });
  }

  return { nodes, links };
}

function computeContributions(latest: FeatureSnapshot) {
  const contributions: Contribution[] = Object.entries(FEATURE_WEIGHTS).map(([feature, weight]) => {
    const value = safeN(latest.features[feature], 0);
    return {
      feature,
      value,
      contribution: Number((value * weight).toFixed(4)),
    };
  });
  contributions.sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  return contributions;
}

function computeConfidenceDelta(history: FeatureSnapshot[]) {
  if (history.length < 3) return 0;
  const tail = history.slice(-6).map((x) => x.score);
  const avg = tail.reduce((s, x) => s + x, 0) / tail.length;
  const last = tail[tail.length - 1];
  return Number((last - avg).toFixed(2));
}

function computeDrift(history: FeatureSnapshot[]) {
  if (history.length < 12) return 0;
  const a = history.slice(-12, -6).map((x) => x.score);
  const b = history.slice(-6).map((x) => x.score);
  const avgA = a.reduce((s, x) => s + x, 0) / a.length;
  const avgB = b.reduce((s, x) => s + x, 0) / b.length;
  return Number(Math.abs(avgB - avgA).toFixed(2));
}

function computeAnomalies(history: FeatureSnapshot[]) {
  const rows = history.slice(-30);
  if (rows.length < 6) return [] as Anomaly[];

  const anomalies: Anomaly[] = [];
  for (let i = 1; i < rows.length; i++) {
    const prev = rows[i - 1];
    const cur = rows[i];
    const delta = Math.abs(cur.score - prev.score);
    if (delta < 6) continue;
    const rootCause =
      Math.abs((cur.features.crypto_volatility ?? 0) - (prev.features.crypto_volatility ?? 0)) >
      Math.abs((cur.features.stock_volatility ?? 0) - (prev.features.stock_volatility ?? 0))
        ? "Crypto volatility spike"
        : "Equity volatility regime shift";
    anomalies.push({
      id: `${cur.timestamp}-${i}`,
      severity: Number(Math.min(100, delta * 6).toFixed(1)),
      blastRadius: Number(Math.min(100, 35 + delta * 4).toFixed(1)),
      rootCause,
      note: `Risk jumped by ${delta.toFixed(2)} points`,
      timestamp: cur.timestamp,
    });
  }
  anomalies.sort((a, b) => b.severity - a.severity);
  return anomalies.slice(0, 8);
}

self.onmessage = (evt: MessageEvent<WorkerIn>) => {
  if (evt.data?.type !== "ANALYZE") return;
  const history = evt.data.payload?.history ?? [];
  if (!history.length) return;
  const latest = history[history.length - 1];
  const { nodes, links } = buildGraph(history);
  const contributions = computeContributions(latest);
  const confidenceDelta = computeConfidenceDelta(history);
  const anomalies = computeAnomalies(history);
  const driftScore = computeDrift(history);

  const out: WorkerOut = {
    type: "ANALYSIS_READY",
    payload: {
      nodes,
      links,
      contributions,
      confidenceDelta,
      anomalies,
      driftScore,
    },
  };
  self.postMessage(out);
};

