"""Build persisted FAISS artifacts from a cleaned Q&A JSON dataset."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from pathlib import Path

from app.integrations.embeddings import HuggingFaceEmbeddingProvider
from app.repositories.retrieval import FaissVectorRepository
from app.services.retrieval import SemanticRetrievalService, as_retrieval_document


def build_parser() -> argparse.ArgumentParser:
    """Build the offline index-generation command."""
    parser = argparse.ArgumentParser(
        description="Build a persisted FAISS index from cleaned Q&A records."
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--index", type=Path, default=Path("data/kb_index.faiss"))
    parser.add_argument(
        "--records",
        type=Path,
        default=Path("data/kb_index_records.json"),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get(
            "HF_EMBED_MODEL", "sentence-transformers/all-mpnet-base-v2"
        ),
    )
    return parser


def load_documents(path: Path) -> list:
    """Load and validate cleaned Q&A records without exposing their contents."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError("input dataset must be a JSON list")
    return [
        as_retrieval_document(record, position)
        for position, record in enumerate(payload, 1)
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Build the local persisted index using the runtime Hugging Face token."""
    args = build_parser().parse_args(argv)
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN must be provided by the runtime environment")
    documents = load_documents(args.input)
    provider = HuggingFaceEmbeddingProvider(token=token, model=args.model)
    repository = FaissVectorRepository(args.index, args.records)
    SemanticRetrievalService(provider, repository).rebuild(documents)
    print(f"Indexed {len(documents)} records to {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
