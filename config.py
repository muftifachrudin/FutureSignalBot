"""
Configuration management for the trading signals bot
"""
import os
from typing import Dict, List

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
    COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com/api"
    MEXC_BASE_URL = "https://api.mexc.com"
    
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
        required_keys = [
            "TELEGRAM_BOT_TOKEN",
            "MEXC_API_KEY", 
            "MEXC_SECRET_KEY",
            "COINGLASS_API_KEY",
            "GEMINI_API_KEY"
        ]
        
        for key in required_keys:
            if not getattr(cls, key):
                print(f"Missing required environment variable: {key}")
                return False
        return True

# Validate configuration on import
if not Config.validate():
    raise ValueError("Missing required configuration. Please check your environment variables.")
