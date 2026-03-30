"""
Callback handler - Single User, Local MT5 Terminal (No Registration)
Simplified version for personal use without multi-user logic
"""
from handlers.user_settings_handler import (
    show_user_settings,
    prompt_change_name,
    confirm_delete_account,
    process_delete_account
)
from handlers.mt5_handler import (
    initialize_mt5_session,
    start_mt5_trading,
    stop_mt5_trading,
    get_mt5_balance,
    get_detailed_mt5_status,
    is_mt5_trading_active,
    get_mt5_trading_mode,
    MAX_CONCURRENT_TRADES as MT5_MAX_TRADES,
)
from telebot import types
from config import BOT_CREATOR_ID


def safe_edit_and_answer(bot, call, text, keyboard=None, parse_mode='HTML'):
    """Safely edit message and answer callback query - handles timeouts and unchanged messages"""
    try:
        # Try to edit message
        try:
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=keyboard
            )
        except Exception as edit_error:
            error_str = str(edit_error)
            # Ignore these non-critical errors
            if "message is not modified" not in error_str and "query is too old" not in error_str:
                raise
        
        # Try to answer callback query
        try:
            bot.answer_callback_query(call.id)
        except Exception as answer_error:
            # Ignore callback timeout errors - they're expected if user waits too long
            if "query is too old" not in str(answer_error) and "query ID is invalid" not in str(answer_error):
                raise
    except Exception as e:
        print(f"[CALLBACK-SAFE-EDIT] Error: {e}")
        # Final attempt to notify - if this fails, just log it
        try:
            bot.answer_callback_query(call.id, f"⚠️ Error: {str(e)[:40]}", show_alert=False)
        except:
            pass


def safe_answer_callback(bot, call, text=None, show_alert=False):
    """Safely answer callback query - handles timeouts gracefully"""
    try:
        if text:
            bot.answer_callback_query(call.id, text, show_alert=show_alert)
        else:
            bot.answer_callback_query(call.id)
    except Exception as e:
        error_str = str(e)
        # These errors are expected and safe to ignore
        if "query is too old" not in error_str and "query ID is invalid" not in error_str:
            print(f"[CALLBACK-ANSWER] Error: {e}")


def _get_running_trading_keyboard():
    """Keyboard shown while MT5 trading is active."""
    keyboard = types.InlineKeyboardMarkup()
    keyboard.row(
        types.InlineKeyboardButton("🛑 Stop Trading", callback_data="stop_trading"),
        types.InlineKeyboardButton("📊 View Status", callback_data="view_status")
    )
    keyboard.row(
        types.InlineKeyboardButton("💰 Balance", callback_data="view_balance"),
        types.InlineKeyboardButton("🔙 Back", callback_data="user_dashboard")
    )
    return keyboard


def _start_mt5_trading_from_callback(bot, call, user_id, username_key):
    """One-tap MT5 trading start used by both current and legacy buttons."""
    initialize_mt5_session(username_key, user_id)

    # Let the user know the bot is working before the MT5 startup call blocks.
    safe_answer_callback(bot, call, "⏳ Connecting to MT5...", show_alert=False)

    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="<b>⏳ Connecting to MT5...</b>\n\n"
                 "Starting local MT5 connection.\n"
                 "Please wait...",
            parse_mode='HTML',
        )
    except Exception as e:
        if "message is not modified" not in str(e) and "query is too old" not in str(e):
            raise

    from utils.bg_loop import loop, start_background_loop, is_background_loop_running
    import asyncio
    from concurrent.futures import TimeoutError as FutureTimeoutError

    if not is_background_loop_running():
        print("[START_TRADING] Background loop was not running, starting it now")
        start_background_loop()

    print(f"[START_TRADING] Scheduling MT5 trading task for {username_key}")

    future = asyncio.run_coroutine_threadsafe(
        start_mt5_trading(bot, user_id, username_key), loop
    )

    try:
        success = future.result(timeout=20)
    except FutureTimeoutError:
        print(f"[START_TRADING] Timed out waiting for MT5 startup for {username_key}")
        safe_answer_callback(
            bot,
            call,
            "❌ MT5 startup timed out. Check terminal logs.",
            show_alert=True
        )
        return

    if success:
        safe_edit_and_answer(
            bot, call,
            text="<b>🚀 MT5 FOREX TRADING STARTED 🚀</b>\n"
                 "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                 "✅ <b>Status:</b> <u>Running</u>\n"
                 "✅ <b>Pair:</b> XAUUSD (Gold)\n"
                 "✅ <b>Connection:</b> Local MT5 Terminal\n\n"
                 "<i>Trading is now active. Monitor your positions below.</i>",
            keyboard=_get_running_trading_keyboard()
        )
    else:
        safe_answer_callback(bot, call, "❌ Failed to start MT5 trading", show_alert=True)


def handle_callback_query(bot, call):
    """Handle all callback queries from inline buttons - Single user version"""
    callback_data = call.data
    user_id = call.from_user.id
    
    # Verify user is the bot creator
    if user_id != BOT_CREATOR_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized - This bot is for personal use only", show_alert=True)
        return
    
    username_key = f"user_{user_id}"
    
    # ========== USER SETTINGS CALLBACKS ==========
    
    if callback_data == "user_settings":
        show_user_settings(bot, call)
        return
    
    if callback_data == "settings_change_name":
        prompt_change_name(bot, call)
        return
    
    if callback_data == "settings_delete_account":
        confirm_delete_account(bot, call)
        return
    
    if callback_data == "settings_confirm_delete":
        process_delete_account(bot, call)
        return
    
    # ========== MT5 TRADING CALLBACKS ==========
    
    # Start Trading
    if callback_data == "start_trading":
        try:
            # Check if trading is already active
            if is_mt5_trading_active(username_key):
                safe_answer_callback(bot, call, "⚠️ MT5 Trading is already running!", show_alert=True)
                return

            _start_mt5_trading_from_callback(bot, call, user_id, username_key)
        except Exception as e:
            print(f"[START_TRADING] Error: {e}")
            safe_answer_callback(bot, call, f"❌ Error: {str(e)[:50]}", show_alert=True)
        return
    
    # Start MT5 Trading (legacy compatibility for older inline keyboards)
    if callback_data == "trade_mode_mt5":
        try:
            if is_mt5_trading_active(username_key):
                safe_answer_callback(bot, call, "⚠️ MT5 Trading is already running!", show_alert=True)
                return

            _start_mt5_trading_from_callback(bot, call, user_id, username_key)
        except Exception as e:
            print(f"[TRADE_MODE_MT5] Error: {e}")
            safe_answer_callback(bot, call, f"❌ Error: {str(e)[:50]}", show_alert=True)
        return
    
    # Stop Trading
    if callback_data == "stop_trading":
        try:
            from utils.bg_loop import loop
            import asyncio
            
            if is_mt5_trading_active(username_key):
                if asyncio.run_coroutine_threadsafe(stop_mt5_trading(username_key), loop).result():
                    stopped = True
                else:
                    stopped = False
            else:
                stopped = False
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("🚀 Restart Trading", callback_data="start_trading"),
                types.InlineKeyboardButton("📊 View Balance", callback_data="view_balance")
            )
            keyboard.row(
                types.InlineKeyboardButton("🔙 Main Menu", callback_data="user_dashboard")
            )
            
            if stopped:
                msg = (
                    "<b>🛑 MT5 FOREX TRADING STOPPED 🛑</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "✅ All open positions closed\n"
                    "✅ Trading halted\n\n"
                    "<i>You can restart anytime.</i>"
                )
            else:
                msg = (
                    "<b>🛑 TRADING STOPPED 🛑</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "ℹ️ No active trading to stop.\n\n"
                    "<i>You can start trading anytime.</i>"
                )
            
            safe_edit_and_answer(bot, call, text=msg, keyboard=keyboard)
        except Exception as e:
            print(f"[STOP_TRADING] Error: {e}")
            safe_answer_callback(bot, call, f"❌ Error: {str(e)[:50]}", show_alert=True)
        return
    
    # View Balance
    if callback_data == "view_balance":
        try:
            balance = get_mt5_balance()
            currency = "USD"
            
            if balance is not None:
                balance_text = (
                    f"<b>💼 MT5 ACCOUNT BALANCE 💼</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💹 <b>Platform:</b> MT5 (Local Terminal)\n"
                    f"🏦 <b>Broker:</b> XM Global\n"
                    f"💵 <b>Balance:</b> <code>{balance:.2f} {currency}</code>\n"
                    f"📊 <b>Total:</b> <code>{balance:.2f} {currency}</code>"
                )
            else:
                safe_answer_callback(bot, call, "❌ Unable to fetch balance. Connect to MT5 first.", show_alert=True)
                return
            
            keyboard = types.InlineKeyboardMarkup()
            keyboard.row(
                types.InlineKeyboardButton("🔙 Back", callback_data="user_dashboard")
            )
            
            safe_edit_and_answer(bot, call, text=balance_text, keyboard=keyboard)
        except Exception as e:
            print(f"[VIEW_BALANCE] Error: {e}")
            safe_answer_callback(bot, call, f"❌ Error: {str(e)[:50]}", show_alert=True)
        return
    
    # View Trading Status
    if callback_data == "view_status":
        try:
            status = get_detailed_mt5_status(username_key)
            
            if status:
                keyboard = types.InlineKeyboardMarkup()
                keyboard.row(
                    types.InlineKeyboardButton("🔄 Refresh", callback_data="view_status"),
                    types.InlineKeyboardButton("🔙 Back", callback_data="user_dashboard")
                )
                
                # Extract status info
                bot_status = status.get('status') or 'Unknown'
                active_trades = status.get('active_trades', 0)
                balance = status.get('balance', 0)
                unrealized_pnl = status.get('unrealized_pnl', 0)
                pnl_percentage = status.get('pnl_percentage', 0)
                positions = status.get('positions', [])
                equity = status.get('equity', 0)
                margin = status.get('margin', 0)
                free_margin = status.get('free_margin', 0)
                leverage = status.get('leverage', 0)
                
                # Format values
                pnl_emoji = "🟢" if unrealized_pnl >= 0 else "🔴"
                pnl_sign = "+" if unrealized_pnl >= 0 else ""
                
                # Build message
                message = (
                    f"<b>📊 MT5 TRADING STATUS 📊</b>\n"
                    "━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💹 <b>Platform:</b> MT5 (Local Terminal)\n"
                    f"🔄 <b>Status:</b> <u>{bot_status}</u>\n\n"
                    
                    "<b>💰 ACCOUNT SUMMARY</b>\n"
                    "─────────────────────\n"
                    f"💵 <b>Balance:</b> <code>${balance:.2f}</code>\n"
                    f"📊 <b>Equity:</b> <code>${equity:.2f}</code>\n"
                    f"🔒 <b>Margin Used:</b> <code>${margin:.2f}</code>\n"
                    f"💎 <b>Free Margin:</b> <code>${free_margin:.2f}</code>\n"
                    f"⚡ <b>Leverage:</b> 1:{leverage}\n"
                    f"\n{pnl_emoji} <b>Unrealized P&L:</b> <code>{pnl_sign}${unrealized_pnl:.2f}</code>\n"
                    f"📈 <b>P&L %:</b> <code>{pnl_sign}{pnl_percentage:.2f}%</code>\n"
                )
                
                # Add positions details
                message += (
                    f"\n<b>📊 OPEN POSITIONS ({active_trades}/{MT5_MAX_TRADES})</b>\n"
                    "─────────────────────\n"
                )
                
                if positions:
                    for pos in positions:
                        symbol = pos.get('symbol', 'Unknown')
                        side = pos.get('side', '?')
                        pos_pnl = pos.get('profit', pos.get('unrealized_pnl', 0))
                        pos_pnl_pct = pos.get('pnl_percentage', 0)
                        entry = pos.get('entry_price', 0)
                        current = pos.get('current_price', 0)
                        volume = pos.get('volume', 0)
                        sl = pos.get('sl', 0)
                        tp = pos.get('tp', 0)
                        
                        pos_emoji = "🟢" if pos_pnl >= 0 else "🔴"
                        side_emoji = "📈" if side in ["BUY", "LONG"] else "📉"
                        pnl_sign_pos = "+" if pos_pnl >= 0 else ""
                        
                        message += (
                            f"\n{side_emoji} <b>{symbol}</b> ({side}) {volume} lots\n"
                            f"   Entry: <code>{entry:.2f}</code>\n"
                            f"   Current: <code>{current:.2f}</code>\n"
                            f"   SL: <code>{sl:.2f}</code> | TP: <code>{tp:.2f}</code>\n"
                            f"   {pos_emoji} P&L: <code>{pnl_sign_pos}${pos_pnl:.2f} ({pnl_sign_pos}{pos_pnl_pct:.2f}%)</code>\n"
                        )
                else:
                    message += "<i>No open positions</i>\n"
                
                safe_edit_and_answer(bot, call, text=message, keyboard=keyboard)
            else:
                safe_answer_callback(bot, call, "❌ No active session. Start trading first.", show_alert=True)
        except Exception as e:
            print(f"[VIEW_STATUS] Error: {e}")
            safe_answer_callback(bot, call, f"❌ Error: {str(e)[:50]}", show_alert=True)
        return
    
    # User Dashboard
    if callback_data == "user_dashboard":
        try:
            username_key = f"user_{user_id}"
            
            # Check MT5 trading status
            trading_active = is_mt5_trading_active(username_key)
            trading_mode = get_mt5_trading_mode(username_key)
            
            keyboard = types.InlineKeyboardMarkup()
            
            if trading_active:
                keyboard.row(
                    types.InlineKeyboardButton("🛑 Stop Trading", callback_data="stop_trading"),
                    types.InlineKeyboardButton("📊 View Status", callback_data="view_status")
                )
            else:
                keyboard.row(
                    types.InlineKeyboardButton("🚀 Start Trading", callback_data="start_trading"),
                    types.InlineKeyboardButton("💹 View Balance", callback_data="view_balance")
                )
            
            keyboard.row(
                types.InlineKeyboardButton("⚙️ Settings", callback_data="user_settings")
            )
            
            status_text = "🟢 Running" if trading_active else "⭕ Stopped"
            
            welcome_text = (
                f"<b>🤖 MT5 FOREX TRADING BOT 🤖</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"💹 <b>Platform:</b> MT5 (Local Terminal)\n"
                f"📊 <b>Asset:</b> XAUUSD (Gold)\n"
                f"🏦 <b>Broker:</b> XM Global\n\n"
                f"<b>Status:</b> {status_text}\n"
                f"{f'<b>Mode:</b> {trading_mode}' if trading_mode else ''}\n\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"<b>Choose an action:</b>"
            )
            
            safe_edit_and_answer(bot, call, text=welcome_text, keyboard=keyboard)
        except Exception as e:
            print(f"[USER_DASHBOARD] Error: {e}")
            safe_answer_callback(bot, call, f"❌ Error: {str(e)[:50]}", show_alert=True)
        return
    
    # Default response for unknown callbacks
    safe_answer_callback(bot, call, "Unknown action", show_alert=False)
