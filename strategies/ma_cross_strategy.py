import backtrader as bt  # Импортируем Backtrader, чтобы описать торговую стратегию на его классах.

from strategies.base_strategy import BaseLoggingStrategy  # Импортируем базовую стратегию, чтобы переиспользовать общую логику логирования.


class MovingAverageCrossStrategy(BaseLoggingStrategy):  # Создаем простую стратегию на пересечении двух скользящих средних с общим базовым логированием.
    params = (  # Описываем параметры стратегии, чтобы их можно было легко менять при запуске.
        ("fast_period", 10),  # Задаем период быстрой скользящей средней: 10 свечей.
        ("slow_period", 20),  # Задаем период медленной скользящей средней: 20 свечей.
        ("commission", 0.001),  # Сохраняем комиссию биржи, чтобы корректно рассчитывать размер покупки.
    )  # Завершаем описание параметров стратегии.

    def __init__(self):  # Создаем метод инициализации, который Backtrader вызывает при старте стратегии.
        super().__init__()  # Инициализируем базовый класс, чтобы подготовить структуры для логирования и отслеживания ордеров.
        self.fast_sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.fast_period)  # Строим быструю простую скользящую среднюю по ценам закрытия.
        self.slow_sma = bt.indicators.SimpleMovingAverage(self.data.close, period=self.params.slow_period)  # Строим медленную простую скользящую среднюю по ценам закрытия.
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)  # Создаем индикатор пересечения, который покажет момент смены сигнала.

    def next(self):  # Создаем главный метод стратегии, который выполняется на каждой новой свече.
        self.record_equity()  # Сохраняем текущий капитал на каждой свече для будущего графика equity curve.
        if self.order is not None:  # Проверяем, есть ли уже активный приказ в обработке.
            return  # Если приказ еще не завершен, пропускаем текущую свечу.
        if not self.position and self.crossover > 0:  # Проверяем, что позиции сейчас нет и быстрая SMA пересекла медленную снизу вверх.
            current_price = self.data.close[0]  # Берем текущую цену закрытия, чтобы рассчитать размер покупки.
            available_cash = self.broker.getcash()  # Получаем доступный кэш на счете.
            size = available_cash / (current_price * (1 + self.params.commission))  # Рассчитываем размер покупки почти на весь капитал с учетом комиссии.
            if size > 0:  # Проверяем, что рассчитанный размер позиции получился положительным.
                self.order = self.buy(size=size)  # Отправляем приказ на покупку рассчитанного количества актива.
        elif self.position and self.crossover < 0:  # Проверяем, что позиция уже открыта и быстрая SMA пересекла медленную сверху вниз.
            self.order = self.close()  # Закрываем текущую позицию целиком.
