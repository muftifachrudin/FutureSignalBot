"""
Gemini AI integration for market analysis and signal generation
"""
import json
import logging
import os
from typing import Dict, List, Optional
from pydantic import BaseModel
from google import genai
from google.genai import types
from config import Config

logger = logging.getLogger(__name__)

class TradingSignal(BaseModel):
    """Trading signal response model"""
    signal: str  # "LONG", "SHORT", or "WAIT"
    confidence: float  # 0.0 to 1.0
    reasoning: str
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_level: str  # "LOW", "MEDIUM", "HIGH"

class MarketAnalysis(BaseModel):
    """Market analysis response model"""
    trend_strength: float  # -1.0 to 1.0 (bearish to bullish)
    volatility: float  # 0.0 to 1.0
    sentiment: str  # "BULLISH", "BEARISH", "NEUTRAL"
    key_levels: Dict[str, float]  # support/resistance levels
    timeframe_analysis: Dict[str, str]  # analysis per timeframe

class GeminiAnalyzer:
    """Gemini AI analyzer for trading signals"""
    
    def __init__(self):
        self.client = genai.Client(api_key=Config.GEMINI_API_KEY)
        self.model = "gemini-2.5-pro"
    
    async def analyze_market_data(self, market_data: Dict) -> MarketAnalysis:
        """Analyze comprehensive market data"""
        try:
            system_prompt = """
            You are an expert cryptocurrency futures trader and analyst. 
            Analyze the provided market data and return a comprehensive market analysis.
            Consider price action, volume, open interest, funding rates, and sentiment indicators.
            
            Respond with JSON in this exact format:
            {
                "trend_strength": number between -1.0 and 1.0,
                "volatility": number between 0.0 and 1.0,
                "sentiment": "BULLISH" or "BEARISH" or "NEUTRAL",
                "key_levels": {"support": number, "resistance": number},
                "timeframe_analysis": {"5m": "analysis", "15m": "analysis", "30m": "analysis", "1h": "analysis", "4h": "analysis"}
            }
            """
            
            user_prompt = f"""
            Analyze this market data for trading insights:
            
            Market Data: {json.dumps(market_data, indent=2)}
            
            Provide detailed analysis considering:
            1. Price trends across all timeframes
            2. Volume and open interest changes
            3. Funding rate implications
            4. Long/short ratio analysis
            5. Support and resistance levels
            """
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=MarketAnalysis,
                ),
            )
            
            if response.text:
                data = json.loads(response.text)
                return MarketAnalysis(**data)
            else:
                raise ValueError("Empty response from Gemini")
                
        except Exception as e:
            logger.error(f"Error analyzing market data: {e}")
            # Return neutral analysis on error
            return MarketAnalysis(
                trend_strength=0.0,
                volatility=0.5,
                sentiment="NEUTRAL",
                key_levels={"support": 0.0, "resistance": 0.0},
                timeframe_analysis={tf: "Unable to analyze" for tf in Config.SUPPORTED_TIMEFRAMES}
            )
    
    async def generate_trading_signal(self, symbol: str, market_data: Dict, analysis: MarketAnalysis) -> TradingSignal:
        """Generate trading signal based on market analysis"""
        try:
            system_prompt = """
            You are an expert cryptocurrency futures trading signal generator.
            Based on the market data and analysis provided, generate a precise trading signal.
            
            Signal Rules:
            - LONG: When multiple timeframes show uptrend + positive funding + high short ratio + rising OI
            - SHORT: When multiple timeframes show downtrend + negative funding + high long ratio + declining OI
            - WAIT: When conditions are mixed or unclear
            
            Respond with JSON in this exact format:
            {
                "signal": "LONG" or "SHORT" or "WAIT",
                "confidence": number between 0.0 and 1.0,
                "reasoning": "detailed explanation",
                "entry_price": number or null,
                "stop_loss": number or null,
                "take_profit": number or null,
                "risk_level": "LOW" or "MEDIUM" or "HIGH"
            }
            """
            
            user_prompt = f"""
            Generate trading signal for {symbol}:
            
            Market Data: {json.dumps(market_data, indent=2)}
            
            Market Analysis: {json.dumps(analysis.dict(), indent=2)}
            
            Consider these factors:
            1. Trend alignment across timeframes
            2. Open interest changes
            3. Funding rate direction
            4. Long/short ratio extremes
            5. Volume confirmation
            6. Risk management levels
            
            Provide clear reasoning for your signal decision.
            """
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=[types.Content(role="user", parts=[types.Part(text=user_prompt)])],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=TradingSignal,
                ),
            )
            
            if response.text:
                data = json.loads(response.text)
                return TradingSignal(**data)
            else:
                raise ValueError("Empty response from Gemini")
                
        except Exception as e:
            logger.error(f"Error generating trading signal: {e}")
            # Return wait signal on error
            return TradingSignal(
                signal="WAIT",
                confidence=0.0,
                reasoning=f"Analysis error: {str(e)}",
                risk_level="HIGH"
            )
    
    async def explain_market_conditions(self, symbol: str, market_data: Dict) -> str:
        """Provide detailed explanation of current market conditions"""
        try:
            prompt = f"""
            Provide a comprehensive but concise explanation of current market conditions for {symbol}.
            
            Market Data: {json.dumps(market_data, indent=2)}
            
            Explain in simple terms:
            1. What the current trend looks like
            2. What the indicators are suggesting
            3. What traders should watch for
            4. Key risk factors
            
            Keep it under 300 words and trader-friendly.
            """
            
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            
            return response.text or "Unable to analyze current market conditions."
            
        except Exception as e:
            logger.error(f"Error explaining market conditions: {e}")
            return f"Error analyzing market conditions for {symbol}: {str(e)}"
