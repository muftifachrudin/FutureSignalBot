"""Persistent pairs (watchlist) storage for dynamic /pairs management.

Stores a JSON file containing a list of symbols (uppercase) the bot should treat
as the *user managed* watchlist. This is distinct from the full exchange
supported pairs list returned by the signal generator. The watchlist allows
admins to curate which symbols are highlighted via /pairs.

Design goals:
 - Simple JSON file (atomic write) for portability
 - Uppercase canonical symbols, validation (must end with USDT by default)
 - Thread/async safety via an asyncio.Lock (bot is async)
 - Graceful corruption handling (auto backup + reset)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

DEFAULT_FILENAME = "pairs_watchlist.json"


class PairsStore:
    def __init__(self, file_path: str | None = None) -> None:
        root = Path(__file__).parent
        self.file_path = Path(file_path) if file_path else (root / DEFAULT_FILENAME)
        self._lock = asyncio.Lock()
        # Ensure directory exists
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    async def get_pairs(self) -> List[str]:
        async with self._lock:
            data = self._read_raw()
            # Guarantee sorted unique order for deterministic output
            # Normalize to strings; ignore non-string entries
            cleaned: List[str] = [str(s) for s in data]
            return sorted(set(cleaned))

    async def add_pair(self, symbol: str) -> bool:
        """Add symbol to watchlist. Returns True if added, False if already present or invalid."""
        symbol_u = symbol.upper().strip()
        if not self._is_valid_symbol(symbol_u):
            return False
        async with self._lock:
            data = self._read_raw()
            if symbol_u in data:
                return False
            data.append(symbol_u)
            self._write_raw(data)
            return True

    async def remove_pair(self, symbol: str) -> bool:
        symbol_u = symbol.upper().strip()
        async with self._lock:
            data = self._read_raw()
            if symbol_u not in data:
                return False
            data = [s for s in data if s != symbol_u]
            self._write_raw(data)
            return True

    def _is_valid_symbol(self, symbol: str) -> bool:
        # Basic validation: alnum and ends with USDT
        return symbol.isalnum() and symbol.endswith("USDT") and 5 <= len(symbol) <= 20

    # --- File IO helpers (synchronous; wrapped by async lock) ---
    def _read_raw(self) -> List[str]:
        if not self.file_path.is_file():
            # Seed with popular defaults if file absent
            return [
                "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
                "DOGEUSDT", "ADAUSDT"
            ]
        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                data_list: List[str] = [str(s).upper() for s in raw]
                return data_list
        except json.JSONDecodeError:
            # Corrupted file – backup then reset
            try:
                backup_path = self.file_path.with_suffix(".corrupt")
                self.file_path.rename(backup_path)
                logger.warning("Corrupted pairs watchlist JSON moved to %s", backup_path)
            except Exception:
                logger.warning("Failed to backup corrupted pairs watchlist file")
        except Exception as e:
            logger.warning("Failed reading pairs watchlist: %s", e)
        return []

    def _write_raw(self, pairs: List[str]) -> None:
        tmp_path = self.file_path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                json.dump(sorted(set(pairs)), f, ensure_ascii=False, indent=2)
            # Atomic replace
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            logger.error("Failed writing pairs watchlist: %s", e)
            try:
                if tmp_path.is_file():
                    tmp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass

__all__ = ["PairsStore"]
