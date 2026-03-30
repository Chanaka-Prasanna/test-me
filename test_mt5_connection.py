#!/usr/bin/env python3
"""
Test script to verify MT5 local terminal connection
"""
import sys
import asyncio

print("Testing MT5 local terminal connection setup...")
print("=" * 60)

try:
    from mt5.local_mt5_connection import connect_mt5, disconnect_mt5, is_mt5_connected, get_mt5_connection
    print("✅ Imported local_mt5_connection module")
except Exception as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

try:
    print("\n1. Testing MT5 connection...")
    if not connect_mt5():
        print("⚠️  MT5 connection failed - this is expected if MT5 terminal is not running")
        print("   Solution: Start MetaTrader 5 on your computer first")
    else:
        print("✅ Connected to MT5 terminal")
        
        conn = get_mt5_connection()
        
        print("\n2. Retrieving account info...")
        account_info = conn.get_account_info()
        if account_info:
            print(f"   Account: {account_info['login']}")
            print(f"   Balance: ${account_info['balance']:,.2f}")
            print(f"   Equity: ${account_info['equity']:,.2f}")
            print(f"   Server: {account_info['server']}")
            print(f"   Leverage: 1:{account_info['leverage']}")
            print("✅ Account info retrieved successfully")
        else:
            print("❌ Failed to get account info")
        
        print("\n3. Testing candle data retrieval...")
        candles = conn.get_candles("XAUUSD", "M15", 10)
        if candles:
            print(f"   Retrieved {len(candles)} candles for XAUUSD M15")
            latest = candles[-1]
            print(f"   Latest candle: O={latest['open']}, H={latest['high']}, L={latest['low']}, C={latest['close']}")
            print("✅ Candle data retrieved successfully")
        else:
            print("⚠️  Could not retrieve candles (symbol not available on this broker)")
        
        print("\n4. Checking open positions...")
        positions = conn.get_positions()
        if positions is not None:
            print(f"   Found {len(positions)} open positions")
            for pos in positions:
                print(f"   • {pos['symbol']} {pos['type']} {pos['volume']} @ {pos['price_open']:.5f}")
            print("✅ Positions retrieved successfully")
        else:
            print("❌ Failed to get positions")
        
        print("\n5. Disconnecting...")
        disconnect_mt5()
        print("✅ Disconnected from MT5")
        
        if not is_mt5_connected():
            print("✅ Verified disconnection")
        
except Exception as e:
    import traceback
    print(f"❌ Test error: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ All tests completed!")
print("\nNext steps:")
print("1. Make sure MetaTrader 5 is running on your machine")
print("2. Start the bot with: python main.py")
print("3. Send /start to your bot in Telegram")
print("4. Select 'Start Trading' to begin")
