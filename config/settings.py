"""
Configuration settings for the MEXC futures trading signals bot
"""
import os
from typing import List, Dict, Any
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class Settings:
    """Main configuration class"""
    
    # API Keys from environment variables
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    MEXC_API_KEY = os.getenv("MEXC_API_KEY", "")
    MEXC_SECRET_KEY = os.getenv("MEXC_SECRET_KEY", "")
    COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    
    # API Endpoints
    MEXC_BASE_URL = "https://api.mexc.com"
    COINGLASS_BASE_URL = "https://open-api-v4.coinglass.com/api"
    
    # Bot Configuration
    BOT_NAME = "MEXC Futures Signals Bot"
    BOT_VERSION = "1.0.0"
    BOT_DESCRIPTION = "AI-powered trading signals for MEXC futures"
    
    # Trading Configuration
    SUPPORTED_TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]
    BASE_CURRENCY = "USDT"
    TARGET_EXCHANGE = "MEXC"
    
    # Rate Limiting
    SIGNAL_COOLDOWN_SECONDS = 300  # 5 minutes between signals for same pair
    API_RATE_LIMIT_PER_MINUTE = 60
    MAX_SIGNALS_PER_USER_PER_HOUR = 20
    
    # Signal Generation Thresholds
    MIN_SIGNAL_CONFIDENCE = 0.3  # Minimum confidence to show signal
    HIGH_CONFIDENCE_THRESHOLD = 0.8  # Threshold for high confidence signals
    
    # Market Analysis Thresholds
    OI_CHANGE_THRESHOLD = 0.05  # 5% change in open interest
    FUNDING_RATE_THRESHOLD = 0.01  # 1% funding rate threshold
    LONG_SHORT_RATIO_THRESHOLD = 0.6  # 60% threshold for long/short ratio
    VOLUME_CHANGE_THRESHOLD = 0.2  # 20% volume change threshold
    VOLATILITY_HIGH_THRESHOLD = 0.7  # High volatility threshold
    VOLATILITY_LOW_THRESHOLD = 0.3  # Low volatility threshold
    
    # Timeframe Weights for Analysis
    TIMEFRAME_WEIGHTS = {
        "5m": 0.1,
        "15m": 0.15,
        "30m": 0.2,
        "1h": 0.25,
        "4h": 0.3
    }
    
    # Signal Quality Criteria
    MIN_TIMEFRAMES_ALIGNED = 3  # Minimum timeframes that should align for strong signal
    MIN_DATA_POINTS = 10  # Minimum data points needed for analysis
    
    # Risk Management
    DEFAULT_RISK_PERCENTAGE = 2.0  # Default risk per trade
    MAX_RISK_PERCENTAGE = 5.0  # Maximum risk per trade
    MIN_RISK_REWARD_RATIO = 1.5  # Minimum risk/reward ratio
    
    # Telegram Bot Settings
    MAX_MESSAGE_LENGTH = 4000  # Telegram message limit
    INLINE_KEYBOARD_MAX_BUTTONS = 8  # Max buttons per row
    
    # Cache Settings
    SIGNAL_CACHE_TTL = 300  # Signal cache time-to-live in seconds
    MARKET_DATA_CACHE_TTL = 60  # Market data cache TTL
    PAIRS_CACHE_TTL = 3600  # Supported pairs cache TTL
    
    # Performance Settings
    MAX_CONCURRENT_REQUESTS = 10
    REQUEST_TIMEOUT_SECONDS = 30
    RETRY_ATTEMPTS = 3
    RETRY_DELAY_SECONDS = 1
    
    # Gemini AI Settings
    GEMINI_MODEL = "gemini-2.5-pro"
    GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"
    GEMINI_MAX_TOKENS = 2048
    GEMINI_TEMPERATURE = 0.1  # Low temperature for consistent results
    
    # Popular Trading Pairs
    POPULAR_PAIRS = [
        "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", 
        "SOLUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT",
        "LINKUSDT", "LTCUSDT", "MATICUSDT", "AVAXUSDT"
    ]
    
    # Error Messages
    ERROR_MESSAGES = {
        "invalid_symbol": "❌ Invalid symbol format. Please use format like BTCUSDT",
        "rate_limited": "⏰ Please wait {seconds} seconds before requesting another signal",
        "api_error": "❌ API error occurred. Please try again later",
        "no_data": "❌ No market data available for this symbol",
        "analysis_failed": "❌ Failed to analyze market data. Please try again",
        "signal_generation_failed": "❌ Failed to generate signal. Please try again",
        "symbol_not_supported": "❌ Symbol not supported on MEXC",
        "insufficient_data": "❌ Insufficient market data for analysis"
    }
    
    # Success Messages
    SUCCESS_MESSAGES = {
        "signal_generated": "✅ Signal generated successfully",
        "analysis_complete": "✅ Market analysis completed",
        "data_updated": "✅ Market data updated"
    }
    
    # Feature Flags
    FEATURES = {
        "enable_ai_analysis": True,
        "enable_technical_analysis": True,
        "enable_sentiment_analysis": True,
        "enable_multi_timeframe": True,
        "enable_risk_management": True,
        "enable_performance_tracking": False,  # Disabled for now
        "enable_webhook_alerts": False,  # Future feature
        "enable_portfolio_tracking": False  # Future feature
    }
    
    # Logging Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE = os.getenv("LOG_FILE", "bot.log")
    
    @classmethod
    def validate_config(cls) -> Dict[str, bool]:
        """Validate configuration settings"""
        validation_results = {}
        
        # Check required API keys
        required_keys = [
            ("TELEGRAM_BOT_TOKEN", cls.TELEGRAM_BOT_TOKEN),
            ("MEXC_API_KEY", cls.MEXC_API_KEY),
            ("MEXC_SECRET_KEY", cls.MEXC_SECRET_KEY),
            ("COINGLASS_API_KEY", cls.COINGLASS_API_KEY),
            ("GEMINI_API_KEY", cls.GEMINI_API_KEY)
        ]
        
        for key_name, key_value in required_keys:
            validation_results[key_name] = bool(key_value and len(key_value) > 10)
        
        # Check timeframe configuration
        validation_results["timeframes_valid"] = (
            len(cls.SUPPORTED_TIMEFRAMES) > 0 and
            all(tf in ["5m", "15m", "30m", "1h", "4h", "1d", "1w"] for tf in cls.SUPPORTED_TIMEFRAMES)
        )
        
        # Check thresholds are reasonable
        validation_results["thresholds_valid"] = (
            0 < cls.MIN_SIGNAL_CONFIDENCE < 1 and
            0 < cls.HIGH_CONFIDENCE_THRESHOLD < 1 and
            cls.MIN_SIGNAL_CONFIDENCE < cls.HIGH_CONFIDENCE_THRESHOLD
        )
        
        return validation_results
    
    @classmethod
    def get_missing_config(cls) -> List[str]:
        """Get list of missing required configuration"""
        validation = cls.validate_config()
        return [key for key, valid in validation.items() if not valid]
    
    @classmethod
    def is_valid(cls) -> bool:
        """Check if configuration is valid"""
        validation = cls.validate_config()
        return all(validation.values())
    
    @classmethod
    def get_bot_info(cls) -> Dict[str, Any]:
        """Get bot information dictionary"""
        return {
            "name": cls.BOT_NAME,
            "version": cls.BOT_VERSION,
            "description": cls.BOT_DESCRIPTION,
            "supported_timeframes": cls.SUPPORTED_TIMEFRAMES,
            "base_currency": cls.BASE_CURRENCY,
            "target_exchange": cls.TARGET_EXCHANGE,
            "features": cls.FEATURES
        }

# Convenience exports
TELEGRAM_BOT_TOKEN = Settings.TELEGRAM_BOT_TOKEN
MEXC_API_KEY = Settings.MEXC_API_KEY
MEXC_SECRET_KEY = Settings.MEXC_SECRET_KEY
COINGLASS_API_KEY = Settings.COINGLASS_API_KEY
GEMINI_API_KEY = Settings.GEMINI_API_KEY

# Validate configuration on import
if not Settings.is_valid():
    missing = Settings.get_missing_config()
    print(f"⚠️ Configuration validation failed. Missing/invalid: {', '.join(missing)}")
    print("Please check your environment variables.")
    
    # Don't raise exception to allow development with partial config
    # raise ValueError(f"Invalid configuration: {missing}")

# Log configuration status
logger = logging.getLogger(__name__)
logger.info(f"Configuration loaded: {Settings.BOT_NAME} v{Settings.BOT_VERSION}")
logger.info(f"Supported timeframes: {', '.join(Settings.SUPPORTED_TIMEFRAMES)}")
logger.info(f"Target exchange: {Settings.TARGET_EXCHANGE}")

if Settings.is_valid():
    logger.info("✅ All configuration validated successfully")
else:
    logger.warning(f"⚠️ Configuration issues detected: {Settings.get_missing_config()}")
