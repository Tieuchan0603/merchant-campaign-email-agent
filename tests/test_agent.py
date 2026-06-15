# test_agent.py
# Purpose: Unit tests for src/agent.py (EmailAgent orchestration logic)
#
# Strategy: inject mock reader, generator, and reviewer so NO real API calls
# are made. We test the orchestration logic — retry loops, generation_history,
# error handling — not the individual modules (those have their own test files).
#
# Run all:   python -m pytest tests/test_agent.py -v
# Run live:  python -m pytest tests/test_agent.py::test_live_agent_run -v -s

import os
import sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
from src.agent import EmailAgent, MAX_RETRIES


# ---------------------------------------------------------------------------
# Shared fixtures — reusable mock objects
# ---------------------------------------------------------------------------

SAMPLE_CAMPAIGN = {
    "Merchant": "KFC",
    "Campaign Name": "World Cup 2026",
    "Timeline": "1/7-31/7",
    "Scheme": "Giam 20k cho don 99k",
    "Sponsor": "Zalopay fund 100%",
    "Channel": "ONLINE",
    "CTA": "Confirm truoc 20/6",
}

GOOD_EMAIL = {
    "subject": "De xuat CTKM World Cup 2026 cung ZaloPay",
    "body": "Kinh gui Anh/Chi KFC,\n\nNoi dung...\n\nTran trong,\nZaloPay",
    "raw_response": '{"subject": "...", "body": "..."}',
}

PASSING_REVIEW = {
    "score": 5,
    "passed": True,
    "strengths": ["Good greeting", "Clear timeline"],
    "weaknesses": [],
    "improvement_suggestions": [],
    "raw_response": "{}",
}

FAILING_REVIEW = {
    "score": 2,
    "passed": False,
    "strengths": ["Mentions KFC"],
    "weaknesses": ["Missing greeting", "No timeline stated"],
    "improvement_suggestions": ["Add greeting", "Add dates"],
    "raw_response": "{}",
}

FIXED_EMAIL = {
    "subject": "De xuat CTKM World Cup 2026 cung ZaloPay (fixed)",
    "body": "Kinh gui Anh/Chi KFC,\n\n[Fixed content]\n\nTran trong,\nZaloPay",
    "raw_response": '{"subject": "...", "body": "..."}',
}


# ---------------------------------------------------------------------------
# Helper: build an agent with all three dependencies mocked
# ---------------------------------------------------------------------------

def make_agent(
    merchant_data=SAMPLE_CAMPAIGN,
    email=GOOD_EMAIL,
    review=PASSING_REVIEW,
    fixed_email=FIXED_EMAIL,
    fixed_review=PASSING_REVIEW,
):
    """
    Build an EmailAgent with controllable mock dependencies.

    merchant_data: what reader.find_merchant() returns (None = not found)
    email:         what generator.generate() returns
    review:        what reviewer.review() returns on 1st call
    fixed_email:   what reviewer.auto_fix_email() returns
    fixed_review:  what reviewer.review() returns after auto-fix
    """
    mock_reader = MagicMock()
    mock_reader.find_merchant.return_value = merchant_data

    mock_generator = MagicMock()
    mock_generator.generate.return_value = email

    mock_reviewer = MagicMock()
    # review() called multiple times: first returns `review`, then `fixed_review`
    mock_reviewer.review.side_effect = [review, fixed_review, fixed_review]
    mock_reviewer.auto_fix_email.return_value = fixed_email

    agent = EmailAgent(
        reader=mock_reader,
        generator=mock_generator,
        reviewer=mock_reviewer,
    )
    return agent, mock_reader, mock_generator, mock_reviewer


# ---------------------------------------------------------------------------
# Tests: return structure
# ---------------------------------------------------------------------------

def test_result_has_all_required_keys():
    """run() must always return all standard keys."""
    agent, *_ = make_agent()
    result = agent.run("KFC")
    required_keys = [
        "merchant", "campaign", "subject", "body",
        "review", "attempts", "approved_samples_used",
        "approved_files", "generation_history",
    ]
    for key in required_keys:
        assert key in result, f"Missing key: {key}"


def test_result_merchant_and_campaign_match_data():
    """merchant and campaign in result should match the Excel data."""
    agent, *_ = make_agent()
    result = agent.run("KFC")
    assert result["merchant"] == "KFC"
    assert result["campaign"] == "World Cup 2026"


def test_result_subject_and_body_from_generator():
    """subject and body should come from the email generator."""
    agent, *_ = make_agent()
    result = agent.run("KFC")
    assert result["subject"] == GOOD_EMAIL["subject"]
    assert result["body"] == GOOD_EMAIL["body"]


def test_result_approved_samples_used_is_int():
    """approved_samples_used should be an integer >= 0."""
    agent, *_ = make_agent()
    result = agent.run("KFC")
    assert isinstance(result["approved_samples_used"], int)
    assert result["approved_samples_used"] >= 0


def test_result_approved_files_is_list():
    """approved_files should always be a list (empty if no files loaded)."""
    agent, *_ = make_agent()
    result = agent.run("KFC")
    assert isinstance(result["approved_files"], list)


# ---------------------------------------------------------------------------
# Tests: happy path (email passes on first attempt)
# ---------------------------------------------------------------------------

def test_single_attempt_when_email_passes_immediately():
    """If review passes on attempt 1, attempts should be 1."""
    agent, *_ = make_agent(review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert result["attempts"] == 1


def test_generation_history_has_one_entry_on_first_pass():
    """generation_history should have exactly one entry when passed on attempt 1."""
    agent, *_ = make_agent(review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert len(result["generation_history"]) == 1


def test_history_entry_structure():
    """Each history entry must have attempt, score, and reason keys."""
    agent, *_ = make_agent(review=PASSING_REVIEW)
    result = agent.run("KFC")
    entry = result["generation_history"][0]
    assert "attempt" in entry
    assert "score" in entry
    assert "reason" in entry


def test_passing_history_reason_contains_accepted():
    """Reason in a passing history entry should contain 'Accepted'."""
    agent, *_ = make_agent(review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert "Accepted" in result["generation_history"][0]["reason"]


def test_auto_fix_not_called_when_passes_first_try():
    """auto_fix_email should NOT be called if the first review passes."""
    agent, _, _, mock_reviewer = make_agent(review=PASSING_REVIEW)
    agent.run("KFC")
    mock_reviewer.auto_fix_email.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: retry logic
# ---------------------------------------------------------------------------

def test_attempts_is_2_after_one_retry():
    """When review fails once then passes, attempts should be 2."""
    agent, *_ = make_agent(review=FAILING_REVIEW, fixed_review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert result["attempts"] == 2


def test_generation_history_has_two_entries_after_one_retry():
    """generation_history should have 2 entries after one retry."""
    agent, *_ = make_agent(review=FAILING_REVIEW, fixed_review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert len(result["generation_history"]) == 2


def test_history_first_entry_shows_failure_reason():
    """First history entry should show the weakness as the reason."""
    agent, *_ = make_agent(review=FAILING_REVIEW, fixed_review=PASSING_REVIEW)
    result = agent.run("KFC")
    first_reason = result["generation_history"][0]["reason"]
    # Should contain a weakness, not "Accepted"
    assert "Accepted" not in first_reason


def test_history_second_entry_shows_accepted():
    """Second history entry should show 'Accepted' after the fix."""
    agent, *_ = make_agent(review=FAILING_REVIEW, fixed_review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert "Accepted" in result["generation_history"][1]["reason"]


def test_auto_fix_called_once_after_one_failure():
    """auto_fix_email should be called exactly once when email fails once."""
    agent, _, _, mock_reviewer = make_agent(
        review=FAILING_REVIEW, fixed_review=PASSING_REVIEW
    )
    agent.run("KFC")
    assert mock_reviewer.auto_fix_email.call_count == 1


def test_retry_does_not_exceed_max_retries():
    """Even if review keeps failing, retries must not exceed MAX_RETRIES."""
    mock_reader = MagicMock()
    mock_reader.find_merchant.return_value = SAMPLE_CAMPAIGN

    mock_generator = MagicMock()
    mock_generator.generate.return_value = GOOD_EMAIL

    mock_reviewer = MagicMock()
    # review() always returns failing — should still stop at MAX_RETRIES
    mock_reviewer.review.return_value = FAILING_REVIEW
    mock_reviewer.auto_fix_email.return_value = FIXED_EMAIL

    agent = EmailAgent(reader=mock_reader, generator=mock_generator, reviewer=mock_reviewer)
    result = agent.run("KFC")

    # Total attempts = 1 initial + MAX_RETRIES
    assert result["attempts"] == 1 + MAX_RETRIES
    assert mock_reviewer.auto_fix_email.call_count == MAX_RETRIES


def test_result_body_updated_after_auto_fix():
    """After a successful auto-fix, the body in the result should be the fixed one."""
    agent, *_ = make_agent(review=FAILING_REVIEW, fixed_review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert result["body"] == FIXED_EMAIL["body"]


def test_keeps_original_email_if_auto_fix_returns_empty():
    """If auto_fix returns empty strings, agent should keep the original email."""
    empty_fix = {"subject": "", "body": "", "raw_response": ""}

    mock_reader = MagicMock()
    mock_reader.find_merchant.return_value = SAMPLE_CAMPAIGN

    mock_generator = MagicMock()
    mock_generator.generate.return_value = GOOD_EMAIL

    mock_reviewer = MagicMock()
    mock_reviewer.review.side_effect = [FAILING_REVIEW, PASSING_REVIEW]
    mock_reviewer.auto_fix_email.return_value = empty_fix

    agent = EmailAgent(reader=mock_reader, generator=mock_generator, reviewer=mock_reviewer)
    result = agent.run("KFC")

    # Should keep the original email, not replace with empty strings
    assert result["body"] == GOOD_EMAIL["body"]


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------

def test_merchant_not_found_returns_error():
    """run() should return an error dict (not crash) when merchant is not found."""
    agent, *_ = make_agent(merchant_data=None)
    result = agent.run("UnknownBrand")
    assert "error" in result
    assert result["subject"] == ""
    assert result["attempts"] == 0


def test_error_result_contains_merchant_name():
    """Error result should still include the merchant name for UI display."""
    agent, *_ = make_agent(merchant_data=None)
    result = agent.run("UnknownBrand")
    assert result["merchant"] == "UnknownBrand"


def test_generator_exception_returns_error_dict():
    """If generator raises an exception, return an error dict rather than crashing."""
    mock_reader = MagicMock()
    mock_reader.find_merchant.return_value = SAMPLE_CAMPAIGN

    mock_generator = MagicMock()
    mock_generator.generate.side_effect = Exception("API connection failed")

    mock_reviewer = MagicMock()

    agent = EmailAgent(reader=mock_reader, generator=mock_generator, reviewer=mock_reviewer)
    result = agent.run("KFC")

    assert "error" in result
    assert "API connection failed" in result["error"]


def test_reviewer_exception_does_not_crash_agent():
    """If reviewer raises an exception, _safe_review should absorb it."""
    mock_reader = MagicMock()
    mock_reader.find_merchant.return_value = SAMPLE_CAMPAIGN

    mock_generator = MagicMock()
    mock_generator.generate.return_value = GOOD_EMAIL

    mock_reviewer = MagicMock()
    mock_reviewer.review.side_effect = Exception("Review service down")

    agent = EmailAgent(reader=mock_reader, generator=mock_generator, reviewer=mock_reviewer)
    result = agent.run("KFC")

    # Should not raise; error absorbed and treated as passed=True
    assert "subject" in result
    assert result["attempts"] == 1


def test_generation_history_always_present_on_error():
    """generation_history key must exist even on error result."""
    agent, *_ = make_agent(merchant_data=None)
    result = agent.run("Unknown")
    assert "generation_history" in result


# ---------------------------------------------------------------------------
# Tests: generation_history detail
# ---------------------------------------------------------------------------

def test_history_attempt_numbers_are_sequential():
    """Attempt numbers in history should be 1, 2, 3... in order."""
    mock_reader = MagicMock()
    mock_reader.find_merchant.return_value = SAMPLE_CAMPAIGN
    mock_generator = MagicMock()
    mock_generator.generate.return_value = GOOD_EMAIL
    mock_reviewer = MagicMock()
    mock_reviewer.review.side_effect = [FAILING_REVIEW, FAILING_REVIEW, PASSING_REVIEW]
    mock_reviewer.auto_fix_email.return_value = FIXED_EMAIL

    agent = EmailAgent(reader=mock_reader, generator=mock_generator, reviewer=mock_reviewer)
    result = agent.run("KFC")

    attempts_in_history = [e["attempt"] for e in result["generation_history"]]
    assert attempts_in_history == list(range(1, len(attempts_in_history) + 1))


def test_history_scores_match_review_scores():
    """Scores recorded in history should match what the reviewer returned."""
    agent, *_ = make_agent(review=FAILING_REVIEW, fixed_review=PASSING_REVIEW)
    result = agent.run("KFC")
    assert result["generation_history"][0]["score"] == FAILING_REVIEW["score"]
    assert result["generation_history"][1]["score"] == PASSING_REVIEW["score"]


def test_max_retries_constant_is_2():
    """MAX_RETRIES should be 2 — verifying the constant hasn't drifted."""
    assert MAX_RETRIES == 2


# ---------------------------------------------------------------------------
# Live test (requires real ANTHROPIC_API_KEY in .env)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY")
    or os.getenv("ANTHROPIC_API_KEY", "").startswith("sk-test"),
    reason="Skipped: ANTHROPIC_API_KEY not set or is a test key",
)
def test_live_agent_run():
    """End-to-end live test: real Excel + real Claude API."""
    agent = EmailAgent()
    result = agent.run("KFC")

    print("\n--- Live Agent Result ---")
    print(f"Merchant:  {result['merchant']}")
    print(f"Campaign:  {result['campaign']}")
    print(f"Attempts:  {result['attempts']}")
    print(f"Score:     {result['review'].get('score')}/5")
    print(f"Passed:    {result['review'].get('passed')}")
    print("\nGeneration History:")
    for entry in result["generation_history"]:
        icon = "OK" if entry["score"] >= 4 else "X"
        print(f"  Attempt {entry['attempt']} -> {entry['score']}/5 [{icon}] {entry['reason']}")
    print(f"\nSubject: {result['subject']}")
    print(f"\nBody:\n{result['body']}")

    assert "error" not in result
    assert result["subject"] != ""
    assert result["body"] != ""
    assert result["attempts"] >= 1
    assert len(result["generation_history"]) == result["attempts"]
