import asyncio
import aiohttp
from metaapi_cloud_sdk import MetaApi
from config import METAAPI_TOKEN
from datetime import datetime, timedelta

async def test_metaapi():
    api = MetaApi(token=METAAPI_TOKEN)
    accounts = await api.metatrader_account_api.get_accounts()
    if not accounts:
        print("No accounts")
        return
    
    account = accounts[0]
    metaapi_account_id = account.id
    region = account.region
    symbol = "XAUUSD" # or something
    # find out actual symbol
    connection = account.get_rpc_connection()
    await connection.connect()
    await connection.wait_synchronized()
    
    timeframe = "5m"
    tf_minutes = 5
    count = 2000
    
    url = (
        f"https://mt-market-data-client-api-v1.{region}.agiliumtrade.ai"
        f"/users/current/accounts/{metaapi_account_id}"
        f"/historical-market-data/symbols/GOLD/timeframes/{timeframe}/candles"
    )

    headers = {
        'auth-token': METAAPI_TOKEN,
        'Content-Type': 'application/json',
    }
    
    # Let's test different limits and startTimes
    async with aiohttp.ClientSession() as session:
        # 1. No startTime, limit 10
        print("\n--- Test 1: No startTime, limit 10 ---")
        params = {'limit': 10}
        async with session.get(url, headers=headers, params=params) as resp:
            data = await resp.json()
            if data:
                print(f"Got {len(data)} candles.")
                print(f"Oldest: {data[0]['time']}")
                print(f"Newest: {data[-1]['time']}")
        
        # 2. Use a startTime from 2 hours ago, limit 10
        print("\n--- Test 2: With startTime 2 hours ago, limit 10 ---")
        start_time = datetime.utcnow() - timedelta(hours=2)
        params = {'startTime': start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z'), 'limit': 10}
        async with session.get(url, headers=headers, params=params) as resp:
            data = await resp.json()
            if data:
                print(f"Got {len(data)} candles.")
                print(f"Oldest: {data[0]['time']}")
                print(f"Newest: {data[-1]['time']}")

if __name__ == "__main__":
    asyncio.run(test_metaapi())
