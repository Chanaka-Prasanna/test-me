"""
MetaAPI Connection Manager
Manages cloud-based MT5 connections for multiple users simultaneously.
Each user gets their own MetaAPI RPC connection, enabling parallel trading
without requiring a local MetaTrader 5 terminal.

Architecture:
    - One global MetaApi client (authenticated with admin token)
    - Per-user MetatraderAccount + RpcMetaApiConnection
    - Account provisioning during user registration
    - Historical candle data via MetaAPI REST endpoint
"""
import asyncio
import aiohttp
from datetime import datetime
from metaapi_cloud_sdk import MetaApi

from config import METAAPI_TOKEN, MT5_DEPLETION_THRESHOLD, MT5_RECOVERY_THRESHOLD, MT5_DEPLETION_ALERT_COOLDOWN_HOURS


# =====================================================
# GLOBAL STATE
# =====================================================

# Global MetaApi client instance
_meta_api = None
_meta_api_lock = None          # created lazily inside running event loop

# Per-user caches: telegram_id -> connection / account objects
_user_connections = {}         # telegram_id -> RpcMetaApiConnection
_user_accounts = {}            # telegram_id -> MetatraderAccount
_last_connection_errors = {}   # telegram_id -> user-friendly error string
_user_balance_state = {}       # telegram_id -> last_known_balance (for recharge detection)
_user_depletion_alert_sent = {}
_user_recovery_alert_sent = {}
_user_depletion_alert_timestamp = {}

# Per-user lock: prevents two coroutines from creating a new connection for
# the same user at the same time (e.g. trade loop + balance check both fire
# right as the websocket rotates).
_user_connection_locks = {}    # telegram_id -> asyncio.Lock

# Global semaphore: caps the number of simultaneous new connection.connect()
# calls.  Without this, a websocket rotation wakes up every active user at
# once and they all call connect() in a storm that crashes the SDK pool.
_connect_semaphore = None      # asyncio.Semaphore, created lazily


def _get_user_lock(telegram_id):
    """Return (creating if needed) the per-user asyncio.Lock."""
    if telegram_id not in _user_connection_locks:
        _user_connection_locks[telegram_id] = asyncio.Lock()
    return _user_connection_locks[telegram_id]


async def _get_meta_api_lock():
    global _meta_api_lock
    if _meta_api_lock is None:
        _meta_api_lock = asyncio.Lock()
    return _meta_api_lock


async def _get_connect_semaphore():
    """At most 2 users may run connection.connect() simultaneously."""
    global _connect_semaphore
    if _connect_semaphore is None:
        _connect_semaphore = asyncio.Semaphore(2)
    return _connect_semaphore



async def _probe_connection_ready(connection, attempts=3, delay_seconds=3):
    """Confirm the RPC connection can actually serve account requests."""
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            info = await connection.get_account_information()
            print(f"[METAAPI] ✅ RPC probe succeeded on attempt {attempt}")
            return info
        except Exception as exc:
            last_error = exc
            print(f"[METAAPI] ⚠️ RPC probe failed (attempt {attempt}/{attempts}): {exc}")
            if attempt < attempts:
                await asyncio.sleep(delay_seconds)

    raise last_error


async def _connection_alive_with_grace(connection, attempts=3, delay_seconds=3):
    """Give the SDK time to self-recover before declaring a connection dead."""
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            await connection.get_account_information()
            return True
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(delay_seconds)

    raise last_error


# =====================================================
# CLIENT INITIALIZATION
# =====================================================

async def get_meta_api():
    """Get or create the global MetaApi client instance."""
    global _meta_api
    if _meta_api is None:
        lock = await _get_meta_api_lock()
        async with lock:
            if _meta_api is None:
                _meta_api = MetaApi(token=METAAPI_TOKEN)
                print("[METAAPI] ✅ MetaApi client initialized")
    return _meta_api


# =====================================================
# ACCOUNT PROVISIONING (called during registration)
# =====================================================

async def provision_account(telegram_id, mt5_login, mt5_password, mt5_server, name=None, bot=None):
    """
    Provision a new MetaAPI cloud account for a user's MT5 credentials.
    This creates a cloud-hosted connection to the user's broker MT5 server.

    Args:
        telegram_id: User's Telegram ID
        mt5_login: MT5 account login number (int or str)
        mt5_password: MT5 trading password
        mt5_server: MT5 broker server name (e.g. "XMGlobal-MT5 5")
        name: Optional display name
        bot: Optional Telegram bot instance — used to alert admin on errors

    Returns:
        str: MetaAPI account ID, or None on failure
    """
    try:
        api = await get_meta_api()

        account = await api.metatrader_account_api.create_account({
            'name': name or f'tgbot_user_{telegram_id}',
            'type': 'cloud',
            'login': str(mt5_login),
            'password': mt5_password,
            'server': mt5_server,
            'platform': 'mt5',
            'magic': 0,
        })

        # Deploy — starts the cloud MT5 instance
        await account.deploy()
        await account.wait_deployed()

        account_id = account.id
        print(f"[METAAPI] ✅ Account provisioned for user {telegram_id}: {account_id}")
        
        # Give the server time to initialize websocket connections (5 second delay)
        print(f"[METAAPI] ⏳ Waiting for account to be ready for websocket connections...")
        await asyncio.sleep(5)
        print(f"[METAAPI] ✅ Account ready for trading")
        
        return account_id

    except Exception as e:
        # Print full validation details if available
        details = getattr(e, 'details', None)
        error_str = str(e) or repr(e) or e.__class__.__name__
        print(f"[METAAPI] ❌ Failed to provision account for {telegram_id}: {e}")
        if details:
            print(f"[METAAPI]    Validation details: {details}")
            if not str(e):
                error_str = f"{error_str} | details={details}"

        # Determine alert message for admin
        if 'top up' in error_str.lower() or 'billing' in error_str.lower():
            print(f"[METAAPI] ⚠️  BILLING ISSUE: MetaAPI subscription has no credits.")
            admin_alert = (
                "⚠️ <b>MetaAPI Billing Alert</b>\n\n"
                "A new user tried to register for MT5 trading, but the "
                "<b>MetaAPI account could not be deployed</b> due to insufficient credits.\n\n"
                f"👤 <b>User Telegram ID:</b> <code>{telegram_id}</code>\n"
                f"🔑 <b>MT5 Login:</b> <code>{mt5_login}</code>\n\n"
                "<b>Action required:</b>\n"
                "• Go to app.metaapi.cloud → Billing → Top up your account, OR\n"
                "• Delete unused deployed accounts to free up a slot.\n\n"
                "The user has been saved in the database. "
                "Re-provision their account after resolving the billing issue."
            )
        elif 'limit' in error_str.lower() or 'quota' in error_str.lower():
            print(f"[METAAPI] ⚠️  QUOTA LIMIT: Maximum cloud accounts reached.")
            admin_alert = (
                "⚠️ <b>MetaAPI Quota Limit Reached</b>\n\n"
                "A new user tried to register for MT5 trading, but the "
                "<b>maximum number of cloud accounts</b> has been reached.\n\n"
                f"👤 <b>User Telegram ID:</b> <code>{telegram_id}</code>\n"
                f"🔑 <b>MT5 Login:</b> <code>{mt5_login}</code>\n\n"
                "<b>Action required:</b>\n"
                "• Go to app.metaapi.cloud → Accounts → Remove unused accounts.\n\n"
                "The user has been saved in the database. "
                "Re-provision their account after freeing up a slot."
            )
        else:
            admin_alert = (
                "⚠️ <b>MetaAPI Provisioning Failed</b>\n\n"
                f"👤 <b>User Telegram ID:</b> <code>{telegram_id}</code>\n"
                f"🔑 <b>MT5 Login:</b> <code>{mt5_login}</code>\n\n"
                f"<b>Error:</b> <code>{error_str[:300]}</code>\n\n"
                "The user has been saved but their MetaAPI account was not created. "
                "Please provision it manually."
            )

        # Send alert to admin via Telegram if bot is available
        if bot:
            try:
                from config import BOT_CREATOR_ID
                bot.send_message(BOT_CREATOR_ID, admin_alert, parse_mode='HTML')
            except Exception as notify_err:
                print(f"[METAAPI] ⚠️ Could not notify admin: {notify_err}")

        return None


# =====================================================
# PER-USER CONNECTION MANAGEMENT
# =====================================================

async def get_user_connection(telegram_id, metaapi_account_id, bot=None):
    """
    Get or create an RPC connection for a specific user.
    Each user gets their own connection — enabling multi-user trading.
    
    CRITICAL: Detects account recharge after depletion and forces fresh connection.
    Also monitors balance and sends alerts when depleted or recovered.

    Args:
        telegram_id: User's Telegram ID
        metaapi_account_id: User's MetaAPI account ID (from Firestore)
        bot: Optional Telegram bot instance for sending alerts

    Returns:
        RpcMetaApiConnection or None
    """
    # ── Fast path: cached connection ────────────────────────────────────────
    if telegram_id in _user_connections:
        conn = _user_connections[telegram_id]

        # Helper: run balance/alert checks and return conn, or signal fall-through
        async def _check_cached(conn):
            account_info = await conn.get_account_information()
            current_balance = account_info.get('balance', 0)
            last_balance = _user_balance_state.get(telegram_id, current_balance)

            # Alert: balance depleted
            if current_balance < MT5_DEPLETION_THRESHOLD and not _user_depletion_alert_sent.get(telegram_id):
                last_alert_time = _user_depletion_alert_timestamp.get(telegram_id)
                now = datetime.now()
                hours_elapsed = (now - last_alert_time).total_seconds() / 3600 if last_alert_time else float('inf')
                if last_alert_time is None or hours_elapsed >= MT5_DEPLETION_ALERT_COOLDOWN_HOURS:
                    _user_depletion_alert_sent[telegram_id] = True
                    _user_depletion_alert_timestamp[telegram_id] = now
                    _user_recovery_alert_sent.pop(telegram_id, None)
                    print(f"[METAAPI] ⚠️ ALERT: User {telegram_id} balance depleted! ${current_balance:.2f}")
                    if bot:
                        try:
                            from config import BOT_CREATOR_ID
                            bot.send_message(BOT_CREATOR_ID,
                                f"⚠️ <b>MT5 Balance Depleted Alert</b>\n\n"
                                f"👤 <b>User Telegram ID:</b> <code>{telegram_id}</code>\n"
                                f"💸 <b>Current Balance:</b> <code>${current_balance:.2f}</code>\n"
                                f"🚨 <b>Threshold:</b> <code>${MT5_DEPLETION_THRESHOLD:.2f}</code>\n\n"
                                f"<b>Account status:</b> Account has insufficient funds for trading.",
                                parse_mode='HTML')
                        except Exception as e:
                            print(f"[METAAPI] ⚠️ Could not send depletion alert: {e}")

            # Alert: balance recovered
            if (current_balance > MT5_RECOVERY_THRESHOLD
                    and _user_depletion_alert_sent.get(telegram_id)
                    and not _user_recovery_alert_sent.get(telegram_id)):
                _user_recovery_alert_sent[telegram_id] = True
                _user_depletion_alert_sent.pop(telegram_id, None)
                print(f"[METAAPI] ✅ Account recharged: User {telegram_id} | ${current_balance:.2f}")
                if bot:
                    try:
                        from config import BOT_CREATOR_ID
                        bot.send_message(BOT_CREATOR_ID,
                            f"✅ <b>MT5 Account Recovered</b>\n\n"
                            f"👤 <b>User Telegram ID:</b> <code>{telegram_id}</code>\n"
                            f"💰 <b>Current Balance:</b> <code>${current_balance:.2f}</code>\n"
                            f"🎯 <b>Recovery Threshold:</b> <code>${MT5_RECOVERY_THRESHOLD:.2f}</code>\n\n"
                            f"<b>Status:</b> Account is now above minimum balance and safe for trading.",
                            parse_mode='HTML')
                    except Exception as e:
                        print(f"[METAAPI] ⚠️ Could not send recovery alert: {e}")

            # Force fresh connection only when balance crosses from depleted → recovered
            if last_balance < MT5_DEPLETION_THRESHOLD and current_balance > MT5_RECOVERY_THRESHOLD:
                print(f"[METAAPI] 💰 Account recovery detected! ${last_balance:.2f} → ${current_balance:.2f}")
                _user_connections.pop(telegram_id, None)
                _user_accounts.pop(telegram_id, None)
                _user_balance_state.pop(telegram_id, None)
                return None  # signal: fall through to new connection

            _user_balance_state[telegram_id] = current_balance
            return conn  # all good

        try:
            result = await _check_cached(conn)
            if result is not None:
                return result
            # Balance-recovery fall-through — create a new connection below
        except Exception as cache_err:
            # The MetaAPI websocket may be mid-rotation (takes ~1 s to reconnect).
            # Wait for the SDK to auto-reconnect before giving up on the cached
            # connection — this prevents every active user from simultaneously
            # firing new connect() calls and crashing the websocket pool.
            print(f"[METAAPI] ⚠️ Cached connection check failed for {telegram_id} "
                  f"(SDK may be reconnecting): {cache_err}")
            for wait_attempt in range(3):
                await asyncio.sleep(3)
                try:
                    result = await _check_cached(conn)
                    if result is not None:
                        print(f"[METAAPI] ✅ Connection self-recovered for {telegram_id} "
                              f"after {wait_attempt + 1} wait(s)")
                        return result
                except Exception:
                    pass
            # Truly dead — fall through to create a new connection
            print(f"[METAAPI] Connection permanently lost for {telegram_id}, creating new one...")
            _user_connections.pop(telegram_id, None)
            _user_accounts.pop(telegram_id, None)

    # ── Slow path: create a new connection ──────────────────────────────────
    # Per-user lock: only one coroutine per user may run the expensive
    # connect() path.  A second coroutine that arrives while the first is
    # still connecting will wait here and then return the now-cached result.
    user_lock = _get_user_lock(telegram_id)
    async with user_lock:
        # Re-check: another coroutine for this user may have connected while
        # we were waiting for the lock.
        if telegram_id in _user_connections:
            return _user_connections[telegram_id]

        # Global semaphore: at most 2 users may call connection.connect() at
        # the same time.  Without this, a websocket rotation wakes every
        # active user at once and they all storm the SDK pool simultaneously.
        semaphore = await _get_connect_semaphore()
        async with semaphore:
            try:
                api = await get_meta_api()
                account = await api.metatrader_account_api.get_account(metaapi_account_id)

                # Ensure account is deployed. Never undeploy/redeploy — it costs credits.
                if account.state != 'DEPLOYED':
                    print(f"[METAAPI] 🔧 Account not deployed yet, deploying...")
                    await account.deploy()
                    await account.wait_deployed()

                # Check broker connection status — NO redeploy, just wait and retry
                await account.reload()
                broker_connected = account.connection_status == "CONNECTED"

                if broker_connected:
                    print(f"[METAAPI] ✅ Broker already connected.")
                else:
                    print(f"[METAAPI] ⏳ Waiting for broker connection (status: {account.connection_status})...")
                    for broker_attempt in range(3):
                        try:
                            await asyncio.wait_for(account.wait_connected(), timeout=30)
                            print(f"[METAAPI] ✅ Broker connected on attempt {broker_attempt + 1}!")
                            broker_connected = True
                            break
                        except Exception as connect_err:
                            print(f"[METAAPI] ⚠️ Broker wait attempt {broker_attempt + 1}/3: {connect_err}")
                            if broker_attempt < 2:
                                await asyncio.sleep(10)
                                await account.reload()

                    if not broker_connected:
                        print(f"[METAAPI] ⚠️ Broker not CONNECTED after retries — attempting RPC anyway...")

                # Connect the RPC connection (up to 5 attempts)
                connection = None
                connect_success = False

                for attempt in range(5):
                    print(f"[METAAPI] 🔌 RPC connect for {metaapi_account_id} (attempt {attempt + 1}/5)...")
                    connection = account.get_rpc_connection()
                    try:
                        await connection.connect()
                        print(f"[METAAPI] ✅ Websocket connected!")
                        connect_success = True
                        break
                    except Exception as ws_error:
                        print(f"[METAAPI] ⚠️ Websocket error on attempt {attempt + 1}: {ws_error}")
                        try:
                            await connection.close()
                        except Exception:
                            pass
                        if attempt < 4:
                            await asyncio.sleep(5)

                if not connect_success:
                    raise Exception("Failed to connect websocket after 5 attempts.")

                # Cache
                _user_connections[telegram_id] = connection
                _user_accounts[telegram_id] = account
                _last_connection_errors.pop(telegram_id, None)

                info = await _probe_connection_ready(connection)
                current_balance = info.get('balance', 0)
                _user_balance_state[telegram_id] = current_balance
                print(f"[METAAPI] ✅ Connected user {telegram_id} | "
                      f"Login: {info.get('login')} | Balance: ${current_balance:.2f}")
                return connection

            except Exception as e:
                error_str = str(e).lower()
                print(f"[METAAPI] ❌ Failed to connect user {telegram_id}: {e}")
                import traceback
                traceback.print_exc()

                # Map exception to a user-friendly message
                if 'connection refused' in error_str or 'connection error' in error_str:
                    friendly = (
                        "❌ Network Connection Error\n\n"
                        "Cannot connect to MetaAPI servers. Possible causes:\n"
                        "• Your internet connection is unstable\n"
                        "• MetaAPI servers are temporarily unavailable\n"
                        "• Your firewall is blocking the connection\n\n"
                        "Please try again in a few moments."
                    )
                elif any(k in error_str for k in ['do not have access', 'access to any', 'no access']):
                    friendly = (
                        "❌ MT5 Connection Failed\n\n"
                        "Your MT5 account could not be accessed.\n"
                        "This is usually caused by:\n"
                        "• Incorrect MT5 login, password, or server name\n"
                        "• Your account not being activated yet\n\n"
                        "Please double-check your details or contact your broker."
                    )
                elif any(k in error_str for k in ['unauthorized', '401', 'forbidden', '403']):
                    friendly = (
                        "❌ MT5 Connection Failed\n\n"
                        "The bot could not authenticate with the trading service.\n"
                        "Please contact the admin to resolve this."
                    )
                elif any(k in error_str for k in ['invalid credentials', 'authentication', 'wrong password',
                                                   'invalid password', 'incorrect password', 'login failed',
                                                   'not authenticated', 'auth error']):
                    friendly = (
                        "❌ MT5 Connection Failed\n\n"
                        "Your MT5 login, password, or server name is incorrect.\n"
                        "Please re-register with the correct details."
                    )
                elif any(k in error_str for k in ['not found', '404', 'no account']):
                    friendly = (
                        "❌ MT5 Connection Failed\n\n"
                        "Your MT5 account was not found in the system.\n"
                        "Please contact admin to set up your account."
                    )
                elif any(k in error_str for k in ['connection refused', 'connection error', 'refused by the server']):
                    friendly = (
                        "❌ MT5 Connection Failed\n\n"
                        "The trading service is temporarily unavailable.\n"
                        "Please try again in a few minutes."
                    )
                elif any(k in error_str for k in ['timeout', 'timed out']):
                    friendly = (
                        "❌ MT5 Connection Timed Out\n\n"
                        "The server did not respond in time.\n"
                        "Please try again."
                    )
                elif any(k in error_str for k in ['not connected to broker', 'disconnected_from_broker']):
                    friendly = (
                        "❌ MT5 Broker Connection Not Ready\n\n"
                        "MetaAPI reached the account, but the broker session is not fully connected yet.\n"
                        "Please wait a little and try again. If it keeps happening, check the MT5 login, password, and server."
                    )
                elif any(k in error_str for k in ['server', 'broker', 'deploy']):
                    friendly = (
                        "❌ MT5 Connection Failed\n\n"
                        "Could not reach your broker's MT5 server.\n"
                        "Please check that your server name is correct."
                    )
                else:
                    friendly = (
                        "❌ MT5 Connection Failed\n\n"
                        "An unexpected error occurred while connecting to MT5.\n"
                        "Please try again or contact admin if the problem persists."
                    )

                _last_connection_errors[telegram_id] = friendly
                return None


def get_last_connection_error(telegram_id):
    """Return the last user-friendly connection error for a user, or None."""
    return _last_connection_errors.get(telegram_id)


async def get_user_account(telegram_id, metaapi_account_id):
    """Get the MetatraderAccount object for a user (for region info etc.)."""
    if telegram_id in _user_accounts:
        return _user_accounts[telegram_id]

    try:
        api = await get_meta_api()
        account = await api.metatrader_account_api.get_account(metaapi_account_id)
        _user_accounts[telegram_id] = account
        return account
    except Exception as e:
        print(f"[METAAPI] ❌ Failed to get account for {telegram_id}: {e}")
        return None


async def disconnect_user(telegram_id):
    """Disconnect and clean up user's MetaAPI resources."""
    if telegram_id in _user_connections:
        try:
            conn = _user_connections[telegram_id]
            await conn.close()
        except Exception as e:
            print(f"[METAAPI] ⚠️ Error closing connection for {telegram_id}: {e}")
        finally:
            _user_connections.pop(telegram_id, None)

    _user_accounts.pop(telegram_id, None)
    print(f"[METAAPI] Disconnected user {telegram_id}")


async def is_user_connected(telegram_id):
    """Check if a user's MetaAPI connection is active."""
    if telegram_id not in _user_connections:
        return False
    try:
        await _connection_alive_with_grace(_user_connections[telegram_id])
        return True
    except Exception as e:
        print(f"[METAAPI] Connection health check failed for {telegram_id}: {e}")
        _user_connections.pop(telegram_id, None)
        _user_accounts.pop(telegram_id, None)
        return False


# =====================================================
# HISTORICAL CANDLE DATA (REST API)
# =====================================================

# Cache to avoid fetching 2000 candles on every loop cycle.
# Structure: {(metaapi_account_id, symbol, timeframe): [candle1, candle2, ...]}
_historical_candles_cache = {}

async def get_historical_candles(telegram_id, metaapi_account_id, symbol, timeframe, count=100):
    """
    Fetch historical candle data using the MetaAPI REST endpoint.

    Endpoint:
        GET /users/current/accounts/{accountId}/historical-market-data/
            symbols/{symbol}/timeframes/{timeframe}/candles

    Args:
        telegram_id: User's Telegram ID (for account lookup)
        metaapi_account_id: MetaAPI account ID
        symbol: Trading symbol (e.g. "XAUUSD")
        timeframe: MetaAPI timeframe string (e.g. "15m", "1h", "4h")
        count: Number of candles to fetch (supports up to 2000 via chunking)

    Returns:
        list of candle dicts [{time, open, high, low, close, tickVolume}, ...] or None
    """
    cache_key = (metaapi_account_id, symbol, timeframe)
    cached_candles = _historical_candles_cache.get(cache_key, [])
    
    # If the cache already has enough candles, we only need to fetch the latest few candles
    # to keep it fully up to date on every scan, which takes only 1 fast API request.
    fetch_count = count if len(cached_candles) < count else 20

    # Determine account region for correct API URL
    account = await get_user_account(telegram_id, metaapi_account_id)
    region = getattr(account, 'region', 'vint-hill') if account else 'vint-hill'

    url = (
        f"https://mt-market-data-client-api-v1.{region}.agiliumtrade.ai"
        f"/users/current/accounts/{metaapi_account_id}"
        f"/historical-market-data/symbols/{symbol}"
        f"/timeframes/{timeframe}/candles"
    )

    headers = {
        'auth-token': METAAPI_TOKEN,
        'Content-Type': 'application/json',
    }

    # ── MetaAPI REST caps `limit` at 1000 per request. ──────────────────────
    # Candles are loaded in a *backwards* direction from `startTime`.
    # To get >= 2000 candles, we leave `startTime` empty to get the most recent,
    # then use the time of the *oldest* candle we received as the `startTime`
    # for the next chunk, effectively walking backward in time.
    # ────────────────────────────────────────────────────────────────────────
    MAX_PER_REQUEST = 1000
    all_candles = []
    remaining = fetch_count
    current_start_time = None
    chunk_index = 0

    try:
        async with aiohttp.ClientSession() as session:
            while remaining > 0:
                batch_size = min(remaining, MAX_PER_REQUEST)

                params = {
                    'limit': batch_size,
                }
                if current_start_time:
                    params['startTime'] = current_start_time

                async with session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        batch = await response.json()
                        if not batch:
                            if chunk_index > 0:
                                print(f"[METAAPI] ℹ️ No more candles returned for {symbol}")
                            break
                        
                        # MetaAPI returns candles chronologically (oldest at index 0).
                        # The start of the next chunk backwards should be the time of the oldest candle here.
                        new_start_time = batch[0].get('time')
                        
                        # If the API returned exactly the same start time, break to avoid infinite loop
                        if current_start_time and new_start_time == current_start_time and len(batch) <= 1:
                            break
                            
                        current_start_time = new_start_time

                        # Prepend older candles so result is chronological (oldest→newest)
                        all_candles = list(batch) + all_candles
                        remaining -= len(batch)
                        
                        if fetch_count > 100:
                            print(f"[METAAPI] 📊 {symbol} {timeframe}: fetched {len(batch)} candles "
                                  f"(chunk {chunk_index + 1}, total so far: {len(all_candles)})")
                        chunk_index += 1
                    else:
                        error_text = await response.text()
                        print(f"[METAAPI] ❌ Historical candles error ({response.status}): {error_text[:200]}")
                        break

                # Small delay between chunks to avoid rate limiting
                if remaining > 0:
                    await asyncio.sleep(0.3)

        # Merge with cached candles and deduplicate
        seen_times = set()
        merged_candles = []
        
        # Combine cache and newly fetched candles
        for c in cached_candles + all_candles:
            t = c.get('time')
            if t not in seen_times:
                seen_times.add(t)
                merged_candles.append(c)

        # Sort chronologically (oldest to newest)
        merged_candles.sort(key=lambda x: x.get('time', ''))
        
        # Keep an upper bound in cache to prevent endless memory growth
        if len(merged_candles) > 3000:
            merged_candles = merged_candles[-3000:]
            
        # Update cache
        _historical_candles_cache[cache_key] = merged_candles

        # Trim to identically precisely what was originally requested
        result = merged_candles[-count:] if len(merged_candles) > count else merged_candles

        if fetch_count > 100:
            print(f"[METAAPI] ✅ {symbol} {timeframe}: {len(result)} total ready, cache fully populated.")
            
        return result if result else None

    except Exception as e:
        print(f"[METAAPI] ❌ Error fetching historical candles for {symbol}: {e}")
        return None


# =====================================================
# ACCOUNT REMOVAL
# =====================================================

async def remove_account(metaapi_account_id):
    """Remove a provisioned MetaAPI account entirely."""
    try:
        api = await get_meta_api()
        account = await api.metatrader_account_api.get_account(metaapi_account_id)
        await account.undeploy()
        await account.remove()
        print(f"[METAAPI] ✅ Account {metaapi_account_id} removed")
    except Exception as e:
        error_str = str(e)
        # If the account no longer exists on MetaAPI, treat it as already removed
        if "not found" in error_str.lower():
            print(f"[METAAPI] ℹ️ Account {metaapi_account_id} not found on MetaAPI (already removed or never synced) — skipping")
        else:
            print(f"[METAAPI] ❌ Error removing account {metaapi_account_id}: {e}")
            raise
