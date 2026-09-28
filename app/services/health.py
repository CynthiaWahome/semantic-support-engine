"""Application liveness; external-service readiness is a separate concern."""

from typing import Literal


def get_liveness_status() -> Literal["ok"]:
    """An executing application can report liveness without external I/O."""
    return "ok"
