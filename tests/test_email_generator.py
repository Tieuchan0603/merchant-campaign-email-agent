# test_email_generator.py
# Purpose: Unit tests for src/email_generator.py
#
# These tests check the parsing and prompt-building logic WITHOUT calling the
# real Claude API (no API key needed, no cost, runs instantly).
#
# For a live end-to-end test, see the bottom of this file.
#
# Run with:  python -m pytest tests/test_email_generator.py -v

import json
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
from src.email_generator import EmailGenerator


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SAMPLE_CAMPAIGN = {
    "Merchant": "KFC",
    "Campaign Name": "World Cup 2026",
    "Timeline": "1/7-31/7",
    "Scheme": "Giảm 20k cho đơn 99k",
    "Sponsor": "Zalopay fund 100%",
    "Channel": "ONLINE",
    "CTA": "Confirm trước 20/6",
}

VALID_JSON_RESPONSE = json.dumps({
    "subject": "Đề xuất triển khai CTKM World Cup 2026 cùng ZaloPay",
    "body": "Kính gửi Anh/Chị KFC,\n\nNội dung email...\n\nTrân trọng,\nĐội ngũ ZaloPay",
})


# ---------------------------------------------------------------------------
# Helper: create a generator with a mocked Anthropic client
# ---------------------------------------------------------------------------

def make_generator_with_mock(raw_response: str) -> EmailGenerator:
    """
    Create an EmailGenerator where the Claude API is replaced by a mock
    that always returns raw_response.

    Mocking means: we substitute the real API call with a fake one
    that returns whatever we tell it to — no network, no cost.
    """
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-fake-key"}):
        generator = EmailGenerator.__new__(EmailGenerator)
        generator.model = "claude-sonnet-4-6"
        generator.prompt_template = generator._load_prompt_template()

        # Build a fake message object that mimics what Claude returns.
        fake_content_block = MagicMock()
        fake_content_block.text = raw_response

        fake_message = MagicMock()
        fake_message.content = [fake_content_block]

        # Replace the real Anthropic client with a mock.
        generator.client = MagicMock()
        generator.client.messages.create.return_value = fake_message

    return generator


# ---------------------------------------------------------------------------
# Tests: JSON parsing
# ---------------------------------------------------------------------------

def test_parse_valid_json():
    """Should correctly extract subject and body from a valid JSON response."""
    gen = make_generator_with_mock(VALID_JSON_RESPONSE)
    result = gen.generate(SAMPLE_CAMPAIGN)

    assert result["subject"] == "Đề xuất triển khai CTKM World Cup 2026 cùng ZaloPay"
    assert "Kính gửi" in result["body"]
    assert "error" not in result


def test_parse_json_with_code_fence():
    """Should handle Claude wrapping JSON in ```json ... ``` code fences."""
    fenced = f"```json\n{VALID_JSON_RESPONSE}\n```"
    gen = make_generator_with_mock(fenced)
    result = gen.generate(SAMPLE_CAMPAIGN)

    assert result["subject"] != ""
    assert "error" not in result


def test_parse_invalid_json_returns_error():
    """Should return an error key (not crash) when Claude returns non-JSON."""
    gen = make_generator_with_mock("Xin chào, đây là email của bạn... (plain text, not JSON)")
    result = gen.generate(SAMPLE_CAMPAIGN)

    assert result["subject"] == ""
    assert result["body"] == ""
    assert "error" in result


def test_raw_response_always_present():
    """raw_response should always be in the result, regardless of success."""
    gen = make_generator_with_mock(VALID_JSON_RESPONSE)
    result = gen.generate(SAMPLE_CAMPAIGN)
    assert "raw_response" in result


def test_generate_with_approved_samples():
    """approved_samples string should be accepted without error."""
    gen = make_generator_with_mock(VALID_JSON_RESPONSE)
    result = gen.generate(
        campaign_data=SAMPLE_CAMPAIGN,
        approved_samples="Dear KFC, chúng tôi đề xuất...",
    )
    assert "error" not in result


def test_generate_with_user_instruction():
    """user_instruction string should be accepted without error."""
    gen = make_generator_with_mock(VALID_JSON_RESPONSE)
    result = gen.generate(
        campaign_data=SAMPLE_CAMPAIGN,
        user_instruction="Viết ngắn gọn, không quá 150 từ.",
    )
    assert "error" not in result


def test_prompt_contains_merchant_name():
    """The built prompt should include the merchant name."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-fake-key"}):
        gen = EmailGenerator.__new__(EmailGenerator)
        gen.model = "claude-sonnet-4-6"
        gen.prompt_template = gen._load_prompt_template()
        gen.client = MagicMock()

    prompt = gen._build_prompt(SAMPLE_CAMPAIGN, "", "")
    assert "KFC" in prompt
    assert "World Cup 2026" in prompt
    assert "1/7-31/7" in prompt


# ---------------------------------------------------------------------------
# Live test (manual, requires real API key in .env)
# ---------------------------------------------------------------------------
# To run ONLY this test:
#   python -m pytest tests/test_email_generator.py::test_live_generate -v -s
#
# It will be SKIPPED automatically if ANTHROPIC_API_KEY is not set.
# ---------------------------------------------------------------------------

import pytest

@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-test"),
    reason="Skipped: ANTHROPIC_API_KEY not set or is a test key"
)
def test_live_generate():
    """Live test: actually calls Claude API. Requires real API key in .env."""
    from src.email_generator import EmailGenerator
    gen = EmailGenerator()
    result = gen.generate(SAMPLE_CAMPAIGN)

    print("\n--- Live Test Result ---")
    print("Subject:", result.get("subject"))
    print("Body:\n", result.get("body"))
    if "error" in result:
        print("Error:", result["error"])

    assert result["subject"] != "", "Subject should not be empty"
    assert result["body"] != "", "Body should not be empty"
    assert "error" not in result, f"Unexpected error: {result.get('error')}"
