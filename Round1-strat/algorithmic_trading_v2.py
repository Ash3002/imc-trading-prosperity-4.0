"""
ENHANCED ALGORITHMIC TRADING SYSTEM v2
========================================
Complete implementation with:
- Order execution and matching
- Realistic fill simulation
- Full PnL accounting
- Advanced signal generation
- Performance metrics
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import json

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class OrderBookSnapshot:
    timestamp: int
    day: int
    product: str
    bid_price: float
    bid_volume: float
    ask_price: float
    ask_volume: float
    
    @property
    def mid_price(self) -> float:
        return (self.bid_price + self.ask_price) / 2.0
    
    @property
    def spread(self) -> float:
        return self.ask_price - self.bid_price
    
    @property
    def microprice(self) -> float:
        total_vol = self.bid_volume + self.ask_volume
        if total_vol == 0:
            return self.mid_price
        return (self.bid_price * self.ask_volume + self.ask_price * self.bid_volume) / total_vol
    
    @property
    def imbalance(self) -> float:
        total_vol = self.bid_volume + self.ask_volume
        if total_vol == 0:
            return 0.0
        return (self.ask_volume - self.bid_volume) / total_vol

@dataclass
class Trade:
    timestamp: int
    day: int
    product: str
    direction: str
    price: float
    quantity: float
    
    @property
    def side(self) -> int:
        return 1 if self.direction == 'BUY' else -1

@dataclass
class Position:
    product: str
    quantity: float = 0.0
    vwap_entry: float = 0.0
    realized_pnl: float = 0.0
    
    def add_trade(self, direction: int, qty: float, price: float):
        """Execute trade and update position"""
        old_qty = self.quantity
        old_cost = old_qty * self.vwap_entry if abs(old_qty) > 1e-9 else 0.0
        
        # Realize P&L if closing position
        if old_qty * direction < 0:  # Opposite sign = closing
            close_qty = min(abs(direction * qty), abs(old_qty))
            self.realized_pnl += close_qty * (self.vwap_entry - price) if direction < 0 else close_qty * (price - self.vwap_entry)
        
        # Update quantity and VWAP
        new_qty = old_qty + direction * qty
        if abs(new_qty) < 1e-9:
            self.vwap_entry = 0.0
            self.quantity = 0.0
        else:
            new_cost = old_cost + direction * qty * price
            self.vwap_entry = new_cost / new_qty
            self.quantity = new_qty

@dataclass
class Order:
    order_id: int
    timestamp: int
    product: str
    side: int  # 1=BUY, -1=SELL
    price: float
    quantity: float
    filled_quantity: float = 0.0
    filled_price: float = 0.0
    
    @property
    def remaining(self) -> float:
        return self.quantity - self.filled_quantity
    
    @property
    def is_filled(self) -> bool:
        return self.filled_quantity >= self.quantity - 1e-9

@dataclass
class SignalEvent:
    timestamp: int
    day: int
    product: str
    signal_type: str  # 'BUY', 'SELL', 'NEUTRAL'
    strength: float   # [0, 1]
    fair_value: float
    mid_price: float
    spread: float
    imbalance: float
    reasons: str

# ============================================================================
# FEATURE ENGINEERING (ENHANCED)
# ============================================================================

class FeatureEngine:
    """Advanced signal generation"""
    
    @staticmethod
    def fair_value_intarian(timestamp: int, day: int) -> float:
        """
        INTARIAN_PEPPER_ROOT fair value
        Strong deterministic trend: FV = 10000 + 1000*(day+2) + timestamp/1000
        """
        return 10000 + 1000 * (day + 2) + timestamp / 1000.0
    
    @staticmethod
    def fair_value_ash(mid_prices: List[float], window: int = 50) -> float:
        """
        ASH_COATED_OSMIUM fair value
        Mean-reverting: use exponential moving average
        """
        if not mid_prices or len(mid_prices) == 0:
            return 10000.0
        
        prices = np.array(mid_prices)
        if len(prices) < window:
            return float(np.mean(prices))
        
        # Exponential moving average
        alpha = 2.0 / (window + 1)
        ema = prices[0]
        for price in prices[1:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return ema
    
    @staticmethod
    def analyze_intarian(
        timestamp: int, 
        day: int,
        fair_value: float,
        mid_price: float,
        spread: float,
        imbalance: float,
        position_qty: float
    ) -> Tuple[float, str]:
        """
        Generate signal for INTARIAN_PEPPER_ROOT
        Strategy: directional + inventory carry with long bias
        """
        score = 0.5  # Baseline neutral
        reasons = []
        
        # 1. VALUATION SIGNAL (strongest)
        mispricing = (mid_price - fair_value) / fair_value if fair_value > 0 else 0
        
        if mispricing < -0.015:  # Significantly undervalued
            score += 0.35
            reasons.append(f"undervalued({mispricing:.3f})")
        elif mispricing < -0.005:  # Moderately undervalued
            score += 0.15
            reasons.append(f"slightly_under({mispricing:.3f})")
        elif mispricing > 0.015:  # Significantly overvalued
            score -= 0.35
            reasons.append(f"overvalued({mispricing:.3f})")
        elif mispricing > 0.005:
            score -= 0.15
            reasons.append(f"slightly_over({mispricing:.3f})")
        
        # 2. SPREAD SIGNAL
        # Wide spread = lower liquidity, be careful
        if spread > 3.0:
            score *= 0.8
            reasons.append(f"wide_spread({spread:.1f})")
        elif spread < 1.0:
            score *= 1.1
            reasons.append(f"tight_spread({spread:.1f})")
        
        # 3. IMBALANCE SIGNAL
        # Positive imbalance = more ask volume = sell pressure
        if imbalance > 0.15:
            score *= 0.9
            reasons.append(f"ask_pressure({imbalance:.2f})")
        elif imbalance < -0.15:
            score *= 1.1
            reasons.append(f"bid_strength({imbalance:.2f})")
        
        # 4. INVENTORY SIGNAL (long bias)
        # Want to build and hold long position
        if position_qty < 30:
            score += 0.2 * (1 - min(position_qty / 30, 1))
            reasons.append(f"low_inventory({position_qty:.0f})")
        elif position_qty > 200:
            score -= 0.15
            reasons.append(f"high_inventory({position_qty:.0f})")
        
        # Normalize score to [0, 1]
        score = max(0.0, min(1.0, score))
        
        return score, ",".join(reasons)
    
    @staticmethod
    def analyze_ash(
        fair_value: float,
        mid_price: float,
        spread: float,
        imbalance: float,
        position_qty: float
    ) -> Tuple[float, str]:
        """
        Generate signal for ASH_COATED_OSMIUM
        Strategy: mean-reversion market making with neutral inventory
        """
        score = 0.5
        reasons = []
        
        # 1. MEAN REVERSION SIGNAL
        mispricing = (mid_price - fair_value) / fair_value if fair_value > 0 else 0
        
        if mispricing < -0.01:  # Below mean, buy
            score += 0.4
            reasons.append(f"mean_revert_down({mispricing:.3f})")
        elif mispricing > 0.01:  # Above mean, sell
            score -= 0.4
            reasons.append(f"mean_revert_up({mispricing:.3f})")
        
        # 2. SPREAD CAPTURE
        if spread < 2.0:
            score += 0.1
            reasons.append(f"spread_capture({spread:.1f})")
        else:
            score -= 0.1
            reasons.append(f"wide_spread({spread:.1f})")
        
        # 3. IMBALANCE (strength indicator)
        if imbalance < -0.2:  # Strong buying
            score += 0.15
            reasons.append(f"bid_strength({imbalance:.2f})")
        elif imbalance > 0.2:  # Strong selling
            score -= 0.15
            reasons.append(f"ask_weakness({imbalance:.2f})")
        
        # 4. INVENTORY CONTROL (stay near neutral)
        if abs(position_qty) > 80:
            score *= 0.5  # Heavily penalize over-position
            reasons.append(f"overposition({position_qty:.0f})")
        elif abs(position_qty) > 50:
            score *= 0.7
            reasons.append(f"high_position({position_qty:.0f})")
        
        score = max(0.0, min(1.0, score))
        
        return score, ",".join(reasons)

# ============================================================================
# TRADING STRATEGY
# ============================================================================

class TradingStrategy:
    """Hybrid strategy for both products"""
    
    def __init__(self):
        self.positions: Dict[str, Position] = {
            'INTARIAN_PEPPER_ROOT': Position('INTARIAN_PEPPER_ROOT'),
            'ASH_COATED_OSMIUM': Position('ASH_COATED_OSMIUM')
        }
        
        self.position_limits = {
            'INTARIAN_PEPPER_ROOT': {'max': 300, 'target': 100},
            'ASH_COATED_OSMIUM': {'max': 100, 'target': 0}
        }
        
        self.mid_price_history = {
            'INTARIAN_PEPPER_ROOT': [],
            'ASH_COATED_OSMIUM': []
        }
        
        self.order_counter = 0
    
    def generate_signal(self, 
                       product: str,
                       ob: OrderBookSnapshot) -> SignalEvent:
        """Generate trading signal"""
        
        mid = ob.mid_price
        spread = ob.spread
        imbalance = ob.imbalance
        pos = self.positions[product]
        
        # Update price history
        self.mid_price_history[product].append(mid)
        if len(self.mid_price_history[product]) > 500:
            self.mid_price_history[product] = self.mid_price_history[product][-500:]
        
        if product == 'INTARIAN_PEPPER_ROOT':
            fair = FeatureEngine.fair_value_intarian(ob.timestamp, ob.day)
            score, reasons = FeatureEngine.analyze_intarian(
                ob.timestamp, ob.day, fair, mid, spread, imbalance, pos.quantity
            )
        else:
            fair = FeatureEngine.fair_value_ash(self.mid_price_history[product])
            score, reasons = FeatureEngine.analyze_ash(
                fair, mid, spread, imbalance, pos.quantity
            )
        
        # Convert score to signal
        if score > 0.65:
            signal_type = 'BUY'
        elif score < 0.35:
            signal_type = 'SELL'
        else:
            signal_type = 'NEUTRAL'
        
        return SignalEvent(
            timestamp=ob.timestamp,
            day=ob.day,
            product=product,
            signal_type=signal_type,
            strength=score,
            fair_value=fair,
            mid_price=mid,
            spread=spread,
            imbalance=imbalance,
            reasons=reasons
        )
    
    def create_orders(self,
                     signal: SignalEvent,
                     ob: OrderBookSnapshot) -> Tuple[Optional[Order], Optional[Order]]:
        """
        Create buy/sell orders based on signal and order book
        """
        pos = self.positions[signal.product]
        
        buy_order = None
        sell_order = None
        
        # Determine order prices and sizes
        if signal.signal_type == 'BUY':
            # Aggressive: place buy order near/at ask
            size = self._compute_order_size(signal.product, signal.strength, is_buy=True)
            
            if size > 0 and pos.quantity < self.position_limits[signal.product]['max']:
                buy_price = ob.mid_price - 0.3  # Slightly inside bid
                
                buy_order = Order(
                    order_id=self._get_next_order_id(),
                    timestamp=ob.timestamp,
                    product=signal.product,
                    side=1,
                    price=buy_price,
                    quantity=size
                )
        
        elif signal.signal_type == 'SELL':
            size = self._compute_order_size(signal.product, signal.strength, is_buy=False)
            
            if size > 0 and pos.quantity > -self.position_limits[signal.product]['max']:
                sell_price = ob.mid_price + 0.3  # Slightly inside ask
                
                sell_order = Order(
                    order_id=self._get_next_order_id(),
                    timestamp=ob.timestamp,
                    product=signal.product,
                    side=-1,
                    price=sell_price,
                    quantity=size
                )
        
        return buy_order, sell_order
    
    def _compute_order_size(self, product: str, signal_strength: float, is_buy: bool) -> float:
        """Compute order size based on signal and inventory"""
        pos = self.positions[product]
        limits = self.position_limits[product]
        
        if product == 'INTARIAN_PEPPER_ROOT':
            # Base size scaled by signal strength
            base_size = 20 * signal_strength
            
            # Adjust for position
            if is_buy:
                # Buy more aggressively when below target
                if pos.quantity < limits['target']:
                    base_size *= 1.5
            else:
                # Sell aggressively when above target
                if pos.quantity > limits['target']:
                    base_size *= 1.5
            
            return max(base_size, 1.0)
        
        else:  # ASH_COATED_OSMIUM
            base_size = 10 * signal_strength
            
            # Reduce size if far from neutral
            distance_from_neutral = abs(pos.quantity) / limits['max']
            base_size *= max(0.3, 1.0 - distance_from_neutral)
            
            return max(base_size, 1.0)
    
    def _get_next_order_id(self) -> int:
        self.order_counter += 1
        return self.order_counter

# ============================================================================
# EXECUTION ENGINE
# ============================================================================

class ExecutionEngine:
    """Order matching and execution"""
    
    def __init__(self):
        self.pending_orders: Dict[int, Order] = {}
    
    def match_order(self, order: Order, ob: OrderBookSnapshot) -> Tuple[bool, float, float]:
        """
        Match order against order book
        Returns (filled, filled_price, filled_qty)
        """
        if order.side == 1:  # BUY
            # Check if can fill at order price
            if order.price >= ob.ask_price:
                # Aggressive buy: match at ask
                fill_qty = min(order.quantity, ob.ask_volume * 0.8)  # Assume 80% of volume available
                return True, ob.ask_price, fill_qty
            else:
                # Passive buy: place in book, might partially fill
                if np.random.random() < 0.1:  # 10% chance of partial fill
                    fill_qty = min(order.quantity * 0.3, ob.bid_volume * 0.1)
                    return True, order.price, fill_qty if fill_qty > 0 else 0.0
        
        else:  # SELL (-1)
            if order.price <= ob.bid_price:
                fill_qty = min(order.quantity, ob.bid_volume * 0.8)
                return True, ob.bid_price, fill_qty
            else:
                if np.random.random() < 0.1:
                    fill_qty = min(order.quantity * 0.3, ob.ask_volume * 0.1)
                    return True, order.price, fill_qty if fill_qty > 0 else 0.0
        
        return False, 0.0, 0.0
    
    def execute_order(self, order: Order, filled_price: float, filled_qty: float) -> bool:
        """Execute fill"""
        if filled_qty > 0:
            order.filled_quantity += filled_qty
            order.filled_price = filled_price if order.filled_quantity == 0 else \
                (order.filled_price * (order.filled_quantity - filled_qty) + filled_price * filled_qty) / order.filled_quantity
            return True
        return False

# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class Backtest:
    """Event-driven backtesting"""
    
    def __init__(self, strategy: TradingStrategy, executor: ExecutionEngine):
        self.strategy = strategy
        self.executor = executor
        
        # Tracking
        self.trade_log: List[Dict] = []
        self.daily_pnl: Dict[int, float] = defaultdict(float)
        self.realized_pnl_by_product: Dict[str, float] = defaultdict(float)
        
        self.max_drawdown = 0.0
        self.peak_equity = 0.0
        self.current_equity = 0.0
    
    def run(self, prices: List[OrderBookSnapshot]):
        """Run backtest on price data"""
        
        for i, ob in enumerate(prices):
            # Generate signal
            signal = self.strategy.generate_signal(ob.product, ob)
            
            # Create orders
            buy_order, sell_order = self.strategy.create_orders(signal, ob)
            
            # Try to execute
            for order in [buy_order, sell_order]:
                if order:
                    filled, filled_price, filled_qty = self.executor.match_order(order, ob)
                    
                    if filled and filled_qty > 0:
                        # Execute the trade
                        pos = self.strategy.positions[ob.product]
                        pos.add_trade(order.side, filled_qty, filled_price)
                        
                        # Log
                        self.trade_log.append({
                            'timestamp': ob.timestamp,
                            'day': ob.day,
                            'product': ob.product,
                            'side': 'BUY' if order.side == 1 else 'SELL',
                            'price': filled_price,
                            'quantity': filled_qty,
                            'position': pos.quantity,
                            'realized_pnl': pos.realized_pnl,
                        })
                        
                        self.daily_pnl[ob.day] += pos.realized_pnl
            
            # Update equity
            self._update_equity(ob)
    
    def _update_equity(self, ob: OrderBookSnapshot):
        """Compute equity at current market prices"""
        total_unrealized = 0.0
        total_realized = 0.0
        
        for product, pos in self.strategy.positions.items():
            total_realized += pos.realized_pnl
            
            if abs(pos.quantity) > 1e-9:
                # Use current mid price for valuation
                if product == ob.product:
                    mid = ob.mid_price
                else:
                    mid = 10000  # Placeholder
                
                unrealized = pos.quantity * (mid - pos.vwap_entry)
                total_unrealized += unrealized
        
        self.current_equity = total_realized + total_unrealized
        
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        else:
            dd = (self.peak_equity - self.current_equity) / max(abs(self.peak_equity), 1.0)
            self.max_drawdown = max(self.max_drawdown, dd)
    
    def get_results(self) -> Dict:
        """Summarize backtest"""
        trades_df = pd.DataFrame(self.trade_log)
        
        intarian_pnl = self.strategy.positions['INTARIAN_PEPPER_ROOT'].realized_pnl
        ash_pnl = self.strategy.positions['ASH_COATED_OSMIUM'].realized_pnl
        total_pnl = intarian_pnl + ash_pnl
        
        return {
            'total_pnl': total_pnl,
            'intarian_pnl': intarian_pnl,
            'ash_pnl': ash_pnl,
            'total_trades': len(self.trade_log),
            'peak_equity': self.peak_equity,
            'max_drawdown': self.max_drawdown,
            'final_intarian_qty': self.strategy.positions['INTARIAN_PEPPER_ROOT'].quantity,
            'final_ash_qty': self.strategy.positions['ASH_COATED_OSMIUM'].quantity,
        }

# ============================================================================
# SYNTHETIC DATA GENERATION
# ============================================================================

def generate_synthetic_data(num_days: int = 3, points_per_day: int = 100) -> List[OrderBookSnapshot]:
    """Generate realistic synthetic data"""
    np.random.seed(42)
    prices = []
    
    for day in range(-num_days + 1, 1):
        # INTARIAN: strong uptrend
        intarian_base = 10000 + 1000 * (day + 2)
        intarian_drift = np.random.normal(0, 20, points_per_day)
        intarian_drift = np.cumsum(intarian_drift)  # Random walk
        
        # ASH: mean-reverting
        ash_trend = 10000 + np.sin((day + 3) / 2) * 100
        ash_noise = np.random.normal(0, 30, points_per_day)
        ash_noise = np.cumsum(ash_noise)
        
        for t in range(points_per_day):
            timestamp = t * (900 // points_per_day)  # Spread over 900 seconds
            
            # INTARIAN prices
            intarian_mid = intarian_base + intarian_drift[t] + timestamp / 1000
            intarian_bid = intarian_mid - np.abs(np.random.normal(1.5, 0.5))
            intarian_ask = intarian_mid + np.abs(np.random.normal(1.5, 0.5))
            
            prices.append(OrderBookSnapshot(
                timestamp=timestamp,
                day=day,
                product='INTARIAN_PEPPER_ROOT',
                bid_price=intarian_bid,
                bid_volume=np.abs(np.random.normal(25, 10)),
                ask_price=intarian_ask,
                ask_volume=np.abs(np.random.normal(25, 10))
            ))
            
            # ASH prices
            ash_mid = ash_trend + ash_noise[t] + np.random.normal(0, 10)
            ash_bid = ash_mid - np.abs(np.random.normal(1.0, 0.5))
            ash_ask = ash_mid + np.abs(np.random.normal(1.0, 0.5))
            
            prices.append(OrderBookSnapshot(
                timestamp=timestamp,
                day=day,
                product='ASH_COATED_OSMIUM',
                bid_price=ash_bid,
                bid_volume=np.abs(np.random.normal(20, 8)),
                ask_price=ash_ask,
                ask_volume=np.abs(np.random.normal(20, 8))
            ))
    
    return sorted(prices, key=lambda x: (x.day, x.timestamp))

# ============================================================================
# MAIN RUNNER
# ============================================================================

def main():
    print("="*70)
    print("ALGORITHMIC TRADING SYSTEM - ENHANCED")
    print("="*70)
    
    # Generate synthetic data
    print("\n[*] Generating synthetic data...")
    prices = generate_synthetic_data(num_days=3, points_per_day=150)
    print(f"    - Generated {len(prices)} price snapshots")
    
    # Initialize
    print("\n[*] Initializing strategy and execution...")
    strategy = TradingStrategy()
    executor = ExecutionEngine()
    backtest = Backtest(strategy, executor)
    
    # Run
    print("[*] Running backtest...")
    backtest.run(prices)
    
    # Results
    results = backtest.get_results()
    
    print("\n" + "="*70)
    print("BACKTEST RESULTS")
    print("="*70)
    print(f"Total PnL:                ${results['total_pnl']:>12,.2f}")
    print(f"  - INTARIAN:             ${results['intarian_pnl']:>12,.2f}")
    print(f"  - ASH_COATED_OSMIUM:    ${results['ash_pnl']:>12,.2f}")
    print(f"\nTotal Trades:             {results['total_trades']:>12,.0f}")
    print(f"Peak Equity:              ${results['peak_equity']:>12,.2f}")
    print(f"Max Drawdown:             {results['max_drawdown']*100:>12.2f}%")
    print(f"\nFinal Positions:")
    print(f"  - INTARIAN:             {results['final_intarian_qty']:>12,.0f} units")
    print(f"  - ASH:                  {results['final_ash_qty']:>12,.0f} units")
    print("="*70)
    
    # Save logs
    if backtest.trade_log:
        logs_df = pd.DataFrame(backtest.trade_log)
        logs_df.to_csv('/mnt/user-data/outputs/trade_execution_log.csv', index=False)
        print(f"\n[+] Saved trade log to: /mnt/user-data/outputs/trade_execution_log.csv")
        
        # Summary statistics
        print(f"\nTrade Summary:")
        print(f"  Total trades: {len(logs_df)}")
        if len(logs_df) > 0:
            print(f"  Avg fill size: {logs_df['quantity'].mean():.2f}")
            print(f"  Buy trades: {len(logs_df[logs_df['side']=='BUY'])}")
            print(f"  Sell trades: {len(logs_df[logs_df['side']=='SELL'])}")
    
    # Save results
    with open('/mnt/user-data/outputs/backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f"[+] Saved results to: /mnt/user-data/outputs/backtest_results.json")
    
    return backtest, results

if __name__ == '__main__':
    main()
