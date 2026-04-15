# ALGORITHMIC TRADING STRATEGY GUIDE
## INTARIAN_PEPPER_ROOT + ASH_COATED_OSMIUM

---

## EXECUTIVE SUMMARY

This document describes a **hybrid algorithmic trading strategy** optimized for two different asset types:

1. **INTARIAN_PEPPER_ROOT** - Directional momentum strategy with positive inventory bias
2. **ASH_COATED_OSMIUM** - Market making and mean reversion strategy with neutral inventory target

### Key Design Principles

- **Asymmetric risk**: INTARIAN favors long positions; ASH favors neutrality
- **Signal-driven**: All decisions stem from statistically significant patterns
- **Inventory-aware**: Position sizing and quote placement adjusted for current holdings
- **Liquidity-sensitive**: Order sizing and aggressiveness scale with available volume

---

## 1. PATTERN ANALYSIS & DISCOVERY

### INTARIAN_PEPPER_ROOT: Deterministic Trend

**Observed Behavior:**
- Strong, consistent upward drift over time
- Fair value approximation: `FV = 10000 + 1000*(day+2) + timestamp/1000`
- This relationship is **highly deterministic** (not random)
- Suggests predictable alpha opportunity through:
  - **Directional positioning**: Buy strength, ride trend
  - **Inventory carry**: Hold long positions for drift capture
  - **Valuation-based entry/exit**: Exploit predictable mean reversion around fair value

**Economic Interpretation:**
- The linear time-based trend suggests a predictable supply/demand imbalance
- Could reflect structural factors: inventory depletion, seasonal demand, cost accumulation
- **Opportunity**: Buy below fair value, hold through drift, sell above fair value

**Risk Factors:**
- Trend could break (e.g., if underlying supply/demand changes)
- Model assumes linearity - may fail in extreme market conditions
- Need to monitor fit quality of fair value model

---

### ASH_COATED_OSMIUM: Mean Reversion

**Observed Behavior:**
- Price clusters around ~10000 (mean)
- No strong directional trend
- Exhibits stationarity (mean-reverting process)
- Order book imbalance provides short-term information

**Economic Interpretation:**
- Market structure more balanced (supply ≈ demand at equilibrium)
- Price movements are temporary deviations from fair value
- Quick reversion creates spread capture opportunity

**Opportunity:**
- Buy when price is below mean → profit from reversion up
- Sell when price is above mean → profit from reversion down
- Quote tighter spreads than market provides → capture spread repeatedly

---

## 2. STRATEGY DESIGN

### A. INTARIAN_PEPPER_ROOT Strategy

#### Objective
Maximize profit from trending market by:
1. Building and maintaining positive inventory
2. Buying weakness, selling strength
3. Capturing drift over time

#### Signal Generation

**Buy Signal Strength** (0 to 1 scale):
```
buy_score = 0.5 (baseline)

// Valuation component (strongest)
if (mid_price - fair_value) / fair_value < -1.5%:
    buy_score += 0.35  // Significantly undervalued → aggressive buy
else if (mid_price - fair_value) / fair_value < -0.5%:
    buy_score += 0.15  // Moderately undervalued → modest buy

// Spread component
if spread < 1.0:
    buy_score *= 1.1   // Tight spread → confidence boost
else if spread > 3.0:
    buy_score *= 0.8   // Wide spread → caution

// Imbalance component
if imbalance < -0.15:  // More bids than asks
    buy_score *= 1.1   // Bullish sign
else if imbalance > 0.15:
    buy_score *= 0.9   // Bearish sign

// Inventory component (long bias)
if position < 30 units:
    buy_score += 0.2 * (1 - position/30)  // Underweight → buy more
```

**Sell Signal**: Mirror of buy (penalize if overweight)

#### Order Execution

**Buy Orders:**
- Passive placement: `bid_price = mid_price - 0.50`
- Size: `base_size = 20 * signal_strength`
- Adjustment: If position < 50, multiply size by 1.5 (aggressive build)

**Sell Orders:**
- Passive placement: `ask_price = mid_price + 0.50`
- Size: `base_size = 10 * signal_strength` (sell less aggressively)
- Adjustment: If position > 100, multiply size by 1.5 (risk reduction)

#### Position Management

- **Target inventory**: 100 units
- **Position limits**: Max 300, Min -100 (allow small short for hedging)
- **Inventory-based risk control**: 
  - At max position: stop buying, prioritize selling
  - At min position: stop selling, prioritize buying

---

### B. ASH_COATED_OSMIUM Strategy

#### Objective
Maximize profit from mean-reversion and spread capture:
1. Stay near-neutral inventory
2. Buy weakness, sell strength
3. Repeatedly capture bid-ask spread

#### Signal Generation

**Buy Signal Strength**:
```
buy_score = 0.5

// Mean reversion (strongest signal)
if (mid_price - fair_value) / fair_value < -1.0%:
    buy_score += 0.4   // Below mean → buy aggressively
else if (mid_price - fair_value) / fair_value > 1.0%:
    buy_score -= 0.4   // Above mean → sell aggressively

// Spread component
if spread < 2.0:
    buy_score += 0.1   // Good for capturing spread
else:
    buy_score -= 0.1   // Wide spread → wait

// Imbalance (strength indicator)
if imbalance < -0.2:   // Strong bid side
    buy_score += 0.15  // Buyers active
else if imbalance > 0.2:
    buy_score -= 0.15  // Sellers active

// Inventory control (stay neutral)
if abs(position) > 80:
    buy_score *= 0.5   // Heavily overweight → reduce activity
```

#### Order Execution

**Market Making Approach:**
- **Buy**: `bid_price = mid_price - 0.20`
- **Sell**: `ask_price = mid_price + 0.20`
- **Size**: `base_size = 10 * signal_strength`, scaled down if far from neutral
- **Goal**: Post quotes, capture spread on both sides

#### Position Management

- **Target inventory**: 0 units (neutral)
- **Position limits**: Max 100, Min -100
- **Rebalancing**: If position deviates significantly:
  - Long 50+: prioritize selling (reduce)
  - Short 50+: prioritize buying (reduce)

---

## 3. EXECUTION LOGIC

### Order Matching Simulation

Our backtest simulates realistic order execution:

1. **Limit Orders (Passive)**
   - Buy orders placed below mid → wait for someone to sell into them
   - Sell orders placed above mid → wait for someone to buy from them
   - 10-30% chance of partial fill each tick

2. **Market Orders (Aggressive)**
   - Buy at or above ask → immediate fill at ask price
   - Sell at or below bid → immediate fill at bid price
   - Fill size: min(order_quantity, available_volume * 80%)

3. **Partial Fills**
   - Real order books don't have infinite volume
   - Algorithm tracks filled_qty and tries again later
   - VWAP calculated across all fills

---

## 4. RISK MANAGEMENT

### Position Limits

| Asset | Max Long | Target | Max Short |
|-------|----------|--------|-----------|
| INTARIAN | 300 | +100 | -100 |
| ASH | 100 | 0 | -100 |

### Inventory-Based Sizing

- **Dynamic position sizing**: Scale order size by signal strength
- **Inventory penalty**: Reduce order size when far from target
- **Hard limits**: Reject new orders if hitting position limits

### Daily Risk Controls

- Track daily PnL
- Monitor drawdown in real-time
- Potential circuit breaker: Stop if daily loss > X%

---

## 5. PERFORMANCE METRICS

### Key Metrics to Track

1. **PnL Metrics**
   - Total profit/loss (realized + unrealized)
   - Daily returns
   - Monthly/quarterly returns

2. **Risk Metrics**
   - Maximum drawdown
   - Sharpe ratio (return / volatility)
   - Win rate (% profitable trades)
   - Average win / average loss ratio

3. **Execution Metrics**
   - Total number of trades
   - Average fill size
   - Slippage vs fair value
   - Participation rate (our volume / market volume)

4. **Inventory Metrics**
   - Average position size
   - Days held in inventory
   - Turnover rate

---

## 6. PARAMETER TUNING

### Sensitive Parameters

**INTARIAN Fair Value Model:**
- Coefficients: `10000 + 1000*(day+2) + timestamp/1000`
- Could be refined with regression on actual data

**Signal Thresholds:**
- BUY if score > 0.65
- SELL if score < 0.35
- NEUTRAL otherwise
- **Tuning**: Sweep these thresholds to optimize Sharpe ratio

**Order Placement:**
- BUY offset from mid: currently -0.50
- SELL offset from mid: currently +0.50
- **Tuning**: Smaller offset = more aggressive, larger = more passive

**Position Sizing:**
- Base size multiplier (currently 20 for INTARIAN, 10 for ASH)
- Inventory adjustment factors (currently 1.5x when building)
- **Tuning**: Optimize for target position and turnover

---

## 7. IMPLEMENTATION NOTES

### Python Code Structure

```
algorithmic_trading_system.py
├── DataLoader              # Load CSV files
├── OrderBookSnapshot       # Data structure
├── FeatureEngine           # Signal generation
├── TradingStrategy         # Decision logic
├── ExecutionEngine         # Order matching
├── Backtest                # Event-driven backtest
└── run_backtest()          # Main entry point
```

### Running the Backtest

```python
from algorithmic_trading_system import run_backtest

# With real data
prices_paths = [
    'prices_round_1_day_-2.csv',
    'prices_round_1_day_-1.csv',
    'prices_round_1_day_0.csv'
]
trades_paths = [
    'trades_round_1_day_-2.csv',
    'trades_round_1_day_-1.csv',
    'trades_round_1_day_0.csv'
]

backtest, results, logs_df, daily_df = run_backtest(prices_paths, trades_paths)
```

### Output Files

1. **trading_logs.csv**: Detailed transaction log
2. **daily_pnl.csv**: Daily profit/loss summary
3. **backtest_summary.json**: Key metrics

---

## 8. NEXT STEPS FOR IMPROVEMENT

### Short-term
- [ ] Calibrate fair value models on actual data (regression)
- [ ] Optimize signal thresholds (parameter sweep)
- [ ] Test with different order placement offsets
- [ ] Add slippage estimation

### Medium-term
- [ ] Add machine learning for signal generation (e.g., LSTM predicting next move)
- [ ] Implement volatility-based position sizing
- [ ] Add correlation analysis between products
- [ ] Test different rebalancing frequencies

### Long-term
- [ ] Live trading system integration
- [ ] Real-time monitoring dashboard
- [ ] Automated parameter adaptation
- [ ] Multi-asset extension (scale to more products)

---

## CONCLUSION

This hybrid strategy exploits two different market behaviors:
1. **INTARIAN**: Directional trend + inventory carry
2. **ASH**: Mean reversion + spread capture

The key insight is **asymmetric risk management**: accept long inventory for trending asset, maintain neutrality for mean-reverting asset. This diversification provides robustness and risk control while maximizing alpha capture.

Expected performance targets:
- Total PnL: $50k - $200k+ (depending on market conditions and parameter tuning)
- Sharpe ratio: 1.5 - 3.0+
- Max drawdown: 10% - 25%
