from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
trend = (ROOT / "world-pulse-frontend" / "src" / "pages" / "TrendPrediction.tsx").read_text()
api = (ROOT / "world-pulse-frontend" / "src" / "services" / "api.ts").read_text()
workflow = (ROOT / ".github" / "workflows" / "deploy-backend.yml").read_text()

def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing {label}: {needle}")

require(api, "feature_snapshot?: AdvancedFeatureSnapshotEntry[];", "advanced insights feature snapshot contract")
require(api, "governance?: GovernanceData;", "advanced insights governance contract")
require(trend, "const canonicalFeatureSnapshot = useMemo", "canonical feature snapshot usage")
require(trend, 'badge: canonicalStatusBadge', "section tab unavailable badge")
require(trend, 'Canonical Refresh', "canonical refresh UI")
require(trend, 'predictionsWithheld ? (advancedInsights?.predictions?.fallback_reason', "withheld history/forecast UX")
require(trend, 'predictionsDegraded && !predictionsWithheld', "degraded chart UX")
require(trend, 'Canonical advanced forecast track', "advanced-forecast-first history subtitle")
if "visiblePredictionLogs" in trend:
    raise SystemExit("prediction history still references visiblePredictionLogs fallback")
require(workflow, "allow_image_tag_override", "manual image override guard")
print("prediction page contract checks passed")
