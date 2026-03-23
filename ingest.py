"""
ingest.py — Load loans from a JSON file into Supabase.

Usage:
    python ingest.py --file data/loans.json --telegram-id 123456789

Or via the /ingest command in the Telegram bot.
"""
import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from database import add_loan, get_existing_loan, update_loan


def validate_loan(loan: dict, index: int) -> list[str]:
    """Validate a single loan entry and return a list of errors."""
    errors = []
    required = ["lender_name", "principal", "interest_rate", "loan_date"]
    for field in required:
        if field not in loan:
            errors.append(f"  Loan #{index + 1}: missing required field '{field}'")

    if "principal" in loan:
        try:
            val = float(loan["principal"])
            if val <= 0:
                errors.append(f"  Loan #{index + 1}: 'principal' must be positive")
        except (ValueError, TypeError):
            errors.append(f"  Loan #{index + 1}: 'principal' is not a valid number")

    if "interest_rate" in loan:
        try:
            val = float(loan["interest_rate"])
            if val < 0:
                errors.append(f"  Loan #{index + 1}: 'interest_rate' cannot be negative")
        except (ValueError, TypeError):
            errors.append(f"  Loan #{index + 1}: 'interest_rate' is not a valid number")

    return errors


def ingest_loans(file_path: str, telegram_id: int) -> dict:
    """
    Read a JSON file and insert/update loans into Supabase.

    Returns a dict with counts: inserted, updated, skipped, errors.
    """
    path = Path(file_path)
    if not path.exists():
        return {"error": f"File not found: {file_path}"}

    try:
        with open(path, "r", encoding="utf-8") as f:
            loans = json.load(f)
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}

    if not isinstance(loans, list):
        return {"error": "JSON must be an array of loan objects"}

    # Validate all loans first
    all_errors = []
    for i, loan in enumerate(loans):
        all_errors.extend(validate_loan(loan, i))

    if all_errors:
        return {"error": "Validation failed:\n" + "\n".join(all_errors)}

    inserted = 0
    updated = 0
    skipped = 0
    results = []

    for loan in loans:
        lender = loan["lender_name"]
        loan_date = loan["loan_date"]
        principal = float(loan["principal"])
        interest_rate = float(loan["interest_rate"])
        last_paid_month = loan.get("last_paid_month")

        existing_loan = get_existing_loan(telegram_id, lender, loan_date)

        if existing_loan:
            # Check if any mutable data actually changed compared to DB
            db_principal = existing_loan.get("principal")
            db_rate = existing_loan.get("interest_rate")
            db_last_paid = existing_loan.get("last_paid_month")

            if (
                float(db_principal) != principal or 
                float(db_rate) != interest_rate or 
                db_last_paid != last_paid_month
            ):
                try:
                    update_loan(
                        existing_loan["id"],
                        principal=principal,
                        interest_rate=interest_rate,
                        last_paid_month=last_paid_month
                    )
                    updated += 1
                    results.append(f"🔄 Updated: {lender} — {loan_date}")
                except Exception as e:
                    results.append(f"❌ Error updating {lender}: {e}")
            else:
                skipped += 1
                results.append(f"⏭ Skipped (no changes): {lender} — {loan_date}")
        else:
            try:
                add_loan(
                    telegram_id=telegram_id,
                    lender_name=lender,
                    principal=principal,
                    interest_rate=interest_rate,
                    loan_date=loan_date,
                    last_paid_month=last_paid_month,
                )
                inserted += 1
                results.append(f"✅ Inserted: {lender} — ₹{principal:,.0f}")
            except Exception as e:
                results.append(f"❌ Error inserting {lender}: {e}")

    summary = (
        f"\n{'─' * 40}\n"
        f"📥 Ingestion Complete\n"
        f"  ✅ Inserted: {inserted}\n"
        f"  🔄 Updated:  {updated}\n"
        f"  ⏭ Skipped:  {skipped}\n"
        f"  📋 Total:    {len(loans)}\n"
        f"{'─' * 40}"
    )

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "total": len(loans),
        "details": results,
        "summary": summary,
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest loans from JSON into Supabase")
    parser.add_argument("--file", "-f", required=True, help="Path to loans JSON file")
    parser.add_argument(
        "--telegram-id", "-t", required=True, type=int,
        help="Telegram user ID (owner of these loans)"
    )
    args = parser.parse_args()

    print(f"📂 Loading loans from: {args.file}")
    print(f"👤 Telegram ID: {args.telegram_id}")
    print()

    result = ingest_loans(args.file, args.telegram_id)

    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)

    for detail in result["details"]:
        print(detail)

    print(result["summary"])


if __name__ == "__main__":
    main()
