# Slack runtime

The Slack adapter runs the existing answering service through Slack Bolt
Socket Mode. Socket Mode is the first executable transport for local and
controlled testing; the FastAPI application remains responsible for the HTTP
knowledge-base endpoints.

## Required settings

Provide these values through the process environment or `uv --env-file`:

| Variable | Purpose |
| --- | --- |
| `SLACK_BOT_TOKEN` | Bot token used to post threaded replies |
| `SLACK_APP_TOKEN` | App-level token used to establish the Socket Mode connection |
| `SLACK_BOT_USER_ID` | Optional bot identity used to ignore the bot's own messages |
| `HF_TOKEN` | Embedding-provider token used when the configured RAG service starts |

The persisted FAISS index and JSON record sidecar must also exist at the paths
configured by `RAG_INDEX_PATH` and `RAG_RECORDS_PATH`. The default state backend
is in-memory; use the Upstash settings and `RAG_STATE_BACKEND=upstash` when the
process must share cache and rate-limit state across workers.

`SLACK_SIGNING_SECRET` is required for an HTTP Slack receiver. It is not used by
Socket Mode, because Socket Mode authenticates the app connection with the app
token. The HTTP receiver is a separate future transport boundary.

## Start the runtime

From the repository root:

```sh
uv sync --locked
uv run --env-file .env --no-sync python -m app.adapters.slack.socket_mode
```

The process blocks while it maintains the Socket Mode connection. It receives
supported direct messages and bot mentions, normalizes the Slack user, channel,
thread, and event identity, then sends the answer back in the source thread.

## Controlled smoke test

Use a test Slack app and a test channel. Confirm that:

1. A known question returns its curated semantic or keyword answer.
2. A paraphrase retrieves the expected approved semantic answer.
3. An unsupported question follows the documented fallback behavior.
4. A blocked topic cannot reach a sensitive keyword answer.
5. The response is posted in the original thread.
6. Retrying the same Slack event does not create a duplicate reply.

Do not use production workspace data for the first run. Keep tokens and
workspace-derived records out of the repository.
