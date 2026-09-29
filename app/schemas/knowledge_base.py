"""Knowledge-base storage and HTTP contracts (not ORM entities)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class KnowledgeTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[NonBlank]
    answer: NonBlank
    priority: int = 0


class QuestionRequest(BaseModel):
    question: Annotated[NonBlank, Field(max_length=4000)]


class AnswerResponse(BaseModel):
    answer: str
    source: Literal["knowledge_base", "semantic_retrieval", "fallback"]


class SyncRowError(BaseModel):
    """Locate invalid input without returning private cell contents."""

    tab: str
    row: int
    reason: str


class SyncResult(BaseModel):
    success: bool
    topics_written: int = 0
    errors: list[SyncRowError] = Field(default_factory=list)
