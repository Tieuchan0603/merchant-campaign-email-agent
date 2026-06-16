import os
from pathlib import Path

from dotenv import load_dotenv
from greennode_agentbase import GreenNodeAgentBaseApp, PingStatus, RequestContext

from src.agent import EmailAgent

load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=False)

app = GreenNodeAgentBaseApp()


@app.entrypoint
def handler(payload: dict, context: RequestContext) -> dict:
    """Main agent entrypoint for POST /invocations.

    Expected payload:
        {
            "merchant_name": "KFC",
            "user_instruction": "Optional instruction text"
        }
    """
    merchant_name = payload.get("merchant_name") or payload.get("merchant")
    if not merchant_name or not isinstance(merchant_name, str) or not merchant_name.strip():
        return {
            "error": "Missing required field 'merchant_name' in request payload."
        }

    user_instruction = payload.get("user_instruction", "") or ""
    if not isinstance(user_instruction, str):
        user_instruction = str(user_instruction)

    agent = EmailAgent()
    result = agent.run(merchant_name.strip(), user_instruction.strip())
    return result


@app.ping
def health_check() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
