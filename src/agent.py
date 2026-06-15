# agent.py
# Purpose: Orchestrate the full email generation flow.
#          1. Find merchant in Excel
#          2. Generate email (with approved samples as style reference)
#          3. Self-review → regenerate if needed (max 3 attempts)
#          4. Return final email to app.py for display
# TODO: Implement in Step 4

MAX_RETRIES = 3


def run(merchant_name: str) -> dict:
    """
    Main entry point called by app.py.
    Returns {"subject": str, "body": str, "review": dict, "attempts": int}.
    """
    pass
