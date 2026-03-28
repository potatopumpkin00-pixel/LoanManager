import database as db
import os
telegram_id = int(os.environ.get("AUTHORIZED_TELEGRAM_ID", 0))

loans = db.get_loan_by_name(telegram_id, "Raj")
print("Found loans for Raj:")
for l in loans:
    print(l)
