# Overview

This is a comprehensive Telegram bot for MEXC futures trading signals that leverages AI and multiple data sources to generate trading recommendations. The bot integrates Telegram Bot API, MEXC Exchange API, Coinglass market sentiment data, and Gemini AI analysis to provide users with intelligent trading signals across multiple timeframes (5m, 15m, 30m, 1h, 4h).

The system performs multi-timeframe technical analysis, incorporates market sentiment indicators like open interest and funding rates, and uses Gemini AI to generate structured trading signals with confidence levels, entry/exit points, and risk assessments.

## Current Status

✅ **COMPLETED**: The bot is fully functional and running successfully!

**Bot Features Implemented:**
- Multi-timeframe technical analysis (5m, 15m, 30m, 1h, 4h)
- MEXC Exchange API integration for real-time price data
- Coinglass API integration for market sentiment data (open interest, funding rates, long/short ratios)
- Gemini AI analysis for intelligent signal generation
- Interactive Telegram bot with command handlers
- Signal generation with confidence levels and risk assessment
- Rate limiting to prevent spam (5-minute cooldown per symbol)

**Available Commands:**
- `/start` - Welcome message and bot introduction
- `/signal <SYMBOL>` - Get trading signal for a specific symbol (e.g., `/signal BTCUSDT`)
- `/analyze <SYMBOL>` - Get detailed market analysis
- `/pairs` - View supported trading pairs
- `/timeframes` - Show analyzed timeframes
- `/help` - Detailed help guide
- `/about` - Bot information and disclaimers

**Signal Logic:**
- **LONG**: Multiple timeframes bullish + positive funding rates + high short ratio + rising open interest
- **SHORT**: Multiple timeframes bearish + negative funding rates + high long ratio + declining open interest  
- **WAIT**: Mixed or unclear market conditions

**Enhanced Signal Display:**
- Comprehensive market statistics with K-line data for all timeframes
- Detailed price data including 24h changes and volume
- Market sentiment indicators (funding rates, open interest, long/short ratios)
- Professional formatting with emojis and clear data presentation
- Real-time data from MEXC and Coinglass APIs

**Recent Improvements (2025-08-08):**
- ✅ **Completely resolved API connectivity issues** - Implemented robust signal generator v2
- ✅ **MEXC ticker data fully functional** - Getting real-time price data for all symbols
- ✅ **Coinglass market data operational** - Successfully fetching 30+ market entries per symbol 
- ✅ **Gemini AI analysis working perfectly** - Generating intelligent signal analysis
- ✅ **Enhanced signal generation logic** - Multi-criteria analysis using available data sources
- ✅ **Improved error handling and fallback systems** - Bot continues working even with partial data
- ✅ **Rate limiting operational** - 5-minute cooldown prevents spam, confirmed in logs
- ✅ **Signal confidence scoring** - Dynamic confidence based on multiple market factors
- ✅ **Comprehensive market analysis** - Price action, sentiment, and momentum analysis

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Bot Framework
- **Core Application**: Python-based Telegram bot using `python-telegram-bot` library
- **Async Architecture**: Built with asyncio for handling multiple API calls concurrently
- **Context Managers**: Proper resource management with async context managers for API clients
- **Message Handling**: Command handlers for `/start`, `/signal`, `/analyze`, and callback query handlers for inline keyboards

## API Integration Layer
- **MEXC Client**: Handles futures trading data with HMAC-SHA256 signed requests
- **Coinglass Client**: Fetches market sentiment data including open interest, funding rates, and long/short ratios
- **Gemini AI Analyzer**: Uses Google's Gemini 2.5 models for market analysis and signal generation
- **Rate Limiting**: Built-in cooldown mechanisms (5-minute intervals between signals per symbol)

## Data Processing Pipeline
- **Signal Generator**: Central orchestrator that combines data from all sources
- **Multi-timeframe Analysis**: Analyzes price action across 5 different timeframes
- **Threshold-based Filtering**: Applies configurable thresholds for OI changes (5%), funding rates (1%), and long/short ratios (60%)
- **Signal Caching**: Prevents spam by caching recent signals per symbol

## Data Models
- **Pydantic Models**: Structured data validation using Pydantic for signal responses
- **Enum Classifications**: Type-safe enums for signal types (LONG/SHORT/WAIT), risk levels, and trend directions
- **Nested Structures**: Complex models for market analysis with technical levels and sentiment indicators

## Configuration Management
- **Environment Variables**: All API keys and sensitive data stored as environment variables
- **Centralized Config**: Single configuration class with validation methods
- **Flexible Thresholds**: Adjustable parameters for signal generation criteria

# External Dependencies

## Trading APIs
- **MEXC Exchange API**: Real-time futures trading data, price history, and market information
- **Coinglass API**: Market sentiment analytics including open interest, funding rates, and trader positioning data

## AI Services
- **Google Gemini AI**: Uses `google-genai` SDK with Gemini 2.5 models for market analysis and structured signal generation
- **Structured Outputs**: JSON response formatting with Pydantic model validation

## Messaging Platform
- **Telegram Bot API**: User interaction, command handling, and message delivery
- **Inline Keyboards**: Interactive buttons for enhanced user experience

## Python Packages
- **Core**: `asyncio`, `aiohttp`, `telegram`, `pydantic`
- **Security**: `hmac`, `hashlib` for API signature generation
- **AI**: `google-genai` for Gemini AI integration
- **Utilities**: `logging`, `json`, `time` for system operations

## Infrastructure Requirements
- **Environment Variables**: Secure storage for 5+ API keys (Telegram, MEXC, Coinglass, Gemini)
- **Network Access**: HTTPS connectivity to multiple external APIs
- **Memory Management**: Efficient session handling for concurrent API connections