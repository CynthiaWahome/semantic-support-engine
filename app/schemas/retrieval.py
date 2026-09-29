"""Contracts for semantic retrieval over curated support documents."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrievalDocument(BaseModel):
    """A sanitized support document that can be indexed for retrieval."""

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    source: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)


class RetrievedDocument(BaseModel):
    """A document and its normalized similarity score."""

    model_config = ConfigDict(extra="forbid")

    document: RetrievalDocument
    score: float = Field(ge=-1.0, le=1.0)
