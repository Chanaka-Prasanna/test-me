"""
Discover available symbols on your MT5 broker
Run this to see what symbols your broker has
"""
import MetaTrader5 as mt5
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

print("[SYMBOL DISCOVERY] Connecting to MT5 terminal...")
if not mt5.initialize():
    print(f"[ERROR] Failed to initialize MT5: {mt5.last_error()}")
    exit(1)

authorized = mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
if not authorized:
    print(f"[ERROR] Login failed: {mt5.last_error()}")
    mt5.shutdown()
    exit(1)

print(f"[OK] Connected to {MT5_SERVER} | Account: {MT5_LOGIN}")

# Get all symbols
all_symbols = mt5.symbols_get()
if not all_symbols:
    print("[ERROR] No symbols found")
    mt5.shutdown()
    exit(1)

print(f"\n[SYMBOLS] Total symbols on broker: {len(all_symbols)}")

# Search for gold-related symbols
gold_keywords = ["GOLD", "XAU", "XAUUSD"]
gold_symbols = []

for sym in all_symbols:
    sym_name = sym.name.upper()
    if any(kw in sym_name for kw in gold_keywords):
        gold_symbols.append(sym)

if gold_symbols:
    print(f"\n[GOLD SYMBOLS] Found {len(gold_symbols)} gold-related symbols:\n")
    for sym in gold_symbols:
        print(f"  ✓ {sym.name}")
        print(f"    - Digits: {sym.digits}")
        print(f"    - Point: {sym.point}")
        print(f"    - Min Volume: {sym.volume_min}")
        print(f"    - Max Volume: {sym.volume_max}")
        
        # Try to get price
        try:
            if not sym.visible:
                mt5.symbol_select(sym.name, True)
            info = mt5.symbol_info(sym.name)
            if info:
                print(f"    - Bid: {info.bid}")
                print(f"    - Ask: {info.ask}")
        except:
            pass
        print()
else:
    print("\n[NO GOLD] No gold symbols found. Searching all available symbols...")
    print("\nFirst 50 symbols on your broker:\n")
    for i, sym in enumerate(all_symbols[:50]):
        print(f"  {i+1}. {sym.name}")

mt5.shutdown()
print("[DONE] Discovery complete")
