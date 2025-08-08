#!/usr/bin/env python3
"""
Main entry point for the MEXC Futures Trading Signals Telegram Bot
"""
import logging
import os
from typing import Optional, IO
try:
    # Windows-only import for file locking
    import msvcrt  # type: ignore
except Exception:  # pragma: no cover
    msvcrt = None  # type: ignore
from logging.handlers import RotatingFileHandler
from bot import TradingSignalBot

# Configure logging
# Console logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Rotating file logging (logs/bot.log)
try:
    os.makedirs('logs', exist_ok=True)
    file_handler = RotatingFileHandler('logs/bot.log', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    file_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(file_handler)
except Exception as _e:
    logging.getLogger(__name__).warning(f"File logging disabled: {_e}")
logger = logging.getLogger(__name__)

_lock_handle: Optional[IO[str]] = None

def _acquire_single_instance_lock() -> bool:
    """Prevent multiple instances on Windows to avoid Telegram 409 conflicts.
    Returns True if lock acquired, False otherwise.
    """
    global _lock_handle
    lock_path = os.path.join(os.path.dirname(__file__), '.bot.lock')
    try:
        if msvcrt is None:
            # Non-Windows: skip lock silently
            return True
        # Keep the handle open for the lifetime of the process
        _lock_handle = open(lock_path, 'a+')
        # Lock 1 byte without blocking
        msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except Exception as e:
        logger.warning(f"Another bot instance appears to be running (lock busy). {e}")
        try:
            if _lock_handle:
                _lock_handle.close()
        finally:
            _lock_handle = None
        return False

def _release_single_instance_lock() -> None:
    global _lock_handle
    try:
        if _lock_handle and msvcrt is not None:
            # Unlock the same 1 byte region
            msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
            _lock_handle.close()
    except Exception:
        pass
    finally:
        _lock_handle = None

def main():
    try:
        if not _acquire_single_instance_lock():
            logger.error("Bot already running. Exiting this instance to prevent conflicts.")
            return
        bot = TradingSignalBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise
    finally:
        _release_single_instance_lock()

if __name__ == "__main__":
    main()
