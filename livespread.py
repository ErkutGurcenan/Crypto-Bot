import asyncio
from datetime import datetime
from typing import Optional
from binance import AsyncClient, BinanceSocketManager

PAIRS = [
    {"base": "BTC", "quote": "USDT", "symbol": "BTCUSDT"},
    {"base": "ETH", "quote": "USDT", "symbol": "ETHUSDT"},
    {"base": "ETH", "quote": "BTC",  "symbol": "ETHBTC"},
]
SYMBOLS = [p["symbol"] for p in PAIRS]

# --- parameters ---
TAKER_FEE = 0.001
FEE_FACTOR = (1 - TAKER_FEE) ** 3
PRINT_THRESHOLD = -0.001     # -0.100 % in decimal

latest = {s: {"bid": None, "ask": None} for s in SYMBOLS}

# --- helpers ---
def tri_edges():
    b_btc, a_btc   = latest["BTCUSDT"]["bid"], latest["BTCUSDT"]["ask"]
    b_ethu, a_ethu = latest["ETHUSDT"]["bid"], latest["ETHUSDT"]["ask"]
    b_ethb, a_ethb = latest["ETHBTC"]["bid"], latest["ETHBTC"]["ask"]
    if None in (b_btc, a_btc, b_ethu, a_ethu, b_ethb, a_ethb):
        return None, None

    gross_A = (1 / a_btc) * (1 / a_ethb) * b_ethu
    gross_B = (1 / a_ethu) * b_ethb * b_btc
    edgeA = gross_A * FEE_FACTOR - 1.0
    edgeB = gross_B * FEE_FACTOR - 1.0
    return edgeA, edgeB

# --- async tasks ---
async def consumer(bsm: BinanceSocketManager):
    streams = [f"{s.lower()}@bookTicker" for s in SYMBOLS]
    async with bsm.multiplex_socket(streams) as stream:
        while True:
            msg = await stream.recv()
            data = msg.get("data", {})
            if not isinstance(data, dict) or "b" not in data or "a" not in data:
                continue
            sym = data.get("s")
            if sym in SYMBOLS:
                latest[sym]["bid"] = float(data["b"])
                latest[sym]["ask"] = float(data["a"])

async def fast_printer():
    """Print whenever either edge > -0.100 %."""
    while True:
        edgeA, edgeB = tri_edges()
        if edgeA is not None and edgeB is not None:
            if edgeA > PRINT_THRESHOLD or edgeB > PRINT_THRESHOLD:
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"[{ts}] EdgeA {edgeA*100:>7.4f}% | EdgeB {edgeB*100:>7.4f}%")
        await asyncio.sleep(0.001)  # 1 ms delay

async def main():
    client = await AsyncClient.create()
    bsm = BinanceSocketManager(client)
    try:
        await asyncio.gather(consumer(bsm), fast_printer())
    finally:
        await client.close_connection()

if __name__ == "__main__":
    asyncio.run(main())
