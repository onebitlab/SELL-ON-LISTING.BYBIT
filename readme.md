# 🚀 Bybit Sell on Listing Bot

This Python script automatically places a limit sell order immediately after a new token is listed on Bybit. It's built for speed, precision, and safety during high-volatility listing events.

## ⚡️ Features

* **Asynchronous Execution** — Built using `asyncio` and `asyncio.to_thread` to handle API calls without blocking, ensuring maximum responsiveness with the Bybit API.
* **Time synchronization** — Syncs local time with Bybit's server time to avoid clock drift, using modern `datetime` practices.
* **Configurable Pre-Launch Pooling** — Begins checking for the trading pair a specified number of seconds (`pre_launch_pooling`) before your exact `launch_time`.
* **Continuous Monitoring** — Polls the Bybit REST API for the appearance of the trading pair at a defined `pair_check_interval`.
* **Smart Price and Quantity Calculation** — Applies Bybit's `priceFilter` and `lotSizeFilter` to ensure your order meets exchange requirements and is not rejected.
* **Infinite Price Retrieval Retries** — Continuously attempts to fetch the current price until successful or program interruption, with a configurable `price_check_interval` between attempts.
* **Automatic Order Cancellation** — If the order isn't filled within a configurable `order_timeout`, it is automatically cancelled.
* **API Key Pre-Checks** — Verifies the validity of your API key and permissions before starting the main bot logic, preventing failed operations due to misconfiguration.

## ⚙️ Configuration

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Create a `config.py` file in the root directory:**

   ```python
   # config.py

   # BYBIT API Credentials 
   api_key = 'YOUR_BYBIT_API_KEY'          # Your Bybit API Key
   api_secret = 'YOUR_BYBIT_SECRET_KEY'    # Your Bybit Secret Key

   # Trading configuration
   pair = 'ALT/USDT'                       # Trading pair, e.g.: 'ALT/USDT'
   tokens_for_sale = '170'                 # Amount of tokens to sell (as a string)
   price_offset = '1.0'                    # Percentage below market price (e.g., '1.0' means 1% below)

   # Timing
   launch_time = '2025-06-25 10:00:00'     # Exact trading start time (UTC) in 'YYYY-MM-DD HH:MM:SS' format
   pre_launch_pooling = 10                 # Interval (in seconds) before launch_time to start checking for the pair listing
   pair_check_interval = 0.5               # Interval (in seconds) between trade pair availability checks
   price_check_interval = 1.0              # Interval (in seconds) between price retrieval attempts upon error
   order_timeout = 30                      # Cancel order after this many seconds if not filled
   ```

## ⚠️ Important: API Key Permissions

Make sure your Bybit API key has **"Read/Write"** permissions enabled for **"Spot Trading"** or **"Unified Trading Account"**.

If you encounter an `InvalidRequestError` during pre-checks, double-check your API key, secret, and any IP restrictions on your Bybit account. Ensure the key is not expired.

## ▶️ Usage

Simply run:

```bash
python3 main.py
```

## 🛠 Notes

* The time format for `launch_time` must be `"YYYY-MM-DD HH:MM:SS"` in **UTC**.
* If you launch the bot after `launch_time` has passed, it will immediately begin checking for the pair.
* The script uses `asyncio` with `asyncio.to_thread` for robust non-blocking operation with the synchronous `pybit` library.
* Order details are displayed in a readable table format using `tabulate`.
* The bot will continuously attempt to fetch the token's price until successful or interrupted, respecting the `price_check_interval`.

## 📄 License

MIT License — free to use, modify, and distribute.

## 🛑 Disclaimer

Cryptocurrency trading carries significant risks and may result in the loss of your capital. You are solely responsible for any financial decisions you make. This tool is provided for educational purposes only. Use this bot at your own risk. The author is not responsible for any financial losses caused by the use of this program. Always understand the risks associated with automated trading and API interaction.
