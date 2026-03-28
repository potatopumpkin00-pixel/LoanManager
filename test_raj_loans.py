import os
import database as db

telegram_id = int(os.environ.get("AUTHORIZED_TELEGRAM_ID", 0))
loans = db.get_loan_by_name(telegram_id, "Raj")
print(f"Total Raj loans: {len(loans)}")
for idx, l in enumerate(loans):
    print(f"Loan {idx+1}: id={l['id']}, amount={l['principal']}, int={l['interest_rate']}, due={l['loan_date']}, paid={l['last_paid_month']}")
