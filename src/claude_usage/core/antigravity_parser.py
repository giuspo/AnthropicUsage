"""Local transcript parser and filesystem watcher for Google Antigravity conversations."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class AntigravityTranscriptParser:
    """Parses local Antigravity transcript files (~/.gemini/antigravity/brain/**/transcript.jsonl)."""

    def __init__(self, brain_dir: Optional[Path] = None):
        if brain_dir:
            self.brain_dir = brain_dir
        else:
            if sys.platform == "win32":
                user_prof = os.environ.get("USERPROFILE") or str(Path.home())
                self.brain_dir = Path(user_prof) / ".gemini" / "antigravity" / "brain"
            else:
                self.brain_dir = Path.home() / ".gemini" / "antigravity" / "brain"

    def get_recent_activity(self, window_hours: int = 5) -> tuple[int, int, Optional[str]]:
        """Scans recent transcripts within window_hours.

        Returns (turn_count, thinking_steps_count, last_conversation_id).
        """
        if not self.brain_dir.exists():
            return 0, 0, None

        cutoff = time.time() - (window_hours * 3600)
        recent_transcripts: list[Path] = []

        try:
            for p in self.brain_dir.glob("*/.system_generated/logs/transcript.jsonl"):
                if p.is_file():
                    try:
                        if p.stat().st_mtime >= cutoff:
                            recent_transcripts.append(p)
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Error scanning brain transcripts: {e}")
            return 0, 0, None

        if not recent_transcripts:
            return 0, 0, None

        # Sort by mtime descending
        recent_transcripts.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        latest_conv_id = recent_transcripts[0].parent.parent.parent.name

        total_turns = 0
        total_thinking = 0

        for tfile in recent_transcripts:
            try:
                with open(tfile, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                            step_type = item.get("type")
                            if step_type == "USER_INPUT":
                                total_turns += 1
                            elif step_type == "PLANNER_RESPONSE":
                                if item.get("thinking"):
                                    total_thinking += 1
                        except Exception:
                            continue
            except Exception:
                continue

        return total_turns, total_thinking, latest_conv_id

