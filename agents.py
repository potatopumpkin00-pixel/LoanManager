"""
agents.py — Conversation Agent powered by Groq (Llama-3.1 + Whisper).

Handles:
- Natural language understanding in Tamil & English
- Intent detection (check_status, mark_paid, add_loan, delete_loan, get_summary)
- Speech-to-text via Groq Whisper
- Executing database operations based on parsed intents
"""
import json
import logging
import os
from datetime import date
from typing import Optional

from dotenv import load_dotenv
from groq import Groq

import database as db
from utils.audio import detect_language

load_dotenv()

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
LLM_MODEL = "llama-3.1-8b-instant"
WHISPER_MODEL = "whisper-large-v3"

# System prompt for the Conversation Agent
SYSTEM_PROMPT = """
SYSTEM ROLE

You are an AI Personal Loan Manager assistant.

You help ONE user manage loans they have given to other people.

The assistant operates inside a Telegram bot and must handle:
- Text messages
- Voice messages (speech converted to text)

Users may speak casually and use natural language.

You must understand the request, extract structured data, and return a JSON command for the backend.

--------------------------------------------------

LANGUAGE SUPPORT

You understand:

• English
• Tamil (தமிழ்)
• Tanglish (Tamil written in English letters)

LANGUAGE RESPONSE RULES (CRITICAL)

1. ALWAYS respond in Tamil script (தமிழ்) regardless of the input language.
2. English input → Tamil script response
3. Tamil script input → Tamil script response
4. Tanglish input → Tamil script response
5. Never respond in English. All responses must be in Tamil.

Examples:

User: "Ravi interest paid"
Response: Tamil script

User: "ரவி பணம் கட்டிட்டார்"
Response: Tamil script

User: "ravi kaasu kuduthutan"
Response: Tamil script

--------------------------------------------------

USER CAPABILITIES

The user can ask about loans using natural language such as:

• lender name
• principal amount
• interest rate
• loan date
• due day
• paid / unpaid status
• date ranges
• "till today"
• "till due date"
• comparisons (above, below)

Examples:

"Show Ravi loan"
"Loans above 50000"
"Who hasn't paid interest"
"How much Sangeetha should pay till date"
"Show loans with 5 percent interest"

You must interpret these queries correctly.

--------------------------------------------------

SUPPORTED INTENTS

You must classify the message into ONE intent.

INTENTS:

check_status
Retrieve loan details using filters.

mark_paid
Mark an interest payment as completed.

add_loan
Create a new loan record.

delete_loan
Delete an existing loan record.

get_summary
Show overall loan statistics.

general_chat
Any message that does not match a command.

--------------------------------------------------

INTENT DETAILS

CHECK_STATUS

Used for retrieving loan information.

Examples:

"Show Ravi loan"
"Loans above 50000"
"Who hasn't paid interest"
"Loans with 5 percent interest"
"Show loans due on 15th"
"How much Sangeetha should pay till today"

Possible filters:

• lender_name
• principal
• interest_rate
• due_day
• loan_date
• payment_status
• amount greater/less than

--------------------------------------------------

MARK_PAID

Mark interest payment as completed.

Examples:

"Ravi paid"
"Mark interest paid for Kumar"
"ரவி 1000 கட்டினார்"
"ravi paid 2000 on 15th"
"Raj paid today 5000"

Extract:
• lender_name
• amount (number or null)
• payment_date (Format: YYYY-MM-DD or null. Translate 'today', 'yesterday', etc to YYYY-MM-DD using CURRENT DATE)

Always set intent to `mark_paid` when the user mentions a payment being made, even if amount or date is missing. DO NOT use `check_status` for "X paid" messages. If `amount` or `payment_date` is not mentioned, leave them as `null` in the params.

--------------------------------------------------

ADD_LOAN

Create a new loan record.

Required fields:

• lender_name
• principal
• interest_rate
• loan_date

Optional:

• due_day

Examples:

"I gave Ravi 50000 at 5% on Jan 5"
"Add loan Kumar 30000 4 percent Feb 10"

If any required information is missing,
ask the user for the missing data.

--------------------------------------------------

DELETE_LOAN

Delete a loan record.

Examples:

"Delete Ravi loan"
"Remove Kumar loan"

This is destructive.

Set:
needs_confirmation = true

--------------------------------------------------

GET_SUMMARY

Return overall loan statistics.

Examples:

"Loan summary"
"Total outstanding"
"Show all loans summary"

--------------------------------------------------

PARAMETER EXTRACTION

Extract parameters whenever possible.

PARAMETERS:

lender_name
Name of borrower.

principal
Loan amount.

interest_rate
Monthly interest percentage.

loan_date
Format: YYYY-MM-DD

due_day
Integer 1–31.

If user says:
"today"
"till date"

Use the current day number.

--------------------------------------------------

FILTER SUPPORT

Users may ask filtered queries.

Examples:

"Loans above 50000"

filters:
{
  "principal_gt": 50000
}

"Loans below 20000"

filters:
{
  "principal_lt": 20000
}

"Loans with 5 percent interest"

filters:
{
  "interest_rate": 5
}

"Unpaid interest"

filters:
{
  "payment_status": "unpaid"
}

--------------------------------------------------

OUTPUT FORMAT

You must ALWAYS return ONLY JSON.

Never include explanations outside JSON.

FORMAT:

{
  "intent": "check_status | mark_paid | add_loan | delete_loan | get_summary | general_chat",
  "params": {
    "lender_name": "",
    "amount": null,
    "payment_date": null,
    "principal": 0,
    "interest_rate": 0,
    "loan_date": "",
    "due_day": null
  },
  "filters": {},
  "response": "",
  "needs_confirmation": false
}

--------------------------------------------------

FIELD DESCRIPTION

intent
Detected action.

params
Direct parameters extracted.

filters
Conditions used for search queries.

response
Friendly message for the user.

needs_confirmation
True for destructive actions like delete_loan.

--------------------------------------------------

CONFIRMATION RULES

When confirming actions always clearly mention:

• lender name
• amount (if applicable)

Example:

"ரவியின் வட்டி செலுத்தப்பட்டதாக குறிக்கப்பட்டது."

"குமாரின் கடன் நீக்கப்பட்டது."

--------------------------------------------------

ERROR HANDLING

If required information is missing:

1. Set intent to "general_chat"
2. Ask for missing data.

Example:

User:
"Add loan for Ravi"

Response:
"கடன் தொகை மற்றும் வட்டி விகிதம் என்ன?"

--------------------------------------------------

IMPORTANT RULES

1. Output JSON only.
2. No text outside JSON.
3. Always respond in Tamil script.
4. Be concise and friendly.
5. Understand casual speech and voice transcription errors.
"""

class ConversationAgent:
    """Multi-lingual conversation agent for loan management."""

    def __init__(self):
        self.client = Groq(api_key=GROQ_API_KEY)
        # Per-user conversation history (limited to last 10 exchanges)
        self.history: list[dict] = []
        self.max_history = 10
        # Pending action awaiting confirmation
        self.pending_action: Optional[dict] = None

    async def process(self, user_text: str, telegram_id: int) -> dict:
        """
        Process a user message and return an action result.

        Returns:
            dict with keys:
                - response: str (text to send back to user)
                - action_taken: str (what DB action was performed, if any)
                - lang: str ("ta" or "en")
        """
        lang = detect_language(user_text)

        # Check if user is confirming a pending action
        if self.pending_action:
            return await self._handle_confirmation(user_text, telegram_id, lang)

        # Fetch current lender names to help LLM resolve entities correctly (e.g., cross-lingual or misspellings)
        try:
            loans = db.get_all_loans(telegram_id)
            unique_names = list(set([loan["lender_name"] for loan in loans]))
            if unique_names:
                names_context = (
                    f"\n\nKNOWN LENDERS IN DATABASE: {', '.join(unique_names)}\n"
                    f"CRITICAL RULE FOR lender_name IN JSON PARAMS:\n"
                    f"1. The `lender_name` field in JSON params MUST ALWAYS use the EXACT English spelling from the KNOWN LENDERS list above.\n"
                    f"2. NEVER translate lender names to Tamil script in the JSON params. For example, output \"Sangeetha\" NOT \"சங்கீதா\".\n"
                    f"3. If the user says a name in Tamil (e.g., 'சங்கீதா', 'அமலா') or misspells it (e.g., 'Sangeeta'), match it phonetically to the KNOWN LENDERS list and output the exact English spelling.\n"
                    f"4. Tamil script is ONLY for the `response` field, NEVER for `lender_name` in params.\n"
                )
            else:
                names_context = ""
        except Exception as e:
            logger.error(f"Failed to fetch known lenders for context: {e}")
            names_context = ""

        # Inject current date context so the AI knows what "today" or "tomorrow" means
        today = date.today()
        date_context = f"\n\nCURRENT DATE: {today.strftime('%Y-%m-%d')} (Day {today.day} of the month)\n"

        # Build messages for LLM
        messages = [{"role": "system", "content": SYSTEM_PROMPT + names_context + date_context}]

        # Add conversation history
        for msg in self.history[-self.max_history:]:
            messages.append(msg)

        # Add current user message
        messages.append({"role": "user", "content": user_text})

        try:
            # Call Groq LLM
            completion = self.client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                temperature=0.3,
                max_tokens=1024,
                response_format={"type": "json_object"},
            )

            response_text = completion.choices[0].message.content
            parsed = json.loads(response_text)

            # Update conversation history
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": response_text})

            # Trim history
            if len(self.history) > self.max_history * 2:
                self.history = self.history[-self.max_history * 2:]

            # Execute the intent
            return await self._execute_intent(parsed, telegram_id, lang, user_text)

        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM response: {response_text}")
            return {
                "response": "மன்னிக்கவும், புரியவில்லை. மீண்டும் சொல்ல முடியுமா?",
                "action_taken": None,
                "lang": lang,
            }
        except Exception as e:
            logger.error(f"Agent error: {e}")
            return {
                "response": f"பிழை ஏற்பட்டது: {str(e)}",
                "action_taken": None,
                "lang": lang,
            }

    async def _execute_intent(self, parsed: dict, telegram_id: int, lang: str, user_text: str = "") -> dict:
        """Execute the detected intent against the database."""
        intent = parsed.get("intent", "general_chat")
        params = parsed.get("params", {})
        llm_response = parsed.get("response", "")
        needs_confirmation = parsed.get("needs_confirmation", False)

        # Handle confirmation-required actions
        if needs_confirmation and intent in ("delete_loan",):
            self.pending_action = {"intent": intent, "params": params, "telegram_id": telegram_id}
            return {
                "response": llm_response or "உறுதியாகவா? உறுதிப்படுத்த 'ஆம்' என்று பதில் அனுப்புங்கள்.",
                "action_taken": None,
                "lang": lang,
            }

        if intent == "check_status":
            filters = parsed.get("filters", {}) or {}
            
            # lender_name could be in params or filters depending on how the LLM structures it
            lender_name = params.get("lender_name") or filters.pop("lender_name", None)
            
            raw_due_day = params.get("due_day")
            
            # Safe parsing for due_day to avoid crashing on strings like "today"
            due_day = None
            if raw_due_day is not None:
                try:
                    due_day = int(raw_due_day)
                except ValueError:
                    # If LLM failed to convert to integer, assume "today" or fallback gracefully
                    due_day = date.today().day
            else:
                # If LLM didn't extract a due_day but user said "till date" or "today"
                text_lower = user_text.lower()
                if "till date" in text_lower or "today" in text_lower or "இன்று" in text_lower:
                    due_day = date.today().day

            if lender_name:
                loans = db.get_loan_by_name(telegram_id, lender_name, due_day, filters)
            else:
                loans = db.get_all_loans(telegram_id, filters)
            summary = db.format_loan_summary(loans)
            interactive_prompt = "\n\nஉங்களுக்கு ஏதேனும் விவரங்களை புதுப்பிக்க வேண்டுமா? (எழுத்து அல்லது குரல் வழியாக பதிலளிக்கவும்)"
            return {
                "response": summary + interactive_prompt,
                "action_taken": "check_status",
                "lang": lang,
                "audio_prompt": "உங்களுக்கு ஏதேனும் விவரங்களை புதுப்பிக்க வேண்டுமா?"
            }

        elif intent == "mark_paid":
            lender_name = params.get("lender_name", "")
            amount = params.get("amount")
            payment_date = params.get("payment_date")
            
            loans = db.get_loan_by_name(telegram_id, lender_name)
            if not loans:
                return {
                    "response": f"'{lender_name}' என்ற பெயரில் கடன் இல்லை.",
                    "action_taken": None,
                    "lang": lang,
                }
            
            # Check for missing amount or date
            if not amount and not payment_date:
                return {
                    "response": f"{lender_name} எவ்வளவு தொகை, எந்த தேதியில் செலுத்தினார்?",
                    "action_taken": None,
                    "lang": lang,
                }
            elif not amount:
                return {
                    "response": f"{lender_name} எவ்வளவு தொகை செலுத்தினார்?",
                    "action_taken": None,
                    "lang": lang,
                }
            elif not payment_date:
                return {
                    "response": f"{lender_name} எந்த தேதியில் தொகையை செலுத்தினார்?",
                    "action_taken": None,
                    "lang": lang,
                }

            # Parse the payment date string
            try:
                current_date = date.fromisoformat(str(payment_date))
            except (ValueError, AttributeError):
                current_date = date.today()

            # Mark the first matching loan as paid
            loan = loans[0]
            db.mark_paid(loan["id"], current_date)
            
            response = (
                f"✅ {loan['lender_name']} "
                f"₹{float(amount):,.0f} செலுத்தியதாக குறிக்கப்பட்டது! "
                f"(தேதி: {current_date.strftime('%Y-%m-%d')})"
            )
            return {"response": response, "action_taken": "mark_paid", "lang": lang}

        elif intent == "add_loan":
            lender_name = params.get("lender_name")
            principal = params.get("principal")
            interest_rate = params.get("interest_rate")
            loan_date = params.get("loan_date")

            # Verify all fields are present
            if not all([lender_name, principal, interest_rate, loan_date]):
                return {
                    "response": llm_response or "கடன் விவரங்கள் தேவை: பெயர், கடன் தொகை, வட்டி விகிதம், தேதி.",
                    "action_taken": None,
                    "lang": lang,
                }

            new_loan = db.add_loan(
                telegram_id=telegram_id,
                lender_name=lender_name,
                principal=float(principal),
                interest_rate=float(interest_rate),
                loan_date=loan_date,
            )
            response = (
                f"✅ புதிய கடன் சேர்க்கப்பட்டது!\n"
                f"👤 {lender_name}\n"
                f"💰 ₹{float(principal):,.0f} @ {interest_rate}%/மாதம்\n"
                f"📅 தேதி: {loan_date}"
            )
            return {"response": response, "action_taken": "add_loan", "lang": lang}

        elif intent == "delete_loan":
            lender_name = params.get("lender_name", "")
            loans = db.get_loan_by_name(telegram_id, lender_name)
            if not loans:
                return {
                    "response": f"'{lender_name}' என்ற பெயரில் கடன் இல்லை.",
                    "action_taken": None,
                    "lang": lang,
                }
            db.delete_loan(loans[0]["id"])
            return {
                "response": f"🗑 {loans[0]['lender_name']} கடன் நீக்கப்பட்டது.",
                "action_taken": "delete_loan",
                "lang": lang,
            }

        elif intent == "get_summary":
            loans = db.get_all_loans(telegram_id)
            summary = db.format_loan_summary(loans)
            interactive_prompt = "\n\nஉங்களுக்கு ஏதேனும் விவரங்களை புதுப்பிக்க வேண்டுமா? (எழுத்து அல்லது குரல் வழியாக பதிலளிக்கவும்)"
            return {
                "response": summary + interactive_prompt,
                "action_taken": "get_summary",
                "lang": lang,
                "audio_prompt": "உங்களுக்கு ஏதேனும் விவரங்களை புதுப்பிக்க வேண்டுமா?"
            }

        else:
            # general_chat — just return the LLM response
            return {
                "response": llm_response or "உங்கள் கடன்கள் குறித்து எப்படி உதவ வேண்டும்?",
                "action_taken": None,
                "lang": lang,
            }

    async def _handle_confirmation(self, user_text: str, telegram_id: int, lang: str) -> dict:
        """Handle yes/no confirmation for pending actions."""
        positive = user_text.lower().strip() in (
            "yes", "y", "ஆம்", "aam", "ok", "confirm", "sure", "சரி",
        )

        action = self.pending_action
        self.pending_action = None

        if not positive:
            return {
                "response": "ரத்து செய்யப்பட்டது.",
                "action_taken": None,
                "lang": lang,
            }

        # Re-execute the intent without confirmation flag
        parsed = {"intent": action["intent"], "params": action["params"]}
        return await self._execute_intent(parsed, telegram_id, lang, user_text)


# ---------------------------------------------------------------------------
# Speech-to-Text (Whisper)
# ---------------------------------------------------------------------------

def transcribe_audio(mp3_path: str) -> str:
    """
    Transcribe an audio file using Groq Whisper.

    Args:
        mp3_path: Path to the MP3 file.

    Returns:
        Transcribed text.
    """
    client = Groq(api_key=GROQ_API_KEY)

    with open(mp3_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            file=("audio.mp3", audio_file.read()),
            model=WHISPER_MODEL,
            language="ta",          # Hint for Tamil, Whisper auto-detects too
            response_format="text",
        )

    return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
