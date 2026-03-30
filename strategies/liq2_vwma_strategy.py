import math

import backtrader as bt

from strategies.base_strategy import BaseLoggingStrategy


class LIQ2VWMACompatibleStrategy(BaseLoggingStrategy):
    """
    Backtrader adaptation of LIQ2 VWMA logic for this app.

    Notes:
    - Uses current chart timeframe for all indicators.
    - Uses bar-close checks for DCA/TP (no intrabar path simulation).
    - `entry_profile`: 0 = official, 1 = hidden.
    """

    params = (
        ("vwma_length", 89),
        ("rsi_length", 14),
        ("smi_length", 30),
        ("smi_smooth", 5),
        ("ema_fast_length", 106),
        ("ema_slow_length", 36),
        ("entry_profile", 0),
        ("official_uptrend_deviation_bps", 200),
        ("official_downtrend_deviation_bps", 400),
        ("hidden_uptrend_deviation_bps", 100),
        ("hidden_downtrend_deviation_bps", 300),
        ("rsi_threshold", 40.0),
        ("smi_threshold", 0.0),
        ("dca_1_size", 6.0),
        ("dca_2_size", 12.0),
        ("dca_3_size", 24.0),
        ("dca_4_size", 48.0),
        ("dca_2_drawdown_bps", 150),
        ("dca_3_drawdown_bps", 300),
        ("dca_4_drawdown_bps", 600),
        ("uptrend_take_profit_bps", 150),
        ("downtrend_take_profit_bps", 100),
        ("max_bars_in_trade", 50),
        ("losing_streak_limit", 3),
        ("cooldown_bars", 48),
        ("commission", 0.001),
    )

    def __init__(self):
        super().__init__()

        vwma_period = int(self.p.vwma_length)
        rsi_period = int(self.p.rsi_length)
        smi_period = int(self.p.smi_length)
        smi_smooth = int(self.p.smi_smooth)
        ema_fast_period = int(self.p.ema_fast_length)
        ema_slow_period = int(self.p.ema_slow_length)

        price_volume_sum = bt.indicators.SumN(self.data.close * self.data.volume, period=vwma_period)
        volume_sum = bt.indicators.SumN(self.data.volume, period=vwma_period)
        self.vwma = price_volume_sum / (volume_sum + 1e-12)

        self.rsi = bt.indicators.RSI(self.data.close, period=rsi_period, safediv=True)

        highest_high = bt.indicators.Highest(self.data.high, period=smi_period)
        lowest_low = bt.indicators.Lowest(self.data.low, period=smi_period)
        midpoint = (highest_high + lowest_low) / 2.0
        rel = self.data.close - midpoint
        spread = highest_high - lowest_low
        rel_smoothed = bt.indicators.EMA(bt.indicators.EMA(rel, period=smi_smooth), period=smi_smooth)
        spread_smoothed = bt.indicators.EMA(bt.indicators.EMA(spread, period=smi_smooth), period=smi_smooth)
        self.smi = 200.0 * rel_smoothed / (spread_smoothed + 1e-12)

        self.ema_fast = bt.indicators.EMA(self.data.close, period=ema_fast_period)
        self.ema_slow = bt.indicators.EMA(self.data.close, period=ema_slow_period)

        self.first_entry_price = None
        self.entry_bar_index = None
        self.tp_ratio_for_trade = None
        self.dca_filled = [False, False, False, False]
        self.order_to_dca_index = {}
        self.losing_streak = 0
        self.cooldown_until_bar = -1

    @staticmethod
    def _bps_to_ratio(value_bps):
        return float(value_bps) / 10000.0

    @staticmethod
    def _is_finite(*values):
        return all(math.isfinite(float(value)) for value in values)

    def _is_uptrend(self, offset=0):
        fast = self.ema_fast[offset]
        slow = self.ema_slow[offset]
        if not self._is_finite(fast, slow):
            return False
        return fast > slow

    def _active_deviation_ratio(self, offset=-1):
        use_hidden_profile = int(round(self.p.entry_profile)) == 1
        is_uptrend = self._is_uptrend(offset=offset)

        if use_hidden_profile:
            bps = self.p.hidden_uptrend_deviation_bps if is_uptrend else self.p.hidden_downtrend_deviation_bps
        else:
            bps = self.p.official_uptrend_deviation_bps if is_uptrend else self.p.official_downtrend_deviation_bps

        return self._bps_to_ratio(bps)

    def _active_entry_level(self, offset=-1):
        vwma_value = self.vwma[offset]
        if not self._is_finite(vwma_value):
            return float("nan")
        return float(vwma_value) * (1.0 - self._active_deviation_ratio(offset=offset))

    def _take_profit_ratio(self, regime_is_uptrend):
        bps = self.p.uptrend_take_profit_bps if regime_is_uptrend else self.p.downtrend_take_profit_bps
        return self._bps_to_ratio(bps)

    def _dca_sizes(self):
        return [
            float(self.p.dca_1_size),
            float(self.p.dca_2_size),
            float(self.p.dca_3_size),
            float(self.p.dca_4_size),
        ]

    def _dca_drawdown_ratios(self):
        return [
            0.0,
            self._bps_to_ratio(self.p.dca_2_drawdown_bps),
            self._bps_to_ratio(self.p.dca_3_drawdown_bps),
            self._bps_to_ratio(self.p.dca_4_drawdown_bps),
        ]

    def _try_open_position(self):
        prev_level = self._active_entry_level(offset=-1)
        prev_low = self.data.low[-1]
        current_open = self.data.open[0]
        prev_rsi = self.rsi[-1]
        prev_smi = self.smi[-1]

        if not self._is_finite(prev_level, prev_low, current_open, prev_rsi, prev_smi):
            return

        touched_level = prev_low <= prev_level
        reclaimed_above_level = current_open > prev_level
        filters_ok = prev_rsi < float(self.p.rsi_threshold) and prev_smi < float(self.p.smi_threshold)
        if not (touched_level and reclaimed_above_level and filters_ok):
            return

        regime_is_uptrend = self._is_uptrend(offset=-1)
        self.tp_ratio_for_trade = self._take_profit_ratio(regime_is_uptrend=regime_is_uptrend)

        first_size = self._dca_sizes()[0]
        self.order = self.buy(size=first_size)
        self.order_to_dca_index[self.order.ref] = 0

    def _try_dca_entry(self):
        if self.first_entry_price is None:
            return False

        close_price = self.data.close[0]
        if not self._is_finite(close_price):
            return False

        drawdowns = self._dca_drawdown_ratios()
        sizes = self._dca_sizes()

        for dca_index in (1, 2, 3):
            if self.dca_filled[dca_index]:
                continue

            trigger_price = self.first_entry_price * (1.0 - drawdowns[dca_index])
            if close_price <= trigger_price:
                self.order = self.buy(size=sizes[dca_index])
                self.order_to_dca_index[self.order.ref] = dca_index
                return True

        return False

    def _should_take_profit(self):
        if self.tp_ratio_for_trade is None:
            return False

        close_price = self.data.close[0]
        avg_entry_price = float(self.position.price)
        if not self._is_finite(close_price, avg_entry_price) or avg_entry_price <= 0.0:
            return False

        take_profit_price = avg_entry_price * (1.0 + self.tp_ratio_for_trade)
        return close_price >= take_profit_price

    def _reset_trade_state(self):
        self.first_entry_price = None
        self.entry_bar_index = None
        self.tp_ratio_for_trade = None
        self.dca_filled = [False, False, False, False]
        self.order_to_dca_index = {}

    def next(self):
        self.record_equity()

        if self.order is not None:
            return

        if len(self) < 3:
            return

        if not self.position:
            if len(self) <= self.cooldown_until_bar:
                return
            self._try_open_position()
            return

        if self._try_dca_entry():
            return

        if self._should_take_profit():
            self.order = self.close()
            return

        if self.entry_bar_index is None:
            return

        bars_held = len(self) - self.entry_bar_index + 1
        if bars_held >= int(self.p.max_bars_in_trade):
            self.order = self.close()

    def notify_order(self, order):
        if order.status == order.Completed:
            if order.isbuy():
                dca_index = self.order_to_dca_index.pop(order.ref, None)
                if dca_index is not None:
                    self.dca_filled[dca_index] = True
                if self.first_entry_price is None:
                    self.first_entry_price = float(order.executed.price)
                    self.entry_bar_index = len(self)
            else:
                self.order_to_dca_index.pop(order.ref, None)
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.order_to_dca_index.pop(order.ref, None)

        super().notify_order(order)

    def notify_trade(self, trade):
        super().notify_trade(trade)

        if not trade.isclosed:
            return

        if float(trade.pnlcomm) < 0.0:
            self.losing_streak += 1
            if self.losing_streak >= int(self.p.losing_streak_limit):
                self.cooldown_until_bar = len(self) + int(self.p.cooldown_bars)
                self.losing_streak = 0
        else:
            self.losing_streak = 0

        self._reset_trade_state()
