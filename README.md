# Semantic Support Engine

ETL pipeline and semantic-retrieval service for curated support answers, with
Slack as the first delivery adapter.

[![CI](https://github.com/CynthiaWahome/semantic-support-engine/actions/workflows/ci.yml/badge.svg?branch=dev)](https://github.com/CynthiaWahome/semantic-support-engine/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB)
![License](https://img.shields.io/badge/License-MIT-green)

## Overview

The service turns structured knowledge and reviewed question-and-answer records
into searchable serving artifacts. At runtime it retrieves an approved answer,
applies policy safeguards, and delivers the result through an adapter.

The current implementation includes:

- spreadsheet-backed keyword answers and fallback responses;
- Slack history extraction and Excel review exports;
- Hugging Face embeddings and a persisted FAISS index;
- semantic retrieval followed by keyword fallback;
- caching, per-user rate limiting, blocked-topic protection, notifications,
  and duplicate-event protection;
- a Slack Bolt Socket Mode runtime.

The repository does not contain the wider Thanos grading, promotion,
administration, or cohort-management application.

## Architecture

```text
Structured knowledge + reviewed Slack Q&A
                    ↓
              ETL and curation
                    ↓
        FAISS index + JSON record sidecar
                    ↓
          Answer service and safeguards
                    ↓
       Slack adapter or another future adapter
```

The answering services do not depend on Slack event objects. An adapter
normalizes its platform event into a question, user identity, channel, and
request identity before calling the answer service.

## Quick start

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/CynthiaWahome/semantic-support-engine.git
cd semantic-support-engine
uv sync --locked
cp -n .env.example .env
```

Set a local `KB_API_KEY`, then start the HTTP application:

```sh
uv run --env-file .env --no-sync uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive API documentation
is available at `/docs`.

## HTTP answer endpoint

The protected answer endpoint accepts a question with the `X-API-Key` header:

```sh
curl -X POST http://127.0.0.1:8000/knowledge-base/answer \
  -H "X-API-Key: ${KB_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do I sign in?"}'
```

Health and OpenAPI endpoints remain public. Answer requests require a configured
server key and a matching client key.

## Slack runtime

The Slack runtime uses Socket Mode and composes the existing RAG answer service.
It requires `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and the RAG settings described
in [the Slack runtime guide](docs/SLACK_RUNTIME.md).

Start it with:

```sh
uv run --env-file .env --no-sync python -m app.adapters.slack.socket_mode
```

The runtime handles direct messages and bot mentions, preserves the source
thread, forwards user/channel/event context to safeguards, and ignores repeated
event deliveries. The FastAPI application and Slack runtime are separate
process boundaries; starting Uvicorn does not start a Slack receiver.

## Knowledge and indexing workflow

The system has two related knowledge paths:

1. Curated spreadsheet records provide trusted keyword answers and fallback
   behavior.
2. Scraped and reviewed conversation records provide approved input for the
   semantic index.

Typical workflow:

```text
Update knowledge → sync or curate → rebuild index → restart serving process
```

The scraper writes local JSON and Excel review exports. Review and sanitization
are manual before records are supplied to the index builder. Raw workspace data
and generated index files remain outside version control.

The current index uses Hugging Face `sentence-transformers/all-mpnet-base-v2`,
normalized vectors, FAISS inner-product search, and a JSON record sidecar.
Index rebuilding is currently a manual operation.

## Configuration

Core settings include:

| Variable | Purpose |
| --- | --- |
| `KB_API_KEY` | HTTP answer endpoint secret |
| `KB_STORAGE_PATH` | Keyword knowledge snapshot path |
| `HF_TOKEN` | Hugging Face embedding-provider token |
| `RAG_INDEX_PATH` | Persisted FAISS index path |
| `RAG_RECORDS_PATH` | Retrieval-record sidecar path |
| `RAG_MIN_SIMILARITY` | Semantic confidence threshold |
| `RAG_STATE_BACKEND` | `memory`, `upstash`, or `none` |
| `SLACK_BOT_TOKEN` | Slack bot API token |
| `SLACK_APP_TOKEN` | Slack Socket Mode app token |
| `SLACK_SIGNING_SECRET` | Required by a future HTTP Slack receiver |

Do not commit `.env` files, credentials, raw Slack exports, generated data, or
production workspace content.

## Tests and quality checks

```sh
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

The automated suite uses synthetic fixtures and does not contact Slack, Google,
Hugging Face, or Upstash. A controlled Slack smoke test is documented in the
[Slack runtime guide](docs/SLACK_RUNTIME.md).

## Boundaries and future adapters

Slack is the first adapter, not the application boundary. A Teams, Telegram,
Zedu, or web adapter should normalize its own event into the same answer-service
contract. User, channel, workspace, and request identity must be passed
explicitly when safeguards or tenant isolation are enabled.

The current implementation is single-workspace. Multi-tenant retrieval,
automatic scheduled re-indexing, managed vector storage, and a web management
interface are separate production-upgrade tracks.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for branch, commit, testing, and pull
request conventions.

## License

This project is available under the [MIT License](LICENSE).
