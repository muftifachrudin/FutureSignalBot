"""
Gemini AI Analysis Service for Trading Signals
"""

import json
import logging
import os
from typing import Dict, List, Any
from google import genai
from google.genai import types
from pydantic import BaseModel
from models.signal_models import TradingSignal, SignalType

logger = logging.getLogger(__name__)


class MarketAnalysis(BaseModel):
    signal_type: str  # "LONG", "SHORT", or "WAIT"
    confidence: float  # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    # thoughts
This is a comprehensive Telegram bot for MEXC futures trading signals that needs to integrate multiple APIs (Telegram, MEXC, Coinglass, Gemini AI) and perform multi-timeframe analysis. The bot will analyze market data across 5 timeframes (5m, 15m, 30m, 1h, 4h) and use various indicators like open interest, funding rates, and long/short ratios to generate trading signals. The Gemini AI will process all this data to provide intelligent signal recommendations.

Key components needed:
1. Main bot application with Telegram integration
2. MEXC API client for trading data
3. Coinglass API client for market sentiment data
4. Gemini AI integration for signal analysis
5. Signal generation logic based on multi-timeframe analysis
6. Configuration management for API keys
7. Utility functions for data processing

The bot will provide interactive commands for users to request signals and will use real-time data from both MEXC and Coinglass APIs.

# useful_guidelines_from_blueprints
- Use the newest Gemini model series "gemini-2.5-flash" or "gemini-2.5-pro"
- The API key is from Gemini Developer API Key, not vertex AI API Key
- Use the google-genai SDK (renamed from google-generativeai)
- Use proper JSON response formatting with Pydantic models for structured outputs
- Handle exceptions properly when calling Gemini API

# directory_structure
```json
[
    {"path": "main.py", "status": "new"},
    {"path": "bot.py", "status": "new"},
    {"path": "mexc_client.py", "status": "new"},
    {"path": "coinglass_client.py", "status": "new"},
    {"path": "gemini_analyzer.py", "status": "new"},
    {"path": "signal_generator.py", "status": "new"},
    {"path": "config.py", "status": "new"},
    {"path": "utils.py", "status": "new"}
]
