from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json

class Trader:
    
    def run(self, state: TradingState):
        result = {}
        
        # 1. STATE MANAGEMENT
        if state.traderData == "":
            tomato_history = []
        else:
            tomato_history = json.loads(state.traderData)

        # 2. PROCESS EACH PRODUCT
        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []
            
            if len(order_depth.buy_orders) > 0 and len(order_depth.sell_orders) > 0:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                mid_price = (best_bid + best_ask) / 2
                
                # ---------------------------------------------------------
                # STRATEGY 1: EMERALDS (The Sniper)
                # ---------------------------------------------------------
                if product == 'EMERALDS':
                    current_position = state.position.get('EMERALDS', 0)
                    POSITION_LIMIT = 20
                    
                    # Acceptable limits (Fair value is 10000)
                    acceptable_buy = 9998
                    acceptable_sell = 10002
                    
                    # THE BUY SNIPER
                    if best_ask <= acceptable_buy:
                        my_buy_price = best_ask # Instantly take the cheap ask!
                    else:
                        my_buy_price = min(best_bid + 1, acceptable_buy) # Penny jump
                        
                    # THE SELL SNIPER
                    if best_bid >= acceptable_sell:
                        my_sell_price = best_bid # Instantly sell to the high bidder!
                    else:
                        my_sell_price = max(best_ask - 1, acceptable_sell) # Penny jump
                    
                    max_buy = POSITION_LIMIT - current_position
                    if max_buy > 0:
                        orders.append(Order(product, my_buy_price, max_buy))
                        
                    max_sell = -POSITION_LIMIT - current_position
                    if max_sell < 0:
                        orders.append(Order(product, my_sell_price, max_sell))
                        
                    result[product] = orders

                # ---------------------------------------------------------
                # STRATEGY 2: TOMATOES (Dynamic Sniper + Aggressive Skew)
                # ---------------------------------------------------------
                if product == 'TOMATOES':
                    current_position = state.position.get('TOMATOES', 0)
                    POSITION_LIMIT = 20
                    
                    tomato_history.append(mid_price)
                    
                    if len(tomato_history) > 5:
                        tomato_history.pop(0)
                        
                    if len(tomato_history) == 5:
                        # 1. Math & Fair Value
                        sma = sum(tomato_history) / 5
                        
                        buy_vol = sum(order_depth.buy_orders.values())
                        sell_vol = abs(sum(order_depth.sell_orders.values())) 
                        total_vol = buy_vol + sell_vol
                        
                        obi = 0
                        if total_vol > 0:
                            obi = (buy_vol - sell_vol) / total_vol 
                            
                        obi_shift = 0
                        if obi > 0.5:
                            obi_shift = 1   
                        elif obi < -0.5:
                            obi_shift = -1  
                            
                        dynamic_fair_value = sma + obi_shift
                        
                        # 2. Aggressive Skew (Divide by 5 instead of 10)
                        skew = -int(current_position / 5)
                        
                        # 3. Calculate what we are willing to accept
                        acceptable_buy = int(round(dynamic_fair_value - 1 + skew))
                        acceptable_sell = int(round(dynamic_fair_value + 1 + skew))
                        
                        # 4. THE BUY SNIPER
                        if best_ask <= acceptable_buy:
                            my_buy_price = best_ask
                        else:
                            my_buy_price = min(best_bid + 1, acceptable_buy)
                            
                        # 5. THE SELL SNIPER
                        if best_bid >= acceptable_sell:
                            my_sell_price = best_bid
                        else:
                            my_sell_price = max(best_ask - 1, acceptable_sell)
                        
                        max_buy = POSITION_LIMIT - current_position
                        if max_buy > 0:
                            orders.append(Order(product, my_buy_price, max_buy))
                            
                        max_sell = -POSITION_LIMIT - current_position
                        if max_sell < 0:
                            orders.append(Order(product, my_sell_price, max_sell))

                    result[product] = orders

        new_traderData = json.dumps(tomato_history)
        return result, 1, new_traderData