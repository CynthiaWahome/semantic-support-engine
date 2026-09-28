"""Read-only question answering; no public spreadsheet synchronization route."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.knowledge_base import get_knowledge_base_service
from app.schemas.knowledge_base import AnswerResponse, QuestionRequest
from app.services.knowledge_base import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


@router.post("/answer", response_model=AnswerResponse)
def answer_question(
    body: QuestionRequest,
    service: Annotated[KnowledgeBaseService, Depends(get_knowledge_base_service)],
) -> AnswerResponse:
    return service.answer(body.question)
