"""
Status monitoring - SIMPLIFIED for single-user operation
No database queries, just periodic MT5 status updates
"""
import threading
import time
import traceback
from datetime import datetime
from config import BOT_CREATOR_ID, STATUS_CHECK_INTERVAL_MINUTES, BOT_NAME, APP_MODE


def get_bot_statistics():
    """Get simple bot statistics for single-user"""
    try:
        # For single-user: just return basic info
        return {
            "total_users": 1,
            "active_users": 1,
            "bot_name": BOT_NAME,
            "mode": APP_MODE,
            "uptime": "Running"
        }
    except Exception as e:
        print(f"[STATUS-MONITOR] Error gathering stats: {e}")
        return None


def send_status_to_admin(bot):
    """Send status update to admin (single user)"""
    try:
        stats = get_bot_statistics()
        if not stats:
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode_emoji = "🟢" if APP_MODE == "DEV" else "🔴"
        
        message = (
            f"{mode_emoji} <b>{BOT_NAME}</b> - Status Report\n\n"
            f"⏰ <b>Time</b>: {timestamp}\n"
            f"🤖 <b>Mode</b>: {APP_MODE}\n"
            f"✅ <b>Status</b>: Running\n\n"
            f"📊 <b>Statistics</b>:\n"
            f"• Total Users: {stats['total_users']}\n"
            f"• Active Users: {stats['active_users']}\n"
        )
        
        bot.send_message(
            BOT_CREATOR_ID,
            message,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"[STATUS-REPORT] Error sending status to admin: {e}")
        traceback.print_exc()


def start_status_monitor(bot):
    """Start periodic status monitoring thread"""
    def monitor_loop():
        print(f"[STATUS-MONITOR] Started (interval: {STATUS_CHECK_INTERVAL_MINUTES} minutes)")
        
        while True:
            try:
                time.sleep(STATUS_CHECK_INTERVAL_MINUTES * 60)
                send_status_to_admin(bot)
            except Exception as e:
                print(f"[STATUS-MONITOR] Loop error: {e}")
                traceback.print_exc()
                time.sleep(60)  # Wait 1 minute before retrying on error
    
    # Start monitoring in background thread
    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    print("[STATUS-MONITOR] ✅ Monitoring thread started")
