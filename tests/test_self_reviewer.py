# test_self_reviewer.py
# Purpose: Unit tests for src/self_reviewer.py
#
# All tests mock the Claude API — no real API calls, no cost, runs instantly.
# For live end-to-end tests, see test_live_review() at the bottom.
#
# Run all offline tests:
#   python -m pytest tests/test_self_reviewer.py -v
#
# Run only the live test (requires real API key in .env):
#   python -m pytest tests/test_self_reviewer.py::test_live_review -v -s

import json
import os
import sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
from src.self_reviewer import EmailReviewer, PASS_THRESHOLD


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

GOOD_EMAIL_SUBJECT = "De xuat hop tac CTKM World Cup 2026 cung Zalopay"
GOOD_EMAIL_BODY = (
    "Kinh gui Anh/Chi KFC,\n\n"
    "Zalopay tran trong de xuat chuong trinh: Giam 20k cho don 99k.\n"
    "Thoi gian: 1/7 - 31/7/2026.\n"
    "Vui long xac nhan truoc ngay 20/6 de chung toi trien khai dung han.\n\n"
    "Tran trong,\nDoi ngu Zalopay"
)

WEAK_EMAIL_SUBJECT = "Hello"
WEAK_EMAIL_BODY = "KFC co muon chay khuyen mai khong?"

VALID_REVIEW_RESPONSE = json.dumps({
    "score": 5,
    "passed": True,
    "strengths": [
        "Has a warm, professional greeting",
        "Timeline (1/7 - 31/7) is clearly stated",
        "CTA with deadline (truoc 20/6) is specific and actionable",
        "Professional closing with team signature",
        "Tone is respectful and appropriate for B2B",
    ],
    "weaknesses": [],
    "improvement_suggestions": [],
})

FAILING_REVIEW_RESPONSE = json.dumps({
    "score": 2,
    "passed": False,
    "strengths": ["Mentions the merchant name"],
    "weaknesses": [
        "Missing proper greeting",
        "No campaign timeline stated",
        "No CTA or deadline",
        "No professional closing",
    ],
    "improvement_suggestions": [
        "Add 'Kinh gui Anh/Chi...' as the opening line",
        "State the promotion period explicitly",
        "Add a confirmation deadline",
        "End with 'Tran trong,' and your team name",
    ],
})

VALID_FIX_RESPONSE = json.dumps({
    "subject": "De xuat hop tac CTKM World Cup 2026 cung Zalopay",
    "body": "Kinh gui Anh/Chi KFC,\n\n[improved body]\n\nTran trong,\nDoi ngu Zalopay",
})


# ---------------------------------------------------------------------------
# Helper: build a mocked EmailReviewer
# ---------------------------------------------------------------------------

def make_reviewer_with_mock(raw_response: str) -> EmailReviewer:
    """
    Create an EmailReviewer with the Claude API replaced by a mock
    that always returns raw_response — no network, no API key needed.
    """
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-fake-key"}):
        reviewer = EmailReviewer.__new__(EmailReviewer)
        reviewer.model = "claude-sonnet-4-6"
        reviewer.review_prompt_template = reviewer._load_prompt(
            __import__("pathlib").Path(__file__).parent.parent
            / "prompts" / "self_review.txt"
        )

        fake_block = MagicMock()
        fake_block.text = raw_response
        fake_message = MagicMock()
        fake_message.content = [fake_block]

        reviewer.client = MagicMock()
        reviewer.client.messages.create.return_value = fake_message
    return reviewer


# ---------------------------------------------------------------------------
# Tests: review() — happy path
# ---------------------------------------------------------------------------

def test_review_returns_score():
    """review() should return an integer score."""
    reviewer = make_reviewer_with_mock(VALID_REVIEW_RESPONSE)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert isinstance(result["score"], int)
    assert result["score"] == 5


def test_review_passed_true_when_score_high():
    """passed should be True when score >= PASS_THRESHOLD."""
    reviewer = make_reviewer_with_mock(VALID_REVIEW_RESPONSE)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert result["passed"] is True


def test_review_passed_false_when_score_low():
    """passed should be False when score < PASS_THRESHOLD."""
    reviewer = make_reviewer_with_mock(FAILING_REVIEW_RESPONSE)
    result = reviewer.review(WEAK_EMAIL_SUBJECT, WEAK_EMAIL_BODY)
    assert result["passed"] is False
    assert result["score"] == 2


def test_review_returns_strengths_list():
    """strengths should be a non-empty list for a good email."""
    reviewer = make_reviewer_with_mock(VALID_REVIEW_RESPONSE)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert isinstance(result["strengths"], list)
    assert len(result["strengths"]) > 0


def test_review_returns_weaknesses_list():
    """weaknesses should be a list (empty is valid for perfect emails)."""
    reviewer = make_reviewer_with_mock(VALID_REVIEW_RESPONSE)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert isinstance(result["weaknesses"], list)


def test_review_returns_improvement_suggestions():
    """improvement_suggestions should be a list and populated for failing emails."""
    reviewer = make_reviewer_with_mock(FAILING_REVIEW_RESPONSE)
    result = reviewer.review(WEAK_EMAIL_SUBJECT, WEAK_EMAIL_BODY)
    assert isinstance(result["improvement_suggestions"], list)
    assert len(result["improvement_suggestions"]) > 0


def test_review_always_includes_raw_response():
    """raw_response must always be present for debugging."""
    reviewer = make_reviewer_with_mock(VALID_REVIEW_RESPONSE)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert "raw_response" in result
    assert result["raw_response"] == VALID_REVIEW_RESPONSE


# ---------------------------------------------------------------------------
# Tests: review() — edge cases and error handling
# ---------------------------------------------------------------------------

def test_review_handles_code_fence_response():
    """Should correctly parse JSON even if Claude wraps it in code fences."""
    fenced = f"```json\n{VALID_REVIEW_RESPONSE}\n```"
    reviewer = make_reviewer_with_mock(fenced)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert result["score"] == 5
    assert "error" not in result


def test_review_fallback_on_invalid_json():
    """When Claude returns non-JSON, should return safe fallback (not crash)."""
    reviewer = make_reviewer_with_mock("Xin loi, toi khong the danh gia email nay.")
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)

    # Must not raise; must return a valid dict
    assert isinstance(result, dict)
    assert "score" in result
    assert "passed" in result
    assert "error" in result


def test_review_fallback_sets_passed_true():
    """Fallback should default to passed=True to avoid infinite retry loop."""
    reviewer = make_reviewer_with_mock("invalid json response")
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert result["passed"] is True


def test_review_clamps_score_to_valid_range():
    """Score should be clamped to 0-5 even if Claude returns an out-of-range value."""
    bad_score_response = json.dumps({
        "score": 99,      # out of range — should be clamped to 5
        "passed": True,
        "strengths": [],
        "weaknesses": [],
        "improvement_suggestions": [],
    })
    reviewer = make_reviewer_with_mock(bad_score_response)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert result["score"] <= 5


def test_review_score_minimum_is_zero():
    """Score should never go below 0."""
    bad_score_response = json.dumps({
        "score": -3,
        "passed": False,
        "strengths": [],
        "weaknesses": [],
        "improvement_suggestions": [],
    })
    reviewer = make_reviewer_with_mock(bad_score_response)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert result["score"] >= 0


def test_review_missing_fields_default_to_empty():
    """Partial JSON from Claude should not crash — missing lists default to []."""
    partial_response = json.dumps({"score": 3, "passed": False})
    reviewer = make_reviewer_with_mock(partial_response)
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)
    assert result["strengths"] == []
    assert result["weaknesses"] == []
    assert result["improvement_suggestions"] == []


# ---------------------------------------------------------------------------
# Tests: auto_fix_email()
# ---------------------------------------------------------------------------

SAMPLE_REVIEW = {
    "score": 2,
    "passed": False,
    "strengths": ["Mentions KFC"],
    "weaknesses": ["No greeting", "No timeline", "No closing"],
    "improvement_suggestions": [
        "Add 'Kinh gui Anh/Chi...'",
        "State the promotion dates",
        "End with 'Tran trong,'",
    ],
}


def test_auto_fix_returns_subject():
    """auto_fix_email() should return a non-empty subject."""
    reviewer = make_reviewer_with_mock(VALID_FIX_RESPONSE)
    result = reviewer.auto_fix_email(WEAK_EMAIL_SUBJECT, WEAK_EMAIL_BODY, SAMPLE_REVIEW)
    assert "subject" in result
    assert result["subject"] != ""


def test_auto_fix_returns_body():
    """auto_fix_email() should return a non-empty body."""
    reviewer = make_reviewer_with_mock(VALID_FIX_RESPONSE)
    result = reviewer.auto_fix_email(WEAK_EMAIL_SUBJECT, WEAK_EMAIL_BODY, SAMPLE_REVIEW)
    assert "body" in result
    assert result["body"] != ""


def test_auto_fix_returns_raw_response():
    """raw_response should always be present in the result."""
    reviewer = make_reviewer_with_mock(VALID_FIX_RESPONSE)
    result = reviewer.auto_fix_email(WEAK_EMAIL_SUBJECT, WEAK_EMAIL_BODY, SAMPLE_REVIEW)
    assert "raw_response" in result


def test_auto_fix_handles_parse_error_gracefully():
    """auto_fix_email() should return error dict (not crash) on bad Claude response."""
    reviewer = make_reviewer_with_mock("Not valid JSON at all.")
    result = reviewer.auto_fix_email(WEAK_EMAIL_SUBJECT, WEAK_EMAIL_BODY, SAMPLE_REVIEW)
    assert "error" in result
    assert result["subject"] == ""
    assert result["body"] == ""


def test_auto_fix_accepts_empty_review_fields():
    """Should not crash when review has empty weaknesses/suggestions lists."""
    empty_review = {
        "score": 3,
        "passed": False,
        "strengths": [],
        "weaknesses": [],
        "improvement_suggestions": [],
    }
    reviewer = make_reviewer_with_mock(VALID_FIX_RESPONSE)
    result = reviewer.auto_fix_email(WEAK_EMAIL_SUBJECT, WEAK_EMAIL_BODY, empty_review)
    assert result["subject"] != ""


# ---------------------------------------------------------------------------
# Tests: internal helpers
# ---------------------------------------------------------------------------

def test_clean_json_strips_code_fence():
    """_clean_json() should remove ```json ... ``` wrappers."""
    reviewer = make_reviewer_with_mock("{}")
    raw = "```json\n{\"key\": \"value\"}\n```"
    cleaned = reviewer._clean_json(raw)
    data = json.loads(cleaned)
    assert data["key"] == "value"


def test_clean_json_leaves_plain_json_unchanged():
    """_clean_json() should not modify a plain JSON string."""
    reviewer = make_reviewer_with_mock("{}")
    raw = '{"score": 5}'
    assert reviewer._clean_json(raw) == raw


def test_pass_threshold_constant():
    """PASS_THRESHOLD should be 4 — verifying the constant hasn't drifted."""
    assert PASS_THRESHOLD == 4


# ---------------------------------------------------------------------------
# Live test (requires real ANTHROPIC_API_KEY in .env)
# ---------------------------------------------------------------------------
# Run with:  python -m pytest tests/test_self_reviewer.py::test_live_review -v -s

@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY")
    or os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-test"),
    reason="Skipped: ANTHROPIC_API_KEY not set or is a test key",
)
def test_live_review():
    """Live test: actually calls Claude to review a real email."""
    reviewer = EmailReviewer()
    result = reviewer.review(GOOD_EMAIL_SUBJECT, GOOD_EMAIL_BODY)

    print("\n--- Live Review Result ---")
    print(f"Score: {result['score']}/5")
    print(f"Passed: {result['passed']}")
    print(f"Strengths: {result['strengths']}")
    print(f"Weaknesses: {result['weaknesses']}")
    print(f"Suggestions: {result['improvement_suggestions']}")

    assert isinstance(result["score"], int)
    assert isinstance(result["passed"], bool)
    assert isinstance(result["strengths"], list)
    assert isinstance(result["weaknesses"], list)
    assert isinstance(result["improvement_suggestions"], list)
    assert "error" not in result
