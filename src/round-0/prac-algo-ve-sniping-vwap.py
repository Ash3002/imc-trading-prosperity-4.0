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
            
            # Ensure the order book isn't empty before we do math
            if len(order_depth.buy_orders) > 0 and len(order_depth.sell_orders) > 0:
                best_bid = max(order_depth.buy_orders.keys())
                best_ask = min(order_depth.sell_orders.keys())
                
                # ---------------------------------------------------------
                # STRATEGY 1: EMERALDS (The Sniper)
                # ---------------------------------------------------------
                if product == 'EMERALDS':
                    current_position = state.position.get('EMERALDS', 0)
                    POSITION_LIMIT = 20
                    
                    acceptable_buy = 9998
                    acceptable_sell = 10002
                    
                    # THE BUY SNIPER
                    if best_ask <= acceptable_buy:
                        my_buy_price = best_ask 
                    else:
                        my_buy_price = min(best_bid + 1, acceptable_buy) 
                        
                    # THE SELL SNIPER
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

                # ---------------------------------------------------------
                # STRATEGY 2: TOMATOES (VWAP + OBI + Skew + Sniper)
                # ---------------------------------------------------------
                if product == 'TOMATOES':
                    current_position = state.position.get('TOMATOES', 0)
                    POSITION_LIMIT = 20
                    
                    # 1. Volume & VWAP Calculation
                    buy_vol = sum(order_depth.buy_orders.values())
                    sell_vol = abs(sum(order_depth.sell_orders.values())) 
                    total_vol = buy_vol + sell_vol
                    
                    if total_vol > 0:
                        vwap = ((best_bid * buy_vol) + (best_ask * sell_vol)) / total_vol
                    else:
                        vwap = (best_bid + best_ask) / 2
                        
                    tomato_history.append(vwap)
                    
                    if len(tomato_history) > 5:
                        tomato_history.pop(0)
                        
                    if len(tomato_history) == 5:
                        # 2. Dynamic Fair Value (5-tick VWAP average)
                        dynamic_fair_value = sum(tomato_history) / 5
                        
                        # 3. Order Book Imbalance (Momentum Shift)
                        obi = 0
                        if total_vol > 0:
                            obi = (buy_vol - sell_vol) / total_vol 
                            
                        obi_shift = 0
                        if obi > 0.5:
                            obi_shift = 1   
                        elif obi < -0.5:
                            obi_shift = -1  
                            
                        dynamic_fair_value += obi_shift
                        
                        # 4. Aggressive Inventory Skew
                        skew = -int(current_position / 5)
                        
                        acceptable_buy = int(round(dynamic_fair_value - 1 + skew))
                        acceptable_sell = int(round(dynamic_fair_value + 1 + skew))
                        
                        # 5. THE BUY SNIPER
                        if best_ask <= acceptable_buy:
                            my_buy_price = best_ask
                        else:
                            my_buy_price = min(best_bid + 1, acceptable_buy)
                            
                        # 6. THE SELL SNIPER
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

        # 3. STATE SAVING
        new_traderData = json.dumps(tomato_history)
        return result, 1, new_traderData