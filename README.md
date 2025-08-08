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

## Deploy (Azure Container Apps + GitHub Actions)

1. Prerequisites

- Azure subscription (Student access works)
- Azure Container Registry (ACR)
- Azure Container Apps environment (ACA)

2. Repo Secrets (Settings → Secrets and variables → Actions)

- AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_SUBSCRIPTION_ID (for OIDC login)
- ACR_USERNAME, ACR_PASSWORD (or use ACR admin enabled)
- TELEGRAM_BOT_TOKEN (required)
- MEXC_API_KEY, MEXC_SECRET_KEY (optional)
- COINGLASS_API_KEY (optional)
- GEMINI_API_KEY (optional)

3. Repo Variables (Settings → Secrets and variables → Actions → Variables)

- ACR_LOGIN_SERVER (e.g. myregistry.azurecr.io)
- AZURE_RESOURCE_GROUP (e.g. fsb-rg)
- ACA_ENV_NAME (your Container Apps environment name)
- ACA_APP_NAME (app name, e.g. futuresignalbot)

4. On push to main, GitHub Actions builds Docker, pushes to ACR, and deploys to ACA.

Container receives config via environment variables (no .env inside image).

## Notes

- If optional keys are missing, bot still runs with reduced features.
- Ensure `telegram` package is NOT installed alongside python-telegram-bot (we removed it).
- For Windows PowerShell, use the provided command format.
