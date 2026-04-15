# COMPLETE IMPLEMENTATION GUIDE
## Algorithmic Trading System for INTARIAN_PEPPER_ROOT & ASH_COATED_OSMIUM

---

## PART 1: QUICK START

### 1.1 Installation & Setup

```bash
# Required packages
pip install pandas numpy scipy scikit-learn matplotlib seaborn

# Clone or download the project
cd algorithmic_trading_system/
```

### 1.2 Running with Your Data

```python
import glob
from algorithmic_trading_v3_production import Backtest, TradingStrategy
from algorithmic_trading_system import DataLoader

# 1. Load your CSV files
price_files = [
    'prices_round_1_day_-2.csv',
    'prices_round_1_day_-1.csv',
    'prices_round_1_day_0.csv'
]

trade_files = [
    'trades_round_1_day_-2.csv',
    'trades_round_1_day_-1.csv',
    'trades_round_1_day_0.csv'
]

# 2. Load data
prices, trades = DataLoader.load_all_data(price_files, trade_files)
print(f"Loaded {len(prices)} price snapshots")

# 3. Run backtest
strategy = TradingStrategy()
backtest = Backtest(strategy)
backtest.run(prices)

# 4. Get results
results = backtest.get_results()
print(f"Total PnL: ${results['total_pnl']:,.2f}")
print(f"Sharpe Ratio: {results['sharpe_ratio']:.3f}")
```

### 1.3 Expected Input Format

**prices_XXX.csv:**
```
timestamp,day,product,bid_price,bid_volume,ask_price,ask_volume
0,-2,INTARIAN_PEPPER_ROOT,10000.5,20.0,10001.0,22.0
0,-2,ASH_COATED_OSMIUM,9999.8,15.0,10000.5,18.0
10,-2,INTARIAN_PEPPER_ROOT,10001.0,21.0,10001.5,23.0
...
```

**trades_XXX.csv:**
```
timestamp,day,product,direction,price,quantity
0,-2,INTARIAN_PEPPER_ROOT,BUY,10000.75,5.0
5,-2,ASH_COATED_OSMIUM,SELL,10000.2,3.0
...
```

---

## PART 2: STRATEGY ARCHITECTURE

### 2.1 Core Components

```
TradingStrategy
├─ Position tracking (quantity, cost basis, realized PnL)
├─ Fair value computation
├─ Signal generation
└─ Order creation

ExecutionEngine
├─ Order matching simulator
└─ Fill logic

Backtest
├─ Event processing
├─ Equity tracking
└─ Performance metrics
```

### 2.2 Signal Flow Diagram

```
OrderBook Snapshot
    ↓
Fair Value Model → INTARIAN: trend model
              └──→ ASH: exponential moving average
    ↓
Signal Analysis
├─ Valuation (vs fair value)
├─ Spreads (liquidity)
├─ Imbalance (market pressure)
└─ Inventory (position management)
    ↓
Signal Score [0, 1]
    ↓
Decision Rules
├─ BUY if score > 0.62
├─ SELL if score < 0.38
└─ NEUTRAL otherwise
    ↓
Order Generation
├─ Price: fair ± offset
└─ Size: based on signal + position
    ↓
Order Matching
└─ Fill against order book
```

---

## PART 3: KEY PARAMETERS & TUNING

### 3.1 Signal Thresholds

**Current Settings:**
```python
BUY_THRESHOLD = 0.62   # Signal score > this triggers buy
SELL_THRESHOLD = 0.38  # Signal score < this triggers sell
```

**How to Tune:**
- Higher buy threshold → fewer but higher-conviction buys
- Lower sell threshold → more aggressive selling
- Trade off: more trades vs higher signal quality

**Testing Strategy:**
```python
for buy_thresh in [0.55, 0.60, 0.65, 0.70]:
    for sell_thresh in [0.30, 0.35, 0.40, 0.45]:
        results = run_backtest_with_params(buy_thresh, sell_thresh)
        print(f"{buy_thresh}, {sell_thresh}: Sharpe={results['sharpe']:.3f}")
```

### 3.2 Order Sizing

**INTARIAN:**
```python
# Base size × signal strength
size = 15 * signal_strength

# Boost if building position
if position_qty < 80:
    size *= 1.3

# Parameters to tune:
BASE_SIZE = 15        # Try: 10-20
BUILD_BOOST = 1.3     # Try: 1.1-1.5
BUILD_THRESHOLD = 80  # Try: 50-150
```

**ASH:**
```python
# Market maker: smaller sizes
size = 8 * signal_strength

# Scale down if overweight
if abs(position_qty) > 50:
    size *= 0.5
```

### 3.3 Order Placement (Price Offsets)

**Current:**
```python
buy_price = fair_value - 0.30    # Buy 30 bps below fair
sell_price = fair_value + 0.30   # Sell 30 bps above fair
```

**Tuning Recommendations:**
| Offset | Execution | Alpha Capture |
|--------|-----------|---|
| 0.1 | High | Lower |
| 0.3 | Medium | Medium |
| 0.5 | Lower | Higher |
| 1.0 | Very Low | Highest |

**Strategy**: Start with 0.3, then:
- If execution rate < 5%: decrease offset
- If execution rate > 50%: increase offset (grab more alpha)

### 3.4 Fair Value Models

**INTARIAN (deterministic):**
```python
FV = 10000 + 1000*(day+2) + timestamp/1000

# Can fine-tune coefficients:
FV = A + B*(day+offset) + C*timestamp + D*timestamp²

# Regression on actual data:
from scipy import optimize
def fit_model(prices_df):
    def loss(params):
        predicted = params[0] + params[1]*prices_df['day'] + params[2]*prices_df['timestamp']
        return np.sum((predicted - prices_df['price'])**2)
    result = optimize.minimize(loss, [10000, 1000, 0.001])
    return result.x
```

**ASH (mean-reverting):**
```python
# Current: simple EMA
ema = alpha * current_price + (1 - alpha) * prev_ema

# Parameters:
EMA_WINDOW = 30      # Try: 20-50
EMA_ALPHA = 2/(window+1)

# Advanced: Kalman filter or ARIMA for better estimates
```

### 3.5 Position Limits

**Current:**
```python
INTARIAN: max=300, target=+100, min=-100
ASH:      max=100, target=0,    min=-100
```

**Tuning Logic:**
- Increase `target` → more aggressive directional bet
- Increase `max` → higher capital allocation
- Adjust based on:
  - Risk appetite
  - Capital available
  - Margin requirements

---

## PART 4: PERFORMANCE OPTIMIZATION

### 4.1 Parameter Sweep Example

```python
import itertools
import pandas as pd

def grid_search():
    """Find optimal parameters"""
    
    params = {
        'buy_threshold': [0.55, 0.60, 0.65, 0.70],
        'sell_threshold': [0.30, 0.35, 0.40, 0.45],
        'base_size': [10, 15, 20],
        'price_offset': [0.2, 0.3, 0.5]
    }
    
    results = []
    
    for combo in itertools.product(*params.values()):
        param_dict = dict(zip(params.keys(), combo))
        
        # Run backtest with these params
        backtest = run_backtest_with_params(**param_dict)
        result = backtest.get_results()
        
        results.append({
            **param_dict,
            'pnl': result['total_pnl'],
            'sharpe': result['sharpe_ratio'],
            'max_dd': result['max_drawdown'],
            'trades': result['total_trades']
        })
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('sharpe', ascending=False)
    
    return results_df.head(10)

# Run it
best_params = grid_search()
print(best_params)
```

### 4.2 Walk-Forward Analysis

Test on non-overlapping periods:

```python
def walk_forward_test(all_prices, test_fraction=0.2):
    """Simulate live trading"""
    
    n = len(all_prices)
    test_size = int(n * test_fraction)
    
    all_results = []
    
    # Divide into train/test windows
    for i in range(0, n - test_size, test_size):
        train_data = all_prices[:i]
        test_data = all_prices[i:i+test_size]
        
        # Train on historical data
        params = optimize_params(train_data)
        
        # Test on unseen data
        backtest = Backtest(TradingStrategy(**params))
        backtest.run(test_data)
        results = backtest.get_results()
        
        all_results.append(results)
    
    # Summary
    avg_pnl = np.mean([r['total_pnl'] for r in all_results])
    avg_sharpe = np.mean([r['sharpe_ratio'] for r in all_results])
    
    print(f"Walk-forward Sharpe: {avg_sharpe:.3f}")
    print(f"Walk-forward PnL: ${avg_pnl:,.2f}")
```

### 4.3 Sensitivity Analysis

```python
def sensitivity_analysis():
    """Check robustness to parameter changes"""
    
    baseline = run_backtest(params=DEFAULT_PARAMS)
    baseline_sharpe = baseline.get_results()['sharpe_ratio']
    
    sensitivities = {}
    
    for param_name in ['buy_threshold', 'base_size', 'position_target']:
        sensitivities[param_name] = {}
        
        original_value = DEFAULT_PARAMS[param_name]
        
        for pct_change in [-20, -10, -5, 0, 5, 10, 20]:
            new_value = original_value * (1 + pct_change/100)
            params = DEFAULT_PARAMS.copy()
            params[param_name] = new_value
            
            result = run_backtest(params)
            sharpe = result.get_results()['sharpe_ratio']
            
            sensitivities[param_name][pct_change] = sharpe - baseline_sharpe
    
    return sensitivities
```

---

## PART 5: MONITORING & LIVE TRADING

### 5.1 Real-Time Monitoring Dashboard

```python
import time
from datetime import datetime

def live_monitor(strategy, executor):
    """Monitor positions and PnL in real-time"""
    
    while True:
        # Fetch latest market data
        market_data = fetch_market_data()
        
        # Update positions
        for product in market_data:
            ob = market_data[product]
            
            # Compute fair value
            fair = strategy.compute_fair_value(product, ob)
            
            # Check position
            pos = strategy.positions[product]
            unrealized = pos.quantity * (ob.mid_price - pos.cost_basis)
            
            # Log
            print(f"\n{datetime.now()} - {product}")
            print(f"  Price: ${ob.mid_price:.2f} | Fair: ${fair:.2f}")
            print(f"  Bid/Ask: ${ob.bid_price:.2f} / ${ob.ask_price:.2f}")
            print(f"  Position: {pos.quantity:.0f} @ ${pos.cost_basis:.2f}")
            print(f"  P&L: Realized ${pos.realized_pnl:.2f} | Unrealized ${unrealized:.2f}")
        
        time.sleep(1)  # Update every second
```

### 5.2 Risk Controls

```python
class RiskController:
    """Enforce risk limits during live trading"""
    
    def __init__(self, max_daily_loss=-50000, max_position_loss=-20000):
        self.max_daily_loss = max_daily_loss
        self.max_position_loss = max_position_loss
        self.daily_loss = 0.0
    
    def check_order(self, order, positions):
        """Approve or reject order based on risk"""
        
        # Check if order would breach position limit
        new_qty = positions[order.product].quantity + order.side * order.quantity
        if abs(new_qty) > 300:
            return False, "Position limit breached"
        
        # Check if would increase daily loss
        potential_loss = self._estimate_loss(order, positions)
        if self.daily_loss + potential_loss < self.max_daily_loss:
            return False, "Daily loss limit breached"
        
        return True, "OK"
    
    def update_daily_loss(self, realized_pnl, unrealized_pnl):
        self.daily_loss += realized_pnl
    
    def reset_daily(self):
        self.daily_loss = 0.0
```

### 5.3 Logging & Alerting

```python
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Log trades
def log_trade(trade):
    logger.info(f"TRADE FILLED: {trade.product} {trade.side} {trade.quantity}@{trade.price:.2f}")

# Alert on significant moves
def check_alerts(position, fair_value, mid_price):
    mispricing = (mid_price - fair_value) / fair_value
    
    if abs(mispricing) > 0.05:
        logger.warning(f"Large mispricing: {mispricing:.2%}")
    
    if abs(position.quantity) > 200:
        logger.warning(f"Large position: {position.quantity:.0f}")
```

---

## PART 6: DEPLOYMENT CHECKLIST

### Before Going Live

- [ ] Backtested on ≥3 months of historical data
- [ ] Walk-forward test shows consistent performance
- [ ] Parameter sensitivity checked
- [ ] Risk controls implemented and tested
- [ ] Execution engine matches real broker behavior
- [ ] Slippage assumptions validated
- [ ] Latency/timing verified
- [ ] Order types match broker API (limit, market, etc.)
- [ ] Monitoring dashboard ready
- [ ] Alert system configured
- [ ] Kill switch implemented (emergency close all)
- [ ] Paper trading run for 1 week
- [ ] Position limits set in broker accounts
- [ ] Daily loss limits configured

### During Live Trading

- [ ] Monitor live dashboard
- [ ] Check position sizes daily
- [ ] Review fills and slippage
- [ ] Track realized vs expected PnL
- [ ] Verify no system errors in logs
- [ ] Check for regulatory/compliance issues

### Rebalancing Schedule

- **Daily**: Check position limits, daily loss
- **Weekly**: Review performance, check for model drift
- **Monthly**: Full backtest with latest data, reoptimize parameters
- **Quarterly**: Strategy review, consider new signals

---

## PART 7: TROUBLESHOOTING

### Problem: Low execution rate (< 5% of orders fill)

**Cause**: Order placement too passive

**Solutions**:
1. Reduce price offset (0.3 → 0.1)
2. Increase order size
3. Switch to market orders for aggressive fills

### Problem: High execution rate (> 50% orders fill)

**Cause**: Order placement too aggressive

**Solutions**:
1. Increase price offset (0.3 → 0.5)
2. Reduce order size
3. Be more selective with signals

### Problem: Large unrealized losses

**Cause**: Adverse price movement or poor position management

**Solutions**:
1. Reduce position limits
2. Tighten inventory targets
3. Review signal generation logic
4. Consider hedging

### Problem: Low Sharpe ratio

**Causes**: Low alpha or high volatility

**Solutions**:
1. Improve signal generation
2. Reduce position sizing
3. Diversify across more products
4. Reduce holding periods (shorter-term trading)

---

## PART 8: ADVANCED TOPICS

### 8.1 Machine Learning Enhancement

```python
from sklearn.ensemble import RandomForestClassifier

class MLSignalGenerator:
    def __init__(self):
        self.model = RandomForestClassifier()
    
    def train(self, features, labels):
        """Train on historical data"""
        self.model.fit(features, labels)
    
    def predict(self, features):
        """Predict next price direction"""
        return self.model.predict_proba(features)
```

### 8.2 Multi-Asset Correlation

```python
def correlation_aware_sizing(positions, correlation_matrix):
    """Adjust sizing based on correlation"""
    
    portfolio_var = 0
    for p1, pos1 in positions.items():
        for p2, pos2 in positions.items():
            corr = correlation_matrix.loc[p1, p2]
            portfolio_var += pos1.quantity * pos2.quantity * corr
    
    return portfolio_var
```

### 8.3 Adaptive Parameters

```python
def adaptive_signal_threshold(win_rate, recent_sharpe):
    """Dynamically adjust thresholds based on performance"""
    
    if win_rate < 0.4:
        return 0.70  # Stricter signal
    elif recent_sharpe > 2.0:
        return 0.60  # Relax if performing well
    else:
        return 0.65  # Default
```

---

## SUPPORT & RESOURCES

- Full strategy documentation: `STRATEGY_GUIDE.md`
- Code documentation: See docstrings in each function
- Example notebooks: `examples/` directory
- Performance analysis tools: `analysis/`

---

## FINAL NOTES

This system is designed to be:
1. **Transparent**: All decisions logged and traceable
2. **Testable**: Comprehensive backtesting framework
3. **Adaptive**: Parameters can be tuned and optimized
4. **Robust**: Risk controls and safety checks throughout

Success with algorithmic trading requires:
- Discipline in following the system
- Regular performance monitoring
- Continuous improvement through testing
- Proper risk management (never overlook)

Good luck! 🚀
