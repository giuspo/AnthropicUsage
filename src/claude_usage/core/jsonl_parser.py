"""Incremental parser for local Claude Code JSONL transcripts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from claude_usage.core.models import TokenBreakdown

logger = logging.getLogger(__name__)


def clean_project_name(raw_name: str) -> str:
    """Formats raw path-encoded project folder names into clean labels."""
    if not raw_name or raw_name in ("Nessun progetto", "projects", "Claude Code"):
        return "Claude Code"

    # Handle path-encoded folder names like 'C--Windows-System32' or 'D--Git-AnthropicUsage'
    if "--" in raw_name:
        parts = raw_name.split("--")
        last_part = parts[-1]
        # If there are subfolders with dashes
        sub_parts = [p for p in last_part.split("-") if p]
        if sub_parts:
            leaf = sub_parts[-1]
            if leaf.lower() in ("system32", "windows", "system", "cmd"):
                return "Claude Code"
            return leaf

    if raw_name.lower() in ("system32", "windows"):
        return "Claude Code"

    return raw_name


class JsonlParser:
    """Parses local session logs to extract Input, Output, and Thinking tokens."""

    def __init__(self, projects_dir: Optional[Path] = None):
        self.projects_dir = projects_dir or (Path.home() / ".claude" / "projects")

    def parse_recent_window(self, window_hours: int = 5) -> Tuple[TokenBreakdown, str]:
        """Scans JSONL files modified within the rolling window and aggregates token counts."""
        if not self.projects_dir.exists():
            return TokenBreakdown(), "Claude Code"

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        total_in = 0
        total_out = 0
        total_thinking = 0
        total_cache_read = 0
        total_cache_write = 0
        most_recent_project = "Claude Code"
        most_recent_mtime = 0.0

        try:
            jsonl_files = list(self.projects_dir.glob("**/*.jsonl"))
        except Exception as e:
            logger.debug(f"Error globbing JSONL files: {e}")
            return TokenBreakdown(), "Claude Code"

        for filepath in jsonl_files:
            try:
                stat = filepath.stat()
                file_mtime = stat.st_mtime
                file_dt = datetime.fromtimestamp(file_mtime, tz=timezone.utc)
                if file_dt < cutoff_time:
                    continue

                if file_mtime > most_recent_mtime:
                    most_recent_mtime = file_mtime
                    # Folder name is typically the project identifier
                    parent_name = filepath.parent.name
                    if parent_name and parent_name != "projects":
                        most_recent_project = parent_name

                # Parse the file, deduplicating messages by message ID
                msg_cache: dict[str, dict] = {}
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            msg = record.get("message")
                            if isinstance(msg, dict):
                                msg_id = msg.get("id")
                                if msg_id:
                                    msg_cache[msg_id] = msg
                                else:
                                    # Fallback if no ID
                                    self._accumulate_usage(
                                        msg,
                                        total_in,
                                        total_out,
                                        total_thinking,
                                        total_cache_read,
                                        total_cache_write,
                                    )
                            elif record.get("type") == "usage" and isinstance(record.get("usage"), dict):
                                # Direct usage record
                                u = record["usage"]
                                total_in += int(u.get("input_tokens", 0))
                                total_out += int(u.get("output_tokens", 0))
                                total_cache_read += int(u.get("cache_read_input_tokens", 0))
                                total_cache_write += int(u.get("cache_creation_input_tokens", 0))
                                thinking = self._extract_thinking(record, u)
                                total_thinking += thinking
                        except Exception:
                            continue

                # Accumulate the deduplicated final message states
                for msg in msg_cache.values():
                    usage = msg.get("usage")
                    if isinstance(usage, dict):
                        in_tok = int(usage.get("input_tokens", 0))
                        out_tok = int(usage.get("output_tokens", 0))
                        c_read = int(usage.get("cache_read_input_tokens", 0))
                        c_write = int(usage.get("cache_creation_input_tokens", 0))
                        thinking = self._extract_thinking(msg, usage)

                        total_in += in_tok
                        total_out += out_tok
                        total_cache_read += c_read
                        total_cache_write += c_write
                        total_thinking += thinking

            except Exception as e:
                logger.debug(f"Error parsing {filepath}: {e}")
                continue

        breakdown = TokenBreakdown(
            input_tokens=total_in,
            output_tokens=total_out,
            thinking_tokens=total_thinking,
            cache_read_tokens=total_cache_read,
            cache_write_tokens=total_cache_write,
            total_tokens=total_in + total_out + total_cache_read + total_cache_write,
        )
        return breakdown, clean_project_name(most_recent_project)

    def _extract_thinking(self, container: dict, usage: dict) -> int:
        """Extracts thinking tokens from usage details or message content."""
        # Check output_tokens_details
        details = usage.get("output_tokens_details") or {}
        if isinstance(details, dict) and "thinking_tokens" in details:
            return int(details["thinking_tokens"])

        # Check content blocks for type == "thinking"
        content = container.get("content")
        if isinstance(content, list):
            thinking_chars = 0
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    text = block.get("thinking", "")
                    thinking_chars += len(text)
            if thinking_chars > 0:
                # Approximate 1 token ~ 3.8 characters for thinking blocks
                return max(1, int(thinking_chars / 3.8))

        return 0

    def _accumulate_usage(self, msg: dict, t_in: int, t_out: int, t_think: int, t_cr: int, t_cw: int) -> None:
        usage = msg.get("usage")
        if isinstance(usage, dict):
            t_in += int(usage.get("input_tokens", 0))
            t_out += int(usage.get("output_tokens", 0))
            t_cr += int(usage.get("cache_read_input_tokens", 0))
            t_cw += int(usage.get("cache_creation_input_tokens", 0))
            t_think += self._extract_thinking(msg, usage)

