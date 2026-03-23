"""
utils/scheduler.py — Daily reminder scheduler using APScheduler.

Sends payment reminders on the due date and for 2 days after if unpaid.
"""
import logging
import os
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

AUTHORIZED_TELEGRAM_ID = int(os.getenv("AUTHORIZED_TELEGRAM_ID", "0"))
REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "9"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")


def format_reminder_message(loan: dict, day_offset: int = 0) -> str:
    """
    Format a reminder message for a single loan in Tamil.

    Args:
        loan: Loan dict from database.
        day_offset: 0=due today, 1=1 day overdue, 2=2 days overdue.
    """
    principal = float(loan["principal"])
    rate = float(loan["interest_rate"])
    monthly_interest = principal * rate / 100
    lender = loan["lender_name"]

    if day_offset == 0:
        urgency = "🔔 இன்று நிலுவை"
    elif day_offset == 1:
        urgency = "⚠️ 1 நாள் தாமதம்"
    else:
        urgency = "🚨 2 நாள் தாமதம்"

    return (
        f"{urgency}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **{lender}**\n"
        f"💰 வட்டி நிலுவை: **₹{monthly_interest:,.0f}**\n"
        f"📊 அசல்: ₹{principal:,.0f} @ {rate}%/மாதம்\n"
        f"📅 நிலுவை தேதி: {loan['loan_date']}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"\"**{lender} paid**\" என்று பதில் அனுப்பவும் அல்லது குரல் செய்தி அனுப்பவும்.\n"
    )


async def check_and_send_reminders(bot):
    """
    Check for due and overdue loans and send reminders.

    This is called daily by APScheduler.
    """
    # Import here to avoid circular imports
    from database import get_overdue_loans

    logger.info("🕐 Running daily reminder check...")

    try:
        overdue_loans = get_overdue_loans(AUTHORIZED_TELEGRAM_ID, date.today())

        if not overdue_loans:
            logger.info("No due or overdue loans today.")
            return

        today = date.today()

        for loan in overdue_loans:
            loan_day = int(loan["loan_date"].split("-")[2]) if isinstance(loan["loan_date"], str) else loan["loan_date"].day
            day_offset = today.day - loan_day
            day_offset = max(0, min(day_offset, 2))

            message = format_reminder_message(loan, day_offset)

            try:
                await bot.send_message(
                    chat_id=AUTHORIZED_TELEGRAM_ID,
                    text=message,
                    parse_mode="Markdown",
                )
                logger.info(f"Sent reminder for: {loan['lender_name']}")
            except Exception as e:
                logger.error(f"Failed to send reminder for {loan['lender_name']}: {e}")

        # Send summary if multiple loans
        if len(overdue_loans) > 1:
            total_interest = sum(
                float(l["principal"]) * float(l["interest_rate"]) / 100
                for l in overdue_loans
            )
            summary = (
                f"📋 **மொத்த நினைவூட்டல்கள்: {len(overdue_loans)}**\n"
                f"💰 மொத்த வட்டி நிலுவை: **₹{total_interest:,.0f}**"
            )
            await bot.send_message(
                chat_id=AUTHORIZED_TELEGRAM_ID,
                text=summary,
                parse_mode="Markdown",
            )

    except Exception as e:
        logger.error(f"Reminder check failed: {e}")


async def run_startup_check(bot):
    """
    Run a reminder check shortly after bot startup to catch any missed reminders.
    Waits 10 seconds to ensure the bot is fully initialized.
    """
    import asyncio
    await asyncio.sleep(10)
    logger.info("🔄 Running startup reminder check for any missed reminders...")
    await check_and_send_reminders(bot)
    logger.info("✅ Startup reminder check complete.")


def setup_scheduler(bot) -> AsyncIOScheduler:
    """
    Set up the APScheduler with a daily reminder job.

    Args:
        bot: The Telegram Bot instance.

    Returns:
        The configured scheduler (already started).
    """
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Daily reminder at configured hour
    scheduler.add_job(
        check_and_send_reminders,
        trigger=CronTrigger(hour=REMINDER_HOUR, minute=0, timezone=TIMEZONE),
        args=[bot],
        id="daily_reminder",
        name="Daily Loan Payment Reminder",
        replace_existing=True,
        misfire_grace_time=3600,  # Allow 1 hour grace time if the execution gets delayed
    )

    # Startup check — catch any missed reminders
    scheduler.add_job(
        run_startup_check,
        trigger="date",  # Run once immediately
        args=[bot],
        id="startup_reminder_check",
        name="Startup Reminder Check",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(f"✅ Scheduler started — reminders at {REMINDER_HOUR}:00 {TIMEZONE}")

    return scheduler
