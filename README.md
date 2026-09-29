# Slack Support Assistant

![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white&style=for-the-badge)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white&style=for-the-badge)
![Slack Bolt](https://img.shields.io/badge/Slack_Bolt-4A154B?logo=slack&logoColor=white&style=for-the-badge)
![FAISS](https://img.shields.io/badge/FAISS-Semantic_Search-36C5F0?style=for-the-badge)
![Google Sheets](https://img.shields.io/badge/Google_Sheets-Sync-34A853?logo=googlesheets&logoColor=white&style=for-the-badge)
![Upstash Redis](https://img.shields.io/badge/Upstash_Redis-State-DC382D?logo=redis&logoColor=white&style=for-the-badge)
![Pytest](https://img.shields.io/badge/Pytest-0A9EDC?logo=pytest&logoColor=white&style=for-the-badge)
![Ruff](https://img.shields.io/badge/Ruff-D7FF64?logo=ruff&logoColor=black&style=for-the-badge)
![uv](https://img.shields.io/badge/uv-6E56CF?style=for-the-badge)

A standalone, platform-agnostic knowledge-support backend that turns recurring
team questions into searchable, consistent, and safeguarded answers. Slack is
the current delivery adapter; the knowledge, retrieval, fallback, and policy
services are kept independent of Slack so another team platform can reuse them.

This repository preserves and rebuilds a substantial prior knowledge-support
feature as an independently structured FastAPI application. It is deliberately
not a recreation of a full administration or grading platform.

## Current status

The core implementation is complete and locally tested. It includes:

- spreadsheet-backed keyword question answering with priority ordering;
- CSV import, local JSON snapshots, and read-only Google Sheets synchronization;
- Slack question extraction, local checkpoints, and Excel review exports;
- Hugging Face embeddings, a persisted FAISS index, and a JSON record sidecar;
- semantic retrieval first, followed by the approved keyword fallback;
- seven-day semantic-answer caching;
- ten-question hourly per-user rate limiting;
- blocked-topic protection that cannot bypass through keyword fallback;
- unanswered-question and rate-limit notification hooks;
- Slack direct messages and mentions answered in the original thread;
- duplicate-event protection and event-aware rate-limit accounting;
- injectable in-memory and Upstash Redis state-store adapters;
- a deployment factory that composes the RAG service with Slack Bolt.

The controlled live Slack smoke test remains a deployment verification step. No
production usage, live cohort result, or external workspace data is claimed by
this repository.

## What problem this solves

Teams often answer the same operational questions repeatedly. The answer may
exist in a spreadsheet, a pinned message, a previous support conversation, or a
review document, but it is difficult to find consistently. This project turns
that scattered knowledge into a maintained answering workflow:

```text
curated knowledge → validated records → searchable index → safeguarded answer
                                                       → Slack thread
```

The system is intentionally conservative. A semantic match must meet a
confidence threshold. If it does not, the service preserves the existing
approved keyword behavior instead of inventing an answer. Policy checks run
before fallback so restricted topics cannot be exposed through another path.

## Architecture

```mermaid
flowchart LR
    Sources["Excel / Google Sheets\nReviewed Q&A records\nSanitized Slack dataset"]
    Curate["Validate and normalize\nTopic, keywords, answer, priority"]
    Index["Build embeddings\nPersist FAISS index\nWrite JSON sidecar"]
    Slack["Slack event\nUser, channel, event, thread"]
    Normalize["Normalize event\nClaim duplicate key"]
    Policy["Safeguards\nBlocked topics\nRate limit\nCache"]
    Retrieve["Semantic retrieval\nConfidence threshold"]
    Fallback["Approved keyword\nfallback"]
    Reply["Threaded Slack reply"]
    Notify["Admin notification\nUnanswered or limited"]
    State["In-memory or\nUpstash Redis state"]

    Sources -. "offline curation" .-> Curate
    Curate -. "index build" .-> Index
    Index --> Retrieve
    Slack --> Normalize --> Policy
    Policy <--> State
    Policy --> Retrieve
    Retrieve -->|confident| Reply
    Retrieve -->|low confidence / missing index| Fallback --> Reply
    Policy -->|blocked or rate limited| Reply
    Policy -. "optional hook" .-> Notify
```

The solid arrows represent the online answering path. Dashed arrows represent
offline curation, indexing, or optional notification work. The FAISS index is a
persisted retrieval artifact; Redis is used for shared runtime state, not as a
replacement for the reviewed knowledge source.

## Is this an ETL or ELT project?

It contains data-pipeline work, but it is not one single ETL or ELT pipeline.
It has two offline ingestion pipelines and one online serving path.

### Knowledge-base ingestion: ETL

The spreadsheet path is best described as ETL:

1. **Extract** rows from CSV, Excel exports, or Google Sheets.
2. **Transform** headers, booleans, priorities, duplicate topics, disabled rows,
   and validation errors.
3. **Load** a validated JSON knowledge-base snapshot used by the answer service.

### Slack question curation: ETL

The scraper is also ETL:

1. **Extract** messages and threads from selected Slack channels.
2. **Transform** them into question-and-answer records, checkpoints, and review
   exports.
3. **Load** sanitized records for human review and later indexing.

### Retrieval-index preparation: transform and load

The index builder takes approved records, transforms text into embeddings, and
loads the vectors plus document sidecar into a persisted FAISS index. This is a
feature-indexing pipeline rather than a traditional analytics warehouse.

### Online answering: serving, not ETL

When a user asks a question, the service performs retrieval, policy checks,
fallback selection, and response delivery. That is an online application flow,
not ETL or ELT.

The most accurate description is therefore: **a knowledge-support application
with ETL ingestion pipelines and an online semantic-retrieval serving layer**.

## Implemented capabilities

| Capability | What it provides |
| --- | --- |
| Curated knowledge base | Maintainers control the answers that can be returned. |
| Semantic retrieval | Related questions can find an approved answer even when wording differs. |
| Keyword fallback | Known phrase matching remains available when retrieval is uncertain. |
| Persistent index | FAISS vectors and records survive application restarts. |
| Caching | Repeated semantic questions can reuse answers for seven days. |
| Rate limiting | A user is limited to ten questions per hour by default. |
| Blocked topics | Restricted questions cannot bypass policy through keyword fallback. |
| Duplicate protection | Slack retries do not create duplicate threaded replies. |
| Event-aware limits | A failed Slack delivery retry does not consume another rate-limit unit. |
| Notifications | Unanswered and rate-limited questions can notify administrators. |
| Platform boundary | Core services can be reused behind another delivery adapter. |

## Run locally

Requires Python 3.13+ and uv. From this repository directory, install dependencies
and create your own local configuration. The copy command will not overwrite an
existing `.env`:

```sh
uv sync --locked
cp -n .env.example .env
```

Set `KB_API_KEY` in your local `.env` to a strong random secret. You can generate
one locally with the command below; keep its output private, paste it into your
local file, and never commit or share it:

Use an ASCII-safe token, such as the `secrets.token_urlsafe` output below. The
application rejects non-ASCII API-key configuration so HTTP header decoding is
unambiguous.

```sh
uv run --no-sync python -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Start the server with explicit environment-file loading:

```sh
uv run --env-file .env --no-sync uvicorn app.main:app --reload
```

`uv sync` installs dependencies into the project's `.venv`. The server runs at
`http://127.0.0.1:8000`; interactive API documentation is available at `/docs`.
`GET /health` returns `{"status":"ok"}` and checks application liveness only.
Local question answering requires no Slack account or external service. `uv`
loads the specified file into the child process; the application itself does not
load `.env` files. Existing process environment values take precedence, so use
one configuration source consistently. In `/docs`, select **Authorize**, enter the same key, then
try the answer endpoint. Clients must send it in the `X-API-Key` header.

Missing or incorrect client keys return `401`. Missing, blank or whitespace-padded
server configuration returns `503` without accessing answers. `/health`, `/docs`
and `/openapi.json` remain public. This intentionally replaces anonymous answering.

The complete current application configuration is:

| Variable | Purpose | Default |
| --- | --- | --- |
| `KB_API_KEY` | Shared secret required for HTTP question answering | Unset; answering returns 503 |
| `KB_STORAGE_PATH` | JSON snapshot path shared by the server and importer | `data/kb_topics.json` |
| `HF_TOKEN` | Hugging Face token used by the offline index builder | Unset; index building fails |
| `HF_EMBED_MODEL` | Hugging Face feature-extraction model | `sentence-transformers/all-mpnet-base-v2` |
| `RAG_INDEX_PATH` | Persisted FAISS index path | `data/kb_index.faiss` |
| `RAG_RECORDS_PATH` | Persisted retrieval-record sidecar path | `data/kb_index_records.json` |
| `RAG_MIN_SIMILARITY` | Minimum semantic-match score | `0.6` |
| `RAG_STATE_BACKEND` | Safeguard state backend: `memory`, `upstash`, or `none` | `memory` |
| `UPSTASH_REDIS_REST_URL` | Upstash REST URL when the state backend is `upstash` | Unset |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash REST token when the state backend is `upstash` | Unset |
| `SLACK_BOT_TOKEN` | Slack bot token for the configured Bolt app | Unset |
| `SLACK_SIGNING_SECRET` | Slack request-signing secret for HTTP receivers | Unset |
| `SLACK_BOT_USER_ID` | Bot user ID used to identify mentions and ignore bot messages | Unset |
| `SLACK_ADMIN_CHANNEL` | Optional channel for unanswered and rate-limit notifications | Unset |

The Google Sheets sync consumes `GOOGLE_SPREADSHEET_ID`,
`GOOGLE_SERVICE_ACCOUNT_FILE` and `GOOGLE_SHEET_TABS` when invoked with
`--google`. Slack runtime composition consumes the Slack and RAG variables above
when a deployment calls `create_configured_slack_app(settings)`. The factory
does not read `.env` files or perform a startup Slack `auth.test` call by
default; the configured receiver still verifies signed incoming requests.
Production may inject these variables directly and omit `--env-file`. Local
`.env` files, credentials, data, notes and the roadmap are ignored; only the
root `.env.example` template is intended for version control. Ignore rules do
not protect files already tracked or files deliberately added with `git add -f`.

## Structure

```text
app/
  main.py                 Application factory and entry point
  routes/                 HTTP handlers and central router
  services/               Business logic shared across interfaces
  schemas/                Pydantic request and response contracts
  models/                 Database entities and persistence mappings
  repositories/           Database queries and persistence access
  integrations/           External adapters: Slack, Sheets, embeddings
  core/                   Shared configuration, logging, lifecycle
scripts/                  Operational commands; runtime credentials stay local
tests/
  test_health.py          HTTP contract test
.github/
  PULL_REQUEST_TEMPLATE.md
```

The HTTP flow is `routes → services → repositories/integrations`. Routes use
schemas to validate input and serialize output; repositories use database
models for persistence. Services do not depend on HTTP requests or Slack event
objects, allowing the same feature logic to serve both interfaces.

The liveness endpoint demonstrates `routes/health.py → services/health.py`, with
its response contract in `schemas/health.py`. No database or ORM is configured
yet; knowledge-base persistence uses JSON. `models/` is reserved for database
entities, not HTTP schemas. Register new HTTP routers in `routes/router.py`.

## Run the Slack extraction pipeline

The scraper reads Slack history through the runtime environment and writes only
to local ignored output paths. It never loads `.env` files itself. Start with a
dry run to verify channel targeting without fetching message history:

```sh
export SLACK_BOT_TOKEN="xoxb-your-token"
uv run --no-sync python -m scripts.scrape_kb --dry-run
```

Run extraction for the configured `support-` and `help-` channel prefixes:

```sh
uv run --no-sync python -m scripts.scrape_kb
```

The command writes `data/scraper/kb_checkpoint.json` after each channel and
publishes `kb_dataset.json` and `kb_dataset.xlsx` for local review. Use
`--channels`, `--exclude-channels`, `--patterns`, `--mentors-channel`, or
`--output-dir` to narrow a run. The optional runtime variables are
`CHANNEL_PATTERNS`, `MENTORS_CHANNEL`, and `SCRAPER_OUTPUT_DIR`. Do not commit
Slack-derived output; review and sanitize it before any retrieval index is built.

## Slack answering

`SlackAnsweringService` accepts Slack `message` and `app_mention` events. It
answers direct messages and messages that mention the bot, then sends the answer
with the original message timestamp as `thread_ts`. When its caller supplies an
`event_id`, repeated deliveries are claimed by that ID and ignored within the
duplicate-event TTL. The Slack Bolt adapter currently passes the inner event
payload, so Bolt deliveries use the message identity (`channel`, `ts`, `user`,
and `text`) for deduplication.

`create_slack_app` registers the narrow Slack Bolt event surface for this
feature. `create_configured_slack_app(settings)` composes the RAG service,
configured state backend, optional administrator notifier, and authenticated
Bolt app from an injected deployment mapping. The factory does not load `.env`
files, choose a hosting platform, or perform a startup `auth.test` call by
default. The configured receiver still verifies signed incoming requests.

The in-memory duplicate and RAG state stores are appropriate for one process;
shared stores are required before running multiple workers. Merge the event-aware
rate-limit hardening before enabling the configured Slack runtime in production
so a failed delivery retry cannot consume a second rate-limit unit.

## Spreadsheet knowledge base

Export a worksheet from Excel or Google Sheets as UTF-8 CSV. The five headers
are `topic,keywords,answer,enabled,priority` (case-insensitive). Quote cells that
contain commas:

```csv
topic,keywords,answer,enabled,priority
account_access,"login,sign in",Use your account portal.,TRUE,10
```

Import your local export, then start the server using the command above:

```sh
uv run --env-file .env --no-sync python -m app.sync_kb data/faq.csv
```

The import writes `data/kb_topics.json`; set `KB_STORAGE_PATH` in your process
environment to override that path for both importer and server. Relative paths
resolve from the working directory. Use the same environment file for the importer
and server so both select the same snapshot. No Google credential file is loaded.
Keep source exports and generated storage in ignored `data/`, never in commits.

For a shell where you have separately exported `KB_API_KEY`, the HTTP request is
shown below. `uv --env-file` does not export values back into your parent shell;
otherwise, use `/docs` and its **Authorize** dialog to test the endpoint.

```sh
curl -X POST http://127.0.0.1:8000/knowledge-base/answer \
  -H "X-API-Key: ${KB_API_KEY}" \
  -H 'Content-Type: application/json' \
  -d '{"question":"How do I sign in?"}'
```

The current HTTP response includes `answer` and `source` (`knowledge_base` or
`fallback`). The `RagKnowledgeBaseService` composition additionally returns
`source: semantic_retrieval` for a confident indexed answer, then falls back to
the existing keyword response when the index is missing or the score is below
the configured threshold. The Slack answering boundary accepts this composition;
runtime provider and index configuration remain deployment concerns.

Matching preserves Thanos's case-insensitive whole-word/phrase behavior and
highest-priority selection; ties use the first topic. `periodic_` topics are
stored but excluded from question answering. Blank enabled cells mean true;
`false`, `0`, `no`, and `n` disable a topic. Fully blank records are ignored.
Every populated row needs a topic and a recognized enabled value. Enabled rows
also need an answer, integer priority (blank defaults to zero), and keywords
unless the topic starts with `periodic_`. Disabled rows need no answer or keywords.
Any invalid row rejects the entire import, even when other rows are valid.
Later valid rows/tabs override earlier duplicate topics, including an explicit
disable. All-disabled input clears the snapshot; empty input preserves it and
reports failure.

Sync results include `success`, `topics_written` and `errors`. Row errors contain
the tab, one-based spreadsheet record number (header is row 1), and a reason,
never answer contents. CSV multiline fields count as one record. Invalid headers,
extra cells and malformed quoting also identify the offending record. Provider
or file-access failures return `success: false` without row errors. Failed imports exit with
code 1 and preserve the previous snapshot; correct the source before retrying.

Google Sheets integration uses `GoogleSheetsReader(service, spreadsheet_id)`
with a caller-provided authenticated Sheets v4 discovery client. Provision that
client with the read-only Sheets scope in your deployment integration; this repo
does not yet include client authentication/bootstrap or scheduled synchronization.
Pass the reader and repository into `KnowledgeBaseSyncService`, optionally with
an ordered list of tab names, then call `sync()`. Columns A:E use the same five
fields; row 1 is a header. Without a tab selection, it reads `Sheet1`. Any missing
requested tab or read failure prevents replacement of the previous snapshot.
The adapter is tested with a fake provider, not a live Google account.

To synchronize directly from Google Sheets, create a Google Cloud service
account, grant its email read access to the spreadsheet, and place its JSON key
under the ignored `credentials/` directory at the path in
`GOOGLE_SERVICE_ACCOUNT_FILE`. Set the spreadsheet ID and
optional comma-separated tab names, then run:

```sh
uv run --env-file .env --no-sync python -m app.sync_kb --google
```

The adapter requests the read-only Sheets scope, reads columns A:E after the
header, and publishes only a successful validated snapshot. It does not create,
edit or delete spreadsheet content. The service-account JSON is never committed;
do not paste it into chat or public repositories. This is an explicit sync
command, not a background scheduler yet.

### Build the semantic retrieval index

Use a cleaned and reviewed Q&A JSON export from the scraper pipeline. The command
embeds each question-answer pair through Hugging Face and writes the durable
`data/kb_index.faiss` and `data/kb_index_records.json` artifacts. Keep the input,
token and generated files local; they are ignored and must not be committed.

```sh
export HF_TOKEN="hf-your-token"
uv run --no-sync python -m scripts.build_retrieval_index \
  --input data/rag_kb_clean.json
```

The original feature uses cosine-equivalent inner-product search over normalized
`all-mpnet-base-v2` vectors. Runtime retrieval searches the top three records and
requires a minimum similarity of `0.6` before returning a curated answer.

### RAG safeguards

`RagKnowledgeBaseService` accepts an optional `RagSafeguards` instance. With an
injected Upstash-compatible state store it provides seven-day semantic-answer
caching and a ten-question hourly per-user limit. Restricted topics return the
generic fallback instead of bypassing policy through keyword matching. Weak or
missing semantic matches retain the keyword fallback and can notify an injected
Slack administrator notifier. `InMemoryRagStateStore` is for tests and local
single-process development; production should inject `UpstashRagStateStore`.

`app.core.rag_runtime` provides `RagRuntimeConfig`, `create_state_store`, and
`create_rag_service` for composing these boundaries without coupling the core
service to a particular deployment platform. Deployment code supplies settings
and secrets through an injected mapping or explicit constructor values; the RAG
core does not load `.env` files or discover credentials. Select `memory` for
local development, `upstash` for shared runtime state, or `none` when safeguards
are intentionally disabled for a controlled test. The notifier remains an
injected adapter so Slack, Zedu, or another platform can provide its own
delivery mechanism.

JSON replacement is atomic, but concurrent imports are last-writer-wins; run
one importer at a time. This is a local single-instance baseline, not a shared
database deployment. API-key authentication gates answers, but does not provide
per-user permissions, tenant isolation or rate limiting. Keep the demo on localhost;
external deployment additionally requires HTTPS, securely provisioned keys and
appropriate ingress/rate controls. Do not embed a shared server key in a public
web frontend.

### Migration provenance

Adapted from Cynthia Wahome's Thanos branch `feat/rag-and-onboarding-dms` at
`cf0285e0`: `core/kb_service.py`, `core/database/local/kb_repository.py`,
`slack/kb_sync.py`, the read methods in `core/spreadsheet.py`, and
`tests/kb/test_kb_logic.py`. Relevant original work includes
[spreadsheet sync PR #36](https://github.com/hngprojects/thanos/pull/36) and
[PR #181](https://github.com/hngprojects/thanos/pull/181).

Standalone adaptations remove Slack/global configuration coupling and credential
loading, validate stored topics, use unique temporary files, preserve snapshots
on partial sync failure, handle negative priorities, and correctly honor boolean
or numeric disabled cells. Unlike the original, explicitly disabling all rows
removes stale answers. No private workspace content or original notes are included.

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
