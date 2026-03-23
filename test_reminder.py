import asyncio
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

from database import get_overdue_loans

telegram_id = int(os.getenv("AUTHORIZED_TELEGRAM_ID", "7540981315"))
print(f"Testing for telegram_id: {telegram_id}")

loans = get_overdue_loans(telegram_id, date(2026, 3, 19))
print(f"Found {len(loans)} overdue loans:")
for loan in loans:
    print(f" - {loan['lender_name']} (Due: {loan['loan_date']}, Paid till: {loan.get('last_paid_month')})")
