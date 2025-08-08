#!/usr/bin/env python3
"""
Main entry point for the MEXC Futures Trading Signals Telegram Bot
"""
import asyncio
import logging
import os
from bot import TradingSignalBot

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def main():
    """Main function to start the bot"""
    try:
        # Initialize and start the bot
        bot = TradingSignalBot()
        await bot.start()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        return

if __name__ == "__main__":
    # Run the bot
    asyncio.run(main())
