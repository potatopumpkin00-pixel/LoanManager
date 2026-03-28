"""
database.py — Supabase CRUD operations for the loans table.
"""
import os
from datetime import date, timedelta
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")


def _get_client() -> Client:
    """Create and return a Supabase client."""
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------

def get_all_loans(telegram_id: int, filters: Optional[dict] = None) -> list[dict]:
    """Fetch all loans for the authorized user with optional filters."""
    client = _get_client()
    query = client.table("loans").select("*").eq("telegram_id", telegram_id)
    
    if filters:
        if "principal_lt" in filters:
            query = query.lt("principal", filters["principal_lt"])
        if "principal_gt" in filters:
            query = query.gt("principal", filters["principal_gt"])
        if "interest_rate" in filters:
            query = query.eq("interest_rate", filters["interest_rate"])
        if "interest_rate_lt" in filters:
            query = query.lt("interest_rate", filters["interest_rate_lt"])
        if "interest_rate_gt" in filters:
            query = query.gt("interest_rate", filters["interest_rate_gt"])

    response = query.order("loan_date").execute()
    data = response.data

    # Handle payment_status filter (unpaid/paid) in memory since it depends on current date logic
    if filters and "payment_status" in filters:
        status_filter = filters["payment_status"].lower()
        current_month_start = date.today().replace(day=1)
        
        filtered_data = []
        for loan in data:
            last_paid = _parse_date(loan.get("last_paid_month")) if loan.get("last_paid_month") else None
            is_paid = last_paid and last_paid >= current_month_start
            
            if status_filter == "unpaid" and not is_paid:
                filtered_data.append(loan)
            elif status_filter == "paid" and is_paid:
                filtered_data.append(loan)
        return filtered_data

    return data


def get_loan_by_name(telegram_id: int, lender_name: str, due_day: Optional[int] = None, filters: Optional[dict] = None) -> list[dict]:
    """Search loans by lender name (case-insensitive partial match).
    Prioritizes exact matches if found.
    Optionally filter by a specific due_day (day of the month).
    """
    client = _get_client()
    query = client.table("loans").select("*").eq("telegram_id", telegram_id).ilike("lender_name", f"%{lender_name}%")
    
    if filters:
        if "principal_lt" in filters:
            query = query.lt("principal", filters["principal_lt"])
        if "principal_gt" in filters:
            query = query.gt("principal", filters["principal_gt"])
        if "interest_rate" in filters:
            query = query.eq("interest_rate", filters["interest_rate"])
        if "interest_rate_lt" in filters:
            query = query.lt("interest_rate", filters["interest_rate_lt"])
        if "interest_rate_gt" in filters:
            query = query.gt("interest_rate", filters["interest_rate_gt"])

    response = query.execute()

    data = response.data
    if not data:
        return []

    # Prioritize exact matches
    exact_matches = [d for d in data if d["lender_name"].lower() == lender_name.lower()]
    filtered = exact_matches if exact_matches else data

    if due_day is not None:
        # Extract the day from YYYY-MM-DD and return loans due ON OR BEFORE this day
        filtered = [d for d in filtered if _parse_date(d["loan_date"]).day <= int(due_day)]

    # Handle payment_status filter
    if filters and "payment_status" in filters:
        status_filter = filters["payment_status"].lower()
        current_month_start = date.today().replace(day=1)
        
        final_filtered = []
        for loan in filtered:
            last_paid = _parse_date(loan.get("last_paid_month")) if loan.get("last_paid_month") else None
            is_paid = last_paid and last_paid >= current_month_start
            
            if status_filter == "unpaid" and not is_paid:
                final_filtered.append(loan)
            elif status_filter == "paid" and is_paid:
                final_filtered.append(loan)
        return final_filtered

    return filtered


def get_due_loans(telegram_id: int, target_date: Optional[date] = None) -> list[dict]:
    """
    Get loans whose monthly due day matches the target_date's day,
    AND whose last_paid_month is before the current month.

    For example, if target_date is 2026-03-15, returns loans where
    day(loan_date) == 15 and last_paid_month < '2026-03-01'.
    """
    if target_date is None:
        target_date = date.today()

    all_loans = get_all_loans(telegram_id)
    current_month_start = target_date.replace(day=1)
    due_day = target_date.day

    due_loans = []
    for loan in all_loans:
        loan_date = _parse_date(loan["loan_date"])
        last_paid = _parse_date(loan.get("last_paid_month")) if loan.get("last_paid_month") else None

        # Check if the due day matches
        if loan_date.day != due_day:
            continue

        # Check if already paid for this month
        if last_paid and last_paid >= current_month_start:
            continue

        due_loans.append(loan)

    return due_loans


def get_overdue_loans(telegram_id: int, target_date: Optional[date] = None) -> list[dict]:
    """
    Get loans that are due today OR were due in the past 1-2 days
    but still not paid for the current month.
    """
    if target_date is None:
        target_date = date.today()

    all_loans = get_all_loans(telegram_id)
    current_month_start = target_date.replace(day=1)

    overdue = []
    for loan in all_loans:
        loan_date = _parse_date(loan["loan_date"])
        last_paid = _parse_date(loan.get("last_paid_month")) if loan.get("last_paid_month") else None

        # Already paid this month — skip
        if last_paid and last_paid >= current_month_start:
            continue

        due_day = loan_date.day
        # Check if due_day falls within [target_date - 2, target_date]
        for offset in range(3):  # 0, 1, 2 days ago
            check_date = target_date - timedelta(days=offset)
            if check_date.day == due_day and check_date.month == target_date.month:
                overdue.append(loan)
                break

    return overdue


# ---------------------------------------------------------------------------
# WRITE
# ---------------------------------------------------------------------------

def add_loan(
    telegram_id: int,
    lender_name: str,
    principal: float,
    interest_rate: float,
    loan_date: str,
    last_paid_month: Optional[str] = None,
) -> dict:
    """Insert a new loan record."""
    client = _get_client()
    row = {
        "telegram_id": telegram_id,
        "lender_name": lender_name,
        "principal": principal,
        "interest_rate": interest_rate,
        "loan_date": loan_date,
    }
    if last_paid_month:
        row["last_paid_month"] = last_paid_month

    response = client.table("loans").insert(row).execute()
    return response.data[0] if response.data else {}


def mark_paid(loan_id: str, month: Optional[date] = None) -> dict:
    """
    Update last_paid_month for a loan.
    Defaults to the current date.
    """
    if month is None:
        month = date.today()

    client = _get_client()
    response = (
        client.table("loans")
        .update({"last_paid_month": month.isoformat()})
        .eq("id", loan_id)
        .execute()
    )
    return response.data[0] if response.data else {}


def delete_loan(loan_id: str) -> bool:
    """Delete a loan by its UUID."""
    client = _get_client()
    response = client.table("loans").delete().eq("id", loan_id).execute()
    return len(response.data) > 0


def get_existing_loan(telegram_id: int, lender_name: str, loan_date: str) -> Optional[dict]:
    """Check if a loan with the same lender_name and loan_date already exists and return it."""
    client = _get_client()
    response = (
        client.table("loans")
        .select("*")
        .eq("telegram_id", telegram_id)
        .eq("lender_name", lender_name)
        .eq("loan_date", loan_date)
        .execute()
    )
    return response.data[0] if response.data else None


def update_loan(loan_id: str, principal: float, interest_rate: float, last_paid_month: Optional[str] = None) -> dict:
    """Update an existing loan's principal, interest rate, and last paid month by ID."""
    client = _get_client()
    updates = {
        "principal": principal,
        "interest_rate": interest_rate,
        "last_paid_month": last_paid_month
    }
    response = client.table("loans").update(updates).eq("id", loan_id).execute()
    return response.data[0] if response.data else {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> date:
    """Parse an ISO date string to a date object."""
    return date.fromisoformat(str(date_str))


def format_loan_summary(loans: list[dict]) -> str:
    """Format a list of loans into a readable vertical summary string in Tamil."""
    if not loans:
        return "கடன் எதுவும் இல்லை."

    total_principal = sum(float(l["principal"]) for l in loans)
    total_monthly_interest = sum(float(l["principal"]) * float(l["interest_rate"]) / 100 for l in loans)

    header = (
        f"📋 **கடன் சுருக்கம்** ({len(loans)} கடன்கள்)\n"
        f"💰 மொத்த அசல்: ₹{total_principal:,.0f}\n"
        f"📈 மொத்த மாத வட்டி: ₹{total_monthly_interest:,.0f}\n"
    )

    lines = []
    for loan in loans:
        name = loan['lender_name']
        principal = float(loan['principal'])
        rate = float(loan['interest_rate'])
        monthly_interest = principal * rate / 100
        
        loan_date = loan["loan_date"]
        
        last_paid = loan.get("last_paid_month")
        if last_paid:
            status = f"✅ {last_paid} வரை செலுத்தப்பட்டது"
        else:
            status = "❌ இதுவரை செலுத்தப்படவில்லை"

        block = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {name}\n"
            f"💰 வட்டி நிலுவை: ₹{monthly_interest:,.0f}\n"
            f"📊 அசல்: ₹{principal:,.0f} @ {rate}%/மாதம்\n"
            f"📅 நிலுவை தேதி: {loan_date}\n"
            f"📌 நிலை: {status}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"\"{name} paid\" என்று பதில் அனுப்பவும் அல்லது குரல் செய்தி அனுப்பவும்."
        )
        lines.append(block)

    return header + "\n" + "\n\n".join(lines)
