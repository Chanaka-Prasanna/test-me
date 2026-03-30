"""
Local MT5 Terminal Connection Manager
Handles connection to MetaTrader 5 running locally on the machine.
Replaces MetaAPI cloud with direct local terminal communication.
"""

import MetaTrader5 as mt5
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from config import MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

print(f"[MT5-CONN] Loading MetaTrader5 library")


class MT5Connection:
    """Manages connection to local MT5 terminal"""
    
    def __init__(self):
        self.connected = False
        self.connection_time = None
        self.account_info = None
        self.last_error = None
        
    def connect(self) -> bool:
        """
        Connect to local MT5 terminal
        Returns: True if successful, False otherwise
        """
        try:
            if self.connected:
                return True
            
            print(f"[MT5-CONN] 🔌 Connecting to MT5 terminal...")
            print(f"[MT5-CONN] Server: {MT5_SERVER} | Login: {MT5_LOGIN}")
            
            # Initialize MetaTrader5 connection
            if not mt5.initialize():
                error_msg = f"Failed to initialize MT5: {mt5.last_error()}"
                self.last_error = error_msg
                print(f"[MT5-CONN] ❌ {error_msg}")
                return False
            
            # Try to login
            authorized = mt5.login(
                login=MT5_LOGIN,
                password=MT5_PASSWORD,
                server=MT5_SERVER
            )
            
            if not authorized:
                error_msg = f"Login failed: {mt5.last_error()}"
                self.last_error = error_msg
                print(f"[MT5-CONN] ❌ {error_msg}")
                mt5.shutdown()
                return False
            
            # Get account info
            self.account_info = mt5.account_info()
            if self.account_info is None:
                error_msg = f"Cannot get account info: {mt5.last_error()}"
                self.last_error = error_msg
                print(f"[MT5-CONN] ❌ {error_msg}")
                mt5.shutdown()
                return False
            
            self.connected = True
            self.connection_time = datetime.now()
            print(f"✅ [MT5-CONN] Connected to account {self.account_info.login}")
            print(f"   Balance: ${self.account_info.balance:,.2f}")
            print(f"   Equity: ${self.account_info.equity:,.2f}")
            print(f"   Free Margin: ${self.account_info.margin_free:,.2f}")
            
            return True
            
        except Exception as e:
            error_msg = f"Connection exception: {str(e)}"
            self.last_error = error_msg
            print(f"[MT5-CONN] ❌ {error_msg}")
            return False
    
    def disconnect(self):
        """Disconnect from MT5 terminal"""
        if self.connected:
            try:
                mt5.shutdown()
                self.connected = False
                print(f"[MT5-CONN] ✅ Disconnected from MT5")
            except Exception as e:
                print(f"[MT5-CONN] ⚠️ Error during disconnect: {e}")
    
    def is_connected(self) -> bool:
        """Check if connected to MT5"""
        if not self.connected:
            return False
        
        try:
            # Verify connection by getting account info
            info = mt5.account_info()
            return info is not None
        except Exception:
            self.connected = False
            return False
    
    def get_balance(self) -> Optional[float]:
        """Get current account balance"""
        if not self.is_connected():
            return None
        
        try:
            info = mt5.account_info()
            return float(info.balance) if info else None
        except Exception as e:
            print(f"[MT5-CONN] Error getting balance: {e}")
            return None
    
    def get_equity(self) -> Optional[float]:
        """Get current account equity"""
        if not self.is_connected():
            return None
        
        try:
            info = mt5.account_info()
            return float(info.equity) if info else None
        except Exception as e:
            print(f"[MT5-CONN] Error getting equity: {e}")
            return None
    
    def get_free_margin(self) -> Optional[float]:
        """Get free margin available for trading"""
        if not self.is_connected():
            return None
        
        try:
            info = mt5.account_info()
            return float(info.margin_free) if info else None
        except Exception as e:
            print(f"[MT5-CONN] Error getting free margin: {e}")
            return None
    
    def get_account_info(self) -> Optional[Dict]:
        """Get full account information"""
        if not self.is_connected():
            return None
        
        try:
            info = mt5.account_info()
            if not info:
                return None
            
            return {
                "login": info.login,
                "server": info.server,
                "balance": float(info.balance),
                "equity": float(info.equity),
                "margin": float(info.margin),
                "margin_free": float(info.margin_free),
                "margin_level": float(info.margin_level),
                "currency": info.currency,
                "leverage": info.leverage
            }
        except Exception as e:
            print(f"[MT5-CONN] Error getting account info: {e}")
            return None
    
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        count: int = 100,
        start_time: Optional[datetime] = None
    ) -> Optional[List]:
        """
        Get historical candle data
        
        Args:
            symbol: Symbol name (e.g., "XAUUSD")
            timeframe: Timeframe string ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
            count: Number of candles to retrieve
            start_time: Optional start time (if None, gets last N candles)
        
        Returns:
            List of candle dictionaries or None if error
        """
        if not self.is_connected():
            return None
        
        try:
            # First, ensure the symbol is selected on the MT5 terminal
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                print(f"[MT5-CONN] Symbol {symbol} not found on broker")
                return None
            
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    print(f"[MT5-CONN] Cannot select symbol {symbol} for candle retrieval")
                    return None
            
            # Convert timeframe string to MT5 constant
            tf_map = {
                "M1": mt5.TIMEFRAME_M1,
                "M5": mt5.TIMEFRAME_M5,
                "M15": mt5.TIMEFRAME_M15,
                "M30": mt5.TIMEFRAME_M30,
                "H1": mt5.TIMEFRAME_H1,
                "H4": mt5.TIMEFRAME_H4,
                "D1": mt5.TIMEFRAME_D1,
            }
            
            tf = tf_map.get(timeframe)
            if tf is None:
                print(f"[MT5-CONN] Unknown timeframe: {timeframe}")
                return None
            
            # Get candles
            if start_time:
                rates = mt5.copy_rates_from(symbol, tf, start_time, count)
            else:
                rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
            
            if rates is None or len(rates) == 0:
                print(f"[MT5-CONN] No candles found for {symbol} {timeframe}")
                return None
            
            # Convert to list of dicts
            candles = []
            for rate in rates:
                candles.append({
                    "time": datetime.fromtimestamp(rate["time"]),
                    "open": float(rate["open"]),
                    "high": float(rate["high"]),
                    "low": float(rate["low"]),
                    "close": float(rate["close"]),
                    "volume": int(rate["tick_volume"]),
                    "real_volume": int(rate["real_volume"]) if "real_volume" in rate else None
                })
            
            return candles
            
        except Exception as e:
            print(f"[MT5-CONN] Error getting candles for {symbol}: {e}")
            return None
    
    def get_positions(self, symbol: Optional[str] = None) -> Optional[List]:
        """
        Get open positions
        
        Args:
            symbol: Filter by symbol (e.g., "XAUUSD"), or None for all
        
        Returns:
            List of position dictionaries or None if error
        """
        if not self.is_connected():
            return None
        
        try:
            if symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()
            
            if positions is None:
                return []
            
            # Convert to list of dicts
            pos_list = []
            for pos in positions:
                pos_list.append({
                    "ticket": int(pos.ticket),
                    "symbol": pos.symbol,
                    "type": "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL",
                    "volume": float(pos.volume),
                    "price_open": float(pos.price_open),
                    "price_current": float(pos.price_current),
                    "sl": float(pos.sl) if pos.sl > 0 else None,
                    "tp": float(pos.tp) if pos.tp > 0 else None,
                    "profit": float(pos.profit),
                    "time_open": datetime.fromtimestamp(pos.time),
                    "comment": pos.comment
                })
            
            return pos_list
            
        except Exception as e:
            print(f"[MT5-CONN] Error getting positions: {e}")
            return None
    
    def open_position(
        self,
        symbol: str,
        order_type: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "",
        magic: int = 0,
        deviation: int = 20
    ) -> Optional[int]:
        """
        Open a trading position
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSD")
            order_type: "BUY" or "SELL"
            volume: Lot size (e.g., 0.01)
            price: Entry price
            sl: Stop loss price (optional)
            tp: Take profit price (optional)
            comment: Order comment
            magic: Magic number for order identification
            deviation: Deviation for price slippage (in points)
        
        Returns:
            Ticket number if successful, None if error
        """
        if not self.is_connected():
            return None
        
        try:
            # Check symbol availability
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                print(f"[MT5-CONN] Symbol {symbol} not found")
                return None
            
            if not symbol_info.visible:
                if not mt5.symbol_select(symbol, True):
                    print(f"[MT5-CONN] Cannot select symbol {symbol}")
                    return None
            
            # Convert order type
            order_type_mt5 = mt5.ORDER_TYPE_BUY if order_type == "BUY" else mt5.ORDER_TYPE_SELL
            
            # Create trade request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type_mt5,
                "price": price,
                "sl": sl if sl else 0,
                "tp": tp if tp else 0,
                "deviation": deviation,
                "magic": magic,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Send order
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                print(f"[MT5-CONN] ❌ Order send failed: {error}")
                return None
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"[MT5-CONN] ❌ Order rejected: {result.comment}")
                return None
            
            ticket = result.order
            print(f"[MT5-CONN] ✅ Position opened: {order_type} {volume} {symbol} at {price} (Ticket: {ticket})")
            return ticket
            
        except Exception as e:
            print(f"[MT5-CONN] Error opening position: {e}")
            return None
    
    def close_position(self, ticket: int, volume: Optional[float] = None) -> bool:
        """
        Close a trading position
        
        Args:
            ticket: Position ticket number
            volume: Volume to close (if None, closes entire position)
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            return False
        
        try:
            # Get position
            position = mt5.positions_get(ticket=ticket)
            if position is None or len(position) == 0:
                print(f"[MT5-CONN] Position {ticket} not found")
                return False
            
            pos = position[0]
            close_volume = volume if volume else pos.volume
            
            # Determine close type (opposite of position type)
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            # Get current price
            symbol_info = mt5.symbol_info(pos.symbol)
            close_price = symbol_info.bid if pos.type == mt5.ORDER_TYPE_BUY else symbol_info.ask
            
            # Create close request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": close_volume,
                "type": close_type,
                "price": close_price,
                "position": ticket,
                "deviation": 20,
                "magic": 0,
                "comment": f"Close position {ticket}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Send close order
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                print(f"[MT5-CONN] ❌ Close order failed: {error}")
                return False
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"[MT5-CONN] ❌ Close order rejected: {result.comment}")
                return False
            
            print(f"[MT5-CONN] ✅ Position {ticket} closed: {close_volume} {pos.symbol}")
            return True
            
        except Exception as e:
            print(f"[MT5-CONN] Error closing position: {e}")
            return False
    
    def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None
    ) -> bool:
        """
        Modify stops (SL/TP) for a position
        
        Args:
            ticket: Position ticket number
            sl: New stop loss price
            tp: New take profit price
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_connected():
            return False
        
        try:
            # Get current position
            position = mt5.positions_get(ticket=ticket)
            if position is None or len(position) == 0:
                print(f"[MT5-CONN] Position {ticket} not found")
                return False
            
            pos = position[0]
            
            # Create modify request
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": ticket,
                "sl": sl if sl else pos.sl,
                "tp": tp if tp else pos.tp,
            }
            
            # Send modify order
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                print(f"[MT5-CONN] ❌ Modify order failed: {error}")
                return False
            
            if result.retcode != mt5.TRADE_RETCODE_DONE:
                print(f"[MT5-CONN] ❌ Modify rejected: {result.comment}")
                return False
            
            print(f"[MT5-CONN] ✅ Position {ticket} modified: SL={sl}, TP={tp}")
            return True
            
        except Exception as e:
            print(f"[MT5-CONN] Error modifying position: {e}")
            return False
    
    def get_symbol_specification(self, symbol: str) -> Optional[Dict]:
        """
        Get symbol specification (point, digits, contract size, etc.)
        
        Args:
            symbol: Symbol name (e.g., "XAUUSD")
        
        Returns:
            Dictionary with symbol info, or None if error
        """
        if not self.is_connected():
            return None
        
        try:
            # Get symbol info from MT5
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                print(f"[MT5-CONN] Symbol not found: {symbol}")
                # Try selecting it first, then get info again
                if not mt5.symbol_select(symbol, True):
                    print(f"[MT5-CONN] Cannot select symbol {symbol}")
                    return None
                symbol_info = mt5.symbol_info(symbol)
                if symbol_info is None:
                    print(f"[MT5-CONN] Symbol still not available after selection: {symbol}")
                    return None
            
            # Convert to dict format compatible with rest of code
            return {
                "symbol": symbol_info.name,
                "point": float(symbol_info.point),
                "digits": int(symbol_info.digits),
                "spread": int(symbol_info.spread),
                "minVolume": float(symbol_info.volume_min),
                "maxVolume": float(symbol_info.volume_max),
                "volumeStep": float(symbol_info.volume_step),
                "contractSize": float(symbol_info.trade_contract_size),
                "bid": float(symbol_info.bid),
                "ask": float(symbol_info.ask),
            }
        except Exception as e:
            print(f"[MT5-CONN] Error getting symbol specification for {symbol}: {e}")
            return None
    
    def symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Alias for get_symbol_specification() for backward compatibility.
        Returns full symbol information including bid/ask prices.
        """
        return self.get_symbol_specification(symbol)
    
    def get_symbol_price(self, symbol: str) -> Optional[Dict]:
        """
        Get current bid/ask prices for a symbol
        
        Args:
            symbol: Symbol name (e.g., "XAUUSD")
        
        Returns:
            Dictionary with bid/ask, or None if error
        """
        if not self.is_connected():
            return None
        
        try:
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            return {
                "bid": float(symbol_info.bid),
                "ask": float(symbol_info.ask),
            }
        except Exception as e:
            print(f"[MT5-CONN] Error getting price for {symbol}: {e}")
            return None
    
    def get_account_information(self) -> Optional[Dict]:
        """
        Get full account information (wrapper for compatibility)
        
        Returns:
            Dictionary with account info, or None if error
        """
        return self.get_account_info()
    
    def create_market_buy_order(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None, comment: str = "") -> Optional[Dict]:
        """
        Create a market buy order (wrapper for compatibility with MetaAPI interface)
        
        Args:
            symbol: Symbol to trade
            volume: Trade volume (in lots)
            sl: Stop loss price
            tp: Take profit price
            comment: Order comment
        
        Returns:
            Dictionary with order result or None
        """
        try:
            # Get current ask price for market BUY
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            ask_price = float(symbol_info.ask)
            
            ticket = self.open_position(
                symbol=symbol,
                order_type="BUY",
                volume=volume,
                price=ask_price,  # Use current ask for market buy
                sl=sl,
                tp=tp,
                comment=comment,
                magic=0,
                deviation=20
            )
            if ticket:
                return {"ticket": ticket, "orderId": ticket}
            return None
        except Exception as e:
            print(f"[MT5-CONN] Error creating buy order: {e}")
            return None
    
    def create_market_sell_order(self, symbol: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None, comment: str = "") -> Optional[Dict]:
        """
        Create a market sell order (wrapper for compatibility with MetaAPI interface)
        
        Args:
            symbol: Symbol to trade
            volume: Trade volume (in lots)
            sl: Stop loss price
            tp: Take profit price
            comment: Order comment
        
        Returns:
            Dictionary with order result or None
        """
        try:
            # Get current bid price for market SELL
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return None
            
            bid_price = float(symbol_info.bid)
            
            ticket = self.open_position(
                symbol=symbol,
                order_type="SELL",
                volume=volume,
                price=bid_price,  # Use current bid for market sell
                sl=sl,
                tp=tp,
                comment=comment,
                magic=0,
                deviation=20
            )
            if ticket:
                return {"ticket": ticket, "orderId": ticket}
            return None
        except Exception as e:
            print(f"[MT5-CONN] Error creating sell order: {e}")
            return None


# Global connection instance
_mt5_connection: Optional[MT5Connection] = None


def get_mt5_connection() -> MT5Connection:
    """Get or create the global MT5 connection instance"""
    global _mt5_connection
    if _mt5_connection is None:
        _mt5_connection = MT5Connection()
    return _mt5_connection


def connect_mt5() -> bool:
    """Initialize and connect to MT5 terminal"""
    conn = get_mt5_connection()
    return conn.connect()


def disconnect_mt5():
    """Disconnect from MT5 terminal"""
    global _mt5_connection
    if _mt5_connection:
        _mt5_connection.disconnect()
        _mt5_connection = None


def is_mt5_connected() -> bool:
    """Check if connected to MT5"""
    conn = get_mt5_connection()
    return conn.is_connected()
