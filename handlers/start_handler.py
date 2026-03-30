"""
Start command handler - Single User (No Registration)
Simplified version for personal use with local MT5 terminal
"""
from handlers.welcome_messages import get_active_user_welcome
from config import BOT_CREATOR_ID
from handlers.mt5_handler import is_mt5_trading_active, get_mt5_trading_mode


def handle_start_command(bot, message):
    """
    Handle /start command - Single User, No Registration
    Checks if user is authorized and shows dashboard
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Trading User"
    username = message.from_user.username or "N/A"
    
    # Only allow the bot creator
    if user_id != BOT_CREATOR_ID:
        bot.send_message(
            message.chat.id,
            "<b>❌ Unauthorized</b>\n\n"
            "This bot is for personal use only.\n"
            "Contact the bot owner for access.",
            parse_mode='HTML'
        )
        return
    
    # Show the main dashboard
    username_key = f"user_{user_id}"
    
    # Check MT5 trading status
    trading_active = is_mt5_trading_active(username_key)
    trading_mode = get_mt5_trading_mode(username_key) if trading_active else None
    platform = "mt5"
    
    welcome_text, markup = get_active_user_welcome(
        user_name, username, user_id, 
        trading_active, trading_mode, platform
    )
    
    bot.send_message(message.chat.id, welcome_text, parse_mode='HTML', reply_markup=markup)
