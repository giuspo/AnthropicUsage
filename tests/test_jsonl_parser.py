"""Tests for JsonlParser transcript reading and deduplication."""

import json
from pathlib import Path

import pytest

from claude_usage.core.jsonl_parser import JsonlParser, clean_project_name


def test_clean_project_name():
    assert clean_project_name("C--Windows-System32") == "Claude Code"
    assert clean_project_name("D--Git-AnthropicUsage") == "AnthropicUsage"
    assert clean_project_name("Nessun progetto") == "Claude Code"
    assert clean_project_name("MyCustomProject") == "MyCustomProject"


def test_jsonl_parser_deduplication(tmp_path: Path):
    proj_dir = tmp_path / "projects" / "MyWorkspace"
    proj_dir.mkdir(parents=True)
    jsonl_file = proj_dir / "session.jsonl"

    # Write multiple turns including streaming chunks with the same message id
    records = [
        # Chunk 1 of msg_01 (placeholder tokens)
        {
            "type": "assistant_response",
            "message": {
                "id": "msg_01",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 5,
                    "cache_read_input_tokens": 50,
                    "cache_creation_input_tokens": 10,
                },
            },
        },
        # Chunk 2 of msg_01 (final tokens)
        {
            "type": "assistant_response",
            "message": {
                "id": "msg_01",
                "content": [{"type": "thinking", "thinking": "Thinking step by step..."}],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 25,
                    "cache_read_input_tokens": 50,
                    "cache_creation_input_tokens": 10,
                },
            },
        },
        # Turn 2: msg_02
        {
            "type": "assistant_response",
            "message": {
                "id": "msg_02",
                "usage": {
                    "input_tokens": 200,
                    "output_tokens": 40,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "output_tokens_details": {"thinking_tokens": 15},
                },
            },
        },
    ]

    with open(jsonl_file, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")

    parser = JsonlParser(projects_dir=tmp_path / "projects")
    breakdown, project_name = parser.parse_recent_window(window_hours=24)

    assert project_name == "MyWorkspace"
    # msg_01 (100) + msg_02 (200) = 300
    assert breakdown.input_tokens == 300
    # msg_01 (25) + msg_02 (40) = 65 (chunk 1 was deduplicated)
    assert breakdown.output_tokens == 65
    # Thinking tokens: estimated from msg_01 + explicit in msg_02 (15)
    assert breakdown.thinking_tokens > 15
    assert breakdown.cache_read_tokens == 50

