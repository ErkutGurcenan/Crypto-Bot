# Prototype for triangular arbitrage bot with telegram bot
import asyncio
import csv
import os
from datetime import datetime, timedelta
from binance import AsyncClient, BinanceSocketManager
import aiohttp

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
TAKER_FEE = 0.001              # 0.10% taker fee per leg
FEE_FACTOR = (1 - TAKER_FEE) ** 3
THRESHOLD = 0.0            # trigger when edge > 0.000%
NOTIONAL_USDT = 1000.0         # for simulated P&L calc
CSV_PATH = "arb_opportunities.csv"
ALERT_COOLDOWN_SECONDS = 15     # per-cycle min gap between Telegram alerts

# Telegram (set env vars before running)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ---- shared state ----
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
    """ Return dict of fee-adjusted edges for cycles A..F, or None if missing data """
    try:
        b_btc, a_btc   = latest["BTCUSDT"]["bid"], latest["BTCUSDT"]["ask"]
        b_ethu, a_ethu = latest["ETHUSDT"]["bid"], latest["ETHUSDT"]["ask"]
        b_ethb, a_ethb = latest["ETHBTC"]["bid"], latest["ETHBTC"]["ask"]
        b_bnbu, a_bnbu = latest["BNBUSDT"]["bid"], latest["BNBUSDT"]["ask"]
        b_bnbb, a_bnbb = latest["BNBBTC"]["bid"], latest["BNBBTC"]["ask"]
        b_bnbe, a_bnbe = latest["BNBETH"]["bid"], latest["BNBETH"]["ask"]
    except KeyError:
        return None

    if None in (b_btc, a_btc, b_ethu, a_ethu, b_ethb, a_ethb,
                b_bnbu, a_bnbu, b_bnbb, a_bnbb, b_bnbe, a_bnbe):
        return None

    ff = FEE_FACTOR

    # BTC-ETH-USDT
    gross_A = (1.0 / a_btc)  * (1.0 / a_ethb) * b_ethu
    gross_B = (1.0 / a_ethu) * b_ethb         * b_btc
    edgeA = gross_A * ff - 1.0
    edgeB = gross_B * ff - 1.0

    # BTC-BNB-USDT
    gross_C = (1.0 / a_btc)  * (1.0 / a_bnbb) * b_bnbu
    gross_D = (1.0 / a_bnbu) * b_bnbb         * b_btc
    edgeC = gross_C * ff - 1.0
    edgeD = gross_D * ff - 1.0

    # ETH-BNB-USDT
    gross_E = (1.0 / a_ethu) * (1.0 / a_bnbe) * b_bnbu
    gross_F = (1.0 / a_bnbu) * b_bnbe         * b_ethu
    edgeE = gross_E * ff - 1.0
    edgeF = gross_F * ff - 1.0

    return {"A": edgeA, "B": edgeB, "C": edgeC, "D": edgeD, "E": edgeE, "F": edgeF}

async def send_telegram(session: aiohttp.ClientSession, text: str):
    """ Send a Telegram message if token/chat are configured """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "disable_web_page_preview": True,
        "parse_mode": "Markdown"
    }
    try:
        async with session.post(url, data=payload, timeout=10) as resp:
            # Optional: raise on non-200 to see errors
            if resp.status != 200:
                body = await resp.text()
                print(f"Telegram send failed [{resp.status}]: {body}")
    except Exception as e:
        print(f"Telegram send error: {e}")

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
    Checks every millisecond for arbitrage opportunities
    Sends Telegram message immediately when an opportunity occurs
    Enforces a global cooldown of 1 second between alerts
    """
    ensure_csv_header(CSV_PATH)
    last_alert_time = datetime.min  # Last Telegram message sent

    async with aiohttp.ClientSession() as session:
        while True:
            edges = tri_edges_all()
            if edges is not None:
                now = datetime.now()
                # Checks which cycles are above threshold
                passing = [(k, v) for k, v in edges.items() if v > THRESHOLD]

                # Print if any cycle passes
                if passing:
                    ts = now.strftime("%H:%M:%S.%f")[:-3]
                    status = " | ".join(f"{k}:{edges[k]*100:>7.4f}%" for k in edges.keys())
                    print(f"[{ts}] {status}")

                # If any opportunity and cooldown elapsed
                if passing and (now - last_alert_time).total_seconds() >= 1.0:
                    # Pick the best cycle (highest edge)
                    best_cycle, best_edge = max(passing, key=lambda x: x[1])
                    pnl = NOTIONAL_USDT * best_edge
                    pct = best_edge * 100

                    # Log to CSV
                    append_csv(best_cycle, best_edge)

                    # Prepare Telegram message
                    text = (
                        f"*Arb Opportunity*  Cycle *{best_cycle}*\n"
                        f"Edge: *{pct:.3f}%*   (sim P&L on ${NOTIONAL_USDT:.0f}: {pnl:.2f} USDT)\n"
                        f"Threshold: {THRESHOLD*100:.3f}%   Fees/leg: {TAKER_FEE*100:.2f}%\n"
                        f"`BTCUSDT` {latest['BTCUSDT']['bid']:.2f}/{latest['BTCUSDT']['ask']:.2f} | "
                        f"`ETHUSDT` {latest['ETHUSDT']['bid']:.2f}/{latest['ETHUSDT']['ask']:.2f} | "
                        f"`ETHBTC` {latest['ETHBTC']['bid']:.8f}/{latest['ETHBTC']['ask']:.8f}\n"
                        f"`BNBUSDT` {latest['BNBUSDT']['bid']:.2f}/{latest['BNBUSDT']['ask']:.2f} | "
                        f"`BNBBTC` {latest['BNBBTC']['bid']:.8f}/{latest['BNBBTC']['ask']:.8f} | "
                        f"`BNBETH` {latest['BNBETH']['bid']:.8f}/{latest['BNBETH']['ask']:.8f}"
                    )

                    # Send Telegram message
                    await send_telegram(session, text)
                    last_alert_time = now

            await asyncio.sleep(0.001)  # 1 ms check loop

async def main():
    client = await AsyncClient.create()  # Public data
    bsm = BinanceSocketManager(client)
    try:
        await asyncio.gather(consumer(bsm), opportunity_monitor())
    finally:
        await client.close_connection()

if __name__ == "__main__":
    asyncio.run(main())
    

