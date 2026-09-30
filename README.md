# Semantic Support Engine

ETL pipeline and semantic-retrieval service for curated support answers.

![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white&style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white&style=for-the-badge)
![Slack Bolt](https://img.shields.io/badge/Slack_Bolt-4A154B?logo=slack&logoColor=white&style=for-the-badge)
![FAISS](https://img.shields.io/badge/FAISS-Semantic_Search-36C5F0?style=for-the-badge)
![Google Sheets](https://img.shields.io/badge/Google_Sheets-Sync-34A853?logo=googlesheets&logoColor=white&style=for-the-badge)
![Upstash Redis](https://img.shields.io/badge/Upstash_Redis-State-DC382D?logo=redis&logoColor=white&style=for-the-badge)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?logo=pytest&logoColor=white&style=for-the-badge)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black&style=for-the-badge)

## Problem

Teams repeatedly answer the same questions, but the answers are scattered
across conversations, pinned messages, internal documents, and disconnected
team knowledge. That creates duplicated effort, inconsistent guidance, and
knowledge that is easy to lose.

## Solution

Semantic Support Engine creates a controlled path from knowledge to answer:

```text
Ingest → validate → curate → index → retrieve → safeguard → answer
```

Curated knowledge is searched first through semantic retrieval. When the
semantic match is unavailable or below the configured confidence threshold, the
service preserves deterministic keyword fallback behavior.

## Architecture

```text
Knowledge sources
      ↓
ETL and review
      ↓
Semantic index + approved answers
      ↓
Answer service and safeguards
      ↓
Delivery adapter
```

The answering service is independent of the transport that delivered the
question. Adapters normalize platform events into a question, user identity,
channel, workspace, and request identity before calling the service.

## Knowledge pipeline

The system has two related knowledge paths:

1. Curated spreadsheet records provide trusted keyword answers and fallback
   behavior.
2. Scraped and reviewed conversation records provide approved input for the
   semantic index.

The scraper extracts question-and-answer candidates from selected conversation
history and produces local JSON and Excel review exports. Review and
sanitization happen before records are supplied to the index builder.

The current semantic index uses Hugging Face embeddings, normalized vectors,
FAISS inner-product search, and a JSON record sidecar. Index rebuilding is a
manual operation:

```text
Update knowledge → sync or curate → rebuild index → restart serving process
```

## Local development

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/CynthiaWahome/semantic-support-engine.git
cd semantic-support-engine
uv sync --locked
cp -n .env.example .env
```

Start the HTTP application:

```sh
uv run --env-file .env --no-sync uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive documentation is
available at `/docs`.

## Tests

```sh
uv run --no-sync pytest
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
```

The automated suite uses synthetic fixtures and does not contact external
Slack, Google, Hugging Face, or Upstash services.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Configuration](docs/CONFIGURATION.md)
- [Data pipelines](docs/DATA_PIPELINES.md)
- [Slack runtime](docs/SLACK_RUNTIME.md)
- [Contributing](CONTRIBUTING.md)

## License

This project is available under the [MIT License](LICENSE).
