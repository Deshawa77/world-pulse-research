# World Pulse Viva Master Guide

Prepared for viva preparation from a repository-wide scan of the core implementation and supporting configuration. This guide is intentionally detailed and practical: it explains what the system does, how the parts connect, what is strong, what is weak, and what each team member should be ready to defend.

Important honesty note: this document is based on a deep scan of the architecture-critical files and the main supporting scripts, not a line-by-line commentary on every tiny helper or cache artifact. For viva purposes, this is the right level of depth because examiners usually test system understanding, design logic, implementation choices, tradeoffs, reliability, and role ownership.

## 1. How to Use This Guide

Use this document in three passes.

First pass: read Sections 2 to 8 to understand the whole system story.

Second pass: each member should read the role section in Section 19 and the matching question bank in Section 21.

Third pass: revise Sections 17, 18, 22, 23, and 24 because viva panels often ask about limitations, non-functional requirements, ethics, and future improvements.

## 2. One-Minute Explanation of the System

World Pulse is a real-time crisis intelligence and risk forecasting platform. It collects heterogeneous signals from external sources such as news, GDELT, Wikipedia attention, Google Trends, weather, earthquakes, finance, health, mobility, aviation, logistics, and world-state indicators. These signals are pushed through collectors, optionally streamed through Kafka, stored in MongoDB, enriched by preprocessing and NLP, transformed into country-level and global feature sets, and then used by machine-learning and analytics modules to estimate risk, detect anomalies, generate forecasts, and support operator decision making.

The backend is implemented in FastAPI and exposes secure REST and WebSocket interfaces. The frontend is a React and TypeScript dashboard with protected routes, admin views, analytics panels, country drilldowns, historical views, and scenario simulation. The platform also includes authentication, role-based access control, security event logging, observability, validation, backtesting, and partial deployment automation.

In simple terms: this system watches many global signals, converts them into structured intelligence, scores risk at country and global levels, and presents the results in a secure operational dashboard.

## 3. Core Problem the Project Solves

The system exists because crisis-related signals are fragmented across many domains. Financial volatility, disasters, social narratives, public-health alerts, logistics disruption, and conflict indicators often live in separate tools. Human operators then struggle to build a unified picture quickly enough to act. World Pulse tries to solve this by creating one pipeline that ingests multiple signals, standardizes them, stores them, enriches them, and surfaces a fused operational picture with traceable metrics and explainable outputs.

This means the system is not just a dashboard and not just a model. It is a full-stack intelligence pipeline.

## 4. High-Level Repository Map

The most important directories are below.

| Directory | Purpose |
|---|---|
| `backend/` | FastAPI API, auth, admin endpoints, observability, WebSockets, streaming health |
| `collectors/` | Data ingestion from external APIs and public data sources |
| `processing/` | Feature engineering, NLP, risk fusion, validation, counterfactuals, explainability |
| `machine_learning/` | Forecasting, anomaly detection, advanced analytics, training helpers |
| `database/` | MongoDB connection and helper functions |
| `feature_store/` | Offline feature storage and model registry |
| `world-pulse-frontend/` | React and TypeScript frontend |
| `deploy/` | Backend deployment compose files and deploy notes |
| `scheduler/` | Periodic model refresh and validation tasks |
| `data/`, `data_lake/`, `models/` | Local artifacts, serialized data, and model assets |
| `tests/` and root test scripts | Script-based checks and selected tests |

## 5. Main Technology Stack

| Layer | Main Technologies |
|---|---|
| Backend API | Python, FastAPI, Uvicorn, Pydantic, SlowAPI |
| Security | JWT, API keys, Passlib bcrypt, role checks, security event logging |
| Storage | MongoDB via `pymongo` |
| Streaming | Apache Kafka via `kafka-python` |
| Data/ML | pandas, numpy, scikit-learn, TensorFlow or statistical fallbacks, VADER and NLP utilities |
| Frontend | React 19, TypeScript, Vite, React Router, Axios |
| Visualization | Three.js, charts, live panels, historical playback |
| Deployment | Docker image for backend, Docker Compose for backend service, GitHub Actions-oriented deployment layout |

## 6. End-to-End Architecture Story

The easiest way to defend this system in viva is to explain it as a data journey.

### 6.1 Stage 1: External Data Collection

The collectors pull data from many domains:

- News and event text: NewsAPI, GDELT, Reddit, Telegram public signals, YouTube trends
- Public attention: Wikipedia pageviews, Google Trends
- Disaster and environment: USGS earthquakes, OpenWeather, NASA and fire-related sources through world-state aggregation
- Finance and macroeconomics: CoinGecko, FRED, Frankfurter, TwelveData, World Bank
- Health: WHO and health-related sources
- Mobility and transport: UNHCR or IDMC style displacement signals, OpenSky aviation
- Logistics and economic behavior: World Bank logistics indicators, economic stress synthesis
- Security and world-state: CISA KEV, ReliefWeb, OpenAQ, ACLED, NOAA, EIA and other operational feeds through aggregate collectors

Each collector typically does three things:

1. Calls an external API or public dataset.
2. Converts the raw payload into a normalized Python dictionary.
3. Inserts the document into MongoDB and or sends it to Kafka.

This is why the system is resilient at the ingestion layer: collectors are separate modules, so adding or removing one feed does not require redesigning the whole backend.

### 6.2 Stage 2: Streaming Through Kafka

Collectors can publish into topic-based streams. The codebase uses Kafka to decouple producers from downstream consumers. Instead of one collector calling one model directly, data is sent to topics and then independently consumed by normalization, feature, and country-risk streams.

This matters for viva because you can explain the architectural benefit clearly:

- Producers and consumers are loosely coupled.
- Consumers can fail or restart without losing the overall architecture.
- Multiple downstream services can react to the same event stream.
- The system can scale by adding more consumers rather than rewriting collectors.

The code explicitly defines raw-source topics and derived topics. Important derived topics include:

- `country_source_events`
- `country_risk_updates`
- `country_risk_dlq`

The dead-letter topic exists to capture malformed or failed events rather than silently dropping them.

### 6.3 Stage 3: Persistence in MongoDB

MongoDB is used as the operational source of truth for both raw and derived data. This is a document-oriented design, which is a good match for heterogeneous multi-source event payloads because different external APIs do not share one fixed relational schema.

Raw collections hold source payloads. Derived collections hold cleaned signals, feature vectors, monitoring summaries, validation runs, security events, and user data.

MongoDB also supports:

- fast lookup of latest records
- time-ordered history
- country-specific feature retrieval
- admin telemetry
- live dashboard fallback when Kafka is unavailable

### 6.4 Stage 4: Preprocessing and NLP

After ingestion, the system preprocesses records, extracts text meaning, generates topics, and creates engineered features. The processing layer is where the project becomes more than a collector bundle.

Examples:

- sentiment extraction from country news and GDELT
- robust topic extraction from MongoDB text collections
- economic and mobility signal fusion
- weather and logistics stress normalization
- evidence quality and freshness scoring
- global mood confidence and uncertainty estimation
- war-state and escalation rule logic for countries

### 6.5 Stage 5: Country and Global Feature Engineering

The project has two key intelligence products.

The first is country-level risk intelligence. This includes a country risk score, supporting component signals, quality flags, evidence metrics, freshness, and confidence.

The second is global operational intelligence. This includes global mood, global risk, forecast risk, aggregate behavior and context indices, and top themes.

This two-level design is important to explain. The country layer lets the system localize events. The global layer lets the system summarize the planet-level operational picture.

### 6.6 Stage 6: Machine Learning and Advanced Analytics

The machine-learning layer performs several analytical roles:

- production prediction using registered models
- time-series forecasting with LSTM or statistical fallback
- anomaly detection using autoencoder-like or statistical methods
- causal discovery and explainability support
- sentiment momentum analysis
- narrative report generation

This means the system is not one single model. It is a collection of analytics services around a core operational feature pipeline.

### 6.7 Stage 7: API and Live Dashboard Delivery

FastAPI exposes:

- protected data endpoints
- feature store endpoints
- risk-map and dashboard endpoints
- analytics and reporting endpoints
- auth and admin endpoints
- health and observability endpoints
- live WebSocket streams

The React frontend consumes these APIs and renders dashboards, analytics pages, historical panels, admin consoles, and response tools.

## 7. Backend Deep Dive

The backend is the central coordination layer of the system. The most important file is `backend/main.py`, which contains a very large FastAPI application. In viva, do not panic about the file size. Instead, explain its responsibilities in grouped form.

### 7.1 Backend Responsibilities

The backend performs five major jobs:

1. Authenticates users and API clients.
2. Exposes REST and WebSocket interfaces.
3. Reads from MongoDB and returns operational intelligence views.
4. Records predictions, monitoring data, and security events.
5. Provides admin observability, health, and reliability endpoints.

### 7.2 Request Lifecycle

The request middleware attaches an `x-request-id`, measures request duration, updates runtime counters, optionally enforces HTTPS, and writes structured logs. This is a strong design point because it improves traceability, diagnostics, and operational maturity.

In viva language:

- every request gets a trace identifier
- every response contributes to runtime statistics
- server logs become machine-readable
- production deployments can require HTTPS

### 7.3 Rate Limiting

The app uses `SlowAPI` and the `Limiter` abstraction. Different endpoints have different request quotas such as 10 per minute or 60 per minute depending on use case. This supports non-functional requirements around performance protection and abuse prevention.

### 7.4 Authentication Model

The system supports two authentication modes.

Mode one is API key authentication. This is useful for service-to-service access, testing, and simple secured clients.

Mode two is JWT bearer authentication. This is used for registered users who log in through the frontend.

The `verify_api_key` dependency first checks whether the `Authorization` header contains a bearer token. If yes, it decodes and validates the JWT. If no, it falls back to checking API keys from headers.

This is a practical hybrid model:

- API keys secure automation and basic access
- JWT supports user sessions and role-aware identity

### 7.5 Role-Based Access Control

The backend defines:

- `admin`
- `user`

It also normalizes user types such as `researcher`, `policy`, `student`, and `developer`.

Admin routes use `require_admin` or `require_admin_identity`. These dependencies reject non-admin callers with HTTP 403. This is a direct implementation of authorization control.

### 7.6 Registration and Login

Registration inserts users into MongoDB with hashed passwords, role, user type, organization, and timestamps. Users are normal users by default. Admin self-registration is allowed only when a valid admin invite code is provided.

Login verifies email and password, checks whether the account is active, logs the outcome into `security_events`, increments security counters, and returns a JWT-based auth response.

This is a strong viva point: the auth system is not just login success and failure. It also creates an audit trail.

### 7.7 Password Handling

Passwords are hashed using bcrypt through Passlib with 12 rounds. The code also safely truncates UTF-8 byte length before hashing because bcrypt has a 72-byte input limitation. This is the kind of implementation detail that impresses examiners because it shows security awareness beyond textbook statements.

### 7.8 Security Event Logging

The backend records security events such as:

- login success
- login failure
- blocked login
- JWT validation failure
- invalid API key use
- suspicious activity patterns

There are thresholds for suspicious repeated failures. This means the system has basic detection logic, not just passive logging.

### 7.9 Health Endpoints

The backend exposes:

- `/health/live`
- `/health/ready`
- `/health`
- `/health/dependencies`

Explain them in viva like this:

- liveness answers “is the service process alive?”
- readiness answers “is the service ready to handle traffic?”
- dependency health answers “are MongoDB, model loading, and risk dependencies available?”

This distinction is a classic systems-engineering point.

### 7.10 Admin Monitoring

The `/admin/system-monitoring` endpoint is especially important because it synthesizes:

- server status
- API health
- data pipeline dependency status
- latest ingestion timestamps
- freshness summaries
- source-health snapshots
- mobility and economic observability
- operational alerts
- uptime statistics

In short, this route is the operations command center.

### 7.11 Security Logs Endpoint

The `/admin/security-logs` endpoint aggregates:

- login totals
- success, failed, and blocked attempts
- suspicious activity counts
- JWT validation failures
- recent event records

This supports both security engineering and viva discussion on observability and auditability.

### 7.12 Prediction and Monitoring

The backend loads a production model bundle, aligns features using a schema, performs prediction, computes drift against recent baseline data, writes logs to `prediction_logs`, writes monitoring entries to `model_monitoring`, and exposes metadata through observability endpoints.

This means the prediction layer is governed, not just executed.

### 7.13 Live WebSockets

There are secure WebSocket endpoints for:

- `/ws/risk`
- `/ws/country-risk-map`
- `/ws/sentinel`

These streams authenticate via JWT or API key credentials. When Kafka is available, they consume live events. When Kafka is unavailable, at least some paths fall back to sending fresh MongoDB-derived snapshots and keepalive messages. This is a strong resilience feature.

## 8. MongoDB Deep Dive

MongoDB is the operational heart of the system.

### 8.1 Why MongoDB Fits This Project

MongoDB is suitable here because:

- source payloads are heterogeneous and nested
- schema evolves as collectors and features expand
- latest-by-time queries are common
- documents often include variable metadata
- the system needs both raw payload storage and derived snapshots

A relational database could still work, but it would require more rigid schema planning and more migration friction for rapidly evolving multi-domain feeds.

### 8.2 Important Collections

The collections below represent the most important data entities.

| Collection | Purpose |
|---|---|
| `news`, `gdelt`, `wiki`, `trends`, `earthquakes`, `weather`, `crypto`, `stocks`, `worldbank`, `health`, `economics` | Raw or lightly normalized domain source data |
| `country_news` | Country-specific article intelligence with sentiment and metadata |
| `mobility`, `aviation`, `logistics`, `economic_behavior` | Country-level contextual disruption and pressure signals |
| `source_health` | Health state of external providers, including errors and freshness |
| `country_source_events` | Normalized country events derived from raw streams |
| `country_signal_rollups` | Aggregated per-country daily signal summaries |
| `country_features` | Country-level engineered features and risk outputs |
| `global_features` | Global engineered features and global risk or mood outputs |
| `dashboard_features` | Snapshot documents optimized for dashboard consumption |
| `prediction_logs` | Historical inference records |
| `model_monitoring` | Drift, probability, version, and inference telemetry |
| `users` | Registered users with role, status, and profile information |
| `security_events` | Auth and suspicious-activity logs |
| `operator_events` | Manual operator activity tracking |
| `sentinel_feedback` | Feedback on Sentinel outputs |
| `causal_explanations`, `counterfactual_runs`, `policy_replays`, `action_recommendations` | Explainability and decision-support artifacts |
| `service_status`, `kafka_event_state`, `country_risk_dlq` | Operational tracking, processed-event state, and failure capture |

### 8.3 Index Design

The backend creates indexes for common query patterns, including:

- descending timestamps for latest views
- `email` as a unique user key
- role and user-type indexes for admin filtering
- country plus mode plus timestamp for country feature history
- mode plus timestamp for global features
- source health indexes
- security event indexes by event type, status, email, and client IP

In viva, explain why indexes matter:

- faster latest-record retrieval
- faster admin log queries
- better scalability as history grows
- support for real dashboard latency

### 8.4 Data Integrity Practices

The codebase includes several practical integrity mechanisms:

- sanitizing records for MongoDB-safe keys
- unique and upsert-like insertion logic
- versioned feature writes
- derived snapshots when explicit feature rows are missing
- fallback from configured Mongo URI to local Mongo in some backend startup paths

### 8.5 Online and Offline Modes

Feature writing utilities support `mode` values such as `online` and `offline`. This is important because it separates live operational outputs from training or batch-analysis contexts. That helps with experimentation, replay, and backtesting without contaminating live dashboards.

### 8.6 MongoDB Tradeoffs

The benefits are flexibility and speed of iteration. The tradeoffs are:

- schema discipline must be enforced in code rather than by the database
- collection structures can drift over time
- joins are not naturally as strong as in relational systems
- data provenance becomes more important when multiple fallbacks exist

This is a fair, balanced answer for viva.

## 9. Kafka and Streaming Deep Dive

Kafka is used as the event backbone, even though the repo’s deployment assets do not fully provision Kafka infrastructure. The code clearly assumes a broker at `KAFKA_BROKER` or `localhost:9092`.

### 9.1 Kafka Client Design

`backend/kafka_client.py` initializes a producer if Kafka libraries are installed and the broker is reachable. Messages are JSON-serialized. Consumers can subscribe to one or many topics with configurable group IDs, offset reset mode, and timeout.

The design is optional-runtime friendly. If Kafka support is unavailable, producer actions fail gracefully instead of crashing the entire platform.

### 9.2 Why Kafka Was Chosen

Kafka is useful here because the system has many sources and many possible consumers. The platform benefits from:

- asynchronous ingestion
- replayable event streams
- decoupled producer and consumer lifecycles
- better scaling for live updates
- easier addition of new downstream processors

### 9.3 Orchestrator Topics and Flow

The orchestrator defines a large `COLLECTOR_TASKS` map. Each collector is associated with a topic. Examples include:

- news and GDELT topics
- wiki pageviews
- Telegram and YouTube trend topics
- trends, earthquakes, weather, crypto
- macroeconomic and finance topics
- WHO indicators
- stocks and World Bank topics
- mobility, aviation, logistics, economic behavior, energy stress, and world-state related streams

The orchestrator then:

1. starts collector threads
2. starts a Kafka stream consumer
3. preprocesses and enriches events
4. persists results
5. runs ML cycles
6. updates dashboard-focused views

### 9.4 Country Risk Stream

`backend/country_risk_stream.py` deserves special mention because it is a strong architectural feature.

It defines:

- normalized topic: `country_source_events`
- update topic: `country_risk_updates`
- dead-letter topic: `country_risk_dlq`

It performs:

- raw message normalization
- event deduplication and state tracking
- country-level signal rollups
- incremental country-risk recomputation
- derived event publishing
- lag and service status reporting

This is one of the clearest places where Kafka, MongoDB, processing logic, and live dashboard behavior meet.

### 9.5 Dead-Letter Queue

A dead-letter queue is important in viva because it shows failure awareness. Bad or unprocessable events are not silently lost. They are rerouted to a special topic and also inserted into a dedicated Mongo collection for later inspection.

### 9.6 Streaming Limitations

The most honest limitation is that the code strongly supports Kafka, but the committed deployment assets are backend-oriented and do not fully define Kafka cluster provisioning. Therefore, for a complete production deployment, additional infrastructure setup is required.

## 10. Data Engineering and Processing Pipeline

This is the section the dedicated data engineer should know extremely well.

### 10.1 Collector Philosophy

The collectors are modular. Each source integration is isolated in its own file, which makes maintenance easier and allows source-specific retry, parsing, and normalization logic. The project does not force one universal source schema too early. Instead, it normalizes enough to make later fusion possible.

### 10.2 Country News Collector

The `collectors/country_news.py` module is especially rich. It performs:

- country-aware news retrieval
- query budgeting
- deduplication
- ranking
- translation caching
- sentiment analysis
- persistence into `country_news`

This module is important because country risk is heavily dependent on narrative signals and topic relevance.

### 10.3 World State Collector

The world-state collector aggregates multiple operational and institutional signals into broader cross-domain awareness. It also writes source health data, which lets the platform distinguish between “no crisis signal” and “missing or broken upstream source.”

That difference is a mature systems point. In real-world monitoring, silence from a broken sensor is not the same as a calm world.

### 10.4 Economic Behavior Collector

The economic behavior collector fuses:

- World Bank indicators
- FRED indicators
- energy-related signals
- exchange-rate pressure
- household and labor stress proxies

It transforms economically diverse raw inputs into more operational features such as household stress, fuel pressure, food pressure, FX pressure, remittance stress, and energy stress.

### 10.5 Preprocessing

The preprocessing layer standardizes records before higher analytics. This includes:

- cleaning fields
- managing timestamps
- converting nested records
- extracting signal-friendly values
- building data-lake style JSON artifacts

### 10.6 Topic and NLP Processing

The system includes both classic sentiment and more advanced topic logic. The processing layer contains topic extraction pipelines, robust topic intelligence, text cleaning, and narrative-style analytics. This is important because crises are not only numeric phenomena. Narrative escalation, coordination, and public attention also matter.

### 10.7 Country Daily Risk Construction

`processing/country_daily_risk.py` computes country-level risk features by combining:

- country news
- wiki attention
- mobility
- economic behavior
- other external signals
- conflict or war-state rules
- freshness and evidence quality
- source diversity

The design shows that country risk is not a single direct output from one source. It is a fused intelligence product.

### 10.8 Global Mood Construction

`processing/global_mood.py` builds global operational features using country-level evidence and aggregate signals. It computes:

- `global_mood_score`
- confidence
- uncertainty
- forecast risk score
- global behavior index
- global context index
- global attention index
- global disruption index
- global economic stress index

This is a sophisticated design because it explicitly models uncertainty and coverage rather than pretending all countries are equally observed.

### 10.9 Quality Gating

The system contains quality assessments such as:

- validated vs synthetic vs stale vs unknown data quality
- source counts
- external signal freshness
- evidence quality
- verified-country coverage

This is a major strength because it prevents the system from presenting all outputs as equally trustworthy.

### 10.10 Feature Store

The feature store uses local artifact storage formats such as Parquet and CSV, along with metadata and schema files. This supports:

- offline model development
- reproducibility
- historical analysis
- model bootstrap and fallback logic

In viva, explain that MongoDB is the operational store while the feature store is closer to offline analytics and model asset support.

## 11. Machine Learning and Data Science Deep Dive

The ML layer is broad. A safe viva answer is: the platform has both operational inference and advanced analytics, with fallbacks when data or heavy dependencies are insufficient.

### 11.1 Production Prediction Path

The prediction schema defines expected feature order and schema version. The production model bundle is loaded from the model registry. Prediction calls log:

- model version
- feature names
- schema version
- predicted class or score
- probability
- drift score

This is governance-aware ML.

### 11.2 Model Registry

The model registry supports stages such as:

- staging
- production
- archived

It also tracks metadata and an audit log. This is a professional software engineering feature because it separates model files from deployment status.

### 11.3 Bootstrapping Models

`feature_store/load_models.py` can bootstrap gradient boosting, random forest, and logistic-style models from available feature data, with dummy-classifier fallback if necessary. This makes the environment more resilient for development and demos, though in viva you should present that honestly as a practical support mechanism, not as a substitute for strong production training pipelines.

### 11.4 LSTM Predictor

The LSTM predictor supports multi-horizon forecasting such as:

- 1 hour
- 6 hours
- 24 hours
- 7 days

If TensorFlow or sufficient trained artifacts are unavailable, the module can fall back to statistical forecasting. This is a smart design choice because it keeps the advanced analytics interface working even when the deep-learning stack is not fully available.

### 11.5 Anomaly Detection

The anomaly detector follows a similar idea. It can use a stronger model path when available, but it also has a statistical fallback. This improves graceful degradation.

### 11.6 Advanced Analytics Engine

`machine_learning/advanced_analytics.py` is effectively a meta-orchestrator for advanced insight services. It pulls from MongoDB features, computes analytics, and exposes high-level KPI summaries. Its output is used by analytics-oriented frontend views.

### 11.7 Sentiment Momentum

This module borrows concepts from time-series or financial indicators such as:

- velocity
- acceleration
- RSI-style behavior
- MACD-like interpretation
- bands or thresholds

This is useful because narrative changes often matter more than static sentiment alone.

### 11.8 Causal and Explainability Modules

The project includes:

- causal explanation builder
- counterfactual engine
- policy replay
- action recommender

These modules move the system from “what is happening?” toward “why might this be happening?” and “what could happen under changed conditions?”

### 11.9 Validation and Backtesting

There are explicit validation and backtesting modules for:

- country risk
- global mood

The scheduler can run refreshes and validation suites periodically. One honest limitation visible from the project’s own report and utilities is that global mood validation can suffer from sparse ground truth. This is not a failure of coding but a normal challenge in real-world crisis intelligence systems.

### 11.10 What the ML Team Should Not Overclaim

In viva, do not say the models perfectly predict crises. Better language is:

- the models estimate risk based on heterogeneous signals
- the system exposes confidence, uncertainty, validation, and backtesting
- some modules support fallback analytics to preserve system continuity
- final operational interpretation should still consider data quality and source health

That answer sounds mature and scientifically honest.

## 12. Frontend Deep Dive

The frontend is not a cosmetic add-on. It is the operational surface of the system.

### 12.1 Route Structure

The app includes public routes such as:

- home
- about
- contact
- login
- register
- forgot password
- reset password

Protected user routes include:

- dashboard
- trend prediction
- historical trends
- scenario studio
- response console
- profile

Admin routes include:

- admin console
- system monitoring
- security logs

This means the frontend is role-aware and not just one flat page.

### 12.2 Frontend Service Layer

`world-pulse-frontend/src/services/api.ts` is a key architectural file. It handles:

- active API URL management
- fallback API URL switching
- JWT and API key header creation
- WebSocket URL building
- GET caching
- retry logic for transient failures
- automatic auth clearing on 401
- mock or synthetic fallback data for degraded environments

This is a major strength because it makes the frontend resilient to temporary backend instability.

### 12.3 Dashboard

The main dashboard is a high-density operational view. It loads:

- live command feed
- global features
- risk map
- risk-map coverage
- trust or reliability snapshots
- multiple lazy-loaded panels such as country drilldown, intelligence feed, behavioral analytics, signal integrity, mobility observability, and event streams

It also supports WebSocket-based live risk and country-risk-map updates.

### 12.4 Trend Prediction Page

This page acts like an analytics workbench. It surfaces:

- advanced ML predictions
- anomalies
- causal structures
- governance or reliability panels
- country comparisons
- history-based analytics

### 12.5 Historical Trends

The historical page supports timeline exploration, comparison, and export. This is useful in viva because it shows the system is not only real-time; it also supports retrospective analysis.

### 12.6 Scenario Studio

Scenario simulation lets the operator define market, sentiment, and weather shocks across steps. This demonstrates interactive decision support rather than passive monitoring.

### 12.7 Response Console

The response console maintains action tracking locally and supports event log style interaction. Even if some of the persistence is lighter here, it shows the project’s direction toward operational response, not just intelligence display.

### 12.8 Admin Interfaces

Admin pages visualize:

- health and readiness
- dependencies
- observability metrics
- model health
- validation history
- backtests
- security logs
- user access control

This is a strong full-stack argument: the same system supports analyst users and administrative operators.

### 12.9 Frontend Tradeoffs

The frontend makes heavy use of fallback data and graceful degradation. This is operationally practical, but the team should be transparent that in some failure modes the UI can still render synthetic or cached views rather than fully live data. That is a resilience feature, but it must be explained honestly to avoid misunderstanding.

## 13. Security Engineering View

Security is distributed across auth, transport, logging, admin control, and operational visibility.

### 13.1 Positive Security Features

- API key and JWT hybrid authentication
- role-based authorization for admin routes
- bcrypt password hashing
- active or inactive account state
- guard against self-deactivation for admins
- guard against removing the last active admin
- suspicious login and JWT-failure detection
- security event logging in MongoDB
- optional HTTPS enforcement
- secure WebSocket authentication path

### 13.2 Security Weaknesses or Demo-Only Areas

These should be answered honestly if challenged.

- Password reset tokens are stored in memory.
- The forgot-password path currently returns the reset token in the response, which is acceptable for demo or development but not for production.
- JWT secret has a code fallback value, so production must override it via environment variable.
- Frontend tokens are stored in local storage, which is practical but not as strong as httpOnly cookie strategies against XSS risk.
- The committed deployment assets mainly cover the backend and do not fully provision the surrounding infrastructure.

### 13.3 Security Logging as a Strength

Many student projects stop at “we used JWT.” This project goes further by storing security event logs and aggregated summaries. That gives the security engineers a strong discussion area in viva.

## 14. Deployment, Operations, and Scheduling

### 14.1 Local and Development Runtime

There are lightweight scripts such as `run_all.py` for launching a subset of collectors in parallel. The richer system behavior comes from `orchestrator.py`, which starts collectors, Kafka streaming, country-risk loops, and ML cycles.

### 14.2 Backend Deployment

The backend has:

- a Dockerfile
- a backend compose file
- a deployment README describing a server path and release environment file

The committed compose setup mainly runs the backend container and health checks it. This suggests the project’s deployment maturity is strongest for the API layer.

### 14.3 Scheduler

`scheduler/runner.py` performs:

- hourly lightweight model refresh
- daily forced retraining
- daily validation suite and backtests

This supports continuous model maintenance and governance.

### 14.4 Operational Reality

A fair viva answer is that the codebase demonstrates strong operational thinking, but a complete production environment would still need additional external infrastructure for MongoDB, Kafka, secrets management, TLS, reverse proxying, and perhaps centralized monitoring.

## 15. Functional Requirements Mapping

The existing project report already documents functional requirements, and the code largely supports them. Below is the viva-friendly mapping.

| Requirement Theme | Evidence in Code | Status |
|---|---|---|
| Multi-source ingestion | `collectors/*.py`, `orchestrator.py` | Implemented |
| Kafka-based asynchronous streaming | `backend/kafka_client.py`, `orchestrator.py`, `backend/country_risk_stream.py` | Implemented |
| MongoDB persistence | `database/mongo.py`, collector inserts, backend reads | Implemented |
| Global feature computation | `processing/global_mood.py`, backend feature routes | Implemented |
| Country risk feature computation | `processing/country_daily_risk.py`, country risk stream | Implemented |
| Global and country API access | `/features/global/*`, `/features/country/*` | Implemented |
| Live dashboard feed | `/dashboard/live-feed`, WebSockets | Implemented |
| Country risk map and drilldown | `/dashboard/risk-map`, `/dashboard/country/{country}` | Implemented |
| Advanced analytics | advanced analytics engine and frontend analytics pages | Implemented |
| Scenario analysis and decision support | scenario, counterfactual, policy replay, action plan endpoints | Implemented |
| User authentication and RBAC | auth routes and admin guards | Implemented |
| Admin monitoring and security logging | admin monitoring and security logs routes | Implemented |
| Analytics export | export endpoints and frontend export support | Implemented |
| Historical visualization | historical frontend pages and feature history APIs | Implemented |

## 16. Non-Functional Requirements Mapping

| Non-Functional Area | Implementation Evidence | Assessment |
|---|---|---|
| Security | API keys, JWT, bcrypt, admin guards, security events | Strong for student-project level |
| Performance protection | rate limiting, caching, lazy loading | Good |
| Reliability | health checks, fallback snapshots, retry logic, DLQ | Good |
| Observability | structured logs, runtime metrics, admin monitoring | Strong |
| Scalability | Kafka-based decoupling, MongoDB document model | Conceptually strong, infra still partial |
| Maintainability | modular collectors and processing modules | Good, though `backend/main.py` and `orchestrator.py` are large |
| Data quality | freshness, validation, evidence and quality flags | Strong |
| Usability | protected routes, admin pages, dashboard organization | Good |
| Deployment readiness | Dockerized backend and health check | Partial |
| Scientific validity | validation and backtesting modules | Good but limited by ground-truth scarcity |

## 17. Strong Points to Highlight in Viva

If the panel asks what is especially good about this project, these are the best answers.

### 17.1 It Is a Full Pipeline, Not a Single Model

The project covers ingestion, storage, streaming, feature engineering, modeling, security, frontend, and admin observability. That breadth is a major strength.

### 17.2 It Handles Heterogeneous Real-World Data

The system does not assume clean, single-domain, classroom data. It handles diverse signals and variable schemas.

### 17.3 It Includes Operational Quality Features

Many academic projects stop at dashboards and predictions. This project also includes:

- source health
- readiness checks
- security logs
- drift monitoring
- validation and backtests
- dead-letter handling
- degraded-mode behavior

### 17.4 It Is Honest About Confidence and Quality

Country intelligence and global mood include freshness, evidence, and quality semantics rather than presenting all outputs as equally authoritative.

### 17.5 The Frontend Is Role-Aware

There is a clear distinction between public, user, and admin flows.

## 18. Honest Limitations and How to Defend Them

Examiners often appreciate realistic engineering judgement more than overclaiming.

### 18.1 Limitation: Complete Infrastructure Is Not Fully Containerized in Repo

How to answer:

The application code strongly supports MongoDB and Kafka, but the committed deployment artifacts mainly package the backend. For a full production rollout, Kafka, MongoDB, reverse proxy, secrets management, and TLS would need to be provisioned outside or alongside the repo. We treated the backend deployment first because it was the central service boundary.

### 18.2 Limitation: Some Modules Use Fallback or Synthetic Data Paths

How to answer:

This was a deliberate resilience choice. The system prefers degraded visibility over total blank screens, but it also exposes quality, freshness, and source context so operators can distinguish live verified intelligence from derived fallback outputs.

### 18.3 Limitation: Ground Truth for Global Mood Is Sparse

How to answer:

That is a domain challenge rather than a coding omission. We addressed it by adding validation hooks, backtests, uncertainty, and explicit reporting of no-ground-truth cases instead of pretending the metric is perfectly supervised.

### 18.4 Limitation: Password Reset Flow Is Demo-Level

How to answer:

Yes. The current reset-token path is suitable for development and demonstration, not final production security. A real deployment would move token storage to persistent secure storage and deliver reset links through email instead of returning tokens in the API response.

### 18.5 Limitation: Large Core Files

How to answer:

`backend/main.py` and `orchestrator.py` are functionally rich and therefore large. The architectural separation still exists through collectors, processing modules, feature store, and ML modules. A future refactor would split the large files further into routers and services.

## 19. What Each Developer Should Own in the Viva

The team structure described by you is:

- 1 data engineer or software engineer focused on data engineering
- 3 software engineers
- 3 data scientists
- 2 computer security engineers

Below is a clean ownership map.

| Role | Best Areas to Claim |
|---|---|
| Data Engineer / Software Engineer | ingestion, Kafka, MongoDB schema strategy, feature pipelines, orchestrator, data freshness |
| Software Engineer 1 | backend API design, route structure, health checks, WebSockets, admin endpoints |
| Software Engineer 2 | frontend architecture, route guards, dashboard pages, API client, fallback UX |
| Software Engineer 3 | integration, deployment, scheduler, model registry wiring, end-to-end flow |
| Data Scientist 1 | country risk features, global mood scoring, signal fusion, evidence quality |
| Data Scientist 2 | forecasting, anomaly detection, advanced analytics, model fallback strategy |
| Data Scientist 3 | validation, backtesting, explainability, counterfactuals, AI reporting |
| Security Engineer 1 | authentication, authorization, password security, JWT and API key strategy |
| Security Engineer 2 | security event logging, suspicious activity detection, admin security monitoring, operational hardening |

## 20. Common Whole-System Viva Questions and Answers

### Q1. What is World Pulse in one sentence?

World Pulse is a secure real-time crisis intelligence platform that ingests multi-domain global signals, stores and fuses them, computes country and global risk analytics, and presents them through REST, WebSocket, and dashboard interfaces.

### Q2. Why did you combine backend, frontend, MongoDB, Kafka, and ML instead of building a smaller system?

Because the problem itself is end-to-end. Crisis intelligence is not solved by only a model or only a dashboard. We needed ingestion, persistence, asynchronous event flow, feature engineering, analytics, access control, and an operational UI to create a usable system.

### Q3. Why did you choose FastAPI?

FastAPI gave us strong typing through Pydantic, fast development speed, easy REST route definition, async support, automatic schema generation, and a good fit for Python-based data and ML modules already used elsewhere in the project.

### Q4. Why did you choose MongoDB instead of MySQL or PostgreSQL?

Our source data is heterogeneous, nested, and evolves frequently. MongoDB’s document model reduced schema friction for collector payloads and derived operational documents. It was especially useful for raw event storage, feature snapshots, and varied analytics records.

### Q5. Why did you choose Kafka?

Kafka gave us asynchronous decoupling between producers and consumers. Collectors can publish events once, and multiple downstream processors can consume them asynchronously. This improves scalability, resilience, and the ability to add new processing steps without changing source collectors.

### Q6. What is the main difference between raw data and engineered features in your system?

Raw data is the directly collected or lightly normalized external information, such as an article, an earthquake record, or a market value. Engineered features are derived metrics like country risk score, global mood score, source diversity, economic stress, and confidence values that summarize many raw observations into operational intelligence.

### Q7. How does the system generate a country risk score?

It fuses signals from country news, public attention, mobility, economics, logistics, weather, and rule-based escalation logic. It also tracks evidence quality, freshness, and supporting signal counts, so the score is not isolated from reliability context.

### Q8. How does the system generate a global score?

It aggregates recent global features and country-level evidence to produce system-wide measures such as global risk, global mood, forecast risk, and aggregate behavior or disruption indices. It explicitly models confidence and uncertainty.

### Q9. Is this a purely machine-learning system?

No. It is a hybrid system. It uses rules, heuristics, source-health logic, feature engineering, aggregation, and machine learning together. This is appropriate because operational intelligence requires more than a single predictive model.

### Q10. How do users access the platform securely?

Protected API routes require either a valid API key or a JWT bearer token. Admin routes additionally require admin role authorization. Passwords are hashed with bcrypt, and login activity is logged for auditing.

### Q11. What happens if Kafka becomes unavailable?

Producer sends may fail gracefully, and some live paths fall back to MongoDB-derived snapshots rather than leaving the dashboard completely blank. This does not fully replace streaming, but it improves degraded-mode behavior.

### Q12. What happens if the trained model is missing?

The system has fallback behavior through model bootstrapping and statistical alternatives in some advanced analytics modules. The backend also reports model-loaded status through health and observability endpoints so operators know whether the system is degraded.

### Q13. How do you know if your model is drifting?

The system stores prediction and monitoring documents, compares prediction inputs against recent historical baselines, computes drift metrics, and exposes monitoring summaries through admin observability endpoints.

### Q14. How do you measure whether the data is trustworthy?

We do not treat all data equally. The system tracks source health, freshness, quality flags, evidence levels, source counts, and validation results. Country intelligence also distinguishes between verified, stale, synthetic, and unknown conditions.

### Q15. Why are health and readiness endpoints separate?

Because a process can be alive but not ready. Liveness checks process availability. Readiness checks whether the service can actually serve traffic with its dependencies, such as MongoDB and model artifacts, functioning correctly.

### Q16. What is the role of the frontend beyond visualization?

The frontend is the operational interface. It handles secure route access, degradation logic, live updates, admin workflows, scenario simulation, historical exploration, and decision-support panels. It is not only a chart layer.

### Q17. What are the strongest engineering features of the project?

The strongest features are the multi-source architecture, Kafka-based decoupling, MongoDB document flexibility, explicit observability, security event logging, validation and backtesting modules, and graceful degraded-mode behavior in both backend and frontend.

### Q18. What are the biggest weaknesses?

The main weaknesses are partial production infrastructure packaging, sparse ground truth for some advanced metrics, some demo-oriented security flows like password reset token handling, and very large core files that would benefit from further modular refactoring.

## 21. Role-Specific Viva Questions and Answers

## 21.1 Data Engineer / Software Engineer Focused on Data Engineering

### Q1. What is your main contribution to the pipeline?

My contribution centers on ingestion, normalization, data movement, and feature availability. I worked on how external signals enter the system, how they are stored and streamed, how country and global features are refreshed, and how data quality and freshness are preserved for downstream analytics.

### Q2. Why is the collector layer modular instead of one unified script?

Each external source has unique schema, rate limits, authentication, failure modes, and parsing logic. Keeping collectors separate reduces coupling, improves maintainability, and lets us add or disable sources independently without breaking the rest of the ingestion pipeline.

### Q3. Why store raw data as well as processed data?

Raw data is important for traceability, debugging, replay, feature redesign, and model improvement. If we stored only processed features, we would lose the ability to audit how a signal was derived or rebuild better feature logic later.

### Q4. How is Kafka useful in your data pipeline?

Kafka decouples data producers from consumers. Collectors publish events once, and multiple downstream processors can consume them asynchronously. This improves scalability, resilience, and operational flexibility.

### Q5. Why are MongoDB and Kafka used together instead of choosing only one?

They solve different problems. Kafka is the streaming transport and event backbone. MongoDB is the persisted operational store for querying current and historical state. Kafka gives us flow, while MongoDB gives us durable operational retrieval and analytics context.

### Q6. How do you handle source failures?

The system tracks source health and freshness, logs issues, and can still operate in degraded mode. We distinguish between no signal and no source. That is why source-health tracking is stored separately and surfaced in observability and admin monitoring.

### Q7. What is the purpose of `country_source_events` and `country_signal_rollups`?

`country_source_events` stores normalized country-level event records derived from raw streams. `country_signal_rollups` aggregates them by country and date so we can recompute risk efficiently and provide structured downstream intelligence without repeatedly reprocessing all raw records.

### Q8. Why do feature documents include `mode` such as `online` and `offline`?

It separates live operational outputs from offline or analytical runs. This helps with validation, backtesting, retraining, and experiment control while keeping the live dashboard aligned to operational data only.

### Q9. How do you ensure MongoDB queries remain fast as data grows?

We create indexes on timestamp-heavy access paths, country and mode combinations, user lookups, and security event queries. We also design endpoints around latest snapshots and bounded history windows rather than naive full scans.

### Q10. If the panel asks whether this is a true data engineering system, what do you say?

Yes. The project includes ingestion from diverse sources, streaming, normalization, document persistence, historical storage, feature generation, quality checks, and operational freshness monitoring. Those are core data engineering concerns, not just application coding.

## 21.2 Software Engineer 1: Backend and API

### Q1. What did you build in the backend?

I worked on the FastAPI service layer that authenticates users, enforces role-based access, exposes feature and dashboard endpoints, streams live data over WebSockets, and provides health, observability, monitoring, and admin control capabilities.

### Q2. Why is `backend/main.py` large, and is that a problem?

It is large because it coordinates many route groups and operational concerns in one service entry point. The architecture is still modular underneath through processing, collector, and ML modules. It works functionally, but future refactoring should split it into routers and service classes for improved maintainability.

### Q3. How are protected endpoints implemented?

Protected endpoints depend on a verification layer that checks bearer JWT first and then API key fallback. Admin routes add a separate admin-role dependency. This provides both authentication and authorization.

### Q4. Why did you include both REST and WebSocket interfaces?

REST is best for on-demand retrieval, configuration, history, and admin interactions. WebSockets are better for low-latency live updates such as risk snapshots and streaming intelligence. Using both lets the frontend choose the right communication model for each interaction.

### Q5. What is the purpose of the request middleware?

It adds a request ID, measures request latency, updates runtime counters, optionally enforces HTTPS, and logs structured request information. This improves traceability, debugging, observability, and production readiness.

### Q6. How does the admin monitoring endpoint help operations?

It combines server health, dependency health, model readiness, latest ingestion times, source-health snapshots, mobility and economic observability, alerts, and uptime metrics into one response. This gives administrators a unified operations view instead of scattered status checks.

### Q7. What is the difference between `/health`, `/health/live`, and `/health/ready`?

`/health/live` checks process liveness. `/health/ready` checks service readiness, including MongoDB and model availability. `/health` is a general health summary. The separation follows good service-operation practice.

### Q8. How do you handle invalid JWTs or suspicious auth behavior?

JWT validation failures are recorded in `security_events`, counters are updated, and repeated failures from the same IP can trigger suspicious activity logging. This creates an auditable security trail and supports security monitoring.

### Q9. What happens when a WebSocket consumer cannot connect to Kafka?

The backend does not simply crash. It logs the failure, applies retry windows, and some WebSocket paths continue sending database-derived snapshots or keepalive messages so the UI remains partially functional in degraded mode.

### Q10. Why is FastAPI a good fit for this backend?

It integrates well with Python data and ML code, supports async patterns, makes request and response modeling easy through Pydantic, and allows rapid development of a large, typed, documented API surface.

## 21.3 Software Engineer 2: Frontend and UX

### Q1. What is the frontend’s role in this project?

The frontend turns the backend’s intelligence services into an operational product. It manages route protection, data fetching, retry logic, fallback behavior, live streaming, interactive analysis, and admin workflows for different user roles.

### Q2. Why did you use React and TypeScript?

React is well suited for large component-based dashboards with stateful interaction. TypeScript improves type safety, maintainability, and integration reliability when consuming a wide API surface with many data structures.

### Q3. How are routes protected?

The frontend uses protected-route logic for authenticated users and separate admin-route logic for admin-only pages. It checks token presence and current user role to prevent unauthorized navigation.

### Q4. Why is `api.ts` such an important file?

It centralizes API URL management, auth headers, retries, fallback switching, caching, WebSocket URL creation, and typed client functions. That keeps network logic consistent across the app and reduces duplication.

### Q5. What happens if the backend returns 401?

The frontend interceptor clears invalid auth state and redirects the user appropriately. This prevents stale or broken sessions from causing inconsistent UI behavior.

### Q6. Why did you include fallback and mock data paths?

Because operational dashboards are more useful if they degrade gracefully. During backend outages, network issues, or demos, the UI can still render structure and some context. We pair that with status or timestamp awareness so degraded data is not confused with fully live intelligence.

### Q7. What are the main dashboard capabilities?

The dashboard presents live risk feed, risk map, global intelligence, country drilldown, behavior and integrity panels, and event streams. It mixes top-line situational awareness with drilldown detail, which is important for operator use.

### Q8. Why did you create separate pages for trend prediction, historical trends, and scenario studio?

Because these are different user tasks. Trend prediction focuses on forecasting and analytics. Historical trends supports retrospective comparison and export. Scenario studio supports interactive what-if analysis. Splitting them improves usability and mental clarity.

### Q9. How does the frontend support admin users?

It provides dedicated pages for system monitoring, validation summaries, backtests, user access control, and security log inspection. This means admin functions are not mixed into normal analyst workflows.

### Q10. What is one strong frontend engineering decision in this project?

Centralizing API behavior, route protection, and fallback handling in shared services was a strong decision. It reduces inconsistent network logic and helps the UI remain stable even when the backend or data sources are partially degraded.

## 21.4 Software Engineer 3: Integration, Platform, and System Wiring

### Q1. What makes this role different from pure backend or frontend work?

This role focuses on end-to-end system wiring: how collectors, Kafka, MongoDB, processing modules, models, APIs, deployment artifacts, and schedulers fit together into one operational platform.

### Q2. What does `orchestrator.py` do?

It acts as a system-level coordinator. It starts collectors, starts Kafka consumption, preprocesses records, writes data lake artifacts, updates MongoDB, refreshes dashboard-related features, and can trigger ML cycles and country-risk flows.

### Q3. Why is the orchestrator threaded?

Because collectors and background processing tasks need to run concurrently. Threaded loops let the system keep fetching, consuming, recomputing, and updating live views without waiting for one sequential pipeline to finish before starting another.

### Q4. What is the purpose of the scheduler?

The scheduler automates lightweight refreshes, daily retraining, validation, and backtesting. It separates periodic model maintenance from request-time API behavior, which is good operational design.

### Q5. How is the backend deployed?

The repo provides a Dockerized backend with a compose file and deployment documentation aligned to a release-driven server layout. The backend is health-checked and designed to be restarted from updated image tags.

### Q6. What is still missing for full production deployment?

A full production setup would need infrastructure for MongoDB, Kafka, reverse proxying, certificate and secret management, network controls, and possibly centralized logs and metrics. The repo’s deployment assets are strongest for the backend service itself.

### Q7. Why is model registry integration important?

It prevents us from hardcoding one loose model file and gives us stage-based control over which model is in production. That makes model deployment more disciplined and auditable.

### Q8. How do integration components help reliability?

They define clear responsibilities and failure boundaries. For example, Kafka decouples producers and consumers, service-status tracking exposes stream health, and health endpoints separate backend readiness from raw process liveness.

### Q9. What is the practical value of degraded mode in an integrated system?

In real operations, temporary failure is normal. A degraded system that still provides partial situational awareness is more useful than a system that goes entirely blank. Integration work ensures those fallbacks are coordinated rather than accidental.

### Q10. If asked whether the architecture is scalable, what is the best answer?

Conceptually yes, because it uses modular collectors, Kafka-based event flow, MongoDB for flexible operational storage, and separated processing stages. Infrastructure hardening would still be required to realize that scalability in a fully production-grade deployment.

## 21.5 Data Scientist 1: Feature Engineering and Global Mood

### Q1. What is your main scientific contribution?

My focus is the design of derived signals: how raw heterogeneous observations are transformed into meaningful country and global features such as mood, pressure, disruption, confidence, evidence quality, and operational risk indicators.

### Q2. Why is feature engineering central in this project?

Because the raw sources are noisy, heterogeneous, and not directly suitable for operational interpretation. Feature engineering translates them into comparable, meaningful signals that models and dashboards can use consistently.

### Q3. What is `global_mood_score` conceptually?

It is an aggregate operational sentiment and stability indicator built from recent country-level evidence and global signal components. It is not just social-media sentiment. It reflects multiple domains and is accompanied by confidence and uncertainty.

### Q4. Why do you include confidence and uncertainty instead of only the score?

Because in crisis intelligence, incomplete coverage and uneven source quality are normal. A point estimate without uncertainty can be misleading. Confidence and uncertainty help decision makers interpret how much weight to place on the score.

### Q5. What is the value of behavior, context, attention, disruption, and economic-stress indices?

These indices decompose the global picture into interpretable components. Instead of saying only “risk is high,” we can explain whether the rise is driven by narrative escalation, physical disruption, attention spikes, or economic pressure.

### Q6. Why does the system verify country evidence before using it strongly?

Because not all country snapshots are equally trustworthy. Freshness, source diversity, evidence sufficiency, and multi-signal confirmation affect whether a country should heavily influence aggregate global outputs.

### Q7. What is the difference between direct behavior score and contextual pressure score?

Direct behavior score reflects more immediate, behaviorally visible tension or disruption. Contextual pressure score reflects underlying environmental, economic, or structural stress that may contribute to future escalation even if immediate visible behavior is lower.

### Q8. Why do quality labels like `verified`, `stale`, and `synthetic` matter?

They communicate whether an output is based on current multi-signal evidence, outdated information, or derived fallback logic. This improves scientific honesty and helps users avoid treating all outputs as equally grounded.

### Q9. How would you defend the scientific realism of the system?

I would say the design explicitly embraces uncertainty, multi-source disagreement, and incomplete coverage. Rather than hiding those issues, it exposes quality and validation context. That makes it more realistic than a system that outputs scores without any reliability semantics.

### Q10. What is one future improvement for this area?

A stronger labeled ground-truth framework for global mood and country event outcomes would improve calibration, evaluation, and supervised tuning of the feature aggregation rules.

## 21.6 Data Scientist 2: Forecasting, Anomaly Detection, and Advanced Analytics

### Q1. What advanced analytics does the system support?

It supports forecasting, anomaly detection, causal-style analytics, sentiment momentum analysis, and automated report generation. These are delivered through an advanced analytics engine that reads operational features and exposes higher-level insights.

### Q2. Why does the project include both LSTM and statistical fallback forecasting?

Because real systems need robustness. Deep learning can be useful when sufficient data and dependencies exist, but the platform should still function when TensorFlow or trained artifacts are unavailable. Statistical fallback preserves service continuity.

### Q3. What does multi-horizon prediction add?

It lets users view near-term and slightly longer-term outlooks instead of only one forecast point. In operational systems, different decisions require different horizons, such as immediate awareness versus next-day planning.

### Q4. How does anomaly detection help users?

It highlights unusual patterns that may not be obvious from average trends. This is important because crisis systems often need to detect sudden deviations or rare signal combinations, not only smooth trend changes.

### Q5. Why is a fallback anomaly detector acceptable?

Because the primary need is reliable service behavior. If a complex model is not available, a statistical detector still gives the operator useful signal-change awareness. It is better to provide transparent fallback analytics than to fail silently.

### Q6. What is sentiment momentum and why is it useful?

Sentiment momentum measures not just whether sentiment is positive or negative, but whether it is accelerating, decelerating, or crossing critical thresholds. In crises, rate of change can be more informative than static value.

### Q7. How should you talk about model performance in viva?

Carefully and honestly. We should say the system includes validation and backtesting, drift monitoring, and fallback behavior. We should not claim perfect forecasting. The purpose is decision support and risk estimation, not certainty.

### Q8. What does the advanced analytics engine contribute beyond the core prediction endpoint?

It offers a broader analytic layer by combining several specialized modules into a single insight interface. That makes the platform useful not only for live monitoring but also for interpretation, diagnosis, and exploratory analysis.

### Q9. Why does this project need anomaly detection if it already has a risk score?

Risk scores summarize expected conditions, but anomalies reveal unusual deviations. A system can have moderate overall risk yet still experience highly abnormal movements that deserve attention. The two analytics serve different purposes.

### Q10. What future improvement would strengthen this area?

A stronger model lifecycle with richer benchmark datasets, automated retraining criteria, and more extensive quantitative evaluation across horizons would improve robustness and scientific confidence.

## 21.7 Data Scientist 3: Validation, Explainability, and Decision Support

### Q1. What do you mean by validation in this system?

Validation means checking how well derived risk outputs align with available ground truth or backtesting logic over time. It includes summary status, stored validation history, and explicit reporting of when data is insufficient for meaningful validation.

### Q2. Why are backtests important?

Backtests give us historical evidence about whether the model and feature logic would have behaved reasonably on prior windows. They are not a guarantee of future performance, but they are essential for governance and credibility.

### Q3. What is the purpose of causal explanations?

Causal explanations aim to show influential relationships or drivers behind a risk outcome, making the system more interpretable. They help users understand why a score moved rather than only observing that it changed.

### Q4. What is a counterfactual in this project?

A counterfactual asks “what would happen if certain signal values changed?” For example, if sentiment shock or market shock were lower, how might the risk output differ? This helps with what-if reasoning and decision support.

### Q5. What is policy replay?

Policy replay simulates the impact of interventions across a future horizon using the system’s scenario logic. It helps users think about possible outcomes of different response strategies in a structured way.

### Q6. Why are action recommendations included?

They move the platform from passive intelligence toward actionable support. A decision-support system is more useful when it can suggest next steps or priorities based on observed conditions, while still leaving human judgment in control.

### Q7. How do you defend explainability if the system is partly heuristic and partly ML?

That is actually a strength. Explainability in complex operational systems does not have to come only from one black-box model explanation method. Here, we combine interpretable feature components, rule logic, validation artifacts, and causal-style summaries.

### Q8. What is the purpose of AI-generated reports?

They summarize analytic outputs into human-readable narratives, making it easier for operators to interpret complex model and feature outputs quickly. This improves usability and communication, especially in time-sensitive environments.

### Q9. What is the most honest challenge in this area?

The hardest challenge is evaluation quality, especially when true labeled outcomes are sparse or delayed. That is why we expose validation status and history instead of pretending every explainability or forecast output is fully proven.

### Q10. Why should examiners consider this a serious analytics contribution?

Because the system includes not only scoring but also validation, backtesting, explainability, counterfactual reasoning, policy replay, and narrative reporting. That is a broad and mature analytics toolkit for a student project.

## 21.8 Security Engineer 1: Authentication and API Security

### Q1. What security architecture did you implement?

We implemented a layered approach with API key authentication, JWT bearer tokens for user sessions, role-based authorization for admin routes, bcrypt password hashing, account activation state, optional HTTPS enforcement, and structured security event logging.

### Q2. Why support both API keys and JWT?

They serve different use cases. API keys are practical for service access, scripts, and simple protected clients. JWTs are better for user login sessions and carrying identity details such as role and user type.

### Q3. How are passwords protected?

Passwords are hashed using bcrypt via Passlib with 12 rounds. The code also handles bcrypt input-length limitations safely before hashing. Plain passwords are never stored.

### Q4. How do you prevent unauthorized access to admin endpoints?

Admin endpoints use explicit admin-role dependencies. Even if a user is authenticated, non-admin identities are rejected with HTTP 403. Authorization is separate from authentication.

### Q5. What happens on failed login attempts?

Failed attempts are recorded in the security log with metadata such as email and client IP. Repeated failures within a window can trigger suspicious activity events. This supports detection as well as auditing.

### Q6. How is JWT misuse monitored?

Invalid or failed JWT validations are recorded as security events, and repeated failures from an IP can trigger suspicious activity logging. This helps identify token abuse, expired-token churn, or attack patterns.

### Q7. What is the purpose of admin invite code logic?

It prevents unrestricted admin self-registration. A normal user can register directly, but administrative accounts require an additional secret invite code, which reduces privilege escalation risk.

### Q8. What security issue would you fix first for production?

I would replace the current password-reset development flow with secure persistent token storage and proper email-based delivery. I would also ensure strong secret management for JWT and API keys and review frontend token storage strategy.

### Q9. Why is optional HTTPS enforcement useful?

It lets development remain practical on localhost while allowing stricter enforcement in secured environments. In production, transport encryption should be mandatory to protect tokens and credentials in transit.

### Q10. How would you summarize the maturity of security in this project?

For a student project, it is above average because it includes real authentication, authorization, logging, and suspicious activity tracking. It is still not full enterprise security, but it clearly goes beyond superficial login implementation.

## 21.9 Security Engineer 2: Monitoring, Logging, and Operational Security

### Q1. What is operational security in this project?

Operational security here means monitoring how the live system behaves, recording suspicious and security-relevant events, exposing admin visibility, and making sure failures, degraded states, and abuse patterns can be detected rather than hidden.

### Q2. Why are security logs stored in MongoDB?

Because they need to be queryable, timestamped, filterable, and available to admin dashboards. Storing them centrally lets the system generate summaries and recent-event lists for operational review.

### Q3. What does the admin security logs endpoint provide?

It provides aggregated counts of login attempts, success, failure, blocked activity, suspicious events, JWT validation monitoring, and recent event details over a configurable time window.

### Q4. How does the backend support observability more broadly?

It uses structured JSON logs, runtime request counters, prediction counters, model monitoring collections, health checks, dependency checks, source-health snapshots, and system-monitoring responses that summarize operational status.

### Q5. Why is source health relevant to security or operations?

Because missing or broken sources can create false confidence. Operational security includes awareness of the sensing environment itself. If data sources are down or rate limited, the organization must know that the intelligence picture is degraded.

### Q6. What is the purpose of dead-letter handling in security or reliability terms?

It preserves failed events for inspection instead of silently dropping them. From an operational and forensic standpoint, that is important because hidden failures are more dangerous than visible failures.

### Q7. How do you stop admins from locking the system out of admin access?

The backend prevents demoting or deactivating the last active admin account, and it also blocks self-deactivation in the current admin workflow. That protects administrative continuity.

### Q8. Why are runtime counters useful?

They let us compute uptime statistics, request volumes, error rates, and prediction activity. Those metrics help distinguish between isolated issues and broader operational degradation.

### Q9. What would be your next improvement in this area?

I would add centralized alerting, external SIEM or log shipping integration, stronger secrets management, and possibly rate-limit or IP-ban responses tied to repeated suspicious activity patterns.

### Q10. What is your strongest argument that security was treated seriously?

The system does not stop at login. It records security events, aggregates them for admin inspection, applies role checks, monitors suspicious activity, and integrates security status into operational monitoring. That shows security was part of the architecture, not an afterthought.

## 22. Non-Technical and Management-Oriented Viva Questions

### Q1. Why is this project useful to society or organizations?

It helps decision makers combine fragmented global signals into a more actionable intelligence picture. That can support earlier awareness, better prioritization, and more informed response planning in complex crisis environments.

### Q2. Who are the stakeholders?

Potential stakeholders include analysts, policymakers, humanitarian or NGO teams, researchers, emergency planners, and administrative operators who need secure access to real-time cross-domain intelligence.

### Q3. What was the biggest project management challenge?

The biggest challenge was integrating many heterogeneous domains and keeping the platform coherent. Different team members had to align data formats, risk semantics, API contracts, frontend expectations, and validation logic.

### Q4. How did the team divide responsibilities effectively?

The system naturally divides by pipeline stage and specialty: data engineering for ingestion and storage, software engineering for backend and frontend, data science for feature logic and analytics, and security engineering for auth and monitoring.

### Q5. What ethical issues exist in a crisis intelligence platform?

Ethical issues include data bias, incomplete coverage, overconfidence in scores, privacy concerns in certain sources, and the risk of users treating outputs as certain truth. That is why confidence, validation, source health, and transparency matter.

### Q6. What does success look like for this project?

Success means the system can ingest diverse live signals, produce coherent and explainable country and global intelligence, expose it securely to different users, and remain observable and manageable under partial failure conditions.

### Q7. What would you improve if you had another semester?

I would strengthen infrastructure automation, broaden labeled evaluation datasets, refactor very large service files, harden the password reset and token strategy, and add more formal automated test coverage.

### Q8. Did the team prioritize breadth over depth?

We aimed for both, but yes, this is a broad system. The important point is that the breadth is not superficial: each layer has meaningful implementation. Where depth remains limited, such as full infra automation or some evaluation datasets, we are transparent about it.

## 23. Fast Functional vs Non-Functional Defense Lines

If the panel asks for functional requirements, say they describe what the system does:

- ingest data
- store data
- compute features
- predict risk
- expose dashboards and APIs
- authenticate users
- support admin monitoring

If the panel asks for non-functional requirements, say they describe how well the system should do it:

- securely
- reliably
- with observability
- with acceptable performance
- with maintainability
- with scalability potential
- with usable role-based interfaces

## 24. Quick Answer Templates for Tough Questions

### “Why didn’t you use a relational database?”

Because the project stores many semi-structured event payloads and evolving analytical documents. MongoDB gave us faster iteration and a better fit for variable schemas, while indexes still supported our key query patterns.

### “Why didn’t you build full production infrastructure?”

We prioritized core system capability first: ingestion, intelligence generation, secure API delivery, and dashboard usability. The code is structured to support production deployment, but full infrastructure automation was a future-hardening step.

### “How can we trust your model?”

We do not ask users to trust it blindly. We expose validation, backtesting, drift monitoring, quality flags, confidence and uncertainty, and source-health context. The model is part of a decision-support system, not a magic oracle.

### “What is innovative here?”

The innovation is the combination of heterogeneous global signals, country and global intelligence layers, live operational delivery, explainability and what-if modules, and explicit observability and security controls in one integrated student-built platform.

### “What is the single most important file in the system?”

There is no single file from a design perspective, but if I had to name the central runtime coordinators, they would be `backend/main.py` for service delivery and `orchestrator.py` for pipeline coordination.

## 25. Final Viva Advice for the Team

### 25.1 Do Not Memorize Only Definitions

The panel is likely to ask “why” and “what happens if.” Learn the story of data moving through the system.

### 25.2 Be Honest About Limitations

Honest, precise answers create trust. Saying “that part is development-grade and here is how we would harden it” is stronger than pretending everything is already enterprise-ready.

### 25.3 Keep the Core Narrative Consistent

A strong shared storyline is:

World Pulse ingests global multi-domain data, streams and stores it, engineers country and global intelligence, uses analytics and ML to detect risk and trends, and exposes everything through a secure monitored dashboard.

### 25.4 Each Member Should Know Three Things Deeply

Every team member should be able to explain:

1. their own module
2. how their module connects to the next one
3. one limitation and one future improvement for their area

### 25.5 Best Closing Line in a Viva

If you need a confident closing line, use this:

This project is not just a model or just a dashboard; it is an end-to-end crisis intelligence platform with ingestion, streaming, persistence, feature engineering, analytics, security, observability, and role-based operational delivery. Our biggest achievement was integrating those layers coherently, and our next step would be production hardening and deeper evaluation.

## 26. Appendix A: API and Endpoint Cheat Sheet

The backend API surface is large. The easiest way to revise it is by groups instead of memorizing every exact path.

### 26.1 Raw Data Access Groups

These routes expose or sample raw collections:

- news
- GDELT
- wiki attention
- trends
- earthquakes
- weather
- crypto
- economics
- health data
- stocks
- World Bank data

### 26.2 Feature Access Groups

These routes expose:

- latest global features
- historical global features
- global features by version
- latest country features
- country feature history by country code

### 26.3 Dashboard and Intelligence Groups

These routes expose:

- live dashboard feed
- risk map and risk map coverage
- country drilldown and country intelligence
- disaster monitor
- crypto pulse
- economic indicators
- health alerts
- trends radar
- governance and trust views
- Sentinel outputs

### 26.4 Decision Support Groups

These routes expose:

- scenario simulation
- causal explanations
- counterfactual analysis
- action recommendations
- policy replay

### 26.5 Admin and Operations Groups

These routes expose:

- auth and profile management
- admin user management
- health and readiness
- dependency health
- observability metrics
- model observability
- streaming observability
- validation and backtest summaries
- system monitoring
- security logs

### 26.6 Live Streaming Groups

These WebSocket routes expose:

- live risk snapshots
- live country risk map updates
- live Sentinel event streams

## 27. Appendix B: MongoDB Collection Cheat Sheet

If someone asks for collection examples, answer from these groups.

### 27.1 Raw Collections

Examples are `news`, `gdelt`, `wiki`, `trends`, `earthquakes`, `weather`, `health`, `economics`, `stocks`, `crypto`, `worldbank`, `mobility`, `aviation`, and `logistics`.

### 27.2 Derived Intelligence Collections

Examples are `country_news`, `country_features`, `global_features`, `dashboard_features`, `country_source_events`, and `country_signal_rollups`.

### 27.3 Governance and Monitoring Collections

Examples are `prediction_logs`, `model_monitoring`, `source_health`, and `service_status`.

### 27.4 Security and Access Collections

Examples are `users`, `security_events`, and `operator_events`.

### 27.5 Explainability and Decision Support Collections

Examples are `causal_explanations`, `counterfactual_runs`, `policy_replays`, `action_recommendations`, and `sentinel_feedback`.

## 28. Appendix C: Rapid-Fire Viva Bank

### Q1. Why not a monolithic database schema?

Because the data is heterogeneous and evolves quickly. A document model reduced schema friction.

### Q2. Why not call external APIs directly from the frontend?

Because the backend centralizes authentication, normalization, rate control, auditing, and security.

### Q3. Why store source-health data separately?

So we can distinguish calm conditions from missing or failing upstream sources.

### Q4. Why are timestamps everywhere?

Because freshness is central in operational intelligence and live dashboards.

### Q5. Why keep historical features?

For trend analysis, drift checks, backtesting, and retrospective review.

### Q6. Why are some analytics probabilistic rather than deterministic?

Because crisis risk involves uncertainty, incomplete coverage, and noisy observations.

### Q7. Why use rate limiting?

To protect backend capacity and reduce abuse or accidental overload.

### Q8. Why expose admin-only endpoints?

Because operational and security controls should not be available to all users.

### Q9. Why is liveness alone not enough?

A process can be running while dependencies are broken.

### Q10. Why use WebSockets at all?

To push low-latency updates without repetitive polling.

### Q11. Why is a dead-letter queue useful?

It preserves failed events for later investigation instead of losing evidence.

### Q12. Why not trust every source equally?

Because data quality, freshness, and reliability vary across providers and time windows.

### Q13. Why do you need model registry stages?

To separate candidate models from the active production model.

### Q14. Why include scenario simulation?

Because operators need what-if reasoning, not only passive monitoring.

### Q15. Why is validation history useful?

It shows whether the system is improving, degrading, or remaining stable over time.

### Q16. Why mention uncertainty in a demo?

Because responsible analytics should communicate confidence, not hide it.

### Q17. Why is local storage token handling a tradeoff?

It is practical for frontend apps, but it increases XSS sensitivity compared with httpOnly cookies.

### Q18. Why are large files still acceptable in a student system?

They are acceptable if functionality is clear, but they should be refactored later for maintainability.

### Q19. Why use both live and historical pages?

Live views support immediate awareness, while historical views support analysis and evaluation.

### Q20. Why is this project not “just a dashboard project”?

Because it includes ingestion, streaming, storage, feature engineering, ML, security, observability, and admin workflows.

## 29. Appendix D: Thirty-Second Self-Introductions for Each Role

### Data Engineer Intro

I worked on the data pipeline side of World Pulse, especially source ingestion, Kafka flow, MongoDB persistence, normalization, and feature availability. My responsibility was to make sure heterogeneous real-world signals could reliably enter the system and remain usable for downstream analytics and dashboards.

### Backend Engineer Intro

I worked on the FastAPI backend, including secure route design, authentication, admin controls, health checks, observability, and WebSocket delivery. My focus was turning the intelligence pipeline into a secure service layer that the frontend and operators could use.

### Frontend Engineer Intro

I worked on the React and TypeScript frontend, including protected routes, dashboard composition, analytics pages, API integration, retry and fallback behavior, and admin interfaces. My focus was making the system usable for analysts and administrators in a live environment.

### Integration Engineer Intro

I worked on system integration, which means wiring collectors, streaming, persistence, backend delivery, scheduler jobs, and deployment assets into one coherent architecture. My focus was end-to-end flow and operational continuity.

### Data Scientist Intro

I worked on feature engineering and analytics for crisis intelligence, including risk features, global mood, forecasting, anomaly detection, validation, and explainability modules. My focus was turning raw signals into interpretable and defensible intelligence outputs.

### Security Engineer Intro

I worked on authentication, authorization, password security, security event logging, suspicious activity detection, and security monitoring features. My focus was ensuring that the system was not only functional but also accountable and safe to operate.

---

Prepared from the implementation evidence in core backend, collector, processing, machine-learning, feature-store, deployment, scheduler, and frontend modules in this repository.
