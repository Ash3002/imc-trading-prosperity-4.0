from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json

class Trader:
    
    def run(self, state: TradingState):
        result = {}
        
        # 1. STATE MANAGEMENT (MEMORY)
        if state.traderData == "":
            tomato_history = []
        else:
            tomato_history = json.loads(state.traderData)

        # 2. PROCESS EACH PRODUCT
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            # ---------------------------------------------------------
            # STRATEGY 1: EMERALDS (Stationary Market Making)
            # ---------------------------------------------------------
            if product == 'EMERALDS':
                current_position = state.position.get('EMERALDS', 0)
                POSITION_LIMIT = 20
                
                # Base Fair Value is always 10000
                # INVENTORY SKEW: If we hold > 10, we drop our sell price to 10001 to clear inventory fast.
                # If we hold < -10, we raise our buy price to 9999 to cover our shorts fast.
                buy_price = 9998
                sell_price = 10002
                
                if current_position > 10:
                    sell_price -= 1  # More aggressive to sell
                    buy_price -= 1   # Less aggressive to buy
                elif current_position < -10:
                    buy_price += 1   # More aggressive to buy
                    sell_price += 1  # Less aggressive to sell
                
                max_buy = POSITION_LIMIT - current_position
                if max_buy > 0:
                    orders.append(Order(product, buy_price, max_buy))
                    
                max_sell = -POSITION_LIMIT - current_position
                if max_sell < 0:
                    orders.append(Order(product, sell_price, max_sell))
                    
                result[product] = orders

            # ---------------------------------------------------------
            # STRATEGY 2: TOMATOES (Trending Market Making + OBI + Skew)
            # ---------------------------------------------------------
            if product == 'TOMATOES':
                current_position = state.position.get('TOMATOES', 0)
                POSITION_LIMIT = 20
                
                # Ensure we have data to do math
                if len(order_depth.buy_orders) > 0 and len(order_depth.sell_orders) > 0:
                    best_bid = max(order_depth.buy_orders.keys())
                    best_ask = min(order_depth.sell_orders.keys())
                    mid_price = (best_bid + best_ask) / 2
                    
                    tomato_history.append(mid_price)
                    
                    # Window Size: 5 ticks
                    if len(tomato_history) > 5:
                        tomato_history.pop(0)
                        
                    if len(tomato_history) == 5:
                        # 1. BASELINE: Simple Moving Average
                        sma = sum(tomato_history) / 5
                        
                        # 2. HEURISTIC 1: Order Book Imbalance (OBI)
                        # Calculate total volume of buyers vs sellers
                        buy_vol = sum(order_depth.buy_orders.values())
                        # Sell volumes are negative, so we use abs()
                        sell_vol = abs(sum(order_depth.sell_orders.values())) 
                        
                        total_vol = buy_vol + sell_vol
                        obi = 0
                        if total_vol > 0:
                            # OBI ranges from -1 (all sellers) to +1 (all buyers)
                            obi = (buy_vol - sell_vol) / total_vol 
                        
                        # Shift Fair Value based on OBI
                        obi_shift = 0
                        if obi > 0.5:
                            obi_shift = 1   # Buyers are aggressive, shift value UP
                        elif obi < -0.5:
                            obi_shift = -1  # Sellers are aggressive, shift value DOWN
                            
                        dynamic_fair_value = sma + obi_shift
                        
                        # 3. HEURISTIC 2: Inventory Skew
                        # For every 10 items we hold, we shift our prices by 1 point.
                        # If position = 20, skew = -2. If position = -20, skew = +2.
                        skew = -int(current_position / 10)
                        
                        # 4. FINAL ORDER CALCULATION
                        # We quote 2 points wide from our dynamic fair value, then apply the skew
                        my_buy_price = int(round(dynamic_fair_value - 2 + skew))
                        my_sell_price = int(round(dynamic_fair_value + 2 + skew))
                        
                        max_buy = POSITION_LIMIT - current_position
                        if max_buy > 0:
                            orders.append(Order(product, my_buy_price, max_buy))
                            
                        max_sell = -POSITION_LIMIT - current_position
                        if max_sell < 0:
                            orders.append(Order(product, my_sell_price, max_sell))

                result[product] = orders

        # 3. STATE SAVING
        new_traderData = json.dumps(tomato_history)
        
        return result, 1, new_traderData