# FutureSignalBot

MEXC Futures Trading Signals Telegram Bot with multi-source data and optional AI analysis.

## Setup

1. Create a virtual environment (already auto-configured if using VS Code).
2. Install deps (managed by pyproject.toml).
3. Copy `.env.example` to `.env` and fill values:
   - TELEGRAM_BOT_TOKEN (required)
   - MEXC_API_KEY, MEXC_SECRET_KEY (optional)
   - COINGLASS_API_KEY (optional)
   - GEMINI_API_KEY (optional)

## Run

- Quick run:

```powershell
# From project root
& .\.venv\Scripts\python.exe .\main.py
```

The bot uses python-telegram-bot v22 run_polling and will block the terminal until stopped (Ctrl+C).

## Notes

- If optional keys are missing, bot still runs with reduced features.
- Ensure `telegram` package is NOT installed alongside python-telegram-bot (we removed it).
- For Windows PowerShell, use the provided command format.
