"""Tests for AuthManager credential discovery and parsing."""

import json
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from claude_usage.core.auth_manager import AuthManager
from claude_usage.core.models import AuthProviderType, AuthState


def test_auth_state_expiration():
    state = AuthState(expires_at=1000)  # long in past
    assert state.is_expired() is True

    future_ms = int(3000000000 * 1000)
    state_future = AuthState(expires_at=future_ms)
    assert state_future.is_expired() is False


def test_parse_oauth_payload_json():
    auth_mgr = AuthManager()
    payload = json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": "mock-oauth-access-token",
                "refreshToken": "mock-oauth-refresh-token",
                "expiresAt": 1780000000000,
                "subscriptionType": "pro",
                "rateLimitTier": "default",
            }
        }
    )

    state = auth_mgr._parse_oauth_payload(payload, AuthProviderType.OAUTH_CLI)
    assert state is not None
    assert state.is_valid is True
    assert state.access_token == "mock-oauth-access-token"
    assert state.refresh_token == "mock-oauth-refresh-token"
    assert state.subscription_type == "pro"


def test_env_token_fallback():
    auth_mgr = AuthManager()
    with patch.dict("os.environ", {"CLAUDE_CODE_OAUTH_TOKEN": "mock-env-access-token"}):
        state = auth_mgr._read_env()
        assert state is not None
        assert state.provider == AuthProviderType.OAUTH_ENV
        assert state.access_token == "mock-env-access-token"


def test_admin_api_key_resolution():
    auth_mgr = AuthManager(admin_api_key="sk-ant-admin-mock-test-key-00000")
    with patch.object(auth_mgr, "_read_credentials_file", return_value=None), patch.object(
        auth_mgr, "_read_os_keyring", return_value=None
    ):
        state = auth_mgr.get_credentials(force_reload=True)
        assert state.provider == AuthProviderType.ADMIN_API_KEY
        assert state.admin_api_key == "sk-ant-admin-mock-test-key-00000"
        assert state.subscription_type == "enterprise"


def _step_coro(coro):
    """Executes a coroutine synchronously without starting an IOCP loop."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    raise RuntimeError("Coroutine did not finish in one step")


def test_auth_manager_refresh_token_success():
    auth_mgr = AuthManager()
    auth_mgr._current_state = AuthState(
        provider=AuthProviderType.OAUTH_CLI,
        access_token="old-expired-token",
        refresh_token="valid-refresh-token",
        expires_at=1000,
        is_valid=True,
    )

    fake_response = {
        "access_token": "new-shiny-access-token",
        "refresh_token": "new-rotated-refresh-token",
        "expires_in": 7200,
    }

    async def fake_post(*args, **kwargs):
        return (200, fake_response, "")

    with patch.object(
        auth_mgr, "_post_refresh_request", side_effect=fake_post
    ) as mock_post, patch.object(
        auth_mgr, "_persist_credentials"
    ) as mock_persist, patch.object(
        auth_mgr, "_read_os_keyring", return_value=None
    ), patch.object(
        auth_mgr, "_read_credentials_file", return_value=None
    ):
        success = _step_coro(auth_mgr.refresh_token(force=True))
        assert success is True
        assert auth_mgr._current_state.access_token == "new-shiny-access-token"
        assert auth_mgr._current_state.refresh_token == "new-rotated-refresh-token"
        assert mock_persist.called


def test_api_client_auto_refresh_on_401():
    from claude_usage.core.api_client import ApiClient

    auth_mgr = AuthManager()
    auth_mgr._current_state = AuthState(
        provider=AuthProviderType.OAUTH_CLI,
        access_token="initial-token",
        refresh_token="refresh-token",
        expires_at=9999999999999,
        is_valid=True,
    )

    client = ApiClient(auth_manager=auth_mgr)

    responses = [
        # First call -> 401 Unauthorized
        (401, {"error": "unauthorized"}, None),
        # Second call (after auto-refresh retry) -> 200 OK
        (
            200,
            {
                "five_hour": {"utilization": 25.0, "resets_at": "2026-11-03T20:00:00Z"},
                "seven_day": {"utilization": 40.0, "resets_at": "2026-11-10T20:00:00Z"},
            },
            None,
        ),
    ]

    async def fake_get(*args, **kwargs):
        return responses.pop(0)

    async def fake_refresh(force=False):
        auth_mgr._current_state.access_token = "fresh-token-after-refresh"
        return True

    with patch.object(
        client, "_get_oauth_usage", side_effect=fake_get
    ) as mock_get, patch.object(
        auth_mgr, "refresh_token", side_effect=fake_refresh
    ) as mock_refresh, patch.object(
        auth_mgr, "_read_os_keyring", return_value=None
    ), patch.object(
        auth_mgr, "_read_credentials_file", return_value=None
    ):
        snap = _step_coro(client.fetch_usage(auth_mgr.get_credentials()))
        assert mock_refresh.called
        assert snap.is_offline is False
        assert snap.five_hour.utilization_pct == 25.0


