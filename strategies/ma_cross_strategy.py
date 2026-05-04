import backtrader as bt

from strategies.base_strategy import BaseLoggingStrategy


class MovingAverageCrossStrategy(BaseLoggingStrategy):
    CHART_INDICATOR_CONFIG = {
        "fast_sma": {
            "label": "Fast SMA",
            "panel": "price",
            "color": "#38bdf8",
            "default_visible": True,
        },
        "slow_sma": {
            "label": "Slow SMA",
            "panel": "price",
            "color": "#f59e0b",
            "default_visible": True,
        },
        "crossover": {
            "label": "CrossOver",
            "panel": "oscillator",
            "color": "#a78bfa",
            "default_visible": True,
        },
    }
    OPTIMIZATION_PARAM_WHITELIST = (
        "fast_period",
        "slow_period",
    )

    PARAMETER_SPECS = {
        "fast_period": {
            "type": "int",
            "min": 1,
            "max": 200,
            "step": 1,
            "lt": "slow_period",
            "label_ru": "Период быстрой SMA",
            "optimization_group": "indicator",
        },
        "slow_period": {
            "type": "int",
            "min": 2,
            "max": 500,
            "step": 1,
            "label_ru": "Период медленной SMA",
            "optimization_group": "indicator",
        },
        "commission": {
            "type": "float",
            "min": 0.0,
            "max": 0.05,
            "step": 0.0001,
            "label_ru": "Комиссия",
        },
    }

    params = (
        ("fast_period", 10),
        ("slow_period", 20),
        ("commission", 0.001),
    )

    def __init__(self):
        super().__init__()
        self.fast_sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.fast_period)
        self.slow_sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.slow_period)
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)

    def next(self):
        self.record_equity()
        if self.order is not None:
            return
        if not self.position and self.crossover > 0:
            current_price = self.data.close[0]
            available_cash = self.broker.getcash()
            size = available_cash / (current_price * (1 + self.params.commission))
            if size > 0:
                self.order = self.buy(size=size)
        elif self.position and self.crossover < 0:
            self.order = self.close()
