# stream_btc_trade_threaded.py
from binance import ThreadedWebsocketManager
from datetime import datetime
import time

def handle_trade(msg):
    # msg keys include: e (event type), E (event time), s (symbol), p (price), q (qty)
    if not msg or 'p' not in msg:
        return
    t = datetime.fromtimestamp(msg['E'] / 1000).strftime('%H:%M:%S.%f')[:-3]
    print(f"[{t}] {msg['s']} trade @ {msg['p']} (qty {msg['q']})")

if __name__ == "__main__":
    twm = ThreadedWebsocketManager()  # public streams don't need API keys
    twm.start()

    # Lowest-latency last-price ticks (every trade)
    twm.start_trade_socket(callback=handle_trade, symbol='BTCUSDT')

    try:
        while True:
            time.sleep(1)  # keep main thread alive
    except KeyboardInterrupt:
        pass
    finally:
        twm.stop()
