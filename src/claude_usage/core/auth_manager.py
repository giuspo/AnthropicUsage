"""Authentication Manager for Claude Code credentials discovery and lifecycle."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import keyring

from claude_usage.core.models import AuthProviderType, AuthState

logger = logging.getLogger(__name__)

KEYCHAIN_CLAUDE_SERVICE = "Claude Code-credentials"


class AuthManager:
    """Discovers and refreshes credentials across Keyring, files, and environment."""

    def __init__(self, admin_api_key: Optional[str] = None):
        self.admin_api_key = admin_api_key
        self._current_state = AuthState()

    def clear(self) -> None:
        """Resets cached credentials in memory."""
        self._current_state = AuthState(
            provider=AuthProviderType.NONE,
            is_valid=False,
            error_message="Disconnesso. Clicca su 'Accedi con Claude'.",
        )

    def get_credentials(self, force_reload: bool = False) -> AuthState:
        """Resolves active credentials following the priority chain."""
        if self._current_state.is_valid and not force_reload and not self._current_state.is_expired():
            return self._current_state

        state = self._resolve_credentials()
        self._current_state = state
        return state

    def _resolve_credentials(self) -> AuthState:
        # Priority 1: Keyring / Credential Manager (CLI session)
        keyring_state = self._read_os_keyring()
        if keyring_state and keyring_state.is_valid:
            return keyring_state

        # Priority 2: File ~/.claude/.credentials.json
        file_state = self._read_credentials_file()
        if file_state and file_state.is_valid:
            return file_state

        # Priority 3: Environment variable CLAUDE_CODE_OAUTH_TOKEN
        env_state = self._read_env()
        if env_state and env_state.is_valid:
            return env_state

        # Priority 4: Manual Key or Token (Enterprise Admin or Direct OAuth)
        if self.admin_api_key:
            key = self.admin_api_key.strip()
            if key.startswith("sk-ant-admin-"):
                return AuthState(
                    provider=AuthProviderType.ADMIN_API_KEY,
                    admin_api_key=key,
                    subscription_type="enterprise",
                    is_valid=True,
                    workspace_name="Enterprise Admin",
                )
            elif key.startswith("sk-ant-oat") or key.startswith("{"):
                if key.startswith("{"):
                    parsed = self._parse_oauth_payload(key, AuthProviderType.OAUTH_ENV)
                    if parsed:
                        return parsed
                return AuthState(
                    provider=AuthProviderType.OAUTH_ENV,
                    access_token=key,
                    subscription_type="team",
                    is_valid=True,
                    workspace_name="Claude Team Account",
                )
            elif key.startswith("sk-ant-api"):
                # Standard API Key (used with Admin API or Console)
                return AuthState(
                    provider=AuthProviderType.ADMIN_API_KEY,
                    admin_api_key=key,
                    subscription_type="api_key",
                    is_valid=True,
                    workspace_name="Anthropic API Key",
                )

        return AuthState(
            provider=AuthProviderType.NONE,
            is_valid=False,
            error_message="Nessuna sessione trovata. Fai il login con la CLI o inserisci una chiave.",
        )

    def _read_os_keyring(self) -> Optional[AuthState]:
        """Queries Windows Credential Manager or Linux Secret Service."""
        try:
            # Claude Code stores its session under service "Claude Code-credentials"
            raw = keyring.get_password(KEYCHAIN_CLAUDE_SERVICE, "claude-code")
            if not raw:
                # Try default account name if none
                raw = keyring.get_password(KEYCHAIN_CLAUDE_SERVICE, "")
            if raw:
                return self._parse_oauth_payload(raw, AuthProviderType.OAUTH_CLI)
        except Exception as e:
            logger.debug(f"Keyring read error: {e}")
        return None

    def _read_credentials_file(self) -> Optional[AuthState]:
        """Reads ~/.claude/.credentials.json."""
        paths_to_check = [
            Path.home() / ".claude" / ".credentials.json",
            Path.home() / ".claude.json",
        ]
        if sys.platform == "win32":
            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                paths_to_check.append(Path(user_profile) / ".claude" / ".credentials.json")

        for p in paths_to_check:
            if p.exists() and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        raw = f.read()
                    state = self._parse_oauth_payload(raw, AuthProviderType.OAUTH_CLI)
                    if state and state.is_valid:
                        return state
                except Exception as e:
                    logger.debug(f"Failed reading {p}: {e}")
        return None

    def _read_env(self) -> Optional[AuthState]:
        """Reads CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_ADMIN_API_KEY."""
        oauth_token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        if oauth_token:
            # Check if it is a JSON string payload or raw token
            if oauth_token.strip().startswith("{"):
                return self._parse_oauth_payload(oauth_token, AuthProviderType.OAUTH_ENV)
            else:
                return AuthState(
                    provider=AuthProviderType.OAUTH_ENV,
                    access_token=oauth_token.strip(),
                    subscription_type="pro",
                    is_valid=True,
                    workspace_name="CLI Env Token",
                )

        admin_key = os.environ.get("ANTHROPIC_ADMIN_API_KEY")
        if admin_key and admin_key.startswith("sk-ant-admin-"):
            return AuthState(
                provider=AuthProviderType.ADMIN_API_KEY,
                admin_api_key=admin_key.strip(),
                subscription_type="enterprise",
                is_valid=True,
                workspace_name="Enterprise Env Key",
            )
        return None

    def _parse_oauth_payload(self, raw_json: str, provider: AuthProviderType) -> Optional[AuthState]:
        try:
            data = json.loads(raw_json)
            oauth_data = data.get("claudeAiOauth", data)
            access_token = oauth_data.get("accessToken")
            if not access_token:
                return None

            refresh_token = oauth_data.get("refreshToken")
            expires_at = oauth_data.get("expiresAt")
            sub_type = oauth_data.get("subscriptionType", "pro")
            rate_tier = oauth_data.get("rateLimitTier", "default")

            return AuthState(
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                subscription_type=sub_type,
                rate_limit_tier=rate_tier,
                is_valid=True,
                workspace_name=f"Claude Code ({sub_type.capitalize()})",
            )
        except Exception as e:
            logger.debug(f"JSON parsing error for credentials: {e}")
            return None

    async def refresh_if_expired(self) -> AuthState:
        """Silently re-reads credentials from keyring or triggers OAuth refresh if needed."""
        state = self.get_credentials()
        if not state.is_valid:
            return state

        if state.is_expired():
            # First try re-reading: the user's active CLI may have already refreshed it
            fresh = self._resolve_credentials()
            if fresh and fresh.is_valid and not fresh.is_expired():
                self._current_state = fresh
                return fresh

            # If still expired and we have a refresh token, perform refresh
            if state.refresh_token:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(
                            "https://platform.claude.com/v1/oauth/token",
                            json={
                                "grant_type": "refresh_token",
                                "refresh_token": state.refresh_token,
                            },
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            state.access_token = data.get("access_token", state.access_token)
                            state.refresh_token = data.get("refresh_token", state.refresh_token)
                            expires_in = data.get("expires_in", 3600)
                            state.expires_at = int((resp.headers.get("date") or 0)) + (expires_in * 1000)
                            self._current_state = state
                except Exception as e:
                    logger.warning(f"OAuth token refresh attempt failed: {e}")

        return self._current_state

