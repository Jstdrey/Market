import backtrader as bt  # Импортируем Backtrader, чтобы использовать его базовый класс стратегии и утилиты дат.


class BaseLoggingStrategy(bt.Strategy):  # Создаем базовый класс, который отвечает только за сбор логов сделок и кривой капитала.
    def __init__(self):  # Создаем инициализацию базовой стратегии, чтобы подготовить структуры для логирования.
        self.order = None  # Создаем переменную для хранения текущего биржевого приказа, чтобы дочерние стратегии не отправляли дубликаты.
        self.trades_log = []  # Создаем список, в который будем складывать информацию по закрытым сделкам.
        self.equity_curve = []  # Создаем список для сохранения истории изменения капитала по свечам.
        self.current_trade_entry = {}  # Создаем словарь для временного хранения данных по текущей открытой сделке.
        self.current_trade_exit_price = None  # Создаем переменную для хранения цены закрытия позиции перед записью сделки в лог.
        self.current_trade_exit_date = None  # Создаем переменную для хранения даты закрытия позиции перед записью сделки в лог.

    def record_equity(self):  # Создаем вспомогательный метод, который сохраняет текущий капитал на каждой свече.
        current_datetime = bt.num2date(self.data.datetime[0])  # Получаем дату и время текущей свечи из Backtrader.
        current_equity = self.broker.getvalue()  # Получаем текущую стоимость счета с учетом открытых позиций.
        self.equity_curve.append({"datetime": current_datetime, "equity": current_equity})  # Добавляем новую точку в историю капитала.

    def prenext(self):  # Создаем метод, который Backtrader вызывает на первых свечах до полного прогрева индикаторов.
        self.record_equity()  # Сохраняем капитал даже на ранних свечах, чтобы график капитала был непрерывным.

    def notify_order(self, order):  # Создаем метод, который Backtrader вызывает при изменении состояния приказа.
        if order.status in [order.Submitted, order.Accepted]:  # Проверяем, был ли приказ только отправлен или принят в обработку.
            return  # Ничего не делаем, пока приказ еще не исполнен.
        if order.status == order.Completed:  # Проверяем, был ли приказ исполнен полностью.
            executed_datetime = bt.num2date(order.executed.dt)  # Преобразуем время исполнения приказа в обычный формат даты и времени.
            if order.isbuy():  # Проверяем, что исполненный приказ является покупкой.
                self.current_trade_entry = {  # Сохраняем основные параметры открытой позиции во временный словарь.
                    "open_date": executed_datetime,  # Запоминаем дату открытия сделки.
                    "open_price": order.executed.price,  # Запоминаем фактическую цену открытия сделки.
                    "size": order.executed.size,  # Запоминаем размер купленной позиции.
                }  # Завершаем заполнение словаря по открытой сделке.
            elif order.issell():  # Проверяем, что исполненный приказ является продажей или закрытием позиции.
                self.current_trade_exit_price = order.executed.price  # Сохраняем фактическую цену закрытия позиции.
                self.current_trade_exit_date = executed_datetime  # Сохраняем дату и время закрытия позиции.
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:  # Проверяем, завершился ли жизненный цикл приказа.
            self.order = None  # Очищаем ссылку на приказ, чтобы стратегия могла отправлять следующий.

    def notify_trade(self, trade):  # Создаем метод, который Backtrader вызывает при изменении состояния сделки.
        if not trade.isclosed:  # Проверяем, закрылась ли сделка полностью.
            return  # Если сделка еще открыта, ничего не записываем в лог.
        open_date = self.current_trade_entry.get("open_date", bt.num2date(trade.dtopen))  # Берем дату открытия из сохраненного словаря или запасной вариант из объекта сделки.
        open_price = self.current_trade_entry.get("open_price", trade.price)  # Берем цену открытия из сохраненного словаря или из объекта сделки.
        size = self.current_trade_entry.get("size", trade.size)  # Берем размер позиции из сохраненного словаря или из объекта сделки.
        close_date = self.current_trade_exit_date or bt.num2date(trade.dtclose)  # Берем дату закрытия из исполненного ордера или запасной вариант из объекта сделки.
        close_price = self.current_trade_exit_price if self.current_trade_exit_price is not None else self.data.close[0]  # Берем цену закрытия из сохраненного ордера или текущей цены закрытия свечи.
        trade_record = {  # Создаем словарь с итоговой информацией по закрытой сделке.
            "open_date": open_date,  # Сохраняем дату открытия сделки.
            "close_date": close_date,  # Сохраняем дату закрытия сделки.
            "open_price": float(open_price),  # Сохраняем цену открытия как число с плавающей точкой.
            "close_price": float(close_price),  # Сохраняем цену закрытия как число с плавающей точкой.
            "size": float(abs(size)),  # Сохраняем абсолютный размер позиции, чтобы он был удобен для чтения.
            "pnl": float(trade.pnl),  # Сохраняем результат сделки без учета комиссии.
            "commission": float(trade.commission),  # Сохраняем общую комиссию по сделке.
            "pnl_after_commission": float(trade.pnlcomm),  # Сохраняем итоговый результат сделки уже с учетом комиссии.
        }  # Завершаем формирование словаря по закрытой сделке.
        self.trades_log.append(trade_record)  # Добавляем закрытую сделку в общий список лога.
        self.current_trade_entry = {}  # Очищаем временные данные по открытой сделке после записи в лог.
        self.current_trade_exit_price = None  # Очищаем сохраненную цену закрытия, чтобы она не попала в следующую сделку.
        self.current_trade_exit_date = None  # Очищаем сохраненную дату закрытия, чтобы она не попала в следующую сделку.
