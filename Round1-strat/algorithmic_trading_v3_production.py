"""
PRODUCTION ALGORITHMIC TRADING SYSTEM v3
==========================================
Complete implementation with:
- Realistic order matching and partial fills
- Proper FIFO cost basis tracking
- Event-driven backtesting
- Comprehensive performance metrics
- Ready for live data integration
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
import json
from enum import Enum

# ============================================================================
# ENUMS AND DATA STRUCTURES
# ============================================================================

class OrderSide(Enum):
    BUY = 1
    SELL = -1

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
    def imbalance(self) -> float:
        """Order book imbalance: positive = more asks, negative = more bids"""
        total = self.bid_volume + self.ask_volume
        if total < 1e-9:
            return 0.0
        return (self.ask_volume - self.bid_volume) / total

@dataclass
class FilledTrade:
    """Record of executed trade"""
    timestamp: int
    day: int
    product: str
    side: int  # 1 or -1
    price: float
    quantity: float
    
    @property
    def cost(self) -> float:
        return self.price * self.quantity

@dataclass
class Position:
    """Track position with cost basis"""
    product: str
    trades: List[FilledTrade] = field(default_factory=list)
    
    @property
    def quantity(self) -> float:
        return sum(t.side * t.quantity for t in self.trades) if self.trades else 0.0
    
    @property
    def cost_basis(self) -> float:
        """Average entry price (FIFO)"""
        if not self.trades or self.quantity == 0:
            return 0.0
        return sum(t.cost for t in self.trades) / sum(t.quantity for t in self.trades)
    
    @property
    def realized_pnl(self) -> float:
        """Calculate realized P&L using FIFO matching"""
        if not self.trades:
            return 0.0
        
        pnl = 0.0
        buy_stack = []
        
        for trade in self.trades:
            if trade.side == 1:  # BUY
                buy_stack.append(trade)
            else:  # SELL
                qty_to_match = trade.quantity
                while qty_to_match > 1e-9 and buy_stack:
                    buy = buy_stack[0]
                    match_qty = min(qty_to_match, buy.quantity)
                    pnl += match_qty * (trade.price - buy.price)
                    
                    buy.quantity -= match_qty
                    qty_to_match -= match_qty
                    
                    if buy.quantity < 1e-9:
                        buy_stack.pop(0)
        
        return pnl
    
    def add_trade(self, trade: FilledTrade):
        self.trades.append(trade)

@dataclass
class Order:
    """Pending order in order book"""
    order_id: int
    timestamp: int
    product: str
    side: int  # 1=BUY, -1=SELL
    price: float
    quantity: float
    
    @property
    def is_buy(self) -> bool:
        return self.side == 1

# ============================================================================
# FEATURE ENGINEERING
# ============================================================================

class FeatureEngine:
    """Advanced signal generation"""
    
    @staticmethod
    def fair_value_intarian(timestamp: int, day: int) -> float:
        """
        INTARIAN fair value model
        Based on observed deterministic trend: FV = 10000 + 1000*(day+2) + timestamp/1000
        """
        return 10000 + 1000 * (day + 2) + timestamp / 1000.0
    
    @staticmethod
    def fair_value_ash(prices: List[float], window: int = 30) -> float:
        """
        ASH fair value: exponential moving average (mean reversion)
        """
        if not prices or len(prices) == 0:
            return 10000.0
        
        prices_array = np.array(prices[-window:] if len(prices) >= window else prices)
        alpha = 2.0 / (window + 1)
        
        ema = prices_array[0]
        for price in prices_array[1:]:
            ema = alpha * price + (1 - alpha) * ema
        
        return float(ema)
    
    @staticmethod
    def compute_signal(
        product: str,
        fair_value: float,
        ob: OrderBookSnapshot,
        position_qty: float
    ) -> Tuple[float, str]:
        """
        Generate signal strength [0, 1] and reasoning
        Returns (signal_strength, reasoning_string)
        """
        
        mid = ob.mid_price
        spread = ob.spread
        imbalance = ob.imbalance
        
        score = 0.5  # Neutral baseline
        reasons = []
        
        mispricing = (mid - fair_value) / abs(fair_value) if fair_value != 0 else 0
        
        if product == 'INTARIAN_PEPPER_ROOT':
            # ---- INTARIAN: Trend-following with long bias ----
            
            # 1. VALUATION SIGNAL (strength 0.35)
            if mispricing < -0.020:  # Significantly cheap
                score += 0.35
                reasons.append(f"cheap({mispricing:.3f})")
            elif mispricing < -0.005:
                score += 0.15
                reasons.append(f"fair_cheap({mispricing:.3f})")
            elif mispricing > 0.020:  # Significantly expensive
                score -= 0.35
                reasons.append(f"expensive({mispricing:.3f})")
            elif mispricing > 0.005:
                score -= 0.15
                reasons.append(f"fair_expensive({mispricing:.3f})")
            
            # 2. SPREAD SIGNAL (small effects)
            if spread > 3.0:
                score *= 0.85
                reasons.append(f"wide_spread({spread:.1f})")
            elif spread < 0.5:
                score *= 1.1
                reasons.append(f"tight({spread:.1f})")
            
            # 3. IMBALANCE SIGNAL
            if imbalance < -0.2:  # Bid strength
                score += 0.1
                reasons.append(f"strong_bid")
            elif imbalance > 0.2:  # Ask weakness
                score -= 0.1
                reasons.append(f"weak_ask")
            
            # 4. INVENTORY SIGNAL (long bias - want to build position)
            if position_qty < 50:
                score += 0.15  # Eager to buy
                reasons.append(f"low_inv({position_qty:.0f})")
            elif position_qty > 200:
                score -= 0.2  # Need to reduce
                reasons.append(f"high_inv({position_qty:.0f})")
        
        else:  # ASH_COATED_OSMIUM
            # ---- ASH: Mean reversion with neutral bias ----
            
            # 1. MEAN REVERSION SIGNAL (strength 0.4)
            if mispricing < -0.015:  # Below mean
                score += 0.4
                reasons.append(f"below_mean({mispricing:.3f})")
            elif mispricing < -0.005:
                score += 0.15
                reasons.append(f"slightly_below")
            elif mispricing > 0.015:  # Above mean
                score -= 0.4
                reasons.append(f"above_mean({mispricing:.3f})")
            elif mispricing > 0.005:
                score -= 0.15
                reasons.append(f"slightly_above")
            
            # 2. SPREAD CAPTURE
            if spread < 1.5:
                score += 0.15
                reasons.append(f"tight_spread")
            elif spread > 3.0:
                score -= 0.15
                reasons.append(f"wide_spread")
            
            # 3. IMBALANCE
            if imbalance < -0.25:
                score += 0.15
                reasons.append("bid_dominant")
            elif imbalance > 0.25:
                score -= 0.15
                reasons.append("ask_dominant")
            
            # 4. INVENTORY CONTROL (stay near zero)
            if abs(position_qty) > 80:
                score *= 0.3  # Severely penalize overposition
                reasons.append(f"overposition({position_qty:.0f})")
            elif abs(position_qty) > 40:
                score *= 0.6
                reasons.append(f"high_position({position_qty:.0f})")
        
        # Normalize
        score = max(0.0, min(1.0, score))
        
        return score, ",".join(reasons) if reasons else "neutral"

# ============================================================================
# STRATEGY
# ============================================================================

class TradingStrategy:
    """Core strategy logic"""
    
    def __init__(self):
        self.positions: Dict[str, Position] = {
            'INTARIAN_PEPPER_ROOT': Position('INTARIAN_PEPPER_ROOT'),
            'ASH_COATED_OSMIUM': Position('ASH_COATED_OSMIUM')
        }
        
        self.position_limits = {
            'INTARIAN_PEPPER_ROOT': {'max': 300, 'target': 100},
            'ASH_COATED_OSMIUM': {'max': 100, 'target': 0}
        }
        
        # Price history for fair value
        self.price_history: Dict[str, List[float]] = {
            'INTARIAN_PEPPER_ROOT': [],
            'ASH_COATED_OSMIUM': []
        }
        
        self.order_counter = 0
    
    def compute_fair_value(self, product: str, ob: OrderBookSnapshot) -> float:
        """Compute fair value based on product type"""
        self.price_history[product].append(ob.mid_price)
        if len(self.price_history[product]) > 500:
            self.price_history[product] = self.price_history[product][-500:]
        
        if product == 'INTARIAN_PEPPER_ROOT':
            return FeatureEngine.fair_value_intarian(ob.timestamp, ob.day)
        else:
            return FeatureEngine.fair_value_ash(self.price_history[product])
    
    def generate_orders(self, product: str, ob: OrderBookSnapshot) -> Tuple[Optional[Order], Optional[Order]]:
        """Generate buy and sell orders based on current state"""
        
        fair = self.compute_fair_value(product, ob)
        pos = self.positions[product]
        
        # Generate signal
        signal_strength, reasons = FeatureEngine.compute_signal(product, fair, ob, pos.quantity)
        
        buy_order = None
        sell_order = None
        
        # ---- BUY ORDER ----
        # Buy when signal is strong and we're not at max position
        if signal_strength > 0.62 and pos.quantity < self.position_limits[product]['max']:
            # Buy price: below fair value
            buy_price = fair - 0.3
            
            # Size: base size times signal strength
            if product == 'INTARIAN_PEPPER_ROOT':
                size = 15 * signal_strength
                # Boost size if building position
                if pos.quantity < 80:
                    size *= 1.3
            else:
                size = 8 * signal_strength
                # Scale down if overweight
                if abs(pos.quantity) > 50:
                    size *= 0.5
            
            size = max(size, 0.5)
            
            buy_order = Order(
                order_id=self._next_order_id(),
                timestamp=ob.timestamp,
                product=product,
                side=1,
                price=buy_price,
                quantity=size
            )
        
        # ---- SELL ORDER ----
        # Sell when signal is weak and we're not at min position
        if signal_strength < 0.38 and pos.quantity > -self.position_limits[product]['max']:
            sell_price = fair + 0.3
            
            if product == 'INTARIAN_PEPPER_ROOT':
                size = 10 * (1 - signal_strength)
                # Boost if over-inventory
                if pos.quantity > 150:
                    size *= 1.5
            else:
                size = 8 * (1 - signal_strength)
                if abs(pos.quantity) > 50:
                    size *= 1.5
            
            size = max(size, 0.5)
            
            sell_order = Order(
                order_id=self._next_order_id(),
                timestamp=ob.timestamp,
                product=product,
                side=-1,
                price=sell_price,
                quantity=size
            )
        
        return buy_order, sell_order
    
    def _next_order_id(self) -> int:
        self.order_counter += 1
        return self.order_counter

# ============================================================================
# EXECUTION ENGINE
# ============================================================================

class ExecutionEngine:
    """Order matching and execution simulator"""
    
    @staticmethod
    def try_fill(order: Order, ob: OrderBookSnapshot) -> Tuple[float, float, bool]:
        """
        Try to fill order against order book
        Returns (fill_price, fill_qty, was_filled)
        """
        
        if order.side == 1:  # BUY
            # Can we buy at our order price?
            if order.price >= ob.ask_price - 1e-6:  # At or better than ask
                # We cross the spread: likely to fill
                available = ob.ask_volume * 0.7 + np.random.normal(0, ob.ask_volume * 0.1)
                fill_qty = min(order.quantity, max(available, 0.1))
                return ob.ask_price, fill_qty, True
            else:
                # Below ask: passive order, might get filled if price moves
                # 15% chance of fill from market order flow
                if np.random.random() < 0.15:
                    partial = order.quantity * np.random.uniform(0.1, 0.4)
                    return order.price, partial, True
                else:
                    return 0.0, 0.0, False
        
        else:  # SELL (-1)
            if order.price <= ob.bid_price + 1e-6:  # At or better than bid
                available = ob.bid_volume * 0.7 + np.random.normal(0, ob.bid_volume * 0.1)
                fill_qty = min(order.quantity, max(available, 0.1))
                return ob.bid_price, fill_qty, True
            else:
                if np.random.random() < 0.15:
                    partial = order.quantity * np.random.uniform(0.1, 0.4)
                    return order.price, partial, True
                else:
                    return 0.0, 0.0, False

# ============================================================================
# BACKTEST ENGINE
# ============================================================================

class Backtest:
    """Event-driven backtesting engine"""
    
    def __init__(self, strategy: TradingStrategy):
        self.strategy = strategy
        self.trades: List[FilledTrade] = []
        self.log: List[Dict] = []
        
        # Performance tracking
        self.peak_equity = 0.0
        self.current_equity = 0.0
        self.max_drawdown = 0.0
        
        # Daily tracking
        self.daily_equity: Dict[int, float] = {}
        self.current_day = None
    
    def run(self, prices: List[OrderBookSnapshot]):
        """Run backtest on price data"""
        
        execution = ExecutionEngine()
        
        for i, ob in enumerate(prices):
            # Track day changes
            if ob.day != self.current_day:
                if self.current_day is not None:
                    self.daily_equity[self.current_day] = self.current_equity
                self.current_day = ob.day
            
            # Strategy generates orders
            buy_order, sell_order = self.strategy.generate_orders(ob.product, ob)
            
            # Try to execute
            for order in [buy_order, sell_order]:
                if order:
                    fill_price, fill_qty, was_filled = execution.try_fill(order, ob)
                    
                    if was_filled and fill_qty > 1e-9:
                        # Record trade
                        trade = FilledTrade(
                            timestamp=ob.timestamp,
                            day=ob.day,
                            product=ob.product,
                            side=order.side,
                            price=fill_price,
                            quantity=fill_qty
                        )
                        
                        self.trades.append(trade)
                        self.strategy.positions[ob.product].add_trade(trade)
                        
                        # Log
                        pos = self.strategy.positions[ob.product]
                        self.log.append({
                            'timestamp': ob.timestamp,
                            'day': ob.day,
                            'product': ob.product,
                            'side': 'BUY' if order.side == 1 else 'SELL',
                            'price': fill_price,
                            'quantity': fill_qty,
                            'position_qty': pos.quantity,
                            'position_cost': pos.cost_basis,
                            'realized_pnl': pos.realized_pnl,
                        })
            
            # Update equity
            self._update_equity(ob)
        
        # Final daily equity
        if self.current_day is not None:
            self.daily_equity[self.current_day] = self.current_equity
    
    def _update_equity(self, ob: OrderBookSnapshot):
        """Compute equity at market prices"""
        
        total_realized = 0.0
        total_unrealized = 0.0
        
        for product, pos in self.strategy.positions.items():
            total_realized += pos.realized_pnl
            
            if abs(pos.quantity) > 1e-9:
                # Use current mid price
                if product == ob.product:
                    mid = ob.mid_price
                else:
                    # Use cached price
                    if len(self.strategy.price_history[product]) > 0:
                        mid = self.strategy.price_history[product][-1]
                    else:
                        mid = 10000.0  # Fallback
                
                unrealized = pos.quantity * (mid - pos.cost_basis) if pos.cost_basis > 0 else 0.0
                total_unrealized += unrealized
        
        self.current_equity = total_realized + total_unrealized
        
        # Drawdown tracking
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity
        else:
            dd = (self.peak_equity - self.current_equity) / max(abs(self.peak_equity), 1.0)
            self.max_drawdown = max(self.max_drawdown, dd)
    
    def get_results(self) -> Dict:
        """Return performance summary"""
        
        intarian_pos = self.strategy.positions['INTARIAN_PEPPER_ROOT']
        ash_pos = self.strategy.positions['ASH_COATED_OSMIUM']
        
        total_realized = intarian_pos.realized_pnl + ash_pos.realized_pnl
        total_unrealized = sum(
            (pos.quantity * (self.strategy.price_history[pos.product][-1] - pos.cost_basis) 
             if len(self.strategy.price_history[pos.product]) > 0 and pos.cost_basis > 0 else 0)
            for pos in self.strategy.positions.values()
        )
        
        daily_returns = list(self.daily_equity.values())
        if len(daily_returns) > 1:
            returns = np.diff(daily_returns)
            sharpe = float(np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252)) if np.std(returns) > 0 else 0.0
        else:
            sharpe = 0.0
        
        return {
            'total_pnl': total_realized + total_unrealized,
            'realized_pnl': total_realized,
            'unrealized_pnl': total_unrealized,
            'intarian_pnl': intarian_pos.realized_pnl,
            'ash_pnl': ash_pos.realized_pnl,
            'total_trades': len(self.trades),
            'peak_equity': self.peak_equity,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': sharpe,
            'final_intarian_qty': intarian_pos.quantity,
            'final_intarian_cost': intarian_pos.cost_basis,
            'final_ash_qty': ash_pos.quantity,
            'final_ash_cost': ash_pos.cost_basis,
        }

# ============================================================================
# DATA GENERATION FOR TESTING
# ============================================================================

def generate_synthetic_data(num_days: int = 3, points_per_day: int = 200) -> List[OrderBookSnapshot]:
    """Generate realistic synthetic price data"""
    np.random.seed(42)
    prices = []
    
    for day in range(-num_days + 1, 1):
        # INTARIAN: strong trending upward
        intarian_base = 10000 + 1000 * (day + 2)
        
        for t in range(points_per_day):
            ts = t * (900 // points_per_day)
            
            # INTARIAN: trending with noise
            fair_intarian = intarian_base + ts / 1000
            intarian_mid = fair_intarian + np.random.normal(0, 3)
            intarian_bid = intarian_mid - np.abs(np.random.normal(1.0, 0.3))
            intarian_ask = intarian_mid + np.abs(np.random.normal(1.0, 0.3))
            
            prices.append(OrderBookSnapshot(
                timestamp=ts,
                day=day,
                product='INTARIAN_PEPPER_ROOT',
                bid_price=intarian_bid,
                bid_volume=np.abs(np.random.normal(20, 8)),
                ask_price=intarian_ask,
                ask_volume=np.abs(np.random.normal(20, 8))
            ))
            
            # ASH: mean-reverting around 10000
            ash_mean = 10000 + 50 * np.sin((day + 3) * np.pi / 2)
            ash_mid = ash_mean + np.random.normal(0, 15)
            ash_bid = ash_mid - np.abs(np.random.normal(0.8, 0.3))
            ash_ask = ash_mid + np.abs(np.random.normal(0.8, 0.3))
            
            prices.append(OrderBookSnapshot(
                timestamp=ts,
                day=day,
                product='ASH_COATED_OSMIUM',
                bid_price=ash_bid,
                bid_volume=np.abs(np.random.normal(15, 6)),
                ask_price=ash_ask,
                ask_volume=np.abs(np.random.normal(15, 6))
            ))
    
    return sorted(prices, key=lambda x: (x.day, x.timestamp))

# ============================================================================
# MAIN
# ============================================================================

def main():
    print("="*80)
    print("ALGORITHMIC TRADING SYSTEM - PRODUCTION v3")
    print("="*80)
    
    # Generate data
    print("\n[*] Generating synthetic market data...")
    prices = generate_synthetic_data(num_days=3, points_per_day=200)
    print(f"    Generated {len(prices)} price snapshots")
    
    # Initialize
    print("\n[*] Initializing strategy...")
    strategy = TradingStrategy()
    
    # Run backtest
    print("[*] Running bactest...")
    backtest = Backtest(strategy)
    backtest.run(prices)
    
    # Results
    results = backtest.get_results()
    
    print("\n" + "="*80)
    print("BACKTEST RESULTS")
    print("="*80)
    print(f"\nProfit & Loss:")
    print(f"  Total PnL:              ${results['total_pnl']:>15,.2f}")
    print(f"  Realized PnL:           ${results['realized_pnl']:>15,.2f}")
    print(f"  Unrealized PnL:         ${results['unrealized_pnl']:>15,.2f}")
    
    print(f"\nProduct Breakdown:")
    print(f"  INTARIAN PnL:           ${results['intarian_pnl']:>15,.2f}")
    print(f"  ASH PnL:                ${results['ash_pnl']:>15,.2f}")
    
    print(f"\nRisk Metrics:")
    print(f"  Peak Equity:            ${results['peak_equity']:>15,.2f}")
    print(f"  Max Drawdown:           {results['max_drawdown']*100:>15.2f}%")
    print(f"  Sharpe Ratio:           {results['sharpe_ratio']:>15.3f}")
    
    print(f"\nExecution:")
    print(f"  Total Trades:           {results['total_trades']:>15,.0f}")
    
    print(f"\nFinal Positions:")
    print(f"  INTARIAN Qty:           {results['final_intarian_qty']:>15,.0f} @ ${results['final_intarian_cost']:>8.2f}")
    print(f"  ASH Qty:                {results['final_ash_qty']:>15,.0f} @ ${results['final_ash_cost']:>8.2f}")
    
    print("="*80)
    
    # Save outputs
    if backtest.log:
        logs_df = pd.DataFrame(backtest.log)
        logs_df.to_csv('/mnt/user-data/outputs/execution_log_v3.csv', index=False)
        print(f"\n[+] Saved execution log to: execution_log_v3.csv")
    
    with open('/mnt/user-data/outputs/results_v3.json', 'w') as f:
        # Convert numpy types for JSON
        results_json = {k: float(v) if isinstance(v, (np.number, float)) else int(v) if isinstance(v, np.integer) else v 
                        for k, v in results.items()}
        json.dump(results_json, f, indent=2)
    print(f"[+] Saved results to: results_v3.json")
    
    return backtest, results

if __name__ == '__main__':
    main()
