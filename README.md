🔄 Crypto Triangular Arbitrage Bot (Prototype)






A prototype triangular arbitrage detection bot built for learning, experimentation, and real-time market monitoring.
⚠️ This bot does NOT execute trades — it only detects potential arbitrage opportunities and sends Telegram alerts.

📌 Overview

This bot continuously monitors selected crypto trading pairs to identify triangular arbitrage opportunities. When a potential opportunity appears, the bot automatically sends a message through a Telegram Bot.

Currently, the bot checks the following coins:

BTC

ETH

BNB

More coins can be added easily.

🚀 Features

Real-time triangular arbitrage detection

Telegram notifications for opportunities

Hourly summary logging (optional)

CSV logging for later analysis

Works with the Binance API (public endpoints only)

Fully asynchronous for improved performance

Safe to test — no trading actions performed

⚠️ Disclaimer

This project is a prototype for educational purposes.
It does not place orders, execute trades, or interact with user finances in any form.
Do not use this code for live trading without proper risk management and exchange compliance.

🧰 Technologies Used

Python 3.10+

python-binance

asyncio

python-telegram-bot

📩 Telegram Integration

The bot sends:

Arbitrage alerts

Startup confirmation

Optional hourly summaries

You'll need:

A Telegram Bot Token

Your Telegram Chat ID
