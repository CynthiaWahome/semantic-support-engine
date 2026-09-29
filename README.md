# Slack Support Assistant

A standalone application reproducing selected features contributed by Cynthia
Wahome to Thanos, reusing the existing implementation where appropriate.

## Current status

Spreadsheet-backed question answering is migrated: prioritized keyword matching,
local JSON storage, CSV import, and a read-only Google Sheets adapter. Slack
event answering is now migrated as an isolated adapter: direct messages and bot
mentions receive knowledge-base answers, replies stay in the source thread, and
replayed Slack events are ignored. Slack Q&A extraction, local JSON checkpoints,
and Excel review exports are now migrated. Semantic retrieval now follows the
recovered design: Hugging Face embeddings, a persisted FAISS index, a JSON record
sidecar, and RAG-first keyword fallback composition. RAG safeguards now have
injectable cache, rate-limit, blocked-topic, and notification boundaries;
onboarding remains separate integration work.

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
| `SLACK_ADMIN_CHANNEL` | Optional channel for unanswered and rate-limit notifications | Unset; notifications disabled |

The Google Sheets sync consumes `GOOGLE_SPREADSHEET_ID`,
`GOOGLE_SERVICE_ACCOUNT_FILE` and `GOOGLE_SHEET_TABS` when invoked with
`--google`.
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
configured state backend, optional admin notifier, and authenticated Bolt app
from an injected deployment mapping. It does not load `.env` files, call Slack,
or choose a hosting platform. Provide `SLACK_BOT_TOKEN` and
`SLACK_SIGNING_SECRET` through the deployment environment; the optional bot
user ID enables mention filtering and the optional admin channel enables
unanswered-question and rate-limit notifications. The in-memory duplicate and
RAG state stores are appropriate for one process; shared stores are required
before running multiple workers.

The configured factory activates semantic retrieval first, preserves the
existing keyword answer fallback, and keeps the transport boundary separate
from the answer service. Merge the event-aware rate-limit hardening before
enabling this factory in production so a retried Slack delivery does not
consume a second rate-limit unit.

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
