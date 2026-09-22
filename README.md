# NESTS PDF Monitor

This bot monitors nests.tribal.gov.in for new PDFs. It checks server directly so you get PDF before it shows on website.

I made it for ESSE 2025 results because they upload PDF hours before showing link on site.

## How it works

- Checks `showfile.php?ls_id=` next IDs (1042, 1043...) - if file exists in DB before website update, we catch it
- Checks `WriteReadData/RTF1984/<timestamp>.pdf` direct folder - this is where PDF actually stored on server
- Sends telegram message with PDF file as soon as found

## Setup

1. Create telegram bot:
   - Talk to @BotFather on telegram, /newbot, get token
   - Send message to your bot, then get chat id from @userinfobot

2. Set env vars:
```
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

3. Run:
```
pip install -r requirements.txt
python bot.py --loop
```

For free cloud hosting:

**Render.com (best, checks every 5-15 sec):**
- Push to github
- New Background Worker on render.com
- Build: pip install -r requirements.txt
- Start: python bot.py --loop
- Add env vars token and chat id

**Github Actions (checks every 2 min):**
- Add secrets TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in repo settings -> secrets
- Workflow will run automatically

## Files

- bot.py - main bot
- requirements.txt

Tested with previous PDFs like 1789749299.pdf etc - works.

Made for ESSE 2025.
