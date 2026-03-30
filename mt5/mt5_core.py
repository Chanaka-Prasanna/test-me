"""
MT5 Connection & Core Trading Functions (Local Terminal)
Handles MT5 operations via local MetaTrader 5 terminal.
All functions are async and take a context (ctx) parameter.

The MT5UserContext dataclass holds connection info for a specific user.
"""
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import asyncio

from mt5.mt5_config import (
    MAGIC_NUMBER, DEVIATION, SUPPORT_RESISTANCE_TIMEFRAME,
)


# =====================================================
# USER CONTEXT — passed to all core functions
# =====================================================

@dataclass
class MT5UserContext:
    """
    Holds local MT5 connection info for a single user.
    """
    connection: Any           # Local MT5Connection instance
    telegram_id: int          # User's Telegram ID
    metaapi_account_id: str   # Unused (for backward compatibility)


# =====================================================
# METAAPI TIMEFRAME MAPPING
# =====================================================
TIMEFRAME_MAP = {
    "M1": "1m",
    "M5": "5m",
    "M15": "15m",
    "M30": "30m",
    "H1": "1h",
    "H4": "4h",
    "D1": "1d",
    "W1": "1w",
}


def _timeframe_to_minutes(timeframe):
    """Convert timeframe string to minutes."""
    return {
        "M1": 1, "M5": 5, "M15": 15, "M30": 30,
        "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
    }.get(timeframe.upper(), 15)


# =====================================================
# LOCAL MT5 CONNECTION MANAGEMENT
# =====================================================

async def connect_mt5(telegram_id, metaapi_account_id, bot=None):
    """
    Connect to local MT5 terminal for a specific user.

    Args:
        telegram_id: User's Telegram ID
        metaapi_account_id: Unused (for backward compatibility)
        bot: Optional Telegram bot instance for alerts

    Returns:
        bool: True if connection successful
    """
    from mt5.local_mt5_connection import connect_mt5 as local_connect
    return local_connect()


async def disconnect_mt5(telegram_id):
    """Disconnect user's local MT5 terminal connection."""
    from mt5.local_mt5_connection import disconnect_mt5 as local_disconnect
    local_disconnect()


async def is_mt5_connected(telegram_id):
    """Check if user's local MT5 terminal connection is active."""
    from mt5.local_mt5_connection import get_mt5_connection
    conn = get_mt5_connection()
    return conn.is_connected() if conn else False



async def get_connection(telegram_id, metaapi_account_id=None, bot=None):
    """Get the local MT5 connection for a user."""
    from mt5.local_mt5_connection import get_mt5_connection
    return get_mt5_connection()


async def create_user_context(telegram_id, metaapi_account_id, bot=None):
    """
    Create an MT5UserContext for a user — uses LOCAL MT5 terminal connection.

    Args:
        telegram_id: User's Telegram ID
        metaapi_account_id: User's MetaAPI account ID (ignored, for compatibility)
        bot: Optional Telegram bot instance for alerts

    Returns:
        MT5UserContext or None on failure
    """
    # Use local MT5 connection instead of MetaAPI
    from mt5.local_mt5_connection import get_mt5_connection
    
    connection = get_mt5_connection()
    if not connection.is_connected():
        try:
            if not connection.connect():
                print(f"[MT5] Failed to connect to local MT5 terminal")
                return None
        except Exception as e:
            print(f"[MT5] Error connecting to MT5: {e}")
            return None
    
    return MT5UserContext(
        connection=connection,
        telegram_id=telegram_id,
        metaapi_account_id=metaapi_account_id,
    )


async def _get_account_information_with_retry(ctx, attempts=3, delay_seconds=1.5):
    """Fetch account info with retry (handles both MetaAPI and local MT5 connections)."""
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            # Call get_account_information() - works with both connection types
            result = ctx.connection.get_account_information()
            if result is None and attempt < attempts:
                await asyncio.sleep(delay_seconds)
                continue
            return result
        except Exception as e:
            last_error = e
            print(f"[MT5] Account info request failed (attempt {attempt}/{attempts}): {e}")

            if attempt < attempts:
                await asyncio.sleep(delay_seconds)

    if last_error:
        raise last_error
    return None


# =====================================================
# ACCOUNT INFO
# =====================================================

async def get_account_balance(ctx):
    """Get account balance in account currency."""
    try:
        info = await _get_account_information_with_retry(ctx)
        return info.get('balance', 0.0)
    except Exception as e:
        print(f"[MT5] Error getting balance: {e}")
        return 0.0


async def get_account_equity(ctx):
    """Get account equity."""
    try:
        info = await _get_account_information_with_retry(ctx)
        return info.get('equity', 0.0)
    except Exception as e:
        print(f"[MT5] Error getting equity: {e}")
        return 0.0


async def get_account_info(ctx):
    """Get full account info dict."""
    try:
        info = await _get_account_information_with_retry(ctx)
        return {
            "login": info.get('login'),
            "balance": info.get('balance', 0),
            "equity": info.get('equity', 0),
            "margin": info.get('margin', 0),
            "free_margin": info.get('freeMargin', 0),
            "profit": info.get('profit', 0),
            "leverage": info.get('leverage', 0),
            "server": info.get('server', ''),
            "currency": info.get('currency', 'USD'),
        }
    except Exception as e:
        print(f"[MT5] Error getting account info: {e}")
        return {}


# =====================================================
# MARKET DATA
# =====================================================

async def get_candles(ctx, symbol, timeframe="M15", count=100):
    """
    Fetch OHLCV candle data via MetaAPI historical data endpoint.

    Args:
        ctx: MT5UserContext
        symbol: Forex pair (e.g., "XAUUSD")
        timeframe: Timeframe string (M1, M5, M15, M30, H1, H4, D1, W1)
        count: Number of candles to fetch

    Returns:
        list of dicts with keys: time, open, high, low, close, volume
        or None on error
    """
    tf = TIMEFRAME_MAP.get(timeframe.upper())
    if tf is None:
        print(f"[MT5] Invalid timeframe: {timeframe}")
        return None

    try:
        # Use local MT5 terminal connection
        candles = ctx.connection.get_candles(symbol, timeframe, count)
        return candles

    except Exception as e:
        print(f"[MT5] Error getting candles for {symbol}: {e}")
        return None


async def get_close_prices(ctx, symbol, timeframe="M15", count=100):
    """Fetch close prices as a list of floats."""
    candles = await get_candles(ctx, symbol, timeframe, count)
    if candles is None:
        return None
    return [c["close"] for c in candles]


async def get_current_price(ctx, symbol):
    """
    Get current bid/ask for a symbol.
    Handles both MetaAPI and local MT5 connections.

    Returns:
        tuple: (bid, ask) or (None, None) on error
    """
    try:
        # Call without await - works with both connection types
        price = ctx.connection.get_symbol_price(symbol)
        if price is None:
            print(f"[MT5] Could not get price for {symbol}")
            return None, None
        return price.get('bid'), price.get('ask')
    except Exception as e:
        print(f"[MT5] Error getting price for {symbol}: {e}")
        return None, None


async def get_symbol_info(ctx, symbol, silent=False):
    """
    Get symbol details (point, digits, trade sizes, etc.)
    Handles both MetaAPI and local MT5 connections.
    """
    try:
        # Call without await - works with both connection types
        spec = ctx.connection.get_symbol_specification(symbol)
        if spec is None:
            if not silent:
                print(f"[MT5] Symbol not found: {symbol}")
            return None
            
        return {
            "symbol": spec.get('symbol', symbol),
            "point": spec.get('point', 0.00001),
            "digits": spec.get('digits', 5),
            "spread": spec.get('spread', 0),
            "volume_min": spec.get('minVolume', 0.01),
            "volume_max": spec.get('maxVolume', 100),
            "volume_step": spec.get('volumeStep', 0.01),
            "trade_contract_size": spec.get('contractSize', 100000),
        }
    except Exception as e:
        if not silent:
            print(f"[MT5] Error getting symbol info for {symbol}: {e}")
        return None

async def resolve_symbol(ctx, base_symbol):
    """Attempt to find the correct suffix for a base symbol (e.g. XAUUSD -> XAUUSDm)."""
    if "XAUUSD" in base_symbol or "GOLD" in base_symbol:
        alts = [base_symbol, "GOLD", "GOLDm", "GOLD.a", "XAUUSD", "XAUUSDm", "XAUUSD.a", "XAUUSD.pro", "XAUUSD.c", "XAUUSD_m"]
    else:
        alts = [base_symbol, base_symbol + "m", base_symbol + ".a", base_symbol + ".pro", base_symbol + ".c"]
    
    print(f"[MT5-RESOLVE] Resolving symbol: {base_symbol} | Trying alternatives: {alts}")
    
    for alt in alts:
        try:
            spec = await get_symbol_info(ctx, alt, silent=True)
            if spec is not None:
                print(f"[MT5-RESOLVE] ✅ Found working symbol: {alt}")
                return alt
        except Exception as e:
            print(f"[MT5-RESOLVE] ⚠️ {alt} failed: {e}")
            pass
    
    print(f"[MT5-RESOLVE] ❌ No working symbol found, defaulting to: {base_symbol}")
    return base_symbol

# =====================================================
# SUPPORT / RESISTANCE (from H4 candles)
# =====================================================

async def find_support_level_mt5(ctx, symbol, timeframe=SUPPORT_RESISTANCE_TIMEFRAME, count=200):
    """Find support level using 10th percentile of lows from candles."""
    candles = await get_candles(ctx, symbol, timeframe, count)
    if candles is None or len(candles) < 5:
        bid, _ = await get_current_price(ctx, symbol)
        return bid * 0.998 if bid else None

    lows = sorted([c["low"] for c in candles])
    idx = max(1, int(len(lows) * 0.1))
    support = lows[idx]
    print(f"[MT5-SUPPORT] {symbol}: Min={min(lows):.5f}, Support(10%)={support:.5f}")
    return support


async def find_resistance_level_mt5(ctx, symbol, timeframe=SUPPORT_RESISTANCE_TIMEFRAME, count=200):
    """Find resistance level using 90th percentile of highs from candles."""
    candles = await get_candles(ctx, symbol, timeframe, count)
    if candles is None or len(candles) < 5:
        _, ask = await get_current_price(ctx, symbol)
        return ask * 1.002 if ask else None

    highs = sorted([c["high"] for c in candles])
    idx = min(len(highs) - 2, int(len(highs) * 0.9))
    resistance = highs[idx]
    print(f"[MT5-RESISTANCE] {symbol}: Max={max(highs):.5f}, Resistance(90%)={resistance:.5f}")
    return resistance


# =====================================================
# ORDER EXECUTION
# =====================================================

async def open_position(ctx, symbol, direction, lot, sl, tp, comment=""):
    """
    Open a market position via MetaAPI.

    Args:
        ctx: MT5UserContext
        symbol: Forex pair
        direction: "BUY" or "SELL"
        lot: Volume (e.g., 0.01)
        sl: Stop loss price
        tp: Take profit price
        comment: Order comment

    Returns:
        dict (MetaAPI trade result) or None on failure
    """
    try:
        options = {
            'comment': comment,
            'magic': MAGIC_NUMBER,
        }

        # Handle both async (MetaAPI) and sync (local MT5) connections
        if direction.upper() == "BUY":
            result = ctx.connection.create_market_buy_order(
                symbol, lot, sl, tp, comment
            )
        elif direction.upper() == "SELL":
            result = ctx.connection.create_market_sell_order(
                symbol, lot, sl, tp, comment
            )
        else:
            print(f"[MT5] Invalid direction: {direction}")
            return None

        # Handle local MT5 result (simple dict) vs MetaAPI result
        if result:
            # For local MT5 results
            if 'ticket' in result:
                print(f"[MT5] ✅ {direction} {lot} {symbol} | SL: {sl:.5f} TP: {tp:.5f} | Ticket: {result['ticket']}")
                return result
            # For MetaAPI results
            elif result.get('stringCode') == 'TRADE_RETCODE_DONE':
                order_id = result.get('orderId', result.get('positionId', ''))
                open_price = result.get('price', 0)
                print(f"[MT5] ✅ {direction} {lot} {symbol} @ {open_price} | SL: {sl:.5f} TP: {tp:.5f} | Order: {order_id}")
                return result
            else:
                string_code = result.get('stringCode', '')
                message = result.get('message', '')
                print(f"[MT5] ❌ Order rejected: {message or string_code}")
                return None
        else:
            print(f"[MT5] ❌ Order failed: no result")
            return None

    except Exception as e:
        print(f"[MT5] Error opening position: {e}")
        raise  # re-raise so open_position_with_retry can inspect the exception type/message


async def open_position_with_retry(ctx, symbol, direction, lot, sl, tp, comment="", max_retries=3, backoff_seconds=2):
    """
    Open a market position via MetaAPI with retry logic.
    Uses exponential backoff for transient failures.

    Returns:
        (result_dict, success: bool, error_msg: str)
    """
    attempt = 0
    last_error = None
    
    # Non-retryable error fragments — abort immediately on these
    NON_RETRYABLE = [
        'TRADE_RETCODE_INVALID_PRICE',
        'TRADE_RETCODE_INVALID_VOLUME',
        'TRADE_RETCODE_MARKET_CLOSED',
        'Market is closed',
        'market is closed',
        'trading disabled',
        'Trade is disabled',
        'invalid volume',
        'invalid price',
    ]

    while attempt < max_retries:
        try:
            print(f"[MT5-ORDER-RETRY] 🔄 Attempting {direction} {symbol} (Attempt {attempt + 1}/{max_retries})")
            
            result = await open_position(ctx, symbol, direction, lot, sl, tp, comment)
            
            if result and result.get('stringCode') == 'TRADE_RETCODE_DONE':
                print(f"[MT5-ORDER-RETRY] ✅ Order placed successfully on attempt {attempt + 1}")
                return result, True, None
            else:
                last_error = result.get('message', result.get('stringCode', 'Unknown error')) if result else 'No result'
                print(f"[MT5-ORDER-RETRY] ⚠️ Order failed (attempt {attempt + 1}): {last_error}")
                
                # Don't retry on permanent/non-transient errors
                if any(nr in str(last_error) for nr in NON_RETRYABLE) or (
                    result and any(nr in result.get('stringCode', '') for nr in NON_RETRYABLE)
                ):
                    print(f"[MT5-ORDER-RETRY] ❌ Non-retryable error — aborting retries: {last_error}")
                    return result, False, last_error
        
        except Exception as e:
            last_error = str(e)
            is_non_retryable = any(nr.lower() in last_error.lower() for nr in NON_RETRYABLE)
            if is_non_retryable:
                print(f"[MT5-ORDER-RETRY] ❌ Non-retryable error — aborting immediately: {last_error}")
                return None, False, last_error
            else:
                import traceback
                print(f"[MT5-ORDER-RETRY] ⚠️ Attempt {attempt + 1} exception: {last_error}")
                traceback.print_exc()
                # For local MT5, connection is persistent
                # Just log the error and retry
                print(f"[MT5-ORDER-RETRY] 🔄 Retrying with local MT5 terminal")
        
        attempt += 1
        
        # Exponential backoff
        if attempt < max_retries:
            wait_time = backoff_seconds * (2 ** (attempt - 1))
            print(f"[MT5-ORDER-RETRY] ⏳ Waiting {wait_time}s before retry...")
            await asyncio.sleep(wait_time)
    
    print(f"[MT5-ORDER-RETRY] ❌ Failed after {max_retries} attempts: {last_error}")
    return None, False, last_error


async def close_position(ctx, position_id, max_retries=3, backoff_seconds=2):
    """
    Close an open position by position ID, with retry on transient connection errors.
    Handles both MetaAPI (async, returns dict) and local MT5 (sync, returns bool).

    Args:
        ctx: MT5UserContext
        position_id: Position ID (string or int)

    Returns:
        dict/bool (result) or None on failure
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            # Call close_position (works with both connection types)
            result = ctx.connection.close_position(int(position_id) if isinstance(position_id, str) and position_id.isdigit() else position_id)

            # Handle local MT5 result (boolean)
            if isinstance(result, bool):
                if result:
                    print(f"[MT5] ✅ Closed position {position_id}")
                    return result
                else:
                    print(f"[MT5] ❌ Close failed for {position_id}: broker rejection")
                    return None
            # Handle MetaAPI result (dict)
            elif result and result.get('stringCode') == 'TRADE_RETCODE_DONE':
                print(f"[MT5] ✅ Closed position {position_id}")
                return result
            else:
                error_msg = (result.get('message', 'Unknown error') if result else 'No result')
                print(f"[MT5] ❌ Close failed for {position_id}: {error_msg}")
                return None  # broker-level rejection — don't retry

        except Exception as e:
            last_error = str(e)
            print(f"[MT5] Error closing position {position_id} (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                # Refresh cached connection on connection errors before retrying
                if any(k in last_error.lower() for k in ['timeout', 'disconnect', 'not connected', 'websocket']):
                    # Local MT5 connection is persistent, skip refresh
                    pass
                await asyncio.sleep(backoff_seconds * attempt)

    print(f"[MT5] ❌ close_position failed after {max_retries} attempts: {last_error}")
    return None


async def modify_position_sl(ctx, position_id, new_sl, new_tp=None, max_retries=3, backoff_seconds=2):
    """
    Modify the stop loss (and optionally take profit) of an open position,
    with retry on transient connection errors. Handles both MetaAPI and local MT5.

    Args:
        ctx: MT5UserContext
        position_id: Position ID (string or int)
        new_sl: New stop loss price
        new_tp: New take profit price (optional)

    Returns:
        dict/bool (result) or None on failure
    """
    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            # Convert position_id to int if needed
            pos_id = int(position_id) if isinstance(position_id, str) and position_id.isdigit() else position_id
            
            # Call modify_position with (ticket, sl, tp) - works with both connection types
            result = ctx.connection.modify_position(pos_id, new_sl, new_tp)

            # Handle local MT5 result (boolean)
            if isinstance(result, bool):
                if result:
                    tp_str = f" | New TP: {new_tp:.5f}" if new_tp else ""
                    print(f"[MT5] ✅ Modified position {position_id} | New SL: {new_sl:.5f}{tp_str}")
                    return result
                else:
                    print(f"[MT5] ❌ Modify failed for {position_id}: broker rejection")
                    return None
            # Handle MetaAPI result (dict)
            elif result and result.get('stringCode') == 'TRADE_RETCODE_DONE':
                print(f"[MT5] ✅ Modified position {position_id} | New SL: {new_sl:.5f}")
                return result
            else:
                error_msg = (result.get('message', 'Unknown error') if result else 'No result')
                print(f"[MT5] ❌ Modify failed for {position_id}: {error_msg}")
                return None  # broker-level rejection — don't retry

        except Exception as e:
            last_error = str(e)
            print(f"[MT5] Error modifying position {position_id} (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                if any(k in last_error.lower() for k in ['timeout', 'disconnect', 'not connected', 'websocket']):
                    # Local MT5 connection is persistent, skip refresh
                    pass
                await asyncio.sleep(backoff_seconds * attempt)

    print(f"[MT5] ❌ modify_position_sl failed after {max_retries} attempts: {last_error}")
    return None


# =====================================================
# POSITION QUERIES
# =====================================================

async def get_open_positions(ctx, magic_only=True):
    """
    Get all open positions (optionally filtered by magic number).
    Handles both MetaAPI (async) and local MT5 (sync) connections.

    Returns:
        list of position dicts
    """
    try:
        # Call get_positions (works with both connection types)
        positions = ctx.connection.get_positions()
        if positions is None:
            return []

        result = []
        for pos in positions:
            pos_magic = pos.get('magic', 0)
            if magic_only and pos_magic != MAGIC_NUMBER:
                continue

            # Normalize position type
            raw_type = str(pos.get('type', ''))
            if 'BUY' in raw_type.upper():
                pos_type = "BUY"
            elif 'SELL' in raw_type.upper():
                pos_type = "SELL"
            else:
                pos_type = raw_type

            time_val = pos.get('time', datetime.utcnow())
            if isinstance(time_val, str):
                try:
                    time_val = datetime.fromisoformat(time_val.replace('Z', '+00:00'))
                except Exception:
                    time_val = datetime.utcnow()

            result.append({
                "ticket": pos.get('id'),
                "symbol": pos.get('symbol', ''),
                "type": pos_type,
                "volume": pos.get('volume', 0),
                "price_open": pos.get('openPrice', 0),
                "price_current": pos.get('currentPrice', 0),
                "sl": pos.get('stopLoss', 0),
                "tp": pos.get('takeProfit', 0),
                "profit": (pos.get('profit', 0)
                           + pos.get('swap', 0)
                           + pos.get('commission', 0)),
                "magic": pos_magic,
                "comment": pos.get('comment', ''),
                "time": time_val,
            })
        return result

    except Exception as e:
        print(f"[MT5] Error getting positions: {e}")
        return []


async def get_active_positions_count(ctx, magic_only=True):
    """Get count of currently open positions."""
    positions = await get_open_positions(ctx, magic_only)
    return len(positions)


# =====================================================
# ORDER & DEAL HISTORY (For P&L Tracking)
# =====================================================

# MQL5 ENUM_DEAL_ENTRY: IN=0, OUT=1, INOUT=2, OUT_BY=3
_MT5_DEAL_ENTRY_OUT = frozenset((1, 2, 3))


def _deal_read(deal, key, default=None):
    """Read deal fields from MetaAPI dicts or SDK objects (camelCase / snake_case)."""
    if isinstance(deal, dict):
        if key in deal:
            return deal[key]
        alt = {"positionId": "position_id", "entryType": "entry_type"}.get(key)
        if alt and alt in deal:
            return deal[alt]
        return deal.get(key, default)
    v = getattr(deal, key, None)
    if v is not None:
        return v
    alt = {"positionId": "position_id", "entryType": "entry_type"}.get(key)
    if alt:
        return getattr(deal, alt, default)
    return default


def _is_closing_deal_entry(entry_type) -> bool:
    """True if this deal closes (or opens+closes) a position — not a bare IN entry."""
    if entry_type is None:
        return False
    if isinstance(entry_type, (int, float)):
        return int(entry_type) in _MT5_DEAL_ENTRY_OUT
    if isinstance(entry_type, str):
        st = entry_type.strip()
        if st.isdigit():
            return int(st) in _MT5_DEAL_ENTRY_OUT
    s = str(entry_type).upper()
    return "OUT" in s


async def get_history_deals(ctx, lookback_hours=24):
    """
    Get history deals for the last N hours via time-range fallback.
    Tries multiple MetaAPI method names for compatibility.
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=lookback_hours)

        for method_name in ('get_deals_by_time_range', 'get_deals'):
            method = getattr(ctx.connection, method_name, None)
            if method is None:
                continue
            try:
                deals = await method(start_time, end_time)
            except Exception as e:
                print(f"[MT5] {method_name} failed: {e}")
                continue

            if deals is None:
                continue

            # Convert to a plain list so subscript access always works,
            # regardless of whether MetaAPI returns a list, generator, or
            # custom iterable.
            try:
                deals = list(deals)
            except Exception:
                pass

            print(f"[MT5] Fetched {len(deals)} deals via {method_name}")
            return deals

        return []
    except Exception as e:
        print(f"[MT5] Error fetching history deals: {e}")
        return []

def _is_real_deal(deal) -> bool:
    """True if this is a proper deal dict/object (not a bare string/ID)."""
    if isinstance(deal, str):
        return False
    if isinstance(deal, dict):
        return "profit" in deal or "entryType" in deal or "symbol" in deal
    return hasattr(deal, "profit") or hasattr(deal, "entryType")


async def get_position_realized_pnl(ctx, ticket):
    """
    Calculate realized P&L for a specific position ticket from history.
    Returns (profit_amount, percent) or (None, None) if not found.

    Strategy:
      1. Try get_deals_by_position(ticket) — direct MetaAPI lookup.
         Some SDK versions return bare ID strings instead of deal objects;
         if so, discard and fall through.
      2. Fall back to time-range search filtered by positionId.
      3. Accept any deal whose entryType indicates a close (OUT / OUT_BY / INOUT).
    """
    target_ticket = str(ticket)

    # ── Step 1: direct position lookup ──────────────────────────────────────
    deals = []
    for method_name in ('get_deals_by_position', 'get_history_deals_by_position'):
        method = getattr(ctx.connection, method_name, None)
        if method is None:
            continue
        try:
            raw = await method(target_ticket)
            if raw:
                if all(_is_real_deal(d) for d in raw):
                    deals = raw
                    print(f"[MT5] Found {len(deals)} deals for position {ticket} via {method_name}")
                    break
                else:
                    print(f"[MT5-DEBUG] {method_name} returned non-deal items "
                          f"(e.g. {type(raw[0]).__name__}: {str(raw[0])[:80]}), skipping to time-range")
        except Exception as e:
            print(f"[MT5] {method_name}({ticket}) failed: {e}")

    # ── Step 2: time-range fallback ──────────────────────────────────────────
    if not deals:
        all_deals = await get_history_deals(ctx, lookback_hours=48)
        deals = [
            d for d in all_deals
            if _is_real_deal(d) and str(_deal_read(d, "positionId") or "") == target_ticket
        ]
        if deals:
            print(f"[MT5] Found {len(deals)} deals for position {ticket} via time-range search")

    if not deals:
        print(f"[MT5] No history deals found for position {ticket}")
        return None, None

    # ── Step 3: sum P&L and detect closing deal ──────────────────────────────
    total_profit = 0.0
    found_closing_deal = False

    for deal in deals:
        profit = float(_deal_read(deal, "profit") or 0)
        swap = float(_deal_read(deal, "swap") or 0)
        commission = float(_deal_read(deal, "commission") or 0)
        total_profit += profit + swap + commission

        et = _deal_read(deal, "entryType")
        if _is_closing_deal_entry(et):
            found_closing_deal = True

    if not found_closing_deal and len(deals) >= 2:
        found_closing_deal = True

    if found_closing_deal:
        print(f"[MT5] Realized P&L for position {ticket}: ${total_profit:.2f}")
        return total_profit, 0.0

    return None, None

