"""Tests for the Slack Socket Mode entrypoint without external connections."""

from unittest.mock import Mock

import pytest

from app.adapters.slack.socket_mode import (
    create_socket_mode_app,
    create_socket_mode_handler,
)


def test_socket_mode_handler_requires_app_token():
    with pytest.raises(ValueError, match="SLACK_APP_TOKEN must be provided"):
        create_socket_mode_handler({})


def test_socket_mode_handler_injects_app_and_token():
    fake_app = object()
    handler = Mock()

    result = create_socket_mode_handler(
        {"SLACK_APP_TOKEN": "xapp-test-token"},
        app_factory=lambda settings: fake_app,
        handler_factory=lambda app, token: handler,
    )

    assert result is handler


def test_socket_mode_app_requires_bot_token():
    with pytest.raises(ValueError, match="SLACK_BOT_TOKEN must be provided"):
        create_socket_mode_app({})
