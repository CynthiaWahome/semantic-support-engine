# Slack Support Assistant

A standalone application reproducing selected features contributed by Cynthia
Wahome to Thanos, reusing the existing implementation where appropriate.

## Current status

FastAPI scaffold only. Slack messaging, spreadsheet knowledge-base sync, Q&A
ingestion, semantic retrieval, and onboarding have not yet been migrated.

## Run locally

Requires Python 3.13+ and uv. From this repository directory:

```sh
uv sync --locked
uv run --no-sync uvicorn app.main:app --reload
```

`uv sync` installs dependencies into the project's `.venv`. The server runs at
`http://127.0.0.1:8000`; interactive API documentation is available at `/docs`.
`GET /health` returns `{"status":"ok"}` and checks application liveness only.
The scaffold requires no Slack account, credentials, or external service.

## Structure

```text
app/
  main.py                 Application factory and entry point
  views/                  HTTP handlers and central router
  services/               Business logic shared across interfaces
  schemas/                Pydantic request and response contracts
  models/                 Database entities and persistence mappings
  repositories/           Database queries and persistence access
  integrations/           External adapters: Slack, Sheets, embeddings
  core/                   Shared configuration, logging, lifecycle
tests/
  test_health.py          HTTP contract test
.github/
  PULL_REQUEST_TEMPLATE.md
```

The HTTP flow is `views → services → repositories/integrations`. Views use
schemas to validate input and serialize output; repositories use database
models for persistence. Services do not depend on HTTP requests or Slack event
objects, allowing the same feature logic to serve both interfaces.

The liveness endpoint demonstrates `views/health.py → services/health.py`, with
its response contract in `schemas/health.py`. The persistence, integrations, and
core packages currently establish boundaries only; concrete implementations
will arrive with the corresponding features. No database or ORM is configured
yet. Register new HTTP routers in `views/router.py`.

## Verification

```sh
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync pytest -q
```

## Contribution workflow

See [CONTRIBUTING.md](CONTRIBUTING.md). The initial scaffold seeds `main`;
`dev` is created from it and becomes the default branch. Subsequent changes use
feature branches and template-based PRs targeting `dev`.
