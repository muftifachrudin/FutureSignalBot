#!/usr/bin/env python3
"""
Main entry point for the MEXC Futures Trading Signals Telegram Bot
"""
import asyncio
import logging
import signal
import sys
from signal_generator import SignalGenerator
from bot.telegram_bot import TradingSignalsBot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variable to hold the bot instance
bot_instance = None

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info("Received shutdown signal, stopping bot...")
    if bot_instance:
        asyncio.create_task(bot_instance.stop())
    sys.exit(0)

async def main():
    """Main function to start the bot"""
    global bot_instance
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("Starting MEXC Futures Trading Signals Bot...")
        
        # Initialize and start the bot
        bot_instance = TradingSignalsBot()
        await bot_instance.start()
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        if bot_instance:
            await bot_instance.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Application terminated by user")
    except Exception as e:
        logger.error(f"Application error: {e}")
        sys.exit(1)