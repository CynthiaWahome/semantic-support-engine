"""Persistent FAISS index and answer-record storage for semantic retrieval."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

import faiss
import numpy as np

from app.schemas.retrieval import RetrievalDocument, RetrievedDocument


class FaissVectorRepository:
    """Persist normalized vectors and their documents as replaceable snapshots."""

    def __init__(self, index_path: Path, records_path: Path) -> None:
        self.index_path = index_path
        self.records_path = records_path
        self.manifest_path = index_path.with_name(f"{index_path.stem}.manifest.json")
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
        generation = uuid4().hex
        generation_index_path = _generation_path(self.index_path, generation)
        generation_records_path = _generation_path(self.records_path, generation)
        _write_index_atomically(index, generation_index_path)
        _write_records_atomically(list(documents), generation_records_path)
        _write_manifest_atomically(
            {
                "generation": generation,
                "index": generation_index_path.name,
                "records": generation_records_path.name,
            },
            self.manifest_path,
        )
        self._index = index
        self._documents = list(documents)

    def load(self) -> None:
        """Load and validate the persisted index and its document sidecar."""
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, RuntimeError) as error:
            raise FileNotFoundError("retrieval index manifest is missing") from error
        if not isinstance(manifest, dict):
            raise TypeError("retrieval index manifest must be a JSON object")
        index_name = manifest.get("index")
        records_name = manifest.get("records")
        if not all(
            isinstance(name, str) and Path(name).name == name
            for name in (index_name, records_name)
        ):
            raise ValueError("retrieval index manifest contains invalid paths")
        try:
            index = faiss.read_index(str(self.manifest_path.parent / index_name))
            payload = json.loads(
                (self.manifest_path.parent / records_name).read_text(encoding="utf-8")
            )
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


def _generation_path(path: Path, generation: str) -> Path:
    """Return a generation-specific sibling path for one artifact."""
    return path.with_name(f"{path.stem}.{generation}{path.suffix}")


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


def _write_manifest_atomically(manifest: dict[str, str], path: Path) -> None:
    """Publish the complete generation pointer only after both artifacts exist."""
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
            json.dump(manifest, temporary, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
