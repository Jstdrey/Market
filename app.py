from datetime import date, timedelta  # Импортируем date и timedelta, чтобы задавать диапазон дат в интерфейсе.
from pathlib import Path  # Импортируем Path, чтобы удобно работать с путями к файлам проекта.

import pandas as pd  # Импортируем Pandas, чтобы читать CSV-файл и работать с таблицами.
import plotly.graph_objects as go  # Импортируем Plotly, чтобы строить красивые графики.
import plotly.io as pio  # Импортируем модуль настройки Plotly, чтобы включить темную тему графиков.
import streamlit as st  # Импортируем Streamlit, чтобы создать веб-интерфейс.

from backtest.engine import format_balance  # Импортируем функцию форматирования суммы для красивого вывода результатов.
from backtest.engine import run_backtest  # Импортируем функцию запуска бектеста.
from backtest.engine import run_optimization  # Импортируем функцию оптимизации параметров стратегии.
from data.downloader import OUTPUT_FILE  # Импортируем путь к файлу data.csv из загрузчика.
from data.downloader import run_downloader  # Импортируем функцию загрузки, которая умеет принимать параметры интерфейса.
from utils.strategy_loader import load_available_strategies  # Импортируем загрузчик стратегий, чтобы автоматически находить все стратегии из папки strategies.

pio.templates.default = "plotly_dark"  # Принудительно включаем темную тему для всех графиков Plotly.

APP_TITLE = "Crypto Backtester Pro"  # Задаем новый заголовок приложения в более профессиональном стиле.
APP_DESCRIPTION = "Профессиональный терминал для загрузки исторических свечей Binance, просмотра данных и запуска бектеста."  # Задаем описание приложения для верхнего блока.
DATA_FILE = Path(OUTPUT_FILE)  # Преобразуем путь к CSV-файлу в объект Path для проверки существования файла.
AVAILABLE_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]  # Создаем список доступных торговых пар для выпадающего списка.
AVAILABLE_TIMEFRAMES = ["1h", "4h", "1d"]  # Создаем список доступных таймфреймов для выпадающего списка.
BINANCE_START_DATE = date(2017, 1, 1)  # Сохраняем разумную минимальную дату выбора периода, близкую к старту Binance.
BACKTEST_RESULTS_KEY = "backtest_results"  # Создаем ключ для хранения результатов бектеста в session_state.
OPTIMIZATION_RESULTS_KEY = "optimization_results"  # Создаем ключ для хранения результатов оптимизации в session_state.
POSITIVE_ROW_COLOR = "rgba(38, 166, 154, 0.2)"  # Сохраняем цвет подсветки прибыльных сделок.
NEGATIVE_ROW_COLOR = "rgba(239, 83, 80, 0.2)"  # Сохраняем цвет подсветки убыточных сделок.


def configure_page():  # Создаем функцию для базовой настройки страницы Streamlit.
    st.set_page_config(page_title=APP_TITLE, layout="wide")  # Устанавливаем заголовок вкладки и широкий режим страницы.
    st.markdown(  # Добавляем кастомный CSS, чтобы карточки метрик выглядели современно на темной теме.
        """
        <style>
        div[data-testid="metric-container"] {
            background-color: #1E212B;
            border: 1px solid #2E9AFE;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )  # Завершаем вставку кастомного CSS в страницу.
    st.title("📈 Crypto Backtester Pro")  # Показываем новый заголовок страницы с иконкой.
    st.write("Здесь можно загружать исторические данные, смотреть график, запускать бектест, анализировать сделки и искать лучшие параметры стратегии прямо из интерфейса.")  # Простыми словами объясняем, что делает приложение.
    st.caption(APP_DESCRIPTION)  # Показываем дополнительное описание под заголовком.


def get_available_strategies():  # Создаем функцию, которая загружает словарь всех доступных стратегий для интерфейса.
    strategies = load_available_strategies()  # Загружаем все найденные стратегии из папки strategies.
    if not strategies:  # Проверяем, найден ли хотя бы один класс стратегии.
        raise ValueError("В папке strategies не найдено ни одной доступной стратегии Backtrader.")  # Сообщаем понятную ошибку, если стратегий нет.
    return strategies  # Возвращаем словарь найденных стратегий наружу.


def render_sidebar():  # Создаем функцию, которая рисует боковую панель с настройками пользователя.
    st.sidebar.header("⚙️ Параметры загрузки")  # Добавляем заголовок в боковую панель.
    selected_symbol = st.sidebar.selectbox("Торговая пара", AVAILABLE_SYMBOLS, index=0)  # Создаем выпадающий список с доступными торговыми парами.
    selected_timeframe = st.sidebar.selectbox("Таймфрейм", AVAILABLE_TIMEFRAMES, index=0)  # Создаем выпадающий список с доступными таймфреймами.
    default_end_date = date.today()  # Берем сегодняшнюю дату как правую границу диапазона по умолчанию.
    default_start_date = default_end_date - timedelta(days=365)  # Отматываем дату на год назад, чтобы задать стартовую левую границу диапазона.
    selected_date_range = st.sidebar.date_input(  # Рисуем виджет выбора диапазона дат в боковой панели.
        "Диапазон дат",  # Задаем подпись для выбора периода загрузки.
        value=[default_start_date, default_end_date],  # По умолчанию предлагаем период от года назад до сегодняшнего дня.
        min_value=BINANCE_START_DATE,  # Запрещаем выбирать даты раньше разумного старта истории Binance.
        max_value=default_end_date,  # Не даем выбирать даты позже сегодняшней.
    )  # Завершаем описание виджета выбора диапазона дат.
    if isinstance(selected_date_range, tuple):  # Проверяем, вернул ли Streamlit кортеж дат.
        selected_date_range = list(selected_date_range)  # Преобразуем кортеж в список для единообразной обработки.
    if len(selected_date_range) != 2:  # Проверяем, выбрал ли пользователь обе границы диапазона.
        st.sidebar.warning("Пожалуйста, выберите обе даты периода загрузки.")  # Показываем понятное предупреждение, если диапазон выбран не полностью.
        selected_start_date = default_start_date  # Используем дату по умолчанию, пока диапазон не выбран полностью.
        selected_end_date = default_end_date  # Используем сегодняшнюю дату как правую границу по умолчанию.
    else:  # Переходим в этот блок, если пользователь выбрал обе даты диапазона.
        selected_start_date, selected_end_date = selected_date_range  # Распаковываем выбранные даты начала и конца периода.
    st.sidebar.caption("Если в data.csv сохранены старые данные, нажмите кнопку загрузки еще раз, чтобы пересобрать файл под новую пару, таймфрейм или даты.")  # Поясняем, как обновить файл при смене выбора в боковой панели.
    return selected_symbol, selected_timeframe, selected_start_date, selected_end_date  # Возвращаем выбранные значения наружу.


def load_data_from_csv(file_path):  # Создаем функцию, которая читает data.csv и возвращает таблицу.
    if not file_path.exists():  # Проверяем, существует ли CSV-файл в корне проекта.
        raise FileNotFoundError("Файл data.csv пока не найден. Сначала нажмите кнопку загрузки данных.")  # Сообщаем понятную ошибку, если файла еще нет.
    dataframe = pd.read_csv(file_path)  # Читаем CSV-файл в таблицу Pandas.
    dataframe["datetime"] = pd.to_datetime(dataframe["datetime"], utc=True)  # Превращаем текстовую дату в настоящий формат даты и времени.
    return dataframe  # Возвращаем готовую таблицу наружу.


def extract_dataset_metadata(dataframe):  # Создаем функцию, которая извлекает метаданные набора из data.csv.
    dataset_symbol = dataframe["symbol"].iloc[0] if "symbol" in dataframe.columns and not dataframe.empty else None  # Берем торговую пару из файла, если колонка присутствует.
    dataset_timeframe = dataframe["timeframe"].iloc[0] if "timeframe" in dataframe.columns and not dataframe.empty else None  # Берем таймфрейм из файла, если колонка присутствует.
    return dataset_symbol, dataset_timeframe  # Возвращаем найденные метаданные наружу.


def show_dataset_mismatch_warning(dataframe, selected_symbol, selected_timeframe):  # Создаем функцию, которая предупреждает о несоответствии выбранных параметров и текущего data.csv.
    dataset_symbol, dataset_timeframe = extract_dataset_metadata(dataframe=dataframe)  # Извлекаем торговую пару и таймфрейм из текущего файла данных.
    if dataset_symbol is None or dataset_timeframe is None:  # Проверяем, есть ли в файле метаданные новой версии загрузчика.
        st.warning("Файл data.csv не содержит метаданных symbol/timeframe. Нажмите 'Загрузить данные с Binance', чтобы пересоздать файл и исключить путаницу данных.")  # Показываем предупреждение для старого формата файла.
        return  # Завершаем функцию, потому что сравнивать параметры пока не с чем.
    if dataset_symbol != selected_symbol or dataset_timeframe != selected_timeframe:  # Проверяем, совпадают ли выбранные параметры интерфейса с данными внутри файла.
        st.warning(f"Внимание: в data.csv сейчас записаны {dataset_symbol} / {dataset_timeframe}, а в боковой панели выбраны {selected_symbol} / {selected_timeframe}. Нажмите кнопку загрузки, чтобы обновить набор данных перед бектестом.")  # Показываем понятное предупреждение о возможной причине некорректных сделок.


def create_candlestick_chart(dataframe, selected_symbol, selected_timeframe):  # Создаем функцию, которая строит свечной график из таблицы.
    figure = go.Figure()  # Создаем пустую фигуру Plotly.
    figure.add_trace(  # Добавляем на график один слой со свечами.
        go.Candlestick(  # Используем специальный тип графика для финансовых свечей.
            x=dataframe["datetime"],  # Передаем даты по горизонтальной оси.
            open=dataframe["open"],  # Передаем цены открытия свечей.
            high=dataframe["high"],  # Передаем максимумы свечей.
            low=dataframe["low"],  # Передаем минимумы свечей.
            close=dataframe["close"],  # Передаем цены закрытия свечей.
            name=selected_symbol,  # Указываем подпись серии данных по выбранной пользователем паре.
            increasing_line_color="#26A69A",  # Делаем растущие свечи красивого зеленого цвета.
            decreasing_line_color="#EF5350",  # Делаем падающие свечи красивого красного цвета.
        )  # Завершаем описание свечного слоя.
    )  # Завершаем добавление слоя на график.
    figure.update_layout(  # Настраиваем внешний вид графика.
        title=f"Свечной график {selected_symbol} | Таймфрейм {selected_timeframe}",  # Показываем понятный заголовок графика с выбранными параметрами.
        xaxis_title="Дата и время UTC",  # Подписываем горизонтальную ось.
        yaxis_title="Цена",  # Подписываем вертикальную ось.
        xaxis_rangeslider_visible=False,  # Отключаем нижний ползунок, чтобы график выглядел проще.
        height=650,  # Делаем график выше, чтобы свечи было удобнее смотреть.
        paper_bgcolor="rgba(0,0,0,0)",  # Делаем фон всей фигуры прозрачным, чтобы он красиво ложился на темную тему.
        plot_bgcolor="rgba(0,0,0,0)",  # Делаем фон самой области построения прозрачным.
    )  # Завершаем настройку внешнего вида.
    return figure  # Возвращаем готовый график.


def create_equity_curve_chart(equity_dataframe):  # Создаем функцию, которая строит линейный график изменения капитала.
    figure = go.Figure()  # Создаем пустую фигуру Plotly.
    figure.add_trace(  # Добавляем на график одну линию капитала.
        go.Scatter(  # Используем линейный график для отображения equity curve.
            x=equity_dataframe["datetime"],  # Передаем даты по горизонтальной оси.
            y=equity_dataframe["equity"],  # Передаем значения капитала по вертикальной оси.
            mode="lines",  # Просим Plotly рисовать именно линию.
            name="Капитал",  # Задаем подпись линии графика.
            line={"color": "#2E9AFE", "width": 3},  # Делаем линию капитала ярко-синей и чуть толще стандартной.
            fill="tozeroy",  # Добавляем заливку под линией графика.
            fillcolor="rgba(46, 154, 254, 0.1)",  # Делаем мягкую полупрозрачную синюю заливку под линией.
        )  # Завершаем описание линейного графика.
    )  # Завершаем добавление линии в фигуру.
    figure.update_layout(  # Настраиваем внешний вид графика капитала.
        title="📊 График капитала (Equity Curve)",  # Показываем понятный заголовок графика с иконкой.
        xaxis_title="Дата и время",  # Подписываем горизонтальную ось.
        yaxis_title="Капитал, USDT",  # Подписываем вертикальную ось.
        height=450,  # Делаем график достаточно высоким для удобного просмотра.
        paper_bgcolor="rgba(0,0,0,0)",  # Делаем фон всей фигуры прозрачным.
        plot_bgcolor="rgba(0,0,0,0)",  # Делаем фон области построения прозрачным.
    )  # Завершаем настройку внешнего вида графика.
    return figure  # Возвращаем готовый график наружу.


def show_data_summary(dataframe):  # Создаем функцию, которая показывает краткую сводку по данным.
    first_date = dataframe["datetime"].min()  # Находим самую раннюю дату в таблице.
    last_date = dataframe["datetime"].max()  # Находим самую позднюю дату в таблице.
    dataset_symbol, dataset_timeframe = extract_dataset_metadata(dataframe=dataframe)  # Извлекаем торговую пару и таймфрейм, записанные в файле данных.
    col_1, col_2, col_3 = st.columns(3)  # Создаем три колонки для компактного вывода основных показателей.
    col_1.metric("Количество строк", f"{len(dataframe)}")  # Показываем общее количество строк в файле.
    col_2.metric("Первая свеча", first_date.strftime("%Y-%m-%d %H:%M"))  # Показываем дату первой свечи.
    col_3.metric("Последняя свеча", last_date.strftime("%Y-%m-%d %H:%M"))  # Показываем дату последней свечи.
    if dataset_symbol is not None and dataset_timeframe is not None:  # Проверяем, есть ли в файле метаданные символа и таймфрейма.
        st.caption(f"Источник data.csv: {dataset_symbol} | {dataset_timeframe}")  # Показываем фактические метаданные, чтобы пользователь видел что именно сейчас тестируется.


def handle_data_button(selected_symbol, selected_timeframe, selected_start_date, selected_end_date):  # Создаем функцию, которая обрабатывает нажатие кнопки загрузки данных.
    button_clicked = st.button("⬇️ Загрузить данные с Binance", type="primary", use_container_width=True)  # Рисуем большую кнопку, по которой пользователь запускает загрузку выбранных параметров.
    if button_clicked:  # Проверяем, была ли нажата кнопка.
        if selected_start_date > selected_end_date:  # Проверяем, что дата начала периода не позже даты окончания.
            st.error("Дата начала периода не может быть позже даты окончания.")  # Показываем понятную ошибку, если диапазон выбран неверно.
            return  # Прерываем загрузку, пока пользователь не исправит диапазон.
        with st.spinner("Скачиваю данные с Binance. Это может занять немного времени..."):  # Показываем анимацию ожидания, пока работает загрузчик.
            run_downloader(symbol=selected_symbol, timeframe=selected_timeframe, start_date=selected_start_date, end_date=selected_end_date, output_file=DATA_FILE)  # Передаем выбранную пару, таймфрейм и диапазон дат в функцию скачивания.
        st.success(f"Загрузка завершена. В файл data.csv сохранены данные {selected_symbol} с таймфреймом {selected_timeframe} за период с {selected_start_date.strftime('%Y-%m-%d')} по {selected_end_date.strftime('%Y-%m-%d')}.")  # Сообщаем, что скачивание успешно завершено для выбранного диапазона.


def show_market_data_tab(selected_symbol, selected_timeframe, selected_start_date, selected_end_date):  # Создаем функцию, которая выводит вкладку с загрузкой и просмотром данных.
    st.caption(f"Сейчас в интерфейсе выбраны: {selected_symbol} | {selected_timeframe} | период с {selected_start_date.strftime('%Y-%m-%d')} по {selected_end_date.strftime('%Y-%m-%d')}.")  # Показываем пользователю, какие параметры сейчас выбраны в боковой панели.
    handle_data_button(selected_symbol, selected_timeframe, selected_start_date, selected_end_date)  # Показываем кнопку загрузки данных внутри вкладки просмотра рынка.
    if not DATA_FILE.exists():  # Проверяем, существует ли data.csv до чтения файла.
        st.warning("Файл data.csv пока отсутствует. Выберите пару, таймфрейм и диапазон дат слева, а затем нажмите кнопку загрузки данных.")  # Показываем понятное предупреждение, если файл еще не создан.
        return  # Останавливаем дальнейший вывод, потому что показывать пока нечего.
    dataframe = load_data_from_csv(DATA_FILE)  # Читаем данные из CSV-файла в таблицу.
    show_dataset_mismatch_warning(dataframe=dataframe, selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)  # Показываем предупреждение, если выбранные параметры не совпадают с текущим файлом данных.
    show_data_summary(dataframe)  # Показываем краткую сводку по загруженным данным.
    st.subheader("Таблица со свечами")  # Добавляем подзаголовок перед таблицей.
    st.dataframe(dataframe, use_container_width=True)  # Выводим таблицу на экран во всю доступную ширину.
    st.subheader("Свечной график")  # Добавляем подзаголовок перед графиком.
    chart = create_candlestick_chart(dataframe, selected_symbol, selected_timeframe)  # Строим свечной график на основе таблицы и текущих настроек в боковой панели.
    st.plotly_chart(chart, use_container_width=True)  # Показываем готовый график в приложении.


def get_strategy_parameter_defaults(selected_strategy_class):  # Создаем функцию, которая извлекает значения params из выбранного класса стратегии.
    raw_params = getattr(selected_strategy_class, "params", ())  # Получаем атрибут params у класса стратегии или пустой кортеж, если его нет.
    if isinstance(raw_params, dict):  # Проверяем, описаны ли параметры стратегии в виде словаря.
        parameter_defaults = dict(raw_params)  # Преобразуем словарь параметров к обычному словарю Python.
    else:  # Переходим в этот блок, если params описан как кортеж пар, что типично для Backtrader.
        parameter_defaults = {name: value for name, value in raw_params}  # Собираем словарь параметров из кортежа пар вида (имя, значение).
    parameter_defaults.pop("commission", None)  # Удаляем комиссию из списка настраиваемых параметров, потому что она не должна редактироваться в этих контролах.
    return parameter_defaults  # Возвращаем словарь параметров стратегии и их значений по умолчанию наружу.


def build_number_input_for_parameter(parameter_name, parameter_value, widget_key):  # Создаем вспомогательную функцию, которая рисует number_input для одного параметра стратегии.
    if isinstance(parameter_value, int):  # Проверяем, является ли значение параметра целым числом.
        input_value = st.number_input(parameter_name, value=int(parameter_value), step=1, key=widget_key)  # Рисуем поле ввода целого числа с шагом 1.
        return int(input_value)  # Возвращаем введенное пользователем значение как целое число.
    input_value = st.number_input(parameter_name, value=float(parameter_value), step=0.1, key=widget_key)  # Рисуем поле ввода дробного числа с шагом 0.1 для нецелых параметров.
    return float(input_value)  # Возвращаем введенное пользователем значение как число с плавающей точкой.


def build_slider_range_for_parameter(parameter_name, parameter_value, widget_key):  # Создаем вспомогательную функцию, которая рисует диапазонный слайдер для одного параметра стратегии.
    if isinstance(parameter_value, int):  # Проверяем, является ли значение параметра целым числом.
        minimum_value = max(1, int(parameter_value) - 5)  # Считаем нижнюю границу слайдера вокруг значения по умолчанию, но не меньше 1.
        maximum_value = max(minimum_value + 1, int(parameter_value) + 5)  # Считаем верхнюю границу слайдера и гарантируем, что она больше нижней.
        slider_value = st.slider(parameter_name, min_value=minimum_value, max_value=maximum_value, value=(minimum_value, maximum_value), step=1, key=widget_key)  # Рисуем диапазонный слайдер для целого параметра.
        return range(slider_value[0], slider_value[1] + 1), slider_value  # Возвращаем Python range для оптимизации и исходный tuple для отображения в session_state.
    minimum_value = max(0.1, float(parameter_value) - 1.0)  # Считаем нижнюю границу слайдера для дробного параметра и не даем ей уйти ниже 0.1.
    maximum_value = max(minimum_value + 0.1, float(parameter_value) + 1.0)  # Считаем верхнюю границу слайдера для дробного параметра.
    slider_value = st.slider(parameter_name, min_value=float(minimum_value), max_value=float(maximum_value), value=(float(minimum_value), float(maximum_value)), step=0.1, key=widget_key)  # Рисуем диапазонный слайдер для дробного параметра.
    return [slider_value[0], slider_value[1]], slider_value  # Возвращаем список с двумя значениями для оптимизации и исходный tuple для отображения в session_state.


def render_strategy_selector(available_strategies, label, key):  # Создаем функцию, которая рисует выпадающий список доступных стратегий.
    strategy_names = list(available_strategies.keys())  # Получаем список имен всех найденных стратегий для выпадающего списка.
    selected_strategy_name = st.selectbox(label, strategy_names, index=0, key=key)  # Создаем выпадающий список выбора стратегии с уникальным ключом.
    selected_strategy_class = available_strategies[selected_strategy_name]  # Получаем класс стратегии по выбранному имени.
    return selected_strategy_name, selected_strategy_class  # Возвращаем выбранное имя стратегии и сам класс наружу.


def render_backtest_controls(selected_strategy_class, selected_strategy_name):  # Создаем функцию, которая динамически рисует поля настройки стратегии внутри вкладки бектеста.
    parameter_defaults = get_strategy_parameter_defaults(selected_strategy_class=selected_strategy_class)  # Получаем словарь параметров выбранной стратегии, кроме commission.
    strategy_kwargs = {}  # Создаем пустой словарь, куда будем складывать введенные пользователем значения параметров.
    if not parameter_defaults:  # Проверяем, есть ли у стратегии параметры для ручной настройки.
        st.info("У выбранной стратегии нет пользовательских параметров для настройки через number_input.")  # Показываем понятное сообщение, если параметров нет.
        return strategy_kwargs  # Возвращаем пустой словарь параметров наружу.
    for parameter_name, parameter_value in parameter_defaults.items():  # Проходим по всем параметрам выбранной стратегии.
        widget_key = f"backtest_{selected_strategy_name}_{parameter_name}"  # Создаем уникальный ключ виджета, чтобы Streamlit не путал поля разных стратегий.
        strategy_kwargs[parameter_name] = build_number_input_for_parameter(parameter_name=parameter_name, parameter_value=parameter_value, widget_key=widget_key)  # Рисуем number_input для текущего параметра и сохраняем результат в словарь.
    return strategy_kwargs  # Возвращаем словарь введенных пользователем параметров стратегии наружу.


def render_optimization_controls(selected_strategy_class, selected_strategy_name):  # Создаем функцию, которая динамически рисует диапазонные слайдеры для оптимизации выбранной стратегии.
    parameter_defaults = get_strategy_parameter_defaults(selected_strategy_class=selected_strategy_class)  # Получаем словарь параметров выбранной стратегии, кроме commission.
    strategy_param_ranges = {}  # Создаем пустой словарь, куда будем складывать диапазоны параметров для оптимизации.
    display_ranges = {}  # Создаем словарь, чтобы сохранить пользовательские tuple-диапазоны для вывода в интерфейсе.
    if not parameter_defaults:  # Проверяем, есть ли у стратегии параметры для оптимизации.
        st.info("У выбранной стратегии нет пользовательских параметров для оптимизации через slider.")  # Показываем понятное сообщение, если параметров нет.
        return strategy_param_ranges, display_ranges  # Возвращаем пустые словари наружу.
    for parameter_name, parameter_value in parameter_defaults.items():  # Проходим по всем параметрам выбранной стратегии.
        widget_key = f"optimization_{selected_strategy_name}_{parameter_name}"  # Создаем уникальный ключ слайдера, чтобы Streamlit не путал диапазоны разных стратегий.
        optimization_values, slider_value = build_slider_range_for_parameter(parameter_name=parameter_name, parameter_value=parameter_value, widget_key=widget_key)  # Рисуем диапазонный слайдер для текущего параметра и получаем значения для оптимизации.
        strategy_param_ranges[parameter_name] = optimization_values  # Сохраняем подготовленный диапазон параметра для передачи в движок оптимизации.
        display_ranges[parameter_name] = slider_value  # Сохраняем исходный tuple диапазона для отображения пользователю.
    return strategy_param_ranges, display_ranges  # Возвращаем словарь диапазонов параметров и словарь отображаемых диапазонов наружу.


def validate_strategy_kwargs(strategy_kwargs):  # Создаем функцию, которая выполняет простую валидацию параметров стратегии перед запуском бектеста.
    if "fast_period" in strategy_kwargs and "slow_period" in strategy_kwargs and strategy_kwargs["fast_period"] >= strategy_kwargs["slow_period"]:  # Проверяем специальный случай SMA, когда fast_period должен быть меньше slow_period.
        return "Период fast_period должен быть меньше slow_period."  # Возвращаем понятный текст ошибки, если параметры введены неверно.
    return None  # Возвращаем None, если ошибок в параметрах не найдено.


def validate_strategy_param_ranges(strategy_param_ranges):  # Создаем функцию, которая выполняет простую валидацию диапазонов параметров стратегии перед оптимизацией.
    if "fast_period" in strategy_param_ranges and "slow_period" in strategy_param_ranges:  # Проверяем, есть ли среди диапазонов оба SMA-параметра.
        fast_values = list(strategy_param_ranges["fast_period"])  # Превращаем диапазон fast_period в список конкретных значений.
        slow_values = list(strategy_param_ranges["slow_period"])  # Превращаем диапазон slow_period в список конкретных значений.
        if fast_values and slow_values and min(fast_values) >= max(slow_values):  # Проверяем крайний случай, когда все возможные fast_period уже не меньше slow_period.
            return "Диапазоны выбраны неудачно: значения fast_period должны быть меньше slow_period хотя бы для части комбинаций."  # Возвращаем понятный текст ошибки, если диапазоны заведомо невалидны.
    return None  # Возвращаем None, если ошибок в диапазонах не найдено.


def save_backtest_results(starting_balance, final_balance, trades_log, equity_curve, strategy_name, strategy_kwargs):  # Создаем функцию, которая сохраняет результаты бектеста в session_state между перерисовками Streamlit.
    st.session_state[BACKTEST_RESULTS_KEY] = {  # Сохраняем словарь с полным набором результатов бектеста.
        "starting_balance": starting_balance,  # Запоминаем стартовый капитал.
        "final_balance": final_balance,  # Запоминаем итоговый капитал.
        "trades_log": trades_log,  # Запоминаем список закрытых сделок.
        "equity_curve": equity_curve,  # Запоминаем историю изменения капитала.
        "strategy_name": strategy_name,  # Запоминаем имя стратегии, по которой считался результат.
        "strategy_kwargs": strategy_kwargs,  # Запоминаем параметры стратегии, которые использовались в бектесте.
    }  # Завершаем сохранение словаря с результатами.


def save_optimization_results(optimization_results, strategy_name, display_ranges):  # Создаем функцию, которая сохраняет результаты оптимизации в session_state.
    st.session_state[OPTIMIZATION_RESULTS_KEY] = {  # Создаем словарь с результатами оптимизации для хранения между перерисовками.
        "results": optimization_results,  # Сохраняем список всех результатов оптимизации.
        "strategy_name": strategy_name,  # Сохраняем имя стратегии, по которой запускалась оптимизация.
        "display_ranges": display_ranges,  # Сохраняем отображаемые диапазоны параметров, выбранные пользователем в слайдерах.
    }  # Завершаем сохранение словаря результатов оптимизации.


def build_trades_dataframe(trades_log):  # Создаем функцию, которая превращает список сделок в удобную таблицу Pandas.
    trades_dataframe = pd.DataFrame(trades_log)  # Создаем таблицу из списка словарей со сделками.
    if trades_dataframe.empty:  # Проверяем, есть ли в логе хотя бы одна закрытая сделка.
        return trades_dataframe  # Если сделок нет, сразу возвращаем пустую таблицу.
    trades_dataframe["open_date"] = pd.to_datetime(trades_dataframe["open_date"])  # Преобразуем дату открытия сделки в настоящий формат даты и времени.
    trades_dataframe["close_date"] = pd.to_datetime(trades_dataframe["close_date"])  # Преобразуем дату закрытия сделки в настоящий формат даты и времени.
    return trades_dataframe  # Возвращаем подготовленную таблицу сделок наружу.


def build_equity_dataframe(equity_curve):  # Создаем функцию, которая превращает историю капитала в таблицу Pandas.
    equity_dataframe = pd.DataFrame(equity_curve)  # Создаем таблицу из списка точек изменения капитала.
    if equity_dataframe.empty:  # Проверяем, есть ли хотя бы одна точка в истории капитала.
        return equity_dataframe  # Если точек нет, сразу возвращаем пустую таблицу.
    equity_dataframe["datetime"] = pd.to_datetime(equity_dataframe["datetime"])  # Преобразуем дату точки капитала в настоящий формат даты и времени.
    return equity_dataframe  # Возвращаем подготовленную таблицу истории капитала наружу.


def build_optimization_dataframe(optimization_results):  # Создаем функцию, которая превращает список результатов оптимизации в таблицу Pandas.
    optimization_dataframe = pd.DataFrame(optimization_results)  # Создаем таблицу из списка словарей по всем комбинациям параметров.
    if optimization_dataframe.empty:  # Проверяем, есть ли хотя бы один результат оптимизации.
        return optimization_dataframe  # Если результатов нет, сразу возвращаем пустую таблицу.
    optimization_dataframe = optimization_dataframe.sort_values("pnl", ascending=False).reset_index(drop=True)  # Сортируем комбинации по убыванию прибыли и обновляем индексы.
    return optimization_dataframe  # Возвращаем отсортированную таблицу наружу.


def highlight_trade_rows(row):  # Создаем функцию для подсветки строк сделок в зависимости от их результата.
    pnl_after_commission = row.get("pnl_after_commission", 0)  # Получаем итоговый результат сделки после комиссии из текущей строки.
    if pnl_after_commission > 0:  # Проверяем, является ли сделка прибыльной.
        background_style = f"background-color: {POSITIVE_ROW_COLOR}"  # Готовим зеленую подсветку для прибыльной сделки.
    elif pnl_after_commission < 0:  # Проверяем, является ли сделка убыточной.
        background_style = f"background-color: {NEGATIVE_ROW_COLOR}"  # Готовим красную подсветку для убыточной сделки.
    else:  # Переходим в этот блок, если сделка закрылась в ноль.
        background_style = ""  # Для нулевого результата не применяем цветовую подсветку.
    return [background_style] * len(row)  # Возвращаем стиль сразу для всех ячеек строки.


def style_trades_dataframe(trades_dataframe):  # Создаем функцию, которая превращает обычную таблицу сделок в стилизованный Pandas Styler.
    styled_dataframe = trades_dataframe.style.apply(highlight_trade_rows, axis=1)  # Применяем подсветку строк по прибыли и убытку через Pandas Styler.
    return styled_dataframe  # Возвращаем готовый стилизованный объект наружу.


def convert_dataframe_to_csv_bytes(dataframe):  # Создаем функцию, которая переводит таблицу в CSV-байты для кнопки скачивания.
    csv_bytes = dataframe.to_csv(index=False).encode("utf-8")  # Преобразуем таблицу в CSV без индекса и кодируем в UTF-8.
    return csv_bytes  # Возвращаем готовые байты наружу.


def show_export_buttons(trades_dataframe, equity_dataframe):  # Создаем функцию, которая рисует две кнопки скачивания рядом друг с другом.
    col_1, col_2 = st.columns(2)  # Создаем две колонки, чтобы кнопки экспорта стояли рядом.
    trades_csv_bytes = convert_dataframe_to_csv_bytes(trades_dataframe)  # Готовим CSV-байты для лога сделок.
    equity_csv_bytes = convert_dataframe_to_csv_bytes(equity_dataframe)  # Готовим CSV-байты для истории капитала.
    col_1.download_button(  # Рисуем кнопку скачивания лога сделок.
        label="📥 Скачать лог сделок (CSV)",  # Задаем текст левой кнопки скачивания.
        data=trades_csv_bytes,  # Передаем подготовленные CSV-байты лога сделок.
        file_name="trades_log.csv",  # Задаем имя файла, который скачает пользователь.
        mime="text/csv",  # Указываем тип содержимого как CSV.
        use_container_width=True,  # Просим Streamlit растянуть кнопку на всю ширину колонки.
    )  # Завершаем описание левой кнопки скачивания.
    col_2.download_button(  # Рисуем кнопку скачивания истории капитала.
        label="📥 Скачать историю капитала (CSV)",  # Задаем текст правой кнопки скачивания.
        data=equity_csv_bytes,  # Передаем подготовленные CSV-байты истории капитала.
        file_name="equity_curve.csv",  # Задаем имя файла для скачивания истории капитала.
        mime="text/csv",  # Указываем тип содержимого как CSV.
        use_container_width=True,  # Просим Streamlit растянуть кнопку на всю ширину колонки.
    )  # Завершаем описание правой кнопки скачивания.


def show_backtest_results(result_data):  # Создаем функцию, которая красиво выводит итог бектеста, лог сделок и график капитала.
    starting_balance = result_data["starting_balance"]  # Извлекаем стартовый капитал из сохраненного результата.
    final_balance = result_data["final_balance"]  # Извлекаем итоговый капитал из сохраненного результата.
    trades_dataframe = build_trades_dataframe(result_data["trades_log"])  # Превращаем лог сделок в таблицу для вывода на экран.
    equity_dataframe = build_equity_dataframe(result_data["equity_curve"])  # Превращаем историю капитала в таблицу для графика.
    profit = final_balance - starting_balance  # Считаем прибыль или убыток стратегии в деньгах.
    profit_delta = f"{profit:,.2f} USDT"  # Подготавливаем красивую подпись для разницы между итоговым и стартовым балансом.
    col_1, col_2, col_3 = st.columns(3)  # Создаем три колонки, чтобы вывести три ключевые метрики в одну строку.
    col_1.metric("Начальный баланс", format_balance(starting_balance))  # Показываем стартовый капитал.
    col_2.metric("Итоговый баланс", format_balance(final_balance), delta=profit_delta)  # Показываем итоговый капитал и его отличие от начального.
    col_3.metric("Прибыль / убыток", format_balance(profit))  # Показываем абсолютный финансовый результат отдельно.
    show_export_buttons(trades_dataframe, equity_dataframe)  # Показываем две кнопки экспорта CSV сразу под карточками метрик.
    st.caption(f"Стратегия: {result_data['strategy_name']} | Параметры: {result_data['strategy_kwargs']}")  # Показываем, какая стратегия и какие параметры использовались в текущем бектесте.
    st.subheader("📝 Лог сделок")  # Добавляем подзаголовок перед таблицей сделок с иконкой.
    if trades_dataframe.empty:  # Проверяем, есть ли у стратегии хотя бы одна закрытая сделка.
        st.info("Закрытых сделок пока нет. Это означает, что за выбранный период стратегия не получила полного сигнала на вход и выход.")  # Показываем понятное сообщение, если лог сделок пуст.
    else:  # Переходим в этот блок, если сделки в логе есть.
        styled_trades_dataframe = style_trades_dataframe(trades_dataframe)  # Применяем цветовую подсветку к таблице сделок через Pandas Styler.
        st.dataframe(styled_trades_dataframe, use_container_width=True)  # Выводим стилизованную таблицу со всеми закрытыми сделками.
    st.subheader("📈 График капитала")  # Добавляем подзаголовок перед equity curve с иконкой.
    if equity_dataframe.empty:  # Проверяем, есть ли точки для построения графика капитала.
        st.info("История капитала пока пуста.")  # Показываем понятное сообщение, если история капитала не была собрана.
    else:  # Переходим в этот блок, если данные для equity curve есть.
        equity_chart = create_equity_curve_chart(equity_dataframe)  # Строим линейный график изменения капитала.
        st.plotly_chart(equity_chart, use_container_width=True)  # Показываем график капитала в интерфейсе.


def show_optimization_results(result_data):  # Создаем функцию, которая показывает лучшую комбинацию параметров и полную таблицу оптимизации.
    optimization_dataframe = build_optimization_dataframe(result_data["results"])  # Преобразуем сохраненные результаты оптимизации в отсортированную таблицу.
    if optimization_dataframe.empty:  # Проверяем, есть ли хотя бы одна валидная комбинация параметров в результатах.
        st.info("Оптимизация не нашла ни одной корректной комбинации параметров. Попробуйте изменить диапазоны.")  # Показываем понятное сообщение, если список результатов пуст.
        return  # Завершаем функцию, потому что показывать таблицу и метрики пока нечего.
    best_result = optimization_dataframe.iloc[0]  # Берем первую строку таблицы как лучшую комбинацию по прибыли.
    best_parameters = [f"{column}={int(best_result[column])}" for column in optimization_dataframe.columns if column not in {"final_balance", "pnl"}]  # Формируем список параметров лучшей комбинации в читаемом виде.
    best_parameters_text = ", ".join(best_parameters)  # Объединяем параметры лучшей комбинации в одну строку.
    best_profit_text = format_balance(float(best_result["pnl"]))  # Красиво форматируем прибыль лучшей комбинации.
    col_1, col_2 = st.columns(2)  # Создаем две колонки для компактного показа лучших результатов оптимизации.
    col_1.metric("Лучшая связка", best_parameters_text)  # Показываем параметры самой прибыльной комбинации.
    col_2.metric("Лучший профит", best_profit_text)  # Показываем прибыль самой успешной комбинации.
    st.caption(f"Стратегия: {result_data['strategy_name']} | Диапазоны: {result_data['display_ranges']}")  # Показываем, по какой стратегии и каким диапазонам была выполнена текущая оптимизация.
    st.subheader("⚡ Результаты оптимизации")  # Добавляем подзаголовок перед итоговой таблицей оптимизации.
    st.dataframe(optimization_dataframe, use_container_width=True)  # Выводим таблицу всех комбинаций, уже отсортированную по убыванию прибыли.


def show_backtest_tab(available_strategies, selected_symbol, selected_timeframe):  # Создаем функцию, которая выводит вкладку бектеста и запускает симуляцию по кнопке.
    st.subheader("⚙️ Настройки стратегии")  # Показываем подзаголовок раздела бектеста с иконкой.
    if not DATA_FILE.exists():  # Проверяем, есть ли файл data.csv перед запуском бектеста.
        st.warning("Сначала загрузите исторические данные во вкладке 'Данные и график'.")  # Показываем понятное предупреждение, если файл с данными еще не создан.
        return  # Прерываем дальнейший вывод, потому что бектест пока запускать не на чем.
    preview_dataframe = load_data_from_csv(DATA_FILE)  # Читаем data.csv перед бектестом, чтобы проверить соответствие выбранных параметров текущему набору.
    show_dataset_mismatch_warning(dataframe=preview_dataframe, selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)  # Показываем предупреждение, если в файле данные другой пары или таймфрейма.
    selected_strategy_name, selected_strategy_class = render_strategy_selector(available_strategies=available_strategies, label="Стратегия для бектеста", key="backtest_strategy_selector")  # Показываем выпадающий список всех доступных стратегий для вкладки бектеста.
    strategy_kwargs = render_backtest_controls(selected_strategy_class=selected_strategy_class, selected_strategy_name=selected_strategy_name)  # Динамически рисуем поля настройки параметров для выбранной стратегии и получаем kwargs.
    validation_error = validate_strategy_kwargs(strategy_kwargs=strategy_kwargs)  # Проверяем параметры стратегии перед запуском бектеста.
    if validation_error is not None:  # Проверяем, нашлась ли ошибка валидации параметров.
        st.error(validation_error)  # Показываем понятную ошибку, если параметры введены неверно.
        return  # Останавливаем запуск бектеста до исправления значений.
    button_clicked = st.button("🚀 Запустить бектест", type="primary", use_container_width=True)  # Создаем большую кнопку запуска бектеста с иконкой.
    if button_clicked:  # Проверяем, нажал ли пользователь кнопку запуска.
        with st.spinner("Запускаю бектест стратегии. Пожалуйста, подождите..."):  # Показываем анимацию ожидания, пока идет расчет.
            starting_balance, final_balance, trades_log, equity_curve = run_backtest(strategy_class=selected_strategy_class, data_file=DATA_FILE, strategy_kwargs=strategy_kwargs)  # Запускаем движок бектеста с выбранной стратегией и ее параметрами.
        save_backtest_results(starting_balance, final_balance, trades_log, equity_curve, strategy_name=selected_strategy_name, strategy_kwargs=strategy_kwargs)  # Сохраняем результаты бектеста в session_state, чтобы они не исчезали после перерисовки.
        st.success(f"Бектест завершен для стратегии {selected_strategy_name}.")  # Сообщаем, что симуляция успешно завершилась.
    result_data = st.session_state.get(BACKTEST_RESULTS_KEY)  # Пробуем получить сохраненный результат последнего запущенного бектеста.
    if result_data is None:  # Проверяем, запускался ли бектест хотя бы один раз в текущей сессии.
        st.info("После запуска бектеста здесь появятся метрики, лог сделок и график капитала.")  # Показываем подсказку, пока результатов еще нет.
        return  # Завершаем функцию, потому что показывать пока нечего.
    show_backtest_results(result_data)  # Показываем метрики, кнопки экспорта, таблицу сделок и график капитала из сохраненного результата.


def show_optimization_tab(available_strategies, selected_symbol, selected_timeframe):  # Создаем функцию, которая выводит вкладку оптимизации и запускает перебор параметров по кнопке.
    st.subheader("⚡ Оптимизация параметров стратегии")  # Показываем подзаголовок раздела оптимизации с иконкой.
    st.write("Здесь можно перебрать множество комбинаций параметров стратегии и быстро найти самую прибыльную связку.")  # Простыми словами объясняем, что делает этот раздел.
    if not DATA_FILE.exists():  # Проверяем, есть ли файл data.csv перед запуском оптимизации.
        st.warning("Сначала загрузите исторические данные во вкладке 'Данные и график'.")  # Показываем понятное предупреждение, если файл с данными еще не создан.
        return  # Прерываем дальнейний вывод, потому что оптимизацию пока запускать не на чем.
    preview_dataframe = load_data_from_csv(DATA_FILE)  # Читаем data.csv перед оптимизацией, чтобы проверить соответствие выбранных параметров текущему набору.
    show_dataset_mismatch_warning(dataframe=preview_dataframe, selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)  # Показываем предупреждение, если в файле данные другой пары или таймфрейма.
    selected_strategy_name, selected_strategy_class = render_strategy_selector(available_strategies=available_strategies, label="Стратегия для оптимизации", key="optimization_strategy_selector")  # Показываем выпадающий список всех доступных стратегий для вкладки оптимизации.
    strategy_param_ranges, display_ranges = render_optimization_controls(selected_strategy_class=selected_strategy_class, selected_strategy_name=selected_strategy_name)  # Динамически рисуем диапазонные слайдеры и получаем словарь диапазонов параметров для выбранной стратегии.
    validation_error = validate_strategy_param_ranges(strategy_param_ranges=strategy_param_ranges)  # Проверяем диапазоны параметров стратегии перед оптимизацией.
    if validation_error is not None:  # Проверяем, нашлась ли ошибка валидации диапазонов.
        st.error(validation_error)  # Показываем понятную ошибку, если диапазоны выбраны неудачно.
        return  # Останавливаем запуск оптимизации до исправления диапазонов.
    button_clicked = st.button("⚡ Запустить оптимизацию", type="primary", use_container_width=True)  # Создаем большую кнопку запуска оптимизации.
    if button_clicked:  # Проверяем, нажал ли пользователь кнопку запуска оптимизации.
        with st.spinner("Запускаю оптимизацию стратегии. Это может занять некоторое время..."):  # Показываем анимацию ожидания, пока движок перебирает все комбинации.
            optimization_results = run_optimization(strategy_class=selected_strategy_class, data_file=DATA_FILE, strategy_param_ranges=strategy_param_ranges, strategy_kwargs={})  # Запускаем оптимизацию для выбранной стратегии и переданных диапазонов параметров.
        save_optimization_results(optimization_results, strategy_name=selected_strategy_name, display_ranges=display_ranges)  # Сохраняем результаты оптимизации в session_state, чтобы они не исчезали после перерисовки.
        st.success(f"Оптимизация завершена для стратегии {selected_strategy_name}.")  # Сообщаем, что перебор параметров успешно завершился.
    result_data = st.session_state.get(OPTIMIZATION_RESULTS_KEY)  # Пробуем получить сохраненный результат последней оптимизации.
    if result_data is None:  # Проверяем, запускалась ли оптимизация хотя бы один раз в текущей сессии.
        st.info("После запуска оптимизации здесь появятся лучшая связка параметров и таблица всех результатов.")  # Показываем подсказку, пока результатов еще нет.
        return  # Завершаем функцию, потому что показывать пока нечего.
    show_optimization_results(result_data)  # Показываем метрики и таблицу результатов оптимизации.


def main():  # Создаем главную функцию приложения Streamlit.
    configure_page()  # Сначала настраиваем страницу и выводим заголовок.
    available_strategies = get_available_strategies()  # Загружаем все доступные стратегии из папки strategies один раз на запуск страницы.
    selected_symbol, selected_timeframe, selected_start_date, selected_end_date = render_sidebar()  # Затем рисуем боковую панель и получаем выбор пользователя.
    data_tab, backtest_tab, optimization_tab = st.tabs(["📊 Данные и график", "🧪 Бектест", "⚡ Оптимизация"])  # Создаем три вкладки, чтобы разделить просмотр данных, бектест и оптимизацию.
    with data_tab:  # Открываем контекст первой вкладки.
        show_market_data_tab(selected_symbol, selected_timeframe, selected_start_date, selected_end_date)  # Рисуем содержимое вкладки с загрузкой данных и графиком.
    with backtest_tab:  # Открываем контекст второй вкладки.
        show_backtest_tab(available_strategies=available_strategies, selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)  # Рисуем содержимое вкладки бектеста с динамическим выбором стратегии.
    with optimization_tab:  # Открываем контекст третьей вкладки.
        show_optimization_tab(available_strategies=available_strategies, selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)  # Рисуем содержимое вкладки оптимизации параметров стратегии.


if __name__ == "__main__":  # Проверяем, что файл app.py запущен как основной модуль.
    main()  # Запускаем приложение.
