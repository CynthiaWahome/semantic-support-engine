# Support Answering Platform

![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white&style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white&style=for-the-badge)
![Slack Bolt](https://img.shields.io/badge/Slack_Bolt-4A154B?logo=slack&logoColor=white&style=for-the-badge)
![FAISS](https://img.shields.io/badge/FAISS-Semantic_Search-36C5F0?style=for-the-badge)
![Google Sheets](https://img.shields.io/badge/Google_Sheets-Sync-34A853?logo=googlesheets&logoColor=white&style=for-the-badge)
![Upstash Redis](https://img.shields.io/badge/Upstash_Redis-State-DC382D?logo=redis&logoColor=white&style=for-the-badge)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?logo=pytest&logoColor=white&style=for-the-badge)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black&style=for-the-badge)
![uv](https://img.shields.io/badge/uv-6E56CF?style=for-the-badge)

An ETL-backed support answering platform that turns recurring team questions
into reliable, searchable answers through semantic retrieval, approved fallback
responses, policy safeguards, and pluggable delivery adapters.

Slack is the current delivery integration. The knowledge ingestion, retrieval,
fallback, and safeguard services are kept independent of Slack so the same
answering system can serve another team platform later.

## Why this exists

Support knowledge is often spread across spreadsheets, previous conversations,
pinned messages, and review documents. This project turns that knowledge into a
maintained answering workflow instead of an unbounded chatbot.

The system searches curated knowledge first. If semantic retrieval is not
confident enough, it preserves approved keyword behavior rather than inventing
an answer. Blocked-topic and rate-limit policies run before fallback.

## What it includes

- Excel, CSV, and Google Sheets knowledge ingestion;
- Slack question extraction and review exports;
- persisted FAISS semantic index with JSON document records;
- semantic retrieval with keyword fallback;
- seven-day semantic-answer caching;
- ten-question hourly per-user rate limiting;
- blocked-topic protection that cannot bypass fallback;
- duplicate Slack-event protection;
- retry-aware rate-limit accounting;
- unanswered-question and rate-limit notification hooks;
- in-memory and Upstash Redis state adapters;
- a FastAPI HTTP interface and Slack Bolt delivery adapter.

## Architecture at a glance

```text
Knowledge sources → ETL and curation → Semantic index
                                         ↓
Slack event → Answer service → Safeguards → Retrieval or fallback → Threaded reply
```

Read the detailed designs:

- [Architecture](docs/ARCHITECTURE.md)
- [Data pipelines](docs/DATA_PIPELINES.md)
- A local demo guide will be added after live Slack validation is complete.

## Run locally

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```sh
uv sync --locked
cp -n .env.example .env
uv run --env-file .env --no-sync uvicorn app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`. Open `/docs` for the interactive API
documentation. `/health` checks application liveness.

Generate a local API key and place it in `.env`:

```sh
uv run --no-sync python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Use the same key in the `/docs` **Authorize** dialog or the `X-API-Key` header.
The application itself does not load `.env` files; `uv --env-file` supplies
configuration to the process.

## Configuration

| Variable | Purpose | Default |
| --- | --- | --- |
| `KB_API_KEY` | HTTP answering secret | Unset; answering returns `503` |
| `KB_STORAGE_PATH` | Keyword knowledge snapshot | `data/kb_topics.json` |
| `HF_TOKEN` | Hugging Face embedding token | Unset; index building fails |
| `HF_EMBED_MODEL` | Embedding model | `sentence-transformers/all-mpnet-base-v2` |
| `RAG_INDEX_PATH` | Persisted FAISS index | `data/kb_index.faiss` |
| `RAG_RECORDS_PATH` | Retrieval-record sidecar | `data/kb_index_records.json` |
| `RAG_MIN_SIMILARITY` | Semantic confidence threshold | `0.6` |
| `RAG_STATE_BACKEND` | `memory`, `upstash`, or `none` | `memory` |
| `UPSTASH_REDIS_REST_URL` | Upstash URL when selected | Unset |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash token when selected | Unset |
| `SLACK_BOT_TOKEN` | Slack bot token | Unset |
| `SLACK_SIGNING_SECRET` | Slack request-signing secret | Unset |
| `SLACK_BOT_USER_ID` | Bot identity for mention filtering | Unset |
| `SLACK_ADMIN_CHANNEL` | Optional notification channel | Unset |

The configured Slack factory accepts an injected settings mapping. It does not
load `.env` files or perform a startup Slack `auth.test` call by default.

## Knowledge-base import

Knowledge rows use five columns:

```csv
topic,keywords,answer,enabled,priority
account_access,"login, sign in",Use your account portal.,TRUE,10
```

Import a local CSV snapshot:

```sh
uv run --env-file .env --no-sync python -m app.sync_kb data/faq.csv
```

Google Sheets synchronization uses a caller-provided authenticated Sheets v4
client and the same five-column contract. See the pipeline documentation for
validation, replacement, and failure-preservation behavior.

## Slack extraction and answering

Run a dry extraction first:

```sh
export SLACK_BOT_TOKEN="xoxb-your-token"
uv run --no-sync python -m scripts.scrape_kb --dry-run
```

The Slack adapter answers direct messages and bot mentions in the original
thread. It ignores unsupported subtypes, bot messages, and duplicate events.
The in-memory stores are suitable for one process; shared stores are required
for multi-worker deployments.

## Test and quality checks

```sh
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

The repository includes unit, integration-boundary, security, pipeline, and
network-free Slack/RAG composition tests.

## Current boundary

The backend implementation is locally tested. A controlled live Slack smoke
test remains before claiming live workspace validation. This repository does
not include private workspace data, credentials, or the portfolio landing page.
