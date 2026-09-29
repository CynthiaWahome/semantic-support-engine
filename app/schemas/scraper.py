"""Typed records produced by the Slack Q&A extraction stage."""

from pydantic import BaseModel, ConfigDict, Field


class ThreadContextMessage(BaseModel):
    """A sanitized reply included as extraction context."""

    model_config = ConfigDict(extra="forbid")

    author: str
    text: str
    is_mentor: bool


class ScrapedQAPair(BaseModel):
    """The highest-scoring answer extracted from one Slack thread."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    confidence_score: float = Field(ge=0.0, le=1.0)
    is_trusted_answer: bool
    source_channel: str = Field(min_length=1)
    thread_ts: str = Field(min_length=1)
    asker_name: str = Field(min_length=1)
    answerer_name: str = Field(min_length=1)
    date: str = Field(min_length=1)
    full_thread_context: list[ThreadContextMessage]
