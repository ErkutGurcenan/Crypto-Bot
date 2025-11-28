# Doesn't have the telegram bot feature however successfully prints the arbitrage opputunities to a csv file
import asyncio
import csv
import os
from datetime import datetime
from binance import AsyncClient, BinanceSocketManager

# Possible pairs for arbitrage
PAIRS = [
    {"base": "BTC", "quote": "USDT", "symbol": "BTCUSDT"},
    {"base": "ETH", "quote": "USDT", "symbol": "ETHUSDT"},
    {"base": "ETH", "quote": "BTC",  "symbol": "ETHBTC"},
    {"base": "BNB", "quote": "USDT", "symbol": "BNBUSDT"},
    {"base": "BNB", "quote": "BTC",  "symbol": "BNBBTC"},
    {"base": "BNB", "quote": "ETH",  "symbol": "BNBETH"},
]
SYMBOLS = [p["symbol"] for p in PAIRS]

# Parameters
TAKER_FEE = 0.001                 # 0.10% taker fee per leg
FEE_FACTOR = (1 - TAKER_FEE) ** 3
THRESHOLD = -0.001                # print/log when edge > -0.100%
NOTIONAL_USDT = 1000.0            # for simulated P&L
CSV_PATH = "arb_opportunities_bnb.csv"

# Current state
latest = {s: {"bid": None, "ask": None} for s in SYMBOLS}

def ensure_csv_header(path: str):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp",
                "cycle",                 # A..F
                "edge",                  # decimal (e.g., 0.0035 = 0.35%)
                "edge_pct",              # percent
                "sim_pnl_usdt",          # on NOTIONAL_USDT
                "BTCUSDT_bid","BTCUSDT_ask",
                "ETHUSDT_bid","ETHUSDT_ask",
                "ETHBTC_bid","ETHBTC_ask",
                "BNBUSDT_bid","BNBUSDT_ask",
                "BNBBTC_bid","BNBBTC_ask",
                "BNBETH_bid","BNBETH_ask",
            ])


# 
def append_csv(cycle: str, edge: float):
    """ Writes the data to csv file """
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    pnl = NOTIONAL_USDT * edge
    row = [
        ts, cycle, edge, edge * 100.0, pnl,
        latest["BTCUSDT"]["bid"], latest["BTCUSDT"]["ask"],
        latest["ETHUSDT"]["bid"], latest["ETHUSDT"]["ask"],
        latest["ETHBTC"]["bid"],  latest["ETHBTC"]["ask"],
        latest["BNBUSDT"]["bid"], latest["BNBUSDT"]["ask"],
        latest["BNBBTC"]["bid"],  latest["BNBBTC"]["ask"],
        latest["BNBETH"]["bid"],  latest["BNBETH"]["ask"],
    ]
    with open(CSV_PATH, "a", newline="") as f:
        csv.writer(f).writerow(row)

def tri_edges_all():
    """
    Returns dict of edges (fee-adjusted) for 6 cycles:
      A: USDT -> BTC (ask) -> ETH (ask ETHBTC) -> USDT (bid ETHUSDT)
      B: USDT -> ETH (ask) -> BTC (bid ETHBTC) -> USDT (bid BTCUSDT)
      C: USDT -> BTC (ask) -> BNB (ask BNBBTC) -> USDT (bid BNBUSDT)
      D: USDT -> BNB (ask) -> BTC (bid BNBBTC) -> USDT (bid BTCUSDT)
      E: USDT -> ETH (ask) -> BNB (ask BNBETH) -> USDT (bid BNBUSDT)
      F: USDT -> BNB (ask) -> ETH (bid BNBETH) -> USDT (bid ETHUSDT)
    """
    # Extract quotes
    try:
        b_btc, a_btc   = latest["BTCUSDT"]["bid"], latest["BTCUSDT"]["ask"]
        b_ethu, a_ethu = latest["ETHUSDT"]["bid"], latest["ETHUSDT"]["ask"]
        b_ethb, a_ethb = latest["ETHBTC"]["bid"], latest["ETHBTC"]["ask"]
        b_bnbu, a_bnbu = latest["BNBUSDT"]["bid"], latest["BNBUSDT"]["ask"]
        b_bnbb, a_bnbb = latest["BNBBTC"]["bid"], latest["BNBBTC"]["ask"]
        b_bnbe, a_bnbe = latest["BNBETH"]["bid"], latest["BNBETH"]["ask"]
    except KeyError:
        return None  # Symbols not ready yet

    if None in (b_btc, a_btc, b_ethu, a_ethu, b_ethb, a_ethb,
                b_bnbu, a_bnbu, b_bnbb, a_bnbb, b_bnbe, a_bnbe):
        return None

    ff = FEE_FACTOR

    # BTC-ETH-USDT cycles
    gross_A = (1.0 / a_btc) * (1.0 / a_ethb) * b_ethu
    gross_B = (1.0 / a_ethu) * b_ethb * b_btc
    edgeA = gross_A * ff - 1.0
    edgeB = gross_B * ff - 1.0

    # BTC-BNB-USDT cycles  (BNBBTC = BNB priced in BTC)
    gross_C = (1.0 / a_btc) * (1.0 / a_bnbb) * b_bnbu
    gross_D = (1.0 / a_bnbu) * b_bnbb * b_btc
    edgeC = gross_C * ff - 1.0
    edgeD = gross_D * ff - 1.0

    # ETH-BNB-USDT cycles  (BNBETH = BNB priced in ETH)
    gross_E = (1.0 / a_ethu) * (1.0 / a_bnbe) * b_bnbu
    gross_F = (1.0 / a_bnbu) * b_bnbe * b_ethu
    edgeE = gross_E * ff - 1.0
    edgeF = gross_F * ff - 1.0

    return {"A": edgeA, "B": edgeB, "C": edgeC, "D": edgeD, "E": edgeE, "F": edgeF}

async def consumer(bsm: BinanceSocketManager):
    """ Receive live bookTicker updates """
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
    Check every 1 ms; print if any cycle edge > THRESHOLD
    Log to CSV only on 'crossing' events (from <= THRESHOLD to > THRESHOLD)
    """
    ensure_csv_header(CSV_PATH)
    was_above = {k: False for k in ["A","B","C","D","E","F"]}

    while True:
        edges = tri_edges_all()
        if edges is not None:
            # Checks which cycles are above threshold
            passing = [k for k, v in edges.items() if v > THRESHOLD]

            # Print if any cycle passes
            if passing:
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                # Build a compact status string for all cycles
                status = " | ".join(f"{k}:{edges[k]*100:>7.4f}%" for k in ["A","B","C","D","E","F"])
                print(f"[{ts}] {status}")

            # CSV logging on crossing events only
            for k, v in edges.items():
                if v > THRESHOLD and not was_above[k]:
                    append_csv(k, v)
                was_above[k] = (v > THRESHOLD)

        await asyncio.sleep(0.001)  # 1 ms

async def main():
    client = await AsyncClient.create()  # Public data
    bsm = BinanceSocketManager(client)
    try:
        await asyncio.gather(consumer(bsm), opportunity_monitor())
    finally:
        await client.close_connection()

if __name__ == "__main__":
    asyncio.run(main())
