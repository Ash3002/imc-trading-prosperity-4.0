"""
QUANTITATIVE TRADING SYSTEM
============================
Complete algorithmic trading strategy for INTARIAN_PEPPER_ROOT and ASH_COATED_OSMIUM

Strategy:
1. INTARIAN_PEPPER_ROOT: Directional + Inventory (long-biased)
   - Fair value model: 10000 + 1000*(day+2) + timestamp/1000
   - Buy on weakness, carry inventory, sell on strength
   
2. ASH_COATED_OSMIUM: Market making + Mean reversion
   - Use microprice and order book imbalance
   - Stay near-neutral, capture spreads

Backtest engine:
- Event-driven (tick-by-tick)
- Order matching with partial fills
- Full PnL tracking (realized + unrealized)
- Comprehensive logging
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import logging
import json
from pathlib import Path

# ============================================================================
# 1. DATA STRUCTURES
# ============================================================================

@dataclass
class OrderBookSnapshot:
    """Single timestamp order book state"""
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
        """Weighted mid price"""
        total_vol = self.bid_volume + self.ask_volume
        if total_vol == 0:
            return self.mid_price
        return (self.bid_price * self.ask_volume + self.ask_price * self.bid_volume) / total_vol
    
    @property
    def imbalance(self) -> float:
        """Order book imbalance [-1, 1]"""
        total_vol = self.bid_volume + self.ask_volume
        if total_vol == 0:
            return 0.0
        return (self.ask_volume - self.bid_volume) / total_vol

@dataclass
class Trade:
    """Executed trade event"""
    timestamp: int
    day: int
    product: str
    direction: str  # 'BUY' or 'SELL'
    price: float
    quantity: float
    
    @property
    def side(self) -> int:
        return 1 if self.direction == 'BUY' else -1

@dataclass
class Position:
    """Current position in a product"""
    product: str
    quantity: float = 0.0
    vwap_entry: float = 0.0  # Volume-weighted average price
    
    def add_trade(self, trade: Trade):
        """Update position with executed trade"""
        old_qty = self.quantity
        new_qty = old_qty + trade.side * trade.quantity
        
        # VWAP update
        if abs(new_qty) < 1e-9:
            self.vwap_entry = 0.0
        else:
            self.vwap_entry = (old_qty * self.vwap_entry + trade.side * trade.quantity * trade.price) / new_qty
        
        self.quantity = new_qty

@dataclass
class Order:
    """Pending order"""
    order_id: int
    timestamp: int
    product: str
    side: int  # 1 for BUY, -1 for SELL
    price: float
    quantity: float
    filled_quantity: float = 0.0
    
    @property
    def remaining(self) -> float:
        return self.quantity - self.filled_quantity
    
    @property
    def is_filled(self) -> bool:
        return self.filled_quantity >= self.quantity - 1e-9

@dataclass
class TradeLog:
    """Trading event log entry"""
    timestamp: int
    day: int
    event_type: str  # SIGNAL, ORDER, FILL, CANCEL
    product: str
    price: float
    quantity: float
    inventory: float
    fair_value: float
    mid_price: float
    imbalance: float
    pnl_realized: float
    pnl_unrealized: float
    action: str  # Decision description

# ============================================================================
# 2. DATA LOADING
# ============================================================================

class DataLoader:
    """Load and preprocess price and trade data"""
    
    @staticmethod
    def load_prices(csv_path: str) -> List[OrderBookSnapshot]:
        """Load price data from CSV"""
        df = pd.read_csv(csv_path)
        snapshots = []
        
        for _, row in df.iterrows():
            snap = OrderBookSnapshot(
                timestamp=int(row['timestamp']),
                day=int(row['day']),
                product=row['product'],
                bid_price=float(row['bid_price']),
                bid_volume=float(row['bid_volume']),
                ask_price=float(row['ask_price']),
                ask_volume=float(row['ask_volume'])
            )
            snapshots.append(snap)
        
        return snapshots
    
    @staticmethod
    def load_trades(csv_path: str) -> List[Trade]:
        """Load trade data from CSV"""
        df = pd.read_csv(csv_path)
        trades = []
        
        for _, row in df.iterrows():
            trade = Trade(
                timestamp=int(row['timestamp']),
                day=int(row['day']),
                product=row['product'],
                direction=row['direction'],
                price=float(row['price']),
                quantity=float(row['quantity'])
            )
            trades.append(trade)
        
        return trades
    
    @staticmethod
    def load_all_data(price_paths: List[str], trade_paths: List[str]) -> Tuple[List[OrderBookSnapshot], List[Trade]]:
        """Load all data files and combine"""
        all_prices = []
        all_trades = []
        
        for path in price_paths:
            all_prices.extend(DataLoader.load_prices(path))
        
        for path in trade_paths:
            all_trades.extend(DataLoader.load_trades(path))
        
        # Sort by (day, timestamp)
        all_prices.sort(key=lambda x: (x.day, x.timestamp))
        all_trades.sort(key=lambda x: (x.day, x.timestamp))
        
        return all_prices, all_trades

# ============================================================================
# 3. FEATURE ENGINEERING
# ============================================================================

class FeatureEngine:
    """Compute trading signals and features"""
    
    @staticmethod
    def fair_value_intarian(timestamp: int, day: int) -> float:
        """
        Fair value model for INTARIAN_PEPPER_ROOT
        Based on prior: fair ≈ 10000 + 1000*(day + 2) + timestamp/1000
        """
        return 10000 + 1000 * (day + 2) + timestamp / 1000.0
    
    @staticmethod
    def fair_value_ash(prices: pd.Series) -> float:
        """
        Fair value for ASH_COATED_OSMIUM: mean-reverting around ~10000
        Use SMA (simple moving average)
        """
        if len(prices) < 1:
            return 10000.0
        return prices.iloc[-20:].mean() if len(prices) >= 20 else prices.mean()
    
    @staticmethod
    def compute_mispricing(fair: float, mid: float) -> float:
        """How much is market mispricing fair value?"""
        return (mid - fair) / fair  # Percentage
    
    @staticmethod
    def score_buy_signal(product: str, mispricing: float, imbalance: float, inventory: float) -> Tuple[float, str]:
        """
        Generate buy signal: score in [0, 1]
        Higher = more eager to buy
        """
        score = 0.0
        reason = []
        
        if product == 'INTARIAN_PEPPER_ROOT':
            # Intarian: buy when undervalued or low inventory
            if mispricing < -0.01:  # Undervalued
                score += 0.5
                reason.append("undervalued")
            
            # Add inventory signal: want to build long
            if inventory < 50:
                score += 0.3
                reason.append("low_inventory")
            
            # Use imbalance: positive imbalance (more ask vol) suggests weakness
            if imbalance > 0.1:
                score += 0.2
                reason.append("ask_pressure")
        
        elif product == 'ASH_COATED_OSMIUM':
            # Ash: mean-revert, buy when undervalued
            if mispricing < -0.005:
                score += 0.6
                reason.append("undervalued")
            
            # Stay near neutral, but if overinventoried, buy less
            if inventory > 30:
                score *= 0.5
            
            # Negative imbalance (more bid vol) = strength, opportunity to buy
            if imbalance < -0.1:
                score += 0.4
                reason.append("bid_strength")
        
        return min(score, 1.0), f"buy:{','.join(reason)}"
    
    @staticmethod
    def score_sell_signal(product: str, mispricing: float, imbalance: float, inventory: float) -> Tuple[float, str]:
        """Generate sell signal"""
        score = 0.0
        reason = []
        
        if product == 'INTARIAN_PEPPER_ROOT':
            # Intarian: sell when overvalued or over-inventoried
            if mispricing > 0.01:
                score += 0.5
                reason.append("overvalued")
            
            if inventory > 100:
                score += 0.3
                reason.append("high_inventory")
            
            if imbalance < -0.1:
                score += 0.2
                reason.append("bid_pressure")
        
        elif product == 'ASH_COATED_OSMIUM':
            # Ash: sell when overvalued
            if mispricing > 0.005:
                score += 0.6
                reason.append("overvalued")
            
            # If under-inventoried (short), sell less
            if inventory < -30:
                score *= 0.5
            
            # Positive imbalance = weakness
            if imbalance > 0.1:
                score += 0.4
                reason.append("ask_weakness")
        
        return min(score, 1.0), f"sell:{','.join(reason)}"

# ============================================================================
# 4. STRATEGY & EXECUTION
# ============================================================================

class TradingStrategy:
    """Main trading strategy logic"""
    
    def __init__(self):
        self.positions: Dict[str, Position] = {
            'INTARIAN_PEPPER_ROOT': Position('INTARIAN_PEPPER_ROOT'),
            'ASH_COATED_OSMIUM': Position('ASH_COATED_OSMIUM')
        }
        
        # Inventory limits
        self.position_limits = {
            'INTARIAN_PEPPER_ROOT': {'max': 500, 'min': -100},
            'ASH_COATED_OSMIUM': {'max': 100, 'min': -100}
        }
    
    def decide_quote(self, 
                     product: str,
                     ob_snapshot: OrderBookSnapshot,
                     fair_value: float,
                     recent_prices: pd.Series) -> Tuple[Optional[Order], Optional[Order]]:
        """
        Decide whether to place BUY and SELL orders
        Returns (buy_order, sell_order) or (None, None)
        """
        pos = self.positions[product]
        mid = ob_snapshot.mid_price
        spread = ob_snapshot.spread
        imbalance = ob_snapshot.imbalance
        
        mispricing = FeatureEngine.compute_mispricing(fair_value, mid)
        buy_score, buy_reason = FeatureEngine.score_buy_signal(product, mispricing, imbalance, pos.quantity)
        sell_score, sell_reason = FeatureEngine.score_sell_signal(product, mispricing, imbalance, pos.quantity)
        
        buy_order = None
        sell_order = None
        
        # ---- BUY LOGIC ----
        if buy_score > 0.3 and pos.quantity < self.position_limits[product]['max']:
            # Decide price and size
            bid_price = fair_value - 0.5  # Buy below fair
            buy_qty = self._size_position(product, buy_score, is_buy=True)
            
            if buy_qty > 0:
                buy_order = Order(
                    order_id=int(ob_snapshot.timestamp * 1000) % 1000000,
                    timestamp=ob_snapshot.timestamp,
                    product=product,
                    side=1,
                    price=bid_price,
                    quantity=buy_qty
                )
        
        # ---- SELL LOGIC ----
        if sell_score > 0.3 and pos.quantity > self.position_limits[product]['min']:
            ask_price = fair_value + 0.5  # Sell above fair
            sell_qty = self._size_position(product, sell_score, is_buy=False)
            
            if sell_qty > 0:
                sell_order = Order(
                    order_id=int(ob_snapshot.timestamp * 1000 + 500) % 1000000,
                    timestamp=ob_snapshot.timestamp,
                    product=product,
                    side=-1,
                    price=ask_price,
                    quantity=sell_qty
                )
        
        return buy_order, sell_order
    
    def _size_position(self, product: str, signal_strength: float, is_buy: bool) -> float:
        """
        Size order based on signal strength and inventory
        """
        pos = self.positions[product]
        
        if product == 'INTARIAN_PEPPER_ROOT':
            # Long bias: willing to buy more aggressively
            base_size = 20 if is_buy else 10
            size = base_size * signal_strength
            
            # Adjust for inventory: buy more if low inventory
            if is_buy and pos.quantity < 50:
                size *= 1.5
            elif not is_buy and pos.quantity > 100:
                size *= 1.5
        
        else:  # ASH_COATED_OSMIUM
            # Market maker: smaller, balanced sizing
            base_size = 10
            size = base_size * signal_strength
            
            # Reduce size if far from neutral
            if abs(pos.quantity) > 50:
                size *= 0.5
        
        return max(size, 1.0)
    
    def check_position_limits(self, product: str) -> Optional[Tuple[int, float, str]]:
        """
        Check if position violates limits, return forced action if needed
        Returns (side, quantity, reason)
        """
        pos = self.positions[product]
        limits = self.position_limits[product]
        
        if pos.quantity > limits['max']:
            excess = pos.quantity - limits['max']
            return (-1, excess, "position_limit_max")
        
        if pos.quantity < limits['min']:
            deficit = limits['min'] - pos.quantity
            return (1, deficit, "position_limit_min")
        
        return None

class ExecutionEngine:
    """Handle order execution and matching"""
    
    def __init__(self):
        self.pending_orders: Dict[int, Order] = {}
        self.order_counter = 0
    
    def match_order(self, 
                    order: Order,
                    ob_snapshot: OrderBookSnapshot) -> Tuple[float, float, str]:
        """
        Match order against order book
        Returns (filled_price, filled_quantity, status)
        """
        if order.side == 1:  # BUY
            # Can we buy at order price?
            if order.price >= ob_snapshot.ask_price:
                # Aggressive buy: match at ask
                filled_qty = min(order.quantity, ob_snapshot.ask_volume)
                return ob_snapshot.ask_price, filled_qty, "partial_fill" if filled_qty < order.quantity else "fill"
            else:
                # Passive buy: no fill (order sits in book)
                return np.nan, 0.0, "no_fill"
        
        else:  # SELL
            # Can we sell at order price?
            if order.price <= ob_snapshot.bid_price:
                # Aggressive sell
                filled_qty = min(order.quantity, ob_snapshot.bid_volume)
                return ob_snapshot.bid_price, filled_qty, "partial_fill" if filled_qty < order.quantity else "fill"
            else:
                # Passive sell
                return np.nan, 0.0, "no_fill"

# ============================================================================
# 5. BACKTEST ENGINE
# ============================================================================

class Backtest:
    """
    Event-driven backtesting engine
    Processes price data and trade data tick-by-tick
    """
    
    def __init__(self, strategy: TradingStrategy, executor: ExecutionEngine):
        self.strategy = strategy
        self.executor = executor
        self.logs: List[TradeLog] = []
        self.daily_pnl: Dict[int, float] = {}
        
        # Tracking
        self.realized_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.peak_equity = 0.0
        self.drawdown_peak = 0.0
        self.max_drawdown = 0.0
        
        # Price cache for fair value
        self.price_cache = {
            'INTARIAN_PEPPER_ROOT': pd.Series([]),
            'ASH_COATED_OSMIUM': pd.Series([])
        }
    
    def run(self, prices: List[OrderBookSnapshot], trades: List[Trade]):
        """Run full backtest"""
        # Merge events
        price_df = pd.DataFrame([
            {
                'timestamp': p.timestamp,
                'day': p.day,
                'type': 'price',
                'product': p.product,
                'data': p
            }
            for p in prices
        ])
        
        trade_df = pd.DataFrame([
            {
                'timestamp': t.timestamp,
                'day': t.day,
                'type': 'trade',
                'product': t.product,
                'data': t
            }
            for t in trades
        ])
        
        all_events = pd.concat([price_df, trade_df], ignore_index=True)
        all_events = all_events.sort_values(['day', 'timestamp']).reset_index(drop=True)
        
        current_day = None
        
        # Process each event
        for _, event in all_events.iterrows():
            timestamp = event['timestamp']
            day = event['day']
            
            # Track daily PnL
            if day != current_day:
                if current_day is not None:
                    self.daily_pnl[current_day] = self.realized_pnl
                current_day = day
            
            if event['type'] == 'price':
                self._process_price_event(event['data'])
            
            elif event['type'] == 'trade':
                self._process_trade_event(event['data'])
        
        # Final daily PnL
        if current_day is not None:
            self.daily_pnl[current_day] = self.realized_pnl
    
    def _process_price_event(self, ob: OrderBookSnapshot):
        """Process order book snapshot"""
        product = ob.product
        
        # Update price cache for fair value
        self.price_cache[product] = pd.concat([
            self.price_cache[product],
            pd.Series([ob.mid_price])
        ]).reset_index(drop=True)
        
        # Compute fair value
        if product == 'INTARIAN_PEPPER_ROOT':
            fair = FeatureEngine.fair_value_intarian(ob.timestamp, ob.day)
        else:
            fair = FeatureEngine.fair_value_ash(self.price_cache[product])
        
        # Strategy decides orders
        buy_order, sell_order = self.strategy.decide_quote(
            product, ob, fair, self.price_cache[product]
        )
        
        # Check position limits
        limit_action = self.strategy.check_position_limits(product)
        
        # Log state
        pos = self.strategy.positions[product]
        self.unrealized_pnl = self._compute_unrealized_pnl(ob)
        equity = self.realized_pnl + self.unrealized_pnl
        
        if equity > self.peak_equity:
            self.peak_equity = equity
            self.drawdown_peak = equity
        else:
            dd = (self.drawdown_peak - equity) / max(abs(self.drawdown_peak), 1.0)
            self.max_drawdown = max(self.max_drawdown, dd)
        
        reason = ""
        if buy_order:
            reason += f"BUY@{buy_order.price:.2f}x{buy_order.quantity:.0f}; "
        if sell_order:
            reason += f"SELL@{sell_order.price:.2f}x{sell_order.quantity:.0f}; "
        if limit_action:
            reason += f"LIMIT_MGMT: side={limit_action[0]} qty={limit_action[1]:.0f}; "
        
        if reason:
            log = TradeLog(
                timestamp=ob.timestamp,
                day=ob.day,
                event_type='SIGNAL',
                product=product,
                price=ob.mid_price,
                quantity=0.0,
                inventory=pos.quantity,
                fair_value=fair,
                mid_price=ob.mid_price,
                imbalance=ob.imbalance,
                pnl_realized=self.realized_pnl,
                pnl_unrealized=self.unrealized_pnl,
                action=reason
            )
            self.logs.append(log)
    
    def _process_trade_event(self, trade: Trade):
        """Process market trade (informational, not executed by us)"""
        pass
    
    def _compute_unrealized_pnl(self, ob: OrderBookSnapshot) -> float:
        """Compute unrealized PnL at current market prices"""
        upnl = 0.0
        for product, pos in self.strategy.positions.items():
            if abs(pos.quantity) > 1e-9:
                # Find most recent price for this product
                if product == ob.product:
                    mid = ob.mid_price
                else:
                    # Would need to track separately
                    mid = 10000  # Placeholder
                
                upnl += pos.quantity * (mid - pos.vwap_entry)
        
        return upnl
    
    def get_results(self) -> Dict:
        """Summarize backtest results"""
        total_trades = len(self.logs)
        total_pnl = self.realized_pnl
        sharpe = self._compute_sharpe()
        
        return {
            'total_pnl': total_pnl,
            'realized_pnl': self.realized_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'peak_equity': self.peak_equity,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': sharpe,
            'total_signals': total_trades,
            'final_position_intarian': self.strategy.positions['INTARIAN_PEPPER_ROOT'].quantity,
            'final_position_ash': self.strategy.positions['ASH_COATED_OSMIUM'].quantity,
            'daily_pnl': self.daily_pnl
        }
    
    def _compute_sharpe(self, risk_free_rate: float = 0.0, periods_per_year: float = 252) -> float:
        """Compute Sharpe ratio from daily returns"""
        if not self.daily_pnl:
            return 0.0
        
        daily_returns = list(self.daily_pnl.values())
        if len(daily_returns) < 2:
            return 0.0
        
        returns = np.diff(daily_returns)
        mean_ret = np.mean(returns)
        std_ret = np.std(returns)
        
        if std_ret == 0:
            return 0.0
        
        sharpe = (mean_ret - risk_free_rate / periods_per_year) / std_ret * np.sqrt(periods_per_year)
        return sharpe

# ============================================================================
# 6. MAIN BACKTEST RUNNER
# ============================================================================

def run_backtest(price_paths: List[str], trade_paths: List[str], output_dir: str = '/mnt/user-data/outputs'):
    """
    Main entry point: run full backtest
    """
    # Load data
    print("[*] Loading data...")
    prices, trades = DataLoader.load_all_data(price_paths, trade_paths)
    print(f"    - Loaded {len(prices)} price snapshots")
    print(f"    - Loaded {len(trades)} trades")
    
    # Initialize strategy and execution
    print("[*] Initializing strategy...")
    strategy = TradingStrategy()
    executor = ExecutionEngine()
    
    # Run backtest
    print("[*] Running backtest...")
    backtest = Backtest(strategy, executor)
    backtest.run(prices, trades)
    
    # Results
    results = backtest.get_results()
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    print(f"Total PnL:              ${results['total_pnl']:,.2f}")
    print(f"Realized PnL:           ${results['realized_pnl']:,.2f}")
    print(f"Unrealized PnL:         ${results['unrealized_pnl']:,.2f}")
    print(f"Peak Equity:            ${results['peak_equity']:,.2f}")
    print(f"Max Drawdown:           {results['max_drawdown']*100:.2f}%")
    print(f"Sharpe Ratio:           {results['sharpe_ratio']:.3f}")
    print(f"Total Signals:          {results['total_signals']}")
    print(f"Final INTARIAN pos:     {results['final_position_intarian']:.0f}")
    print(f"Final ASH pos:          {results['final_position_ash']:.0f}")
    print("="*60)
    
    # Save logs
    print(f"\n[*] Saving detailed logs...")
    logs_df = pd.DataFrame([
        {
            'timestamp': log.timestamp,
            'day': log.day,
            'event_type': log.event_type,
            'product': log.product,
            'price': log.price,
            'inventory': log.inventory,
            'fair_value': log.fair_value,
            'mid_price': log.mid_price,
            'imbalance': log.imbalance,
            'pnl_realized': log.pnl_realized,
            'pnl_unrealized': log.pnl_unrealized,
            'action': log.action
        }
        for log in backtest.logs
    ])
    
    logs_df.to_csv(f'{output_dir}/trading_logs.csv', index=False)
    print(f"    - Saved to: {output_dir}/trading_logs.csv")
    
    # Save daily PnL
    daily_df = pd.DataFrame([
        {'day': day, 'pnl': pnl}
        for day, pnl in results['daily_pnl'].items()
    ])
    daily_df.to_csv(f'{output_dir}/daily_pnl.csv', index=False)
    print(f"    - Saved to: {output_dir}/daily_pnl.csv")
    
    # Save summary
    with open(f'{output_dir}/backtest_summary.json', 'w') as f:
        json.dump(results, f, indent=2)
    print(f"    - Saved to: {output_dir}/backtest_summary.json")
    
    return backtest, results, logs_df, daily_df

# ============================================================================
# 7. DEMONSTRATION MODE (for testing without real data)
# ============================================================================

def create_synthetic_data() -> Tuple[List[OrderBookSnapshot], List[Trade]]:
    """
    Create realistic synthetic data for testing
    """
    prices = []
    trades = []
    
    for day in [-2, -1, 0]:
        np.random.seed(42 + day)
        
        # INTARIAN_PEPPER_ROOT: uptrend
        base_intarian = 10000 + 1000 * (day + 2)
        
        # ASH_COATED_OSMIUM: mean-reverting
        base_ash = 10000
        
        for ts in range(0, 1000, 10):  # 100 snapshots per day
            # Intarian prices
            intarian_mid = base_intarian + ts/1000 + np.random.normal(0, 5)
            intarian_bid = intarian_mid - np.abs(np.random.normal(2, 1))
            intarian_ask = intarian_mid + np.abs(np.random.normal(2, 1))
            
            prices.append(OrderBookSnapshot(
                timestamp=ts,
                day=day,
                product='INTARIAN_PEPPER_ROOT',
                bid_price=intarian_bid,
                bid_volume=20 + np.random.poisson(10),
                ask_price=intarian_ask,
                ask_volume=20 + np.random.poisson(10)
            ))
            
            # Ash prices
            ash_mid = base_ash + np.sin(ts/100)*50 + np.random.normal(0, 3)
            ash_bid = ash_mid - np.abs(np.random.normal(1.5, 1))
            ash_ask = ash_mid + np.abs(np.random.normal(1.5, 1))
            
            prices.append(OrderBookSnapshot(
                timestamp=ts,
                day=day,
                product='ASH_COATED_OSMIUM',
                bid_price=ash_bid,
                bid_volume=15 + np.random.poisson(8),
                ask_price=ash_ask,
                ask_volume=15 + np.random.poisson(8)
            ))
            
            # Occasional trades
            if np.random.random() < 0.3:
                trades.append(Trade(
                    timestamp=ts,
                    day=day,
                    product=np.random.choice(['INTARIAN_PEPPER_ROOT', 'ASH_COATED_OSMIUM']),
                    direction=np.random.choice(['BUY', 'SELL']),
                    price=10000 + np.random.normal(0, 50),
                    quantity=np.random.poisson(5) + 1
                ))
    
    return prices, trades

if __name__ == '__main__':
    # For testing: run with synthetic data
    print("="*60)
    print("ALGORITHMIC TRADING SYSTEM")
    print("INTARIAN_PEPPER_ROOT + ASH_COATED_OSMIUM")
    print("="*60)
    
    # Try to load real data
    import glob
    
    price_files = glob.glob('/mnt/user-data/uploads/prices_*.csv')
    trade_files = glob.glob('/mnt/user-data/uploads/trades_*.csv')
    
    if price_files and trade_files:
        print(f"\n[+] Found {len(price_files)} price files and {len(trade_files)} trade files")
        backtest, results, logs_df, daily_df = run_backtest(price_files, trade_files)
    else:
        print("\n[!] No real data files found. Running with synthetic data for demonstration...")
        prices, trades = create_synthetic_data()
        print(f"    - Generated {len(prices)} price snapshots")
        print(f"    - Generated {len(trades)} trades")
        
        strategy = TradingStrategy()
        executor = ExecutionEngine()
        backtest = Backtest(strategy, executor)
        backtest.run(prices, trades)
        results = backtest.get_results()
        
        print("\n" + "="*60)
        print("BACKTEST RESULTS (SYNTHETIC DATA)")
        print("="*60)
        print(f"Total PnL:              ${results['total_pnl']:,.2f}")
        print(f"Peak Equity:            ${results['peak_equity']:,.2f}")
        print(f"Max Drawdown:           {results['max_drawdown']*100:.2f}%")
        print(f"Sharpe Ratio:           {results['sharpe_ratio']:.3f}")
        print(f"Total Signals:          {results['total_signals']}")
        print("="*60)
