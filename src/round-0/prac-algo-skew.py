# EMERALDS: checked's quote placement (best_bid+1 / best_ask-1)
#           captures 14pts/roundtrip vs v3's 2pts. EMERALDS fair
#           value is rock-stable at 10000 so adverse selection = zero.
#           Also adopts: MAX_POS=20, inventory skew, widening when heavy.
#
# TOMATOES: v3's passive MM (fair±3) with trend skew.
#           BB mean reversion cannot work with 14pt spread & 1-3pt std.
#           Passive MM earns ~6pts/roundtrip with no directional risk.

from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import json
import math

_EMA_ALPHA = 2.0 / 21   # FLOW_EMA_SPAN=20

PRODUCT_PARAMS: Dict[str, dict] = {

    'EMERALDS': dict(
        MODE='mkt_mm',      
        WINDOW=20,
        MAX_POS=20,
        MM_PER_TICK=3,      
        INVENTORY_SKEW=0.2,    
        WIDEN_THRESHOLD=0.6,    
    ),
    # ── TOMATOES ─────────────────────────────────────────────────────────
    # Logic: quote at fair±3. Fair = short SMA. Trend-skew to avoid
    # accumulating inventory against the drift direction.
    'TOMATOES': dict(
        MODE='fair_mm',        
        WINDOW=10,
        MAX_POS=8,
        MM_PER_TICK=2,
        QUOTE_OFFSET=3,        
        TREND_WINDOW=50,
        TREND_SKEW=1,          
    ),
}
DEFAULT_PARAMS = dict(
    MODE='fair_mm',
    WINDOW=15, MAX_POS=5, MM_PER_TICK=2,
    QUOTE_OFFSET=2, TREND_WINDOW=40, TREND_SKEW=0,
    INVENTORY_SKEW=0.0, WIDEN_THRESHOLD=0.6,
)


def _mid_obi(order_depth: OrderDepth):
    if not order_depth.buy_orders or not order_depth.sell_orders:
        return None
    best_bid = max(order_depth.buy_orders)
    best_ask = min(order_depth.sell_orders)
    bid_vol  = abs(order_depth.buy_orders[best_bid])
    ask_vol  = abs(order_depth.sell_orders[best_ask])
    denom    = bid_vol + ask_vol
    obi      = (bid_vol - ask_vol) / denom if denom else 0.0
    mid      = (best_bid + best_ask) / 2.0
    spread   = best_ask - best_bid
    return best_bid, best_ask, mid, spread, obi


def _signed_flow(market_trades, best_bid: float, best_ask: float) -> float:
    if not market_trades:
        return 0.0
    signed = 0.0
    prev_price = None
    for t in market_trades:
        price = float(t.price)
        qty   = float(t.quantity)
        d_ask = abs(price - best_ask)
        d_bid = abs(price - best_bid)
        if d_ask < d_bid:
            signed += qty
        elif d_bid < d_ask:
            signed -= qty
        else:
            if prev_price is not None:
                if price > prev_price:
                    signed += qty
                elif price < prev_price:
                    signed -= qty
        prev_price = price
    return signed


def _sma(history: list, window: int):
    w = history[-window:]
    return sum(w) / len(w) if len(w) >= window else None


class Trader:

    def run(self, state: TradingState):
        try:
            td = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            td = {}

        price_history: Dict[str, list]  = td.get("price_history", {})
        flow_ema:      Dict[str, float] = td.get("flow_ema", {})
        result: Dict[str, List[Order]] = {}

        for product, order_depth in state.order_depths.items():

            book = _mid_obi(order_depth)
            if book is None:
                continue
            best_bid, best_ask, mid, spread, obi = book

            p = {**DEFAULT_PARAMS, **PRODUCT_PARAMS.get(product, {})}
            MODE         = p["MODE"]
            WINDOW       = p["WINDOW"]
            MAX_POS      = p["MAX_POS"]
            MM_PER_TICK  = p["MM_PER_TICK"]
            TREND_WINDOW = p.get("TREND_WINDOW", 40)
            TREND_SKEW   = p.get("TREND_SKEW", 0)
            QUOTE_OFFSET = p.get("QUOTE_OFFSET", 2)
            INV_SKEW     = p.get("INVENTORY_SKEW", 0.0)
            WIDEN_THRESH = p.get("WIDEN_THRESHOLD", 0.6)

            # ── Price history ──────────────────────────────────────────────
            hist = price_history.setdefault(product, [])
            hist.append(mid)
            cap = max(WINDOW, TREND_WINDOW) * 3
            if len(hist) > cap:
                price_history[product] = hist[-cap:]
                hist = price_history[product]

            fair_sma = _sma(hist, WINDOW)
            if fair_sma is None:
                continue

            # ── Flow EMA ───────────────────────────────────────────────────
            raw_flow = _signed_flow(
                state.market_trades.get(product, []), best_bid, best_ask
            )
            flow_ema[product] = (_EMA_ALPHA * raw_flow
                                 + (1 - _EMA_ALPHA) * flow_ema.get(product, 0.0))

            position  = state.position.get(product, 0)
            orders: List[Order] = []

            # ══════════════════════════════════════════════════════════════
            # MODE: mkt_mm  (EMERALDS)
            # ══════════════════════════════════════════════════════════════
            if MODE == 'mkt_mm':
                buy_room  = MAX_POS - position
                sell_room = MAX_POS + position

                skew_ticks = 0
                if position != 0 and INV_SKEW > 0:
                   
                    skew_ticks = int(round(INV_SKEW * (position / max(1, MAX_POS)) * 2))

                widen = 1 if abs(position) > WIDEN_THRESH * MAX_POS else 0

                if buy_room > 0:
                    bid_q = best_bid + 1 - skew_ticks - widen
                    bid_q = max(bid_q, best_bid + 1)        
                    bid_q = min(bid_q, best_ask - 1)       
                    qty   = min(MM_PER_TICK, buy_room)
                    orders.append(Order(product, int(bid_q), qty))

                if sell_room > 0:
                    ask_q = best_ask - 1 - skew_ticks + widen
                    ask_q = min(ask_q, best_ask - 1)      
                    ask_q = max(ask_q, best_bid + 1)        
                    qty   = min(MM_PER_TICK, sell_room)
                    orders.append(Order(product, int(ask_q), -qty))

            # ══════════════════════════════════════════════════════════════
            # MODE: fair_mm  (TOMATOES + any unknown product)
            # ══════════════════════════════════════════════════════════════
            else:
                fair = int(round(fair_sma))

                # Trend detection
                trend_sma_val = _sma(hist, TREND_WINDOW)
                skew          = 0
                buy_cap_mult  = 1.0
                sell_cap_mult = 1.0
                if trend_sma_val is not None and TREND_SKEW > 0:
                    gap = fair_sma - trend_sma_val
                    if gap < -0.5:               
                        skew          = -TREND_SKEW
                        buy_cap_mult  = 0.5
                        sell_cap_mult = 1.5
                    elif gap > 0.5:                 
                        skew          = +TREND_SKEW
                        buy_cap_mult  = 1.5
                        sell_cap_mult = 0.5

                bid_q = fair - QUOTE_OFFSET + skew
                ask_q = fair + QUOTE_OFFSET + skew

                bid_q = min(bid_q, best_ask - 1)
                ask_q = max(ask_q, best_bid + 1)
                if bid_q >= ask_q:
                    continue

                buy_room  = MAX_POS - position
                sell_room = MAX_POS + position

                buy_qty  = max(0, int(min(MM_PER_TICK * buy_cap_mult,  buy_room)))
                sell_qty = max(0, int(min(MM_PER_TICK * sell_cap_mult, sell_room)))

                if buy_qty > 0:
                    orders.append(Order(product, bid_q, buy_qty))
                if sell_qty > 0:
                    orders.append(Order(product, ask_q, -sell_qty))

                inv_ratio = position / MAX_POS
                if inv_ratio > 0.6 and sell_room > sell_qty:
                    unwind_ask = max(ask_q - 1, best_bid + 1)
                    extra = min(MM_PER_TICK, sell_room - sell_qty)
                    if extra > 0:
                        orders.append(Order(product, unwind_ask, -extra))
                elif inv_ratio < -0.6 and buy_room > buy_qty:
                    unwind_bid = min(bid_q + 1, best_ask - 1)
                    extra = min(MM_PER_TICK, buy_room - buy_qty)
                    if extra > 0:
                        orders.append(Order(product, unwind_bid, extra))

            result[product] = orders

        new_trader_data = json.dumps({
            "price_history": price_history,
            "flow_ema":      flow_ema,
        })

        conversions = 0
        return result, conversions, new_trader_data