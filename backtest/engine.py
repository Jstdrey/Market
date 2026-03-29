from pathlib import Path  # Импортируем Path, чтобы удобно работать с путями к файлам проекта.

import backtrader as bt  # Импортируем Backtrader, чтобы собрать и запустить движок бектеста.
import pandas as pd  # Импортируем Pandas, чтобы читать наш CSV-файл с историческими свечами.

from utils.strategy_loader import load_available_strategies  # Импортируем загрузчик стратегий, чтобы двигатель не зависел от одной жестко заданной стратегии.

PROJECT_DIR = Path(__file__).resolve().parent.parent  # Находим корневую папку проекта относительно текущего файла.
DATA_FILE = PROJECT_DIR / "data.csv"  # Указываем путь к CSV-файлу с историческими данными.
INITIAL_CASH = 10_000.0  # Задаем стартовый капитал для симуляции в USDT.
COMMISSION = 0.001  # Задаем комиссию биржи 0.1% в виде десятичной дроби.
DEFAULT_FAST_PERIOD = 10  # Задаем период быстрой SMA по умолчанию.
DEFAULT_SLOW_PERIOD = 20  # Задаем период медленной SMA по умолчанию.
DEFAULT_STRATEGY_NAME = "MovingAverageCrossStrategy"  # Сохраняем имя стратегии по умолчанию для консольного запуска.


def load_market_data(data_file):  # Создаем функцию, которая загружает CSV-файл и подготавливает данные для Backtrader.
    if not data_file.exists():  # Проверяем, существует ли файл data.csv.
        raise FileNotFoundError("Файл data.csv не найден. Сначала загрузите исторические данные через приложение или downloader.py.")  # Сообщаем понятную ошибку, если файла еще нет.
    dataframe = pd.read_csv(data_file)  # Читаем CSV-файл в таблицу Pandas.
    required_columns = ["datetime", "open", "high", "low", "close", "volume"]  # Собираем список обязательных колонок, без которых бектест не запустится.
    missing_columns = [column for column in required_columns if column not in dataframe.columns]  # Проверяем, каких колонок не хватает в файле.
    if missing_columns:  # Проверяем, найден ли хотя бы один пропущенный столбец.
        raise ValueError(f"В data.csv не хватает колонок: {', '.join(missing_columns)}")  # Показываем понятную ошибку со списком отсутствующих колонок.
    dataframe["datetime"] = pd.to_datetime(dataframe["datetime"], utc=True)  # Преобразуем текстовую дату в настоящий формат даты и времени.
    dataframe["datetime"] = dataframe["datetime"].dt.tz_convert(None)  # Убираем временную зону, потому что Backtrader удобнее работает с обычным временем.
    dataframe = dataframe.sort_values("datetime").reset_index(drop=True)  # Сортируем строки по времени и обновляем индексы.
    dataframe = dataframe[["datetime", "open", "high", "low", "close", "volume"]].copy()  # Оставляем только те колонки, которые нужны для бектеста.
    dataframe[["open", "high", "low", "close", "volume"]] = dataframe[["open", "high", "low", "close", "volume"]].astype(float)  # Приводим рыночные значения к числовому типу float.
    dataframe = dataframe.set_index("datetime")  # Делаем колонку datetime индексом, как ожидает PandasData в Backtrader.
    return dataframe  # Возвращаем готовую таблицу наружу.


def create_cerebro_with_data(market_data, initial_cash, commission):  # Создаем вспомогательную функцию, которая собирает базовый объект Cerebro с данными и брокером.
    cerebro = bt.Cerebro()  # Создаем объект Cerebro, который управляет всем бектестом.
    data_feed = bt.feeds.PandasData(dataname=market_data.copy())  # Преобразуем Pandas-таблицу в формат данных, понятный Backtrader.
    cerebro.adddata(data_feed)  # Подключаем источник исторических данных к движку.
    cerebro.broker.setcash(initial_cash)  # Устанавливаем стартовый капитал для симуляции.
    cerebro.broker.setcommission(commission=commission)  # Устанавливаем комиссию биржи 0.1%.
    return cerebro  # Возвращаем готовый объект Cerebro наружу.


def prepare_strategy_kwargs(strategy_kwargs, commission):  # Создаем вспомогательную функцию, которая приводит параметры стратегии к единому виду.
    prepared_kwargs = dict(strategy_kwargs or {})  # Создаем копию словаря параметров стратегии или пустой словарь, если параметры не переданы.
    prepared_kwargs.setdefault("commission", commission)  # Добавляем комиссию в параметры стратегии, если она еще не была передана явно.
    return prepared_kwargs  # Возвращаем подготовленный словарь параметров стратегии наружу.


def run_backtest(strategy_class, data_file=DATA_FILE, initial_cash=INITIAL_CASH, commission=COMMISSION, strategy_kwargs=None):  # Создаем основную функцию, которая запускает симуляцию торгов для переданного класса стратегии.
    strategy_kwargs = prepare_strategy_kwargs(strategy_kwargs=strategy_kwargs, commission=commission)  # Подготавливаем словарь параметров стратегии и гарантируем наличие комиссии.
    market_data = load_market_data(data_file=data_file)  # Загружаем и подготавливаем рыночные данные из CSV-файла.
    cerebro = create_cerebro_with_data(market_data=market_data, initial_cash=initial_cash, commission=commission)  # Создаем готовый объект Cerebro с данными и настройками брокера.
    cerebro.addstrategy(strategy_class, **strategy_kwargs)  # Подключаем выбранную пользователем стратегию с переданными параметрами.
    starting_balance = cerebro.broker.getvalue()  # Сохраняем начальный баланс до запуска стратегии.
    strategies = cerebro.run()  # Запускаем симуляцию торгов по всей исторической выборке и получаем список стратегий после выполнения.
    strategy = strategies[0]  # Берем первую и единственную стратегию из результата работы Cerebro.
    final_balance = cerebro.broker.getvalue()  # Сохраняем итоговый баланс после завершения симуляции.
    trades_log = strategy.trades_log  # Берем список всех закрытых сделок, который стратегия накопила во время бектеста.
    equity_curve = strategy.equity_curve  # Берем историю изменения капитала, которую стратегия сохраняла на каждой свече.
    return starting_balance, final_balance, trades_log, equity_curve  # Возвращаем начальный баланс, итоговый баланс, сделки и equity curve наружу.


def run_optimization(strategy_class, data_file=DATA_FILE, strategy_param_ranges=None, initial_cash=INITIAL_CASH, commission=COMMISSION, strategy_kwargs=None):  # Создаем функцию, которая перебирает диапазоны параметров и возвращает результаты всех комбинаций для выбранной стратегии.
    base_strategy_kwargs = prepare_strategy_kwargs(strategy_kwargs=strategy_kwargs, commission=commission)  # Подготавливаем базовые параметры стратегии, которые одинаковы для всех прогонов оптимизации.
    strategy_param_ranges = dict(strategy_param_ranges or {})  # Создаем копию словаря диапазонов параметров или пустой словарь, если диапазоны не переданы.
    market_data = load_market_data(data_file=data_file)  # Загружаем и подготавливаем рыночные данные из CSV-файла один раз для всей оптимизации.
    cerebro = create_cerebro_with_data(market_data=market_data, initial_cash=initial_cash, commission=commission)  # Создаем базовый объект Cerebro для запуска оптимизации.
    cerebro.optstrategy(strategy_class, **base_strategy_kwargs, **strategy_param_ranges)  # Подключаем оптимизацию выбранной стратегии по всем переданным диапазонам параметров.
    optimization_runs = cerebro.run(maxcpus=1, optreturn=False)  # Запускаем оптимизацию в одном процессе и просим вернуть полноценные объекты стратегий.
    optimization_results = []  # Создаем пустой список, куда будем складывать результаты всех комбинаций параметров.
    for run in optimization_runs:  # Проходим по каждому завершенному прогону оптимизации.
        strategy = run[0]  # Берем единственную стратегию из текущего результата прогона.
        result_record = {}  # Создаем пустой словарь для сохранения параметров и результата текущей комбинации.
        for parameter_name in strategy_param_ranges.keys():  # Проходим по всем параметрам, которые участвовали в оптимизации.
            result_record[parameter_name] = int(getattr(strategy.params, parameter_name))  # Сохраняем фактическое значение каждого параметра для текущего прогона.
        if "fast_period" in result_record and "slow_period" in result_record and result_record["fast_period"] >= result_record["slow_period"]:  # Проверяем, не является ли сочетание SMA-периодов некорректным.
            continue  # Пропускаем такие сочетания, потому что они не имеют смысла для нашей стратегии.
        final_balance = float(strategy.broker.getvalue())  # Берем итоговый баланс по текущему прогону оптимизации.
        pnl = final_balance - float(initial_cash)  # Считаем прибыль или убыток текущей комбинации параметров.
        result_record["final_balance"] = final_balance  # Сохраняем итоговый баланс по комбинации.
        result_record["pnl"] = pnl  # Сохраняем итоговый финансовый результат комбинации.
        optimization_results.append(result_record)  # Добавляем словарь текущего результата в общий список результатов оптимизации.
    return optimization_results  # Возвращаем полный список результатов оптимизации наружу.


def format_balance(value):  # Создаем маленькую функцию, которая красиво форматирует денежное значение для печати.
    return f"{value:,.2f} USDT"  # Возвращаем сумму с двумя знаками после запятой и подписью валюты.


def get_default_strategy_class():  # Создаем вспомогательную функцию, которая находит стратегию по умолчанию для консольного запуска.
    available_strategies = load_available_strategies()  # Загружаем словарь всех доступных стратегий из папки strategies.
    if DEFAULT_STRATEGY_NAME in available_strategies:  # Проверяем, доступна ли стратегия по умолчанию в загруженном словаре.
        return available_strategies[DEFAULT_STRATEGY_NAME]  # Возвращаем класс стратегии по умолчанию, если он найден.
    if not available_strategies:  # Проверяем, найден ли вообще хотя бы один класс стратегии.
        raise ValueError("В папке strategies не найдено ни одной доступной стратегии Backtrader.")  # Сообщаем понятную ошибку, если стратегия не найдена.
    return next(iter(available_strategies.values()))  # Возвращаем первую доступную стратегию как запасной вариант.


def main():  # Создаем функцию, чтобы можно было запускать этот файл напрямую из терминала.
    strategy_class = get_default_strategy_class()  # Находим стратегию по умолчанию для консольного запуска движка.
    starting_balance, final_balance, trades_log, equity_curve = run_backtest(strategy_class=strategy_class, strategy_kwargs={"fast_period": DEFAULT_FAST_PERIOD, "slow_period": DEFAULT_SLOW_PERIOD})  # Запускаем бектест с настройками по умолчанию и получаем полную статистику.
    profit = final_balance - starting_balance  # Считаем абсолютный финансовый результат стратегии.
    print(f"Бектест стратегии {strategy_class.__name__} завершен.")  # Показываем понятное сообщение о завершении расчета.
    print(f"Начальный баланс: {format_balance(starting_balance)}")  # Печатаем стартовый капитал.
    print(f"Итоговый баланс: {format_balance(final_balance)}")  # Печатаем баланс после симуляции.
    print(f"Финансовый результат: {format_balance(profit)}")  # Печатаем прибыль или убыток в деньгах.
    print(f"Количество закрытых сделок: {len(trades_log)}")  # Печатаем количество сделок, которые стратегия успела закрыть.
    print(f"Точек в equity curve: {len(equity_curve)}")  # Печатаем количество сохраненных точек истории капитала.


if __name__ == "__main__":  # Проверяем, что файл engine.py запущен напрямую, а не импортирован как модуль.
    main()  # Запускаем отдельный консольный запуск движка бектеста.
