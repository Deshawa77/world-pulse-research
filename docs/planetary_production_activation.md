# Planetary Intelligence Production Activation

This document covers the remaining environment and deployment work needed after the repository implementation is complete.

## Runtime Worker

The planetary runtime already supports continuous materialization inside the backend through the built-in scheduler in [C:\Projects\world-pulse-research\backend\main.py](C:\Projects\world-pulse-research\backend\main.py).

For deployments that prefer a standalone worker, use:

```powershell
python scripts/run_planetary_runtime_scheduler.py --interval-seconds 300 --source-refresh-interval-seconds 900 --backtest-interval-seconds 21600
```

For local development, bring the frontend, backend, scheduler, and warm materialization up together with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_planetary_local_stack.ps1
```

The local stack scripts are:

- [C:\Projects\world-pulse-research\scripts\restart_frontend.ps1](C:\Projects\world-pulse-research\scripts\restart_frontend.ps1)
- [C:\Projects\world-pulse-research\scripts\restart_planetary_runtime_scheduler.ps1](C:\Projects\world-pulse-research\scripts\restart_planetary_runtime_scheduler.ps1)
- [C:\Projects\world-pulse-research\scripts\start_planetary_local_stack.ps1](C:\Projects\world-pulse-research\scripts\start_planetary_local_stack.ps1)
- [C:\Projects\world-pulse-research\run_planetary_local_stack.bat](C:\Projects\world-pulse-research\run_planetary_local_stack.bat)

For a one-shot manual materialization:

```powershell
python scripts/run_planetary_runtime_materialize.py --run-backtests
```

## Recommended Environment Settings

- `PLANETARY_RUNTIME_ENABLED=true`
- `PLANETARY_RUNTIME_STARTUP_WARM=true`
- `PLANETARY_RUNTIME_INTERVAL_SECONDS=300`
- `PLANETARY_RUNTIME_SOURCE_REFRESH_INTERVAL_SECONDS=900`
- `PLANETARY_RUNTIME_BACKTEST_INTERVAL_SECONDS=21600`

## Provider Wiring

Provider activation remains environment-specific. The repo is ready for:

- behavior and public-signal provider credentials
- internet telemetry provider credentials
- disaster and weather provider credentials
- deployment secret-manager bindings

Keep live credentials out of the repository and inject them via deployment environment variables or mounted secret files.

Use [C:\Projects\world-pulse-research\config\planetary_provider_activation.env.example](C:\Projects\world-pulse-research\config\planetary_provider_activation.env.example) as the starting activation template for runtime, provider, smoke, and threshold variables.

## Deployment Hardening Checklist

- run the backend with the planetary runtime enabled
- run `python scripts/run_planetary_validation.py` after deploy
- run `node scripts/check_planetary_browser_smoke.mjs --headless` against the target frontend/backend URLs
- verify runtime manifest freshness stays below the operational threshold
- verify graph/fusion persistence continues to populate without page-hit seeding
- review latest disaster backtests before enabling aggressive alert thresholds

## Threshold Tuning Workflow

1. Materialize a fresh runtime snapshot with backtests.
2. Review `scripts/run_planetary_validation.py` output.
3. Inspect `disaster_backtests` for flood and cyclone precision/recall drift.
4. Tune provider-side or forecast-side thresholds in the environment, not in ad hoc frontend logic.
   Runtime knobs now include `PLANETARY_FLOOD_SIGNAL_RAIN_THRESHOLD`, `PLANETARY_FLOOD_SIGNAL_WIND_THRESHOLD`, `PLANETARY_CYCLONE_SIGNAL_WIND_THRESHOLD`, `PLANETARY_FLOOD_ACTIVE_THRESHOLD`, `PLANETARY_FLOOD_CRITICAL_THRESHOLD`, `PLANETARY_CYCLONE_ACTIVE_THRESHOLD`, and `PLANETARY_CYCLONE_CRITICAL_THRESHOLD`.
5. Re-run the materialization and validation passes.
