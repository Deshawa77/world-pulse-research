from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend" / "main.py"
FRONTEND_API = REPO_ROOT / "world-pulse-frontend" / "src" / "services" / "api.ts"
WATCHLIST = REPO_ROOT / "world-pulse-frontend" / "src" / "components" / "PriorityWatchlist.tsx"

REQUIRED_BACKEND_SNIPPETS = [
    '@app.get("/country-intelligence/latest")',
    '@app.get("/country-intelligence/{country}")',
    '"display_risk"',
    '"raw_risk_score"',
    '"confidence_score"',
    '"gating_action"',
    'COUNTRY_INTELLIGENCE_SCORE_SEMANTICS',
]

REQUIRED_FRONTEND_SNIPPETS = [
    'API.get("/country-intelligence/latest"',
    'API.get(`/country-intelligence/${country}`',
    'display_risk',
    'raw_risk_score',
    'confidence_score',
    'gating_action',
]

REQUIRED_WATCHLIST_SNIPPETS = [
    'row.gating_action !== "suppress"',
    'row.confidence_score',
    'row.risk_band',
]

DISALLOWED_FRONTEND_SNIPPETS = [
    'confidenceInterval: { lower: Math.max(Number(base.risk || 0) - 0.08, 0), upper: Math.min(Number(base.risk || 0) + 0.08, 1) }',
    'API.get("/dashboard/risk-map"',
    'API.get(`/dashboard/country/${country}`',
]


def _assert_contains(content: str, snippets: list[str], label: str) -> list[str]:
    errors: list[str] = []
    for snippet in snippets:
        if snippet not in content:
            errors.append(f"Missing {label} snippet: {snippet}")
    return errors


def _assert_not_contains(content: str, snippets: list[str], label: str) -> list[str]:
    errors: list[str] = []
    for snippet in snippets:
        if snippet in content:
            errors.append(f"Unexpected {label} snippet still present: {snippet}")
    return errors


def main() -> int:
    backend_text = BACKEND.read_text(encoding="utf-8")
    frontend_text = FRONTEND_API.read_text(encoding="utf-8")
    watchlist_text = WATCHLIST.read_text(encoding="utf-8")

    errors: list[str] = []
    errors.extend(_assert_contains(backend_text, REQUIRED_BACKEND_SNIPPETS, "backend"))
    errors.extend(_assert_contains(frontend_text, REQUIRED_FRONTEND_SNIPPETS, "frontend API"))
    errors.extend(_assert_contains(watchlist_text, REQUIRED_WATCHLIST_SNIPPETS, "watchlist"))
    errors.extend(_assert_not_contains(frontend_text, DISALLOWED_FRONTEND_SNIPPETS, "frontend API legacy"))

    if errors:
        print("Country intelligence contract regression detected:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Country intelligence contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
