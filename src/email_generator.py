# email_generator.py
import os
import json
from datetime import datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent.parent
PROMPT_FILE = PROJECT_ROOT / "prompts" / "email_generation.txt"

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024


class EmailGenerator:
    """
    Generates campaign emails using the Claude API.

    Responsibilities:
    - Load prompt template from prompts/email_generation.txt
    - Fill placeholders with campaign data and style samples
    - Call Claude API and return parsed JSON as a Python dict

    Does NOT:
    - Read approved_emails/ directly (caller passes approved_samples as string)
    - Review or regenerate emails (that is self_reviewer.py + agent.py)
    - Handle the UI (that is app.py)

    Usage:
        gen = EmailGenerator()
        result = gen.generate(
            campaign_data={"Merchant": "KFC", "Campaign Name": "World Cup 2026", ...},
            approved_samples="style reference text",
            user_instruction="Viet ngan gon hon",
        )
        print(result["subject"])
        print(result["body"])
    """

    def __init__(self, model: str = DEFAULT_MODEL):
        """
        Initialize and load the prompt template.

        Args:
            model: Claude model name. Default is claude-sonnet-4-6.

        Raises:
            EnvironmentError: If ANTHROPIC_API_KEY is missing from .env.
            FileNotFoundError: If prompts/email_generation.txt is missing.
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "ANTHROPIC_API_KEY not found.\n"
                "Please copy .env.example to .env and fill in your API key."
            )

        # anthropic.Anthropic() is the client object we use to call Claude.
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

        # Load the prompt template once at startup, not on every generate() call.
        self.prompt_template = self._load_prompt_template()

    # -----------------------------------------------------------------------
    # Public method
    # -----------------------------------------------------------------------

    def generate(
        self,
        campaign_data: dict,
        approved_samples: str = "",
        user_instruction: str = "",
    ) -> dict:
        """
        Generate a campaign email for the given merchant.

        Args:
            campaign_data: Dict of campaign fields (from CampaignDataReader).
                           Expected keys: Merchant, Campaign Name, Timeline,
                           Scheme, Sponsor, Channel, CTA.
            approved_samples: Previously approved emails as style reference.
                              Pass empty string if none exist yet.
            user_instruction: Optional instruction from the user,
                              e.g. "Viet ngan gon hon". Pass "" if none.

        Returns:
            dict:
                "subject"       (str)  - email subject line
                "body"          (str)  - full email body
                "raw_response"  (str)  - exact Claude output (useful for debugging)
                "error"         (str)  - only present if JSON parsing failed
        """
        prompt = self._build_prompt(campaign_data, approved_samples, user_instruction)
        raw_response = self._call_claude(prompt)
        return self._parse_response(raw_response)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _load_prompt_template(self) -> str:
        """Read and return the content of prompts/email_generation.txt."""
        if not PROMPT_FILE.exists():
            raise FileNotFoundError(
                f"Prompt template not found: {PROMPT_FILE}\n"
                "Make sure prompts/email_generation.txt exists."
            )
        return PROMPT_FILE.read_text(encoding="utf-8")

    def _build_prompt(
        self,
        campaign_data: dict,
        approved_samples: str,
        user_instruction: str,
    ) -> str:
        """
        Fill placeholders in the prompt template with actual values.

        Why str.replace() and NOT str.format():
        The prompt template contains a JSON example with literal curly braces
        like {"subject": "..."} which str.format() would wrongly interpret as
        Python placeholders and raise a KeyError.
        str.replace() simply swaps the exact string without any special handling.

        Args:
            campaign_data: Campaign fields dict.
            approved_samples: Style reference text.
            user_instruction: Optional user instruction.

        Returns:
            str: The fully filled-in prompt, ready for Claude.
        """
        today = datetime.now().strftime("%d/%m/%Y")

        samples_text = (
            approved_samples.strip()
            or "Chua co email mau. Hay viet theo phong cach chuyen nghiep cua ZaloPay."
        )
        instruction_text = (
            user_instruction.strip()
            or "Khong co yeu cau dac biet tu nguoi dung."
        )

        replacements = {
            "{merchant}":         campaign_data.get("Merchant", ""),
            "{campaign_name}":    campaign_data.get("Campaign Name", ""),
            "{timeline}":         campaign_data.get("Timeline", ""),
            "{scheme}":           campaign_data.get("Scheme", ""),
            "{sponsor}":          campaign_data.get("Sponsor", ""),
            "{channel}":          campaign_data.get("Channel", ""),
            "{cta}":              campaign_data.get("CTA", ""),
            "{today}":            today,
            "{approved_samples}": samples_text,
            "{user_instruction}": instruction_text,
        }

        prompt = self.prompt_template
        for placeholder, value in replacements.items():
            prompt = prompt.replace(placeholder, str(value))
        return prompt

    def _call_claude(self, prompt: str) -> str:
        """
        Send the prompt to Claude and return the raw text response.

        Args:
            prompt: The complete, filled-in prompt string.

        Returns:
            str: Raw response text from Claude (should be a JSON string).
        """
        message = self.client.messages.create(
            model=self.model,
            max_tokens=DEFAULT_MAX_TOKENS,
            system=(
                "You are a professional email writer. "
                "You always respond with valid JSON only. "
                "Never include markdown fences or text outside the JSON object."
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        # message.content is a list; the first item is the text block.
        return message.content[0].text

    def _parse_response(self, raw_response: str) -> dict:
        """
        Parse Claude's raw text into a structured dict.

        Handles the case where Claude accidentally wraps JSON in code fences.

        Args:
            raw_response: The raw string from Claude.

        Returns:
            dict with subject, body, raw_response, and optionally error.
        """
        cleaned = raw_response.strip()

        # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1]  # content between first fence pair
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            return {
                "subject": data.get("subject", ""),
                "body": data.get("body", ""),
                "raw_response": raw_response,
            }
        except json.JSONDecodeError as e:
            return {
                "subject": "",
                "body": "",
                "raw_response": raw_response,
                "error": (
                    f"Claude did not return valid JSON. Error: {e}\n"
                    f"Raw response: {raw_response}"
                ),
            }


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

_default_generator = None


def generate_email(
    campaign_data: dict,
    approved_samples: str = "",
    user_instruction: str = "",
) -> dict:
    """
    Shortcut for EmailGenerator().generate().

    Creates the generator once and reuses it across calls (lazy init).
    """
    global _default_generator
    if _default_generator is None:
        _default_generator = EmailGenerator()
    return _default_generator.generate(campaign_data, approved_samples, user_instruction)
