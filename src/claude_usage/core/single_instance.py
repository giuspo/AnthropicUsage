"""Single-instance application enforcement and IPC activation."""

from __future__ import annotations

import getpass
import logging
import os
import sys
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)


class SingleInstanceManager(QObject):
    """Guarantees a single instance of the application per user session.

    Uses Windows Named Mutex (atomic kernel check to prevent race conditions at boot)
    and Qt QLocalServer / QLocalSocket (cross-platform IPC to activate the running instance).
    """

    instance_activated = pyqtSignal()

    def __init__(self, app_name: str = "ClaudeCodeUsageWidget", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        username = getpass.getuser()
        self.unique_id = f"{app_name}_{username}"
        self._mutex = None
        self._server: Optional[QLocalServer] = None
        self._is_primary = False

    def acquire(self) -> bool:
        """Attempts to become the primary instance.

        Returns:
            True if this is the primary instance.
            False if another instance is already running.
        """
        # 1. On Windows, use a Named Mutex for atomic race-condition-proof detection
        if sys.platform == "win32":
            try:
                import ctypes

                mutex_name = f"Local\\{self.unique_id}_Mutex"
                self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
                last_error = ctypes.windll.kernel32.GetLastError()
                ERROR_ALREADY_EXISTS = 183

                if last_error == ERROR_ALREADY_EXISTS:
                    logger.info("Another instance detected via Windows Named Mutex.")
                    self._notify_existing_instance()
                    return False
            except Exception as e:
                logger.debug(f"Error checking Windows Named Mutex: {e}")

        # 2. Try to connect to an existing QLocalServer (works cross-platform)
        socket = QLocalSocket()
        socket.connectToServer(self.unique_id)
        if socket.waitForConnected(300):
            logger.info("Another instance is listening on QLocalServer.")
            try:
                socket.write(b"ACTIVATE")
                socket.waitForBytesWritten(500)
                socket.disconnectFromServer()
            except Exception:
                pass
            return False

        # If we reached here, this process is the primary instance.
        # Clean up any stale socket from a previous crash
        QLocalServer.removeServer(self.unique_id)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._handle_connection)
        if not self._server.listen(self.unique_id):
            logger.warning(f"Could not listen on QLocalServer '{self.unique_id}': {self._server.errorString()}")

        self._is_primary = True
        return True

    def _notify_existing_instance(self) -> None:
        """Sends an ACTIVATE message to the running instance via QLocalSocket."""
        try:
            socket = QLocalSocket()
            socket.connectToServer(self.unique_id)
            if socket.waitForConnected(300):
                socket.write(b"ACTIVATE")
                socket.waitForBytesWritten(500)
                socket.disconnectFromServer()
        except Exception as e:
            logger.debug(f"Could not send ACTIVATE signal: {e}")

    def _handle_connection(self) -> None:
        """Handles incoming IPC connection from a secondary instance attempting to launch."""
        if not self._server:
            return
        client = self._server.nextPendingConnection()
        if client:
            client.readyRead.connect(lambda: self._read_client_message(client))

    def _read_client_message(self, client: QLocalSocket) -> None:
        try:
            msg = bytes(client.readAll()).decode("utf-8", errors="ignore").strip()
            if msg == "ACTIVATE":
                logger.info("Received ACTIVATE request from secondary instance.")
                self.instance_activated.emit()
        except Exception as e:
            logger.debug(f"Error reading client IPC message: {e}")
        finally:
            client.disconnectFromServer()

    def release(self) -> None:
        """Releases the server socket and Windows Mutex."""
        if self._server:
            try:
                self._server.close()
                QLocalServer.removeServer(self.unique_id)
            except Exception:
                pass
            self._server = None

        if sys.platform == "win32" and self._mutex:
            try:
                import ctypes

                ctypes.windll.kernel32.CloseHandle(self._mutex)
            except Exception:
                pass
            self._mutex = None

