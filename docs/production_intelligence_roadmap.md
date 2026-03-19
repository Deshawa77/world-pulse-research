# Production Intelligence Roadmap

## Status

Implementation status: complete on code and schema wiring.

Completed outcomes:
- Sprint 1 completed: signal taxonomy, deeper ranked multilingual country news, preserved language metadata, normalized taxonomy persistence.
- Sprint 2 completed: `direct_behavior_score`, `contextual_pressure_score`, and `evidence_quality_score` flow through batch, incremental, API, and UI.
- Sprint 3 completed: free-access social and messaging layer added with Telegram public channels, YouTube public trend feeds, narrative velocity, and coordination risk.
- Sprint 4 completed: mobility layer now includes UNHCR displacement, OpenSky aviation, and World Bank-backed logistics stress.
- Sprint 5 completed: economic behavior now includes household, labor, fuel, food, FX, remittance, and energy stress; global behavior/context indices were added to global processing outputs.
- Sprint 6 completed: trust layer exposes domain freshness, source health, mobility/economic observability, operational alerts, and UI evidence-density/domain-health views.

## Sprint 1: Signal Taxonomy + Country News Depth

Goal: establish a durable ingestion schema and stop relying on shallow, early-stop country news pulls.

Implemented files:
- `processing/signal_taxonomy.py`
- `collectors/country_news.py`
- `backend/country_risk_stream.py`

Delivered:
- reusable signal metadata helpers and source classifications
- `direct` vs `contextual` classification with domain/type/tier tags
- deeper country-news candidate pools with ranking instead of first-hit stopping
- preserved original language and translated English fields
- taxonomy fields persisted on normalized `country_source_events`

## Sprint 2: Country Feature Split

Goal: separate direct behavior from contextual pressure in country features.

Implemented files:
- `processing/country_signal_fusion.py`
- `processing/country_daily_risk.py`
- `processing/country_incremental_risk.py`
- `backend/main.py`
- `world-pulse-frontend/src/services/api.ts`

Delivered:
- `direct_behavior_score`
- `contextual_pressure_score`
- `evidence_quality_score`
- backward-compatible `global_risk_score`
- risk-map and drilldown API exposure

## Sprint 3: Social + Messaging Expansion

Goal: replace fragile Reddit dependence with broader free-access public attention signals.

Implemented files:
- `collectors/telegram_public.py`
- `collectors/youtube_trends.py`
- `collectors/wiki.py`
- `processing/country_signal_fusion.py`
- `backend/country_risk_stream.py`
- `orchestrator.py`

Delivered:
- Telegram public-channel ingestion where configured
- YouTube public feed trend ingestion where configured
- normalized shared social schema
- `narrative_velocity_score`
- `coordination_risk_score`
- stronger public-attention mix beyond Reddit

## Sprint 4: Mobility / Transport / Logistics

Goal: add real-world movement signals.

Implemented files:
- `collectors/unhcr.py`
- `collectors/opensky.py`
- `collectors/logistics.py`
- `collectors/mobility.py`
- `collectors/aviation.py`
- `processing/country_signal_fusion.py`
- `processing/country_daily_risk.py`
- `backend/country_risk_stream.py`
- `orchestrator.py`

Delivered:
- displacement ingestion
- flight disruption ingestion
- logistics stress ingestion
- country mobility and logistics stress features
- mobility observability and cross-checking

## Sprint 5: Economic Behavior Beyond Markets

Goal: track household and operational stress, not just financial proxies.

Implemented files:
- `collectors/worldbank_behavior.py`
- `collectors/energy_stress.py`
- `collectors/economic_behavior.py`
- `processing/daily_feature_builder.py`
- `processing/global_mood.py`
- `processing/country_daily_risk.py`
- `backend/main.py`
- `world-pulse-frontend/src/services/api.ts`
- `world-pulse-frontend/src/components/CountryDrilldown.tsx`
- `world-pulse-frontend/src/components/PriorityWatchlist.tsx`
- `world-pulse-frontend/src/pages/Dashboard.tsx`

Delivered:
- price, labor, remittance, energy, FX, and household-stress proxies
- separate country features for `fuel_price_pressure`, `food_price_pressure`, `labor_stress_score`, `fx_pressure_score`, `remittance_stress_score`, `energy_stress_score`, and `household_stress_score`
- global behavior/context/attention/disruption/economic indices

## Sprint 6: Validation and Trust Layers

Goal: give the system domain-level coverage, freshness, and confidence metrics.

Implemented files:
- `processing/world_state_quality.py`
- `backend/main.py`
- `world-pulse-frontend/src/components/SignalIntegrityBoard.tsx`
- `world-pulse-frontend/src/pages/Dashboard.tsx`
- `world-pulse-frontend/src/pages/SystemMonitoring.tsx`

Delivered:
- per-domain freshness and source-health thresholds
- mobility and economic observability snapshots
- operational alerts for stale, down, rate-limited, and coverage-drop conditions
- domain health and evidence-density UI surfaces

## Validation

Latest implementation validation completed successfully:
- `python -m py_compile collectors/opensky.py collectors/unhcr.py collectors/worldbank_behavior.py collectors/energy_stress.py collectors/logistics.py collectors/telegram_public.py collectors/youtube_trends.py collectors/economic_behavior.py processing/signal_taxonomy.py processing/country_signal_fusion.py processing/country_daily_risk.py processing/country_incremental_risk.py processing/daily_feature_builder.py processing/global_mood.py backend/country_risk_stream.py backend/main.py orchestrator.py`
- `npx --prefix world-pulse-frontend tsc --noEmit -p world-pulse-frontend/tsconfig.app.json`
