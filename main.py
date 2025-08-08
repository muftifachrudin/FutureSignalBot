#!/usr/bin/env python3
"""
Main entry point for the MEXC Futures Trading Signals Telegram Bot
"""
import logging
from logging.handlers import RotatingFileHandler
from bot import TradingSignalBot

# Configure logging
# Console logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Rotating file logging (logs/bot.log)
try:
    import os
    os.makedirs('logs', exist_ok=True)
    file_handler = RotatingFileHandler('logs/bot.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    file_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(file_handler)
except Exception as _e:
    logging.getLogger(__name__).warning(f"File logging disabled: {_e}")
logger = logging.getLogger(__name__)

def main():
    try:
        bot = TradingSignalBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise

if __name__ == "__main__":
    main()
