# filename: tri_arb_realtime_logger.py
import asyncio
import csv
import os
from datetime import datetime
from binance import AsyncClient, BinanceSocketManager

PAIRS = [
    {"base": "BTC", "quote": "USDT", "symbol": "BTCUSDT"},
    {"base": "ETH", "quote": "USDT", "symbol": "ETHUSDT"},
    {"base": "ETH", "quote": "BTC",  "symbol": "ETHBTC"},
]
SYMBOLS = [p["symbol"] for p in PAIRS]

# ---- params ----
TAKER_FEE = 0.001                 # 0.10% taker fee
FEE_FACTOR = (1 - TAKER_FEE) ** 3
THRESHOLD = -0.001                # print/log when edge > -0.100%
NOTIONAL_USDT = 1000.0            # for simulated P&L
CSV_PATH = "arb_opportunities.csv"

# ---- shared state (latest quotes) ----
latest = {s: {"bid": None, "ask": None} for s in SYMBOLS}

def ensure_csv_header(path: str):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "cycle",                 # A: USDT→BTC→ETH→USDT, B: USDT→ETH→BTC→USDT
                "edge",                  # decimal (e.g., 0.0035 = 0.35%)
                "edge_pct",              # percent
                "sim_pnl_usdt",          # on NOTIONAL_USDT
                "BTCUSDT_bid","BTCUSDT_ask",
                "ETHUSDT_bid","ETHUSDT_ask",
                "ETHBTC_bid","ETHBTC_ask",
            ])

def append_csv(cycle: str, edge: float):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    pnl = NOTIONAL_USDT * edge
    row = [
        ts,
        cycle,
        edge,
        edge * 100.0,
        pnl,
        latest["BTCUSDT"]["bid"], latest["BTCUSDT"]["ask"],
        latest["ETHUSDT"]["bid"], latest["ETHUSDT"]["ask"],
        latest["ETHBTC"]["bid"],  latest["ETHBTC"]["ask"],
    ]
    with open(CSV_PATH, "a", newline="") as f:
        csv.writer(f).writerow(row)

def tri_edges():
    """Fee-adjusted triangular edges for both cycles (A & B)."""
    b_btc, a_btc   = latest["BTCUSDT"]["bid"], latest["BTCUSDT"]["ask"]
    b_ethu, a_ethu = latest["ETHUSDT"]["bid"], latest["ETHUSDT"]["ask"]
    b_ethb, a_ethb = latest["ETHBTC"]["bid"], latest["ETHBTC"]["ask"]
    if None in (b_btc, a_btc, b_ethu, a_ethu, b_ethb, a_ethb):
        return None, None
    gross_A = (1.0 / a_btc) * (1.0 / a_ethb) * b_ethu                 # USDT→BTC (ask), BTC→ETH (ask), ETH→USDT (bid)
    gross_B = (1.0 / a_ethu) * b_ethb * b_btc                         # USDT→ETH (ask), ETH→BTC (bid), BTC→USDT (bid)
    edgeA = gross_A * FEE_FACTOR - 1.0
    edgeB = gross_B * FEE_FACTOR - 1.0
    return edgeA, edgeB

async def consumer(bsm: BinanceSocketManager):
    """Receive live bookTicker updates."""
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

async def opportunity_monitor():
    """
    Check every 1 ms; print if either edge > THRESHOLD.
    Log to CSV only on 'crossing' events (from <= THRESHOLD to > THRESHOLD)
    to avoid spamming the file.
    """
    ensure_csv_header(CSV_PATH)
    was_above_A = False
    was_above_B = False

    while True:
        edgeA, edgeB = tri_edges()
        if edgeA is not None and edgeB is not None:
            aboveA = edgeA > THRESHOLD
            aboveB = edgeB > THRESHOLD

            # print when close/positive
            if aboveA or aboveB:
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"[{ts}] EdgeA {edgeA*100:>7.4f}% | EdgeB {edgeB*100:>7.4f}%")

            # log only on threshold crossing events
            if aboveA and not was_above_A:
                append_csv("A", edgeA)
            if aboveB and not was_above_B:
                append_csv("B", edgeB)

            was_above_A = aboveA
            was_above_B = aboveB

        await asyncio.sleep(0.001)  # 1 ms

async def main():
    client = await AsyncClient.create()  # public data; no keys required
    bsm = BinanceSocketManager(client)
    try:
        await asyncio.gather(consumer(bsm), opportunity_monitor())
    finally:
        await client.close_connection()

if __name__ == "__main__":
    asyncio.run(main())
