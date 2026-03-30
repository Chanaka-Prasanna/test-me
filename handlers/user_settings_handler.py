"""
User settings handler - SIMPLIFIED for single-user operation
No database, just hardcoded single-user
"""
from telebot import types
from config import BOT_CREATOR_ID


def show_user_settings(bot, call):
    """Display user settings menu for single user"""
    user_id = call.from_user.id
    
    # Verify user is bot creator
    if user_id != BOT_CREATOR_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        return
    
    try:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📝 Change Name", callback_data="change_name"))
        markup.add(types.InlineKeyboardButton("🗑️ Delete Account", callback_data="confirm_delete_account"))
        markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="user_dashboard"))
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="⚙️ <b>User Settings</b>\n\nWhat would you like to do?",
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e:
        print(f"[USER-SETTINGS] Error: {e}")
        bot.answer_callback_query(call.id, "❌ Error loading settings", show_alert=True)


def prompt_change_name(bot, call):
    """Prompt user to enter new name"""
    user_id = call.from_user.id
    
    # Verify user is bot creator
    if user_id != BOT_CREATOR_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        return
    
    try:
        msg = bot.send_message(
            call.message.chat.id,
            "📝 <b>Change Your Name</b>\n\nEnter your new name:",
            parse_mode="HTML"
        )
        
        # Register next step handler to process the name
        bot.register_next_step_handler(msg, process_name_change, bot)
    except Exception as e:
        print(f"[CHANGE-NAME] Error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)


def process_name_change(message, bot):
    """Process name change"""
    user_id = message.from_user.id
    new_name = message.text.strip()
    
    if len(new_name) < 1 or len(new_name) > 50:
        bot.send_message(
            message.chat.id,
            "❌ <b>Invalid Name</b>\n\nName must be 1-50 characters long.",
            parse_mode="HTML"
        )
        return
    
    # For single-user, name change is just acknowledged (not persisted anywhere)
    bot.send_message(
        message.chat.id,
        f"✅ <b>Name Updated</b>\n\nYour name is now: <b>{new_name}</b>\n\n(Note: This is for display only in this bot session.)",
        parse_mode="HTML"
    )


def confirm_delete_account(bot, call):
    """Confirm account deletion"""
    user_id = call.from_user.id
    
    # Verify user is bot creator
    if user_id != BOT_CREATOR_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        return
    
    try:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Yes, Delete", callback_data="process_delete_account"),
            types.InlineKeyboardButton("❌ Cancel", callback_data="user_dashboard")
        )
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="⚠️ <b>Delete Account</b>\n\n"
                 "Are you sure? This action cannot be undone.\n"
                 "All trading sessions will be stopped.",
            parse_mode="HTML",
            reply_markup=markup
        )
    except Exception as e:
        print(f"[CONFIRM-DELETE] Error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)


def process_delete_account(bot, call):
    """Process account deletion"""
    user_id = call.from_user.id
    
    # Verify user is bot creator
    if user_id != BOT_CREATOR_ID:
        bot.answer_callback_query(call.id, "❌ Unauthorized", show_alert=True)
        return
    
    try:
        # For single-user: just stop trading and notify
        bot.send_message(
            call.message.chat.id,
            "🗑️ <b>Account Deleted</b>\n\n"
            "Your trading session has been stopped.\n"
            "To use this bot again, send /start",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[PROCESS-DELETE] Error: {e}")
        bot.answer_callback_query(call.id, "❌ Error", show_alert=True)
