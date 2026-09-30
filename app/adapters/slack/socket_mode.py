"""Run the configured Slack answering application through Socket Mode."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.core.slack_runtime import create_configured_slack_service
from app.integrations.slack_bolt import create_slack_app

AppFactory = Callable[[Mapping[str, str]], App]
HandlerFactory = Callable[[App, str], SocketModeHandler]


def create_socket_mode_app(settings: Mapping[str, str]) -> App:
    """Compose the answering service and Bolt app for Socket Mode."""
    bot_token = _required_setting(settings, "SLACK_BOT_TOKEN")
    service = create_configured_slack_service(settings)
    return create_slack_app(
        service,
        token=bot_token,
        token_verification_enabled=False,
    )


def create_socket_mode_handler(
    settings: Mapping[str, str],
    *,
    app_factory: AppFactory = create_socket_mode_app,
    handler_factory: HandlerFactory = SocketModeHandler,
) -> SocketModeHandler:
    """Build a Socket Mode handler without starting a network connection."""
    app_token = _required_setting(settings, "SLACK_APP_TOKEN")
    return handler_factory(app_factory(settings), app_token)


def main() -> None:
    """Start the Slack Socket Mode process from environment configuration."""
    handler = create_socket_mode_handler(dict(os.environ))
    handler.start()


def _required_setting(settings: Mapping[str, str], name: str) -> str:
    """Return a non-blank setting without exposing its value."""
    value = settings.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} must be provided")
    return value


if __name__ == "__main__":
    main()
