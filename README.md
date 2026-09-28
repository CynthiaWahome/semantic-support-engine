# Slack Support Assistant

A standalone application reproducing selected features contributed by Cynthia
Wahome to Thanos, reusing the existing implementation where appropriate.

## Current status

Spreadsheet-backed question answering is migrated: prioritized keyword matching,
local JSON storage, CSV import, and a read-only Google Sheets adapter. Slack
event answering is now migrated as an isolated adapter: direct messages and bot
mentions receive knowledge-base answers, replies stay in the source thread, and
replayed Slack events are ignored. Q&A ingestion, semantic retrieval, and
onboarding are not yet migrated.

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

The Google Sheets sync consumes `GOOGLE_SPREADSHEET_ID`,
`GOOGLE_SERVICE_ACCOUNT_FILE` and `GOOGLE_SHEET_TABS` when invoked with
`--google`. Slack configuration will be documented when Slack runtime wiring is
implemented.
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

## Slack answering

`SlackAnsweringService` accepts Slack `message` and `app_mention` events. It
answers direct messages and messages that mention the bot, then sends the answer
with the original message timestamp as `thread_ts`. When its caller supplies an
`event_id`, repeated deliveries are claimed by that ID and ignored within the
duplicate-event TTL. The Slack Bolt adapter currently passes the inner event
payload, so Bolt deliveries use the message identity (`channel`, `ts`, `user`,
and `text`) for deduplication.

`create_slack_app` registers the narrow Slack Bolt event surface for this
feature. Authentication and process transport are deployment concerns: provide
Slack credentials through the runtime environment when wiring Socket Mode or an
HTTP receiver. The in-memory duplicate store is appropriate for one process; a
shared store is required before running multiple workers.

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

The response includes `answer` and `source` (`knowledge_base` or `fallback`).
Unknown questions receive a generic support response; this is not RAG yet.

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
