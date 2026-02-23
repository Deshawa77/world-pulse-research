# Security and Observability

## Required environment variables

Set these in `.env` at project root:

```env
API_KEY=super_secure_api_key
ADMIN_KEY=admin_secret_key
```

Optional key expansion:

```env
USER_API_KEYS=key1,key2,key3
ADMIN_API_KEYS=admin1,admin2
```

## HTTPS / TLS

Enable HTTPS enforcement in production:

```env
REQUIRE_HTTPS=true
ALLOW_INSECURE_LOCALHOST=false
```

Run API with certs:

```env
TLS_CERT_FILE=C:/path/to/fullchain.pem
TLS_KEY_FILE=C:/path/to/privkey.pem
```

Start:

```bash
python -m backend.run_secure
```

## Observability endpoints

- `GET /health/live` (no auth): process liveness
- `GET /health/ready` (auth): db/model readiness
- `GET /observability/metrics` (admin): runtime counters + security posture
- `GET /observability/model?window=200` (admin): prediction probability/drift summary

## Logging

JSON structured logs are emitted to stdout by default.

Optional file sink:

```env
STRUCTURED_LOG_FILE=logs/structured_api.log
```
