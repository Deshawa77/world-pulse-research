# Internet Map Production Activation

## Goal

Activate the Real-Time Internet Map in a production environment without storing secrets in the repository.

## 1. Rotate and externalize secrets

Generate a fresh local secret bundle:

```powershell
python scripts/rotate_runtime_secrets.py --output config/runtime-secrets.local.json --force
```

For deployed environments, mount a non-repo secret file and point the app at it with:
- `WORLD_PULSE_ENVIRONMENT=production`
- `WORLD_PULSE_ENABLE_DOTENV_FALLBACK=false`
- `WORLD_PULSE_SECRETS_FILE=/run/secrets/world-pulse-runtime.json`

The runtime secret file should contain:
- `JWT_SECRET`
- `API_KEY`
- `ADMIN_KEY`
- provider endpoint and auth values such as `INTERNET_MAP_BGP_FEED_URL` and `INTERNET_MAP_BGP_FEED_BEARER_TOKEN`

Use [runtime-secrets.example.json](/c:/Projects/world-pulse-research/config/runtime-secrets.example.json) as the shape reference.

## 2. Attach provider endpoints

Validate that every Internet Map family is configured for live provider use:

```powershell
python scripts/check_internet_map_provider_config.py --require-live
```

Optional probe mode:

```powershell
python scripts/check_internet_map_provider_config.py --require-live --probe --timeout-sec 5
```

Families validated:
- BGP routing
- CDN traffic
- ISP telemetry
- Cloud metrics

## 3. Deploy the runtime worker

Use the example compose file at [internet-map.docker-compose.example.yml](/c:/Projects/world-pulse-research/deploy/internet-map.docker-compose.example.yml).

Production pattern:
- API containers: `INTERNET_MAP_RUNTIME_ENABLED=false`
- Singleton runtime worker: `INTERNET_MAP_RUNTIME_ENABLED=true`

This prevents multiple API replicas from each running their own ingestion scheduler.

## 4. Run rollout checks

After deployment, run:

```powershell
python scripts/run_internet_map_rollout_checks.py --base-url https://your-api.example.com --admin-api-key <admin-key>
```

This checks:
- cold refresh latency
- warm-cache latency
- SSE delivery
- alert action workflow
- admin queue refresh
- backtest execution
- maintenance pruning

## 5. Calibrate live thresholds

Generate a recommended threshold override file from the latest backtest:

```powershell
python scripts/tune_internet_map_thresholds.py --write --output config/internet-map-thresholds.local.json
```

The runtime can load that file with:
- `INTERNET_MAP_THRESHOLD_CONFIG_FILE=config/internet-map-thresholds.local.json`

Use [internet-map-thresholds.example.json](/c:/Projects/world-pulse-research/config/internet-map-thresholds.example.json) as the config shape reference.
