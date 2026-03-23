from datetime import date, datetime, time, timedelta, timezone  # Импортируем инструменты для работы с датами и временем в UTC.
from pathlib import Path  # Импортируем Path для удобной работы с путями к файлам.
import sys  # Импортируем sys, чтобы завершать программу с кодом ошибки.

import ccxt  # Импортируем библиотеку CCXT для подключения к Binance.
import pandas as pd  # Импортируем Pandas для работы с таблицей и сохранения CSV-файла.

LIMIT = 1000  # Указываем максимум свечей за один запрос к Binance.
PROJECT_DIR = Path(__file__).resolve().parent.parent  # Находим корневую папку проекта относительно текущего файла.
OUTPUT_FILE = PROJECT_DIR / "data.csv"  # Указываем путь, куда будет сохранен итоговый файл data.csv.


def create_exchange(symbol):  # Создаем функцию, которая подготавливает подключение к Binance.
    exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}})  # Создаем объект Binance, включаем безопасный режим по лимиту запросов и явно выбираем спотовый рынок.
    exchange.load_markets()  # Загружаем список рынков, чтобы CCXT знал доступные торговые пары.
    if not exchange.has.get("fetchOHLCV"):  # Проверяем, умеет ли биржа отдавать свечи через единый метод CCXT.
        raise RuntimeError("Биржа Binance не поддерживает fetch_ohlcv в текущей конфигурации.")  # Выдаем понятную ошибку, если метод недоступен.
    if symbol not in exchange.symbols:  # Проверяем, существует ли нужная торговая пара на бирже.
        raise ValueError(f"Торговая пара {symbol} не найдена на Binance.")  # Выдаем понятную ошибку, если пара не найдена.
    return exchange  # Возвращаем готовое подключение к бирже.


def align_datetime_to_timeframe(target_datetime_utc, timeframe):  # Создаем функцию, которая округляет datetime вниз до начала закрытой свечи выбранного таймфрейма.
    timeframe_seconds = ccxt.Exchange.parse_timeframe(timeframe)  # Получаем длительность одной свечи в секундах для выбранного таймфрейма.
    target_timestamp = int(target_datetime_utc.timestamp())  # Переводим datetime в секунды для удобного округления.
    aligned_timestamp = target_timestamp - (target_timestamp % timeframe_seconds)  # Округляем время вниз до ближайшей границы свечи.
    return datetime.fromtimestamp(aligned_timestamp, tz=timezone.utc)  # Возвращаем округленное время обратно в формате datetime.


def get_period_boundaries(start_date, end_date, timeframe):  # Создаем функцию, которая рассчитывает начало и конец нужного периода по конкретным датам.
    if start_date is None or end_date is None:  # Проверяем, были ли переданы обе даты диапазона.
        raise ValueError("Нужно передать и start_date, и end_date для загрузки истории.")  # Сообщаем понятную ошибку, если одной из дат нет.
    if start_date > end_date:  # Проверяем, что дата начала не позже даты окончания периода.
        raise ValueError("Дата начала периода не может быть позже даты окончания.")  # Сообщаем понятную ошибку для некорректного диапазона.
    start_time_utc = datetime.combine(start_date, time.min, tzinfo=timezone.utc)  # Преобразуем дату начала в начало суток UTC.
    raw_end_time_utc = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)  # Берем начало следующих суток UTC, чтобы включить весь выбранный день.
    end_time_utc = align_datetime_to_timeframe(raw_end_time_utc, timeframe)  # Округляем правую границу до начала последней полной свечи.
    if end_time_utc <= start_time_utc:  # Проверяем, остался ли после округления хотя бы один интервал для загрузки.
        raise ValueError("Для выбранного диапазона и таймфрейма не найдено ни одной полной свечи. Попробуйте расширить период.")  # Сообщаем понятную ошибку, если период слишком короткий.
    start_ms = int(start_time_utc.timestamp() * 1000)  # Переводим начало периода в миллисекунды.
    end_ms = int(end_time_utc.timestamp() * 1000)  # Переводим конец периода в миллисекунды.
    return start_time_utc, end_time_utc, start_ms, end_ms  # Возвращаем рассчитанные значения наружу.


def get_timeframe_step_ms(timeframe):  # Создаем функцию, которая считает шаг одной свечи в миллисекундах.
    timeframe_seconds = ccxt.Exchange.parse_timeframe(timeframe)  # Получаем длительность выбранного таймфрейма в секундах.
    timeframe_step_ms = timeframe_seconds * 1000  # Переводим секунды в миллисекунды.
    return timeframe_step_ms  # Возвращаем готовый шаг свечи в миллисекундах.


def download_ohlcv(exchange, symbol, timeframe, start_ms, end_ms):  # Создаем функцию для поэтапной загрузки всех свечей за нужный период.
    all_candles = []  # Создаем пустой список, куда будем складывать все полученные свечи.
    current_since = start_ms  # Запоминаем стартовую точку времени для первого запроса.
    timeframe_step_ms = get_timeframe_step_ms(timeframe)  # Рассчитываем шаг времени для выбранного таймфрейма, чтобы правильно двигаться между запросами.

    while current_since < end_ms:  # Повторяем запросы, пока не дойдем до конца нужного периода.
        candles = exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, since=current_since, limit=LIMIT)  # Загружаем очередную порцию свечей из Binance.
        if not candles:  # Проверяем, вернула ли биржа пустой список.
            break  # Останавливаем цикл, если данных больше нет.
        all_candles.extend(candles)  # Добавляем новую порцию свечей в общий список.
        last_candle_open_ms = candles[-1][0]  # Берем время открытия последней свечи из текущей порции.
        last_candle_open_text = datetime.fromtimestamp(last_candle_open_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")  # Переводим время последней свечи в читаемый вид UTC.
        print(f"Скачано свечей: {len(all_candles)} | Последняя свеча открылась: {last_candle_open_text} UTC")  # Показываем прогресс загрузки в терминале.
        next_since = last_candle_open_ms + timeframe_step_ms  # Сдвигаем начало следующего запроса на одну свечу вперед, чтобы не было дубликата.
        if next_since <= current_since:  # Проверяем защитное условие на случай, если время почему-то не продвинулось вперед.
            break  # Останавливаем цикл, чтобы не попасть в бесконечную загрузку.
        current_since = next_since  # Обновляем стартовую точку для следующего запроса.
        if len(candles) < LIMIT:  # Проверяем, была ли последняя порция меньше максимально возможного размера.
            break  # Обычно это означает, что доступные данные закончились.

    return all_candles  # Возвращаем полный список всех скачанных свечей.


def build_dataframe(candles, start_ms, end_ms):  # Создаем функцию, которая превращает список свечей в таблицу Pandas.
    if not candles:  # Проверяем, удалось ли вообще что-то скачать.
        raise ValueError("Binance не вернула ни одной свечи. Проверьте интернет, доступность API Binance и выбранный диапазон дат.")  # Сообщаем понятную ошибку, если данные не пришли.

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])  # Создаем таблицу со стандартными колонками OHLCV.
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)  # Удаляем возможные дубликаты, сортируем строки по времени и обновляем нумерацию.
    df = df[(df["timestamp"] >= start_ms) & (df["timestamp"] < end_ms)].copy()  # Оставляем только свечи внутри нужного периода и исключаем правую границу интервала.
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")  # Создаем понятную колонку с датой и временем в UTC.
    df = df[["timestamp", "datetime", "open", "high", "low", "close", "volume"]]  # Переставляем колонки в удобный порядок.
    numeric_columns = ["open", "high", "low", "close", "volume"]  # Собираем список колонок, которые должны быть числами.

    for column in numeric_columns:  # Запускаем цикл по всем числовым колонкам.
        df[column] = df[column].astype(float)  # Приводим значения к числовому типу float.

    return df  # Возвращаем готовую таблицу.


def save_csv(df, output_file):  # Создаем функцию для сохранения таблицы в CSV-файл.
    df.to_csv(output_file, index=False)  # Сохраняем таблицу без лишней колонки с индексом.
    print(f"Файл сохранен: {output_file}")  # Показываем полный путь к сохраненному файлу.


def run_downloader(symbol, timeframe, start_date, end_date, output_file=OUTPUT_FILE):  # Создаем функцию, которую можно вызывать из интерфейса с выбранными пользователем параметрами.
    exchange = create_exchange(symbol=symbol)  # Подключаемся к Binance и проверяем, что нужный рынок доступен.
    start_time_utc, end_time_utc, start_ms, end_ms = get_period_boundaries(start_date=start_date, end_date=end_date, timeframe=timeframe)  # Рассчитываем начало и конец периода с учетом таймфрейма.
    print(f"Начинаю загрузку {symbol} на таймфрейме {timeframe}.")  # Сообщаем в терминал, какую пару и какой таймфрейм загружаем.
    print(f"Период загрузки: с {start_time_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC по {end_time_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC.")  # Показываем точные границы периода.
    candles = download_ohlcv(exchange=exchange, symbol=symbol, timeframe=timeframe, start_ms=start_ms, end_ms=end_ms)  # Скачиваем исторические свечи по частям.
    df = build_dataframe(candles=candles, start_ms=start_ms, end_ms=end_ms)  # Превращаем список свечей в таблицу Pandas.
    save_csv(df=df, output_file=output_file)  # Сохраняем итоговую таблицу в файл data.csv.
    print(f"Итоговое количество строк: {len(df)}")  # Показываем, сколько строк попало в итоговый CSV-файл.
    print("Готово. Файл data.csv создан в корне проекта.")  # Сообщаем, что работа завершена успешно.
    return df  # Возвращаем готовую таблицу, чтобы интерфейс мог использовать ее сразу.


def main(symbol="BTC/USDT", timeframe="1h", start_date=None, end_date=None, output_file=OUTPUT_FILE):  # Создаем главную функцию, которая запускает весь процесс по шагам и умеет принимать параметры.
    try:  # Начинаем блок, который позволит показать понятные ошибки вместо аварийного падения.
        if start_date is None or end_date is None:  # Проверяем, переданы ли даты явно при прямом запуске файла.
            today = datetime.now(timezone.utc).date()  # Берем сегодняшнюю дату в UTC для значений по умолчанию.
            end_date = today if end_date is None else end_date  # Подставляем сегодняшнюю дату, если правая граница не передана.
            start_date = (end_date - timedelta(days=365)) if start_date is None else start_date  # Подставляем дату год назад, если левая граница не передана.
        run_downloader(symbol=symbol, timeframe=timeframe, start_date=start_date, end_date=end_date, output_file=output_file)  # Запускаем загрузку с переданными параметрами.
    except ccxt.NetworkError as error:  # Отдельно ловим сетевые ошибки, например отсутствие интернета или недоступность API.
        print(f"Ошибка сети: {error}")  # Показываем понятное сообщение о сетевой ошибке.
        sys.exit(1)  # Завершаем программу с кодом ошибки.
    except ccxt.ExchangeError as error:  # Отдельно ловим ошибки, которые вернула сама биржа Binance.
        print(f"Ошибка биржи: {error}")  # Показываем понятное сообщение об ошибке биржи.
        sys.exit(1)  # Завершаем программу с кодом ошибки.
    except Exception as error:  # Ловим все остальные неожиданные ошибки.
        print(f"Неожиданная ошибка: {error}")  # Показываем текст неожиданной ошибки.
        sys.exit(1)  # Завершаем программу с кодом ошибки.


if __name__ == "__main__":  # Проверяем, что файл запущен напрямую, а не импортирован из другого файла.
    main()  # Запускаем главную функцию.
