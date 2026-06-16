# self_reviewer.py
# Purpose: Ask Claude to review a generated email and return structured feedback.
#          Optionally, auto-fix the email based on the review.
#
# Responsibilities:
#   1. Load the review prompt from prompts/self_review.txt
#   2. Accept an email (subject + body) and call Claude to evaluate it
#   3. Parse Claude's JSON response into a structured Python dict
#   4. Return safe fallback if parsing fails (never crash the agent loop)
#   5. Provide auto_fix_email() to generate an improved version
#
# Does NOT:
#   - Generate the original email (that is email_generator.py)
#   - Orchestrate retry loops (that is agent.py)
#   - Handle the UI (that is app.py)

import os
import json
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
REVIEW_PROMPT_FILE = PROJECT_ROOT / "prompts" / "self_review.txt"

# LLM config — defaults target the GreenNode MaaS Anthropic-compatible endpoint.
# Swap models by setting LLM_MODEL in .env (e.g. qwen/qwen3-5-27b, google/gemma-4-31b-it).
DEFAULT_MODEL = os.getenv("LLM_MODEL", "minimax/minimax-m2.5")
DEFAULT_MAX_TOKENS = 1024
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://maas-llm-aiplatform-hcm.api.vngcloud.vn")

# An email passes review if its score meets this threshold (out of 5).
PASS_THRESHOLD = 4


class EmailReviewer:
    """
    Reviews a campaign email using Claude and returns structured feedback.

    Usage:
        reviewer = EmailReviewer()

        # Review an email
        result = reviewer.review(
            subject="De xuat trien khai CTKM World Cup 2026",
            body="Kinh gui Anh/Chi KFC...",
        )
        print(result["score"])    # e.g. 4
        print(result["passed"])   # True or False

        # Auto-fix if needed
        if not result["passed"]:
            fixed = reviewer.auto_fix_email(
                subject=result_subject,
                body=result_body,
                review=result,
            )
            print(fixed["subject"])
            print(fixed["body"])
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Initialize the reviewer and load the review prompt template.

        Args:
            model: LLM model name. Defaults to LLM_MODEL env (minimax/minimax-m2.5 on MaaS).

        Raises:
            EnvironmentError: If neither LLM_API_KEY nor ANTHROPIC_API_KEY is set.
            FileNotFoundError: If prompts/self_review.txt is missing.
        """
        # Prefer the GreenNode MaaS key (Bearer auth against the MaaS endpoint).
        # Fall back to a standard Anthropic API key for local development.
        llm_key = os.getenv("LLM_API_KEY")
        if llm_key:
            self.client = anthropic.Anthropic(base_url=LLM_BASE_URL, auth_token=llm_key)
        else:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise EnvironmentError(
                    "No LLM credentials found.\n"
                    "Set LLM_API_KEY (GreenNode MaaS) or ANTHROPIC_API_KEY in .env."
                )
            self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.review_prompt_template = self._load_prompt(REVIEW_PROMPT_FILE)

    # -----------------------------------------------------------------------
    # Public methods
    # -----------------------------------------------------------------------

    def review(self, subject: str, body: str) -> dict:
        """
        Ask Claude to evaluate an email against 5 quality criteria.

        Args:
            subject: The email subject line.
            body: The full email body text.

        Returns:
            dict:
                "score"                   (int)        - 0 to 5
                "passed"                  (bool)       - True if score >= 4
                "strengths"               (list[str])  - what the email does well
                "weaknesses"              (list[str])  - what is missing or weak
                "improvement_suggestions" (list[str])  - concrete fixes to apply
                "raw_response"            (str)        - exact Claude output
                "error"                   (str)        - only if parsing failed
        """
        prompt = self._build_review_prompt(subject, body)
        raw_response = self._call_claude(prompt)
        return self._parse_review_response(raw_response)

    def auto_fix_email(self, subject: str, body: str, review: dict) -> dict:
        """
        Generate an improved version of the email based on review feedback.

        This is a helper that should be called when review()["passed"] is False.
        It passes the original email AND the reviewer's feedback to Claude,
        asking it to produce a better version.

        Args:
            subject: Original email subject.
            body: Original email body.
            review: The dict returned by review() — used to extract weaknesses
                    and improvement_suggestions as context for Claude.

        Returns:
            dict:
                "subject"      (str) - improved subject line
                "body"         (str) - improved email body
                "raw_response" (str) - exact Claude output
                "error"        (str) - only if JSON parsing failed
        """
        weaknesses = review.get("weaknesses", [])
        suggestions = review.get("improvement_suggestions", [])

        # Build a clear improvement prompt inline (no separate file needed).
        weaknesses_text = "\n".join(f"- {w}" for w in weaknesses) or "None identified."
        suggestions_text = "\n".join(f"- {s}" for s in suggestions) or "No suggestions."

        prompt = f"""You are a professional email writer at Zalopay.

Below is a campaign email that did not pass quality review. Your task is to fix it.

## Original Email
SUBJECT: {subject}

BODY:
{body}

## Review Feedback
Weaknesses identified:
{weaknesses_text}

Improvement suggestions:
{suggestions_text}

## Task
Rewrite the email to address all weaknesses and apply all suggestions.
Keep the core campaign information unchanged. Only improve structure, tone, and completeness.

## IMPORTANT — Output Format
Return ONLY a valid JSON object. No markdown, no text outside the JSON.

{{
  "subject": "<improved subject line>",
  "body": "<improved full email body>"
}}"""

        raw_response = self._call_claude(prompt)
        return self._parse_email_response(raw_response)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _load_prompt(self, filepath: Path) -> str:
        """Read a prompt template file and return its content."""
        if not filepath.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {filepath}"
            )
        return filepath.read_text(encoding="utf-8")

    def _build_review_prompt(self, subject: str, body: str) -> str:
        """
        Fill {subject} and {body} placeholders in the review prompt template.

        Uses str.replace() (not str.format()) because the template contains
        literal JSON braces that would break str.format().
        """
        prompt = self.review_prompt_template
        prompt = prompt.replace("{subject}", subject)
        prompt = prompt.replace("{body}", body)
        return prompt

    def _call_claude(self, prompt: str) -> str:
        """Send a prompt to Claude and return the raw text response."""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=(
                "You are a precise, structured evaluator. "
                "You always respond with valid JSON only. "
                "Never include markdown fences or any text outside the JSON object."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        text_block = next((b for b in message.content if hasattr(b, "text")), None)
        if text_block is None:
            raise ValueError("No text block in model response.")
        return text_block.text

    def _clean_json(self, raw: str) -> str:
        """
        Strip markdown code fences if Claude added them despite instructions.
        Returns a clean string ready for json.loads().
        """
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1]
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()
        return cleaned

    def _parse_review_response(self, raw_response: str) -> dict:
        """
        Parse Claude's review JSON into a structured dict.

        Always returns a valid dict — never raises an exception.
        If parsing fails, returns a safe fallback so agent.py can continue.

        Args:
            raw_response: Raw text from Claude.

        Returns:
            dict with score, passed, strengths, weaknesses,
            improvement_suggestions, raw_response, and optionally error.
        """
        try:
            data = json.loads(self._clean_json(raw_response))

            score = int(data.get("score", 0))
            # Defensive: clamp score to valid range even if Claude returns a bad value.
            score = max(0, min(5, score))

            return {
                "score": score,
                "passed": score >= PASS_THRESHOLD,
                "strengths": data.get("strengths", []),
                "weaknesses": data.get("weaknesses", []),
                "improvement_suggestions": data.get("improvement_suggestions", []),
                "raw_response": raw_response,
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            # Return a safe fallback — the agent loop must not crash here.
            return self._fallback_response(raw_response, str(e))

    def _parse_email_response(self, raw_response: str) -> dict:
        """
        Parse Claude's auto_fix JSON response (subject + body) into a dict.

        Args:
            raw_response: Raw text from Claude.

        Returns:
            dict with subject, body, raw_response, and optionally error.
        """
        try:
            data = json.loads(self._clean_json(raw_response))
            return {
                "subject": data.get("subject", ""),
                "body": data.get("body", ""),
                "raw_response": raw_response,
            }
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            return {
                "subject": "",
                "body": "",
                "raw_response": raw_response,
                "error": f"auto_fix_email parse error: {e}",
            }

    def _fallback_response(self, raw_response: str, error_msg: str) -> dict:
        """
        Return a safe fallback review dict when Claude's response cannot be parsed.

        Design decision: rather than crashing, we return passed=True with score=0
        and an error note. This lets agent.py log the issue and continue,
        instead of breaking the entire email generation loop.

        Args:
            raw_response: The unparseable text from Claude.
            error_msg: Description of what went wrong.

        Returns:
            dict: A minimal valid review structure.
        """
        return {
            "score": 0,
            "passed": True,       # Allow the agent to proceed rather than loop forever.
            "strengths": [],
            "weaknesses": [],
            "improvement_suggestions": [],
            "raw_response": raw_response,
            "error": (
                f"Review parsing failed: {error_msg}\n"
                "Defaulting to passed=True to avoid infinite retry loop.\n"
                f"Raw Claude response: {raw_response}"
            ),
        }


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

_default_reviewer = None


def _get_reviewer() -> EmailReviewer:
    """Lazy-initialize the shared reviewer instance."""
    global _default_reviewer
    if _default_reviewer is None:
        _default_reviewer = EmailReviewer()
    return _default_reviewer


def review_email(subject: str, body: str) -> dict:
    """Shortcut for EmailReviewer().review(subject, body)."""
    return _get_reviewer().review(subject, body)


def auto_fix_email(subject: str, body: str, review: dict) -> dict:
    """Shortcut for EmailReviewer().auto_fix_email(subject, body, review)."""
    return _get_reviewer().auto_fix_email(subject, body, review)
