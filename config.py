TELEGRAM_BOT_TOKEN="8636651526:AAHNU2tyeOPcKwVfQjaFhZr9KT8tDFcH0Hk"
BOT_CREATOR_ID=8292575478
MAIN_ADMIN="@dev_7518"
BOT_NAME="MT5 FOREX TRADING BOT (Single User)"

# =====================================================
# APPLICATION MODE (PROD/DEV)
# =====================================================
# "DEV" = Testnet (fake money), "PROD" = Live trading (real money)
APP_MODE = "DEV"  # Options: "DEV" or "PROD"

# =====================================================
# MT5 CREDENTIALS - HARDCODED (Single User, Local Terminal)
# =====================================================
# Note: Using local MT5 terminal (no MetaAPI cloud required)
MT5_LOGIN = 101047292                # MT5 account number
MT5_PASSWORD = "Chanaka123#"         # MT5 master password
MT5_SERVER = "XMGlobal-MT5 5"        # XM Global broker server

# Status Check Settings (in minutes)
STATUS_CHECK_INTERVAL_MINUTES = 60  # Send status report every N minutes (60 = 1 hour)


# =====================================================
# CRASH PROTECTION CONFIGURATION
# =====================================================

# BTC crash detection - monitors BTC price drop as market health indicator
CRASH_REFERENCE_SYMBOL = "BTCUSDT"   # Reference coin for crash detection
CRASH_DROP_THRESHOLD_PCT = -2         # If BTC drops >2% in monitoring window, trigger crash mode
CRASH_MONITORING_WINDOW = "1h"       # Timeframe to check for crash (candle interval)
CRASH_MONITORING_CANDLES = 1         # Number of candles to look back (1 x 1h = 1h latest candle)

# MT5 FOREX-SPECIFIC CRASH DETECTION (Gold XAUUSD drawdown from window high)
# Trades only open if drop_pct is between LOWER and UPPER thresholds (e.g., -2 to +2)
# Otherwise, it detects as a crash and protects capital
MT5_CRASH_LOWER_THRESHOLD = -2              # Lower bound for normal trading (e.g., -2%)
MT5_CRASH_UPPER_THRESHOLD = 2               # Upper bound for normal trading (e.g., +2%)
MT5_CRASH_DROP_THRESHOLD_PCT = -3           # Deprecated (kept for backward compatibility)
MT5_CRASH_MONITORING_TIMEFRAME = "M15"      # 15-minute candles for MT5 forex crash detection
MT5_CRASH_MONITORING_CANDLES = 1            # Number of M15 candles for window high vs last close (raise for wider window)

# Emergency actions
CRASH_CLOSE_ALL_POSITIONS = True     # Close all positions immediately on crash
CRASH_PAUSE_TRADING = True           # Pause opening new positions after crash
CRASH_COOLDOWN_MINUTES = 1440        # Wait 24 hours before resuming after crash

# =====================================================
# MT5 FOREX TRADING CONFIGURATION
# =====================================================

# Forex Symbols to Trade
MT5_FOREX_SYMBOLS = ["XAUUSD"]       # Gold

# MT5 Trading Parameters
MT5_LOT_SIZE = 0.01                  # Default lot size
MT5_MAX_CONCURRENT_TRADES = 1        # Max simultaneous MT5 positions (1 only - single gold trade)
MT5_MAGIC_NUMBER = 234000            # Magic number for order identification

# MT5 Risk Management
MT5_WIN_PERCENTAGE = 45.0            # Legacy percentage TP (kept for compatibility)
MT5_LOSS_PERCENTAGE = 60.0           # Legacy percentage SL (kept for compatibility)
MT5_TAKE_PROFIT_PIPS = 500           # Fixed TP distance in pips for forex gold (deprecated - use balance-based instead)
MT5_STOP_LOSS_PIPS = 1000            # Fixed SL distance in pips for forex gold (deprecated - use balance-based instead)
MT5_BREAKEVEN_TRIGGER_PCT = 20.0     # Move SL to breakeven at 20%
MT5_TRAILING_TRIGGER_PCT = 30.0      # Start trailing at 30%
MT5_TRAILING_STOP_PCT = 10.0         # Trail SL at 10%
MT5_DEVIATION = 10                   # Max price deviation in points

# MT5 BALANCE-BASED LOT & PIP RANGES FOR GOLD (XAUUSD)
# ──────────────────────────────────────────────────────────────────────────
# For XAUUSD: 1 pip = $0.01 per 0.01 lot  →  dollar_risk = sl_pips × lot × 1
# Target risk-per-trade: ≤3% of balance for sub-$50 accounts
#
# SMALL BALANCE PROTECTION (< $50):
#   - Always use minimum lot (0.01) — never increase lot on tiny accounts
#   - Keep SL tight (50 pips = $0.50 max loss) to survive multiple losing trades
#   - TP is 2× the SL distance (1:2 risk/reward) to grow the account
#
# Tier formula:  dollar_risk = sl_pips × lot × 0.01  (XAUUSD pip value per lot)
#   (0,  5] → lot=0.01, SL=50pip → $0.50 loss max  (10% of $5 account)
#   (5, 10] → lot=0.01, SL=50pip → $0.50 loss max  (5–10% of account)
#   (10,20] → lot=0.01, SL=60pip → $0.60 loss max  (~3–6% of account)
#   (20,30] → lot=0.01, SL=70pip → $0.70 loss max  (~2–4% of account)
#   (30,50] → lot=0.01, SL=80pip → $0.80 loss max  (~2–3% of account)
#   (50,100]→ lot=0.02, SL=100pip→ $2.00 loss max  (~2–4% of account)
#   (100,∞) → lot=0.03, SL=150pip→ $4.50 loss max  (~2–5% of account)
# ──────────────────────────────────────────────────────────────────────────
MT5_BALANCE_TIERS = {
    (0,   5):          {"lot": 0.01, "tp_pips": 75, "sl_pips": 300},    # better RR (1:1.25)
    (5,  10):          {"lot": 0.01, "tp_pips": 75, "sl_pips": 600},    # improved RR
    (10, 20):          {"lot": 0.01, "tp_pips": 80, "sl_pips": 1000},   # stable growth
    (20, 30):          {"lot": 0.01, "tp_pips": 100, "sl_pips": 2000},   # controlled risk
    (30, 50):          {"lot": 0.01, "tp_pips": 150, "sl_pips": 3000},   # consistent RR

    (50, 100):         {"lot": 0.01, "tp_pips": 200, "sl_pips": 4000},   # reduced lot (was 0.02)
    
    (100, float('inf')): {"lot": 0.02, "tp_pips": 120, "sl_pips": 2500}, # reduced aggression
}

# Minimum usable balance — bot will skip opening new trades below this
# ($3 gives enough margin for 1 x 0.01 lot XAUUSD trade + buffer)
MT5_MIN_BALANCE_TO_TRADE = 3.0

# MT5 Daily Trade Limit
MT5_DAILY_TRADE_LIMIT_MODE = False   # Disable daily trade limits for now
MT5_DAILY_MAX_TRADES = 5             # Max trades per day (if limit enabled)

# MT5 Signal Analysis Parameters
MT5_SIGNAL_TIMEFRAME = "M5"         # Timeframe for trade signal generation
MT5_TREND_TIMEFRAME = "H1"           # Timeframe for trend verification
MT5_SUPPORT_RESISTANCE_TIMEFRAME = "H4"  # Timeframe for S/R levels
MT5_STOCH_RSI_PERIOD = 14            # StochRSI period
MT5_STOCH_K_SMOOTH = 3               # StochRSI K smoothing
MT5_STOCH_D_SMOOTH = 3               # StochRSI D smoothing
MT5_RSI_PERIOD = 14                  # RSI period
MT5_STOCH_RSI_SHORT_LEVEL = 80       # StochRSI threshold for SHORT signals
MT5_STOCH_RSI_BUY_LEVEL = 20         # StochRSI threshold for BUY signals
MT5_MIN_SIGNAL_SCORE = 0.5           # Minimum signal confidence (0.0 - 1.0)
MT5_CANDLES_FOR_ANALYSIS = 100       # Number of candles to analyze
MT5_SCAN_INTERVAL_SECONDS = 60       # Scan for signals every N seconds
MT5_SLEEP_BETWEEN_SYMBOLS = 2        # Sleep between symbol scans (seconds)

def get_mt5_balance_based_params(balance):
    """
    Get lot size, TP pips, and SL pips based on account balance.

    Args:
        balance (float): Current account balance in USD

    Returns:
        dict: {"lot": float, "tp_pips": int, "sl_pips": int}
              Returns lowest tier for any balance below the first tier minimum.
    """
    for (min_balance, max_balance), params in sorted(MT5_BALANCE_TIERS.items(), reverse=True):
        if balance >= min_balance:
            return params
    # Fallback for very low or zero balance — use the safest (smallest) tier
    return MT5_BALANCE_TIERS[(0, 5)]



   