import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
from database import get_loan_by_name, get_all_loans
from agents import ConversationAgent

AUTHORIZED_TELEGRAM_ID = int(os.getenv("AUTHORIZED_TELEGRAM_ID", "0"))

print("All loans:", [l["lender_name"] for l in get_all_loans(AUTHORIZED_TELEGRAM_ID)])
print("Search 'Sundar':", [l["lender_name"] for l in get_loan_by_name(AUTHORIZED_TELEGRAM_ID, "Sundar")])

async def test_agent():
    agent = ConversationAgent()
    res = await agent.process("Show Amala loan status", AUTHORIZED_TELEGRAM_ID)
    print("Amala loan status:", res["action_taken"])
    print("Response:", res["response"])

asyncio.run(test_agent())
