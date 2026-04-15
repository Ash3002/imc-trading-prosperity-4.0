from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict, Tuple

class Trader:
    def __init__(self):
        # Position limits mapped to generic identifiers
        self.LIMITS = {
            'PEPPER': 20,
            'OSMIUM': 5
        }
        
    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        
        result = {}
        conversions = 0  
        trader_data = "" 
        
        # Dynamically find the exact keys to avoid case-sensitivity/spelling rejections
        pepper_symbol = next((k for k in state.order_depths.keys() if 'pepper' in k.lower()), 'Intarian Pepper Root')
        osmium_symbol = next((k for k in state.order_depths.keys() if 'osmium' in k.lower()), 'Ash-coated Osmium')

        # ---------------------------------------------------------
        # 1. Pepper Root (The Buy & Hold Trend Machine)
        # ---------------------------------------------------------
        if pepper_symbol in state.order_depths:
            pepper_orders: List[Order] = []
            pepper_pos = state.position.get(pepper_symbol, 0)
            order_depth: OrderDepth = state.order_depths[pepper_symbol]
            
            # Extract current level 1 book depth
            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

            if best_bid and best_ask:
                # Open/Maintain: Continuously check if we are below max position
                if state.timestamp < 990000:  
                    if pepper_pos < self.LIMITS['PEPPER']:
                        buy_qty = self.LIMITS['PEPPER'] - pepper_pos
                        # Guarantee fill by crossing the spread at the exact best ask
                        pepper_orders.append(Order(pepper_symbol, best_ask, buy_qty))
                        
                # Close: Liquidate everything in the final stretch of the simulation day
                else:
                    if pepper_pos > 0:
                        pepper_orders.append(Order(pepper_symbol, best_bid, -pepper_pos))
                
                if pepper_orders:
                    result[pepper_symbol] = pepper_orders

        # ---------------------------------------------------------
        # 2. Ash-coated Osmium (The Add-On Sniper)
        # ---------------------------------------------------------
        if osmium_symbol in state.order_depths:
            osmium_orders: List[Order] = []
            osmium_pos = state.position.get(osmium_symbol, 0)
            order_depth: OrderDepth = state.order_depths[osmium_symbol]
            
            best_bid = max(order_depth.buy_orders.keys()) if order_depth.buy_orders else None
            best_ask = min(order_depth.sell_orders.keys()) if order_depth.sell_orders else None

            if best_bid and best_ask:
                # --- LONG LOGIC ---
                if best_ask < 9990 and osmium_pos < self.LIMITS['OSMIUM']:
                    qty_to_buy = self.LIMITS['OSMIUM'] - osmium_pos
                    osmium_orders.append(Order(osmium_symbol, best_ask, qty_to_buy))
                    
                elif osmium_pos > 0 and best_bid > 9997:
                    osmium_orders.append(Order(osmium_symbol, best_bid, -osmium_pos))

                # --- SHORT LOGIC ---
                if best_bid > 10010 and osmium_pos > -self.LIMITS['OSMIUM']:
                    qty_to_sell = -self.LIMITS['OSMIUM'] - osmium_pos 
                    osmium_orders.append(Order(osmium_symbol, best_bid, qty_to_sell))
                    
                elif osmium_pos < 0 and best_ask < 10003:
                    qty_to_buy = abs(osmium_pos)
                    osmium_orders.append(Order(osmium_symbol, best_ask, qty_to_buy))

            if osmium_orders:
                 result[osmium_symbol] = osmium_orders

        return result, conversions, trader_data