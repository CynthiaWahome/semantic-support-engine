# Support Answering Platform

## From scattered team knowledge to answers people can trust.

An ETL-backed semantic support engine that turns spreadsheets, reviewed
question-and-answer records, and curated conversation history into searchable,
policy-aware answers.

Slack is the first delivery adapter. The answering core is designed to serve
other team platforms without duplicating retrieval, fallback, or safety logic.

![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white&style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white&style=for-the-badge)
![Slack Bolt](https://img.shields.io/badge/Slack_Bolt-4A154B?logo=slack&logoColor=white&style=for-the-badge)
![FAISS](https://img.shields.io/badge/FAISS-Semantic_Search-36C5F0?style=for-the-badge)
![Google Sheets](https://img.shields.io/badge/Google_Sheets-Sync-34A853?logo=googlesheets&logoColor=white&style=for-the-badge)
![Upstash Redis](https://img.shields.io/badge/Upstash_Redis-State-DC382D?logo=redis&logoColor=white&style=for-the-badge)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?logo=pytest&logoColor=white&style=for-the-badge)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black&style=for-the-badge)

## The problem

Teams repeatedly answer the same questions, but the answers are scattered
across spreadsheets, conversations, pinned messages, and internal documents.
That creates duplicated effort, inconsistent guidance, and knowledge that is
easy to lose.

## The solution

Support Answering Platform creates a controlled path from knowledge to answer:

```text
Ingest → validate → index → retrieve → safeguard → answer
```

It searches approved knowledge first, preserves known keyword answers when
semantic confidence is low, and applies policy checks before anything is sent
back to the user.

## What makes it more than a chatbot

- **A real ETL pipeline** — structured knowledge is extracted, transformed,
  validated, reviewed, and loaded into serving artifacts.
- **Controlled retrieval** — semantic search is backed by approved records and
  an explicit confidence threshold.
- **Safe fallback behavior** — uncertain questions use existing approved answers
  instead of unsupported generated responses.
- **Policy-aware delivery** — blocked topics, rate limits, caching, notifications,
  and duplicate-event protection run inside the answer path.
- **Reusable core services** — Slack is an adapter, not the source of the
  retrieval or policy logic.

## Architecture

```text
Knowledge sources
      ↓
ETL and curation
      ↓
Semantic index + approved answers
      ↓
Answer service and safeguards
      ↓
Slack thread today · other adapters later
```

## Explore the engineering

- [Architecture](docs/ARCHITECTURE.md)
- [Data pipelines](docs/DATA_PIPELINES.md)
- [Configuration](docs/CONFIGURATION.md)

## Run locally

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
cp -n .env.example .env
uv run --env-file .env --no-sync uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`; interactive documentation is available
at `/docs`.

Run the quality checks:

```sh
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```
