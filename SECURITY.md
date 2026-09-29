# Security policy

## Reporting a vulnerability

Please do not disclose suspected vulnerabilities in a public issue or pull
request. Contact the repository maintainer privately through GitHub with a
clear description, affected component, reproduction steps, and the potential
impact. Do not include credentials, private workspace exports, or other
sensitive data in the report.

Please allow time for triage before sharing details publicly. Reports will be
assessed against the supported application boundaries, including the HTTP API,
ingestion pipelines, retrieval index, state stores, and delivery adapters.

## Scope reminders

- Never commit `.env` files, credentials, service-account keys, raw Slack
  exports, or production data.
- Provider credentials and workspace data must be supplied through deployment
  configuration, not source files.
- The repository's test fixtures are synthetic and should remain synthetic.
