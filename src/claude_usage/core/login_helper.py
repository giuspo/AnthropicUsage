"""1-Click OAuth Login Helper for Claude Code CLI without getting stuck."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ClaudeLoginHelper:
    """Spawns Claude Code official OAuth login and watches for credential updates."""

    _active_process: Optional[subprocess.Popen] = None
    _is_cancelling: bool = False

    @classmethod
    def get_login_command(cls) -> Optional[list[str]]:
        """Determines the appropriate command to launch login (claude or npx)."""
        if shutil.which("claude"):
            return ["claude", "auth", "login"]

        if shutil.which("npx"):
            return ["npx", "-y", "@anthropic-ai/claude-code", "auth", "login"]

        return None

    @classmethod
    def cancel_login(cls) -> None:
        """Terminates any active login subprocess."""
        cls._is_cancelling = True
        if cls._active_process:
            try:
                cls._active_process.terminate()
            except Exception:
                pass
            cls._active_process = None

    @classmethod
    async def execute_login(
        cls,
        status_callback: Optional[Callable[[str], None]] = None,
        timeout_seconds: int = 120,
    ) -> bool:
        """Executes the login flow, opening browser and console, and waits for credentials."""
        cls._is_cancelling = False
        cmd = cls.get_login_command()
        if not cmd:
            if status_callback:
                status_callback("Errore: Node.js / npx non trovato.")
            return False

        if status_callback:
            status_callback("Apertura finestra di autenticazione...")

        creds_file = Path.home() / ".claude" / ".credentials.json"
        initial_mtime = creds_file.stat().st_mtime if creds_file.exists() else 0.0

        try:
            if sys.platform == "win32":
                # Launch via start command so a visible terminal runs the login flow
                # and opens the browser without hanging detached pipes.
                # '|| pause' ensures any error message remains visible instead of closing instantly.
                command_str = " ".join(f'"{c}"' if " " in c else c for c in cmd)
                full_cmd = f'cmd.exe /c start "Claude Code Login" cmd.exe /c "{command_str} || pause"'
                cls._active_process = subprocess.Popen(full_cmd, shell=True)
            else:
                cls._active_process = subprocess.Popen(cmd)

            # Poll for credentials file modification
            elapsed = 0
            while elapsed < timeout_seconds and not cls._is_cancelling:
                await asyncio.sleep(1.0)
                elapsed += 1

                # Check if credentials file was updated
                if creds_file.exists():
                    current_mtime = creds_file.stat().st_mtime
                    if current_mtime > initial_mtime:
                        logger.info("Credentials file detected!")
                        if status_callback:
                            status_callback("✅ Accesso completato con successo!")
                        return True

                if status_callback and elapsed == 3:
                    status_callback("Completa l'accesso nel browser o nella console aperta...")

            if cls._is_cancelling:
                if status_callback:
                    status_callback("Login annullato.")
                return False

            if status_callback:
                status_callback("Tempo scaduto. Riprova.")
            return False

        except Exception as e:
            logger.error(f"Error executing login: {e}")
            if status_callback:
                status_callback(f"Errore: {e}")
            return False
        finally:
            cls.cancel_login()

    @classmethod
    def logout(cls) -> bool:
        """Clears local credentials across files and OS Keyring."""
        import keyring

        success = False
        # 1. Delete credentials files
        for p in [
            Path.home() / ".claude" / ".credentials.json",
            Path.home() / ".claude.json",
        ]:
            if p.exists():
                try:
                    p.unlink()
                    success = True
                    logger.info(f"Deleted credentials file {p}")
                except Exception as e:
                    logger.warning(f"Error removing {p}: {e}")

        # 2. Delete from OS keyring
        for service in ["Claude Code-credentials"]:
            for acct in ["claude-code", ""]:
                try:
                    keyring.delete_password(service, acct)
                    success = True
                except Exception:
                    pass

        return success
