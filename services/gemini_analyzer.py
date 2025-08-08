"""
Compatibility shim for Gemini analyzer service.

This module re-exports the working Gemini analyzer implementation from the
top-level `gemini_analyzer.py` to keep legacy imports functioning.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    # Prefer the top-level implementation
    from gemini_analyzer import GeminiAnalyzer, TradingSignal, MarketAnalysis  # type: ignore
except Exception:
    from pydantic import BaseModel

    class TradingSignal(BaseModel):
        signal: str
        confidence: float
        reasoning: str = ""
        entry_price: Optional[float] = None
        stop_loss: Optional[float] = None
        take_profit: Optional[float] = None
        risk_level: str = "HIGH"

    class MarketAnalysis(BaseModel):
        trend_strength: float = 0.0
        volatility: float = 0.5
        sentiment: str = "NEUTRAL"
        key_levels: Dict[str, float] = {"support": 0.0, "resistance": 0.0}
        timeframe_analysis: Dict[str, str] = {}

    class GeminiAnalyzer:
        def __init__(self) -> None:
            self.client: Any | None = None

        async def analyze_market_data(self, market_data: Dict[str, Any]) -> MarketAnalysis:
            return MarketAnalysis()

        async def generate_trading_signal(self, symbol: str, market_data: Dict[str, Any], analysis: MarketAnalysis) -> TradingSignal:
            return TradingSignal(signal="WAIT", confidence=0.1, reasoning="AI unavailable")

        async def explain_market_conditions(self, symbol: str, market_data: Dict[str, Any]) -> str:
            return "AI analysis unavailable"

__all__ = ["GeminiAnalyzer", "TradingSignal", "MarketAnalysis"]
