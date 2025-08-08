"""
Data models for trading signals and market analysis
"""
from enum import Enum
from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from datetime import datetime

class SignalType(str, Enum):
    """Trading signal types"""
    LONG = "LONG"
    SHORT = "SHORT" 
    WAIT = "WAIT"

class RiskLevel(str, Enum):
    """Risk level classification"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

class TrendDirection(str, Enum):
    """Trend direction classification"""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"

class TimeframeData(BaseModel):
    """Data for a specific timeframe"""
    timeframe: str
    trend: TrendDirection
    strength: float = Field(ge=-1.0, le=1.0)  # -1 (bearish) to 1 (bullish)
    price_change: float
    volume_change: float
    
class MarketSentiment(BaseModel):
    """Market sentiment indicators"""
    open_interest: float
    open_interest_change_24h: float
    funding_rate: float
    long_rate: float
    short_rate: float
    long_short_ratio: float

class TechnicalLevels(BaseModel):
    """Technical analysis levels"""
    support: Optional[float] = None
    resistance: Optional[float] = None
    pivot: Optional[float] = None
    
class TradingSignal(BaseModel):
    """Complete trading signal with all relevant data"""
    symbol: str
    signal: SignalType
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    risk_level: RiskLevel
    
    # Price levels
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    # Market data
    current_price: Optional[float] = None
    sentiment: Optional[MarketSentiment] = None
    technical_levels: Optional[TechnicalLevels] = None
    
    # Timeframe analysis
    timeframe_analysis: Dict[str, TimeframeData] = Field(default_factory=dict)
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class MarketAnalysis(BaseModel):
    """Comprehensive market analysis"""
    symbol: str
    overall_trend: TrendDirection
    trend_strength: float = Field(ge=-1.0, le=1.0)
    volatility: float = Field(ge=0.0, le=1.0)
    
    # Sentiment indicators
    sentiment: MarketSentiment
    
    # Technical analysis
    technical_levels: TechnicalLevels
    
    # Multi-timeframe analysis
    timeframe_consensus: Dict[str, TrendDirection] = Field(default_factory=dict)
    timeframe_strength: Dict[str, float] = Field(default_factory=dict)
    
    # Key insights
    key_factors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    opportunities: List[str] = Field(default_factory=list)
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data_quality: float = Field(ge=0.0, le=1.0, default=1.0)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ApiResponse(BaseModel):
    """Generic API response wrapper"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
class SignalRequest(BaseModel):
    """Request for signal generation"""
    symbol: str
    force_refresh: bool = False
    include_analysis: bool = True
    timeframes: List[str] = Field(default_factory=lambda: ["5m", "15m", "30m", "1h", "4h"])

class PerformanceMetrics(BaseModel):
    """Signal performance tracking"""
    signal_id: str
    symbol: str
    signal_type: SignalType
    entry_price: float
    current_price: float
    
    # Performance calculation
    pnl_percentage: float
    max_drawdown: float
    time_in_position: int  # seconds
    
    # Signal accuracy
    prediction_accuracy: Optional[float] = None
    confidence_vs_outcome: Optional[float] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class UserSession(BaseModel):
    """User session data for the bot"""
    user_id: int
    username: Optional[str] = None
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    
    # Usage tracking
    signals_requested: int = 0
    analyses_requested: int = 0
    last_symbol: Optional[str] = None
    
    # Preferences
    preferred_timeframes: List[str] = Field(default_factory=lambda: ["1h", "4h"])
    notification_settings: Dict[str, bool] = Field(default_factory=dict)
    
class ExchangeData(BaseModel):
    """Exchange-specific market data"""
    exchange: str
    symbol: str
    price: float
    volume_24h: float
    
    # Futures specific
    open_interest: Optional[float] = None
    funding_rate: Optional[float] = None
    next_funding_time: Optional[datetime] = None
    
    # Order book
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    spread: Optional[float] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class CoinglassData(BaseModel):
    """Coinglass API response data"""
    symbol: str
    
    # Market data
    price_data: Optional[List[Dict]] = None
    open_interest_data: Optional[Dict] = None
    funding_rate_data: Optional[Dict] = None
    long_short_ratio_data: Optional[Dict] = None
    liquidation_data: Optional[Dict] = None
    
    # Processed indicators
    oi_trend: Optional[TrendDirection] = None
    funding_trend: Optional[TrendDirection] = None
    sentiment_score: Optional[float] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class MEXCData(BaseModel):
    """MEXC API response data"""
    symbol: str
    
    # Price data
    klines: Dict[str, List[List]] = Field(default_factory=dict)  # timeframe -> kline data
    ticker_24hr: Optional[Dict] = None
    current_price: Optional[float] = None
    
    # Futures data
    funding_rate: Optional[Dict] = None
    open_interest: Optional[Dict] = None
    long_short_ratio: Optional[Dict] = None
    
    # Volume analysis
    volume_profile: Optional[Dict] = None
    volume_trend: Optional[TrendDirection] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class SignalHistory(BaseModel):
    """Historical signal tracking"""
    signal_id: str
    symbol: str
    signal: TradingSignal
    
    # Outcome tracking
    actual_outcome: Optional[SignalType] = None
    price_target_hit: bool = False
    stop_loss_hit: bool = False
    
    # Performance metrics
    max_profit: float = 0.0
    max_loss: float = 0.0
    final_pnl: Optional[float] = None
    
    # Timing
    signal_time: datetime
    evaluation_time: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Utility functions for models
def create_signal_from_analysis(
    symbol: str,
    market_analysis: MarketAnalysis,
    ai_recommendation: Dict[str, Any]
) -> TradingSignal:
    """Create a trading signal from market analysis and AI recommendation"""
    
    signal_type = SignalType(ai_recommendation.get('signal', 'WAIT'))
    confidence = float(ai_recommendation.get('confidence', 0.5))
    reasoning = ai_recommendation.get('reasoning', 'No reasoning provided')
    risk_level = RiskLevel(ai_recommendation.get('risk_level', 'MEDIUM'))
    
    return TradingSignal(
        symbol=symbol,
        signal=signal_type,
        confidence=confidence,
        reasoning=reasoning,
        risk_level=risk_level,
        entry_price=ai_recommendation.get('entry_price'),
        stop_loss=ai_recommendation.get('stop_loss'),
        take_profit=ai_recommendation.get('take_profit'),
        current_price=market_analysis.sentiment.open_interest,  # This should be actual current price
        sentiment=market_analysis.sentiment,
        technical_levels=market_analysis.technical_levels,
        timeframe_analysis={
            tf: TimeframeData(
                timeframe=tf,
                trend=trend,
                strength=market_analysis.timeframe_strength.get(tf, 0.0),
                price_change=0.0,  # This should be calculated from actual data
                volume_change=0.0   # This should be calculated from actual data
            )
            for tf, trend in market_analysis.timeframe_consensus.items()
        }
    )

def validate_signal_quality(signal: TradingSignal) -> bool:
    """Validate if a trading signal meets quality criteria"""
    
    # Minimum confidence threshold
    if signal.confidence < 0.3:
        return False
    
    # Must have reasoning
    if not signal.reasoning or len(signal.reasoning) < 10:
        return False
    
    # For actionable signals, should have price levels
    if signal.signal in [SignalType.LONG, SignalType.SHORT]:
        if not signal.entry_price:
            return False
    
    return True
