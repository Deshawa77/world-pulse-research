# Backend Server Layout

Recommended production layout on the server:

```text
/opt/world-pulse-research/backend/
  .env
  .backend-release.env
  docker-compose.backend.yml
```

## Files

- `.env`: long-lived runtime secrets and backend environment variables
- `.backend-release.env`: written by GitHub Actions on each deploy with image repo and tag
- `docker-compose.backend.yml`: uploaded by the deploy workflow from this repo

## GitHub Secret Mapping

Set `DEPLOY_PATH` to the exact directory above, for example:

```text
/opt/world-pulse-research/backend
```

## First-Time Server Bootstrap

1. Install Docker Engine and Docker Compose plugin.
2. Create the deploy directory:
   `sudo mkdir -p /opt/world-pulse-research/backend`
3. Copy your real environment file into place as `.env`.
4. Ensure the deploy user can run Docker.
5. Add a reverse proxy or firewall rule for port `8000` if needed.

After that, GitHub Actions will upload `docker-compose.backend.yml`, write `.backend-release.env`, pull the tagged GHCR image, and restart only the backend service.
