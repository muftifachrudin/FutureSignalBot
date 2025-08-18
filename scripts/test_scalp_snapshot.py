import asyncio
from signal_generator_v2 import PairsCache

async def main():
    symbol = 'BTCUSDT'
    async with PairsCache() as gen:  # type: ignore
        snap = await gen.get_scalp_snapshot(symbol)
        print("--- SNAPSHOT START ---")
        print(snap or "<no snapshot>")
        print("--- SNAPSHOT END ---")

if __name__ == '__main__':
    asyncio.run(main())
