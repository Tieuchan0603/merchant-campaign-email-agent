# self_reviewer.py
# Purpose: Ask Claude to review a generated email against 5 quality criteria.
#          If the email fails, the agent will regenerate (max 3 attempts).
# TODO: Implement in Step 4

# Review criteria:
# 1. Has greeting (lời chào)
# 2. Has timeline (thời gian chương trình)
# 3. Has CTA (call-to-action)
# 4. Has closing (phần kết)
# 5. Professional tone (văn phong chuyên nghiệp)

def review_email(subject: str, body: str) -> dict:
    """
    Call Claude API to review the email.
    Returns {"passed": bool, "score": int, "feedback": str}.
    """
    pass
