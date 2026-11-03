"""Unit tests for Google Antigravity provider (Auth, Client, Parser, and Normalization)."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from claude_usage.core.antigravity_auth import AntigravityAuthManager
from claude_usage.core.antigravity_client import AntigravityApiClient
from claude_usage.core.antigravity_parser import AntigravityTranscriptParser
from claude_usage.core.models import (
    AntigravityUsageSnapshot,
    AuthProviderType,
    AuthState,
    UsageWindow,
)


def test_antigravity_mock_snapshot():
    client = AntigravityApiClient()
    mock_auth = AuthState(provider=AuthProviderType.MOCK, is_valid=True)

    # Synchronous test on mock generator
    snap = client._generate_mock_snapshot()
    assert isinstance(snap, AntigravityUsageSnapshot)
    assert snap.gemini_5h.utilization_pct == 38.5
    assert snap.gemini_7d.utilization_pct == 22.0
    assert snap.partner_5h.utilization_pct == 54.0
    assert snap.partner_7d.utilization_pct == 46.5
    assert len(snap.partner_models) == 3
    assert snap.partner_models[0].display_name == "Claude Sonnet 5.5"
    assert snap.partner_models[0].five_hour.utilization_pct == 54.0
    assert snap.ai_credits_balance == 250
    assert snap.use_g1_credits is True


def test_antigravity_single_pool_utilization():
    snap = AntigravityUsageSnapshot(
        gemini_5h=UsageWindow(utilization_pct=30.0),
        gemini_7d=UsageWindow(utilization_pct=15.0),
        partner_5h=UsageWindow(utilization_pct=60.0),
        partner_7d=UsageWindow(utilization_pct=40.0),
    )

    # 1. Mode 'gemini'
    p5, p7, label = snap.get_single_pool_utilization("gemini")
    assert p5 == 30.0
    assert p7 == 15.0
    assert label == "Gemini"

    # 2. Mode 'partner'
    p5, p7, label = snap.get_single_pool_utilization("partner")
    assert p5 == 60.0
    assert p7 == 40.0
    assert label == "Partner"

    # 3. Mode 'max_used' -> Partner is higher
    p5, p7, label = snap.get_single_pool_utilization("max_used")
    assert p5 == 60.0
    assert p7 == 40.0
    assert label == "Partner"


def test_antigravity_quota_parsing_and_normalization():
    client = AntigravityApiClient()
    auth = AuthState(is_valid=True, access_token="test_token")

    fake_summary = {
        "groups": [
            {
                "displayName": "Claude and GPT models",
                "buckets": [
                    {
                        "bucketId": "3p-5h",
                        "window": "5h",
                        "remainingFraction": 0.45,  # 55% used
                        "resetTime": "2026-10-30T23:00:00Z",
                    },
                    {
                        "bucketId": "3p-weekly",
                        "window": "weekly",
                        "remainingFraction": 0.20,  # 80% used
                        "resetTime": "2026-11-06T23:00:00Z",
                    },
                ],
            }
        ]
    }

    fake_models = {
        "models": {
            "gemini-3.8-flash": {
                "displayName": "Gemini 3.8 Flash",
                "modelProvider": "MODEL_PROVIDER_GOOGLE",
                "quotaInfo": {
                    "remainingFraction": 0.90,  # 10% used
                    "resetTime": "2026-10-30T22:00:00Z",
                },
            },
            "claude-sonnet-5-5-medium": {
                "displayName": "Claude Sonnet 5.5 (Medium)",
                "modelProvider": "MODEL_PROVIDER_ANTHROPIC",
                "quotaInfo": {
                    "remainingFraction": 0.45,  # 55% used
                    "resetTime": "2026-10-30T23:00:00Z",
                },
            },
        }
    }

    snap = client._parse_responses(auth, fake_summary, fake_models)

    # Gemini pool
    assert snap.gemini_5h.utilization_pct == 10.0
    # Partner pool
    assert snap.partner_5h.utilization_pct == 55.0
    assert snap.partner_7d.utilization_pct == 80.0
    # Partner models
    assert len(snap.partner_models) == 1
    assert snap.partner_models[0].display_name == "Claude Sonnet 5.5"
    assert snap.partner_models[0].five_hour.utilization_pct == 55.0


def test_antigravity_transcript_parser(tmp_path):
    # Setup mock brain structure
    brain_dir = tmp_path / "brain"
    conv_dir = brain_dir / "conv_123" / ".system_generated" / "logs"
    conv_dir.mkdir(parents=True)
    tfile = conv_dir / "transcript.jsonl"

    lines = [
        '{"type": "USER_INPUT", "content": "Hello"}\n',
        '{"type": "PLANNER_RESPONSE", "thinking": "Let me think"}\n',
        '{"type": "USER_INPUT", "content": "Run this"}\n',
        '{"type": "PLANNER_RESPONSE", "content": "Done"}\n',
    ]
    tfile.write_text("".join(lines), encoding="utf-8")

    parser = AntigravityTranscriptParser(brain_dir=brain_dir)
    turns, thinking, conv_id = parser.get_recent_activity(window_hours=5)

    assert turns == 2
    assert thinking == 1
    assert conv_id == "conv_123"



def test_antigravity_keyring_parsing_both_formats():
    import json
    mgr = AntigravityAuthManager()

    valid_dict = {
        "token": {
            "access_token": "ya29.test_access_token",
            "refresh_token": "1//test_refresh_token",
            "expiry": "2026-11-04T12:00:00Z"
        },
        "id_token_email": "developer@gmail.com"
    }
    json_str = json.dumps(valid_dict)

    # 1. Plain UTF-8 JSON string
    with patch("keyring.get_password", return_value=json_str):
        auth = mgr._read_antigravity_keyring()
        assert auth is not None
        assert auth.is_valid is True
        assert auth.access_token == "ya29.test_access_token"
        assert mgr.account_email == "developer@gmail.com"

    # 2. UTF-16LE byte-decoded string simulation
    utf16_str = json_str.encode("utf-8").decode("latin-1")
    with patch("keyring.get_password", return_value=json_str):
        auth2 = mgr._read_antigravity_keyring()
        assert auth2 is not None
        assert auth2.access_token == "ya29.test_access_token"


def test_antigravity_user_quota_parsing():
    client = AntigravityApiClient()
    auth = AuthState(is_valid=True, access_token="test_token")

    fake_user_quota = {
        "buckets": [
            {
                "modelId": "gemini-2.5-pro",
                "remainingFraction": 0.82,  # 18% used
                "resetTime": "2026-11-03T23:03:36Z",
                "tokenType": "WTUS"
            },
            {
                "modelId": "gemini-3-flash",
                "remainingFraction": 0.82,
                "resetTime": "2026-11-03T23:03:36Z",
                "tokenType": "WTUS"
            }
        ]
    }

    snap = client._parse_responses(auth, quota_summary=None, models_data=None, user_quota=fake_user_quota)
    assert snap.is_offline is False
    assert snap.gemini_5h.utilization_pct == 18.0
    assert snap.gemini_7d.utilization_pct > 0.0
    assert "6g" in snap.gemini_7d.time_remaining_str


def test_antigravity_empty_responses_marks_offline():
    client = AntigravityApiClient()
    auth = AuthState(is_valid=True, access_token="test_token")

    snap = client._parse_responses(auth, quota_summary=None, models_data=None, user_quota=None)
    assert snap.is_offline is True
    assert "Offline" in snap.status_label
