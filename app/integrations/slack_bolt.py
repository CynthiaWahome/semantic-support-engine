"""Optional Slack Bolt event registration for Socket Mode or HTTP adapters."""

from typing import Any

from slack_bolt import App
from slack_sdk.web.client import WebClient

from app.integrations.slack import answer_slack_event
from app.services.slack_answering import SlackAnsweringService


def create_slack_app(
    service: SlackAnsweringService,
    *,
    token: str | None = None,
    signing_secret: str | None = None,
    token_verification_enabled: bool = True,
) -> App:
    """Register only the message events needed for Slack answering."""
    app_settings = {
        name: value
        for name, value in {
            "token": token,
            "signing_secret": signing_secret,
            "token_verification_enabled": token_verification_enabled,
        }.items()
        if value is not None
    }
    slack_app = App(**app_settings)

    @slack_app.event("message")
    def handle_message(event: dict[str, Any], client: WebClient) -> None:
        answer_slack_event(event, client, service)

    @slack_app.event("app_mention")
    def handle_app_mention(event: dict[str, Any], client: WebClient) -> None:
        answer_slack_event(event, client, service)

    return slack_app
