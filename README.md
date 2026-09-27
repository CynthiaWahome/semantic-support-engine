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
  api/routes/health.py    Liveness endpoint
tests/
  test_health.py          HTTP contract test
.github/
  PULL_REQUEST_TEMPLATE.md
```

Feature modules will be introduced as the corresponding features are migrated.

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
