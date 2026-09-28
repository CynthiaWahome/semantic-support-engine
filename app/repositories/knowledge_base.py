"""Repository boundary and atomic JSON storage, adapted from Thanos."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from app.schemas.knowledge_base import KnowledgeTopic

logger = logging.getLogger(__name__)
Topics = dict[str, KnowledgeTopic]
_topics_adapter = TypeAdapter(Topics)


class KnowledgeBaseRepository(Protocol):
    def get_all_topics(self) -> Topics:
        """Load a complete snapshot for question answering."""
        ...

    def set_all_topics(self, topics: Topics) -> None:
        """Replace the stored snapshot only after the caller validates it."""
        ...


class LocalKnowledgeBaseRepository:
    def __init__(self, path: Path):
        """Select a storage path without creating or changing files."""
        self.path = path

    def get_all_topics(self) -> Topics:
        """Load validated JSON, returning no topics if storage is unavailable."""
        try:
            return _topics_adapter.validate_json(self.path.read_bytes())
        except FileNotFoundError:
            return {}
        except (OSError, ValidationError):
            # Never log source content or provider credentials.
            logger.warning("Knowledge-base storage unavailable; using fallback")
            return {}

    def set_all_topics(self, topics: Topics) -> None:
        """Validate and atomically replace JSON using a unique temporary file."""
        payload = _topics_adapter.dump_json(_topics_adapter.validate_python(topics))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            # Unique temporary files avoid collisions between concurrent writers.
            with tempfile.NamedTemporaryFile(
                dir=self.path.parent, prefix=f".{self.path.name}.", delete=False
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_path, self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
