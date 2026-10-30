"""Google Antigravity authentication manager and credential discovery."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import httpx
import keyring

from claude_usage.core.models import AuthProviderType, AuthState

logger = logging.getLogger(__name__)

KEYRING_ANTIGRAVITY_SERVICE = "gemini:antigravity"
KEYRING_ANTIGRAVITY_ACCOUNT = "antigravity"

KEYRING_CUSTOM_SERVICE = "com.anthropic-usage.widget"
KEYRING_CUSTOM_GOOGLE_ACCOUNT = "google_antigravity_oauth"


class AntigravityAuthManager:
    """Discovers and manages OAuth tokens for Google Antigravity / Google AI Pro."""

    def __init__(self, manual_token: Optional[str] = None):
        self.manual_token = manual_token
        self._current_state = AuthState()
        self._account_email: Optional[str] = None

    @property
    def account_email(self) -> Optional[str]:
        return self._account_email

    def clear(self) -> None:
        """Resets cached credentials in memory."""
        self._current_state = AuthState(
            provider=AuthProviderType.NONE,
            is_valid=False,
            error_message="Disconnesso da Google Antigravity.",
        )
        self._account_email = None

    def get_credentials(self, force_reload: bool = False) -> AuthState:
        """Resolves active Google credentials following the priority chain."""
        if self._current_state.is_valid and not force_reload and not self._current_state.is_expired():
            return self._current_state

        state = self._resolve_credentials()
        self._current_state = state
        return state

    def _resolve_credentials(self) -> AuthState:
        # Priority 1: Native Keyring stored by Antigravity / agy (gemini:antigravity / antigravity)
        keyring_state = self._read_antigravity_keyring()
        if keyring_state and keyring_state.is_valid:
            return keyring_state

        # Priority 2: Custom Keyring saved via widget 1-Click login
        custom_keyring_state = self._read_custom_keyring()
        if custom_keyring_state and custom_keyring_state.is_valid:
            return custom_keyring_state

        # Priority 3: File ~/.gemini/oauth_creds.json
        file_state = self._read_oauth_file()
        if file_state and file_state.is_valid:
            return file_state

        # Priority 4: Manual token or environment variable
        env_token = os.environ.get("GOOGLE_OAUTH_TOKEN") or self.manual_token
        if env_token:
            return AuthState(
                provider=AuthProviderType.OAUTH_ENV,
                access_token=env_token.strip(),
                subscription_type="pro",
                workspace_name="Google AI Pro (Env)",
                is_valid=True,
            )

        return AuthState(
            provider=AuthProviderType.NONE,
            is_valid=False,
            error_message="Nessun account Google Antigravity trovato. Accedi con 'agy' o clicca Accedi.",
        )

    def _read_antigravity_keyring(self) -> Optional[AuthState]:
        """Reads OAuth credentials stored by agy / Antigravity CLI in Windows Credential Manager / Secret Service."""
        try:
            raw = keyring.get_password(KEYRING_ANTIGRAVITY_SERVICE, KEYRING_ANTIGRAVITY_ACCOUNT)
            if not raw:
                return None

            # On Windows, raw string from keyring might be UTF-16LE encoded bytes representing UTF-8 JSON
            payload_str = None
            try:
                raw_bytes = raw.encode("utf-16le")
                payload_str = raw_bytes.decode("utf-8")
            except Exception:
                payload_str = raw

            if payload_str and payload_str.strip().startswith("{"):
                data = json.loads(payload_str)
                token_obj = data.get("token", data)
                access_token = token_obj.get("access_token")
                refresh_token = token_obj.get("refresh_token")
                expiry_str = token_obj.get("expiry")
                email = data.get("id_token_email")
                if email:
                    self._account_email = email

                expires_at_ms = None
                if expiry_str:
                    try:
                        clean_exp = expiry_str.replace("Z", "+00:00")
                        exp_dt = datetime.fromisoformat(clean_exp)
                        expires_at_ms = int(exp_dt.timestamp() * 1000)
                    except Exception:
                        pass

                if access_token:
                    name = f"Google AI Pro ({email})" if email else "Google AI Pro"
                    return AuthState(
                        provider=AuthProviderType.OAUTH_CLI,
                        access_token=access_token,
                        refresh_token=refresh_token,
                        expires_at=expires_at_ms,
                        subscription_type="pro",
                        workspace_name=name,
                        is_valid=True,
                    )
        except Exception as e:
            logger.debug(f"Antigravity keyring read error: {e}")
        return None

    def _read_custom_keyring(self) -> Optional[AuthState]:
        try:
            raw = keyring.get_password(KEYRING_CUSTOM_SERVICE, KEYRING_CUSTOM_GOOGLE_ACCOUNT)
            if raw and raw.strip().startswith("{"):
                data = json.loads(raw)
                access_token = data.get("access_token")
                if access_token:
                    return AuthState(
                        provider=AuthProviderType.OAUTH_CLI,
                        access_token=access_token,
                        refresh_token=data.get("refresh_token"),
                        expires_at=data.get("expires_at"),
                        subscription_type="pro",
                        workspace_name="Google AI Pro (Saved)",
                        is_valid=True,
                    )
        except Exception as e:
            logger.debug(f"Custom keyring read error: {e}")
        return None

    def _read_oauth_file(self) -> Optional[AuthState]:
        oauth_file = Path.home() / ".gemini" / "oauth_creds.json"
        if not oauth_file.exists():
            return None

        try:
            with open(oauth_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            access_token = data.get("access_token")
            if not access_token:
                return None

            exp_ms = data.get("expiry_date")
            refresh_token = data.get("refresh_token")

            # Check accounts file for email
            email = self._read_active_email()
            if email:
                self._account_email = email
            name = f"Google AI Pro ({email})" if email else "Google AI Pro"

            return AuthState(
                provider=AuthProviderType.OAUTH_CLI,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=exp_ms,
                subscription_type="pro",
                workspace_name=name,
                is_valid=True,
            )
        except Exception as e:
            logger.debug(f"Error reading ~/.gemini/oauth_creds.json: {e}")
        return None

    def _read_active_email(self) -> Optional[str]:
        acc_file = Path.home() / ".gemini" / "google_accounts.json"
        if acc_file.exists():
            try:
                with open(acc_file, "r", encoding="utf-8") as f:
                    acc_data = json.load(f)
                active = acc_data.get("active")
                if isinstance(active, str):
                    return active
                elif isinstance(active, dict) and active:
                    return list(active.keys())[0]
            except Exception:
                pass
        return None

    async def refresh_if_expired(self) -> AuthState:
        """Checks expiration and triggers silent background refresh via agy CLI or keyring reload."""
        state = self.get_credentials()
        if not state.is_valid:
            return state

        if state.is_expired():
            # If agy CLI is installed, running a quick command refreshes credentials in keyring
            agy_bin = shutil.which("agy") or (
                str(Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe")
                if sys.platform == "win32"
                else None
            )
            if agy_bin and Path(agy_bin).exists():
                try:
                    proc = await asyncio.create_subprocess_exec(
                        agy_bin,
                        "models",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(proc.communicate(), timeout=8.0)
                    fresh = self._resolve_credentials()
                    if fresh and fresh.is_valid and not fresh.is_expired():
                        self._current_state = fresh
                        return fresh
                except Exception as e:
                    logger.debug(f"agy refresh failed: {e}")

            # Re-read credentials in case external app refreshed it
            fresh = self._resolve_credentials()
            if fresh and fresh.is_valid and not fresh.is_expired():
                self._current_state = fresh
                return fresh

        return self._current_state


class AntigravityLoginHelper:
    """Manages 1-Click login and logout for Google Antigravity."""

    _active_process: Optional[subprocess.Popen] = None

    @classmethod
    def get_agy_bin(cls) -> Optional[str]:
        cand = shutil.which("agy")
        if cand:
            return cand
        if sys.platform == "win32":
            local_agy = Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"
            if local_agy.exists():
                return str(local_agy)
        return None

    @classmethod
    async def execute_login(
        cls,
        status_callback: Optional[Callable[[str], None]] = None,
        timeout_seconds: int = 120,
    ) -> bool:
        """Launches agy login in a visible console and waits for credentials to update."""
        agy_bin = cls.get_agy_bin()
        if not agy_bin:
            if status_callback:
                status_callback("Errore: CLI 'agy' non trovata.")
            return False

        if status_callback:
            status_callback("Apertura terminale di accesso Google...")

        try:
            if sys.platform == "win32":
                cmd = f'cmd.exe /c start "Google Antigravity Login" "{agy_bin}" models'
                cls._active_process = subprocess.Popen(cmd, shell=True)
            else:
                cls._active_process = subprocess.Popen([agy_bin, "models"])

            elapsed = 0
            while elapsed < timeout_seconds:
                await asyncio.sleep(1.5)
                elapsed += 1
                mgr = AntigravityAuthManager()
                creds = mgr.get_credentials(force_reload=True)
                if creds.is_valid and not creds.is_expired():
                    if status_callback:
                        status_callback(f"✅ Connesso: {creds.workspace_name}")
                    return True

            if status_callback:
                status_callback("Tempo scaduto. Riprova.")
            return False
        except Exception as e:
            if status_callback:
                status_callback(f"Errore: {e}")
            return False

    @classmethod
    def logout(cls) -> bool:
        """Clears local custom Google tokens from keyring."""
        success = False
        try:
            keyring.delete_password(KEYRING_CUSTOM_SERVICE, KEYRING_CUSTOM_GOOGLE_ACCOUNT)
            success = True
        except Exception:
            pass
        return success

