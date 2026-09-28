"""Knowledge-base composition; no dotenv or credential-file access."""

import os
from pathlib import Path

from app.repositories.knowledge_base import LocalKnowledgeBaseRepository
from app.services.knowledge_base import KnowledgeBaseService


def get_repository() -> LocalKnowledgeBaseRepository:
    return LocalKnowledgeBaseRepository(
        Path(os.environ.get("KB_STORAGE_PATH", "data/kb_topics.json"))
    )


def get_knowledge_base_service() -> KnowledgeBaseService:
    return KnowledgeBaseService(get_repository())
