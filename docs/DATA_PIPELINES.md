# Data Pipelines

This project contains ETL ingestion pipelines and an online semantic-retrieval
serving layer. It is not one monolithic ETL job and it is not an ELT warehouse.

## Pipeline overview

```text
Source data
    ↓ extract
Validation and curation
    ↓ transform
Knowledge snapshot or reviewed dataset
    ↓ index preparation
Embeddings and FAISS artifacts
    ↓ online serving
Retrieved answer or approved fallback
```

## Spreadsheet knowledge-base ETL

### Extract

The importer accepts a UTF-8 CSV export. The Google Sheets adapter reads an
authenticated Sheets v4 client through a caller-provided reader.

### Transform

Rows are normalized and validated against:

```text
topic, keywords, answer, enabled, priority
```

The transformation handles:

- case-insensitive headers;
- boolean enabled values;
- integer priorities;
- duplicate topics and ordered tab overrides;
- disabled records;
- periodic topics excluded from direct answering;
- blank rows;
- malformed or incomplete records.

Invalid input rejects the import as a whole. The previous valid snapshot is
preserved when a replacement cannot be built.

### Load

Validated records are written to the JSON knowledge snapshot consumed by the
keyword answer service.

## Slack question curation ETL

### Extract

The scraper reads selected Slack channel history using explicit channel and
pattern filters. It writes local checkpoints so an interrupted extraction can
resume.

### Transform

Messages and threads are converted into reviewable question-and-answer records.
The pipeline produces JSON and Excel review exports. Raw workspace output stays
local and ignored; it must be reviewed and sanitized before indexing.

### Load

Approved records become the input to retrieval-index preparation. The project
does not treat every scraped message as an answerable fact.

## Retrieval-index preparation

The index builder takes approved records and:

1. converts question-and-answer text into embeddings;
2. normalizes vectors for cosine-equivalent inner-product search;
3. writes a persisted FAISS index;
4. writes a JSON document sidecar;
5. publishes an atomic manifest connecting the two artifacts.

The index is a serving artifact, not the source of truth. Curated knowledge and
approved records remain the source of truth.

## ETL versus ELT

The pipelines are primarily ETL because transformation and validation happen
before the processed data is loaded into the application snapshot or retrieval
index.

The system would be closer to ELT if it loaded largely raw records into a
durable warehouse first and performed most transformations inside that storage
layer. That is not the current design.

## Online serving path

An incoming question is not an ETL job. It follows the online serving path:

```text
event → normalized question → safeguards → cache → retrieval → fallback → reply
```

The answer service reads already-prepared artifacts and returns an answer within
the request flow. It does not mutate the source knowledge during normal serving.

## Future pipeline extensions

Potential client-specific improvements include:

- scheduled re-indexing after approved source changes;
- review and approval states before indexing;
- durable pipeline-run metadata;
- managed vector storage;
- data-quality dashboards;
- multi-tenant source and index isolation.
