from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json

class Trader:
    
    def run(self, state: TradingState):
        """
        Takes all current market data and returns a tuple of:
        (orders_dict, conversions_integer, new_traderData_string)
        """
        result = {}
        
        # 1. LOAD OUR MEMORY (STATE)
        # We deserialize the history from the previous tick
        if state.traderData == "":
            tomato_history = []
        else:
            tomato_history = json.loads(state.traderData)

        # 2. LOOP THROUGH ALL PRODUCTS
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            # ---------------------------------------------------------
            # STRATEGY 1: EMERALDS (The Stationary Asset)
            # ---------------------------------------------------------
            if product == 'EMERALDS':
                current_position = state.position.get('EMERALDS', 0)
                POSITION_LIMIT = 20
                
                # Market Making: Buy at 9998, Sell at 10002
                max_buy = POSITION_LIMIT - current_position
                if max_buy > 0:
                    orders.append(Order(product, 9998, max_buy))
                    
                max_sell = -POSITION_LIMIT - current_position
                if max_sell < 0:
                    orders.append(Order(product, 10002, max_sell))
                    
                result[product] = orders

            # ---------------------------------------------------------
            # STRATEGY 2: TOMATOES (The Trending Asset)
            # ---------------------------------------------------------
            if product == 'TOMATOES':
                current_position = state.position.get('TOMATOES', 0)
                POSITION_LIMIT = 20
                
                # Ensure the order book isn't completely empty before doing math
                if len(order_depth.buy_orders) > 0 and len(order_depth.sell_orders) > 0:
                    best_bid = max(order_depth.buy_orders.keys())
                    best_ask = min(order_depth.sell_orders.keys())
                    mid_price = (best_bid + best_ask) / 2
                    
                    # Add current price to our history array
                    tomato_history.append(mid_price)
                    
                    # Apply your optimized Window Size: 5
                    if len(tomato_history) > 5:
                        tomato_history.pop(0)
                        
                    # Only trade if we have a full 5 ticks of data to calculate the SMA
                    if len(tomato_history) == 5:
                        sma = sum(tomato_history) / 5
                        
                        # Apply your optimized Threshold: 1
                        # (Pro-tip: If you lose money to spread fees in the live simulation, 
                        # bump this 1 up to a 1.5 or 2 for safety)
                        if mid_price < sma - 1:
                            max_buy = POSITION_LIMIT - current_position
                            if max_buy > 0:
                                # Execute buy order
                                orders.append(Order(product, best_ask, max_buy))
                                
                        elif mid_price > sma + 1:
                            max_sell = -POSITION_LIMIT - current_position
                            if max_sell < 0:
                                # Execute sell order
                                orders.append(Order(product, best_bid, max_sell))

                result[product] = orders

        # 3. SAVE OUR MEMORY FOR THE NEXT TICK
        # Serialize the array back into a JSON string so the engine remembers it
        new_traderData = json.dumps(tomato_history)
        
        # 4. RETURN EXPECTED FORMAT
        return result, 1, new_traderData