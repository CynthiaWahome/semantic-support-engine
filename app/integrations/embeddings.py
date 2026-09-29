"""Embedding-provider adapters used by the retrieval index."""

from __future__ import annotations

from typing import Any, Protocol

import faiss
import numpy as np
import requests


class EmbeddingProvider(Protocol):
    """Provider boundary for local or hosted text embeddings."""

    def embed(self, text: str) -> np.ndarray:
        """Return one normalized embedding vector for non-empty text."""
        ...


class HuggingFaceEmbeddingProvider:
    """Use Hugging Face Inference API feature extraction for RAG queries."""

    def __init__(
        self,
        token: str,
        model: str = "sentence-transformers/all-mpnet-base-v2",
        timeout: float = 15.0,
    ) -> None:
        if not token.strip():
            raise ValueError("Hugging Face token must not be blank")
        if not model.strip():
            raise ValueError("Hugging Face model must not be blank")
        self.model = model
        self.timeout = timeout
        self._headers = {"Authorization": f"Bearer {token}"}

    @property
    def endpoint(self) -> str:
        """Return the model's feature-extraction endpoint."""
        return (
            "https://router.huggingface.co/hf-inference/models/"
            f"{self.model}/pipeline/feature-extraction"
        )

    def embed(self, text: str) -> np.ndarray:
        """Request an embedding and normalize it for inner-product search."""
        if not text.strip():
            raise ValueError("cannot embed blank text")
        response = requests.post(
            self.endpoint,
            headers=self._headers,
            json={"inputs": text},
            timeout=self.timeout,
        )
        response.raise_for_status()
        vector = _pool_embedding(response.json())
        faiss.normalize_L2(vector)
        return vector[0]


def _pool_embedding(payload: Any) -> np.ndarray:
    """Convert HF vectors to one float32 row, mean-pooling token vectors."""
    values = np.asarray(payload, dtype="float32")
    if values.ndim == 1:
        values = values.reshape(1, -1)
    elif values.ndim == 2:
        values = values.mean(axis=0, keepdims=True)
    else:
        raise ValueError("embedding response must be a one- or two-dimensional array")
    if values.shape[1] == 0 or not np.isfinite(values).all():
        raise ValueError("embedding response must contain finite values")
    return values
