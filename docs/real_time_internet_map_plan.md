# Real-Time Internet Map Plan

## Status

Implementation status: code-complete in repo and production-activation ready.

This implementation now includes:
- a dedicated protected backend snapshot endpoint and cached serving path for the internet-map surface
- a separate protected frontend page with a real projected world map, country hubs, corridor arcs, map-driven country focus, corridor pinning, source filters, and world-vs-regional focus modes
- replay history, playback frames, scrub controls, live-vs-replay mode switching, and follow-live-focus behavior on the map itself
- persistence collections plus file-backed replay history for internet-map snapshots, normalized events, alerts, and source health
- SSE stream delivery, runtime scheduler/status, queued refresh cycles, and warm-cache snapshot serving
- operator alert workflows for acknowledge, snooze, assign, false-positive, escalation routing, team queues, SLA timers, and audit reporting
- BGP, CDN, ISP, and cloud collector families with direct-event normalization, auth headers, retry handling, rate-limit posture, cache reuse, and fixture-or-provider URL loading
- backtests, replay analytics, retention maintenance, provenance labeling, observability payloads, and deployment-secret loading via environment or local runtime secret files

External activation note:
- provider credentials, production endpoints, and secret-manager attachment are deployment concerns and are intentionally not stored in this repository
- the collectors are implemented and ready for authenticated provider cutover, but this repo ships with local fixtures and env-configurable export URLs instead of bundled third-party credentials

Completion definition for this plan:
- all application, API, storage, replay, operations, and map UX work described below is implemented in the repository
- remaining production work is environment activation, credential attachment, and deployment tuning rather than missing feature code

## Product Goal

Create a Real-Time Internet Map that shows how data moves across the planet every second and supports four operator workflows:
- global internet congestion monitoring
- cyber attack detection
- country internet shutdown alerts
- packet-flow corridor visualization

## Production Capability Target

### Required data-source families

- BGP routing tables and update streams for prefix churn, route instability, hijack heuristics, and reroute pressure
- CDN traffic telemetry for edge load, cache stress, regional latency drift, and packet-loss proxies
- ISP telemetry for last-mile degradation, regional outages, mobile-vs-fixed divergence, and subscriber-impact estimates
- cloud provider metrics for backbone saturation, region-level egress anomalies, control-plane incidents, and DNS/API degradation

### Required platform traits

- sub-minute ingestion for hot-path signals
- country and corridor snapshots with explicit freshness metadata
- confidence and provenance on every alertable metric
- operator-safe degradation when one or more source families are stale or unavailable
- historical persistence for replay, backtesting, and post-incident review

## Architecture

### Ingestion layer

- `collectors/bgp_*` family:
  route updates, withdrawals, prefix announcements, AS-path churn, hijack suspicion, and blackout indicators
- `collectors/cdn_*` family:
  request volume, regional latency, cache miss spikes, POP saturation, and error-rate anomalies
- `collectors/isp_*` family:
  subscriber outage reports, fixed/mobile health, throughput degradation, packet loss, and shutdown signatures
- `collectors/cloud_*` family:
  region health, egress saturation, DNS/API incidents, and backbone impairment signals
- collectors support authenticated HTTP pulls plus local/export fixtures, with retry, timeout, cache, and rate-limit metadata captured per source family

### Normalization layer

- normalize all collectors to a shared event schema with:
  `source_family`, `source_name`, `country`, `region`, `asn`, `prefix`, `timestamp`, `freshness_sec`, `metric_name`, `metric_value`, `confidence_ratio`, `raw_payload_ref`
- store raw and normalized events separately so replay and reprocessing stay possible

### Feature layer

- aggregate internet events into:
  country snapshots
  corridor snapshots
  threat events
  shutdown alerts
  source-health summaries
- expose explicit derived fields such as:
  `congestion_index`
  `attack_index`
  `shutdown_risk`
  `packet_flow_gbps`
  `packet_loss_pct`
  `reroute_factor`
  `confidence_ratio`
- enrich alerts with assignment, escalation, SLA, false-positive, and audit metadata for operator workflows

### Serving layer

- snapshot API for fast protected dashboard reads
- websocket or SSE stream for incremental updates after the snapshot load
- cache recent snapshots for low latency and to protect expensive upstream collectors
- preserve historical snapshots for replay, backtesting, and future modeling
- expose dedicated history, playback, backtest, stream-status, alert-action, and maintenance-aware runtime surfaces

### Frontend layer

- dedicated `/internet-map` route in the console
- projected world-stage visualization for hubs and corridors
- alert boards for shutdowns and attacks
- source-health strip so operators can judge data trust before acting
- replay scrubber, source-family filters, corridor box/lasso selection, corridor pinning, and live-focus follow behavior on the map

## Data Model

### Collections / tables

- `internet_raw_events`
- `internet_normalized_events`
- `internet_country_snapshots`
- `internet_flow_snapshots`
- `internet_alerts`
- `internet_source_health`

### Snapshot contract

`GET /dashboard/internet-map`

Response families:
- `summary`
- `source_health`
- `countries`
- `flows`
- `cyber_attacks`
- `shutdown_alerts`
- `top_corridors`
- `generated_from`
- `governance`
- `observability`
- `runtime_status`
- `ops_reporting`
- `replay_analytics`

Every entity should include:
- `generated_at`
- `mode`
- `data_quality` or `stage`
- `confidence_ratio`
- `freshness_sec`

Phase 1 decision:
- include the `internet_*` persistence collections now so replay, operator actions, provenance, and validation do not depend on a later schema migration

Additional routes:
- `GET /dashboard/internet-map/history`
- `GET /dashboard/internet-map/playback`
- `GET /dashboard/internet-map/backtest`
- `GET /api/internet-map/stream/status`
- `GET /api/internet-map/alerts/stream`
- `POST /api/internet-map/alerts/action`
- `POST /api/internet-map/stream/run-cycle`
- `POST /api/internet-map/backtests/run`

## Rollout Plan

## Phase 1: Derived operational surface

Status: complete.

Goal: ship the feature shell now using existing World Pulse signals so the system has a usable page, API, and UX while direct connectors are built.

Deliver:
- backend snapshot builder derived from current country intelligence
- protected `/internet-map` page
- projected map nodes, corridor flows, shutdown alert list, and cyber attack list
- source-health cards labeled by stage and freshness
- persistence collections for raw events, normalized events, snapshots, alerts, and source health
- replay history and stream status endpoints
- SSE delivery for live frontend updates
- operator acknowledge, snooze, assign, false-positive, and escalate actions on internet alerts
- governance and observability payloads for freshness, provenance, and SLO posture
- browser smoke, unit coverage, and contract validation

Files:
- `backend/internet_map.py`
- `backend/internet_map_ops.py`
- `backend/internet_map_streaming.py`
- `backend/main.py`
- `processing/internet_map_storage.py`
- `world-pulse-frontend/src/services/api.ts`
- `world-pulse-frontend/src/components/ConsoleNavigation.tsx`
- `world-pulse-frontend/src/App.tsx`
- `world-pulse-frontend/src/pages/InternetMap.tsx`
- `world-pulse-frontend/src/pages/InternetMap.css`
- `tests/test_internet_map.py`
- `scripts/check_internet_map_contract.py`
- `scripts/check_internet_map_browser_smoke.mjs`

## Phase 2: Direct BGP integration

Status: implemented in code; production provider credential attachment is environment-specific.

Goal: replace route-instability proxies with direct routing telemetry.

Deliver:
- BGP collector(s)
- normalized AS-path and prefix update events
- direct reroute and hijack pressure metrics
- route-withdrawal and announcement anomaly alerts
- authenticated source loading, retry posture, cache reuse, and runtime scheduling hooks for BGP feeds

## Phase 3: CDN + edge traffic integration

Status: implemented in code; production provider credential attachment is environment-specific.

Goal: make congestion and latency metrics operationally real, not derived.

Deliver:
- POP-level traffic and latency ingestion
- corridor throughput baselines
- regional congestion nowcasting
- packet-loss and edge error anomaly surfacing
- authenticated source loading, retry posture, cache reuse, and runtime scheduling hooks for CDN feeds

## Phase 4: ISP + cloud health integration

Status: implemented in code; production provider credential attachment is environment-specific.

Goal: support shutdown detection and backbone impairment triage with stronger corroboration.

Deliver:
- fixed/mobile subscriber health signals
- cloud region and backbone health overlays
- stronger country shutdown heuristics with confidence bands
- estimated impacted users and service-category disruption
- authenticated source loading, retry posture, cache reuse, and runtime scheduling hooks for ISP and cloud feeds

## Phase 5: Streaming, persistence, and operator actions

Status: complete.

Goal: move from a polling-only feature to an operator-grade incident surface.

Deliver:
- websocket or SSE delta stream
- persistent internet alert timelines
- operator acknowledge, snooze, assign, false-positive, and escalate actions
- replay mode for incident review and model tuning
- backtests, retention jobs, queue routing, SLA timers, and audit/reporting views
- projected world-map playback, corridor filters, and map-driven alert triage

## Alerting Logic

### Congestion

- trigger when corridor congestion stays above threshold for multiple consecutive windows
- require corroboration from at least two source families once live multi-family provider feeds are attached
- expose packet loss, latency drift, throughput delta, and confidence together

### Cyber attack detection

- combine traffic asymmetry, route instability, control-plane anomalies, and edge saturation
- separate volumetric attacks from routing abuse and DNS/control-plane incidents
- expose affected countries, corridors, suspected vector, and confidence

### Shutdown alerts

- watch for route withdrawals, subscriber collapse, mobile/fixed divergence, and service-denial patterns
- score by duration, national concentration, and corroborating source families
- expose operator-safe wording until confidence exceeds escalation threshold

## Observability and SLOs

- ingestion freshness per source family
- collector success/error/rate-limit counts
- snapshot build latency and cache hit ratio
- websocket/SSE delivery health
- alert precision and operator feedback outcomes

Initial SLO targets:
- snapshot API p95 under 800 ms from warm cache
- hot-path freshness under 60 seconds for live connectors
- source-health dashboard updated every refresh cycle
- alert delivery within one refresh cycle of threshold breach

## Security and Governance

- keep the route behind the existing protected-role checks
- label every source family with stage and freshness
- preserve raw-payload references for audit, but do not expose sensitive raw telemetry to the browser
- apply rate limits consistent with other dashboard surfaces
- treat shutdown alerts as confidence-scored intelligence, not confirmed public claims, until corroborated
- prefer deployment environment variables or local runtime-secret files over checked-in development `.env` values

## Validation Plan

Implemented validation now includes:
- backend unit coverage for snapshot builder, collector bundle behavior, queue defaults, and retention policy
- contract tests for snapshot shape, history, playback, stream status, backtest, governance, retention, and alert actions
- frontend type-check and browser smoke coverage for rendering, country focus, operator actions, replay mode, filtering, and corridor pinning
- replay-backed analytics and stored incident-window backtests

## Post-Completion Activation Checklist

- attach production provider credentials and endpoints through deployment env or secret-manager wiring
- rotate any development secrets if they were ever shared outside the trusted environment
- tune thresholds against live provider traffic once real feeds are attached
- calibrate cold-cycle latency and scheduler cadence against the target deployment footprint

## Activation Assets Shipped In Repo

- `config/runtime-secrets.example.json`
- `config/internet-map-thresholds.example.json`
- `docs/internet_map_production_activation.md`
- `scripts/rotate_runtime_secrets.py`
- `scripts/check_internet_map_provider_config.py`
- `scripts/run_internet_map_rollout_checks.py`
- `scripts/tune_internet_map_thresholds.py`
- `deploy/internet-map.docker-compose.example.yml`
