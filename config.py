"""
Configuration management for the trading signals bot
"""
import os
from pathlib import Path

def _safe_load_dotenv():
    """Attempt to load a .env file if python-dotenv is available.
    We try common locations explicitly instead of relying only on CWD.
    """
    try:  # optional dependency
        from dotenv import load_dotenv  # type: ignore
    except Exception:  # library not installed
        return

    # Candidate .env paths (order matters: app root, /opt path, current wd)
    candidates = [
        Path(__file__).parent / ".env",
        Path("/opt/futuresignalbot/.env"),
        Path.cwd() / ".env",
    ]
    for p in candidates:
        if p.is_file():
            load_dotenv(p, override=False)


def _manual_env_fallback():
    """Manually parse env files if TELEGRAM_BOT_TOKEN still missing.

    This handles edge cases where:
      * systemd EnvironmentFile not applied (format / encoding issues)
      * BOM (UTF-8 with signature) at start of file name token
      * CRLF line endings not stripped
    """
    if os.getenv("TELEGRAM_BOT_TOKEN"):
        return
    candidate_files = [
        "/etc/futuresignalbot.env",
        "/opt/futuresignalbot/.env",
        str(Path(__file__).parent / ".env"),
    ]
    for path in candidate_files:
        try:
            p = Path(path)
            if not p.is_file():
                continue
            with p.open("r", encoding="utf-8-sig") as fh:  # utf-8-sig strips BOM
                for raw in fh:
                    line = raw.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if not k:
                        continue
                    # Do not override an existing explicit environment value
                    if k not in os.environ:
                        os.environ[k] = v
        except Exception:
            # Silent: resilience objective; we don't want import-time crashes.
            continue


# Load dotenv first, then manual fallback for robustness
_safe_load_dotenv()
_manual_env_fallback()

class Config:
    """Configuration class for bot settings and API keys"""
    
    # API Keys from environment variables
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    MEXC_API_KEY = os.getenv("MEXC_API_KEY", "")
    MEXC_SECRET_KEY = os.getenv("MEXC_SECRET_KEY", "")
    COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # Trading settings
    SUPPORTED_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]
    BASE_CURRENCY = "USDT"
    TARGET_EXCHANGE = "MEXC"
    
    # API endpoints
    # Coinglass v4 base URL (no trailing /api)
    COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com"
    MEXC_BASE_URL = "https://api.mexc.fm"
    # MEXC Futures (Contract) public API base
    MEXC_CONTRACT_BASE_URL = "https://contract.mexc.fm"
    
    # Rate limiting settings
    MAX_REQUESTS_PER_MINUTE = 60
    SIGNAL_COOLDOWN_SECONDS = 300  # 5 minutes between signals for same pair
    
    # Signal criteria thresholds
    OI_CHANGE_THRESHOLD = 0.05  # 5% change in open interest
    FUNDING_RATE_THRESHOLD = 0.01  # 1% funding rate threshold
    RATIO_THRESHOLD = 0.6  # 60% threshold for long/short ratio

    # Admin / authorization (comma-separated TELEGRAM user IDs)
    ADMIN_USER_IDS_STR = os.getenv("ADMIN_USER_IDS", "")
    try:
        ADMIN_USER_IDS = [int(x.strip()) for x in ADMIN_USER_IDS_STR.split(",") if x.strip().isdigit()]
    except Exception:
        ADMIN_USER_IDS = []  # type: ignore

    # Custom path for pairs watchlist file (optional)
    PAIRS_WATCHLIST_PATH = os.getenv("PAIRS_WATCHLIST_PATH", "")
    
    @classmethod
    def validate(cls) -> bool:
        """Validate that all required API keys are present"""
        # Only Telegram token is strictly required to run the bot.
        ok = True
        if not getattr(cls, "TELEGRAM_BOT_TOKEN"):
            print("Missing required environment variable: TELEGRAM_BOT_TOKEN")
            ok = False
        # Warn for optional keys
        optional = ["MEXC_API_KEY", "MEXC_SECRET_KEY", "COINGLASS_API_KEY", "GEMINI_API_KEY"]
        missing_optional = [k for k in optional if not getattr(cls, k)]
        if missing_optional:
            print(f"Warning: Missing optional environment variables: {', '.join(missing_optional)}")
            print("Some features may be limited (e.g., AI analysis or extended market data).")
        if not cls.ADMIN_USER_IDS:
            print("Info: ADMIN_USER_IDS not set; /pairs add/remove restricted (disabled). Set ADMIN_USER_IDS env to enable.")
        return ok

# Validate configuration on import
if not Config.validate():
    # Fail fast only if Telegram token is missing; otherwise continue with reduced features.
    raise ValueError("Missing TELEGRAM_BOT_TOKEN. Please set it and restart.")
