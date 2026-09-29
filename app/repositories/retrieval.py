"""Persistent FAISS index and answer-record storage for semantic retrieval."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

import faiss
import numpy as np

from app.schemas.retrieval import RetrievalDocument, RetrievedDocument


class FaissVectorRepository:
    """Persist normalized vectors and their documents as replaceable snapshots."""

    def __init__(self, index_path: Path, records_path: Path) -> None:
        self.index_path = index_path
        self.records_path = records_path
        self._index: faiss.Index | None = None
        self._documents: list[RetrievalDocument] | None = None

    def replace(
        self,
        documents: Sequence[RetrievalDocument],
        vectors: Sequence[np.ndarray],
    ) -> None:
        """Build and persist a complete FAISS index and JSON sidecar."""
        if len(documents) != len(vectors):
            raise ValueError("every retrieval document needs one embedding")
        if not documents:
            raise ValueError("cannot build an empty retrieval index")
        matrix = np.asarray(vectors, dtype="float32")
        if matrix.ndim != 2 or matrix.shape[0] != len(documents):
            raise ValueError("embeddings must form one two-dimensional matrix")
        if not np.isfinite(matrix).all():
            raise ValueError("embeddings must contain only finite values")
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        _write_index_atomically(index, self.index_path)
        _write_records_atomically(list(documents), self.records_path)
        self._index = index
        self._documents = list(documents)

    def load(self) -> None:
        """Load and validate the persisted index and its document sidecar."""
        try:
            index = faiss.read_index(str(self.index_path))
            payload = json.loads(self.records_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, RuntimeError) as error:
            raise FileNotFoundError("retrieval index artifacts are missing") from error
        if not isinstance(payload, list):
            raise TypeError("retrieval records must be a JSON list")
        documents = [RetrievalDocument.model_validate(item) for item in payload]
        if index.ntotal != len(documents):
            raise ValueError("retrieval index and records have different sizes")
        self._index = index
        self._documents = documents

    def search(self, vector: np.ndarray, limit: int = 3) -> list[RetrievedDocument]:
        """Return top matches from the loaded persisted index."""
        if limit < 1:
            raise ValueError("limit must be positive")
        if self._index is None or self._documents is None:
            self.load()
        query = np.asarray(vector, dtype="float32").reshape(1, -1)
        if query.shape[1] != self._index.d:
            raise ValueError("query and index dimensions do not match")
        faiss.normalize_L2(query)
        scores, positions = self._index.search(query, min(limit, self._index.ntotal))
        return [
            RetrievedDocument(
                document=self._documents[position],
                score=float(score),
            )
            for score, position in zip(scores[0], positions[0])
            if position >= 0
        ]


def _write_index_atomically(index: faiss.Index, path: Path) -> None:
    """Write a FAISS artifact through a same-directory temporary file."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        faiss.write_index(index, str(temporary_path))
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _write_records_atomically(documents: list[RetrievalDocument], path: Path) -> None:
    """Write the sidecar records through a same-directory temporary file."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(
                [document.model_dump(mode="json") for document in documents],
                temporary,
                indent=2,
                ensure_ascii=False,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
