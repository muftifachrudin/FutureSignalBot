#!/usr/bin/env python3
"""
Quick test script to verify API connections
"""
import asyncio
import sys
from mexc_client import MEXCClient
from coinglass_client import CoinglassClient

async def test_mexc_api():
    """Test MEXC API endpoints"""
    print("Testing MEXC API...")
    
    async with MEXCClient() as client:
        symbol = "BTCUSDT"
        
        # Test ticker
        try:
            ticker = await client.get_24hr_ticker(symbol)
            print(f"✓ Ticker: {ticker.get('lastPrice', 'N/A')}")
        except Exception as e:
            print(f"✗ Ticker failed: {e}")
        
        # Test klines
        try:
            klines = await client.get_klines(symbol, "1h", 5)
            print(f"✓ Klines: {len(klines)} candles")
        except Exception as e:
            print(f"✗ Klines failed: {e}")

async def test_coinglass_api():
    """Test Coinglass API endpoints"""
    print("\nTesting Coinglass API...")
    
    async with CoinglassClient() as client:
        symbol = "BTC"
        
        # Test pairs markets
        try:
            markets = await client.get_pairs_markets(symbol)
            print(f"✓ Markets: {len(markets) if isinstance(markets, list) else 'Data available'}")
        except Exception as e:
            print(f"✗ Markets failed: {e}")

async def main():
    """Run all tests"""
    await test_mexc_api()
    await test_coinglass_api()
    print("\nAPI test completed!")

if __name__ == "__main__":
    asyncio.run(main())