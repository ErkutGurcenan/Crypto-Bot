from binance import Client

client = Client()
ticker = client.get_symbol_ticker(symbol="BTCUSDT")
print("BTC/USDT:", ticker["price"])
print(client.get_orderbook_ticker(symbol="BTCUSDT"))  # best bid/ask
print(client.get_ticker(symbol="BTCUSDT"))            # 24h stats

