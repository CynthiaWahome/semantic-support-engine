# Configuration

The application receives configuration from the deployment environment. The
application and import commands do not load `.env` files themselves; `uv
--env-file` can provide local values to the process.

## Core application

| Variable | Purpose | Default |
| --- | --- | --- |
| `KB_API_KEY` | HTTP answering secret | Unset; answering returns `503` |
| `KB_STORAGE_PATH` | Keyword knowledge snapshot | `data/kb_topics.json` |

## Retrieval and indexing

| Variable | Purpose | Default |
| --- | --- | --- |
| `HF_TOKEN` | Hugging Face embedding token | Unset; index building fails |
| `HF_EMBED_MODEL` | Embedding model | `sentence-transformers/all-mpnet-base-v2` |
| `RAG_INDEX_PATH` | Persisted FAISS index | `data/kb_index.faiss` |
| `RAG_RECORDS_PATH` | Retrieval-record sidecar | `data/kb_index_records.json` |
| `RAG_MIN_SIMILARITY` | Semantic confidence threshold | `0.6` |
| `RAG_STATE_BACKEND` | `memory`, `upstash`, or `none` | `memory` |
| `UPSTASH_REDIS_REST_URL` | Upstash URL when selected | Unset |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash token when selected | Unset |

## Slack delivery

| Variable | Purpose | Default |
| --- | --- | --- |
| `SLACK_BOT_TOKEN` | Slack bot token | Unset |
| `SLACK_SIGNING_SECRET` | Slack request-signing secret | Unset |
| `SLACK_BOT_USER_ID` | Bot identity for mention filtering | Unset |
| `SLACK_ADMIN_CHANNEL` | Optional unanswered-question notification channel | Unset |

`create_slack_app(service)` accepts a `SlackAnsweringService` and constructs a
Bolt app without injected settings. The FastAPI application does not register a
Slack receiver; deployments must configure a receiver separately and provide
`SLACK_SIGNING_SECRET` so it can verify signed requests. The configured factory
does not perform a startup Slack `auth.test` call by default.

## Knowledge synchronization

Google Sheets synchronization consumes:

- `GOOGLE_SPREADSHEET_ID`;
- `GOOGLE_SERVICE_ACCOUNT_FILE`;
- `GOOGLE_SHEET_TABS`.

The spreadsheet contract is:

```text
topic, keywords, answer, enabled, priority
```

Keep credentials, local exports, generated data, and workspace-derived records
outside version control.
