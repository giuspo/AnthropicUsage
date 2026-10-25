"""Tests for AuthManager credential discovery and parsing."""

import json
from unittest.mock import patch

import pytest

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

