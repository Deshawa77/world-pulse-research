# PUSL2021 Computing Group Project  
## Final Report Draft  

**Project Title:** World Pulse: A Real-Time Global Crisis Intelligence and Risk Forecasting Platform  
**Group Number:** _[Insert Group Number]_  
**Academic Year:** 2025/2026  
**Submitted On:** 16 March 2026  
**Word Count (Main Body Only):** _[To be finalized during Word export]_  

---

## Acknowledgements
The project team acknowledged the supervision, academic guidance, and technical feedback provided throughout the development lifecycle. Appreciation was extended to institutional resources that supported experimentation in data engineering, machine learning, and full-stack implementation. Gratitude was also extended to open-data providers and open-source communities whose tooling and APIs enabled the construction and evaluation of the platform.

---

## Abstract
This project addressed the problem of fragmented, delayed, and domain-isolated crisis signals by developing a unified real-time intelligence platform for global risk monitoring. The objective was to ingest heterogeneous geopolitical, economic, environmental, health, and social data streams, transform them into operational features, and provide interpretable risk analytics for analysts and decision-makers.

An iterative engineering approach was applied using Python-based data pipelines, Kafka-based streaming, MongoDB persistence, FastAPI service orchestration, and a React/TypeScript operational dashboard. The system integrated multi-source collectors, country-level and global risk scoring, causal explanation workflows, scenario simulation, policy replay, and administrative observability functions.

Validation and operational checks showed that the platform achieved complete labeled country-risk validation accuracy on the currently available benchmark sample (7/7 records on 16 March 2026), with weighted Brier score 0.0329 in rolling backtest mode over available labeled days. The project concluded that the architecture successfully demonstrated end-to-end crisis intelligence capabilities, while highlighting the need for larger global mood ground-truth datasets, stronger source-health robustness, and sustained production validation.

---

## Table of Contents
1. Chapter 01 – Introduction  
2. Chapter 02 – Literature Review  
3. Chapter 03 – System Analysis  
4. Chapter 04 – Requirements Specification  
5. Chapter 05 – System Architecture  
6. Chapter 06 – Method of Approach / Methodology  
7. Chapter 07 – System Testing and Quality Assurance  
8. Conclusions  
9. Team Plan & Responsibility Matrix  
10. Reference List  
11. Appendices

---

## List of Figures and Tables
**Figures (to be generated in Word export):**  
Figure 5.1 High-Level Data Flow Architecture  
Figure 5.2 Backend Service Layer Architecture  
Figure 5.3 Frontend Route and Interaction Structure  
Figure 6.1 Iterative Delivery Timeline  

**Tables:**  
Table 3.1 Stakeholder Analysis  
Table 3.2 Feasibility Assessment  
Table 3.3 SWOT Analysis  
Table 3.4 Project Risk Register  
Table 4.1 Functional Requirements  
Table 4.2 Non-Functional Requirements  
Table 5.1 Core Collections and Data Entities  
Table 7.1 Test Evidence Summary  
Table 9.1–9.4 Individual Responsibility Matrices

---

# Chapter 01 – Introduction

## 1.1 Background
Global risk signals had increasingly emerged from multiple domains, including financial volatility, geopolitical incidents, disaster streams, social discourse, and public-health alerts. In many monitoring contexts, these signals had been processed independently, resulting in delayed interpretation and weak cross-domain situational awareness. A unified operational intelligence layer was therefore required to combine heterogeneous feeds into explainable risk indicators.

The World Pulse project was developed to address this gap through a full-stack crisis intelligence platform with near-real-time ingestion, feature generation, risk scoring, governance telemetry, and decision-support interaction.

## 1.2 Problem Statement
Existing crisis monitoring workflows lacked a continuously updated, integrated, and explainable mechanism to convert distributed multi-domain signals into country-level and global risk assessments usable by operational analysts.

## 1.3 Aim
The aim of the project was to design and implement a secure, scalable, and explainable real-time crisis intelligence system that fused diverse external data streams into actionable risk analytics.

## 1.4 Objectives
The following measurable objectives were defined and implemented:

1. To integrate multi-domain streaming and batch data collectors into a unified ingestion pipeline.
2. To engineer global and country-level feature sets for model-ready crisis scoring.
3. To implement risk scoring, trend analysis, and advanced analytics endpoints in a secured API layer.
4. To deliver an interactive role-aware frontend for situational awareness, investigation, and scenario analysis.
5. To implement observability, validation, and backtesting pathways for reliability and governance reporting.

## 1.5 Scope
The implemented scope included:

1. Data ingestion from news, GDELT, Wikipedia, Google Trends, USGS, weather, WHO, financial, crypto, and world-state sources.
2. Kafka-assisted event streaming and MongoDB-based persistence.
3. Country and global risk feature pipelines and model inference.
4. Dashboarding for risk map, intelligence feed, disasters, economic indicators, health alerts, and trends radar.
5. Authentication, role-based access control, admin monitoring, and security event logging.

Out-of-scope or partially scoped elements included:

1. Full external-source key provisioning for all optional collectors.
2. Large-scale global mood labeled dataset curation.
3. Hard production deployment architecture (container orchestration and cloud infrastructure automation).

## 1.6 Report Structure
This report was structured according to the required final-report sequence. Chapter 02 reviewed relevant theory and technologies. Chapter 03 analyzed feasibility, stakeholders, and strategic factors. Chapter 04 specified functional and non-functional requirements. Chapter 05 described architecture and component design. Chapter 06 documented methodology enactment. Chapter 07 presented test evidence and QA outcomes. The report ended with conclusions, responsibility matrices, references, and appendices.

---

# Chapter 02 – Literature Review

## 2.1 Real-Time Stream Processing for Situational Intelligence
Modern event-driven analytics platforms were commonly built on distributed log architectures to decouple data producers and downstream consumers. Apache Kafka had become a standard approach for fault-tolerant ingestion and replayable event streams (Apache Software Foundation, n.d.). For multi-source crisis analytics, this model supported resilient fan-out to preprocessing, feature engineering, and model consumers without tight coupling.

## 2.2 Document Stores for Heterogeneous Operational Data
Crisis intelligence pipelines generally combined structured and semi-structured payloads with evolving schemas. Document-oriented storage offered flexibility for varied source payloads and nested analytical fields. MongoDB documentation emphasized this schema-flexibility advantage for event-like operational records and rapid iteration (MongoDB, n.d.). This pattern aligned with the project requirement to persist heterogeneous source documents and derived features.

## 2.3 API-Centric Service Design
FastAPI and related ASGI tooling had provided high-performance Python API development with schema validation and async support (FastAPI, n.d.). This service model was appropriate for secure endpoint-rich intelligence systems where authentication, typed requests, and operational health checks were required.

## 2.4 Machine Learning and Risk Scoring Foundations
Supervised ensemble models and logistic baselines had remained practical options for operational tabular risk scoring due to interpretability and stable inference behavior (Pedregosa et al., 2011). In addition, sequence-oriented forecasting models and anomaly detection routines had improved early warning capability under temporal drift conditions.

## 2.5 Sentiment and NLP in Crisis Contexts
Lexicon-driven social sentiment methods, including VADER, were widely adopted for noisy short text and social channels (Hutto and Gilbert, 2014). Topic extraction and latent-structure approaches, such as probabilistic topic modeling, had supported thematic trend identification in large corpora (Blei, Ng and Jordan, 2003). In crisis intelligence systems, these methods were typically combined with heuristic quality filters and multilingual preprocessing.

## 2.6 Causal and Decision-Support Analytics
Operational risk analytics had increasingly required not only prediction but explanation and intervention simulation. Causal reasoning frameworks provided the conceptual basis for root-cause mapping and policy counterfactual evaluation (Pearl, 2009). In applied systems, simplified causal-weight heuristics were frequently used where complete causal identification was impractical due to sparse intervention data.

## 2.7 Comparative Assessment for This Project
The reviewed approaches suggested that an integrated design should combine:

1. Stream ingestion and replayability.
2. Flexible document persistence.
3. ML plus rule-informed analytics.
4. Explainability and intervention simulation.
5. Operational governance and reliability telemetry.

These findings directly informed the implemented architecture and module decomposition of World Pulse.

---

# Chapter 03 – System Analysis

## 3.1 Current Situation Analysis
Prior to integration, relevant risk signals were dispersed across unrelated platforms, each with distinct update cadences and schemas. Manual synthesis would have produced inconsistent interpretation latency and weak reproducibility. The implemented system addressed this by consolidating collection, processing, scoring, and visualization under one operational stack.

## 3.2 Stakeholder Analysis
Table 3.1 summarized principal stakeholders.

| Stakeholder | Interest | Influence | System Need |
|---|---|---|---|
| Operational Analyst | High | High | Reliable live risk and drilldown evidence |
| Policy Planner | High | Medium | Scenario and policy replay support |
| Academic Supervisor | High | High | Methodological rigor and traceable validation |
| System Administrator | Medium | High | Monitoring, logs, access control |
| End Users (Researchers/Students) | Medium | Medium | Usable dashboard and historical analytics |

## 3.3 Feasibility Study
Table 3.2 summarized feasibility dimensions.

| Dimension | Assessment |
|---|---|
| Technical | Feasible; Python/FastAPI/React/Kafka/MongoDB stack was implemented with 93 backend routes and 15 frontend routes. |
| Economic | Feasible for academic scope; many sources were free/open tiers. Cost exposure remained mainly in optional premium APIs. |
| Operational | Feasible; scripts and health endpoints supported startup, monitoring, and validation routines. |
| Legal/Ethical | Conditionally feasible; compliance depended on API terms, key governance, and data-use restrictions per provider. |

## 3.4 SWOT Analysis
Table 3.3 presented strategic analysis.

| Category | Findings |
|---|---|
| Strengths | Full-stack integration, rich endpoint coverage, role-based access, observability and validation modules. |
| Weaknesses | Uneven source reliability, partial external-key dependence, sparse global mood labels, stale coverage exposure. |
| Opportunities | Broader multilingual ground truth, stronger causal calibration, cloud deployment hardening, richer UAT evidence. |
| Threats | API policy/rate-limit changes, upstream outages, model drift under geopolitical regime shifts. |

## 3.5 Risk Analysis
Table 3.4 summarized key project risks.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| External API downtime | High | High | Multi-source fallback, source-health telemetry, cached responses |
| Data staleness | Medium | High | Freshness gating, coverage metrics, scheduled refresh scripts |
| Validation data scarcity | High | High | Ground-truth expansion plan, staged backtesting, confidence reporting |
| Security exposure | Medium | High | API-key/JWT checks, role controls, security event logs |
| Model drift | Medium | Medium | Monitoring summaries, periodic retraining and validation scripts |

---

# Chapter 04 – Requirements Specification

## 4.1 Functional Requirements
Table 4.1 listed principal functional requirements.

| ID | Requirement |
|---|---|
| FR-01 | The system shall ingest multi-source crisis-related data from configured collectors. |
| FR-02 | The system shall stream collector outputs through Kafka topics for asynchronous processing. |
| FR-03 | The system shall persist raw and processed records in MongoDB collections. |
| FR-04 | The system shall compute hourly global operational features from recent source data. |
| FR-05 | The system shall compute country-level risk features with source fusion and topic extraction. |
| FR-06 | The system shall expose latest and historical global features through API endpoints. |
| FR-07 | The system shall expose latest country features and versioned history by country code. |
| FR-08 | The system shall provide live dashboard feed data including heartbeat and drift indicators. |
| FR-09 | The system shall provide a country risk-map endpoint with quality flags and coverage metrics. |
| FR-10 | The system shall provide country drilldown analytics including trend and driver summaries. |
| FR-11 | The system shall provide causal explanation payloads for global or country scope. |
| FR-12 | The system shall provide counterfactual scenario simulation for feature shocks. |
| FR-13 | The system shall provide action-plan recommendations based on dominant risk drivers. |
| FR-14 | The system shall provide policy replay simulations over selected intervention sets. |
| FR-15 | The system shall provide advanced analytics endpoints for predictions, anomalies, causal links, reports, and momentum. |
| FR-16 | The system shall provide Sentinel intelligence endpoints and websocket streams. |
| FR-17 | The system shall support user registration, login, profile update, and password management. |
| FR-18 | The system shall enforce role-aware access for admin-only endpoints. |
| FR-19 | The system shall provide administrative user management (status/access updates). |
| FR-20 | The system shall provide observability endpoints for runtime, model, streaming, validation, and world-state telemetry. |
| FR-21 | The system shall provide trust/reliability snapshots with freshness and validation summaries. |
| FR-22 | The frontend shall provide protected routes for authenticated dashboard and analytics pages. |
| FR-23 | The frontend shall provide admin routes for monitoring and security log inspection. |
| FR-24 | The frontend shall visualize risk, events, trends, and domain feeds in near-real-time panels. |
| FR-25 | The system shall support export of analytics history in JSON/CSV formats. |

## 4.2 Non-Functional Requirements
Table 4.2 listed non-functional requirements.

| ID | Requirement |
|---|---|
| NFR-01 | Security: All protected endpoints shall require valid API key or JWT identity. |
| NFR-02 | Authorization: Admin endpoints shall reject non-admin callers with HTTP 403. |
| NFR-03 | Performance: Core dashboard endpoints shall apply rate limits (configured at 10–60 requests/minute). |
| NFR-04 | Reliability: GET calls in frontend service layer shall implement retry logic for transient failures. |
| NFR-05 | Availability: Health endpoints shall expose liveness and readiness for operational monitoring. |
| NFR-06 | Observability: Structured logs and runtime counters shall be emitted for requests and predictions. |
| NFR-07 | Data Quality: Risk-map responses shall include data quality and freshness indicators. |
| NFR-08 | Maintainability: Modular collectors/processing/services shall remain separable by functional concern. |
| NFR-09 | Scalability: Streaming and document storage architecture shall support growth in source volume. |
| NFR-10 | Usability: Role-specific frontend routes shall prevent unauthorized access and reduce operator error. |

---

# Chapter 05 – System Architecture

## 5.1 High-Level Architecture
The platform was implemented as a layered pipeline:

```text
External APIs
   -> Collectors (Python modules)
   -> Kafka topics
   -> Stream normalization + preprocessing
   -> MongoDB collections + Feature Store artifacts
   -> ML/Analytics services
   -> FastAPI endpoints + WebSocket streams
   -> React/TypeScript command dashboard
```

## 5.2 Core Components

### 5.2.1 Data Collection Layer
Active collector orchestration in `orchestrator.py` configured 14 primary collector tasks: news, gdelt, wiki, trends, earthquakes, weather, crypto, fred, exchange rates, WHO, stocks, worldbank, reddit, and world_state.

### 5.2.2 Streaming and Processing Layer
Kafka producer/consumer utilities decoupled ingestion and processing. Country risk stream services (`backend/country_risk_stream.py`) normalized source events, updated rollups, and published country risk updates.

### 5.2.3 Persistence Layer
MongoDB stored both raw and derived artifacts. As of 16 March 2026 (snapshot query):

1. `country_features`: 56,793 records  
2. `global_features`: 5,600 records  
3. `dashboard_features`: 18,081 records  
4. `trends`: 43,789 records  
5. `earthquakes`: 203,245 records

### 5.2.4 Analytics and ML Layer
Model assets included gradient boosting, random forest, logistic regression, LSTM horizon models, and anomaly components. Model registry metadata indicated `auto_gb_model` in production and logistic/random-forest variants in staging.

### 5.2.5 Service/API Layer
`backend/main.py` exposed 93 routes spanning dashboard, analytics, auth, observability, trust, health, admin, and websocket domains. Category breakdown included 19 `/dashboard/*` routes, 14 `/observability/*`, and 12 `/analytics/*`.

### 5.2.6 Frontend Layer
`world-pulse-frontend` implemented 15 routes, with protected role-aware navigation. The dashboard and trend-prediction pages integrated lazy-loaded domain components, realtime polling, and advanced analytics panels.

## 5.3 Use Case Perspective
Main use cases were:

1. Monitor global risk and live incidents.
2. Inspect country-level risk, drivers, and context.
3. Execute scenario simulation and counterfactual analysis.
4. View advanced analytics (predictions, anomalies, causal graph, AI report).
5. Administer user access and inspect monitoring/security status.

## 5.4 Data Model (ER-Oriented Summary)
Table 5.1 summarized key entities.

| Entity/Collection | Role |
|---|---|
| `news`, `gdelt`, `trends`, `weather`, `health`, `economics`, `crypto`, etc. | Source-domain raw/normalized documents |
| `country_source_events` | Normalized country event stream |
| `country_signal_rollups` | Aggregated per-country daily signal summaries |
| `country_features` | Country risk feature vectors and risk scores |
| `global_features` | Global feature vectors and aggregate risk/mood outputs |
| `dashboard_features` | Dashboard-focused snapshot view |
| `model_monitoring` | Prediction and drift telemetry |
| `country_model_validation`, `global_mood_validation` | Validation summaries |
| `country_model_backtests`, `global_mood_backtests` | Rolling backtest outputs |
| `users`, `security_events`, `operator_events` | Access control and audit records |

## 5.5 Architectural Strengths and Constraints
The architecture demonstrated strong modularity and observability, but operational quality remained sensitive to external-source health and label availability. On 16 March 2026, source-health telemetry recorded multiple critical feeds in down state (`acled`, `reliefweb`, `openaq`, `eia`, `firms`), illustrating practical resilience pressure in real-world deployment.

---

# Chapter 06 – Method of Approach / Methodology

## 6.1 Development Model
An iterative, increment-driven implementation model was enacted. Delivery progressed through repeated cycles of source integration, feature engineering, API extension, frontend integration, and defect remediation.

## 6.2 Enacted Workflow
The methodology was enacted in six recurring stages:

1. Source integration and collector hardening.
2. Stream normalization and schema alignment.
3. Feature and model pipeline updates.
4. API route extension with typed request models.
5. Frontend panel integration and route protection.
6. Validation, backtesting, and operational telemetry review.

## 6.3 Tooling and Environment
Primary tools included:

1. Python (data, backend, ML, scripts)
2. FastAPI + Uvicorn (service layer)
3. MongoDB (document persistence)
4. Kafka (stream transport)
5. React + TypeScript + Vite (frontend)
6. Git-based versioning and script-driven operational tasks

## 6.4 Versioning and Model Governance
Model lifecycle controls were implemented through a registry with staging/production/archived states, promotion operations, rollback support, and audit logging.

## 6.5 Task Structuring
Implementation work naturally partitioned into:

1. Data engineering tasks (collectors, normalization, freshness).
2. ML/analytics tasks (risk scoring, forecasting, anomaly, causal, report generation).
3. Service and security tasks (auth, RBAC, observability, trust metrics).
4. Frontend tasks (dashboard, trend prediction, admin interfaces).

## 6.6 Methodology Reflection
The methodology was practical for continuous feature addition and stabilization. However, the process remained constrained by asynchronous external-source reliability and incomplete benchmark datasets. These constraints reinforced the need for stronger data-governance checkpoints in future iterations.

---

# Chapter 07 – System Testing and Quality Assurance

## 7.1 Test Strategy
Testing combined static checks, script-based endpoint tests, validation/backtesting scripts, and operational telemetry checks.

## 7.2 Executed Evidence (16 March 2026)
The following checks were executed during this audit:

1. Syntax compilation sweep across core modules (`backend`, `collectors`, `processing`, `machine_learning`, `feature_store`, `database`, `scripts`, `scheduler`) completed successfully.
2. Country-risk validation script (`scripts/run_country_risk_validation.py`) returned status `ok`.
3. Country-risk backtest (`--backtest --days 60`) returned status `ok`.
4. Global mood validation returned `no_ground_truth_matches`.
5. Global mood backtest returned `no_ground_truth`.
6. Sentinel API integration script failed due backend not active on `127.0.0.1:8000` at execution time, plus console encoding failure in test output path.

## 7.3 Validation and Backtest Results
Table 7.1 summarized key quantitative outputs.

| Test Item | Result |
|---|---|
| Country risk validation sample size | 7 |
| Accuracy @ 0.50 | 1.0000 |
| Accuracy @ 0.70 | 1.0000 |
| Brier score | 0.0329 |
| Log loss | 0.1762 |
| Country backtest matched days | 1 |
| Country backtest weighted Brier | 0.0329 |
| Global mood validation sample size | 0 |
| Global mood validation status | `no_ground_truth_matches` |

## 7.4 Data Quality and Coverage Findings
Two evidence snapshots were identified:

1. Local CSV snapshot (`data/country_features.csv`) contained 233 countries, with 198 non-placeholder topic rows and 35 placeholder/no-data rows.
2. Live Mongo coverage snapshot indicated 233 countries but `verified_like` countries were 0 on audit date due freshness/day alignment, with 198 stale-like and 35 synthetic-like entries.

These findings indicated that coverage width had been high, but recency validation remained an operational bottleneck.

## 7.5 Defect and Regression Evidence
Existing project documentation (`TEST_REPORT.md`, dated 25 February 2026) recorded resolution of a critical map-data defect where country risk values had not been persisted for map rendering. The fix path included orchestrator updates and backfill procedures.

## 7.6 QA Gaps
The primary unresolved QA gaps were:

1. Limited ground truth for global mood validation.
2. Dependency on external API uptime and credentials for several critical sources.
3. Inconsistent availability of live backend process during endpoint-script execution.
4. Incomplete automated frontend unit/component test coverage.

---

# Conclusions
The project successfully delivered a technically comprehensive crisis intelligence platform integrating multi-domain data collection, feature engineering, model-driven risk analytics, secure APIs, and role-aware operational dashboards. The implemented system demonstrated broad endpoint capability (93 backend routes), substantial data persistence scale, and working country-risk validation metrics on available benchmark labels.

The objective of building a unified, explainable, and operational monitoring workflow was therefore substantially achieved. Nevertheless, the quality of final-stage reliability remained constrained by three factors: sparse global mood labels, external source instability, and freshness misalignment in validation windows.

Future work should prioritize dataset governance, source resilience engineering, and tighter production-grade deployment controls. No new technical claims were introduced beyond observed implementation and executed evidence.

---

# Team Plan & Responsibility Matrix

> **Note:** The guideline required separate tables per member. The following matrices were provided as structured templates and should be replaced with actual student names and IDs.

## Table 9.1 Member 01 Responsibility Matrix
| Item | Description |
|---|---|
| Member | _[Insert Name / ID]_ |
| Primary Role | Data Engineering Lead |
| Key Responsibilities | Collector integration, Kafka event flow, source-health telemetry |
| Main Artifacts | `collectors/*`, `orchestrator.py`, `backend/country_risk_stream.py` |
| Estimated Contribution | _[Insert %]_ |
| Evidence | Commits, issue logs, integration test outputs |

## Table 9.2 Member 02 Responsibility Matrix
| Item | Description |
|---|---|
| Member | _[Insert Name / ID]_ |
| Primary Role | ML and Analytics Lead |
| Key Responsibilities | Feature engineering, risk scoring, forecasting/anomaly/causal modules |
| Main Artifacts | `processing/*`, `machine_learning/*`, model registry workflows |
| Estimated Contribution | _[Insert %]_ |
| Evidence | Validation scripts, model metadata, backtest snapshots |

## Table 9.3 Member 03 Responsibility Matrix
| Item | Description |
|---|---|
| Member | _[Insert Name / ID]_ |
| Primary Role | Backend and Security Lead |
| Key Responsibilities | API routes, auth/RBAC, observability, admin controls |
| Main Artifacts | `backend/main.py`, `backend/observability.py`, `scripts/restart_backend.ps1` |
| Estimated Contribution | _[Insert %]_ |
| Evidence | Endpoint integration tests, security logs, uptime metrics |

## Table 9.4 Member 04 Responsibility Matrix
| Item | Description |
|---|---|
| Member | _[Insert Name / ID]_ |
| Primary Role | Frontend and UX Lead |
| Key Responsibilities | Dashboard integration, trend prediction views, admin UI |
| Main Artifacts | `world-pulse-frontend/src/pages/*`, `world-pulse-frontend/src/components/*`, `src/services/api.ts` |
| Estimated Contribution | _[Insert %]_ |
| Evidence | UI test artifacts, route guards, feature demos |

---

# Reference List
Apache Software Foundation (n.d.) *Apache Kafka Documentation*. Available at: https://kafka.apache.org/documentation/ (Accessed: 16 March 2026).

Blei, D.M., Ng, A.Y. and Jordan, M.I. (2003) ‘Latent Dirichlet Allocation’, *Journal of Machine Learning Research*, 3, pp. 993-1022.

FastAPI (n.d.) *FastAPI Documentation*. Available at: https://fastapi.tiangolo.com/ (Accessed: 16 March 2026).

Hutto, C.J. and Gilbert, E. (2014) ‘VADER: A Parsimonious Rule-based Model for Sentiment Analysis of Social Media Text’, in *Proceedings of the International AAAI Conference on Web and Social Media*. pp. 216-225.

McKinney, W. (2010) ‘Data Structures for Statistical Computing in Python’, in *Proceedings of the 9th Python in Science Conference*. pp. 56-61.

MongoDB (n.d.) *MongoDB Documentation*. Available at: https://www.mongodb.com/docs/ (Accessed: 16 March 2026).

Pedregosa, F. et al. (2011) ‘Scikit-learn: Machine Learning in Python’, *Journal of Machine Learning Research*, 12, pp. 2825-2830.

Pearl, J. (2009) *Causality: Models, Reasoning and Inference*. 2nd edn. Cambridge: Cambridge University Press.

React (n.d.) *React Documentation*. Available at: https://react.dev/ (Accessed: 16 March 2026).

Vite (n.d.) *Vite Guide*. Available at: https://vite.dev/guide/ (Accessed: 16 March 2026).

World Health Organization (n.d.) *Global Health Observatory (GHO) API*. Available at: https://www.who.int/data/gho/info/gho-odata-api (Accessed: 16 March 2026).

---

# Appendices

## Appendix A – Project Source Code Link
**Required Link:** _[Insert OneDrive source-code link with evaluator access]_  
**Local repository path (audit reference):** `C:\Projects\world-pulse-research`

## Appendix B – GitHub Commit History and Repository Link
**Repository Link:** _[Insert GitHub repository URL]_  
**Commit History Export:** _[Attach log screenshots/export in final PDF appendix]_

## Appendix C – Project Proposal
_Attach the submitted project proposal document._

## Appendix D – Functional & Technical Report
_Attach the approved functional and technical report._

## Appendix E – Interim Report
_Attach the submitted interim report._

## Appendix F – Records of Supervisory Meetings
_Attach dated supervision minutes and action logs._

## Appendix G – Additional Supporting Material
Recommended inclusions:

1. Full endpoint inventory (93 routes) and route category summary.
2. Validation script outputs dated 16 March 2026.
3. Country-risk backtest output snapshot.
4. Source-health telemetry snapshot (critical sources up/down).
5. UI evidence screenshots and environment configuration checklist.

---

## Appendix G.1 – Audit Snapshot (16 March 2026)
The following evidence was captured during this report drafting process:

1. Codebase scale (excluding dependency folders):  
   - Python files: 120 (28,278 lines)  
   - TSX files: 55 (19,779 lines)  
   - TypeScript files: 8 (2,991 lines)
2. Backend route inventory: 93 routes.
3. Frontend route inventory: 15 routes.
4. Active orchestrator collector tasks: 14.
5. Country risk validation: status `ok`, sample size 7, Brier 0.0329.
6. Global mood validation: status `no_ground_truth_matches`.
7. Mongo snapshot counts (selected):  
   - `country_features`: 56,793  
   - `global_features`: 5,600  
   - `dashboard_features`: 18,081

These appendix notes were provided so that the main report remained readable while preserving traceability to detailed evidence.
