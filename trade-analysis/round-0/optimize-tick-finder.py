#run from root i.e /imc

import pandas as pd
import numpy as np

print("Loading data...")
# Load the data and get only the TOMATOES rows
df = pd.read_csv(r'trade-analysis\round-0\prices_round_0_day_-1.csv', sep=';')
tomatoes_df = df[df['product'] == 'TOMATOES'].copy()
tomatoes_df = tomatoes_df.sort_values('timestamp').reset_index(drop=True)

# We want to test every window size from 5 ticks to 100 ticks
# and every trigger threshold from 1 to 5.
best_profit = -999999
best_window = 0
best_threshold = 0

print("Testing hundreds of strategies instantly...")

# Loop through different window sizes
for window in range(5, 101, 5): # Tests 5, 10, 15... up to 100
    for threshold in range(1, 6): # Tests 1, 2, 3, 4, 5
        
        # 1. Calculate the Moving Average for this specific window
        sma = tomatoes_df['mid_price'].rolling(window=window).mean()
        
        # 2. Figure out our target position at every single timestamp
        # If price is way below average -> we want to hold 20 (Max Buy)
        # If price is way above average -> we want to hold -20 (Max Sell)
        # Otherwise -> hold 0 (Neutral)
        
        target_positions = np.zeros(len(tomatoes_df))
        
        # Where price is cheap, set target to +20
        buy_signals = tomatoes_df['mid_price'] < (sma - threshold)
        target_positions[buy_signals] = 20
        
        # Where price is expensive, set target to -20
        sell_signals = tomatoes_df['mid_price'] > (sma + threshold)
        target_positions[sell_signals] = -20
        
        # 3. Calculate how many we had to buy/sell to reach that target
        # e.g., if we were at 0, and target is 20, our trade is +20. 
        # If we were at 20, and target is -20, our trade is -40.
        trades = np.diff(target_positions, prepend=0)
        
        # 4. Calculate Profit and Loss (PnL)
        # If we traded, we multiply the amount we traded by the current price.
        # (Negative cash flow for buying, positive for selling)
        cash_flow = -trades * tomatoes_df['mid_price'].values
        
        # Our total value is the cash we collected + the value of the items we are currently holding
        final_cash = cash_flow.sum()
        final_inventory_value = target_positions[-1] * tomatoes_df['mid_price'].iloc[-1]
        
        total_profit = final_cash + final_inventory_value
        
        # 5. Keep track of the best one
        if total_profit > best_profit:
            best_profit = total_profit
            best_window = window
            best_threshold = threshold

print("\n=== OPTIMIZATION COMPLETE ===")
print(f"The absolute best Window Size is: {best_window}")
print(f"The absolute best Threshold is: {best_threshold}")
print(f"Hypothetical Profit: ${best_profit:,.2f}")