"""
main.py — Telegram Bot entry point for the Personal Loan Manager.

Handles:
- /start, /status, /add, /ingest commands
- Text messages → Conversation Agent
- Voice messages → Whisper STT → Agent → Edge-TTS response
- Inline keyboard callbacks for reminders
"""
import io
import json
import logging
import os
import tempfile

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

import database as db
from agents import ConversationAgent, transcribe_audio
from ingest import ingest_loans
from utils.audio import oga_to_mp3, text_to_speech, detect_language
from utils.scheduler import setup_scheduler, check_and_send_reminders

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Environment
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AUTHORIZED_TELEGRAM_ID = int(os.getenv("AUTHORIZED_TELEGRAM_ID", "0"))

# Conversation Agent (single instance for single user)
agent = ConversationAgent()


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------

def authorized_only(func):
    """Decorator to restrict bot access to the authorized user."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != AUTHORIZED_TELEGRAM_ID:
            await update.message.reply_text(
                "⛔ அங்கீகரிக்கப்படவில்லை. இது தனிப்பட்ட போட்."
            )
            logger.warning(f"Unauthorized access attempt by user {user_id}")
            return
        return await func(update, context)
    return wrapper


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

@authorized_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome = (
        "🏦 **தனிநபர் கடன் மேலாளர்**\n\n"
        "வணக்கம்! உங்கள் கடன்களை நிர்வகிக்க நான் உதவுகிறேன்.\n\n"
        "**கட்டளைகள்:**\n"
        "/status — அனைத்து கடன்களைக் காண\n"
        "/add — புதிய கடன் சேர்க்க\n"
        "/ingest — JSON கோப்பிலிருந்து கடன்களை ஏற்ற\n\n"
        "**அல்லது என்னிடம் பேசுங்கள்!** 💬\n"
        "தமிழ் அல்லது ஆங்கிலத்தில் தட்டச்சு செய்யலாம் அல்லது குரல் செய்தி அனுப்பலாம்.\n\n"
        "எடுத்துக்காட்டுகள்:\n"
        "• \"அனைத்து கடன்களைக் காட்டு\"\n"
        "• \"ரவி இந்த மாதம் பணம் கட்டிட்டார்\"\n"
        "• \"Senthil க்கு 50000, 2% வட்டி, March 10 முதல் கடன் சேர்\"\n"
    )
    await update.message.reply_text(welcome, parse_mode="Markdown")


@authorized_only
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show all loans."""
    loans = db.get_all_loans(AUTHORIZED_TELEGRAM_ID)
    summary = db.format_loan_summary(loans)
    await send_long_message(update, summary, parse_mode="Markdown")


@authorized_only
async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /add command — guided loan addition."""
    msg = (
        "📝 **புதிய கடன் சேர்க்க**\n\n"
        "இந்த வடிவத்தில் விவரங்களை அனுப்புங்கள்:\n"
        "`பெயர், அசல் தொகை, வட்டி விகிதம்%, கடன் தேதி`\n\n"
        "எடுத்துக்காட்டு:\n"
        "`Ravi Kumar, 50000, 2, 2024-06-15`\n\n"
        "அல்லது இயல்பாகச் சொல்லுங்கள்:\n"
        "\"ரவிக்கு 50000 ரூபாய் 2% வட்டியில் June 15, 2024 முதல் கடன் சேர்\""
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


@authorized_only
async def cmd_ingest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ingest command — load JSON from file or attachment."""
    if update.message.document:
        # User sent a JSON file
        file = await update.message.document.get_file()
        tmp_path = os.path.join(tempfile.gettempdir(), "ingest_upload.json")
        await file.download_to_drive(tmp_path)

        await update.message.reply_text("📂 பதிவேற்றிய கோப்பை செயலாக்குகிறது...")
        result = ingest_loans(tmp_path, AUTHORIZED_TELEGRAM_ID)

        if "error" in result:
            await update.message.reply_text(f"❌ {result['error']}")
        else:
            for detail in result["details"]:
                await update.message.reply_text(detail)
            await update.message.reply_text(result["summary"])

        # Cleanup
        os.remove(tmp_path)
    else:
        # Try default file
        default_path = os.path.join(os.path.dirname(__file__), "data", "loans.json")
        if os.path.exists(default_path):
            await update.message.reply_text(f"📂 `data/loans.json` கோப்பிலிருந்து ஏற்றுகிறது...", parse_mode="Markdown")
            result = ingest_loans(default_path, AUTHORIZED_TELEGRAM_ID)

            if "error" in result:
                await update.message.reply_text(f"❌ {result['error']}")
            else:
                for detail in result["details"]:
                    await update.message.reply_text(detail)
                await update.message.reply_text(result["summary"])
        else:
            await update.message.reply_text(
                "📎 கடன் தரவு கொண்ட JSON கோப்பை அனுப்புங்கள், அல்லது `data/` கோப்புறையில் `loans.json` வைக்கவும்.\n\n"
                "வடிவம்:\n```json\n[\n  {\n    \"lender_name\": \"Ravi\",\n"
                "    \"principal\": 50000,\n    \"interest_rate\": 2.0,\n"
                "    \"loan_date\": \"2024-06-15\"\n  }\n]\n```",
                parse_mode="Markdown",
            )


@authorized_only
async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually trigger daily reminders."""
    await update.message.reply_text("⏳ இன்றைய நிலுவை கடன்களை சரிபார்க்கிறது...")
    await check_and_send_reminders(context.bot)
    await update.message.reply_text("✅ நினைவூட்டல் சரிபார்ப்பு முடிந்தது!")


# ---------------------------------------------------------------------------
# Message Helpers
# ---------------------------------------------------------------------------

async def send_long_message(update: Update, text: str, parse_mode: str = "Markdown", **kwargs):
    """
    Safely send long messages that might exceed Telegram's 4096 character limit
    by chunking them by newlines.
    """
    MAX_LENGTH = 4000  # Leave some buffer
    
    if len(text) <= MAX_LENGTH:
        await update.message.reply_text(text, parse_mode=parse_mode, **kwargs)
        return

    # Chunk the message
    chunks = []
    lines = text.split('\n')
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk) + len(line) + 1 > MAX_LENGTH:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = line + "\n"
            else:
                # Edge case: single line is longer than MAX_LENGTH
                chunks.append(line[:MAX_LENGTH])
                current_chunk = line[MAX_LENGTH:] + "\n"
        else:
            current_chunk += line + "\n"
            
    if current_chunk:
        chunks.append(current_chunk)
        
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=parse_mode, **kwargs)


# ---------------------------------------------------------------------------
# Message handlers
# ---------------------------------------------------------------------------

@authorized_only
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming text messages → route to Conversation Agent."""
    user_text = update.message.text
    logger.info(f"Text from user: {user_text}")

    result = await agent.process(user_text, AUTHORIZED_TELEGRAM_ID)
    await send_long_message(update, result["response"], parse_mode="Markdown")


@authorized_only
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle voice messages:
    1. Download OGA → Convert to MP3
    2. Transcribe with Whisper
    3. Process with Conversation Agent
    4. Generate TTS response → Send voice note back
    """
    await update.message.reply_text("🎤 உங்கள் குரல் செய்தியை செயலாக்குகிறது...")

    try:
        # 1. Download voice file
        voice = update.message.voice
        file = await voice.get_file()
        oga_path = os.path.join(tempfile.gettempdir(), f"voice_{update.message.message_id}.oga")
        await file.download_to_drive(oga_path)

        # 2. Convert OGA → MP3
        mp3_path = oga_to_mp3(oga_path)

        # 3. Transcribe
        transcription = transcribe_audio(mp3_path)
        logger.info(f"Transcription: {transcription}")
        await update.message.reply_text(f"🗣 நீங்கள் சொன்னது: _{transcription}_", parse_mode="Markdown")

        # 4. Process with Agent
        result = await agent.process(transcription, AUTHORIZED_TELEGRAM_ID)
        await send_long_message(update, result["response"], parse_mode="Markdown")

        # 5. Generate TTS response and send as voice
        tts_path = await text_to_speech(result["response"], result.get("lang"))
        with open(tts_path, "rb") as audio:
            await update.message.reply_voice(voice=audio)

        # Cleanup temp files
        for path in [oga_path, mp3_path, tts_path]:
            if os.path.exists(path):
                os.remove(path)

    except Exception as e:
        logger.error(f"Voice processing error: {e}")
        await update.message.reply_text(
            f"❌ குரல் செய்தி செயலாக்கத்தில் பிழை: {str(e)}"
        )


@authorized_only
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document uploads — check if it's a JSON for ingestion."""
    doc = update.message.document
    if doc.file_name and doc.file_name.endswith(".json"):
        # Treat as ingestion file
        await cmd_ingest(update, context)
    else:
        await update.message.reply_text(
            "கடன் தரவு ஏற்றுவதற்கு `.json` கோப்புகளை மட்டுமே செயலாக்க முடியும்."
        )


# ---------------------------------------------------------------------------
# Callback handler (for inline keyboard buttons)
# ---------------------------------------------------------------------------

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard callbacks (e.g., from reminders)."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    if user_id != AUTHORIZED_TELEGRAM_ID:
        return

    data = query.data
    if data.startswith("paid:"):
        loan_id = data.split(":")[1]
        from datetime import date
        db.mark_paid(loan_id, date.today().replace(day=1))
        await query.edit_message_text(
            f"✅ {date.today().strftime('%B %Y')} மாதத்திற்கு செலுத்தப்பட்டதாக குறிக்கப்பட்டது!"
        )
    elif data.startswith("skip:"):
        await query.edit_message_text("⏭ தற்போதைக்கு தவிர்க்கப்பட்டது.")


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

def main():
    """Start the bot."""
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_TOKEN not set in .env")
        return

    if not AUTHORIZED_TELEGRAM_ID:
        print("❌ AUTHORIZED_TELEGRAM_ID not set in .env")
        return

    print("🚀 Starting Personal Loan Manager Bot...")

    # post_init runs after the event loop is created, so the scheduler can start
    async def post_init(application):
        setup_scheduler(application.bot)
        print("✅ Scheduler started!")

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("ingest", cmd_ingest))
    app.add_handler(CommandHandler("remind", cmd_remind))

    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Callback handler
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("✅ Bot is running! Press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
