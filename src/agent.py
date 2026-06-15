# agent.py
# Purpose: Orchestrate the full email generation workflow.
#
# This is the "brain" that coordinates all other modules:
#   data_reader    → find merchant in Excel
#   email_generator → generate email draft (with approved samples as context)
#   self_reviewer  → review quality, auto-fix if needed
#
# Workflow per run():
#   1. Find merchant in campaign.xlsx
#   2. Load approved email samples from approved_emails/ (file-based retrieval)
#   3. Generate email via Claude
#   4. Review email via Claude
#   5. If score < threshold → auto_fix → review again (max MAX_RETRIES times)
#   6. Return one clean structured dict including generation_history
#
# Does NOT:
#   - Handle HTTP requests or UI (that is app.py)
#   - Know about Streamlit or any frontend framework

import os
from pathlib import Path

from src.data_reader import CampaignDataReader
from src.email_generator import EmailGenerator
from src.self_reviewer import EmailReviewer

PROJECT_ROOT = Path(__file__).parent.parent
APPROVED_EMAILS_DIR = PROJECT_ROOT / "approved_emails"

# Total attempts = 1 initial generation + MAX_RETRIES auto-fix rounds
MAX_RETRIES = 2


class EmailAgent:
    """
    Orchestrates the full email generation pipeline.

    Accepts optional injected dependencies so tests can mock them:
        agent = EmailAgent(reader=mock_reader, generator=mock_gen, reviewer=mock_rev)

    In production (no args passed), it creates real instances automatically:
        agent = EmailAgent()
        result = agent.run("KFC")

    Returned dict structure:
        {
            "merchant":              str,
            "campaign":              str,
            "subject":               str,
            "body":                  str,
            "review":                dict,   # last review result
            "attempts":              int,    # how many rounds were needed
            "approved_samples_used": int,    # how many approved files were loaded
            "generation_history":    list,   # one entry per attempt
            "error":                 str,    # only present if something went wrong
        }

    generation_history entry:
        {
            "attempt": int,
            "score":   int,
            "reason":  str,   # "Accepted" or first weakness found
        }
    """

    def __init__(
        self,
        reader: CampaignDataReader = None,
        generator: EmailGenerator = None,
        reviewer: EmailReviewer = None,
    ):
        """
        Initialize the agent, creating real module instances if not provided.

        Using dependency injection (passing mocks during tests) keeps the agent
        fully testable without making real API calls or reading real files.

        Args:
            reader:    CampaignDataReader instance (or mock).
            generator: EmailGenerator instance (or mock).
            reviewer:  EmailReviewer instance (or mock).
        """
        # Lazy real instantiation — only creates objects if not injected.
        # This avoids loading API keys or files during import time.
        self.reader = reader or CampaignDataReader()
        self.generator = generator or EmailGenerator()
        self.reviewer = reviewer or EmailReviewer()

    # -----------------------------------------------------------------------
    # Public method
    # -----------------------------------------------------------------------

    def run(self, merchant_name: str, user_instruction: str = "") -> dict:
        """
        Execute the full email generation pipeline for a given merchant.

        Args:
            merchant_name:    Name to search in campaign.xlsx, e.g. "KFC".
            user_instruction: Optional style instruction from the user,
                              e.g. "Viet ngan gon, khong qua 150 tu".

        Returns:
            dict — see class docstring for full structure.
            On error (merchant not found, API failure), returns a dict with "error" key.
        """
        # ------------------------------------------------------------------
        # Step 1: Find merchant
        # ------------------------------------------------------------------
        campaign_data = self.reader.find_merchant(merchant_name)
        if not campaign_data:
            return self._error_result(
                merchant_name,
                f"Merchant '{merchant_name}' not found in campaign.xlsx. "
                "Please check the name and try again.",
            )

        # ------------------------------------------------------------------
        # Step 2: Load approved email samples for style reference
        # ------------------------------------------------------------------
        approved_samples, samples_count, approved_files = self._load_approved_samples(merchant_name)

        # ------------------------------------------------------------------
        # Step 3: Initial email generation
        # ------------------------------------------------------------------
        try:
            email = self.generator.generate(
                campaign_data=campaign_data,
                approved_samples=approved_samples,
                user_instruction=user_instruction,
            )
        except Exception as e:
            return self._error_result(merchant_name, f"Email generation failed: {e}")

        # If generation itself returned an error (bad JSON from Claude), treat
        # the email as empty so the retry loop can still attempt a fix.
        if "error" in email and not email["subject"]:
            email = {"subject": "", "body": "", "raw_response": email.get("raw_response", "")}

        # ------------------------------------------------------------------
        # Step 4: Initial review
        # ------------------------------------------------------------------
        generation_history = []
        attempts = 1

        review = self._safe_review(email["subject"], email["body"])
        generation_history.append(
            self._history_entry(attempt=1, review=review)
        )

        # ------------------------------------------------------------------
        # Step 5: Retry loop — auto-fix up to MAX_RETRIES times
        # ------------------------------------------------------------------
        retry = 0
        while not review["passed"] and retry < MAX_RETRIES:
            retry += 1
            attempts += 1

            # Auto-fix: ask Claude to rewrite the email based on feedback
            fixed = self._safe_auto_fix(email["subject"], email["body"], review)

            # Only replace the email if the fix returned valid content.
            # If auto_fix failed (empty subject/body), keep the previous version
            # rather than replacing with an empty email.
            if fixed.get("subject") and fixed.get("body"):
                email = fixed

            # Review the (possibly fixed) email
            review = self._safe_review(email["subject"], email["body"])
            generation_history.append(
                self._history_entry(attempt=attempts, review=review)
            )

        # ------------------------------------------------------------------
        # Step 6: Return structured result
        # ------------------------------------------------------------------
        return {
            "merchant":              campaign_data.get("Merchant", merchant_name),
            "campaign":              campaign_data.get("Campaign Name", ""),
            "subject":               email.get("subject", ""),
            "body":                  email.get("body", ""),
            "review":                review,
            "attempts":              attempts,
            "approved_samples_used": samples_count,
            "approved_files":        approved_files,
            "generation_history":    generation_history,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _load_approved_samples(
        self, merchant_name: str, max_files: int = 3
    ) -> tuple[str, int, list[str]]:
        """
        Scan approved_emails/ and return the most recent approved emails for
        this merchant as a single concatenated style-reference string.

        Matching strategy: a file is included if the merchant name appears
        (case-insensitive) anywhere in the filename.
        Example: "kfc_20260615_120000.txt" → matches for "KFC".

        Recency: files are sorted by last-modified time, newest first.
        Only the most recent `max_files` (default 3) are used so the prompt
        stays concise and we don't include very old, possibly stale styles.

        This is the file-based retrieval (RAG-lite) for MVP.
        In a future version this can be swapped for a vector store without
        changing any other module.

        Args:
            merchant_name: The merchant to search for.
            max_files:     Maximum number of files to load (default 3).

        Returns:
            Tuple of:
                str       — concatenated content of the selected files.
                int       — number of files actually loaded.
                list[str] — filenames that were loaded (for UI display).
        """
        if not APPROVED_EMAILS_DIR.exists():
            return "", 0, []

        name_lower = merchant_name.strip().lower()

        # Find all .txt files whose filename contains the merchant name.
        matching_files = [
            f for f in APPROVED_EMAILS_DIR.iterdir()
            if f.suffix == ".txt" and name_lower in f.name.lower()
        ]

        if not matching_files:
            return "", 0, []

        # Sort by modification time, newest first, then take the top `max_files`.
        matching_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        selected_files = matching_files[:max_files]

        # Read each file and build the combined context string.
        samples = []
        loaded_names = []
        for file in selected_files:
            try:
                content = file.read_text(encoding="utf-8").strip()
                if content:
                    samples.append(f"=== {file.name} ===\n{content}")
                    loaded_names.append(file.name)
            except OSError:
                # Skip unreadable files rather than crashing.
                continue

        combined = "\n\n---\n\n".join(samples)
        return combined, len(samples), loaded_names

    def _safe_review(self, subject: str, body: str) -> dict:
        """
        Call the reviewer and catch any unexpected exceptions.

        The reviewer already has its own fallback for JSON parse errors,
        but we wrap it again here to protect the agent loop from any
        unforeseen runtime errors.

        Returns a valid review dict — never raises.
        """
        try:
            return self.reviewer.review(subject, body)
        except Exception as e:
            # Worst-case fallback: mark as passed to avoid infinite loop.
            return {
                "score": 0,
                "passed": True,
                "strengths": [],
                "weaknesses": [],
                "improvement_suggestions": [],
                "raw_response": "",
                "error": f"Reviewer raised an exception: {e}",
            }

    def _safe_auto_fix(self, subject: str, body: str, review: dict) -> dict:
        """
        Call auto_fix_email and catch any unexpected exceptions.

        Returns the fixed email dict, or an empty dict on failure.
        The caller should check for non-empty subject/body before accepting the result.
        """
        try:
            return self.reviewer.auto_fix_email(subject, body, review)
        except Exception as e:
            return {"subject": "", "body": "", "error": f"auto_fix raised an exception: {e}"}

    def _history_entry(self, attempt: int, review: dict) -> dict:
        """
        Build one entry for generation_history from a review result.

        The "reason" is a short human-readable explanation:
        - "Accepted (5/5)" if the email passed
        - First weakness if it failed, e.g. "Missing professional closing"

        Args:
            attempt: The attempt number (1-based).
            review:  The review dict from EmailReviewer.review().

        Returns:
            dict: {"attempt": int, "score": int, "reason": str}
        """
        score = review.get("score", 0)
        passed = review.get("passed", False)

        if passed:
            reason = f"Accepted ({score}/5)"
        else:
            weaknesses = review.get("weaknesses", [])
            if weaknesses:
                # Use the first weakness as a short summary.
                reason = weaknesses[0]
                # Truncate long reasons for clean display in the UI.
                if len(reason) > 80:
                    reason = reason[:77] + "..."
            else:
                reason = f"Score below threshold ({score}/5)"

        return {
            "attempt": attempt,
            "score":   score,
            "reason":  reason,
        }

    def _error_result(self, merchant_name: str, error_message: str) -> dict:
        """
        Build a standardised error result dict.

        Returning a consistent structure (instead of raising an exception)
        means app.py can always do result["error"] without needing try/except.

        Args:
            merchant_name: The merchant that was requested.
            error_message: Human-readable description of what went wrong.

        Returns:
            dict with all standard keys set to safe defaults plus "error".
        """
        return {
            "merchant":              merchant_name,
            "campaign":              "",
            "subject":               "",
            "body":                  "",
            "review":                {},
            "attempts":              0,
            "approved_samples_used": 0,
            "approved_files":        [],
            "generation_history":    [],
            "error":                 error_message,
        }
