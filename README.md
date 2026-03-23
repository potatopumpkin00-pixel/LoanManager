# Personal Loan Manager — Telegram Bot

A personal Telegram bot to manage loans given to various people, with **Tamil/English** voice & text support, automated reminders, and AI-powered conversations.

## Features

- 🗣 **Bilingual** — Chat in Tamil, English, or Tanglish
- 🎤 **Voice Support** — Send/receive voice messages (Whisper STT + Edge-TTS)
- 🔔 **Smart Reminders** — Daily reminders on due day + 2 follow-ups
- 🤖 **AI Agent** — Natural language loan management via Groq Llama-3.1
- 📊 **Loan Dashboard** — View all loans, payment status, and summaries
- 🔒 **Single User** — Private bot, authorized via Telegram ID

## Quick Start

### 1. Prerequisites

- Python 3.11+
- FFmpeg (`brew install ffmpeg` on Mac)
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Groq API Key (from [console.groq.com](https://console.groq.com))
- Supabase project (from [supabase.com](https://supabase.com))

### 2. Supabase Setup

Create the `loans` table in your Supabase SQL editor:

```sql
CREATE TABLE loans (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    lender_name TEXT NOT NULL,
    principal NUMERIC NOT NULL,
    interest_rate NUMERIC NOT NULL,
    loan_date DATE NOT NULL,
    last_paid_month DATE,
    telegram_id BIGINT NOT NULL
);
```

### 3. Install & Configure

```bash
cd LoanManager
pip install -r requirements.txt

# Copy and fill in your keys
cp .env.example .env
# Edit .env with your actual keys
```

### 4. Load Initial Data

```bash
python ingest.py --file data/loans.json --telegram-id YOUR_ID
```

### 5. Run the Bot

```bash
python main.py
```

## Usage

| Action | Text Example | Tamil Example |
|---|---|---|
| View loans | "Show all loans" | "எல்லா கடன்களையும் காட்டு" |
| Mark paid | "Ravi paid" | "ரவி பணம் கட்டிட்டார்" |
| Add loan | "Add loan for Senthil, 50000, 2%, March 10" | — |
| Check specific | "How much does Ravi owe?" | "ரவி கடன் எவ்வளவு?" |

## Deployment (Railway)

```bash
# Push to GitHub, then on Railway:
# 1. Connect your repo
# 2. Add environment variables from .env
# 3. Deploy — it auto-detects the Dockerfile
```
