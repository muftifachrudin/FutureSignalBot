"""
Telegram bot implementation for trading signals
"""
import asyncio
import logging
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from signal_generator import SignalGenerator
from config import Config
from utils import (
    format_signal_message, format_market_analysis, format_pairs_list,
    validate_symbol, format_error_message, get_timeframe_display, truncate_text
)
from config import Config

logger = logging.getLogger(__name__)

class TradingSignalBot:
    """Main Telegram bot class"""
    
    def __init__(self):
        self.token = Config.TELEGRAM_BOT_TOKEN
        self.signal_generator = None
        self.application = None
        self.user_sessions = {}  # Track user sessions
    
    async def start(self):
        """Start the bot"""
        try:
            # Initialize signal generator
            self.signal_generator = SignalGenerator()
            await self.signal_generator.__aenter__()
            
            # Create application
            self.application = Application.builder().token(self.token).build()
            
            # Add handlers
            self._add_handlers()
            
            # Start the bot
            logger.info("Starting Telegram bot...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Keep running
            logger.info("Bot started successfully!")
            
            # Keep the bot running
            import asyncio
            await asyncio.Future()  # Run forever
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
        finally:
            # Cleanup
            if self.signal_generator:
                await self.signal_generator.__aexit__(None, None, None)
    
    def _add_handlers(self):
        """Add command and callback handlers"""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("signal", self.signal_command))
        self.application.add_handler(CommandHandler("analyze", self.analyze_command))
        self.application.add_handler(CommandHandler("pairs", self.pairs_command))
        self.application.add_handler(CommandHandler("timeframes", self.timeframes_command))
        self.application.add_handler(CommandHandler("about", self.about_command))
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Message handler for direct symbol input
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_symbol_message))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_message = """
🤖 **Welcome to MEXC Futures Trading Signals Bot!**

This bot provides AI-powered trading signals for MEXC futures using:
• 📊 Multi-timeframe analysis (5m, 15m, 30m, 1h, 4h)  
• 📈 Coinglass market data
• 🤖 Gemini AI analysis
• 💹 MEXC exchange data

**Available Commands:**
• `/signal <SYMBOL>` - Get trading signal
• `/analyze <SYMBOL>` - Get market analysis  
• `/pairs` - View supported pairs
• `/timeframes` - View analyzed timeframes
• `/help` - Show detailed help
• `/about` - About this bot

**Example Usage:**
• `/signal BTCUSDT` - Get BTC signal
• `/analyze ETHUSDT` - Analyze ETH market

⚠️ **Disclaimer:** This bot provides educational signals only. Always do your own research and manage risk appropriately.
"""
        
        keyboard = [
            [InlineKeyboardButton("📊 Popular Pairs", callback_data="popular_pairs")],
            [InlineKeyboardButton("📈 Get Signal", callback_data="get_signal"), 
             InlineKeyboardButton("🔍 Market Analysis", callback_data="market_analysis")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_message = """
📚 **Detailed Help Guide**

**🎯 Signal Commands:**
• `/signal BTCUSDT` - Get trading signal for Bitcoin
• `/signal ETH` - Get signal (USDT automatically added)

**📊 Analysis Commands:**  
• `/analyze BTCUSDT` - Get detailed market analysis
• `/pairs` - List all supported trading pairs
• `/timeframes` - Show analyzed timeframes

**🤖 Signal Types:**
• 🟢 **LONG** - Buy signal with bullish conditions
• 🔴 **SHORT** - Sell signal with bearish conditions  
• 🟡 **WAIT** - Hold/wait signal for unclear conditions

**📈 Analysis Factors:**
• Price trends across 5 timeframes
• Open interest changes
• Funding rates
• Long/short position ratios
• Volume confirmation
• Support/resistance levels

**⚠️ Risk Management:**
• Always use stop losses
• Position size appropriately
• Don't risk more than you can afford
• Signals are educational only

**🔄 Rate Limits:**
• 5-minute cooldown between signals for same pair
• This prevents spam and ensures quality analysis

**💡 Tips:**
• Use signals as part of broader analysis
• Combine with your own research
• Monitor multiple timeframes
• Follow risk management rules
"""
        
        await update.message.reply_text(help_message, parse_mode='Markdown')
    
    async def signal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /signal command"""
        try:
            # Get symbol from command arguments
            if not context.args:
                await update.message.reply_text(
                    "❌ Please provide a trading symbol.\n\n**Usage:** `/signal BTCUSDT`",
                    parse_mode='Markdown'
                )
                return
            
            symbol = validate_symbol(context.args[0])
            
            # Show processing message
            processing_msg = await update.message.reply_text(
                f"🔄 **Analyzing {symbol}...**\n\nGathering data from multiple sources...",
                parse_mode='Markdown'
            )
            
            # Generate signal
            signal = await self.signal_generator.generate_signal(symbol)
            
            if signal:
                # Format and send signal
                message = format_signal_message(symbol, signal.dict())
                message += f"\n\n{get_timeframe_display()}"
                
                # Add action buttons
                keyboard = [
                    [InlineKeyboardButton("🔄 Refresh Signal", callback_data=f"refresh_signal_{symbol}")],
                    [InlineKeyboardButton("📊 Market Analysis", callback_data=f"analyze_{symbol}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(truncate_text(message), reply_markup=reply_markup, parse_mode='Markdown')
            else:
                error_msg = format_error_message("Failed to generate signal. Please try again later.", symbol)
                await processing_msg.edit_text(error_msg, parse_mode='Markdown')
                
        except ValueError as e:
            await update.message.reply_text(format_error_message(str(e)), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in signal command: {e}")
            await update.message.reply_text(
                format_error_message("An unexpected error occurred.", context.args[0] if context.args else None),
                parse_mode='Markdown'
            )
    
    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analyze command"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Please provide a trading symbol.\n\n**Usage:** `/analyze BTCUSDT`",
                    parse_mode='Markdown'
                )
                return
            
            symbol = validate_symbol(context.args[0])
            
            # Show processing message
            processing_msg = await update.message.reply_text(
                f"🔍 **Analyzing market conditions for {symbol}...**",
                parse_mode='Markdown'
            )
            
            # Get market explanation
            analysis = await self.signal_generator.get_market_explanation(symbol)
            
            if analysis:
                message = format_market_analysis(symbol, analysis)
                
                # Add action buttons
                keyboard = [
                    [InlineKeyboardButton("🎯 Get Signal", callback_data=f"signal_{symbol}")],
                    [InlineKeyboardButton("🔄 Refresh Analysis", callback_data=f"analyze_{symbol}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(truncate_text(message), reply_markup=reply_markup, parse_mode='Markdown')
            else:
                error_msg = format_error_message("Failed to analyze market conditions.", symbol)
                await processing_msg.edit_text(error_msg, parse_mode='Markdown')
                
        except ValueError as e:
            await update.message.reply_text(format_error_message(str(e)), parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error in analyze command: {e}")
            await update.message.reply_text(
                format_error_message("An unexpected error occurred.", context.args[0] if context.args else None),
                parse_mode='Markdown'
            )
    
    async def pairs_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pairs command"""
        try:
            processing_msg = await update.message.reply_text("🔄 **Loading supported pairs...**", parse_mode='Markdown')
            
            pairs = await self.signal_generator.get_supported_pairs()
            
            if pairs:
                message = format_pairs_list(pairs)
                
                # Add navigation buttons for pagination if needed
                keyboard = [
                    [InlineKeyboardButton("🎯 Get Signal", callback_data="get_signal_input")],
                    [InlineKeyboardButton("🔄 Refresh List", callback_data="refresh_pairs")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await processing_msg.edit_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            else:
                error_msg = format_error_message("Failed to load supported pairs.")
                await processing_msg.edit_text(error_msg, parse_mode='Markdown')
                
        except Exception as e:
            logger.error(f"Error in pairs command: {e}")
            await update.message.reply_text(
                format_error_message("An unexpected error occurred while loading pairs."),
                parse_mode='Markdown'
            )
    
    async def timeframes_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /timeframes command"""
        message = f"""
⏰ **Analyzed Timeframes**

This bot analyzes the following timeframes for comprehensive market analysis:

• **5 minutes** - Short-term scalping signals
• **15 minutes** - Quick swing opportunities  
• **30 minutes** - Medium-term trends
• **1 hour** - Hourly trend confirmation
• **4 hours** - Major trend direction

**How it works:**
🔍 Each timeframe is analyzed for trend direction
📊 Signals are generated when multiple timeframes align
⚖️ Higher timeframe trends have more weight
🎯 Best signals occur when all timeframes agree

{get_timeframe_display()}

**Signal Quality:**
• 🟢 **High**: 4-5 timeframes aligned
• 🟡 **Medium**: 3 timeframes aligned  
• 🔴 **Low**: 2 or fewer aligned
"""
        
        keyboard = [
            [InlineKeyboardButton("🎯 Get Signal", callback_data="get_signal_input")],
            [InlineKeyboardButton("📊 Popular Pairs", callback_data="popular_pairs")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def about_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /about command"""
        about_message = """
🤖 **MEXC Futures Trading Signals Bot**

**🔧 Technology Stack:**
• 🤖 Gemini AI for intelligent analysis
• 📊 Coinglass API for market sentiment
• 💹 MEXC API for trading data
• ⚡ Real-time multi-timeframe analysis

**📈 Data Sources:**
• Price action across 5 timeframes
• Open interest changes
• Funding rates
• Long/short position ratios
• Volume and volatility metrics
• Support/resistance levels

**🎯 Signal Logic:**
• **LONG**: Bullish alignment + positive funding + high short ratio + rising OI
• **SHORT**: Bearish alignment + negative funding + high long ratio + declining OI  
• **WAIT**: Mixed signals or unclear market conditions

**⚠️ Important Disclaimers:**
• Signals are for educational purposes only
• Past performance doesn't guarantee future results
• Always use proper risk management
• Never invest more than you can afford to lose
• This is not financial advice

**🔒 Security:**
• No trading permissions required
• Read-only market data access
• Secure API key management
• No personal data stored

**📧 Support:**
For technical issues or questions, please contact support.

**Version:** 1.0.0
**Last Updated:** 2025
"""
        
        await update.message.reply_text(about_message, parse_mode='Markdown')
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button callbacks"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        try:
            if data == "popular_pairs":
                await self._handle_popular_pairs(query)
            elif data == "get_signal":
                await self._handle_get_signal_prompt(query)
            elif data == "market_analysis":
                await self._handle_market_analysis_prompt(query)
            elif data == "help":
                await self._handle_help_callback(query)
            elif data.startswith("signal_"):
                symbol = data.split("_", 1)[1]
                await self._handle_signal_callback(query, symbol)
            elif data.startswith("analyze_"):
                symbol = data.split("_", 1)[1]
                await self._handle_analyze_callback(query, symbol)
            elif data.startswith("refresh_signal_"):
                symbol = data.split("_", 2)[2]
                await self._handle_refresh_signal(query, symbol)
            elif data == "refresh_pairs":
                await self._handle_refresh_pairs(query)
            else:
                await query.edit_message_text("❌ Unknown action.")
                
        except Exception as e:
            logger.error(f"Error handling callback {data}: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again.")
    
    async def handle_symbol_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle direct symbol messages"""
        try:
            symbol = validate_symbol(update.message.text)
            
            # Create quick action buttons
            keyboard = [
                [InlineKeyboardButton("🎯 Get Signal", callback_data=f"signal_{symbol}")],
                [InlineKeyboardButton("📊 Market Analysis", callback_data=f"analyze_{symbol}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"📈 **{symbol}** - What would you like to do?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid symbol format. Please use format like `BTCUSDT` or `/help` for assistance.",
                parse_mode='Markdown'
            )
    
    async def _handle_popular_pairs(self, query):
        """Handle popular pairs button"""
        popular_pairs = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "SOLUSDT", "DOGEUSDT", "XRPUSDT", "DOTUSDT"]
        
        message = "🔥 **Popular Trading Pairs**\n\nSelect a pair to get signals:\n\n"
        
        keyboard = []
        for i in range(0, len(popular_pairs), 2):
            row = []
            for j in range(2):
                if i + j < len(popular_pairs):
                    pair = popular_pairs[i + j]
                    row.append(InlineKeyboardButton(pair, callback_data=f"signal_{pair}"))
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton("📋 All Pairs", callback_data="refresh_pairs")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_get_signal_prompt(self, query):
        """Handle get signal prompt"""
        message = """
🎯 **Get Trading Signal**

Send me a trading symbol to get AI-powered analysis:

**Examples:**
• `BTCUSDT` or just `BTC`
• `ETHUSDT` or just `ETH`  
• `ADAUSDT` or just `ADA`

Or use: `/signal SYMBOL`
"""
        
        keyboard = [[InlineKeyboardButton("🔥 Popular Pairs", callback_data="popular_pairs")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_market_analysis_prompt(self, query):
        """Handle market analysis prompt"""
        message = """
📊 **Market Analysis**

Send me a trading symbol for detailed market analysis:

**Examples:**
• `BTCUSDT` - Bitcoin analysis
• `ETHUSDT` - Ethereum analysis
• `BNBUSDT` - Binance Coin analysis

Or use: `/analyze SYMBOL`
"""
        
        keyboard = [[InlineKeyboardButton("🔥 Popular Pairs", callback_data="popular_pairs")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_help_callback(self, query):
        """Handle help button callback"""
        help_message = """
📚 **Quick Help**

**Commands:**
• `/signal BTCUSDT` - Get trading signal
• `/analyze ETHUSDT` - Market analysis
• `/pairs` - Supported pairs
• `/help` - Detailed help

**Signal Types:**
• 🟢 LONG - Buy signal
• 🔴 SHORT - Sell signal  
• 🟡 WAIT - Hold position

**Usage Tips:**
• Signals update every 5 minutes
• Use with proper risk management
• Educational purposes only

**More help:** `/help`
"""
        
        keyboard = [
            [InlineKeyboardButton("🎯 Get Signal", callback_data="get_signal")],
            [InlineKeyboardButton("📊 Analysis", callback_data="market_analysis")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(help_message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def _handle_signal_callback(self, query, symbol: str):
        """Handle signal callback for specific symbol"""
        await query.edit_message_text(
            f"🔄 **Generating signal for {symbol}...**\n\nAnalyzing market data...",
            parse_mode='Markdown'
        )
        
        signal = await self.signal_generator.generate_signal(symbol)
        
        if signal:
            message = format_signal_message(symbol, signal.dict())
            message += f"\n\n{get_timeframe_display()}"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analysis", callback_data=f"analyze_{symbol}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(truncate_text(message), reply_markup=reply_markup, parse_mode='Markdown')
        else:
            error_msg = format_error_message("Failed to generate signal.", symbol)
            await query.edit_message_text(error_msg, parse_mode='Markdown')
    
    async def _handle_analyze_callback(self, query, symbol: str):
        """Handle analyze callback for specific symbol"""
        await query.edit_message_text(
            f"🔍 **Analyzing {symbol}...**\n\nGathering market data...",
            parse_mode='Markdown'
        )
        
        analysis = await self.signal_generator.get_market_explanation(symbol)
        
        if analysis:
            message = format_market_analysis(symbol, analysis)
            
            keyboard = [
                [InlineKeyboardButton("🎯 Get Signal", callback_data=f"signal_{symbol}")],
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"analyze_{symbol}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(truncate_text(message), reply_markup=reply_markup, parse_mode='Markdown')
        else:
            error_msg = format_error_message("Failed to analyze market.", symbol)
            await query.edit_message_text(error_msg, parse_mode='Markdown')
    
    async def _handle_refresh_signal(self, query, symbol: str):
        """Handle refresh signal callback"""
        await query.edit_message_text(
            f"🔄 **Refreshing signal for {symbol}...**",
            parse_mode='Markdown'
        )
        
        signal = await self.signal_generator.generate_signal(symbol, force=True)
        
        if signal:
            message = format_signal_message(symbol, signal.dict())
            message += f"\n\n{get_timeframe_display()}"
            
            keyboard = [
                [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_signal_{symbol}")],
                [InlineKeyboardButton("📊 Analysis", callback_data=f"analyze_{symbol}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(truncate_text(message), reply_markup=reply_markup, parse_mode='Markdown')
        else:
            error_msg = format_error_message("Failed to refresh signal.", symbol)
            await query.edit_message_text(error_msg, parse_mode='Markdown')
    
    async def _handle_refresh_pairs(self, query):
        """Handle refresh pairs callback"""
        await query.edit_message_text("🔄 **Loading supported pairs...**", parse_mode='Markdown')
        
        pairs = await self.signal_generator.get_supported_pairs()
        
        if pairs:
            message = format_pairs_list(pairs)
            
            keyboard = [
                [InlineKeyboardButton("🎯 Get Signal", callback_data="get_signal")],
                [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_pairs")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            error_msg = format_error_message("Failed to load pairs.")
            await query.edit_message_text(error_msg, parse_mode='Markdown')
