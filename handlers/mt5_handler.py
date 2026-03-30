"""
MT5 Forex Trading Handler for Telegram Bot (Local MT5 Terminal — Single User)
Manages MT5 trading sessions using direct local terminal connection.
Simplified for personal trading bot with hardcoded credentials.
"""
import asyncio
from datetime import datetime, timedelta

from mt5.local_mt5_connection import (
    connect_mt5,
    disconnect_mt5,
    is_mt5_connected,
    get_mt5_connection,
)
from mt5.mt5_config import (
    FOREX_SYMBOLS,
    LOT_SIZE,
    MAX_CONCURRENT_TRADES,
    WIN_PERCENTAGE,
    LOSS_PERCENTAGE,
    TAKE_PROFIT_PIPS,
    STOP_LOSS_PIPS,
    BREAKEVEN_TRIGGER_PCT,
    TRAILING_TRIGGER_PCT,
    TRAILING_STOP_PCT,
    SIGNAL_TIMEFRAME,
    TREND_TIMEFRAME,
    SUPPORT_RESISTANCE_TIMEFRAME,
    STOCH_RSI_PERIOD,
    STOCH_K_SMOOTH,
    STOCH_D_SMOOTH,
    RSI_PERIOD,
    STOCH_RSI_SHORT_LEVEL,
    STOCH_RSI_BUY_LEVEL,
    SCAN_INTERVAL_SECONDS,
    SLEEP_BETWEEN_SYMBOLS,
)
from config import (
    CRASH_COOLDOWN_MINUTES,
    MT5_CRASH_DROP_THRESHOLD_PCT,
    MT5_CRASH_MONITORING_CANDLES,
    MT5_CRASH_MONITORING_TIMEFRAME,
    get_mt5_balance_based_params,
    MT5_MIN_BALANCE_TO_TRADE,
    BOT_CREATOR_ID,
)
from mt5.mt5_signals import get_trade_signal_mt5
from mt5.mt5_crash_protection import mt5_crash_protector


def _mt5_crash_reference_symbol(username_key):
    """
    Always use Gold (XAU* / GOLD*) for MT5 crash % — not the traded loop symbol.
    Uses broker-resolved name from active_symbols when present.
    """
    syms = mt5_user_data.get(username_key, {}).get("active_symbols") or []
    for s in syms:
        if s and ("XAU" in s.upper() or "GOLD" in s.upper()):
            return s
    return syms[0] if syms else mt5_crash_protector.CRASH_REFERENCE_SYMBOL


# Global storage for MT5 user sessions
mt5_user_data = {}
mt5_user_tasks = {}


def _normalize_ticket(ticket):
    """Store MetaAPI identifiers consistently so sync logic is stable."""
    return str(ticket) if ticket is not None else ""


def _get_positions_for_symbol(username_key, symbol):
    """Return all tracked positions for a symbol."""
    return [
        (ticket, pos)
        for ticket, pos in mt5_user_data[username_key].get("positions", {}).items()
        if pos.get("symbol") == symbol
    ]


def _has_symbol_direction(username_key, symbol, direction):
    """Prevent duplicate same-side positions on the same symbol."""
    return any(
        pos.get("symbol") == symbol and pos.get("direction") == direction
        for pos in mt5_user_data[username_key].get("positions", {}).values()
    )


def _get_mt5_pip_size(symbol, sym_info):
    """Return an effective pip size for MT5 pricing."""
    point = float(sym_info.get("point", 0.00001) or 0.00001)
    digits = int(sym_info.get("digits", 5) or 5)
    symbol_upper = symbol.upper()

    if "XAU" in symbol_upper or "GOLD" in symbol_upper:
        return 0.01

    if digits in (3, 5):
        return point * 10

    return point


def _calculate_mt5_sl_tp(symbol, direction, price, sym_info, tp_pips=None, sl_pips=None):
    """Calculate fixed-pip stop loss and take profit.
    
    Args:
        symbol: Trading pair (e.g., "XAUUSD")
        direction: "BUY" or "SELL"
        price: Current entry price
        sym_info: Symbol info dict with 'digits' and 'point'
        tp_pips: TP distance in pips (uses balance-based default if None)
        sl_pips: SL distance in pips (uses balance-based default if None)
    """
    # Use provided pips or fall back to global config
    if tp_pips is None:
        tp_pips = TAKE_PROFIT_PIPS
    if sl_pips is None:
        sl_pips = STOP_LOSS_PIPS
        
    digits = int(sym_info["digits"])
    pip_size = _get_mt5_pip_size(symbol, sym_info)
    tp_distance = tp_pips * pip_size
    sl_distance = sl_pips * pip_size

    if direction == "BUY":
        sl = round(price - sl_distance, digits)
        tp = round(price + tp_distance, digits)
    else:
        sl = round(price + sl_distance, digits)
        tp = round(price - tp_distance, digits)

    return sl, tp


def is_mt5_trading_active(username_key):
    """Check if MT5 trading is active for a user"""
    if username_key not in mt5_user_data:
        return False
    return mt5_user_data[username_key].get("bot_status") == "Running"


def get_mt5_trading_mode(username_key):
    """Get MT5 trading mode"""
    if username_key not in mt5_user_data:
        return None
    return mt5_user_data[username_key].get("trading_mode")


def initialize_mt5_session(username_key, telegram_id):
    """Initialize MT5 trading session for a user"""
    mt5_user_data[username_key] = {
        "telegram_id": telegram_id,
        "bot_status": "Not Running",
        "trading_mode": None,
        "ctx": None,  # MT5UserContext — set when trading starts
        "lock": asyncio.Lock(),
        "positions": {},  # ticket -> position data
        "active_symbols": FOREX_SYMBOLS.copy(),
        "last_status_time": datetime.now(),
        "crash_notification_sent": False,  # Track if crash notification already sent
        "cooldown_notification_sent": False,  # Track if cooldown notification already sent
        "market_closed_notification_sent": False,  # Track if market closed notification already sent
    }
    print(f"[MT5-SESSION] ✅ Initialized MT5 session for {username_key}")
    return mt5_user_data[username_key]


async def start_mt5_trading(bot, telegram_id, username_key, existing_ctx=None):
    """Start MT5 forex trading loop using local terminal connection"""
    print(f"[MT5-TRADING] 🚀 Starting MT5 trading for {username_key}")

    # RESET crash mode on new session (fresh start after restart)
    mt5_crash_protector.reset_crash_mode()
    print(f"[MT5-TRADING] 🔄 Crash protection reset for fresh trading session")

    if username_key not in mt5_user_data:
        initialize_mt5_session(username_key, telegram_id)
    
    # Reset crash notification flag for fresh start
    mt5_user_data[username_key]["crash_notification_sent"] = False
    mt5_user_data[username_key]["cooldown_notification_sent"] = False
    mt5_user_data[username_key]["market_closed_notification_sent"] = False

    # Connect to local MT5 terminal
    print(f"[MT5-TRADING] 🔌 Connecting to local MT5 terminal...")
    if not connect_mt5():
        print(f"[MT5-TRADING] ❌ Failed to connect to local MT5 terminal")
        bot.send_message(
            telegram_id,
            "❌ <b>MT5 Connection Failed</b>\n\n"
            "Cannot connect to local MT5 terminal.\n"
            "Make sure MetaTrader 5 is running on your computer.",
            parse_mode="HTML"
        )
        return False
    
    # Get connection and verify
    conn = get_mt5_connection()
    if not conn.is_connected():
        print(f"[MT5-TRADING] ❌ MT5 not connected after initialization")
        return False
    
    # Store connection in user data
    mt5_user_data[username_key]["ctx"] = conn
    
    # Verify account info
    account_info = conn.get_account_info()
    if not account_info:
        print(f"[MT5-TRADING] ❌ Cannot retrieve account info")
        bot.send_message(
            telegram_id,
            "❌ <b>Account Error</b>\n\n"
            "Cannot retrieve account information from MT5.",
            parse_mode="HTML"
        )
        return False
    
    print(f"[MT5-TRADING] ✅ Connected to MT5")
    print(f"   Account: {account_info['login']}")
    print(f"   Balance: ${account_info['balance']:,.2f}")
    print(f"   Leverage: 1:{account_info['leverage']}")
    
    mt5_user_data[username_key]["trading_mode"] = "MT5 Forex Trading"
    mt5_user_data[username_key]["bot_status"] = "Running"
    mt5_user_data[username_key]["active_symbols"] = FOREX_SYMBOLS.copy()

    if username_key not in mt5_user_tasks:
        mt5_user_tasks[username_key] = {}

    task = asyncio.create_task(
        mt5_trade_loop(username_key, bot, telegram_id)
    )
    mt5_user_tasks[username_key]["forex"] = task

    print(f"[MT5-TRADING] ✅ MT5 trading task created for {username_key}")
    return True


async def stop_mt5_trading(username_key):
    """Stop MT5 trading loop and disconnect local terminal"""
    print(f"[MT5-TRADING] 🛑 Stopping MT5 trading for {username_key}")

    if username_key in mt5_user_data:
        mt5_user_data[username_key]["bot_status"] = "Stopped"
        # Reset crash notification flag for next session
        mt5_user_data[username_key]["crash_notification_sent"] = False
        mt5_user_data[username_key]["cooldown_notification_sent"] = False
        mt5_user_data[username_key]["market_closed_notification_sent"] = False
        mt5_user_data[username_key]["insufficient_funds_notification_sent"] = False

        if username_key in mt5_user_tasks:
            for task_name, task in mt5_user_tasks[username_key].items():
                if task and not task.done():
                    task.cancel()
                    print(f"[MT5-TRADING] Cancelled {task_name} task for {username_key}")
            mt5_user_tasks[username_key].clear()

        # Disconnect local MT5 terminal
        disconnect_mt5()
        mt5_user_data[username_key]["ctx"] = None

        return True
    return False


async def mt5_trade_loop(username: str, bot, telegram_id: int):
    """Main MT5 trading loop — simplified for local terminal connection"""
    print(f"[MT5-LOOP] 🚀 ENTERED mt5_trade_loop for {username} at {datetime.now()}")
    print(
        "[MT5-CONFIG] "
        f"SignalTF={SIGNAL_TIMEFRAME} | TrendTF={TREND_TIMEFRAME} | "
        f"SupportResistanceTF={SUPPORT_RESISTANCE_TIMEFRAME} | "
        f"CrashTF={MT5_CRASH_MONITORING_TIMEFRAME} x {MT5_CRASH_MONITORING_CANDLES}"
    )
    print(
        "[MT5-CONFIG] "
        f"StochRSI: RSI={RSI_PERIOD}, Stoch={STOCH_RSI_PERIOD}, "
        f"K={STOCH_K_SMOOTH}, D={STOCH_D_SMOOTH}, "
        f"Sell>={STOCH_RSI_SHORT_LEVEL}, Buy<={STOCH_RSI_BUY_LEVEL}"
    )

    last_status_time = datetime.now()
    loop_count = 0

    while mt5_user_data[username]["bot_status"] == "Running":
        loop_count += 1

        # Get local MT5 connection (not MetaAPI context)
        conn = get_mt5_connection()
        if not conn.is_connected():
            print(f"[MT5-LOOP] ❌ MT5 connection lost for {username}")
            await asyncio.sleep(10)
            continue

        # === SIMPLE CRASH PROTECTION ===
        try:
            # Check for market crash by detecting large price drops
            cr_sym = "XAUUSD"  # Simplified - always use XAUUSD for crash detection
            candles = conn.get_candles(cr_sym, MT5_CRASH_MONITORING_TIMEFRAME, MT5_CRASH_MONITORING_CANDLES + 5)
            
            if candles and len(candles) >= 2:
                current_close = candles[-1]['close']
                window_high = max(c['high'] for c in candles[-MT5_CRASH_MONITORING_CANDLES:])
                drop_pct = ((current_close - window_high) / window_high) * 100 if window_high > 0 else 0
                
                if drop_pct <= MT5_CRASH_DROP_THRESHOLD_PCT:  # e.g., -3% or worse
                    print(f"[MT5-LOOP] 🚨 MARKET CRASH DETECTED: {cr_sym} down {drop_pct:.1f}%")
                    mt5_crash_protector.crash_mode = True
                    mt5_crash_protector.crash_triggered_at = datetime.now()
                    
                    # Close all positions
                    positions = conn.get_positions()
                    if positions:
                        for pos in positions:
                            conn.close_position(pos['ticket'])
                            print(f"[MT5-LOOP] ✅ Closed position {pos['ticket']} (crash protection)")
                    
                    bot.send_message(
                        telegram_id,
                        f"🚨 <b>CRASH DETECTED!</b>\n"
                        f"{cr_sym} down {drop_pct:.1f}%\n"
                        f"All positions closed.\n"
                        f"Trading paused for 24 hours.",
                        parse_mode="HTML"
                    )
                    await asyncio.sleep(60)
                    continue
        except Exception as e:
            print(f"[MT5-LOOP] ⚠️ Crash check error: {str(e)[:100]}")

        # === GET ACCOUNT STATUS ===
        try:
            balance = conn.get_balance()
            equity = conn.get_equity()
            
            if balance is None:
                print(f"[MT5-LOOP] ❌ Cannot get account balance")
                await asyncio.sleep(10)
                continue
            
            account_info = conn.get_account_info()
            active_positions = conn.get_positions(symbol="XAUUSD")
            active_count = len(active_positions) if active_positions else 0
            
            print(f"[MT5-LOOP] 🔄 Loop #{loop_count} | Balance: ${balance:.2f} | Equity: ${equity:.2f} | Active: {active_count}/{MAX_CONCURRENT_TRADES}")
            
        except Exception as e:
            print(f"[MT5-LOOP] ⚠️ Error getting account info: {str(e)[:100]}")
            await asyncio.sleep(5)
            continue

        # === PERIODIC STATUS MESSAGE (every 1 hour) ===
        now = datetime.now()
        if (now - last_status_time).total_seconds() > 3600:
            try:
                bot.send_message(
                    chat_id=telegram_id,
                    text=f"📊 <b>MT5 Hourly Update</b>\n"
                         f"💰 Balance: <code>${balance:.2f}</code>\n"
                         f"📈 Equity: <code>${equity:.2f}</code>\n"
                         f"📍 Active Trades: {active_count}/{MAX_CONCURRENT_TRADES}",
                    parse_mode='HTML'
                )
                last_status_time = now
            except Exception as e:
                print(f"[MT5-LOOP] ⚠️ Error sending status: {e}")

        # === PREVENT INSUFFICIENT FUNDS ===
        if balance < MT5_MIN_BALANCE_TO_TRADE:
            print(f"[MT5-LOOP] ⛔ Balance too low (${balance:.2f} < ${MT5_MIN_BALANCE_TO_TRADE:.2f})")
            if not mt5_user_data[username].get("insufficient_funds_notification_sent"):
                try:
                    bot.send_message(
                        telegram_id,
                        f"⛔ <b>Insufficient Funds</b>\n"
                        f"Balance: ${balance:.2f}\n"
                        f"Minimum required: ${MT5_MIN_BALANCE_TO_TRADE:.2f}\n\n"
                        f"Deposit funds to resume trading.",
                        parse_mode="HTML"
                    )
                    mt5_user_data[username]["insufficient_funds_notification_sent"] = True
                except Exception as e:
                    print(f"[MT5-LOOP] ⚠️ Error sending insufficient funds notification: {e}")
            await asyncio.sleep(30)
            continue

        # === MAIN TRADING LOGIC (PLACEHOLDER FOR NOW) ===
        try:
            # TODO: Implement signal analysis and trading logic
            # For now, just maintain the connection and send updates
            pass
        except Exception as e:
            print(f"[MT5-LOOP] ⚠️ Trading logic error: {e}")

        # Sleep before next iteration
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)

    print(f"[MT5-LOOP] 🛑 Exiting trade loop for {username}")


# ===== HELPER FUNCTIONS FOR FUTURE IMPLEMENTATION =====
# These functions are placeholders for when signal analysis and trading are fully implemented

async def sync_mt5_positions(username, ctx=None, bot=None, telegram_id=None):
    """Sync internal position tracking with actual open positions from broker"""
    conn = get_mt5_connection()
    if not conn.is_connected():
        return
    
    try:
        # Get all open positions from broker
        open_positions = conn.get_positions()
        if open_positions is None:
            open_positions = []
        
        open_tickets = {str(p['ticket']): p for p in open_positions}
        
        # Check for closed positions and remove from tracking
        for ticket in list(mt5_user_data[username]["positions"].keys()):
            if ticket not in open_tickets:
                pos = mt5_user_data[username]["positions"][ticket]
                symbol = pos.get("symbol", "Unknown")
                direction = pos.get("direction", "Unknown")
                entry_price = pos.get("entry", 0)
                
                print(f"[MT5-SYNC] Position closed: {symbol} {direction} | Ticket={ticket}")
                
                # Try to get P&L from closed position
                try:
                    # Recent closed deals info would normally come from deal history
                    # For now, just log that position is closed
                    print(f"[MT5-SYNC] ℹ️ {symbol} {direction} closed (entry: {entry_price:.5f})")
                except Exception as e:
                    print(f"[MT5-SYNC] ⚠️ Could not retrieve P&L for {ticket}: {e}")
                
                # Remove from tracking
                del mt5_user_data[username]["positions"][ticket]
                
                # Send notification
                if bot and telegram_id:
                    try:
                        bot.send_message(
                            chat_id=telegram_id,
                            text=f"ℹ️ <b>Position Closed</b>\n\n"
                                 f"💱 <b>Pair:</b> <code>{symbol}</code>\n"
                                 f"📌 <b>Side:</b> <code>{direction}</code>\n"
                                 f"🎫 <b>Ticket:</b> <code>{ticket}</code>\n\n"
                                 f"✅ Position has been closed.",
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        print(f"[MT5-SYNC] ⚠️ Failed to send close notification: {e}")
        
        # Check for new externally-opened positions (opened outside bot)
        for ticket, broker_pos in open_tickets.items():
            if ticket not in mt5_user_data[username]["positions"]:
                mt5_user_data[username]["positions"][ticket] = {
                    "ticket": ticket,
                    "symbol": broker_pos.get("symbol", "Unknown"),
                    "direction": broker_pos.get("type", "BUY"),
                    "entry": broker_pos.get("price_open", 0),
                    "sl": broker_pos.get("sl", 0),
                    "tp": broker_pos.get("tp", 0),
                    "volume": broker_pos.get("volume", 0),
                    "highest_profit_pct": 0.0,
                    "breakeven_set": False,
                    "trailing_active": False,
                }
                print(f"[MT5-SYNC] 📥 Loaded external position: {broker_pos.get('symbol')} {broker_pos.get('type')} | Ticket={ticket}")
                
    except Exception as e:
        print(f"[MT5-SYNC] ❌ Error syncing positions: {e}")


async def manage_mt5_position(username, ticket, bot, telegram_id, ctx=None):
    """
    Manage open position with breakeven and trailing stop logic using local MT5.
    
    - At BREAKEVEN_TRIGGER_PCT (20%): Move SL to entry price (breakeven)
    - At TRAILING_TRIGGER_PCT (30%): Start trailing stop  
    - Trailing: SL follows at peak_profit - TRAILING_STOP_PCT below peak
    """
    conn = get_mt5_connection()
    if not conn.is_connected():
        return
    
    pos = mt5_user_data[username]["positions"].get(ticket)
    if not pos:
        return

    symbol = pos.get("symbol")
    if not symbol:
        return

    try:
        # Get current price for the symbol using configured trading timeframe
        candles = conn.get_candles(symbol, SIGNAL_TIMEFRAME, 1)
        if not candles or len(candles) == 0:
            return
        
        current_price = candles[-1]['close']
        entry = pos["entry"]
        direction = pos["direction"]
        current_sl = pos["sl"]

        # Calculate current P/L percentage
        if direction == "BUY":
            pnl_pct = ((current_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - current_price) / entry) * 100

        # Update highest profit tracking
        if pnl_pct > pos.get("highest_profit_pct", 0):
            pos["highest_profit_pct"] = pnl_pct

        print(f"[MT5-MANAGE] {symbol} {direction} | Entry: {entry:.5f} | Current: {current_price:.5f} | P/L: {pnl_pct:.2f}% | Peak: {pos.get('highest_profit_pct', 0):.2f}%")

        # === BREAKEVEN LOGIC ===
        if pnl_pct >= BREAKEVEN_TRIGGER_PCT and not pos.get("breakeven_set", False):
            if direction == "BUY":
                new_sl = entry * 1.001  # Slightly above entry for spread
            else:
                new_sl = entry * 0.999  # Slightly below entry for SELL
            
            result = conn.modify_position(ticket, new_sl, pos.get("tp"))
            if result:
                pos["sl"] = new_sl
                pos["breakeven_set"] = True
                print(f"[MT5-MANAGE] ✅ {symbol} BREAKEVEN SET | New SL: {new_sl:.5f}")
                try:
                    bot.send_message(
                        chat_id=telegram_id,
                        text=f"🔒 <b>Breakeven Set</b>\n\n"
                             f"💱 <b>Pair:</b> <code>{symbol}</code>\n"
                             f"📊 <b>Profit:</b> <code>{pnl_pct:.2f}%</code>\n"
                             f"🛑 <b>New SL:</b> <code>{new_sl:.5f}</code>\n\n"
                             f"<i>Stop loss moved to breakeven to protect capital.</i>",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"[MT5-MANAGE] ⚠️ Failed to send breakeven notification: {e}")
            return

        # === TRAILING STOP LOGIC ===
        if pnl_pct >= TRAILING_TRIGGER_PCT:
            pos["trailing_active"] = True
            
            # Calculate trailing stop based on peak profit
            peak_profit_pct = pos["highest_profit_pct"]
            locked_profit_pct = peak_profit_pct - TRAILING_STOP_PCT
            
            if direction == "BUY":
                new_sl = entry * (1 + locked_profit_pct / 100)
                if new_sl > current_sl:
                    result = conn.modify_position(ticket, new_sl, pos.get("tp"))
                    if result:
                        pos["sl"] = new_sl
                        print(f"[MT5-MANAGE] 📈 {symbol} TRAILING | New SL: {new_sl:.5f} | Locking {locked_profit_pct:.1f}% profit")
            else:  # SELL
                new_sl = entry * (1 - locked_profit_pct / 100)
                if new_sl < current_sl:
                    result = conn.modify_position(ticket, new_sl, pos.get("tp"))
                    if result:
                        pos["sl"] = new_sl
                        print(f"[MT5-MANAGE] 📉 {symbol} TRAILING | New SL: {new_sl:.5f} | Locking {locked_profit_pct:.1f}% profit")

    except Exception as e:
        print(f"[MT5-MANAGE] ❌ Error managing {ticket}: {e}")


async def get_mt5_balance_async(telegram_id):
    """Get MT5 account balance from local terminal (async)"""
    conn = get_mt5_connection()
    if not conn.is_connected():
        return None
    try:
        return conn.get_balance()
    except Exception:
        return None


def get_mt5_balance():
    """Get MT5 account balance — sync wrapper for backward compatibility."""
    conn = get_mt5_connection()
    if not conn.is_connected():
        return None
    return conn.get_balance()


def get_mt5_trading_status(username_key):
    """Get MT5 trading status for a user"""
    if username_key not in mt5_user_data:
        return None

    return {
        "status": mt5_user_data[username_key].get("bot_status", "Unknown"),
        "trading_mode": mt5_user_data[username_key].get("trading_mode"),
        "active_trades": len(mt5_user_data[username_key].get("positions", {})),
        "balance": get_mt5_balance(),
    }


async def get_detailed_mt5_status_async(username_key):
    """Get detailed MT5 trading status with P&L information (async)"""
    if username_key not in mt5_user_data:
        return None

    conn = get_mt5_connection()
    if not conn.is_connected():
        return get_mt5_trading_status(username_key)

    try:
        # Get full account info from local MT5
        account_info = conn.get_account_info()
        if not account_info:
            return get_mt5_trading_status(username_key)

        balance = account_info.get('balance', 0)
        equity = account_info.get('equity', 0)
        margin = account_info.get('margin', 0)
        free_margin = account_info.get('margin_free', 0)
        unrealized_pnl = equity - balance
        leverage = account_info.get('leverage', 0)
        currency = account_info.get('currency', 'USD')

        # Calculate PnL percentage
        if balance > 0:
            pnl_percentage = (unrealized_pnl / balance) * 100
        else:
            pnl_percentage = 0

        # Get open positions
        positions = conn.get_positions()
        if positions is None:
            positions = []

        positions_detail = []
        for pos in positions:
            entry_price = pos.get('price_open', 0)
            current_price = pos.get('price_current', 0)
            pos_profit = pos.get('profit', 0)
            pos_type = pos.get('type', 'BUY')

            # Calculate position PnL %
            if entry_price > 0:
                if pos_type == "BUY":
                    pos_pnl_pct = ((current_price - entry_price) / entry_price) * 100
                else:
                    pos_pnl_pct = ((entry_price - current_price) / entry_price) * 100
            else:
                pos_pnl_pct = 0

            positions_detail.append({
                "ticket": pos.get('ticket'),
                "symbol": pos.get('symbol', 'Unknown'),
                "side": pos_type,
                "volume": pos.get('volume', 0),
                "entry_price": entry_price,
                "current_price": current_price,
                "sl": pos.get('sl', 0),
                "tp": pos.get('tp', 0),
                "profit": pos_profit,
                "pnl_percentage": pos_pnl_pct,
                "time": pos.get('time_open'),
            })

        return {
            "status": mt5_user_data[username_key].get("bot_status", "Unknown"),
            "trading_mode": mt5_user_data[username_key].get("trading_mode"),
            "active_trades": len(positions_detail),
            "balance": balance,
            "equity": equity,
            "margin": margin,
            "free_margin": free_margin,
            "unrealized_pnl": unrealized_pnl,
            "pnl_percentage": pnl_percentage,
            "leverage": leverage,
            "currency": currency,
            "positions": positions_detail,
        }
    except Exception as e:
        print(f"[MT5-STATS] Error getting detailed status: {e}")
        return get_mt5_trading_status(username_key)


def get_detailed_mt5_status(username_key):
    """Get detailed status — sync wrapper for callback handler compatibility."""
    # Try to run async version if event loop is available
    try:
        from utils.bg_loop import loop
        import asyncio
        future = asyncio.run_coroutine_threadsafe(
            get_detailed_mt5_status_async(username_key), loop
        )
        return future.result(timeout=15)
    except Exception as e:
        print(f"[MT5-STATS] Async status fallback: {e}")
        return get_mt5_trading_status(username_key)
