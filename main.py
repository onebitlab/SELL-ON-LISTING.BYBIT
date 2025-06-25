import asyncio
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import pytz

from pybit.unified_trading import HTTP
from pybit.exceptions import InvalidRequestError

from config import (
    api_key,
    api_secret,
    pair as cfg_pair,
    tokens_for_sale as cfg_tokens,
    price_offset as cfg_offset,
    order_timeout as cfg_timeout,
    pair_check_interval as cfg_pair_check_interval,
    launch_time as cfg_launch_time,
    pre_launch_pooling as cfg_pre_launch_pooling,
    price_check_interval as cfg_price_check_interval
)
from colorama import init, Fore, Style
from tabulate import tabulate

init(autoreset=True)

pair = cfg_pair.replace('/', '').strip().upper()
tokens_for_sale = Decimal(cfg_tokens)
price_offset = Decimal(cfg_offset)
order_timeout = int(cfg_timeout)
pair_check_interval = float(cfg_pair_check_interval)
pre_launch_pooling = int(cfg_pre_launch_pooling)
price_check_interval = float(cfg_price_check_interval)
launch_time_utc = datetime.strptime(cfg_launch_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=pytz.UTC)

client_instance = None

def log_info(message):
    print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} {message}")

def log_success(message):
    print(f"{Fore.GREEN}[SUCCESS]{Style.RESET_ALL} {message}")

def log_warning(message):
    print(f"{Fore.YELLOW}[WARNING]{Style.RESET_ALL} {message}")

def log_error(message):
    print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {message}")

def print_order_details(order):
    order_table = [
        ["Symbol", order.get('symbol')],
        ["Order ID", order.get('orderId')],
        ["Status", order.get('orderStatus')],
        ["Type", order.get('orderType')],
        ["Side", order.get('side')],
        ["Quantity", order.get('qty')],
        ["Price", order.get('price')],
        ["Filled Qty", order.get('cumExecQty')],
        ["Total USDT", order.get('cumExecValue')],
        ["Time in Force", order.get('timeInForce')],
    ]
    print("-" * 37)
    print(tabulate(order_table, tablefmt="fancy_grid"))
    print("-" * 37)

async def pre_launch_checks(client: HTTP) -> bool:
    log_info("Performing pre-launch API key checks...")
    try:
        await asyncio.to_thread(client.get_wallet_balance, accountType="UNIFIED")
        log_success("API keys are valid and have necessary permissions.")
        return True
    except InvalidRequestError as e:
        log_error(f"API error during pre-launch API key check: {e}")
        log_error("Please check your API key, secret, and permissions.")
        return False
    except Exception as e:
        log_error(f"An unexpected error occurred during pre-launch checks: {e}")
        return False

async def wait_until_launch(client: HTTP):
    try:
        server_time_resp = await asyncio.to_thread(client.get_server_time)
        server_now = datetime.fromtimestamp(int(server_time_resp["result"]["timeNano"]) / 1e9, tz=pytz.UTC)
        wait_until = launch_time_utc - timedelta(seconds=pre_launch_pooling)

        if server_now >= wait_until:
            log_info(f"Launch time already reached or close (within {pre_launch_pooling}s). Skipping wait.")
            return

        while server_now < wait_until:
            remaining = wait_until - server_now
            if remaining.total_seconds() < 0:
                break
            total_seconds = int(remaining.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            print(f"{Fore.CYAN}[INFO]{Style.RESET_ALL} Waiting for launch: "
                  f"{str(hours).zfill(2)}:{str(minutes).zfill(2)}:{str(seconds).zfill(2)}", end="\r")
            await asyncio.sleep(1)
            server_time_resp = await asyncio.to_thread(client.get_server_time)
            server_now = datetime.fromtimestamp(int(server_time_resp["result"]["timeNano"]) / 1e9, tz=pytz.UTC)

        print()
        log_info(f"{pre_launch_pooling} seconds left until launch time. Starting to check listing...")
    except asyncio.CancelledError:
        log_warning("Waiting for launch time was cancelled.")
        raise
    except Exception as e:
        log_error(f"Error while waiting for launch time: {e}")
        raise

async def wait_for_pair_listing(client: HTTP, symbol: str):
    log_info(f"Waiting for pair {symbol} to be listed (every {pair_check_interval}s)...")
    while True:
        try:
            info = await asyncio.to_thread(client.get_instruments_info, category="spot")
            listed_symbols = [s['symbol'] for s in info['result']['list']]
            if symbol in listed_symbols:
                log_success(f"Pair {symbol} found on Bybit!")
                return info
            else:
                await asyncio.sleep(pair_check_interval)
        except asyncio.CancelledError:
            log_warning("Waiting for pair listing was cancelled.")
            raise
        except Exception as e:
            log_error(f"Error querying exchange info: {e}. Retrying in {pair_check_interval}s...")
            await asyncio.sleep(pair_check_interval)

async def get_current_price(client: HTTP, symbol: str):
    while True:
        try:
            ticker = await asyncio.to_thread(client.get_tickers, category="spot", symbol=symbol)
            return Decimal(ticker['result']['list'][0]['lastPrice'])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log_error(f"Error getting current price: {e}. Retrying in {price_check_interval} seconds...")
            await asyncio.sleep(price_check_interval)

async def wait_for_order_fill_or_timeout(client: HTTP, symbol: str, order_id: str, timeout: int):
    log_info(f"Waiting for order {order_id} to fill or timeout in {timeout} seconds...")
    start = asyncio.get_event_loop().time()
    while True:
        try:
            order_resp = await asyncio.to_thread(client.get_order_history, category="spot", orderId=order_id, limit=1)
            if order_resp['retCode'] == 0 and order_resp['result']['list']:
                order = order_resp['result']['list'][0]
                if order['orderStatus'] == 'Filled':
                    log_success(f"Order {order_id} filled successfully.")
                    print_order_details(order)
                    return
                elif order['orderStatus'] in ['Cancelled', 'Rejected', 'PartiallyCanceled']:
                    log_warning(f"Order {order_id} ended with status: {order['orderStatus']}")
                    print_order_details(order)
                    return

            if asyncio.get_event_loop().time() - start > timeout:
                log_info(f"Timeout reached. Cancelling order {order_id}...")
                try:
                    await asyncio.to_thread(client.cancel_order, category="spot", symbol=symbol, orderId=order_id)
                    log_info(f"Order {order_id} cancelled due to timeout.")
                except InvalidRequestError as e:
                    if "170213" in str(e):
                        log_warning(f"Order {order_id} no longer exists during cancellation attempt (already filled or cancelled).")
                    else:
                        log_error(f"Error cancelling order {order_id}: {e}")
                return
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            log_warning(f"Waiting for order {order_id} fill/timeout was cancelled.")
            try:
                await asyncio.to_thread(client.cancel_order, category="spot", symbol=symbol, orderId=order_id)
                log_info(f"Order {order_id} cancelled due to task cancellation.")
            except Exception as e:
                log_warning(f"Could not cancel order {order_id} on task cancellation: {e}")
            raise
        except Exception as e:
            log_warning(f"Error checking order status for {order_id}: {e}")
            await asyncio.sleep(0.5)

async def get_price_filter_precision(symbol_info):
    price_filter = symbol_info.get('priceFilter', {})
    tick_size = Decimal(price_filter.get('tickSize', '0.000001'))
    return abs(tick_size.normalize().as_tuple().exponent)

async def get_lot_size_precision(symbol_info):
    lot_size_filter = symbol_info.get('lotSizeFilter', {})
    step_size = Decimal(lot_size_filter.get('qtyStep', '0.000001'))
    return abs(step_size.normalize().as_tuple().exponent)

async def main():
    global client_instance
    client_instance = HTTP(api_key=api_key, api_secret=api_secret)
    try:
        if not await pre_launch_checks(client_instance):
            log_error("API key pre-checks failed. Exiting.")
            return

        await wait_until_launch(client_instance)

        exchange_info = await wait_for_pair_listing(client_instance, pair)

        current_price = await get_current_price(client_instance, pair)

        offset = current_price * price_offset / Decimal('100')
        target_price = current_price - offset

        quantity = tokens_for_sale

        symbol_info = next((s for s in exchange_info['result']['list'] if s['symbol'] == pair), None)

        if not symbol_info:
            log_error(f"Symbol information for {pair} not found in exchange_info. Cannot apply filters.")
            return
            
        price_precision = await get_price_filter_precision(symbol_info)
        target_price = target_price.quantize(Decimal(f'1e-{price_precision}'), rounding=ROUND_DOWN)

        quantity_precision = await get_lot_size_precision(symbol_info)
        quantity = quantity.quantize(Decimal(f'1e-{quantity_precision}'), rounding=ROUND_DOWN)

        log_info(f"Placing limit sell order for {quantity} {pair} at {target_price} USDT (market: {current_price})...")

        retries = 3
        order_placed = False
        for attempt in range(1, retries + 1):
            try:
                log_info(f"Placing order (attempt {attempt}/{retries})...")
                order_resp = await asyncio.to_thread(
                    client_instance.place_order,
                    category="spot",
                    symbol=pair,
                    side="Sell",
                    orderType="Limit",
                    qty=str(quantity),
                    price=str(target_price),
                )
                if order_resp['retCode'] == 0:
                    log_success("Order placed successfully!")
                    order_id = order_resp['result']['orderId']
                    await wait_for_order_fill_or_timeout(client_instance, pair, order_id, order_timeout)
                    order_placed = True
                    break
                else:
                    log_error(f"API error when placing order: {order_resp.get('retMsg')} (Code: {order_resp.get('retCode')})")
            except InvalidRequestError as e:
                log_error(f"API error when placing order: {e}")
            except Exception as e:
                log_error(f"Request error when placing order: {e}")

            if attempt < retries:
                await asyncio.sleep(0.5)

        if not order_placed:
            log_error("All order placement attempts failed. Exiting.")

    except asyncio.CancelledError:
        log_warning("Main task was cancelled.")
    except Exception as e:
        log_error(f"General error in main function: {e}")
    finally:
        log_info("Bybit client does not require explicit connection closure.")


if __name__ == "__main__":
    try:
        log_info("Starting bot...")
        asyncio.run(main())
    except KeyboardInterrupt:
        log_warning("Program interrupted by user (Ctrl-C).")
    finally:
        log_info("Program terminated.")