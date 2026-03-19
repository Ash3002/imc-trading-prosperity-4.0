# run this file from root i.e /imc

import pandas as pd
import matplotlib.pyplot as plt

print("Loading data...")
df = pd.read_csv(r'trade-analysis\round-0\prices_round_0_day_-1.csv', sep=';')

# Pivot the data to compare products easily
prices_df = df.pivot(index='timestamp', columns='product', values='mid_price')

# 1. Print Correlation (For Pairs Trading)
print("\n--- Correlation Matrix ---")
print(prices_df.corr())

# 2. Print Basic Stats (For Stationarity)
print("\n--- Basic Statistics ---")
print(prices_df.describe())

# 3. Plot the data
print("\nGenerating charts...")
plt.figure(figsize=(12, 6))

# Chart 1: EMERALDS
plt.subplot(1, 2, 1)
plt.plot(prices_df.index, prices_df['EMERALDS'], color='green')
plt.title('EMERALDS (Stationary)')
plt.xlabel('Timestamp')
plt.ylabel('Price')
plt.ylim(9990, 10010) # Lock the Y-axis to see how flat it is

# Chart 2: TOMATOES
plt.subplot(1, 2, 2)
plt.plot(prices_df.index, prices_df['TOMATOES'], color='red')
plt.title('TOMATOES (Trending)')
plt.xlabel('Timestamp')
plt.ylabel('Price')

plt.tight_layout()
plt.show()