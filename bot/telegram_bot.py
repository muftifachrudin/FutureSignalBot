"""
Telegram Bot for MEXC Futures Trading Signals
"""

import asyncio
import logging
from typing import List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from services.mexc_api import MexcAPI
from services.coinglass_api import CoinglassAPI
from services.gemini_analyzer import GeminiAnalyzer
from models.signal_models import TradingSignal, SignalType
from utils.helpers import format_signal_message
from config.settings import (
    TELEGRAM_BOT_TOKEN, MEXC_API_KEY, MEXC_SECRET_KEY,
    COINGLASS_API_KEY, GEMINI_API_KEY
)

logger = logging.getLogger(__name__)


class TradingSignalsBot:
    def __init__(self):
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.mexc_api = MexcAPI(MEXC_API_KEY, MEXC_SECRET_KEY)
        self.coinglass_api = CoinglassAPI(COINGLASS_API_KEY)
        self.gemini_analyzer = GeminiAnalyzer(GEMINI_API_KEY)
        self.setup_handlers()

    def setup_handlers(self):
        """Setup command and callback handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("signal", self.signal_command))
        self.application.add_handler(CommandHandler("analyze", self.analyze_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = (
            "🤖 **MEXC Futures Trading Signals Bot** 🚀\n\n"
            "Welcome! I provide AI-powered trading signals for MEXC futures using:\n"
            "• Multi-timeframe analysis (5m, 15m, 30m, 1h, 4h)\n"
            "• Coinglass market data\n"
            "• Gemini AI analysis\n\n"
            "**Available Commands:**\n"
            "/signal <symbol> - Get trading signal for a symbol (e.g., /signal BTCUSDT)\n"
            "/analyze <symbol> - Get detailed analysis\n"
            "/help - Show this help message\n\n"
            "Example: `/signal BTCUSDT`"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = (
            "📚 **Help - How to use this bot:**\n\n"
            "**Commands:**\n"
            "• `/signal <SYMBOL>` - Get trading signal\n"
            "• `/analyze <SYMBOL>` - Get detailed market analysis\n\n"
            "**Supported Symbols:**\n"
            "All USDT pairs available on MEXC (e.g., BTCUSDT, ETHUSDT, ADAUSDT)\n\n"
            "**Signal Types:**\n"
            "🟢 **LONG** - Buy signal with entry recommendation\n"
            "🔴 **SHORT** - Sell signal with entry recommendation\n"
            "⚪ **WAIT** - Wait and see, market conditions unclear\n\n"
            "**Analysis Factors:**\n"
            "• Price movements across 5 timeframes\n"
            "• Open Interest trends\n"
            "• Funding rates\n"
            "• Long/Short ratios\n"
            "• AI-powered market sentiment\n\n"
            "For support, contact the bot administrator."
        )
        await update.message.reply_text(help_message, parse_mode='Markdown')

    async def signal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signal command"""
        if not context.args:
            await update.message.reply_text(
                "Please provide a symbol. Example: `/signal BTCUSDT`",
                parse_mode='Markdown'
            )
            return

        symbol = context.args[0].upper()
        
        # Send processing message
        processing_msg = await update.message.reply_text("🔄 Analyzing market data... Please wait.")

        try:
            # Generate signal
            signal = await self.generate_signal(symbol)
            
            # Format and send signal
            message = format_signal_message(signal)
            keyboard = self.get_signal_keyboard(symbol)
            
            await processing_msg.edit_text(
                message,
                parse_mode='Markdown',
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            await processing_msg.edit_text(
                f"❌ Error analyzing {symbol}: {str(e)}\n"
                "Please check if the symbol is valid and try again."
            )

    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command for detailed analysis"""
        if not context.args:
            await update.message.reply_text(
                "Please provide a symbol. Example: `/analyze BTCUSDT`",
                parse_mode='Markdown'
            )
            return

        symbol = context.args[0].upper()
        
        processing_msg = await update.message.reply_text("🔍 Generating detailed analysis... Please wait.")

        try:
            # Get comprehensive market data
            timeframes = ['5m', '15m', '30m', '1h', '4h']
            market_data = {}
            
            for tf in timeframes:
                mexc_data = await self.mexc_api.get_kline_data(symbol, tf, limit=50)
                coinglass_data = await self.coinglass_api.get_market_data(symbol, tf)
                market_data[tf] = {
                    'mexc': mexc_data,
                    'coinglass': coinglass_data
                }

            # Generate detailed analysis
            detailed_analysis = await self.gemini_analyzer.generate_detailed_analysis(
                symbol, market_data
            )

            await processing_msg.edit_text(
                detailed_analysis,
                parse_mode='Markdown'
            )

        except Exception as e:
            logger.error(f"Error generating detailed analysis for {symbol}: {e}")
            await processing_msg.edit_text(
                f"❌ Error analyzing {symbol}: {str(e)}\n"
                "Please check if the symbol is valid and try again."
            )

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        query = update.callback_query
        await query.answer()

        if query.data.startswith("refresh_"):
            symbol = query.data.split("_")[1]
            
            try:
                signal = await self.generate_signal(symbol)
                message = format_signal_message(signal)
                keyboard = self.get_signal_keyboard(symbol)
                
                await query.edit_message_text(
                    message,
                    parse_mode='Markdown',
                    reply_markup=keyboard
                )
            except Exception as e:
                await query.edit_message_text(f"❌ Error refreshing signal: {str(e)}")

    async def generate_signal(self, symbol: str) -> TradingSignal:
        """Generate trading signal for a symbol"""
        try:
            # Get data from multiple timeframes
            timeframes = ['5m', '15m', '30m', '1h', '4h']
            timeframe_data = {}
            
            # Collect MEXC data
            for tf in timeframes:
                mexc_data = await self.mexc_api.get_kline_data(symbol, tf, limit=20)
                timeframe_data[tf] = mexc_data

            # Get Coinglass market sentiment data
            open_interest = await self.coinglass_api.get_open_interest(symbol)
            funding_rate = await self.coinglass_api.get_funding_rate(symbol)
            long_short_ratio = await self.coinglass_api.get_long_short_ratio(symbol)

            # Analyze with Gemini AI
            signal = await self.gemini_analyzer.analyze_signal(
                symbol=symbol,
                timeframe_data=timeframe_data,
                open_interest=open_interest,
                funding_rate=funding_rate,
                long_short_ratio=long_short_ratio
            )

            return signal

        except Exception as e:
            logger.error(f"Error generating signal for {symbol}: {e}")
            raise

    def get_signal_keyboard(self, symbol: str) -> InlineKeyboardMarkup:
        """Get inline keyboard for signal messages"""
        keyboard = [
            [InlineKeyboardButton(f"🔄 Refresh {symbol}", callback_data=f"refresh_{symbol}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def start(self):
        """Start the bot"""
        logger.info("Starting MEXC Trading Signals Bot...")
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        logger.info("Bot started successfully!")
        
        # Keep the bot running
        try:
            await self.application.updater.idle()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        finally:
            await self.application.stop()
