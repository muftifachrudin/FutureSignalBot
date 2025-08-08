"""
Configuration management for the trading signals bot
"""
import os

# Optional: load environment variables from a .env file if present
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

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
        return ok

# Validate configuration on import
if not Config.validate():
    # Fail fast only if Telegram token is missing; otherwise continue with reduced features.
    raise ValueError("Missing TELEGRAM_BOT_TOKEN. Please set it and restart.")
