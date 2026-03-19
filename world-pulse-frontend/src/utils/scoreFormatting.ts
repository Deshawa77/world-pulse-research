export type ScoreScale = "absolute" | "normalized";

function toFiniteNumber(value: unknown, fallback = 0): number {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

export function toDisplayScore(value: unknown, scale: ScoreScale): number {
  const safe = toFiniteNumber(value);
  if (scale === "absolute") {
    return Math.max(0, Math.min(100, safe));
  }
  const normalized = Math.abs(safe) <= 1.0001 ? safe * 100 : safe;
  return Math.max(0, Math.min(100, normalized));
}

export function formatDisplayScore(value: unknown, scale: ScoreScale): string {
  return `${toDisplayScore(value, scale).toFixed(1)} / 100`;
}
