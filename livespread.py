from binance import ThreadedWebsocketManager
from datetime import datetime
import time

def handle_book_ticker(msg):
    # Ignore non-data messages (e.g., {"result": None} acks)
    if not isinstance(msg, dict) or 'b' not in msg or 'a' not in msg:
        return

    bid = float(msg['b'])
    ask = float(msg['a'])
    spread = ask - bid
    mid = (ask + bid) / 2

    # bookTicker usually has no 'E'; use local time
    ts_str = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    print(f"[{ts_str}] {msg.get('s','?')} bid {bid:.2f} | ask {ask:.2f} | spread {spread:.2f} | mid {mid:.2f}")

if __name__ == "__main__":
    twm = ThreadedWebsocketManager()
    twm.start()
    twm.start_symbol_book_ticker_socket(callback=handle_book_ticker, symbol='BTCUSDT')

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        twm.stop()
