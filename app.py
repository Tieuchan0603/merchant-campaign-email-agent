# app.py
# Purpose: Streamlit UI for the Merchant Campaign Email Agent.
#
# This file is ONLY responsible for:
#   - Collecting user input (merchant name, optional instruction)
#   - Calling agent.run() and displaying the result
#   - Letting the user edit, regenerate, or approve the email
#   - Saving approved emails to approved_emails/ folder
#
# Business logic lives entirely in src/agent.py.
# Run this app with:  streamlit run app.py

import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

# Make sure Python can find the src/ package
sys.path.insert(0, str(Path(__file__).parent))
from src.agent import EmailAgent

# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Campaign Email Agent",
    page_icon="EMAIL",
    layout="wide",
)

APPROVED_EMAILS_DIR = Path(__file__).parent / "approved_emails"
APPROVED_EMAILS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
# st.session_state persists values across Streamlit reruns (button clicks).
# Without it, every click would reset all variables.

def _init_state():
    defaults = {
        "result":          None,   # latest agent.run() output
        "approved_msg":    "",     # success message shown after Approve
        "last_merchant":   "",     # tracks which merchant the result belongs to
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

_init_state()

# ---------------------------------------------------------------------------
# Helper: save approved email to file
# ---------------------------------------------------------------------------

def save_approved_email(merchant: str, subject: str, body: str) -> Path:
    """
    Save the approved email to approved_emails/ with a timestamp filename.

    Filename format: {merchant}_{YYYYMMDD_HHMMSS}.txt
    File content: plain text with clear Subject / Body sections,
                  readable both by humans and by the file-based retrieval in agent.py.

    Args:
        merchant: Merchant name, e.g. "KFC".
        subject:  Approved email subject.
        body:     Approved email body.

    Returns:
        Path: The file that was created.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize merchant name for use in a filename (replace spaces with underscores)
    safe_merchant = merchant.strip().lower().replace(" ", "_")
    filename = f"{safe_merchant}_{timestamp}.txt"
    filepath = APPROVED_EMAILS_DIR / filename

    content = f"Subject: {subject}\n\n---\n\n{body}"
    filepath.write_text(content, encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# Helper: render the generation history timeline
# ---------------------------------------------------------------------------

def render_history(history: list):
    """Display the generation history as a visual timeline."""
    if not history:
        return

    st.markdown("**Generation History**")
    for entry in history:
        score = entry.get("score", 0)
        attempt = entry.get("attempt", "?")
        reason = entry.get("reason", "")
        passed = score >= 4

        icon = "OK" if passed else "X"
        color = "green" if passed else "red"
        label = f"Attempt {attempt}  {score}/5 [{icon}]  {reason}"
        st.markdown(
            f"<div style='padding:6px 12px; margin:4px 0; border-left: 4px solid {color};"
            f" background:#f8f8f8; border-radius:4px; font-family:monospace'>{label}</div>",
            unsafe_allow_html=True,
        )

    if len(history) > 1:
        st.caption(f"Total attempts: {len(history)}")


# ---------------------------------------------------------------------------
# Helper: render the review quality panel
# ---------------------------------------------------------------------------

def render_review(review: dict):
    """Display score, strengths, weaknesses, and suggestions."""
    score = review.get("score", 0)
    passed = review.get("passed", False)
    strengths = review.get("strengths", [])
    weaknesses = review.get("weaknesses", [])
    suggestions = review.get("improvement_suggestions", [])

    # Score metric
    col_score, col_status = st.columns([1, 3])
    with col_score:
        st.metric("Review Score", f"{score} / 5")
    with col_status:
        if passed:
            st.success("Passed quality review")
        else:
            st.warning(f"Below threshold — {5 - score} criteria need improvement")

    # Strengths
    if strengths:
        with st.expander(f"Strengths ({len(strengths)})", expanded=passed):
            for s in strengths:
                st.markdown(f"- {s}")

    # Weaknesses + suggestions
    if weaknesses:
        with st.expander(f"Weaknesses ({len(weaknesses)})", expanded=not passed):
            for w in weaknesses:
                st.markdown(f"- {w}")

    if suggestions:
        with st.expander("Improvement suggestions", expanded=False):
            for s in suggestions:
                st.markdown(f"- {s}")


# ---------------------------------------------------------------------------
# Main UI layout
# ---------------------------------------------------------------------------

st.title("Merchant Campaign Email Agent")
st.caption("Enter a merchant name to generate a professional campaign collaboration email.")

st.divider()

# ── Input section ─────────────────────────────────────────────────────────

col_input, col_instruction = st.columns([2, 3])
with col_input:
    merchant_name = st.text_input(
        "Merchant Name",
        placeholder="e.g. KFC",
        help="Must match a name in data/campaign.xlsx (case-insensitive)",
    )
with col_instruction:
    user_instruction = st.text_input(
        "Optional instruction",
        placeholder="e.g. Write concisely, focus on the discount offer",
        help="A style or tone instruction passed directly to the AI",
    )

col_gen, col_regen, _ = st.columns([1, 1, 4])
with col_gen:
    generate_clicked = st.button("Generate", type="primary", use_container_width=True)
with col_regen:
    # Only show Regenerate once we have a result
    regen_clicked = (
        st.button("Regenerate", use_container_width=True)
        if st.session_state.result
        else False
    )

# ── Agent execution ────────────────────────────────────────────────────────

should_run = generate_clicked or regen_clicked

if should_run:
    if not merchant_name.strip():
        st.error("Please enter a merchant name.")
    else:
        with st.spinner(f"Generating email for {merchant_name}... (this may take 10-20 seconds)"):
            try:
                agent = EmailAgent()
                result = agent.run(merchant_name.strip(), user_instruction.strip())
                st.session_state.result = result
                st.session_state.approved_msg = ""
                st.session_state.last_merchant = merchant_name.strip()
                # Pre-populate the editable fields with the new email
                st.session_state["edit_subject"] = result.get("subject", "")
                st.session_state["edit_body"] = result.get("body", "")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

# ── Results section ────────────────────────────────────────────────────────

if st.session_state.result:
    result = st.session_state.result
    st.divider()

    # Error from agent
    if "error" in result:
        st.error(result["error"])

    else:
        merchant = result.get("merchant", "")
        campaign = result.get("campaign", "")
        samples_used = result.get("approved_samples_used", 0)
        approved_files = result.get("approved_files", [])

        # ── Header row
        header_col, meta_col = st.columns([3, 2])
        with header_col:
            st.subheader(f"{merchant} — {campaign}")
        with meta_col:
            if samples_used > 0:
                st.caption(
                    f"Style reference: {samples_used} approved email(s) loaded"
                )
                # Show the actual filenames used as reference
                with st.expander("Files used as style reference", expanded=False):
                    for fname in approved_files:
                        st.markdown(f"- `{fname}`")
            else:
                st.caption(
                    "Style reference: none yet — approve this email to start learning your style."
                )

        # ── Two-column layout: Email (left) | Review (right)
        email_col, review_col = st.columns([3, 2])

        with email_col:
            st.markdown("#### Email Draft")
            st.markdown("*You can edit the subject and body directly before approving.*")

            # Editable subject
            subject = st.text_input(
                "Subject",
                key="edit_subject",
                help="Edit the subject line if needed",
            )

            # Editable body
            body = st.text_area(
                "Body",
                key="edit_body",
                height=320,
                help="Edit the email body if needed",
            )

            # ── Action buttons
            st.markdown("")
            approve_col, _ = st.columns([1, 2])
            with approve_col:
                approve_clicked = st.button(
                    "Approve & Save",
                    type="primary",
                    use_container_width=True,
                )

            if approve_clicked:
                final_subject = st.session_state.get("edit_subject", "").strip()
                final_body = st.session_state.get("edit_body", "").strip()

                if not final_subject or not final_body:
                    st.error("Subject and body cannot be empty before approving.")
                else:
                    saved_path = save_approved_email(merchant, final_subject, final_body)
                    st.session_state.approved_msg = (
                        f"Saved to: approved_emails/{saved_path.name}"
                    )
                    st.rerun()

            # Show success message (persists across reruns via session_state)
            if st.session_state.approved_msg:
                st.success(st.session_state.approved_msg)
                st.caption(
                    "This email will be used as a style reference for future emails to the same merchant."
                )

        with review_col:
            st.markdown("#### Quality Review")
            render_review(result.get("review", {}))

            st.markdown("")
            st.markdown("#### Generation History")
            render_history(result.get("generation_history", []))
