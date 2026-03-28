import os
import database as db
from datetime import date

telegram_id = int(os.environ.get("AUTHORIZED_TELEGRAM_ID", 0))

# Get Raj's loan
loans = db.get_loan_by_name(telegram_id, "Raj")
if loans:
    print("Found loan:", loans[0])
    loan_id = loans[0]["id"]
    
    # Try marking as paid
    print("Marking as paid today...")
    res = db.mark_paid(loan_id, date.today())
    print("Response from mark_paid:", res)
    
    # Check again
    loans_after = db.get_loan_by_name(telegram_id, "Raj")
    print("Loan after update:", loans_after[0])
else:
    print("Raj not found.")
