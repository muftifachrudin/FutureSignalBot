#!/usr/bin/env python3
from __future__ import annotations
"""
Quick one-off signal test to verify live metrics for a symbol without starting the bot.
Usage (PowerShell):
    .venv\Scripts\python.exe scripts\quick_signal_test.py BTCUSDT
"""

import asyncio
import json
import sys
from typing import Any, Dict, Optional
import os

# Ensure project root is in sys.path when running from scripts/
_HERE = os.path.dirname(__file__)
_ROOT = os.path.abspath(os.path.join(_HERE, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


async def run_once(symbol: str) -> None:
    try:
        import signal_generator_v2 as sg  # type: ignore
    except Exception as e:
        print(f"Failed to import signal_generator_v2: {e}")
        sys.exit(1)

    Gen = getattr(sg, "PairsCache", None)
    if Gen is None:
        print("PairsCache not found in signal_generator_v2.")
        sys.exit(1)

    try:
        async with Gen() as gen:  # type: ignore[call-arg]
            res: Optional[Dict[str, Any]] = await gen.generate_signal(symbol, force=True)  # type: ignore[attr-defined]
    except Exception as e:
        print(f"Signal generation error: {e}")
        sys.exit(2)

    if not res:
        print("No signal returned.")
        sys.exit(3)

    md: Dict[str, Any] = res.get("market_data", {}) if isinstance(res, dict) else {}
    # Read formatted coinglass_data block
    summary: Dict[str, Any] = {}
    cg = md.get("coinglass_data")
    if isinstance(cg, dict):
        summary = cg  # type: ignore[assignment]

    print(f"Symbol: {symbol}")
    print(f"Signal: {res.get('signal')} | Confidence: {res.get('confidence')} | Risk: {res.get('risk_level')}")
    print("Coinglass metrics (if available):")
    if not summary:
        from config import Config
        hint = "(missing COINGLASS_API_KEY?)" if not Config.COINGLASS_API_KEY else ""
        print(f"  unavailable {hint}")
    else:
        print(f"  funding_rate: {summary.get('funding_rate')}")
        print(f"  open_interest: {summary.get('open_interest')}")
        print(f"  oi_change_24h: {summary.get('oi_change_24h')}")
        print(f"  long_short_ratio: {summary.get('long_short_ratio')}")
    print("\nRaw snippet:")
    print(json.dumps({
        "signal": res.get("signal"),
            "market_data": {
                "funding_rate": summary.get("funding_rate"),
                "open_interest": summary.get("open_interest"),
                "oi_change_24h": summary.get("oi_change_24h"),
                "long_short_ratio": summary.get("long_short_ratio"),
            }
    }, ensure_ascii=False))


def main() -> None:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    asyncio.run(run_once(symbol))


if __name__ == "__main__":
    main()
