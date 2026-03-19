# GitHub Actions Setup

## Workflows Added

- `.github/workflows/ci.yml`
  - runs on every pull request and push to `main`
  - checks backend syntax/import safety
  - runs lightweight backend unit tests
  - runs frontend typecheck and frontend build

- `.github/workflows/deploy-backend.yml`
  - runs on push to `main`
  - also supports manual `workflow_dispatch` for rollback or redeploy
  - builds a backend Docker image
  - tags it with the commit SHA
  - pushes it to GHCR
  - uploads the production compose file from this repo
  - deploys from the image over SSH using Docker Compose
  - runs a post-deploy backend healthcheck with retries

## Exact Server Layout

Use this server directory:

```text
/opt/world-pulse-research/backend/
  .env
  .backend-release.env
  docker-compose.backend.yml
```

The repo now includes the compose file at:

- `deploy/backend/docker-compose.backend.yml`

The deploy workflow uploads that file into `DEPLOY_PATH` before pulling and restarting the container.

## GitHub Secrets Required

Add these in `Settings -> Secrets and variables -> Actions`:

- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PATH`
- `GHCR_USER`
- `GHCR_PAT`
- `BACKEND_HEALTHCHECK_URL`

Recommended values:

- `DEPLOY_PATH=/opt/world-pulse-research/backend`
- `BACKEND_HEALTHCHECK_URL=http://127.0.0.1:8000/health`

## Branch Protection

Set `CI` as a required status check for `main` in:
`Settings -> Branches -> Branch protection rules`

## Remote Deploy Contract

The deploy workflow assumes:

- Docker and Docker Compose are installed on the server
- the deploy user can run Docker
- `.env` already exists in `DEPLOY_PATH`
- GHCR credentials can pull the image

For the first bootstrap, use:

- `deploy/backend/.env.example`
- `deploy/backend/README.md`
