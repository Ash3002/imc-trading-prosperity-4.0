# QUICK REFERENCE CARD
## Key Formulas, Parameters & Decision Rules

---

## 1. FAIR VALUE MODELS

### INTARIAN_PEPPER_ROOT (Trending)
```
FV = 10000 + 1000*(day+2) + timestamp/1000

Example:
- day=-2, timestamp=0: FV = 10000 + 1000*0 + 0 = 10000
- day=-2, timestamp=600: FV = 10000 + 1000*0 + 0.6 = 10000.6
- day=0, timestamp=600: FV = 10000 + 1000*2 + 0.6 = 12000.6
```

### ASH_COATED_OSMIUM (Mean-Reverting)
```
EMA = α * current_price + (1 - α) * prev_EMA
α = 2 / (window + 1) = 2 / 31 ≈ 0.0645

// Or in practice:
Fair Value ≈ 20-period or 30-period moving average
```

---

## 2. SIGNAL SCORE CALCULATION

### INTARIAN_PEPPER_ROOT

```
score = 0.5  // Start neutral

// 1. VALUATION (±0.35)
mispricing = (mid - FV) / FV
if mispricing < -2.0%:  score += 0.35
if -2.0% < mispricing < -0.5%: score += 0.15
if mispricing > 2.0%:   score -= 0.35
if 0.5% < mispricing < 2.0%:  score -= 0.15

// 2. SPREAD (±0.25)
if spread > 3.0: score *= 0.85
if spread < 0.5: score *= 1.10

// 3. IMBALANCE (±0.10)
if imbalance < -20%: score += 0.10
if imbalance > 20%:  score -= 0.10

// 4. INVENTORY (±0.15-0.20)
if position < 50:    score += 0.15
if position > 200:   score -= 0.20

// Decision
if score > 0.62: BUY
if score < 0.38: SELL
else:            NEUTRAL
```

### ASH_COATED_OSMIUM

```
score = 0.5

// 1. MEAN REVERSION (±0.40)
if mispricing < -1.5%: score += 0.40
if -1.5% < mispricing < -0.5%: score += 0.15
if mispricing > 1.5%:  score -= 0.40
if 0.5% < mispricing < 1.5%:   score -= 0.15

// 2. SPREAD (±0.15)
if spread < 1.5: score += 0.15
if spread > 3.0: score -= 0.15

// 3. IMBALANCE (±0.15)
if imbalance < -25%: score += 0.15
if imbalance > 25%:  score -= 0.15

// 4. INVENTORY (harsh penalty)
if abs(position) > 80:  score *= 0.3
if abs(position) > 40:  score *= 0.6

// Decision
if score > 0.62: BUY
if score < 0.38: SELL
else:            NEUTRAL
```

---

## 3. ORDER SIZING

### INTARIAN_PEPPER_ROOT
```
base_size = 15 * signal_strength

if position < 80:
    size = base_size * 1.3        // Build position boost
else:
    size = base_size              // Standard

if position > 200:
    size *= 1.5                   // Reduce position boost
    
final_size = max(size, 1.0)

Example: signal=0.75, position=40
size = 15 * 0.75 * 1.3 = 14.625 units
```

### ASH_COATED_OSMIUM
```
base_size = 8 * signal_strength

if abs(position) > 50:
    size = base_size * 0.5        // Scale down if overweight
else:
    size = base_size

if abs(position) > 80:
    size = 0                      // Don't add

final_size = max(size, 1.0)
```

---

## 4. ORDER PLACEMENT

```
For both products:

BUY ORDER:
  price = fair_value - 0.30
  quantity = computed above
  
SELL ORDER:
  price = fair_value + 0.30
  quantity = computed above

// Tuning guide:
offset  | execution | alpha | typical use
--------|-----------|-------|----------
0.10    | 30-50%    | lower | aggressive entry
0.30    | 10-30%    | med   | default (current)
0.50    | 2-10%     | high  | passive/opportunistic
1.00    | <1%       | max   | opportunistic only
```

---

## 5. POSITION LIMITS

### INTARIAN_PEPPER_ROOT
```
Max Long:       300 units
Target:         100 units (want to hold this)
Max Short:      -100 units (allow small hedges)
Range:          [-100, 300]
```

### ASH_COATED_OSMIUM
```
Max Long:       100 units
Target:         0 units (stay neutral)
Max Short:      -100 units
Range:          [-100, 100]
```

---

## 6. ORDER MATCHING LOGIC

```
BUY ORDER:
  if buy_price >= ask_price:
    → FILL at ask_price
    → qty = min(order_qty, ask_volume * 0.7)
  else:
    → 15% chance partial fill
    → qty = order_qty * random(0.1, 0.4)
  
SELL ORDER:
  if sell_price <= bid_price:
    → FILL at bid_price
    → qty = min(order_qty, bid_volume * 0.7)
  else:
    → 15% chance partial fill
    → qty = order_qty * random(0.1, 0.4)
```

---

## 7. PnL CALCULATION

### Trade-Level
```
For each BUY followed by SELL (FIFO):
  realized_pnl = quantity * (sell_price - buy_price)

Example:
  Buy 10 @ 11000
  Sell 5 @ 11010
  realized_pnl = 5 * (11010 - 11000) = $50
```

### Position-Level
```
unrealized_pnl = position_qty * (current_price - average_cost)

Example:
  Holding 5 units @ avg cost 11000
  Current price: 11020
  unrealized = 5 * (11020 - 11000) = $100

total_pnl = realized_pnl + unrealized_pnl
```

---

## 8. PERFORMANCE METRICS

```
Sharpe Ratio = (avg_daily_return / std_daily_return) * √252

Win Rate = profitable_trades / total_trades

Profit Factor = sum(winning_trades) / sum(losing_trades)

Maximum Drawdown = (peak_equity - trough) / peak_equity

Return on Risk = total_pnl / max_drawdown
```

---

## 9. PARAMETER TUNING CHECKLIST

### Priority 1 (Biggest Impact)
- [ ] BUY_THRESHOLD (0.62) - adjust ±0.05
- [ ] SELL_THRESHOLD (0.38) - adjust ±0.05
- [ ] BASE_SIZE (INTARIAN=15, ASH=8) - adjust ±5

### Priority 2 (Medium Impact)
- [ ] BUY/SELL offset (0.30) - adjust 0.1-0.5
- [ ] Position target (INTARIAN=100, ASH=0)
- [ ] Max position limits (INTARIAN=300, ASH=100)

### Priority 3 (Fine-tuning)
- [ ] Inventory boost factors (1.3 for INTARIAN)
- [ ] Spread thresholds (1.0, 3.0)
- [ ] Imbalance thresholds (-20%, +20%)

---

## 10. KEY DEFINITIONS

### Spread
```
spread = ask_price - bid_price

Interpretation:
  < 0.5: Very tight (good for execution)
  0.5-1.5: Tight (normal)
  1.5-3.0: Medium (be careful)
  > 3.0: Wide (illiquid or volatile)
```

### Imbalance
```
imbalance = (ask_volume - bid_volume) / (ask_volume + bid_volume)

Range: [-1, 1]

Interpretation:
  < -0.2: Strong buying pressure (bullish)
  -0.2 to +0.2: Balanced
  > +0.2: Strong selling pressure (bearish)
```

### Mispricing
```
mispricing = (mid_price - fair_value) / fair_value

Interpretation:
  < -2%: Significantly undervalued (strong BUY)
  -2% to 0%: Slightly undervalued
  0% to +2%: Slightly overvalued
  > +2%: Significantly overvalued (strong SELL)
```

---

## 11. OPTIMIZATION GRID

```
// Quick parameter sweep
for buy_thresh in [0.55, 0.60, 0.65, 0.70]:
  for sell_thresh in [0.30, 0.35, 0.40, 0.45]:
    for base_size in [10, 15, 20]:
      for offset in [0.1, 0.3, 0.5]:
        backtest()  → measure Sharpe ratio

// Then focus on top 5 combinations
```

---

## 12. DAILY CHECKLIST (FOR LIVE TRADING)

- [ ] Check position sizes (within limits?)
- [ ] Monitor unrealized PnL (is it reasonable?)
- [ ] Review fills (slippage acceptable?)
- [ ] Check daily loss (below threshold?)
- [ ] Verify no system errors in logs
- [ ] Fair value models still making sense?

---

## 13. QUICK START CODE

```python
from algorithmic_trading_v3_production import (
    Backtest, TradingStrategy, DataLoader
)

# Load
prices, trades = DataLoader.load_all_data(
    ['prices_round_1_day_-2.csv', ...],
    ['trades_round_1_day_-2.csv', ...]
)

# Run
strategy = TradingStrategy()
backtest = Backtest(strategy)
backtest.run(prices)

# Results
results = backtest.get_results()
print(f"PnL: ${results['total_pnl']:,.2f}")
print(f"Sharpe: {results['sharpe_ratio']:.3f}")
```

---

## 14. TROUBLESHOOTING MATRIX

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Sharpe < 0.8 | Bad signals | Improve fair value model |
| Zero trades | Thresholds too high | Lower BUY_THRESHOLD to 0.55 |
| Too many trades | Thresholds too low | Raise BUY_THRESHOLD to 0.70 |
| Large losses | Bad entries | Increase BUY_THRESHOLD |
| Can't fill | Too passive | Reduce offset to 0.1 |
| Slippage high | Too aggressive | Increase offset to 0.5 |
| High drawdown | Oversized | Cut BASE_SIZE in half |

---

## 15. MENTAL MODEL SUMMARY

```
┌─────────────────────────────────────────┐
│   Order Book Snapshot (tick-by-tick)    │
└──────────────┬──────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│ Fair Value Model (deterministic)         │
│ INTARIAN: 10000 + 1000*(day+2) + t/1000 │
│ ASH: EMA(last_30_prices)                 │
└──────────────┬──────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│ Feature Extraction                       │
│ - Mispricing (vs fair)                   │
│ - Spread (bid-ask width)                 │
│ - Imbalance (buy/sell pressure)          │
│ - Inventory (current position)           │
└──────────────┬──────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│ Signal Generation (score 0-1)            │
│ Weighted combination of features         │
└──────────────┬──────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│ Decision Rules                           │
│ BUY if score > 0.62                      │
│ SELL if score < 0.38                     │
│ NEUTRAL otherwise                        │
└──────────────┬──────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│ Order Generation                         │
│ - Price: fair ± 0.30                     │
│ - Size: base_size * signal * adjustments │
└──────────────┬──────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│ Order Matching                           │
│ - Check vs bid/ask                       │
│ - Simulate fills                         │
│ - Track position & cost basis            │
└──────────────┬──────────────────────────┘
               │
               ↓
┌──────────────────────────────────────────┐
│ P&L Calculation                          │
│ - Realized: closed positions (FIFO)      │
│ - Unrealized: open positions (mid)       │
│ - Total: realized + unrealized           │
└──────────────────────────────────────────┘
```

---

## 16. FORMULA REFERENCE SHEET

| Concept | Formula | Range | Sensitivity |
|---------|---------|-------|------------|
| Fair Value (INTARIAN) | 10000 + 1000*(d+2) + t/1000 | 10000-12000 | High |
| Fair Value (ASH) | EMA(prices, 30) | 9900-10100 | Medium |
| Mispricing | (P - FV) / FV | -5% to +5% | Critical |
| Spread | ask - bid | 0.5-3.0 | Medium |
| Imbalance | (ask_vol - bid_vol) / total | -1 to +1 | Medium |
| Score | weighted_sum | 0 to 1 | Critical |
| Position | ∑(side * qty) | -100 to +300 | High |
| PnL | ∑(realized) + (qty * Δprice) | Unbounded | Critical |
| Sharpe | E[R] / σ[R] * √252 | -∞ to ∞ | Key metric |

---

**Print this page and keep it at your desk for quick reference!** 📋

---

*Last updated: April 2026*
