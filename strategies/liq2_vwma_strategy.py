import math

import backtrader as bt

from strategies.base_strategy import BaseLoggingStrategy


class LIQ2VWMACompatibleStrategy(BaseLoggingStrategy):
    CHART_INDICATOR_CONFIG = {
        "vwma": {
            "label": "VWMA",
            "panel": "price",
            "color": "#22c55e",
            "default_visible": True,
        },
        "rsi": {
            "label": "RSI",
            "panel": "oscillator",
            "color": "#38bdf8",
            "default_visible": True,
        },
        "smi": {
            "label": "SMI",
            "panel": "oscillator",
            "color": "#f97316",
            "default_visible": True,
        },
        "ema_fast": {
            "label": "EMA Fast",
            "panel": "price",
            "color": "#eab308",
            "default_visible": True,
        },
        "ema_slow": {
            "label": "EMA Slow",
            "panel": "price",
            "color": "#f43f5e",
            "default_visible": True,
        },
    }
    OPTIMIZATION_PARAM_WHITELIST = (
        "vwma_length",
        "rsi_length",
        "smi_length",
        "smi_smooth",
        "ema_fast_length",
        "ema_slow_length",
        "rsi_threshold",
        "smi_threshold",
        "dca_1_percent",
        "dca_2_percent",
        "dca_3_percent",
        "dca_4_percent",
        "take_profit_percent",
        "stop_loss_percent",
    )

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
        ("dca_1_percent", 1.0),
        ("dca_2_percent", 2.0),
        ("dca_3_percent", 4.0),
        ("dca_4_percent", 8.0),
        ("dca_2_drawdown_bps", 150),
        ("dca_3_drawdown_bps", 300),
        ("dca_4_drawdown_bps", 600),
        ("take_profit_percent", 1.5),
        ("stop_loss_percent", 2.0),
        ("max_bars_in_trade", 50),
        ("losing_streak_limit", 3),
        ("cooldown_bars", 48),
        ("commission", 0.001),
    )

    PARAMETER_SPECS = {
        "vwma_length": {"type": "int", "min": 1, "max": 500, "step": 1, "label_ru": "Длина VWMA", "optimization_group": "indicator"},
        "rsi_length": {"type": "int", "min": 2, "max": 200, "step": 1, "label_ru": "Длина RSI", "optimization_group": "indicator"},
        "smi_length": {"type": "int", "min": 2, "max": 500, "step": 1, "label_ru": "Длина SMI", "optimization_group": "indicator"},
        "smi_smooth": {"type": "int", "min": 1, "max": 100, "step": 1, "label_ru": "Сглаживание SMI", "optimization_group": "indicator"},
        "ema_fast_length": {"type": "int", "min": 1, "max": 500, "step": 1, "label_ru": "Длина быстрой EMA", "optimization_group": "indicator"},
        "ema_slow_length": {"type": "int", "min": 1, "max": 500, "step": 1, "label_ru": "Длина медленной EMA", "optimization_group": "indicator"},
        "entry_profile": {
            "type": "int",
            "choices": [0, 1],
            "label_ru": "Профиль входа",
        },
        "official_uptrend_deviation_bps": {"type": "int", "min": 0, "max": 10000, "step": 10, "label_ru": "Отклонение входа (официальный, ап-тренд), б.п."},
        "official_downtrend_deviation_bps": {"type": "int", "min": 0, "max": 10000, "step": 10, "label_ru": "Отклонение входа (официальный, даун-тренд), б.п."},
        "hidden_uptrend_deviation_bps": {"type": "int", "min": 0, "max": 10000, "step": 10, "label_ru": "Отклонение входа (скрытый, ап-тренд), б.п."},
        "hidden_downtrend_deviation_bps": {"type": "int", "min": 0, "max": 10000, "step": 10, "label_ru": "Отклонение входа (скрытый, даун-тренд), б.п."},
        "rsi_threshold": {"type": "float", "min": 0.0, "max": 100.0, "step": 0.5, "label_ru": "Порог RSI", "optimization_group": "indicator"},
        "smi_threshold": {"type": "float", "min": -100.0, "max": 100.0, "step": 0.1, "label_ru": "Порог SMI", "optimization_group": "indicator"},
        "dca_1_percent": {"type": "float", "min": 0.0, "max": 100.0, "step": 0.1, "label_ru": "Усреднение 1 (% депозита)", "optimization_group": "averaging"},
        "dca_2_percent": {"type": "float", "min": 0.0, "gt": "dca_1_percent", "max": 100.0, "step": 0.1, "label_ru": "Усреднение 2 (% депозита)", "optimization_group": "averaging"},
        "dca_3_percent": {"type": "float", "min": 0.0, "gt": "dca_2_percent", "max": 100.0, "step": 0.1, "label_ru": "Усреднение 3 (% депозита)", "optimization_group": "averaging"},
        "dca_4_percent": {"type": "float", "min": 0.0, "gt": "dca_3_percent", "max": 100.0, "step": 0.1, "label_ru": "Усреднение 4 (% депозита)", "optimization_group": "averaging"},
        "dca_2_drawdown_bps": {"type": "int", "min": 0, "max": 10000, "step": 10, "label_ru": "Просадка до усреднения 2, б.п."},
        "dca_3_drawdown_bps": {"type": "int", "min": 0, "gt": "dca_2_drawdown_bps", "max": 10000, "step": 10, "label_ru": "Просадка до усреднения 3, б.п."},
        "dca_4_drawdown_bps": {"type": "int", "min": 0, "gt": "dca_3_drawdown_bps", "max": 10000, "step": 10, "label_ru": "Просадка до усреднения 4, б.п."},
        "take_profit_percent": {"type": "float", "min": 0.0, "max": 100.0, "step": 0.1, "label_ru": "Тейк-профит (%)", "optimization_group": "take_profit"},
        "stop_loss_percent": {"type": "float", "min": 0.0, "max": 100.0, "step": 0.1, "label_ru": "Стоп-лосс (%)", "optimization_group": "stop_loss"},
        "max_bars_in_trade": {"type": "int", "min": 1, "max": 10000, "step": 1, "label_ru": "Макс. свечей в сделке"},
        "losing_streak_limit": {"type": "int", "min": 1, "max": 1000, "step": 1, "label_ru": "Лимит серии убытков"},
        "cooldown_bars": {"type": "int", "min": 0, "max": 10000, "step": 1, "label_ru": "Пауза после серии (свечи)"},
        "commission": {"type": "float", "min": 0.0, "max": 0.05, "step": 0.0001, "label_ru": "Комиссия"},
    }

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
        self.stop_loss_ratio_for_trade = None
        self.dca_filled = [False, False, False, False]
        self.order_to_dca_index = {}
        self.losing_streak = 0
        self.cooldown_until_bar = -1
        self.initial_deposit = float(self.broker.getvalue())
        self.pending_exit_reason = None
        self.pending_averaging_count = None

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

    def _take_profit_ratio(self):
        return max(0.0, float(self.p.take_profit_percent)) / 100.0

    def _stop_loss_ratio(self):
        return max(0.0, float(self.p.stop_loss_percent)) / 100.0

    def _dca_percentages(self):
        return [
            float(self.p.dca_1_percent),
            float(self.p.dca_2_percent),
            float(self.p.dca_3_percent),
            float(self.p.dca_4_percent),
        ]

    def _position_size_from_deposit_percent(self, percent_of_deposit, execution_price):
        if not self._is_finite(percent_of_deposit, execution_price):
            return 0.0
        if execution_price <= 0.0:
            return 0.0

        percent = max(0.0, float(percent_of_deposit))
        if percent <= 0.0:
            return 0.0

        target_order_budget = self.initial_deposit * (percent / 100.0)
        available_cash = max(0.0, float(self.broker.getcash()))
        capped_budget = min(target_order_budget, available_cash)
        denominator = float(execution_price) * (1.0 + float(self.p.commission))
        if denominator <= 0.0:
            return 0.0
        return max(0.0, capped_budget / denominator)

    def _dca_drawdown_ratios(self):
        return [
            0.0,
            self._bps_to_ratio(self.p.dca_2_drawdown_bps),
            self._bps_to_ratio(self.p.dca_3_drawdown_bps),
            self._bps_to_ratio(self.p.dca_4_drawdown_bps),
        ]

    def _get_current_averaging_count(self):
        filled_entries = sum(1 for is_filled in self.dca_filled if is_filled)
        return max(0, int(filled_entries) - 1)

    def _set_pending_close_metadata(self, exit_reason):
        normalized_reason = str(exit_reason or "").strip().lower()
        if normalized_reason not in {"take_profit", "stop_loss"}:
            normalized_reason = "other"
        self.pending_exit_reason = normalized_reason
        self.pending_averaging_count = self._get_current_averaging_count()

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

        self.pending_exit_reason = None
        self.pending_averaging_count = None
        self.tp_ratio_for_trade = self._take_profit_ratio()
        self.stop_loss_ratio_for_trade = self._stop_loss_ratio()

        first_size = self._position_size_from_deposit_percent(
            percent_of_deposit=self._dca_percentages()[0],
            execution_price=float(current_open),
        )
        if first_size <= 0.0:
            return
        self.order = self.buy(size=first_size)
        self.order_to_dca_index[self.order.ref] = 0

    def _try_dca_entry(self):
        if self.first_entry_price is None:
            return False

        close_price = self.data.close[0]
        if not self._is_finite(close_price):
            return False

        drawdowns = self._dca_drawdown_ratios()
        percentages = self._dca_percentages()

        for dca_index in (1, 2, 3):
            if self.dca_filled[dca_index]:
                continue

            trigger_price = self.first_entry_price * (1.0 - drawdowns[dca_index])
            if close_price <= trigger_price:
                dca_size = self._position_size_from_deposit_percent(
                    percent_of_deposit=percentages[dca_index],
                    execution_price=float(close_price),
                )
                if dca_size <= 0.0:
                    continue
                self.order = self.buy(size=dca_size)
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

    def _should_stop_loss(self):
        if self.stop_loss_ratio_for_trade is None:
            return False

        close_price = self.data.close[0]
        avg_entry_price = float(self.position.price)
        if not self._is_finite(close_price, avg_entry_price) or avg_entry_price <= 0.0:
            return False

        stop_loss_price = avg_entry_price * (1.0 - self.stop_loss_ratio_for_trade)
        return close_price <= stop_loss_price

    def _reset_trade_state(self):
        self.first_entry_price = None
        self.entry_bar_index = None
        self.tp_ratio_for_trade = None
        self.stop_loss_ratio_for_trade = None
        self.dca_filled = [False, False, False, False]
        self.order_to_dca_index = {}
        self.pending_exit_reason = None
        self.pending_averaging_count = None

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

        if self._should_stop_loss():
            self._set_pending_close_metadata("stop_loss")
            self.order = self.close()
            return

        if self._should_take_profit():
            self._set_pending_close_metadata("take_profit")
            self.order = self.close()
            return

        if self.entry_bar_index is None:
            return

        bars_held = len(self) - self.entry_bar_index + 1
        if bars_held >= int(self.p.max_bars_in_trade):
            self._set_pending_close_metadata("other")
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
            if order.issell():
                self.pending_exit_reason = None
                self.pending_averaging_count = None

        super().notify_order(order)

    def notify_trade(self, trade):
        super().notify_trade(trade)

        if not trade.isclosed:
            return

        if self.trades_log and isinstance(self.trades_log[-1], dict):
            trade_record = self.trades_log[-1]
            exit_reason = self.pending_exit_reason if isinstance(self.pending_exit_reason, str) else ""
            if exit_reason not in {"take_profit", "stop_loss", "other"}:
                exit_reason = "other"
            averaging_count = self.pending_averaging_count
            if averaging_count is None:
                averaging_count = self._get_current_averaging_count()
            trade_record["exit_reason"] = exit_reason
            trade_record["averaging_count"] = max(0, int(averaging_count))

        if float(trade.pnlcomm) < 0.0:
            self.losing_streak += 1
            if self.losing_streak >= int(self.p.losing_streak_limit):
                self.cooldown_until_bar = len(self) + int(self.p.cooldown_bars)
                self.losing_streak = 0
        else:
            self.losing_streak = 0

        self._reset_trade_state()
