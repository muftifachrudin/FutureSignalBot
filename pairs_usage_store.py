"""Track usage frequency of trading pairs to power dynamic "Popular Pairs".

Stores a JSON dict mapping SYMBOL -> usage_count. Thread/async safe via asyncio.Lock.
Handles file corruption by backing up and resetting. Symbols are validated to be
uppercase alphanumeric and typically end with USDT.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, cast

logger = logging.getLogger(__name__)

DEFAULT_FILENAME = "data/pairs_usage.json"


class PairsUsageStore:
    def __init__(self, file_path: str | None = None) -> None:
        root = Path(__file__).parent
        # Default under data/ to keep app root clean
        self.file_path = Path(file_path) if file_path else (root / DEFAULT_FILENAME)
        self._lock = asyncio.Lock()
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    # --- Public API ---
    async def increment(self, symbol: str, by: int = 1) -> None:
        """Increment usage count for a symbol."""
        symbol_u = symbol.upper().strip()
        if not self._is_valid_symbol(symbol_u):
            return
        async with self._lock:
            data = self._read_raw()
            current = int(data.get(symbol_u, 0))
            data[symbol_u] = current + max(1, int(by))
            self._write_raw(data)

    async def get_top_n(self, n: int = 8, allowed: List[str] | None = None) -> List[str]:
        """Return top-N symbols by usage. If allowed is provided, filter by it.

        Ensures deterministic output by sorting by (-count, symbol).
        """
        async with self._lock:
            data = self._read_raw()
        items: List[Tuple[str, int]] = []
        for sym, cnt in data.items():
            try:
                items.append((sym, int(cnt)))
            except Exception:
                continue
        if allowed is not None:
            allowed_set = set(x.upper() for x in allowed)
            items = [(s, c) for s, c in items if s in allowed_set]
        items.sort(key=lambda x: (-x[1], x[0]))
        return [s for s, _ in items[: max(1, int(n))]]

    async def get_counts(self) -> Dict[str, int]:
        async with self._lock:
            data = self._read_raw()
        out: Dict[str, int] = {}
        for s, c in data.items():
            try:
                out[s] = int(c)
            except Exception:
                continue
        return out

    # --- Internals ---
    def _is_valid_symbol(self, symbol: str) -> bool:
        return symbol.isalnum() and 4 <= len(symbol) <= 20

    def _read_raw(self) -> Dict[str, int]:
        if not self.file_path.is_file():
            return {}
        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                out: Dict[str, int] = {}
                raw_any: Dict[Any, Any] = cast(Dict[Any, Any], raw)
                for k_any, v_any in raw_any.items():
                    try:
                        k = str(k_any).upper()
                        v = int(v_any)  # type: ignore[arg-type]
                        out[k] = v
                    except Exception:
                        continue
                return out
        except json.JSONDecodeError:
            try:
                backup_path = self.file_path.with_suffix(".corrupt")
                self.file_path.rename(backup_path)
                logger.warning("Corrupted pairs usage JSON moved to %s", backup_path)
            except Exception:
                logger.warning("Failed to backup corrupted pairs usage file")
        except Exception as e:
            logger.warning("Failed reading pairs usage: %s", e)
        return {}

    def _write_raw(self, data: Dict[str, int]) -> None:
        tmp_path = self.file_path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                # Sort keys for stable diffs
                json.dump({k: int(v) for k, v in sorted(data.items())}, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.file_path)
        except Exception as e:
            logger.error("Failed writing pairs usage: %s", e)
            try:
                if tmp_path.is_file():
                    tmp_path.unlink(missing_ok=True)  # type: ignore[arg-type]
            except Exception:
                pass

__all__ = ["PairsUsageStore"]
