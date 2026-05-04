from datetime import date, datetime, timedelta, timezone  # Импортируем date и timedelta, чтобы задавать диапазон дат в интерфейсе.
from pathlib import Path
import threading
import time
from typing import Any
from uuid import uuid4  # Импортируем Path, чтобы удобно работать с путями к файлам проекта.

import pandas as pd  # Импортируем Pandas, чтобы читать CSV-файл и работать с таблицами.
import numpy as np  # Импортируем NumPy для векторных операций и удобного выбора цвета объема.
import plotly.graph_objects as go  # Импортируем Plotly, чтобы строить красивые графики.
import plotly.io as pio  # Импортируем модуль настройки Plotly, чтобы включить темную тему графиков.
from plotly.subplots import make_subplots  # Импортируем функцию для двухпанельного графика (свечи + объем).
import streamlit as st  # Импортируем Streamlit, чтобы создать веб-интерфейс.

from backtest.engine import format_balance  # Импортируем функцию форматирования суммы для красивого вывода результатов.
from backtest.engine import run_backtest  # Импортируем функцию запуска бектеста.
from backtest.engine import run_optimization  # Импортируем функцию оптимизации параметров стратегии.
from data.downloader import OUTPUT_FILE
from data.downloader import build_market_data_file_context  # Импортируем путь к файлу data.csv из загрузчика.
from data.downloader import get_market_data_file  # Импортируем функцию для отдельных файлов по паре и таймфрейму.
from data.downloader import run_downloader  # Импортируем функцию загрузки, которая умеет принимать параметры интерфейса.
from utils.profile_manager import append_optimization_history
from utils.profile_manager import get_or_init_profile
from utils.profile_manager import load_profiles
from utils.profile_manager import merge_params_with_defaults
from utils.profile_manager import save_profiles
from utils.profile_manager import update_active_params
from utils.profile_manager import update_candidate_params
from utils.optimization_store import build_optimization_scope_key
from utils.optimization_store import load_last_optimization_result
from utils.optimization_store import save_last_optimization_result
from utils.strategy_loader import load_available_strategies  # Импортируем загрузчик стратегий, чтобы автоматически находить все стратегии из папки strategies.

pio.templates.default = "plotly_dark"  # Принудительно включаем темную тему для всех графиков Plotly.

APP_TITLE = "Crypto Backtester Pro"  # Задаем новый заголовок приложения в более профессиональном стиле.
APP_DESCRIPTION = "Профессиональный терминал для загрузки исторических свечей Binance, просмотра данных и запуска бектеста."  # Задаем описание приложения для верхнего блока.
DATA_FILE = Path(OUTPUT_FILE)  # Преобразуем путь к CSV-файлу в объект Path для проверки существования файла.
AVAILABLE_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]  # Создаем список доступных торговых пар для выпадающего списка.
AVAILABLE_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"]  # Добавляем быстрые и долгие интервалы таймфрейма для гибкой аналитики.
BINANCE_START_DATE = date(2017, 1, 1)  # Сохраняем разумную минимальную дату выбора периода, близкую к старту Binance.
BACKTEST_RESULTS_KEY = "backtest_results"  # Создаем ключ для хранения результатов бектеста в session_state.
OPTIMIZATION_RESULTS_KEY = "optimization_results"  # Создаем ключ для хранения результатов оптимизации в session_state.
POSITIVE_ROW_COLOR = "rgba(38, 166, 154, 0.2)"  # Сохраняем цвет подсветки прибыльных сделок.
NEGATIVE_ROW_COLOR = "rgba(239, 83, 80, 0.2)"  # Сохраняем цвет подсветки убыточных сделок.
MAX_CANDLES_ON_CHART = 8000  # Ограничиваем количество свечей на графике для стабильной отрисовки.
BACKTEST_DEFAULT_CHART_HEIGHT = 700  # Базовая высота графика бектеста в обычном режиме.
BACKTEST_FULLSCREEN_CHART_HEIGHT = 980  # Высота графика в полноэкранном модальном режиме.
PLOTLY_WHEEL_ZOOM_CONFIG = {
    "scrollZoom": True,
    "displayModeBar": True,
    "doubleClick": "reset",
    "showTips": False,
}
PROFILE_STORE_FILE = Path(__file__).resolve().parent / "strategy_profiles.json"
OPTIMIZATION_STORE_FILE = Path(__file__).resolve().parent / "output" / "optimization_memory.json"
OPTIMIZATION_STORE_TTL_HOURS = 72
OPTIMIZATION_WARNING_COMBINATIONS = 20_000
OPTIMIZATION_MAX_COMBINATIONS = 50_000
OPTIMIZATION_SECONDS_PER_1000_ROWS_PER_COMBINATION = 0.62
OPTIMIZATION_TASK_STATE_KEY = "_optimization_task_state"
OPTIMIZATION_NOTICE_KEY = "_optimization_notice"
OPTIMIZATION_AUTORERUN_INTERVAL_SECONDS = 0.75
OPTIMIZATION_ALLOWED_GROUPS = {"indicator", "averaging", "take_profit", "stop_loss"}
OPTIMIZATION_ALLOWED_FALLBACK_KEYWORDS = (
    "rsi",
    "smi",
    "ema",
    "sma",
    "ma_",
    "vwma",
    "macd",
    "stoch",
    "adx",
    "cci",
    "mfi",
    "length",
    "period",
    "threshold",
    "dca",
    "averag",
    "take_profit",
    "tp",
    "stop_loss",
    "sl",
)
OPTIMIZATION_METHOD_LABEL_TO_VALUE = {
    "Полный перебор (Brute force)": "bruteforce",
    "Случайный поиск (Random)": "random",
    "Генетический алгоритм (Genetic)": "genetic",
}
OPTIMIZATION_METHOD_DEFAULT_LABEL = "Полный перебор (Brute force)"
OPTIMIZATION_FITNESS_DEFAULT = "PnL"
OPTIMIZATION_RANDOM_DEFAULT_ITERATIONS = 2000
OPTIMIZATION_GENETIC_DEFAULT_SETTINGS = {
    "population": 12,
    "generations_max": 20,
    "generations_stagnation": 5,
    "mutation_probability": 0.12,
    "crossover_probability": 0.9,
    "tournament_size": 3,
    "elite_count": 2,
}
PARAMETER_LABELS_RU = {
    "fast_period": "Период быстрой SMA",
    "slow_period": "Период медленной SMA",
    "vwma_length": "Длина VWMA",
    "rsi_length": "Длина RSI",
    "smi_length": "Длина SMI",
    "smi_smooth": "Сглаживание SMI",
    "ema_fast_length": "Длина быстрой EMA",
    "ema_slow_length": "Длина медленной EMA",
    "rsi_threshold": "Порог RSI",
    "smi_threshold": "Порог SMI",
    "dca_1_percent": "Усреднение 1 (% депозита)",
    "dca_2_percent": "Усреднение 2 (% депозита)",
    "dca_3_percent": "Усреднение 3 (% депозита)",
    "dca_4_percent": "Усреднение 4 (% депозита)",
    "take_profit_percent": "Тейк-профит (%)",
    "stop_loss_percent": "Стоп-лосс (%)",
}


class OptimizationCancelledError(RuntimeError):
    """Raised when optimization is cancelled from optimization tab controls."""


def get_selected_data_file(selected_symbol: str, selected_timeframe: str) -> Path:
    return get_market_data_file(symbol=selected_symbol, timeframe=selected_timeframe)


def _build_file_cache_signature(file_path: Path) -> tuple[str, int, int]:
    normalized_path = Path(file_path).resolve()
    file_stats = normalized_path.stat()
    mtime_ns = int(getattr(file_stats, "st_mtime_ns", int(file_stats.st_mtime * 1_000_000_000)))
    return str(normalized_path), int(file_stats.st_size), mtime_ns


@st.cache_data(show_spinner=False)
def _load_data_from_csv_cached(path_str: str, size_bytes: int, mtime_ns: int) -> pd.DataFrame:
    del size_bytes, mtime_ns  # Эти аргументы используются в cache-key для инвалидатора.
    dataframe = pd.read_csv(path_str, encoding="utf-8")
    dataframe["datetime"] = pd.to_datetime(dataframe["datetime"], utc=True, errors="coerce")
    dataframe = dataframe.dropna(subset=["datetime"]).reset_index(drop=True)
    dataframe["datetime"] = dataframe["datetime"].dt.tz_localize(None)
    return dataframe


@st.cache_data(show_spinner=False)
def _build_market_data_context_cached(
    path_str: str,
    size_bytes: int,
    mtime_ns: int,
    symbol: str,
    timeframe: str,
    mode: str,
) -> dict[str, Any]:
    del size_bytes, mtime_ns  # Эти аргументы используются в cache-key для инвалидатора.
    return build_market_data_file_context(
        data_file=Path(path_str),
        symbol=symbol,
        timeframe=timeframe,
        mode=mode,
    )


def get_market_data_context(
    file_path: Path,
    *,
    symbol: str = "",
    timeframe: str = "",
    mode: str = "light",
) -> dict[str, Any]:
    if not file_path.exists():
        return build_market_data_file_context(
            data_file=file_path,
            symbol=symbol,
            timeframe=timeframe,
            mode=mode,
        )
    path_str, size_bytes, mtime_ns = _build_file_cache_signature(file_path)
    return _build_market_data_context_cached(
        path_str=path_str,
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
        symbol=symbol,
        timeframe=timeframe,
        mode=mode,
    )


def load_data_from_csv(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(f"Market data file not found: {file_path}")
    path_str, size_bytes, mtime_ns = _build_file_cache_signature(file_path)
    return _load_data_from_csv_cached(path_str, size_bytes, mtime_ns)


def filter_data_file_by_date_range(
    file_path: Path,
    start_date: date | None,
    end_date: date | None,
) -> pd.DataFrame:
    dataframe = load_data_from_csv(file_path)
    return filter_data_by_date_range(dataframe, start_date, end_date)


def _timestamp_ms_to_date(value: Any) -> date | None:
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return None
    parsed = pd.to_datetime(int(numeric_value), unit="ms", utc=True, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime().date()


def plotly_chart_with_wheel(chart: go.Figure, **kwargs):  # Отрисовывает график Plotly с единым конфигом колесика.
    plotly_config = PLOTLY_WHEEL_ZOOM_CONFIG.copy()
    if "config" in kwargs and kwargs["config"]:
        plotly_config.update(kwargs.pop("config"))

    st.plotly_chart(
        chart,
        width="stretch",
        config=plotly_config,
        **kwargs,
    )


def deserialize_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    if hasattr(parsed, "to_pydatetime"):
        return parsed.to_pydatetime().date()
    return None


def classify_app_exception(error: Exception) -> tuple[str, str]:
    message = str(error).strip() or error.__class__.__name__
    message = message.replace("\n", " ").replace("\r", " ").strip()
    normalized = message.lower()
    error_type_name = error.__class__.__name__.lower()

    validation_tokens = ("invalid", "must", "should", "диапазон", "параметр", "validation")
    data_tokens = ("no data", "empty", "missing", "csv", "file", "не найден", "данных", "market data")
    api_tokens = (
        "binance",
        "network",
        "timeout",
        "connection",
        "exchange",
        "requesttimeout",
        "read timed out",
        "ssl",
    )

    if isinstance(error, (ValueError, TypeError)) and any(token in normalized for token in validation_tokens):
        return "Validation", message
    if isinstance(error, (FileNotFoundError, PermissionError)) or any(token in normalized for token in data_tokens):
        return "Data", message
    if any(token in normalized for token in api_tokens) or any(
        token in error_type_name for token in ("networkerror", "requesttimeout", "exchangeerror", "connectionerror")
    ):
        return "API", message
    return "Execution", message


def show_classified_error(prefix: str, error: Exception) -> None:
    category, normalized_message = classify_app_exception(error)
    st.error(f"{prefix} ({category}): {normalized_message}")


def _count_optimization_values(values: Any) -> int:
    if isinstance(values, range):
        return max(0, len(values))
    if isinstance(values, (list, tuple, set)):
        return max(0, len(values))
    if values is None:
        return 0
    return 1


def estimate_optimization_combinations(strategy_param_ranges: dict[str, Any]) -> tuple[int, dict[str, int]]:
    if not isinstance(strategy_param_ranges, dict) or not strategy_param_ranges:
        return 0, {}

    combination_sizes: dict[str, int] = {}
    total_combinations = 1
    for parameter_name, values in strategy_param_ranges.items():
        current_size = _count_optimization_values(values)
        combination_sizes[str(parameter_name)] = current_size
        if current_size <= 0:
            return 0, combination_sizes
        total_combinations *= current_size
    return total_combinations, combination_sizes


def format_date_ddmmyyyy(value: date | None) -> str:
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return "дата не указана"


def format_duration_mmss(total_seconds: float | int | None) -> str:
    if total_seconds is None:
        return "—"
    safe_seconds = int(round(float(total_seconds)))
    safe_seconds = max(0, safe_seconds)
    hours, remainder = divmod(safe_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def estimate_selected_rows_for_optimization(
    data_file: Path,
    *,
    symbol: str,
    timeframe: str,
    start_date: date | None,
    end_date: date | None,
) -> int | None:
    if not data_file.exists():
        return None
    try:
        data_context = get_market_data_context(
            file_path=data_file,
            symbol=symbol,
            timeframe=timeframe,
            mode="light",
        )
    except Exception:
        return None

    total_rows = int(data_context.get("rows", 0) or 0)
    if total_rows <= 0:
        return None

    context_start = _timestamp_ms_to_date(data_context.get("first_timestamp"))
    context_end = _timestamp_ms_to_date(data_context.get("last_timestamp"))
    if context_start is None or context_end is None or context_end < context_start:
        return total_rows

    effective_start = start_date or context_start
    effective_end = end_date or context_end
    if effective_end < effective_start:
        effective_start, effective_end = effective_end, effective_start

    clamped_start = max(context_start, effective_start)
    clamped_end = min(context_end, effective_end)
    if clamped_end < clamped_start:
        return 0

    total_days = max(1, (context_end - context_start).days + 1)
    selected_days = max(1, (clamped_end - clamped_start).days + 1)
    share = min(1.0, max(0.0, float(selected_days) / float(total_days)))
    estimated_rows = int(round(float(total_rows) * share))
    return max(1, estimated_rows)


def estimate_optimization_runtime_seconds(
    *,
    combinations: int,
    estimated_rows: int | None,
) -> float | None:
    if combinations <= 0 or estimated_rows is None or estimated_rows <= 0:
        return None
    rows_in_thousands = float(estimated_rows) / 1000.0
    seconds = float(combinations) * rows_in_thousands * float(OPTIMIZATION_SECONDS_PER_1000_ROWS_PER_COMBINATION)
    return max(0.0, seconds)


def _normalize_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def estimate_expected_optimization_evaluations(
    *,
    optimization_mode: str,
    estimated_combinations: int,
    brute_force_max_iterations: int | None = None,
    random_iterations: int | None = None,
    genetic_settings: dict[str, Any] | None = None,
    genetic_max_iterations: int | None = None,
) -> int:
    total_combinations = max(0, int(estimated_combinations))
    if total_combinations <= 0:
        return 0

    normalized_mode = str(optimization_mode or "").strip().lower()
    if normalized_mode == "random":
        planned_runs = _normalize_positive_int(random_iterations) or min(
            total_combinations,
            OPTIMIZATION_RANDOM_DEFAULT_ITERATIONS,
        )
    elif normalized_mode == "genetic":
        safe_settings = genetic_settings if isinstance(genetic_settings, dict) else {}
        population = max(2, int(safe_settings.get("population", 8) or 8))
        generations_max = max(1, int(safe_settings.get("generations_max", 20) or 20))
        planned_runs = population * generations_max
        max_runs = _normalize_positive_int(genetic_max_iterations)
        if max_runs is not None:
            planned_runs = min(planned_runs, max_runs)
    else:
        planned_runs = total_combinations
        max_runs = _normalize_positive_int(brute_force_max_iterations)
        if max_runs is not None:
            planned_runs = min(planned_runs, max_runs)

    return min(total_combinations, max(0, int(planned_runs)))


def _humanize_parameter_name(parameter_name: str) -> str:
    normalized = str(parameter_name).replace("_", " ").strip()
    if not normalized:
        return str(parameter_name)
    return normalized[0].upper() + normalized[1:]


def get_parameter_display_name(
    parameter_name: str,
    parameter_specs: dict[str, dict[str, Any]] | None = None,
) -> str:
    spec = parameter_specs.get(parameter_name, {}) if isinstance(parameter_specs, dict) else {}
    if isinstance(spec, dict):
        label_ru = spec.get("label_ru")
        if isinstance(label_ru, str) and label_ru.strip():
            return label_ru.strip()
    fallback_label = PARAMETER_LABELS_RU.get(parameter_name)
    if fallback_label is not None:
        return fallback_label
    return _humanize_parameter_name(parameter_name)


def get_strategy_optimization_whitelist(selected_strategy_class) -> set[str]:
    raw_whitelist = getattr(selected_strategy_class, "OPTIMIZATION_PARAM_WHITELIST", ())
    if not isinstance(raw_whitelist, (list, tuple, set)):
        return set()
    normalized: set[str] = set()
    for parameter_name in raw_whitelist:
        if isinstance(parameter_name, str) and parameter_name.strip():
            normalized.add(parameter_name.strip())
    return normalized


def is_parameter_allowed_for_optimization(
    parameter_name: str,
    parameter_spec: dict[str, Any] | None,
    optimization_whitelist: set[str],
) -> bool:
    if optimization_whitelist:
        return parameter_name in optimization_whitelist

    spec = parameter_spec or {}
    group = str(spec.get("optimization_group", "")).strip().lower() if isinstance(spec, dict) else ""
    if group in OPTIMIZATION_ALLOWED_GROUPS:
        return True

    normalized_name = parameter_name.lower()
    return any(token in normalized_name for token in OPTIMIZATION_ALLOWED_FALLBACK_KEYWORDS)


def build_labeled_parameter_ranges(
    parameters: dict[str, Any],
    parameter_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        return {}

    labeled: dict[str, Any] = {}
    for parameter_name, value in parameters.items():
        display_name = get_parameter_display_name(parameter_name, parameter_specs=parameter_specs)
        labeled[display_name] = value
    return labeled


def build_parameters_dataframe(
    parameters: dict[str, Any],
    parameter_specs: dict[str, dict[str, Any]] | None = None,
) -> pd.DataFrame:
    if not isinstance(parameters, dict) or not parameters:
        return pd.DataFrame(columns=["Параметр", "Значение"])
    return pd.DataFrame(
        [
            {
                "Параметр": get_parameter_display_name(parameter_name, parameter_specs=parameter_specs),
                "Значение": parameter_value,
            }
            for parameter_name, parameter_value in parameters.items()
        ]
    )


def load_strategy_profile_bundle(
    selected_symbol: str,
    selected_strategy_name: str,
    selected_strategy_class,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    default_params = get_strategy_parameter_defaults(selected_strategy_class=selected_strategy_class)
    profile_store = load_profiles(PROFILE_STORE_FILE)
    profile = get_or_init_profile(
        store=profile_store,
        symbol=selected_symbol,
        strategy_name=selected_strategy_name,
        default_params=default_params,
    )
    active_params = merge_params_with_defaults(default_params, profile.get("active_params"))
    candidate_raw = profile.get("candidate_params")
    candidate_params = (
        merge_params_with_defaults(default_params, candidate_raw)
        if isinstance(candidate_raw, dict) and candidate_raw
        else {}
    )
    return profile_store, profile, default_params, active_params, candidate_params


def prime_strategy_widget_state(
    widget_prefix: str,
    selected_strategy_name: str,
    params: dict[str, Any] | None,
) -> None:
    if not isinstance(params, dict):
        return
    for parameter_name, parameter_value in params.items():
        widget_key = f"{widget_prefix}_{selected_strategy_name}_{parameter_name}"
        st.session_state[widget_key] = parameter_value


def get_data_file_date_range(
    file_path: Path,
    *,
    symbol: str = "",
    timeframe: str = "",
) -> tuple[date | None, date | None]:
    if not file_path.exists():
        return None, None

    try:
        context = get_market_data_context(
            file_path=file_path,
            symbol=symbol,
            timeframe=timeframe,
            mode="light",
        )
    except Exception:
        return None, None

    first_date = _timestamp_ms_to_date(context.get("first_timestamp"))
    last_date = _timestamp_ms_to_date(context.get("last_timestamp"))
    if first_date is None or last_date is None:
        try:
            dataframe = load_data_from_csv(file_path)
        except Exception:
            return None, None
        if dataframe.empty:
            return None, None
        return dataframe["datetime"].min().date(), dataframe["datetime"].max().date()

    if first_date > last_date:
        return None, None

    return first_date, last_date


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
    selected_data_file = get_selected_data_file(selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)
    file_start_date, file_end_date = get_data_file_date_range(
        selected_data_file,
        symbol=selected_symbol,
        timeframe=selected_timeframe,
    )
    if file_start_date is not None and file_end_date is not None:
        default_start_date = file_start_date
        default_end_date = file_end_date
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


def downsample_for_chart(dataframe, max_points=MAX_CANDLES_ON_CHART):  # Создаем функцию для агрегации свечей по периоду.
    if dataframe.empty or len(dataframe) <= max_points:  # Если данных мало или их нет, оставляем как есть.
        return dataframe  # Возвращаем исходный DataFrame без изменений.
    if max_points <= 1:
        return dataframe.head(1).reset_index(drop=True)

    # Используем ту же групповую схему, что и для индикаторов, чтобы оси были строго синхронны.
    normalized = dataframe.reset_index(drop=True).copy()
    group_indices = _build_chart_group_indices(len(normalized), max_points=max_points)
    if group_indices is None or len(group_indices) != len(normalized):
        return normalized

    normalized["_group"] = group_indices
    aggregations = {
        "datetime": ("datetime", "first"),
        "open": ("open", "first"),
        "high": ("high", "max"),
        "low": ("low", "min"),
        "close": ("close", "last"),
        "volume": ("volume", "sum"),
    }
    if "timestamp" in normalized.columns:
        aggregations = {"timestamp": ("timestamp", "first"), **aggregations}

    grouped = normalized.groupby("_group", sort=True, as_index=False).agg(**aggregations)
    grouped = grouped.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)
    output_columns = ["datetime", "open", "high", "low", "close", "volume"]
    if "timestamp" in grouped.columns:
        output_columns = ["timestamp", *output_columns]
    return grouped[output_columns]


def _build_chart_group_indices(row_count: int, max_points: int = MAX_CANDLES_ON_CHART) -> np.ndarray | None:
    if row_count == 0:
        return None
    if row_count <= max_points or max_points <= 1:
        return np.arange(row_count)
    step = max(1, int(row_count / max_points) + (1 if row_count % max_points else 0))
    if step <= 1:
        return np.arange(row_count)
    return np.arange(row_count) // step


def _points_to_indicator_df(points) -> pd.DataFrame:
    if points is None:
        return pd.DataFrame(columns=["datetime", "value"])
    if isinstance(points, pd.DataFrame):
        dataframe = points.copy()
    else:
        dataframe = pd.DataFrame(points)

    if dataframe.empty:
        return dataframe
    if "datetime" not in dataframe.columns or "value" not in dataframe.columns:
        return pd.DataFrame(columns=["datetime", "value"])

    dataframe["datetime"] = pd.to_datetime(dataframe["datetime"], utc=True, errors="coerce")
    dataframe["datetime"] = dataframe["datetime"].dt.tz_localize(None)
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    return dataframe.dropna(subset=["datetime", "value"]).sort_values("datetime").reset_index(drop=True)


def _indicator_payload_id(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("id", "source_attr", "label"):
        value = str(payload.get(key, "")).strip()
        if value:
            return value
    return None


def _filter_indicator_payload(payload_list, start_date: date | None = None, end_date: date | None = None) -> list[dict]:
    if not payload_list:
        return []
    if start_date is None and end_date is None:
        return payload_list

    start_datetime = pd.Timestamp(start_date) if start_date is not None else None
    end_datetime = pd.Timestamp(end_date + timedelta(days=1)) if end_date is not None else None

    filtered_payloads: list[dict] = []
    for payload in payload_list:
        if not isinstance(payload, dict):
            continue
        indicator_df = _points_to_indicator_df(payload.get("points", []))
        if indicator_df.empty:
            filtered_payload = dict(payload)
            filtered_payload["points"] = []
            filtered_payloads.append(filtered_payload)
            continue
        if start_datetime is not None and end_datetime is not None:
            indicator_df = indicator_df[(indicator_df["datetime"] >= start_datetime) & (indicator_df["datetime"] < end_datetime)]
        elif start_datetime is not None:
            indicator_df = indicator_df[indicator_df["datetime"] >= start_datetime]
        elif end_datetime is not None:
            indicator_df = indicator_df[indicator_df["datetime"] < end_datetime]

        filtered_payload = dict(payload)
        filtered_payload["points"] = indicator_df.to_dict("records")
        filtered_payloads.append(filtered_payload)
    return filtered_payloads


def _downsample_indicator_payloads(dataframe: pd.DataFrame, payload_list: list[dict], max_points=MAX_CANDLES_ON_CHART) -> list[dict]:
    if not payload_list:
        return []
    if not isinstance(dataframe, pd.DataFrame):
        return []

    def _empty_payload_copy(payload: dict) -> dict:
        normalized_payload = dict(payload)
        normalized_payload["points"] = []
        return normalized_payload

    if dataframe.empty:
        return [_empty_payload_copy(payload) for payload in payload_list if isinstance(payload, dict)]
    if "datetime" not in dataframe.columns:
        return [_empty_payload_copy(payload) for payload in payload_list if isinstance(payload, dict)]

    normalized_dataframe = dataframe.copy()
    normalized_dataframe["datetime"] = pd.to_datetime(normalized_dataframe["datetime"], utc=True, errors="coerce")
    normalized_dataframe = normalized_dataframe.dropna(subset=["datetime"]).reset_index(drop=True)
    if normalized_dataframe.empty:
        return [_empty_payload_copy(payload) for payload in payload_list if isinstance(payload, dict)]
    normalized_dataframe["datetime"] = normalized_dataframe["datetime"].dt.tz_localize(None)

    group_indices = _build_chart_group_indices(len(normalized_dataframe), max_points=max_points)
    if group_indices is None or len(group_indices) != len(normalized_dataframe):
        return [dict(payload) if isinstance(payload, dict) else payload for payload in payload_list]

    datetime_to_group = pd.Series(group_indices, index=normalized_dataframe["datetime"]).to_dict()

    downsampled_payloads: list[dict] = []
    for payload in payload_list:
        if not isinstance(payload, dict):
            continue
        payload_points = _points_to_indicator_df(payload.get("points", []))
        if payload_points.empty:
            new_payload = dict(payload)
            new_payload["points"] = []
            downsampled_payloads.append(new_payload)
            continue

        payload_points["group"] = payload_points["datetime"].map(datetime_to_group)
        payload_points = payload_points.dropna(subset=["group"]).copy()
        if payload_points.empty:
            new_payload = dict(payload)
            new_payload["points"] = []
            downsampled_payloads.append(new_payload)
            continue

        payload_points["group"] = payload_points["group"].astype(int)
        aggregated = (
            payload_points.groupby("group", sort=True)
            .agg(datetime=("datetime", "first"), value=("value", "last"))
            .reset_index(drop=True)
        )
        new_payload = dict(payload)
        new_payload["points"] = aggregated.to_dict("records")
        downsampled_payloads.append(new_payload)

    return downsampled_payloads


def create_candlestick_chart(
    dataframe,
    selected_symbol,
    selected_timeframe,
    title_suffix="",
    trades_dataframe=None,
    show_navigation_indicators: bool = False,
    navigation_reference_dataframe=None,
    overlay_indicators: list[dict] | None = None,
    chart_height: int = BACKTEST_DEFAULT_CHART_HEIGHT,
    layout_profile: str = "default",
):
    if dataframe.empty:
        return go.Figure()

    candles = dataframe.reset_index(drop=True).copy()
    candles["datetime"] = pd.to_datetime(candles["datetime"], utc=True, errors="coerce")
    candles = candles.dropna(subset=["datetime"]).reset_index(drop=True)
    if candles.empty:
        return go.Figure()

    candles["datetime"] = candles["datetime"].dt.tz_localize(None)
    candles = candles.sort_values("datetime").reset_index(drop=True)
    x_values = candles["datetime"]
    volume_colors = np.where(
        candles["close"] >= candles["open"], "rgba(56, 189, 248, 0.55)", "rgba(248, 113, 113, 0.55)"
    )

    def _fmt_datetime(value: object) -> str:
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return "-"
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    def _jitter_datetime_series(
        timestamp_series: pd.Series, max_offset_seconds: float = 30.0
    ) -> pd.Series:
        if timestamp_series.empty:
            return pd.Series([pd.NaT] * len(timestamp_series), index=timestamp_series.index)
        group_counts = timestamp_series.groupby(timestamp_series).transform("count")
        group_ranks = timestamp_series.groupby(timestamp_series).cumcount()
        offsets = (group_ranks - (group_counts - 1) / 2) / np.maximum(group_counts, 2)
        offsets = offsets * max_offset_seconds
        return pd.to_timedelta(offsets, unit="s")

    overlay_payloads = [payload for payload in (overlay_indicators or []) if isinstance(payload, dict)]
    non_price_panels: list[str] = []
    panel_to_row: dict[str, int] = {"price": 1}
    for payload in overlay_payloads:
        panel_name = str(payload.get("panel", "price")).strip().lower() or "price"
        if panel_name == "price":
            continue
        if panel_name not in non_price_panels:
            non_price_panels.append(panel_name)

    for index, panel_name in enumerate(non_price_panels, start=3):
        panel_to_row[panel_name] = index

    normalized_layout_profile = str(layout_profile).strip().lower()
    if normalized_layout_profile not in {"default", "fullscreen"}:
        normalized_layout_profile = "default"
    is_fullscreen_profile = normalized_layout_profile == "fullscreen"

    total_rows = 2 + len(non_price_panels)
    if total_rows == 2:
        row_heights = [0.82, 0.18] if is_fullscreen_profile else [0.77, 0.23]
    else:
        if is_fullscreen_profile:
            price_row_height = 0.74
            volume_row_height = 0.16
            min_extra_row_height = 0.04
        else:
            price_row_height = 0.68
            volume_row_height = 0.2
            min_extra_row_height = 0.05

        extra_row_height = (1.0 - price_row_height - volume_row_height) / max(1, len(non_price_panels))
        if extra_row_height <= 0:
            extra_row_height = min_extra_row_height
        row_heights = [price_row_height, volume_row_height] + [extra_row_height] * len(non_price_panels)

    try:
        resolved_chart_height = int(chart_height)
    except (TypeError, ValueError):
        resolved_chart_height = BACKTEST_DEFAULT_CHART_HEIGHT
    resolved_chart_height = max(360, resolved_chart_height)

    vertical_spacing = 0.028 if is_fullscreen_profile else 0.04

    figure = make_subplots(
        rows=total_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=vertical_spacing,
        row_heights=row_heights,
    )
    figure.add_trace(
        go.Candlestick(
            x=x_values,
            open=candles["open"],
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            name=selected_symbol,
            yaxis="y",
            increasing={"line": {"color": "#10b981", "width": 1.2}, "fillcolor": "#0b3f2e"},
            decreasing={"line": {"color": "#f43f5e", "width": 1.2}, "fillcolor": "#3b0b17"},
            showlegend=False,
            hovertemplate="O: %{open:.6f}<br>H: %{high:.6f}<br>L: %{low:.6f}<br>C: %{close:.6f}<extra></extra>",
        ),
        row=1,
        col=1,
    )
    volume_max = float(candles["volume"].max()) if not candles.empty else 0.0
    volume_range_top = max(volume_max * 1.2, 1.0)
    figure.add_trace(
        go.Bar(
            x=x_values,
            y=candles["volume"].fillna(0.0),
            marker_color=volume_colors,
            marker_opacity=0.62,
            name="Volume",
            showlegend=False,
            hovertemplate="Volume: %{y:,.0f}<extra></extra>",
        ),
        row=2,
        col=1,
    )

    if trades_dataframe is not None and not trades_dataframe.empty:
        entries = trades_dataframe.copy()
        entries["open_date"] = pd.to_datetime(entries["open_date"], utc=True, errors="coerce")
        entries["close_date"] = pd.to_datetime(entries["close_date"], utc=True, errors="coerce")
        entries["open_date"] = entries["open_date"].dt.tz_localize(None)
        entries["close_date"] = entries["close_date"].dt.tz_localize(None)
        entries = entries.dropna(subset=["open_date", "close_date"]).reset_index(drop=True)

        chart_min_time = x_values.min()
        chart_max_time = x_values.max()
        entries = entries[
            (entries["open_date"] <= chart_max_time) & (entries["close_date"] >= chart_min_time)
        ].copy()
        if not entries.empty:
            entries["open_x"] = entries["open_date"] + _jitter_datetime_series(entries["open_date"])
            entries["close_x"] = entries["close_date"] + _jitter_datetime_series(entries["close_date"])
            entries = entries.dropna(subset=["open_x", "close_x", "open_price", "close_price"])
        if not entries.empty:
            figure.add_trace(
                go.Scatter(
                    x=entries["open_x"],
                    y=entries["open_price"],
                    mode="markers",
                    name="Entry",
                    marker=dict(
                        symbol="triangle-up",
                        size=12,
                        color="#38bdf8",
                        line=dict(width=1.5, color="#0f172a"),
                    ),
                    text=[
                        f"Entry<br>{_fmt_datetime(row.open_date)}<br>Price: {row.open_price:.6f}"
                        for row in entries.itertuples()
                    ],
                    hovertemplate="%{text}<extra></extra>",
                ),
                row=1,
                col=1,
            )

            exits_positive = entries[entries["pnl_after_commission"] >= 0]
            if not exits_positive.empty:
                figure.add_trace(
                    go.Scatter(
                        x=exits_positive["close_x"],
                        y=exits_positive["close_price"],
                        mode="markers",
                        name="Exit +",
                        marker=dict(
                            symbol="triangle-down",
                            size=12,
                            color="#34d399",
                            line=dict(width=1.5, color="#0f172a"),
                        ),
                        text=[
                            f"Exit +<br>{_fmt_datetime(row.close_date)}<br>PnL: {row.pnl_after_commission:.2f}"
                            for row in exits_positive.itertuples()
                        ],
                        hovertemplate="%{text}<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )

            exits_negative = entries[entries["pnl_after_commission"] < 0]
            if not exits_negative.empty:
                figure.add_trace(
                    go.Scatter(
                        x=exits_negative["close_x"],
                        y=exits_negative["close_price"],
                        mode="markers",
                        name="Exit -",
                        marker=dict(
                            symbol="triangle-down",
                            size=12,
                            color="#f87171",
                            line=dict(width=1.5, color="#0f172a"),
                        ),
                        text=[
                            f"Exit -<br>{_fmt_datetime(row.close_date)}<br>PnL: {row.pnl_after_commission:.2f}"
                            for row in exits_negative.itertuples()
                        ],
                        hovertemplate="%{text}<extra></extra>",
                    ),
                    row=1,
                    col=1,
                )

            for is_profit, line_name, line_color in [
                (True, "Entry → Exit +", "#34d399"),
                (False, "Entry → Exit -", "#f87171"),
            ]:
                subset = entries[entries["pnl_after_commission"] >= 0] if is_profit else entries[
                    entries["pnl_after_commission"] < 0
                ]
                if subset.empty:
                    continue
                segment_x = []
                segment_y = []
                for row in subset.itertuples():
                    segment_x.extend([row.open_x, row.close_x, None])
                    segment_y.extend([row.open_price, row.close_price, None])
                figure.add_trace(
                    go.Scatter(
                        x=segment_x,
                        y=segment_y,
                        mode="lines",
                        name=line_name,
                        line=dict(color=line_color, width=1.25, dash="dot"),
                        hoverinfo="skip",
                        showlegend=True,
                    ),
                    row=1,
                    col=1,
                )

    if overlay_payloads:
        for payload in overlay_payloads:
            indicator_id = _indicator_payload_id(payload) or "indicator"
            if not indicator_id:
                continue

            indicator_dataframe = _points_to_indicator_df(payload.get("points", []))
            if indicator_dataframe.empty:
                continue

            panel_name = str(payload.get("panel", "price")).strip().lower() or "price"
            indicator_row = panel_to_row.get(panel_name, 3)
            if indicator_row > total_rows:
                indicator_row = total_rows

            line_color = str(payload.get("color", "#38bdf8"))
            line_width = float(payload.get("line_width", 1.2))
            line_style = str(payload.get("line_style", payload.get("line_dash", "solid")))
            if line_style not in {"solid", "dot", "dash", "dashdot", "longdash", "longdashdot"}:
                line_style = "solid"

            figure.add_trace(
                go.Scatter(
                    x=indicator_dataframe["datetime"],
                    y=indicator_dataframe["value"],
                    mode="lines",
                    name=str(payload.get("label", indicator_id)),
                    line=dict(color=line_color, width=line_width, dash=line_style),
                    connectgaps=False,
                    hovertemplate="Дата: %{x|%Y-%m-%d %H:%M:%S}<br>Значение: %{y:.6f}<extra></extra>",
                ),
                row=indicator_row,
                col=1,
            )

    title_text = f"Candlestick and volume chart | {selected_symbol} | {selected_timeframe}"
    if title_suffix:
        title_text = f"{title_text} | {title_suffix}"

    navigation_reference = candles.copy()
    if navigation_reference_dataframe is not None:
        reference_dataframe = pd.DataFrame(navigation_reference_dataframe).copy()
        if not reference_dataframe.empty and "datetime" in reference_dataframe.columns:
            reference_dataframe["datetime"] = pd.to_datetime(reference_dataframe["datetime"], utc=True, errors="coerce")
            reference_dataframe = reference_dataframe.dropna(subset=["datetime"]).copy()
            if (
                "open" in reference_dataframe.columns
                and "high" in reference_dataframe.columns
                and "low" in reference_dataframe.columns
                and "close" in reference_dataframe.columns
            ):
                reference_dataframe["datetime"] = reference_dataframe["datetime"].dt.tz_localize(None)
                reference_dataframe = reference_dataframe.sort_values("datetime").reset_index(drop=True)
                if not reference_dataframe.empty:
                    navigation_reference = reference_dataframe

    reference_low = pd.to_numeric(navigation_reference["low"], errors="coerce").min()
    reference_high = pd.to_numeric(navigation_reference["high"], errors="coerce").max()
    visible_low = pd.to_numeric(candles["low"], errors="coerce").min()
    visible_high = pd.to_numeric(candles["high"], errors="coerce").max()
    nav_reference_ok = all(
        pd.notna(v)
        for v in (reference_low, reference_high, visible_low, visible_high)
    )
    if nav_reference_ok:
        reference_span = float(reference_high - reference_low)
        if reference_span <= 0:
            reference_span = 1.0
            reference_low -= 0.5
            reference_high += 0.5

    right_margin = 42 if show_navigation_indicators else (20 if is_fullscreen_profile else 16)
    if show_navigation_indicators:
        bottom_margin = 76 if is_fullscreen_profile else 64
    else:
        bottom_margin = 36 if is_fullscreen_profile else 28
    top_margin = 52 if is_fullscreen_profile else 56

    figure.update_layout(
        title=title_text,
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=16, r=right_margin, t=top_margin, b=bottom_margin),
        hovermode="x unified",
        uirevision=f"market-data-chart-{normalized_layout_profile}",
        hoverlabel=dict(
            bgcolor="rgba(15, 23, 42, 0.95)",
            bordercolor="rgba(96, 165, 250, 0.45)",
            font=dict(color="#e5e7eb", size=12),
        ),
        dragmode="zoom",
        height=resolved_chart_height,
    )
    figure.update_xaxes(
        type="date",
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.10)",
        zeroline=False,
        fixedrange=False,
        rangeslider=dict(
            visible=show_navigation_indicators,
            bgcolor="rgba(96, 165, 250, 0.08)",
            bordercolor="rgba(96, 165, 250, 0.45)",
            borderwidth=1,
            thickness=0.05,
        ),
        tickformat="%Y-%m-%d %H:%M",
        row=1,
        col=1,
    )
    figure.update_xaxes(type="date", showgrid=False, zeroline=False, tickformat="%Y-%m-%d", row=2, col=1)
    for extra_row in range(3, total_rows + 1):
        figure.update_xaxes(
            type="date",
            showgrid=False,
            zeroline=False,
            tickformat="%Y-%m-%d",
            row=extra_row,
            col=1,
        )
    figure.update_yaxes(
        title_text="Price",
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.12)",
        zeroline=False,
        side="right",
        showticklabels=True,
        tickformat=".8f",
        fixedrange=not show_navigation_indicators,
        row=1,
        col=1,
    )
    figure.update_yaxes(
        title_text="Volume",
        showgrid=False,
        zeroline=False,
        side="right",
        title_standoff=0,
        range=[0, volume_range_top],
        fixedrange=True,
        row=2,
        col=1,
    )
    for panel_name, row in panel_to_row.items():
        if row <= 2:
            continue
        figure.update_yaxes(
            title_text=panel_name.title(),
            showgrid=True,
            gridcolor="rgba(148, 163, 184, 0.12)",
            zeroline=False,
            side="right",
            showticklabels=True,
            fixedrange=True,
            row=row,
            col=1,
        )

    for axis_row in range(1, total_rows + 1):
        figure.update_xaxes(fixedrange=False, row=axis_row, col=1)

    if show_navigation_indicators:
        range_start = candles["datetime"].min()
        range_end = candles["datetime"].max()
        figure.add_annotation(
            x=0.5,
            y=-0.08,
            xref="paper",
            yref="paper",
            text=f"Окно графика: {range_start.strftime('%Y-%m-%d %H:%M')} — {range_end.strftime('%Y-%m-%d %H:%M')}",
            showarrow=False,
            align="center",
            font=dict(size=10, color="rgba(226, 232, 240, 0.85)"),
            bgcolor="rgba(15, 23, 42, 0.75)",
            bordercolor="rgba(96, 165, 250, 0.35)",
            borderwidth=1,
        )
        figure.add_annotation(
            x=0.5,
            y=-0.13,
            xref="paper",
            yref="paper",
            text="◄ Влево / вправо ►",
            showarrow=False,
            align="center",
            font=dict(size=10, color="rgba(148, 163, 184, 0.9)"),
        )

    if show_navigation_indicators and nav_reference_ok:
        price_axis_domain = (0.24, 0.95)
        if getattr(figure.layout, "yaxis", None) is not None and getattr(figure.layout.yaxis, "domain", None) is not None:
            try:
                axis_domain = tuple(figure.layout.yaxis.domain)
                if len(axis_domain) == 2:
                    price_axis_domain = (float(axis_domain[0]), float(axis_domain[1]))
            except Exception:
                price_axis_domain = (0.24, 0.95)

        track_bottom = max(0.01, min(0.95, price_axis_domain[0] + 0.015))
        track_top = max(track_bottom + 0.1, min(0.99, price_axis_domain[1] - 0.015))
        track_span = max(0.1, track_top - track_bottom)

        figure.add_shape(
            type="rect",
            xref="paper",
            yref="paper",
            x0=0.979,
            x1=0.992,
            y0=track_bottom,
            y1=track_top,
            layer="below",
            line=dict(color="rgba(148, 163, 184, 0.30)", width=1),
            fillcolor="rgba(148, 163, 184, 0.10)",
        )
        visible_mid = float((visible_low + visible_high) / 2.0)
        normalized_position = (visible_mid - float(reference_low)) / float(reference_span)
        normalized_position = min(1.0, max(0.0, normalized_position))
        visible_span = float(visible_high - visible_low)
        handle_height_ratio = (visible_span / float(reference_span))
        handle_height = max(track_span * 0.12, min(track_span * 0.9, handle_height_ratio * track_span))
        handle_center = track_bottom + normalized_position * (track_top - track_bottom)
        handle_half = handle_height / 2
        handle_bottom = max(track_bottom, min(track_top - handle_height, handle_center - handle_half))
        handle_top = min(track_top, max(track_bottom + handle_height, handle_center + handle_half))

        figure.add_shape(
            type="rect",
            xref="paper",
            yref="paper",
            x0=0.979,
            x1=0.992,
            y0=handle_bottom,
            y1=handle_top,
            line=dict(color="rgba(96, 165, 250, 0.9)", width=1),
            fillcolor="rgba(96, 165, 250, 0.24)",
        )
        figure.add_annotation(
            x=0.977,
            y=min(0.995, track_top + 0.016),
            xref="paper",
            yref="paper",
            text="▲",
            showarrow=False,
            font=dict(size=12, color="rgba(148, 163, 184, 0.9)"),
        )
        figure.add_annotation(
            x=0.977,
            y=max(0.005, track_bottom - 0.016),
            xref="paper",
            yref="paper",
            text="▼",
            showarrow=False,
            font=dict(size=12, color="rgba(148, 163, 184, 0.9)"),
        )
        figure.add_annotation(
            x=0.977,
            y=(track_top + track_bottom) / 2,
            xref="paper",
            yref="paper",
            text="Вверх / вниз",
            showarrow=False,
            font=dict(size=10, color="rgba(148, 163, 184, 0.85)"),
        )
    return figure
def create_equity_curve_chart(equity_dataframe, title_suffix: str = ""):  # Создаем функцию, которая строит линейный график изменения капитала.
    if equity_dataframe.empty:
        return go.Figure()

    normalized_equity_dataframe = equity_dataframe.sort_values("datetime").reset_index(drop=True)
    figure = go.Figure()  # Создаем пустую фигуру Plotly.
    figure.add_trace(  # Добавляем на график одну линию капитала.
        go.Scatter(  # Используем линейный график для отображения equity curve.
            x=normalized_equity_dataframe["datetime"],  # Передаем даты по горизонтальной оси.
            y=normalized_equity_dataframe["equity"],  # Передаем значения капитала по вертикальной оси.
            mode="lines",  # Просим Plotly рисовать именно линию.
            name="Капитал",  # Задаем подпись линии графика.
            line={"color": "#2E9AFE", "width": 3},  # Делаем линию капитала ярко-синей и чуть толще стандартной.
            fill="tozeroy",  # Добавляем заливку под линией графика.
            fillcolor="rgba(46, 154, 254, 0.1)",  # Делаем мягкую полупрозрачную синюю заливку под линией.
            hovertemplate="Дата: %{x|%Y-%m-%d %H:%M:%S}<br>Капитал: %{y:,.2f}<extra></extra>",
        )  # Завершаем описание линейного графика.
    )  # Завершаем добавление линии в фигуру.
    chart_title = "📊 График капитала (Equity Curve)"
    if title_suffix:
        chart_title = f"{chart_title} | {title_suffix}"
    figure.update_layout(  # Настраиваем внешний вид графика капитала.
        title=chart_title,
        xaxis_title="Дата и время",  # Подписываем горизонтальную ось.
        yaxis_title="Капитал, USDT",  # Подписываем вертикальную ось.
        height=450,  # Делаем график достаточно высоким для удобного просмотра.
        template="plotly_dark",  # Добавляем тёмную тему для единообразия.
        paper_bgcolor="rgba(0,0,0,0)",  # Делаем фон всей фигуры прозрачным.
        plot_bgcolor="rgba(0,0,0,0)",  # Делаем фон области построения прозрачным.
        margin=dict(l=16, r=16, t=56, b=28),
        hovermode="x unified",
    )  # Завершаем настройку внешнего вида графика.
    figure.update_xaxes(
        type="date",
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.10)",
        zeroline=False,
        tickformat="%Y-%m-%d %H:%M",
        fixedrange=False,
        rangeslider_visible=False,
    )
    figure.update_yaxes(
        title_text="Капитал, USDT",
        showgrid=True,
        gridcolor="rgba(148, 163, 184, 0.12)",
        zeroline=False,
        fixedrange=True,
    )
    return figure  # Возвращаем готовый график наружу.


def show_data_summary(dataframe):  # Создаем функцию, которая показывает краткую сводку по данным.
    first_date = dataframe["datetime"].min()  # Находим самую раннюю дату в таблице.
    last_date = dataframe["datetime"].max()  # Находим самую позднюю дату в таблице.
    col_1, col_2, col_3 = st.columns(3)  # Создаем три колонки для компактного вывода основных показателей.
    col_1.metric("Количество строк", f"{len(dataframe)}")  # Показываем общее количество строк в файле.
    col_2.metric("Первая свеча", first_date.strftime("%Y-%m-%d %H:%M"))  # Показываем дату первой свечи.
    col_3.metric("Последняя свеча", last_date.strftime("%Y-%m-%d %H:%M"))  # Показываем дату последней свечи.


def filter_data_by_date_range(
    dataframe: pd.DataFrame, start_date: date | None, end_date: date | None
) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    if start_date is None or end_date is None:
        return dataframe

    start_time = pd.Timestamp(start_date)
    end_time = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    return dataframe[(dataframe["datetime"] >= start_time) & (dataframe["datetime"] < end_time)].copy()


def filter_trades_by_date_range(
    trades_dataframe: pd.DataFrame, start_date: date | None, end_date: date | None
) -> pd.DataFrame:
    if trades_dataframe.empty:
        return trades_dataframe
    if start_date is None or end_date is None:
        return trades_dataframe.copy()

    start_time = pd.Timestamp(start_date)
    end_time = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    return trades_dataframe[
        (trades_dataframe["open_date"] < end_time) & (trades_dataframe["close_date"] >= start_time)
    ].copy()

def handle_data_button(selected_symbol, selected_timeframe, selected_start_date, selected_end_date):  # Создаем функцию, которая обрабатывает нажатие кнопки загрузки данных.
    selected_data_file = get_selected_data_file(selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)
    load_column, rebuild_column = st.columns([0.74, 0.26], vertical_alignment="bottom")
    with load_column:
        load_clicked = st.button("⬇️ Загрузить данные с Binance", type="primary", width="stretch")  # Рисуем большую кнопку, по которой пользователь запускает загрузку выбранных параметров.
    with rebuild_column:
        rebuild_clicked = st.button("♻️ Пересобрать кэш", width="stretch")  # Добавляем явную кнопку принудительной пересборки кэша под выбранный диапазон.

    if not load_clicked and not rebuild_clicked:
        return

    if selected_start_date > selected_end_date:  # Проверяем, что дата начала периода не позже даты окончания.
        st.error("Дата начала периода не может быть позже даты окончания.")  # Показываем понятную ошибку, если диапазон выбран неверно.
        return  # Прерываем загрузку, пока пользователь не исправит диапазон.

    if rebuild_clicked and selected_data_file.exists():
        try:
            selected_data_file.unlink()
        except Exception as exc:
            show_classified_error("Не удалось очистить кэш перед пересборкой", exc)
            return

    try:
        with st.spinner("Скачиваю данные с Binance. Это может занять немного времени..."):  # Показываем анимацию ожидания, пока работает загрузчик.
            downloaded_dataframe = run_downloader(
                symbol=selected_symbol,
                timeframe=selected_timeframe,
                start_date=selected_start_date,
                end_date=selected_end_date,
                output_file=selected_data_file,
            )  # Передаем выбранную пару, таймфрейм и диапазон дат в функцию скачивания.
    except Exception as exc:
        show_classified_error("Загрузка данных не выполнена", exc)
        return

    loaded_rows = len(downloaded_dataframe) if isinstance(downloaded_dataframe, pd.DataFrame) else 0
    action_text = "Пересборка и загрузка завершены" if rebuild_clicked else "Загрузка завершена"
    st.success(
        f"{action_text}. Данные {selected_symbol} с таймфреймом {selected_timeframe} за период с "
        f"{selected_start_date.strftime('%Y-%m-%d')} по {selected_end_date.strftime('%Y-%m-%d')} готовы к анализу "
        f"(строк: {loaded_rows:,})."
    )


def show_market_data_tab(selected_symbol, selected_timeframe, selected_start_date, selected_end_date):  # Создаем функцию, которая выводит вкладку с загрузкой и просмотром данных.
    st.caption(f"Сейчас в интерфейсе выбраны: {selected_symbol} | {selected_timeframe} | период с {selected_start_date.strftime('%Y-%m-%d')} по {selected_end_date.strftime('%Y-%m-%d')}.")  # Показываем пользователю, какие параметры сейчас выбраны в боковой панели.
    handle_data_button(selected_symbol, selected_timeframe, selected_start_date, selected_end_date)  # Показываем кнопку загрузки данных внутри вкладки просмотра рынка.
    selected_data_file = get_selected_data_file(selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)
    if not selected_data_file.exists():  # Проверяем, существует ли CSV для текущей пары и таймфрейма.
        st.warning(f"Для {selected_symbol} / {selected_timeframe} пока нет загруженных данных. Выберите даты и нажмите кнопку загрузки.")  # Показываем понятное предупреждение, если файл еще не создан.
        return  # Останавливаем дальнейший вывод, потому что показывать пока нечего.
    try:
        data_context = get_market_data_context(
            file_path=selected_data_file,
            symbol=selected_symbol,
            timeframe=selected_timeframe,
            mode="light",
        )
        full_dataframe = load_data_from_csv(selected_data_file)
        dataframe = filter_data_by_date_range(full_dataframe, selected_start_date, selected_end_date)
    except Exception as exc:
        show_classified_error("Не удалось прочитать кэш данных", exc)
        return
    if data_context:
        context_version = data_context.get("context_version", "")
        rows = data_context.get("rows", 0)
        checksum = str(data_context.get("checksum", "") or "")
        if checksum:
            checksum = checksum[:12]
        context_mode = data_context.get("mode", "light")
        st.caption(f"Кэш: version={context_version} | mode={context_mode} | rows={rows:,} | checksum={checksum}")

        context_start = _timestamp_ms_to_date(data_context.get("first_timestamp"))
        context_end = _timestamp_ms_to_date(data_context.get("last_timestamp"))
        if context_start is not None and context_end is not None:
            if selected_start_date < context_start or selected_end_date > context_end:
                st.warning(
                    f"Выбранный диапазон выходит за границы кэша ({context_start} — {context_end}). "
                    "Нажмите загрузку или пересборку кэша."
                )

    if dataframe.empty:
        st.warning(f"No data available for selected period {selected_start_date} to {selected_end_date}.")
        return
    show_data_summary(dataframe)  # Показываем краткую сводку по загруженным данным.
    st.subheader("Свечной график")  # Добавляем подзаголовок перед графиком.
    chart_dataframe = downsample_for_chart(dataframe)  # Ограничиваем число свечей для стабильного и плотного отображения.
    if len(chart_dataframe) < len(dataframe):  # Если данные режутся для графика.
        st.caption(f"Graph data is downsampled to {len(chart_dataframe):,} candles for speed.")  # Сообщаем пользователю, сколько свечей использовано.
    chart = create_candlestick_chart(chart_dataframe, selected_symbol, selected_timeframe)  # Строим свечной график на основе таблицы и текущих настроек в боковой панели.
    plotly_chart_with_wheel(chart)  # Показываем готовый график в приложении.


def get_strategy_parameter_defaults(selected_strategy_class):  # Extract strategy params defined in class metadata.
    raw_params = getattr(selected_strategy_class, "params", ())  # Read raw Backtrader params metadata.
    parameter_defaults = {}  # Build stable default values for UI controls.

    raw_pairs = []
    if isinstance(raw_params, dict):
        raw_pairs = list(raw_params.items())
    elif isinstance(raw_params, type):
        _getitems = getattr(raw_params, "_getitems", None)
        if callable(_getitems):
            try:
                raw_pairs = list(_getitems())
            except Exception:
                raw_pairs = []
        if not raw_pairs:
            fallback = getattr(raw_params, "__dict__", {}).get("params", ())
            if fallback:
                raw_pairs = list(fallback)
    elif hasattr(raw_params, "__iter__") and not isinstance(raw_params, (str, bytes)):
        raw_pairs = list(raw_params)

    for item in raw_pairs:
        if item is None:
            continue
        name = None
        value = None

        if isinstance(item, dict):
            for param_name, param_value in item.items():
                if param_name is not None:
                    parameter_defaults[str(param_name)] = param_value
            continue

        if isinstance(item, (list, tuple)) and len(item) >= 2:
            name, value = item[0], item[1]
        elif hasattr(item, "name") and hasattr(item, "default"):
            name, value = item.name, item.default
        elif hasattr(item, "get") and callable(item.get):
            name = item.get("name", item.get("key"))
            value = item.get("default", item.get("value"))

        if name is None:
            continue
        parameter_defaults[str(name)] = value
    parameter_defaults.pop("commission", None)  # Drop internal commission from user-editable fields.
    return parameter_defaults  # Return only strategy defaults with explicit values.


def get_strategy_parameter_specs(selected_strategy_class) -> dict[str, dict[str, Any]]:
    raw_specs = getattr(selected_strategy_class, "PARAMETER_SPECS", {})
    if not isinstance(raw_specs, dict):
        return {}

    specs: dict[str, dict[str, Any]] = {}
    for parameter_name, spec in raw_specs.items():
        if isinstance(parameter_name, str) and isinstance(spec, dict):
            specs[parameter_name] = spec
    return specs


def _get_numeric_param_limits(parameter_value: Any, parameter_spec: dict[str, Any] | None) -> tuple[float | int | None, float | int | None, float | int | None]:
    spec = parameter_spec or {}

    if isinstance(parameter_value, int) and not isinstance(parameter_value, bool):
        minimum = int(spec.get("min", 1))
        maximum = int(spec.get("max", max(minimum, parameter_value * 2)))
        step = int(spec.get("step", 1))
        return minimum, maximum, step

    minimum = float(spec.get("min", 0.0))
    maximum = float(spec.get("max", max(minimum + 1.0, float(parameter_value) + 1.0)))
    step = float(spec.get("step", 0.1))
    return minimum, maximum, step


def build_number_input_for_parameter(parameter_name, parameter_value, widget_key, parameter_spec=None):  # Создаем вспомогательную функцию, которая рисует number_input для одного параметра стратегии.
    display_name = get_parameter_display_name(parameter_name, parameter_specs={parameter_name: parameter_spec or {}})
    if isinstance(parameter_value, bool):
        choices = parameter_spec.get("choices") if isinstance(parameter_spec, dict) else None
        options = choices if isinstance(choices, (list, tuple)) and choices else [False, True]
        return bool(st.selectbox(display_name, options=options, index=int(bool(parameter_value)), key=widget_key))

    minimum_value, maximum_value, step = _get_numeric_param_limits(parameter_value=parameter_value, parameter_spec=parameter_spec)
    if minimum_value is None or maximum_value is None:
        minimum_value = None
        maximum_value = None

    normalized_value = parameter_value
    if minimum_value is not None and normalized_value < minimum_value:
        normalized_value = minimum_value
    if maximum_value is not None and normalized_value > maximum_value:
        normalized_value = maximum_value

    if isinstance(parameter_value, int) and minimum_value is not None and maximum_value is not None and int(minimum_value) == minimum_value and int(maximum_value) == maximum_value and int(step) == step:
        input_value = st.number_input(
            display_name,
            value=int(normalized_value),
            min_value=int(minimum_value),
            max_value=int(maximum_value),
            step=int(step),
            key=widget_key,
        )  # Рисуем number_input для целого числа с шагом 1.
        return int(input_value)  # Возвращаем введенное число как целое.

    input_value = st.number_input(
        display_name,
        value=float(normalized_value),
        min_value=float(minimum_value) if minimum_value is not None else None,
        max_value=float(maximum_value) if maximum_value is not None else None,
        step=float(step),
        key=widget_key,
    )  # Рисуем number_input для нецелого числа с шагом 0.1.
    return float(input_value)  # Возвращаем введенное число с плавающей точкой.


def _build_float_range_values(value_from: float, value_to: float, step: float) -> list[float]:
    safe_step = abs(float(step))
    if safe_step <= 0.0:
        safe_step = 0.1
    if value_to < value_from:
        return []

    values: list[float] = []
    current_value = float(value_from)
    epsilon = safe_step / 1000.0
    max_iterations = 200_000
    while current_value <= float(value_to) + epsilon and len(values) < max_iterations:
        values.append(round(float(current_value), 10))
        current_value += safe_step
    rounded_to = round(float(value_to), 10)
    if values and abs(values[-1] - rounded_to) > epsilon:
        values.append(rounded_to)
    return values


def build_number_range_for_parameter(parameter_name, parameter_value, widget_key, parameter_spec=None):  # Создаем числовой ввод диапазона "от/до" для оптимизации.
    param_spec = parameter_spec or {}
    display_name = get_parameter_display_name(parameter_name, parameter_specs={parameter_name: param_spec})

    if isinstance(parameter_value, bool):
        return [bool(parameter_value)], {"от": bool(parameter_value), "до": bool(parameter_value)}

    minimum_value, maximum_value, step = _get_numeric_param_limits(parameter_value=parameter_value, parameter_spec=param_spec)
    if minimum_value is None or maximum_value is None:
        minimum_value = 0
        maximum_value = 1

    is_integer_param = (
        isinstance(parameter_value, int)
        and not isinstance(parameter_value, bool)
        and int(minimum_value) == minimum_value
        and int(maximum_value) == maximum_value
        and int(step) == step
    )

    if is_integer_param:
        default_value = int(parameter_value)
        default_value = max(int(minimum_value), min(int(maximum_value), default_value))
        default_step = max(1, int(step))
        col_from, col_to, col_step = st.columns(3)
        with col_from:
            value_from = int(
                st.number_input(
                    f"{display_name} от",
                    value=int(default_value),
                    min_value=int(minimum_value),
                    max_value=int(maximum_value),
                    step=default_step,
                    key=f"{widget_key}_from",
                )
            )
        with col_to:
            value_to = int(
                st.number_input(
                    f"{display_name} до",
                    value=int(default_value),
                    min_value=int(minimum_value),
                    max_value=int(maximum_value),
                    step=default_step,
                    key=f"{widget_key}_to",
                )
            )
        with col_step:
            value_step = int(
                st.number_input(
                    f"{display_name} шаг",
                    value=int(default_step),
                    min_value=1,
                    step=1,
                    key=f"{widget_key}_step",
                )
            )

        normalized_from = min(value_from, value_to)
        normalized_to = max(value_from, value_to)
        normalized_step = max(1, int(value_step))
        optimization_values = list(range(normalized_from, normalized_to + 1, normalized_step))
        if optimization_values and optimization_values[-1] != normalized_to:
            optimization_values.append(normalized_to)
        return optimization_values, {"от": normalized_from, "до": normalized_to, "шаг": normalized_step}

    default_value = float(parameter_value)
    default_value = max(float(minimum_value), min(float(maximum_value), default_value))
    default_step = float(step) if float(step) > 0.0 else 0.1
    col_from, col_to, col_step = st.columns(3)
    with col_from:
        value_from = float(
            st.number_input(
                f"{display_name} от",
                value=float(default_value),
                min_value=float(minimum_value),
                max_value=float(maximum_value),
                step=float(default_step),
                key=f"{widget_key}_from",
                format="%.4f",
            )
        )
    with col_to:
        value_to = float(
            st.number_input(
                f"{display_name} до",
                value=float(default_value),
                min_value=float(minimum_value),
                max_value=float(maximum_value),
                step=float(default_step),
                key=f"{widget_key}_to",
                format="%.4f",
            )
        )
    with col_step:
        value_step = float(
            st.number_input(
                f"{display_name} шаг",
                value=float(default_step),
                min_value=0.0001,
                step=float(default_step),
                key=f"{widget_key}_step",
                format="%.4f",
            )
        )

    normalized_from = min(value_from, value_to)
    normalized_to = max(value_from, value_to)
    safe_step = float(value_step) if float(value_step) > 0.0 else float(default_step)
    optimization_values = _build_float_range_values(normalized_from, normalized_to, step=safe_step)
    return optimization_values, {"от": normalized_from, "до": normalized_to, "шаг": round(float(safe_step), 10)}


def render_strategy_selector(available_strategies, label, key):  # Создаем функцию, которая рисует выпадающий список доступных стратегий.
    strategy_names = list(available_strategies.keys())  # Получаем список имен всех найденных стратегий для выпадающего списка.
    selected_strategy_name = st.selectbox(label, strategy_names, index=0, key=key)  # Создаем выпадающий список выбора стратегии с уникальным ключом.
    selected_strategy_class = available_strategies[selected_strategy_name]  # Получаем класс стратегии по выбранному имени.
    return selected_strategy_name, selected_strategy_class  # Возвращаем выбранное имя стратегии и сам класс наружу.


def _normalize_numeric_value(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    try:
        normalized = float(value)
    except Exception:
        return None
    return normalized


def _normalize_range_values_for_validation(range_values) -> list[Any]:
    if isinstance(range_values, range):
        return list(range_values)
    if isinstance(range_values, (list, tuple, set)):
        return list(range_values)
    return [range_values]


def _validate_parameter_dependency(
    current_name,
    current_values,
    related_name,
    related_values,
    relation: str,
    *,
    is_range: bool,
    parameter_specs: dict[str, dict[str, Any]] | None = None,
) -> str | None:
    if related_name is None:
        return None
    if current_name == related_name:
        return None
    if not related_values:
        return None
    current_display_name = get_parameter_display_name(str(current_name), parameter_specs=parameter_specs)
    related_display_name = get_parameter_display_name(str(related_name), parameter_specs=parameter_specs)

    if is_range:
        if relation == "lt" and min(current_values) >= max(related_values):
            return (
                f"Параметры {current_display_name} и {related_display_name} заданы некорректно: "
                f"необходимо, чтобы была хотя бы часть комбинаций с {current_display_name} < {related_display_name}."
            )
        if relation == "gt" and max(current_values) <= min(related_values):
            return (
                f"Параметры {current_display_name} и {related_display_name} заданы некорректно: "
                f"необходимо, чтобы была хотя бы часть комбинаций с {current_display_name} > {related_display_name}."
            )
    else:
        normalized_current = _normalize_numeric_value(current_values)
        normalized_related = _normalize_numeric_value(related_values)
        if normalized_current is None or normalized_related is None:
            return None
        if relation == "lt" and normalized_current >= normalized_related:
            return f"Параметр {current_display_name} должен быть меньше {related_display_name}."
        if relation == "gt" and normalized_current <= normalized_related:
            return f"Параметр {current_display_name} должен быть больше {related_display_name}."
    return None


def render_backtest_controls(selected_strategy_class, selected_strategy_name, initial_params: dict[str, Any] | None = None):  # Создаем функцию, которая динамически рисует поля настройки стратегии внутри вкладки бектеста.
    parameter_defaults = get_strategy_parameter_defaults(selected_strategy_class=selected_strategy_class)  # Получаем словарь параметров выбранной стратегии, кроме commission.
    if isinstance(initial_params, dict) and initial_params:
        parameter_defaults = merge_params_with_defaults(parameter_defaults, initial_params)
    parameter_specs = get_strategy_parameter_specs(selected_strategy_class=selected_strategy_class)
    strategy_kwargs = {}  # Создаем пустой словарь, куда будем складывать введенные пользователем значения параметров.
    if not parameter_defaults:  # Проверяем, есть ли у стратегии параметры для ручной настройки.
        st.info("У выбранной стратегии нет пользовательских параметров для настройки через number_input.")  # Показываем понятное сообщение, если параметров нет.
        return strategy_kwargs  # Возвращаем пустой словарь параметров наружу.
    for parameter_name, parameter_value in parameter_defaults.items():  # Проходим по всем параметрам выбранной стратегии.
        widget_key = f"backtest_{selected_strategy_name}_{parameter_name}"  # Создаем уникальный ключ виджета, чтобы Streamlit не путал поля разных стратегий.
        strategy_kwargs[parameter_name] = build_number_input_for_parameter(
            parameter_name=parameter_name,
            parameter_value=parameter_value,
            widget_key=widget_key,
            parameter_spec=parameter_specs.get(parameter_name, {}),
        )  # Рисуем number_input для текущего параметра и сохраняем результат в словарь.
    return strategy_kwargs  # Возвращаем словарь введенных пользователем параметров стратегии наружу.


def render_optimization_controls(selected_strategy_class, selected_strategy_name, initial_params: dict[str, Any] | None = None):  # Создаем функцию, которая динамически рисует числовые диапазоны для оптимизации выбранной стратегии.
    parameter_defaults = get_strategy_parameter_defaults(selected_strategy_class=selected_strategy_class)  # Получаем словарь параметров выбранной стратегии, кроме commission.
    if isinstance(initial_params, dict) and initial_params:
        parameter_defaults = merge_params_with_defaults(parameter_defaults, initial_params)
    parameter_specs = get_strategy_parameter_specs(selected_strategy_class=selected_strategy_class)
    strategy_param_ranges = {}  # Создаем пустой словарь, куда будем складывать диапазоны параметров для оптимизации.
    display_ranges = {}  # Создаем словарь, чтобы сохранить пользовательские диапазоны "от/до" для вывода в интерфейсе.
    if not parameter_defaults:  # Проверяем, есть ли у стратегии параметры для оптимизации.
        st.info("У выбранной стратегии нет пользовательских параметров для оптимизации.")  # Показываем понятное сообщение, если параметров нет.
        return strategy_param_ranges, display_ranges  # Возвращаем пустые словари наружу.
    optimization_whitelist = get_strategy_optimization_whitelist(selected_strategy_class=selected_strategy_class)

    allowed_parameters: list[tuple[str, Any]] = []
    for parameter_name, parameter_value in parameter_defaults.items():
        parameter_spec = parameter_specs.get(parameter_name, {})
        if is_parameter_allowed_for_optimization(
            parameter_name=parameter_name,
            parameter_spec=parameter_spec,
            optimization_whitelist=optimization_whitelist,
        ):
            allowed_parameters.append((parameter_name, parameter_value))

    if not allowed_parameters:
        st.info("Для выбранной стратегии не найдено параметров групп: индикаторы, усреднение, тейк-профит, стоп-лосс.")
        return strategy_param_ranges, display_ranges

    st.caption("Введите диапазон вручную: укажите `от`, `до` и `шаг` для каждого параметра.")
    for parameter_name, parameter_value in allowed_parameters:  # Проходим по отфильтрованному списку параметров оптимизации.
        widget_key = f"optimization_{selected_strategy_name}_{parameter_name}"  # Создаем уникальный ключ инпута, чтобы Streamlit не путал диапазоны разных стратегий.
        optimization_values, typed_range = build_number_range_for_parameter(
            parameter_name=parameter_name,
            parameter_value=parameter_value,
            widget_key=widget_key,
            parameter_spec=parameter_specs.get(parameter_name, {}),
        )  # Рисуем поля "от/до" для текущего параметра и получаем значения для оптимизации.
        strategy_param_ranges[parameter_name] = optimization_values  # Сохраняем подготовленный диапазон параметра для передачи в движок оптимизации.
        display_ranges[parameter_name] = typed_range  # Сохраняем диапазон "от/до" для отображения пользователю.
    return strategy_param_ranges, display_ranges  # Возвращаем словарь диапазонов параметров и словарь отображаемых диапазонов наружу.


def validate_strategy_kwargs(strategy_kwargs, selected_strategy_class=None):  # Создаем функцию, которая выполняет валидацию параметров стратегии перед запуском бектеста.
    parameter_specs = get_strategy_parameter_specs(selected_strategy_class) if selected_strategy_class is not None else {}

    for parameter_name, parameter_value in strategy_kwargs.items():
        spec = parameter_specs.get(parameter_name, {})
        parameter_display_name = get_parameter_display_name(parameter_name, parameter_specs=parameter_specs)
        if isinstance(parameter_value, bool):
            allowed = spec.get("choices") if isinstance(spec, dict) else None
            if isinstance(allowed, (list, tuple)) and allowed and parameter_value not in allowed:
                return f"Значение '{parameter_display_name}' должно быть в списке {list(allowed)}."
            continue

        current_value = _normalize_numeric_value(parameter_value)
        if current_value is None:
            return f"Параметр '{parameter_display_name}' должен быть числом."

        spec_type = str(spec.get("type", "")) if isinstance(spec, dict) else ""
        if spec_type == "int" and current_value != int(current_value):
            return f"Параметр '{parameter_display_name}' должен быть целым числом."

        if isinstance(spec, dict):
            minimum = spec.get("min")
            maximum = spec.get("max")
            if minimum is not None and current_value < minimum:
                return f"Параметр '{parameter_display_name}' должен быть >= {minimum}."
            if maximum is not None and current_value > maximum:
                return f"Параметр '{parameter_display_name}' должен быть <= {maximum}."
            if minimum is not None and maximum is not None and minimum >= maximum:
                return f"Неверная граница для '{parameter_display_name}': min должен быть меньше max."

    for parameter_name, spec in parameter_specs.items():
        if not isinstance(spec, dict):
            continue
        current_value = strategy_kwargs.get(parameter_name)
        if current_value is None:
            continue
        for relation in ("lt", "gt"):
            related_name = spec.get(relation)
            if not isinstance(related_name, str):
                continue
            related_value = strategy_kwargs.get(related_name)
            validation_message = _validate_parameter_dependency(
                current_name=parameter_name,
                current_values=current_value,
                related_name=related_name,
                related_values=related_value,
                relation=relation,
                is_range=False,
                parameter_specs=parameter_specs,
            )
            if validation_message is not None:
                return validation_message

    return None  # Возвращаем None, если ошибок в параметрах не найдено.


def validate_strategy_param_ranges(strategy_param_ranges, selected_strategy_class=None):  # Создаем функцию, которая выполняет валидацию диапазонов параметров стратегии перед оптимизацией.
    parameter_specs = get_strategy_parameter_specs(selected_strategy_class) if selected_strategy_class is not None else {}
    normalized_ranges: dict[str, list[Any]] = {}

    for parameter_name, parameter_range in strategy_param_ranges.items():
        parameter_display_name = get_parameter_display_name(parameter_name, parameter_specs=parameter_specs)
        values = _normalize_range_values_for_validation(parameter_range)
        if not values:
            return f"Диапазон параметра '{parameter_display_name}' пустой."

        spec = parameter_specs.get(parameter_name, {})
        for value in values:
            if isinstance(value, bool):
                allowed = spec.get("choices") if isinstance(spec, dict) else None
                if isinstance(allowed, (list, tuple)) and allowed and value not in allowed:
                    return f"Значения параметра '{parameter_display_name}' должны быть в списке {list(allowed)}."
                continue

            current_value = _normalize_numeric_value(value)
            if current_value is None:
                return f"Значения параметра '{parameter_display_name}' должны быть числами."

            if isinstance(spec, dict):
                minimum = spec.get("min")
                maximum = spec.get("max")
                if minimum is not None and current_value < minimum:
                    return f"Параметр '{parameter_display_name}' может иметь значения только >= {minimum}."
                if maximum is not None and current_value > maximum:
                    return f"Параметр '{parameter_display_name}' может иметь значения только <= {maximum}."

        normalized_ranges[parameter_name] = values

    for parameter_name, spec in parameter_specs.items():
        if not isinstance(spec, dict):
            continue
        current_values = normalized_ranges.get(parameter_name)
        if not current_values:
            continue
        for relation in ("lt", "gt"):
            related_name = spec.get(relation)
            if not isinstance(related_name, str):
                continue
            related_values = normalized_ranges.get(related_name)
            if not related_values:
                continue
            validation_message = _validate_parameter_dependency(
                current_name=parameter_name,
                current_values=current_values,
                related_name=related_name,
                related_values=related_values,
                relation=relation,
                is_range=True,
                parameter_specs=parameter_specs,
            )
            if validation_message is not None:
                return validation_message

    return None  # Возвращаем None, если ошибок в диапазонах не найдено.


def build_run_context(
    selected_data_file: Path,
    selected_symbol: str,
    selected_timeframe: str,
    selected_start_date: date | None = None,
    selected_end_date: date | None = None,
) -> dict[str, Any]:
    return {
        "run_id": uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "symbol": selected_symbol,
        "timeframe": selected_timeframe,
        "start_date": selected_start_date.isoformat() if selected_start_date is not None else None,
        "end_date": selected_end_date.isoformat() if selected_end_date is not None else None,
        "data_file": str(selected_data_file),
        "data_context": get_market_data_context(
            file_path=selected_data_file,
            symbol=selected_symbol,
            timeframe=selected_timeframe,
            mode="full",
        ),
    }


def save_backtest_results(  # Сохраняем результаты последнего бектеста в state вместе с мета-информацией для графика.
    starting_balance,
    final_balance,
    trades_log,
    equity_curve,
    strategy_indicators,
    strategy_name,
    strategy_kwargs,
    selected_symbol: str = "",
    selected_timeframe: str = "",
    selected_start_date: date | None = None,
    selected_end_date: date | None = None,
    run_context: dict[str, Any] | None = None,
    sampling_metadata: dict[str, Any] | None = None,
):  # Добавлены поля symbol/timeframe для последующего свечного графика с оверлеями.
    normalized_context = dict(run_context or {})
    normalized_context.setdefault("run_id", uuid4().hex)
    normalized_context.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    st.session_state[BACKTEST_RESULTS_KEY] = {  # Сохраняем словарь с полным набором результатов бектеста.
        "starting_balance": starting_balance,  # Запоминаем стартовый капитал.
        "final_balance": final_balance,  # Запоминаем итоговый капитал.
        "trades_log": trades_log,  # Запоминаем список закрытых сделок.
        "equity_curve": equity_curve,  # Запоминаем историю изменения капитала.
        "strategy_name": strategy_name,  # Запоминаем имя стратегии, по которой считался результат.
        "strategy_kwargs": strategy_kwargs,  # Запоминаем параметры стратегии, которые использовались в бектесте.
        "strategy_indicators": strategy_indicators,  # Сохраняем рассчитанные значения индикаторов для последующей отрисовки.
        "symbol": selected_symbol,  # Сохраняем символ для подписи графика сделок.
        "timeframe": selected_timeframe,  # Сохраняем таймфрейм для подписи графика сделок.
        "start_date": selected_start_date.isoformat() if selected_start_date is not None else None,  # Сохраняем дату начала бектеста.
        "end_date": selected_end_date.isoformat() if selected_end_date is not None else None,  # Сохраняем дату окончания бектеста.
        "run_context": normalized_context,  # Сохраняем metadata запуска для воспроизводимости.
        "sampling_metadata": sampling_metadata if isinstance(sampling_metadata, dict) else {},
        "run_id": normalized_context.get("run_id"),
        "run_created_at": normalized_context.get("created_at"),
    }  # Завершаем сохранение словаря с результатами.


def save_optimization_results(
    optimization_results,
    strategy_name,
    display_ranges,
    run_context: dict[str, Any] | None = None,
    parameter_labels: dict[str, str] | None = None,
):  # Создаем функцию, которая сохраняет результаты оптимизации в session_state.
    normalized_context = dict(run_context or {})
    normalized_context.setdefault("run_id", uuid4().hex)
    normalized_context.setdefault("created_at", datetime.now(timezone.utc).isoformat())

    st.session_state[OPTIMIZATION_RESULTS_KEY] = {  # Создаем словарь с результатами оптимизации для хранения между перерисовками.
        "results": optimization_results,  # Сохраняем список всех результатов оптимизации.
        "strategy_name": strategy_name,  # Сохраняем имя стратегии, по которой запускалась оптимизация.
        "display_ranges": display_ranges,  # Сохраняем отображаемые диапазоны параметров, выбранные пользователем в полях "от/до".
        "parameter_labels": dict(parameter_labels or {}),
        "run_context": normalized_context,  # Сохраняем metadata прогонки.
        "run_id": normalized_context.get("run_id"),
        "run_created_at": normalized_context.get("created_at"),
    }  # Завершаем сохранение словаря результатов оптимизации.


def extract_optimization_result_scope_key(result_data: Any) -> str:
    if not isinstance(result_data, dict):
        return ""

    strategy_name = str(result_data.get("strategy_name", "")).strip()
    if not strategy_name:
        return ""

    run_context = result_data.get("run_context")
    safe_run_context = run_context if isinstance(run_context, dict) else {}
    symbol = str(safe_run_context.get("symbol", "")).strip()
    timeframe = str(safe_run_context.get("timeframe", "")).strip()

    if not symbol or not timeframe:
        raw_results = result_data.get("results")
        if isinstance(raw_results, list) and raw_results:
            first_row = raw_results[0]
            if isinstance(first_row, dict):
                if not symbol:
                    symbol = str(first_row.get("symbol", "")).strip()
                if not timeframe:
                    timeframe = str(first_row.get("timeframe", "")).strip()

    if not symbol or not timeframe:
        return ""

    return build_optimization_scope_key(
        symbol=symbol,
        timeframe=timeframe,
        strategy_name=strategy_name,
    )


def optimization_result_has_rows(result_data: Any) -> bool:
    if not isinstance(result_data, dict):
        return False
    raw_results = result_data.get("results")
    return isinstance(raw_results, list) and bool(raw_results)


def optimization_result_matches_scope(
    result_data: Any,
    *,
    selected_symbol: str,
    selected_timeframe: str,
    selected_strategy_name: str,
) -> bool:
    actual_scope_key = extract_optimization_result_scope_key(result_data)
    if not actual_scope_key:
        return False
    expected_scope_key = build_optimization_scope_key(
        symbol=selected_symbol,
        timeframe=selected_timeframe,
        strategy_name=selected_strategy_name,
    )
    return actual_scope_key == expected_scope_key


def manage_optimization_run(
    *,
    selected_strategy_class,
    selected_strategy_name: str,
    selected_symbol: str,
    selected_timeframe: str,
    selected_start_date: date | None,
    selected_end_date: date | None,
    selected_data_file: Path,
    strategy_param_ranges: dict[str, Any],
    parameter_labels: dict[str, str],
    labeled_display_ranges: dict[str, Any],
    exceeds_hard_limit: bool,
    estimated_combinations: int,
    expected_evaluations: int,
    optimization_mode: str,
    fitness_formula: str,
    optimization_max_iterations: int | None = None,
    optimization_random_seed: int | None = None,
    optimization_random_iterations: int | None = None,
    optimization_genetic_settings: dict[str, Any] | None = None,
) -> None:
    active_states = {"running", "pausing", "paused", "cancelling"}
    terminal_states = {"completed", "cancelled", "failed"}

    def task_snapshot(task_state: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(task_state, dict):
            return None
        task_lock = task_state.get("lock")
        if task_lock is None:
            return None
        with task_lock:
            raw_progress = task_state.get("progress")
            raw_metadata = task_state.get("metadata")
            raw_results = task_state.get("results")
            snapshot = {
                "state": str(task_state.get("state", "")).strip().lower(),
                "progress": dict(raw_progress) if isinstance(raw_progress, dict) else {},
                "metadata": dict(raw_metadata) if isinstance(raw_metadata, dict) else {},
                "results": list(raw_results) if isinstance(raw_results, list) else [],
                "started_at": task_state.get("started_at"),
                "finished_at": task_state.get("finished_at"),
                "error_text": str(task_state.get("error_text", "")).strip(),
                "finalized": bool(task_state.get("finalized", False)),
            }
        task_thread = task_state.get("thread")
        snapshot["is_alive"] = bool(isinstance(task_thread, threading.Thread) and task_thread.is_alive())
        return snapshot

    task_state = st.session_state.get(OPTIMIZATION_TASK_STATE_KEY)
    snapshot = task_snapshot(task_state)
    if snapshot is not None and not snapshot["is_alive"] and snapshot["state"] in active_states:
        task_lock = task_state.get("lock")
        if task_lock is not None:
            with task_lock:
                task_state["state"] = "failed"
                task_state["finished_at"] = task_state.get("finished_at") or datetime.now(timezone.utc)
                if not str(task_state.get("error_text", "")).strip():
                    task_state["error_text"] = "Фоновая задача завершилась неожиданно."
        snapshot = task_snapshot(task_state)

    if snapshot is not None and snapshot["state"] in terminal_states and not snapshot["finalized"]:
        task_lock = task_state.get("lock")
        if task_lock is not None:
            with task_lock:
                task_state["finalized"] = True

        task_metadata = snapshot["metadata"]
        if snapshot["state"] == "completed":
            task_strategy_name = str(task_metadata.get("selected_strategy_name", "")).strip()
            task_strategy_class = task_metadata.get("selected_strategy_class")
            task_symbol = str(task_metadata.get("selected_symbol", selected_symbol))
            task_results = snapshot["results"]
            if task_results and task_strategy_name and task_strategy_class is not None:
                task_profile_store, task_profile, _, _, _ = load_strategy_profile_bundle(
                    selected_symbol=task_symbol,
                    selected_strategy_name=task_strategy_name,
                    selected_strategy_class=task_strategy_class,
                )
                best_result = max(
                    task_results,
                    key=lambda row: float(row.get("fitness", row.get("pnl", row.get("final_balance", 0.0)))),
                )
                best_params = best_result.get("params_snapshot", {})
                if isinstance(best_params, dict) and best_params:
                    update_candidate_params(task_profile, best_params)
                append_optimization_history(task_profile, task_results)
                save_profiles(task_profile_store, PROFILE_STORE_FILE)

            save_optimization_results(
                snapshot["results"],
                strategy_name=task_strategy_name or "N/A",
                display_ranges=task_metadata.get("display_ranges", {}),
                run_context=task_metadata.get("run_context", {}),
                parameter_labels=task_metadata.get("parameter_labels", {}),
            )
            saved_result_data = st.session_state.get(OPTIMIZATION_RESULTS_KEY)
            if snapshot["results"] and isinstance(saved_result_data, dict):
                task_run_context = task_metadata.get("run_context")
                safe_task_run_context = task_run_context if isinstance(task_run_context, dict) else {}
                scope_symbol = str(safe_task_run_context.get("symbol", task_symbol)).strip()
                scope_timeframe = str(safe_task_run_context.get("timeframe", selected_timeframe)).strip()
                scope_strategy_name = str(task_strategy_name or "").strip()
                if scope_symbol and scope_timeframe and scope_strategy_name:
                    scope_key = build_optimization_scope_key(
                        symbol=scope_symbol,
                        timeframe=scope_timeframe,
                        strategy_name=scope_strategy_name,
                    )
                    save_last_optimization_result(
                        file_path=OPTIMIZATION_STORE_FILE,
                        scope_key=scope_key,
                        result_data=saved_result_data,
                        ttl_hours=OPTIMIZATION_STORE_TTL_HOURS,
                    )
            if snapshot["results"]:
                st.session_state[OPTIMIZATION_NOTICE_KEY] = {
                    "level": "success",
                    "text": f"Оптимизация завершена для стратегии {task_strategy_name}. Лучшие параметры сохранены в candidate-профиль.",
                }
            else:
                st.session_state[OPTIMIZATION_NOTICE_KEY] = {
                    "level": "warning",
                    "text": "Оптимизация завершилась без результатов. Проверьте диапазоны параметров.",
                }
        elif snapshot["state"] == "cancelled":
            st.session_state[OPTIMIZATION_NOTICE_KEY] = {
                "level": "warning",
                "text": "Оптимизация отменена. Можно запустить процесс заново.",
            }
        else:
            st.session_state[OPTIMIZATION_NOTICE_KEY] = {
                "level": "error",
                "text": "Оптимизация остановлена из-за ошибки." + (f" {snapshot['error_text']}" if snapshot["error_text"] else ""),
            }

    notice = st.session_state.pop(OPTIMIZATION_NOTICE_KEY, None)
    if isinstance(notice, dict):
        level = str(notice.get("level", "info")).strip().lower()
        text = str(notice.get("text", "")).strip()
        if text:
            if level == "success":
                st.success(text)
            elif level == "warning":
                st.warning(text)
            elif level == "error":
                st.error(text)
            else:
                st.info(text)

    task_state = st.session_state.get(OPTIMIZATION_TASK_STATE_KEY)
    snapshot = task_snapshot(task_state)
    is_active = bool(snapshot is not None and snapshot["state"] in active_states and snapshot["is_alive"])

    if is_active:
        task_status = str(snapshot["state"])
        task_lock = task_state.get("lock")
        pause_event = task_state.get("pause_event")
        cancel_event = task_state.get("cancel_event")
        if task_status in {"running", "pausing"}:
            stop_col, cancel_col = st.columns(2)
            if stop_col.button("СТОП", width="stretch", key="optimization_stop_button"):
                if isinstance(pause_event, threading.Event):
                    pause_event.set()
                if task_lock is not None:
                    with task_lock:
                        if str(task_state.get("state", "")).strip().lower() == "running":
                            task_state["state"] = "pausing"
                st.rerun()
            if cancel_col.button("ОТМЕНА", width="stretch", key="optimization_cancel_button"):
                if isinstance(cancel_event, threading.Event):
                    cancel_event.set()
                if isinstance(pause_event, threading.Event):
                    pause_event.clear()
                if task_lock is not None:
                    with task_lock:
                        if str(task_state.get("state", "")).strip().lower() not in terminal_states:
                            task_state["state"] = "cancelling"
                st.rerun()
        elif task_status == "paused":
            resume_col, cancel_col = st.columns(2)
            if resume_col.button("ПРОДОЛЖИТЬ", type="primary", width="stretch", key="optimization_resume_button"):
                if isinstance(pause_event, threading.Event):
                    pause_event.clear()
                if task_lock is not None:
                    with task_lock:
                        task_state["state"] = "running"
                st.rerun()
            if cancel_col.button("ОТМЕНА", width="stretch", key="optimization_cancel_from_pause_button"):
                if isinstance(cancel_event, threading.Event):
                    cancel_event.set()
                if isinstance(pause_event, threading.Event):
                    pause_event.clear()
                if task_lock is not None:
                    with task_lock:
                        if str(task_state.get("state", "")).strip().lower() not in terminal_states:
                            task_state["state"] = "cancelling"
                st.rerun()
        else:
            st.info("Отменяю оптимизацию, подождите...")
    else:
        if st.button(
            "⚡ Запустить оптимизацию",
            type="primary",
            width="stretch",
            disabled=exceeds_hard_limit or expected_evaluations <= 0,
        ):
            run_context = build_run_context(
                selected_data_file=selected_data_file,
                selected_symbol=selected_symbol,
                selected_timeframe=selected_timeframe,
                selected_start_date=selected_start_date,
                selected_end_date=selected_end_date,
            )
            run_context["optimization_mode"] = str(optimization_mode)
            run_context["fitness_formula"] = str(fitness_formula or OPTIMIZATION_FITNESS_DEFAULT)
            run_context["estimated_combinations"] = int(estimated_combinations)
            run_context["expected_evaluations"] = int(expected_evaluations)
            if optimization_max_iterations is not None:
                run_context["max_iterations"] = int(optimization_max_iterations)
            if optimization_random_seed is not None:
                run_context["random_seed"] = int(optimization_random_seed)
            if optimization_random_iterations is not None:
                run_context["random_iterations"] = int(optimization_random_iterations)
            if isinstance(optimization_genetic_settings, dict) and optimization_genetic_settings:
                run_context["genetic_settings"] = dict(optimization_genetic_settings)
            fallback_stage_date = selected_start_date
            if fallback_stage_date is None:
                file_start_date, _ = get_data_file_date_range(
                    selected_data_file,
                    symbol=selected_symbol,
                    timeframe=selected_timeframe,
                )
                fallback_stage_date = file_start_date

            task_lock = threading.Lock()
            pause_event = threading.Event()
            cancel_event = threading.Event()
            task_state = {
                "lock": task_lock,
                "pause_event": pause_event,
                "cancel_event": cancel_event,
                "thread": None,
                "state": "running",
                "progress": {
                    "completed": 0,
                    "total": max(1, int(expected_evaluations)),
                    "progress": 0.0,
                    "stage_date": fallback_stage_date,
                },
                "results": [],
                "started_at": datetime.now(timezone.utc),
                "finished_at": None,
                "error_text": "",
                "finalized": False,
                "metadata": {
                    "selected_strategy_name": selected_strategy_name,
                    "selected_strategy_class": selected_strategy_class,
                    "selected_symbol": selected_symbol,
                    "run_context": run_context,
                    "display_ranges": dict(labeled_display_ranges),
                    "parameter_labels": dict(parameter_labels),
                    "fallback_stage_date": fallback_stage_date,
                },
            }

            def optimization_worker() -> None:
                def on_progress(progress_payload: dict[str, Any]) -> None:
                    total = int(progress_payload.get("total", 0) or 0)
                    completed = int(progress_payload.get("completed", 0) or 0)
                    if total <= 0:
                        return
                    safe_total = max(1, total)
                    safe_completed = max(0, min(completed, safe_total))
                    with task_lock:
                        task_state["progress"] = {
                            "completed": safe_completed,
                            "total": safe_total,
                            "progress": float(safe_completed) / float(safe_total),
                            "stage_date": progress_payload.get("stage_date"),
                        }

                def on_control() -> None:
                    if cancel_event.is_set():
                        raise OptimizationCancelledError("Cancelled by user.")
                    if pause_event.is_set():
                        with task_lock:
                            if str(task_state.get("state", "")).strip().lower() not in {"cancelling", "cancelled"}:
                                task_state["state"] = "paused"
                        while pause_event.is_set():
                            if cancel_event.is_set():
                                raise OptimizationCancelledError("Cancelled by user.")
                            time.sleep(0.2)
                        if cancel_event.is_set():
                            raise OptimizationCancelledError("Cancelled by user.")
                        with task_lock:
                            if str(task_state.get("state", "")).strip().lower() not in {"cancelling", "cancelled"}:
                                task_state["state"] = "running"

                try:
                    run_max_combinations = None
                    if str(optimization_mode).strip().lower() == "bruteforce":
                        if optimization_max_iterations is None or int(optimization_max_iterations) <= 0:
                            run_max_combinations = OPTIMIZATION_MAX_COMBINATIONS

                    results = run_optimization(
                        strategy_class=selected_strategy_class,
                        data_file=selected_data_file,
                        strategy_param_ranges=strategy_param_ranges,
                        strategy_kwargs={},
                        start_date=selected_start_date,
                        end_date=selected_end_date,
                        source="manual",
                        timeframe=selected_timeframe,
                        symbol=selected_symbol,
                        strategy_name=selected_strategy_name,
                        max_combinations=run_max_combinations,
                        optimization_mode=optimization_mode,
                        fitness_formula=fitness_formula,
                        max_iterations=optimization_max_iterations,
                        random_seed=optimization_random_seed,
                        random_iterations=optimization_random_iterations,
                        genetic_settings=optimization_genetic_settings,
                        progress_callback=on_progress,
                        control_callback=on_control,
                    )
                    with task_lock:
                        task_state["state"] = "cancelled" if cancel_event.is_set() else "completed"
                        task_state["results"] = [] if cancel_event.is_set() else results
                        task_state["finished_at"] = datetime.now(timezone.utc)
                except OptimizationCancelledError:
                    with task_lock:
                        task_state["state"] = "cancelled"
                        task_state["results"] = []
                        task_state["finished_at"] = datetime.now(timezone.utc)
                except Exception as exc:
                    with task_lock:
                        task_state["state"] = "failed"
                        task_state["results"] = []
                        task_state["error_text"] = f"{exc.__class__.__name__}: {exc}"
                        task_state["finished_at"] = datetime.now(timezone.utc)

            task_thread = threading.Thread(
                target=optimization_worker,
                name=f"optimization-worker-{uuid4().hex[:8]}",
                daemon=True,
            )
            task_state["thread"] = task_thread
            st.session_state[OPTIMIZATION_TASK_STATE_KEY] = task_state
            task_thread.start()
            st.rerun()

    task_state = st.session_state.get(OPTIMIZATION_TASK_STATE_KEY)
    snapshot = task_snapshot(task_state)
    if snapshot is not None and snapshot["state"] in active_states and snapshot["is_alive"]:
        total = max(1, int(snapshot["progress"].get("total", 0) or 0))
        completed = max(0, min(int(snapshot["progress"].get("completed", 0) or 0), total))
        percent = 100.0 * float(completed) / float(total)
        stage_date_value = snapshot["progress"].get("stage_date")
        fallback_stage_date = snapshot["metadata"].get("fallback_stage_date")
        current_stage_date = stage_date_value if isinstance(stage_date_value, date) else fallback_stage_date
        started_at = snapshot.get("started_at")
        elapsed_seconds = 0.0
        if isinstance(started_at, datetime):
            elapsed_seconds = max(0.0, (datetime.now(timezone.utc) - started_at).total_seconds())
        eta_label = "оценка времени после первой комбинации"
        if completed > 0:
            avg_seconds_per_run = elapsed_seconds / float(completed)
            eta_seconds = avg_seconds_per_run * float(max(0, total - completed))
            eta_label = f"осталось ~{format_duration_mmss(eta_seconds)}"
        status_prefix = {
            "running": "Прогоняю оптимизацию",
            "pausing": "Ставлю оптимизацию на паузу",
            "paused": "Оптимизация на паузе",
            "cancelling": "Останавливаю оптимизацию",
        }.get(snapshot["state"], "Оптимизация")
        stage_label = format_date_ddmmyyyy(current_stage_date) if isinstance(current_stage_date, date) else "текущий период"
        st.progress(int(round(percent)))
        st.info(
            f"{status_prefix}: {stage_label} "
            f"({completed}/{total}, {percent:.1f}%) | "
            f"прошло {format_duration_mmss(elapsed_seconds)} | {eta_label}"
        )
        if snapshot["state"] in {"running", "pausing", "cancelling"}:
            time.sleep(OPTIMIZATION_AUTORERUN_INTERVAL_SECONDS)
            st.rerun()


def build_trades_dataframe(trades_log):
    trades_dataframe = pd.DataFrame(trades_log)
    if trades_dataframe.empty:
        return trades_dataframe

    trades_dataframe = trades_dataframe.copy()

    for column_name in ("open_date", "close_date"):
        if column_name not in trades_dataframe.columns:
            trades_dataframe[column_name] = pd.NaT
        trades_dataframe[column_name] = pd.to_datetime(trades_dataframe[column_name], utc=True, errors="coerce")
        if pd.api.types.is_datetime64_any_dtype(trades_dataframe[column_name]):
            trades_dataframe[column_name] = trades_dataframe[column_name].dt.tz_localize(None)

    for column_name in ("open_price", "close_price", "pnl_after_commission"):
        if column_name not in trades_dataframe.columns:
            trades_dataframe[column_name] = pd.NA
        trades_dataframe[column_name] = pd.to_numeric(trades_dataframe[column_name], errors="coerce")

    return trades_dataframe.dropna(subset=["open_date", "close_date"]).reset_index(drop=True)


def build_equity_dataframe(equity_curve):
    equity_dataframe = pd.DataFrame(equity_curve)
    if equity_dataframe.empty:
        return equity_dataframe

    equity_dataframe = equity_dataframe.copy()

    if "datetime" not in equity_dataframe.columns:
        equity_dataframe["datetime"] = pd.NaT
    if "equity" not in equity_dataframe.columns:
        equity_dataframe["equity"] = pd.NA

    equity_dataframe["datetime"] = pd.to_datetime(equity_dataframe["datetime"], utc=True, errors="coerce")
    if pd.api.types.is_datetime64_any_dtype(equity_dataframe["datetime"]):
        equity_dataframe["datetime"] = equity_dataframe["datetime"].dt.tz_localize(None)
    equity_dataframe["equity"] = pd.to_numeric(equity_dataframe["equity"], errors="coerce")

    return equity_dataframe.dropna(subset=["datetime", "equity"]).reset_index(drop=True)


def build_optimization_dataframe(optimization_results):
    optimization_dataframe = pd.DataFrame(optimization_results)
    if optimization_dataframe.empty:
        return optimization_dataframe

    if "fitness" in optimization_dataframe.columns:
        optimization_dataframe["fitness"] = pd.to_numeric(optimization_dataframe["fitness"], errors="coerce")
        optimization_dataframe = optimization_dataframe.sort_values("fitness", ascending=False).reset_index(drop=True)
    elif "pnl" in optimization_dataframe.columns:
        optimization_dataframe = optimization_dataframe.sort_values("pnl", ascending=False).reset_index(drop=True)
    elif "final_balance" in optimization_dataframe.columns:
        optimization_dataframe = optimization_dataframe.sort_values("final_balance", ascending=False).reset_index(drop=True)
    else:
        optimization_dataframe = optimization_dataframe.reset_index(drop=True)
    return optimization_dataframe


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
    csv_bytes = dataframe.to_csv(index=False, encoding="utf-8").encode("utf-8")  # Преобразуем таблицу в CSV без индекса и кодируем в UTF-8.
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
        width="stretch",  # Просим Streamlit растянуть кнопку на всю ширину колонки.
    )  # Завершаем описание левой кнопки скачивания.
    col_2.download_button(  # Рисуем кнопку скачивания истории капитала.
        label="📥 Скачать историю капитала (CSV)",  # Задаем текст правой кнопки скачивания.
        data=equity_csv_bytes,  # Передаем подготовленные CSV-байты истории капитала.
        file_name="equity_curve.csv",  # Задаем имя файла для скачивания истории капитала.
        mime="text/csv",  # Указываем тип содержимого как CSV.
        width="stretch",  # Просим Streamlit растянуть кнопку на всю ширину колонки.
    )  # Завершаем описание правой кнопки скачивания.


def build_backtest_fullscreen_state_key(run_id: object, chart_symbol: str, chart_timeframe: str) -> str:
    run_key = str(run_id).strip() if run_id is not None else ""
    if not run_key:
        normalized_symbol = (chart_symbol or "symbol").replace("/", "_")
        normalized_timeframe = chart_timeframe or "timeframe"
        run_key = f"{normalized_symbol}_{normalized_timeframe}"
    return f"backtest_chart_fullscreen_{run_key}"


def show_backtest_fullscreen_chart_dialog(
    dialog_state_key: str,
    chart_dataframe: pd.DataFrame,
    chart_symbol: str,
    chart_timeframe: str,
    filtered_trades: pd.DataFrame,
    chart_indicator_payloads: list[dict],
    market_dataframe: pd.DataFrame,
    view_start_date: date | None,
    view_end_date: date | None,
):
    @st.dialog("📺 Полноэкранный график бектеста", width="large", dismissible=False)
    def _render_dialog():
        st.caption(
            "Режим TV-sized: увеличенное окно графика для детального просмотра входов/выходов и индикаторов."
        )
        if view_start_date is not None and view_end_date is not None:
            st.caption(f"Окно: {view_start_date} — {view_end_date} | свечей: {len(chart_dataframe):,}")

        fullscreen_price_chart = create_candlestick_chart(
            dataframe=chart_dataframe,
            selected_symbol=chart_symbol,
            selected_timeframe=chart_timeframe,
            title_suffix="Backtest | Fullscreen",
            trades_dataframe=filtered_trades,
            overlay_indicators=chart_indicator_payloads,
            show_navigation_indicators=True,
            navigation_reference_dataframe=market_dataframe,
            chart_height=BACKTEST_FULLSCREEN_CHART_HEIGHT,
            layout_profile="fullscreen",
        )
        plotly_chart_with_wheel(
            fullscreen_price_chart,
            key=f"{dialog_state_key}_plot",
        )

        close_button_clicked = st.button(
            "Закрыть полноэкранный режим",
            key=f"{dialog_state_key}_close",
            type="primary",
            width="stretch",
        )
        if close_button_clicked:
            st.session_state[dialog_state_key] = False
            st.rerun()

    _render_dialog()


def show_backtest_results(result_data, selected_symbol: str = "", selected_timeframe: str = "", selected_start_date: date | None = None, selected_end_date: date | None = None):
    starting_balance = result_data["starting_balance"]  # Извлекаем стартовый капитал из сохраненного результата.
    final_balance = result_data["final_balance"]  # Извлекаем итоговый капитал из сохраненного результата.
    trades_dataframe = build_trades_dataframe(result_data["trades_log"])  # Превращаем лог сделок в таблицу для вывода на экран.
    equity_dataframe = build_equity_dataframe(result_data["equity_curve"])  # Превращаем историю капитала в таблицу для графика.
    strategy_indicators = result_data.get("strategy_indicators", [])
    if not isinstance(strategy_indicators, list):
        strategy_indicators = []
    run_context = result_data.get("run_context") if isinstance(result_data.get("run_context"), dict) else {}
    run_id = run_context.get("run_id")
    created_at = run_context.get("created_at")
    data_context = run_context.get("data_context") if isinstance(run_context.get("data_context"), dict) else {}
    run_metadata_parts: list[str] = []
    if run_id:
        run_metadata_parts.append(f"Run ID: {run_id}")
    if created_at:
        run_metadata_parts.append(f"Сформировано: {created_at}")
    if data_context:
        rows = data_context.get("rows")
        if rows is not None:
            run_metadata_parts.append(f"Data rows: {rows}")
        checksum = data_context.get("checksum")
        if checksum:
            run_metadata_parts.append(f"Data checksum: {checksum[:12]}")

    run_metadata_caption = " | ".join(run_metadata_parts)
    if run_metadata_caption:
        st.caption(run_metadata_caption)
    sampling_metadata = result_data.get("sampling_metadata")
    if isinstance(sampling_metadata, dict):
        sampling_caption_parts: list[str] = []
        equity_sampling = sampling_metadata.get("equity_curve")
        if isinstance(equity_sampling, dict):
            equity_original = int(equity_sampling.get("original_points", 0) or 0)
            equity_stored = int(equity_sampling.get("stored_points", 0) or 0)
            if equity_original > 0:
                sampling_caption_parts.append(f"Equity points: {equity_stored:,}/{equity_original:,}")
        indicator_sampling = sampling_metadata.get("indicators")
        if isinstance(indicator_sampling, dict):
            indicators_original = int(indicator_sampling.get("total_original_points", 0) or 0)
            indicators_stored = int(indicator_sampling.get("total_stored_points", 0) or 0)
            if indicators_original > 0:
                sampling_caption_parts.append(f"Indicator points: {indicators_stored:,}/{indicators_original:,}")
        if sampling_caption_parts:
            st.caption("Сэмплинг данных: " + " | ".join(sampling_caption_parts))

    profit = final_balance - starting_balance  # Считаем прибыль или убыток стратегии в деньгах.
    profit_delta = f"{profit:,.2f} USDT"  # Подготавливаем красивую подпись для разницы между итоговым и стартовым балансом.
    col_1, col_2, col_3 = st.columns(3)  # Создаем три колонки, чтобы вывести три ключевые метрики в одну строку.
    col_1.metric("Начальный баланс", format_balance(starting_balance))  # Показываем стартовый капитал.
    col_2.metric("Итоговый баланс", format_balance(final_balance), delta=profit_delta)  # Показываем итоговый капитал и его отличие от начального.
    col_3.metric("Прибыль / убыток", format_balance(profit))  # Показываем абсолютный финансовый результат отдельно.
    show_export_buttons(trades_dataframe, equity_dataframe)  # Показываем две кнопки экспорта CSV сразу под карточками метрик.
    st.caption(f"Стратегия: {result_data['strategy_name']} | Параметры: {result_data['strategy_kwargs']}")  # Показываем, какая стратегия и какие параметры использовались в текущем бектесте.
    chart_symbol = result_data.get("symbol", "") or selected_symbol or "BTC/USDT"  # Берем символ из кэша результатов или из текущего контекста.
    chart_timeframe = result_data.get("timeframe", "") or selected_timeframe or "1h"  # Берем таймфрейм из кэша результатов или из текущего контекста.
    chart_start_date = deserialize_date(result_data.get("start_date")) or selected_start_date
    chart_end_date = deserialize_date(result_data.get("end_date")) or selected_end_date
    chart_data_file = get_selected_data_file(selected_symbol=chart_symbol, selected_timeframe=chart_timeframe)  # Берем файл с историей по сохраненному контексту.
    fullscreen_state_key = build_backtest_fullscreen_state_key(
        run_id=run_id,
        chart_symbol=chart_symbol,
        chart_timeframe=chart_timeframe,
    )
    market_dataframe = pd.DataFrame()
    market_view_dataframe = pd.DataFrame()
    view_start_date: date | None = chart_start_date
    view_end_date: date | None = chart_end_date

    if chart_data_file.exists():  # Проверяем наличие данных для визуализации.
        try:
            market_dataframe = load_data_from_csv(chart_data_file)  # Загружаем market dataframe.
            if chart_start_date is not None or chart_end_date is not None:
                market_dataframe = filter_data_by_date_range(
                    market_dataframe,
                    chart_start_date,
                    chart_end_date,
                )
        except Exception as exc:
            show_classified_error("Не удалось загрузить данные для графика бектеста", exc)
            market_dataframe = pd.DataFrame()

        if market_dataframe.empty:
            st.info(f"По сохраненным параметрам бектеста для {chart_symbol} / {chart_timeframe} нет свечей.")
        else:
            market_data_start = market_dataframe["datetime"].min().date()
            market_data_end = market_dataframe["datetime"].max().date()

            default_view_start = view_start_date if view_start_date is not None else market_data_start
            default_view_end = view_end_date if view_end_date is not None else market_data_end
            default_view_start = max(default_view_start, market_data_start)
            default_view_end = min(default_view_end, market_data_end)
            if default_view_start > default_view_end:
                default_view_start = market_data_start
                default_view_end = market_data_end

            selected_range = st.date_input(
                "Диапазон графика бектеста",
                value=[default_view_start, default_view_end],
                min_value=market_data_start,
                max_value=market_data_end,
                key=f"backtest_chart_range_{run_id or chart_symbol.replace('/', '_')}_{chart_timeframe}",
            )  # Локальный контрол выбора окна вывода результатов.
            if isinstance(selected_range, tuple):
                selected_range = list(selected_range)
            if (
                not isinstance(selected_range, (list, tuple))
                or len(selected_range) != 2
                or selected_range[0] is None
                or selected_range[1] is None
            ):
                selected_range = [default_view_start, default_view_end]
            view_start_date = selected_range[0]
            view_end_date = selected_range[1]

            if view_start_date > view_end_date:
                st.info("Неверный диапазон графика, используется исходный диапазон запуска бектеста.")
                view_start_date = default_view_start
                view_end_date = default_view_end

            view_start_date = max(view_start_date, market_data_start)
            view_end_date = min(view_end_date, market_data_end)

            market_view_dataframe = filter_data_by_date_range(
                market_dataframe,
                view_start_date,
                view_end_date,
            )
            if market_view_dataframe.empty:
                st.info("В выбранном окне графика нет данных свечей.")
            else:
                chart_dataframe = downsample_for_chart(market_view_dataframe)  # Урезаем для графика.
                if len(chart_dataframe) < len(market_view_dataframe):  # Сообщаем о даунсэмплинге если применен.
                    st.caption(f"График цены даунсэмплен до {len(chart_dataframe):,} свечей для скорости.")
                st.caption(
                    f"Диапазон графика бектеста: {view_start_date} — {view_end_date} | свечей: {len(market_view_dataframe):,}"
                )
                available_indicators: list[dict] = []
                indicator_options: list[str] = []
                indicator_label_by_id: dict[str, str] = {}
                default_indicator_selection: list[str] = []

                for payload in strategy_indicators:
                    if not isinstance(payload, dict):
                        continue
                    normalized_payload = dict(payload)
                    indicator_id = _indicator_payload_id(normalized_payload)
                    if not indicator_id or indicator_id in indicator_label_by_id:
                        continue
                    payload_points = normalized_payload.get("points", [])
                    if not isinstance(payload_points, list) or not payload_points:
                        continue
                    if not normalized_payload.get("label"):
                        normalized_payload["label"] = indicator_id
                    normalized_payload["id"] = indicator_id
                    normalized_payload.setdefault("default_visible", True)

                    available_indicators.append(normalized_payload)
                    indicator_options.append(indicator_id)
                    indicator_label_by_id[indicator_id] = str(normalized_payload.get("label", indicator_id))
                    if bool(normalized_payload.get("default_visible", True)):
                        default_indicator_selection.append(indicator_id)

                if not default_indicator_selection:
                    default_indicator_selection = indicator_options.copy()

                if available_indicators:
                    indicator_selection_key = f"backtest_indicator_selection_{run_id or chart_symbol.replace('/', '_')}_{chart_timeframe}"
                    selected_default_indicators = st.session_state.get(indicator_selection_key, default_indicator_selection)
                    if not isinstance(selected_default_indicators, list):
                        selected_default_indicators = default_indicator_selection
                    else:
                        selected_default_indicators = [
                            str(value)
                            for value in selected_default_indicators
                            if str(value) in indicator_options
                        ]
                    if not selected_default_indicators:
                        selected_default_indicators = default_indicator_selection

                    selected_indicator_ids = st.multiselect(
                        "Индикаторы стратегии на графике",
                        options=indicator_options,
                        default=selected_default_indicators,
                        key=indicator_selection_key,
                        format_func=lambda value: indicator_label_by_id.get(value, value),
                    )
                    selected_indicator_payloads = [
                        payload
                        for payload in available_indicators
                        if _indicator_payload_id(payload) in selected_indicator_ids
                    ]
                else:
                    selected_indicator_payloads = []

                filtered_indicator_payloads = _filter_indicator_payload(
                    payload_list=selected_indicator_payloads,
                    start_date=view_start_date,
                    end_date=view_end_date,
                )
                chart_indicator_payloads = _downsample_indicator_payloads(
                    dataframe=market_view_dataframe,
                    payload_list=filtered_indicator_payloads,
                )
                filtered_trades = filter_trades_by_date_range(
                    trades_dataframe,
                    view_start_date,
                    view_end_date,
                )
                header_col, open_fullscreen_col, fullscreen_control_col = st.columns([0.52, 0.26, 0.22], vertical_alignment="center")
                with header_col:
                    st.subheader("📉 График цены с сделками")  # Добавляем подзаголовок к price-чарту.
                with open_fullscreen_col:
                    open_fullscreen_clicked = st.button(
                        "📺 Открыть большой график",
                        key=f"{fullscreen_state_key}_open_button",
                        width="stretch",
                    )
                with fullscreen_control_col:
                    st.toggle(
                        "Полноэкранный режим графика",
                        key=fullscreen_state_key,
                    )
                if open_fullscreen_clicked and not bool(st.session_state.get(fullscreen_state_key, False)):
                    st.session_state[fullscreen_state_key] = True
                    st.rerun()

                price_chart = create_candlestick_chart(  # Строим свечной график в стиле TV-подобного шаблона.
                    dataframe=chart_dataframe,  # Передаем уже усеченные данные рынка.
                    selected_symbol=chart_symbol,  # Указываем символ для заголовка.
                    selected_timeframe=chart_timeframe,  # Указываем таймфрейм для заголовка.
                    title_suffix="Backtest",  # Сразу помечаем, что это график результатов бектеста.
                    trades_dataframe=filtered_trades,  # Накладываем входы и выходы.
                    overlay_indicators=chart_indicator_payloads,  # Накладываем индикаторы стратегии.
                    show_navigation_indicators=True,
                    navigation_reference_dataframe=market_dataframe,
                    chart_height=BACKTEST_DEFAULT_CHART_HEIGHT,
                    layout_profile="default",
                )  # Готовый чартик с trade-оверлеями.
                plotly_chart_with_wheel(price_chart)  # Отрисовываем график цен в интерфейсе с колесиком масштаба.

                if bool(st.session_state.get(fullscreen_state_key, False)):
                    show_backtest_fullscreen_chart_dialog(
                        dialog_state_key=fullscreen_state_key,
                        chart_dataframe=chart_dataframe,
                        chart_symbol=chart_symbol,
                        chart_timeframe=chart_timeframe,
                        filtered_trades=filtered_trades,
                        chart_indicator_payloads=chart_indicator_payloads,
                        market_dataframe=market_dataframe,
                        view_start_date=view_start_date,
                        view_end_date=view_end_date,
                    )
    else:
        st.info(f"Файл данных для графика отсутствует: {chart_symbol} / {chart_timeframe}.")

    st.subheader("📝 Лог сделок")  # Добавляем подзаголовок перед таблицей сделок с иконкой.
    if trades_dataframe.empty:  # Проверяем, есть ли у стратегии хотя бы одна закрытая сделка.
        st.info("Закрытых сделок пока нет. Это означает, что за выбранный период стратегия не получила полного сигнала на вход и выход.")  # Показываем понятное сообщение, если лог сделок пуст.
    else:  # Переходим в этот блок, если сделки в логе есть.
        styled_trades_dataframe = style_trades_dataframe(trades_dataframe)  # Применяем цветовую подсветку к таблице сделок через Pandas Styler.
        st.dataframe(styled_trades_dataframe, width="stretch")  # Выводим стилизованную таблицу со всеми закрытыми сделками.

    st.subheader("📈 График капитала")  # Добавляем подзаголовок перед equity curve с иконкой.
    if equity_dataframe.empty:  # Проверяем, есть ли точки для построения графика капитала.
        st.info("История капитала пока пуста.")  # Показываем понятное сообщение, если история капитала не была собрана.
    else:
        equity_view_dataframe = equity_dataframe
        if view_start_date is not None or view_end_date is not None:
            equity_view_dataframe = filter_data_by_date_range(
                equity_dataframe,
                view_start_date,
                view_end_date,
            )
        if equity_view_dataframe.empty:
            st.info("В выбранном диапазоне истории капитала нет точек.")
        else:
            window_points_text = (
                f"Окно: {equity_view_dataframe['datetime'].min().date()} — {equity_view_dataframe['datetime'].max().date()} | "
                f"точек: {len(equity_view_dataframe):,}"
            )
            equity_chart = create_equity_curve_chart(  # Строим линейный график изменения капитала.
                equity_view_dataframe,
                title_suffix=window_points_text,
            )  # Готовый график капитала.
            plotly_chart_with_wheel(equity_chart)  # Показываем график капитала в интерфейсе с колесиком масштаба.


def show_optimization_results(result_data):
    optimization_dataframe = build_optimization_dataframe(result_data["results"])
    if optimization_dataframe.empty:
        st.info("Оптимизация не дала данных для отображения.")
        return

    parameter_labels_raw = result_data.get("parameter_labels")
    parameter_labels = parameter_labels_raw if isinstance(parameter_labels_raw, dict) else {}

    def display_name(parameter_name: str) -> str:
        mapped = parameter_labels.get(parameter_name)
        if isinstance(mapped, str) and mapped.strip():
            return mapped
        return get_parameter_display_name(parameter_name)

    def to_int(value: Any, default: int = 0) -> int:
        normalized = _normalize_numeric_value(value)
        if normalized is None:
            return int(default)
        return max(0, int(round(float(normalized))))

    def to_float(value: Any) -> float | None:
        normalized = _normalize_numeric_value(value)
        if normalized is None:
            return None
        return float(normalized)

    def to_bool(value: Any) -> bool:
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if value is None:
            return False
        if isinstance(value, (int, float, np.integer, np.floating)):
            if pd.isna(value):
                return False
            return float(value) != 0.0
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y", "да"}:
                return True
            if normalized in {"0", "false", "no", "n", "нет", ""}:
                return False
        return bool(value)

    best_result = optimization_dataframe.iloc[0]
    ignore_columns = {
        "run_id",
        "strategy_name",
        "params_snapshot",
        "pnl",
        "fitness",
        "final_balance",
        "source",
        "created_at",
        "optimized_param",
        "symbol",
        "timeframe",
        "start_date",
        "end_date",
        "optimization_mode",
        "fitness_formula",
        "trade_count",
        "winning_trades",
        "losing_trades",
        "win_rate",
        "gross_profit",
        "gross_loss_abs",
        "profit_factor",
        "avg_trade_pnl",
        "recovery_factor",
        "return_pct",
        "max_drawdown_abs",
        "max_drawdown_pct",
        "take_profit_trades",
        "stop_loss_trades",
        "other_exit_trades",
        "close_after_entry_count",
        "close_after_dca1_count",
        "close_after_dca2_count",
        "close_after_dca3plus_count",
        "has_exit_reason_stats",
        "has_averaging_stats",
    }
    params_snapshot = best_result.get("params_snapshot")
    if isinstance(params_snapshot, dict) and params_snapshot:
        if parameter_labels:
            snapshot_items = [
                (name, params_snapshot.get(name))
                for name in parameter_labels.keys()
                if params_snapshot.get(name) is not None
            ]
        else:
            snapshot_items = [(name, value) for name, value in params_snapshot.items() if value is not None]
        best_parameters = [f"{display_name(name)}={value}" for name, value in snapshot_items]
    else:
        best_parameters = [
            f"{display_name(column)}={best_result[column]}"
            for column in optimization_dataframe.columns
            if column not in ignore_columns
        ]
    best_parameters_text = ", ".join(best_parameters) or "-"

    if "pnl" in best_result and pd.notna(best_result["pnl"]):
        best_profit_text = format_balance(float(best_result["pnl"]))
    elif "final_balance" in best_result and "starting_balance" in result_data and pd.notna(best_result["final_balance"]):
        best_profit_text = format_balance(float(best_result["final_balance"]) - float(result_data["starting_balance"]))
    elif "final_balance" in best_result and pd.notna(best_result["final_balance"]):
        best_profit_text = format_balance(float(best_result["final_balance"]))
    else:
        best_profit_text = "N/A"

    if "fitness" in best_result and pd.notna(best_result["fitness"]):
        best_fitness_text = f"{float(best_result['fitness']):,.4f}"
    else:
        best_fitness_text = "N/A"

    col_1, col_2, col_3 = st.columns(3)
    col_1.metric("Лучшие параметры", best_parameters_text)
    col_2.metric("Лучший Fitness", best_fitness_text)
    col_3.metric("Лучший PnL", best_profit_text)
    run_context = result_data.get("run_context") if isinstance(result_data.get("run_context"), dict) else {}
    run_id = run_context.get("run_id")
    created_at = run_context.get("created_at")
    optimization_mode = str(run_context.get("optimization_mode", "")).strip()
    fitness_formula = str(run_context.get("fitness_formula", "")).strip()
    expected_evaluations = run_context.get("expected_evaluations")
    run_meta = []
    if run_id:
        run_meta.append(f"Run ID: {run_id}")
    if created_at:
        run_meta.append(f"Сформировано: {created_at}")
    if optimization_mode:
        run_meta.append(f"Mode: {optimization_mode}")
    if fitness_formula:
        run_meta.append(f"Fitness: {fitness_formula}")
    if expected_evaluations is not None:
        run_meta.append(f"Runs: {int(expected_evaluations):,}")
    if run_meta:
        st.caption(" | ".join(run_meta))
    st.caption(f"Стратегия: {result_data['strategy_name']} | Диапазоны: {result_data['display_ranges']}")

    renamed_dataframe = optimization_dataframe.copy()
    if parameter_labels:
        keep_meta_columns = [
            "run_id",
            "strategy_name",
            "optimized_param",
            "fitness",
            "final_balance",
            "pnl",
            "source",
            "created_at",
            "symbol",
            "timeframe",
            "start_date",
            "end_date",
            "optimization_mode",
            "fitness_formula",
        ]
        keep_columns = [column for column in keep_meta_columns if column in renamed_dataframe.columns]
        keep_columns += [column for column in parameter_labels.keys() if column in renamed_dataframe.columns]
        if keep_columns:
            renamed_dataframe = renamed_dataframe.loc[:, keep_columns]

    rename_map: dict[str, str] = {
        "strategy_name": "Стратегия",
        "fitness": "Fitness",
        "final_balance": "Финальный баланс",
        "pnl": "PnL",
        "source": "Источник",
        "created_at": "Создано",
        "symbol": "Пара",
        "timeframe": "Таймфрейм",
        "start_date": "Дата начала",
        "end_date": "Дата конца",
        "optimization_mode": "Режим",
        "fitness_formula": "Формула Fitness",
        "trade_count": "Сделок",
        "win_rate": "ВинРейт (%)",
        "profit_factor": "Profit Factor",
        "take_profit_trades": "TP сделки",
        "stop_loss_trades": "SL сделки",
        "other_exit_trades": "Прочие выходы",
        "close_after_entry_count": "Закрыто без усреднения",
        "close_after_dca1_count": "Закрыто после 1 усреднения",
        "close_after_dca2_count": "Закрыто после 2 усреднений",
        "close_after_dca3plus_count": "Закрыто после 3+ усреднений",
        "has_exit_reason_stats": "Есть TP/SL статистика",
        "has_averaging_stats": "Есть статистика усреднений",
    }
    for column_name in renamed_dataframe.columns:
        if column_name in ignore_columns:
            continue
        rename_map.setdefault(column_name, display_name(column_name))
    renamed_dataframe = renamed_dataframe.rename(columns=rename_map)

    st.subheader("Параметры и результаты")
    table_run_id = str(run_id or result_data.get("run_id", "") or result_data.get("run_created_at", "")).strip()
    if not table_run_id:
        table_run_id = str(result_data.get("strategy_name", "optimization")).strip()
    table_state = st.dataframe(
        renamed_dataframe,
        width="stretch",
        key=f"optimization_results_table_{table_run_id}",
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_rows: list[int] = []
    try:
        selection_state = table_state.selection
        selected_rows = [int(index) for index in list(getattr(selection_state, "rows", []) or [])]
    except Exception:
        selected_rows = []

    selected_row_index = int(selected_rows[0]) if selected_rows else 0
    if selected_row_index < 0:
        selected_row_index = 0
    if selected_row_index >= len(optimization_dataframe):
        selected_row_index = len(optimization_dataframe) - 1

    selected_result = optimization_dataframe.iloc[selected_row_index]
    selected_run_id = str(selected_result.get("run_id", "")).strip()
    if selected_run_id:
        st.caption(f"Выбрана строка #{selected_row_index + 1} | Run ID: {selected_run_id}")
    else:
        st.caption(f"Выбрана строка #{selected_row_index + 1}")

    st.subheader("Статистика выбранного прогона")
    trade_count = to_int(selected_result.get("trade_count"), default=0)
    win_rate_value = to_float(selected_result.get("win_rate"))
    profit_factor_value = to_float(selected_result.get("profit_factor"))

    if win_rate_value is None:
        win_rate_text = "N/A"
    else:
        win_rate_text = f"{float(win_rate_value):.2f}%"

    if profit_factor_value is None:
        profit_factor_text = "N/A"
    elif np.isfinite(float(profit_factor_value)):
        profit_factor_text = f"{float(profit_factor_value):,.2f}"
    elif float(profit_factor_value) > 0:
        profit_factor_text = "∞"
    else:
        profit_factor_text = "N/A"

    common_col_1, common_col_2, common_col_3 = st.columns(3)
    common_col_1.metric("Кол-во сделок", f"{trade_count:,}")
    common_col_2.metric("ВинРейт", win_rate_text)
    common_col_3.metric("Риск vs Доходность", profit_factor_text)

    has_exit_reason_stats = to_bool(selected_result.get("has_exit_reason_stats"))
    has_averaging_stats = to_bool(selected_result.get("has_averaging_stats"))

    if has_exit_reason_stats:
        take_profit_trades = to_int(selected_result.get("take_profit_trades"), default=0)
        stop_loss_trades = to_int(selected_result.get("stop_loss_trades"), default=0)
        other_exit_trades = to_int(selected_result.get("other_exit_trades"), default=0)
        exit_col_1, exit_col_2, exit_col_3 = st.columns(3)
        exit_col_1.metric("Кол-во тейк-профитов", f"{take_profit_trades:,}")
        exit_col_2.metric("Кол-во стопов", f"{stop_loss_trades:,}")
        exit_col_3.metric("Прочие выходы", f"{other_exit_trades:,}")

    if has_averaging_stats:
        close_after_entry_count = to_int(selected_result.get("close_after_entry_count"), default=0)
        close_after_dca1_count = to_int(selected_result.get("close_after_dca1_count"), default=0)
        close_after_dca2_count = to_int(selected_result.get("close_after_dca2_count"), default=0)
        close_after_dca3plus_count = to_int(selected_result.get("close_after_dca3plus_count"), default=0)
        total_for_percent = float(trade_count) if trade_count > 0 else 0.0

        def pct(value: int) -> float:
            if total_for_percent <= 0.0:
                return 0.0
            return 100.0 * float(value) / total_for_percent

        st.caption("Усреднения в процентах (по закрытиям сделок):")
        avg_col_1, avg_col_2, avg_col_3, avg_col_4 = st.columns(4)
        avg_col_1.metric("После входа (0)", f"{pct(close_after_entry_count):.2f}%")
        avg_col_2.metric("После 1 уср.", f"{pct(close_after_dca1_count):.2f}%")
        avg_col_3.metric("После 2 уср.", f"{pct(close_after_dca2_count):.2f}%")
        avg_col_4.metric("После 3+ уср.", f"{pct(close_after_dca3plus_count):.2f}%")
        st.caption(
            "Сделок по bucket-ам: "
            f"0={close_after_entry_count:,}, "
            f"1={close_after_dca1_count:,}, "
            f"2={close_after_dca2_count:,}, "
            f"3+={close_after_dca3plus_count:,}"
        )

    if not has_exit_reason_stats and not has_averaging_stats:
        st.caption("Для выбранной стратегии недоступна детализация TP/SL и усреднений.")

def show_backtest_tab(
    available_strategies,
    selected_symbol: str,
    selected_timeframe: str,
    selected_start_date: date | None = None,
    selected_end_date: date | None = None,
):
    st.subheader("⚙️ Настройки стратегии")  # Показываем подзаголовок раздела бектеста с иконкой.
    selected_data_file = get_selected_data_file(selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)
    if not selected_data_file.exists():  # Проверяем, есть ли файл для выбранной пары и таймфрейма.
        st.warning("Сначала загрузите исторические данные именно для выбранной пары и таймфрейма во вкладке 'Данные и график'.")  # Показываем понятное предупреждение, если файл с данными еще не создан.
        return  # Прерываем дальнейший вывод, потому что бектест пока запускать не на чем.
    selected_strategy_name, selected_strategy_class = render_strategy_selector(available_strategies=available_strategies, label="Стратегия для бектеста", key="backtest_strategy_selector")  # Показываем выпадающий список всех доступных стратегий для вкладки бектеста.
    profile_store, profile, _, active_profile_params, candidate_profile_params = load_strategy_profile_bundle(
        selected_symbol=selected_symbol,
        selected_strategy_name=selected_strategy_name,
        selected_strategy_class=selected_strategy_class,
    )
    parameter_specs = get_strategy_parameter_specs(selected_strategy_class=selected_strategy_class)
    profile_meta = profile.get("updated_at")
    if profile_meta:
        st.caption(f"Профиль параметров: last update {profile_meta}")
    profile_apply_col, profile_candidate_col = st.columns(2)
    with profile_apply_col:
        apply_active_clicked = st.button(
            "Применить active-профиль",
            key=f"backtest_apply_active_{selected_symbol}_{selected_strategy_name}",
            width="stretch",
        )
    with profile_candidate_col:
        apply_candidate_clicked = st.button(
            "Применить candidate-профиль",
            key=f"backtest_apply_candidate_{selected_symbol}_{selected_strategy_name}",
            width="stretch",
            disabled=not bool(candidate_profile_params),
        )

    if apply_active_clicked:
        prime_strategy_widget_state(
            widget_prefix="backtest",
            selected_strategy_name=selected_strategy_name,
            params=active_profile_params,
        )
    if apply_candidate_clicked and candidate_profile_params:
        prime_strategy_widget_state(
            widget_prefix="backtest",
            selected_strategy_name=selected_strategy_name,
            params=candidate_profile_params,
        )

    strategy_kwargs = render_backtest_controls(
        selected_strategy_class=selected_strategy_class,
        selected_strategy_name=selected_strategy_name,
        initial_params=active_profile_params,
    )  # Динамически рисуем поля настройки параметров для выбранной стратегии и получаем kwargs.
    validation_error = validate_strategy_kwargs(  # Проверяем параметры стратегии перед запуском бектеста.
        strategy_kwargs=strategy_kwargs, selected_strategy_class=selected_strategy_class
    )  # Проверяем параметры стратегии перед запуском бектеста.
    if validation_error is not None:  # Проверяем, нашлась ли ошибка валидации параметров.
        st.error(validation_error)  # Показываем понятную ошибку, если параметры введены неверно.
        return  # Останавливаем запуск бектеста до исправления значений.
    save_active_clicked = st.button(
        "💾 Сохранить текущие параметры как active",
        key=f"backtest_save_active_{selected_symbol}_{selected_strategy_name}",
        width="stretch",
    )
    if save_active_clicked:
        update_active_params(profile, strategy_kwargs)
        save_profiles(profile_store, PROFILE_STORE_FILE)
        st.success("Active-профиль обновлен из текущих параметров бектеста.")

    button_clicked = st.button("🚀 Запустить бектест", type="primary", width="stretch")  # Создаем большую кнопку запуска бектеста с иконкой.
    if button_clicked:  # Проверяем, нажал ли пользователь кнопку запуска.
        run_context = build_run_context(
            selected_data_file=selected_data_file,
            selected_symbol=selected_symbol,
            selected_timeframe=selected_timeframe,
            selected_start_date=selected_start_date,
            selected_end_date=selected_end_date,
        )
        with st.spinner("Запускаю бектест стратегии. Пожалуйста, подождите..."):  # Показываем анимацию ожидания, пока идет расчет.
            try:
                (
                    starting_balance,
                    final_balance,
                    trades_log,
                    equity_curve,
                    strategy_indicators,
                    sampling_metadata,
                ) = run_backtest(
                    strategy_class=selected_strategy_class,
                    data_file=selected_data_file,
                    strategy_kwargs=strategy_kwargs,
                    start_date=selected_start_date,
                    end_date=selected_end_date,
                )
            except Exception as exc:
                show_classified_error("Бектест не выполнен", exc)
                return
        save_backtest_results(  # Сохраняем расширенный контекст для последующего отображения графика.
            starting_balance=starting_balance,  # Стартовый капитал.
            final_balance=final_balance,  # Итоговый капитал.
            trades_log=trades_log,  # Список сделок.
            equity_curve=equity_curve,  # График капитала.
            strategy_indicators=strategy_indicators,  # Индикаторы из стратегии для графика.
            strategy_name=selected_strategy_name,  # Имя стратегии.
            strategy_kwargs=strategy_kwargs,  # Настройки стратегии.
            selected_symbol=selected_symbol,  # Символ, выбранный в боковой панели.
            selected_timeframe=selected_timeframe,  # Таймфрейм, выбранный в боковой панели.
            selected_start_date=selected_start_date,  # Дата начала периода бектеста.
            selected_end_date=selected_end_date,  # Дата окончания периода бектеста.
            run_context=run_context,  # Контекст запуска для воспроизводимости.
            sampling_metadata=sampling_metadata,
        )  # Кэшируем результат для повторной визуализации без пересчета.
        update_active_params(profile, strategy_kwargs)
        save_profiles(profile_store, PROFILE_STORE_FILE)
        st.success(f"Бектест завершен для стратегии {selected_strategy_name}.")  # Сообщаем, что симуляция успешно завершилась.
    result_data = st.session_state.get(BACKTEST_RESULTS_KEY)  # Пробуем получить сохраненный результат последнего запущенного бектеста.
    if result_data is None:  # Проверяем, запускался ли бектест хотя бы один раз в текущей сессии.
        st.info("После запуска бектеста здесь появятся метрики, лог сделок и график капитала.")  # Показываем подсказку, пока результатов еще нет.
        return  # Завершаем функцию, потому что показывать пока нечего.
    show_backtest_results(
        result_data,
        selected_symbol=selected_symbol,
        selected_timeframe=selected_timeframe,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
    )


def show_optimization_tab(
    available_strategies,
    selected_symbol: str = "",
    selected_timeframe: str = "",
    selected_start_date: date | None = None,
    selected_end_date: date | None = None,
):
    st.subheader("⚡ Оптимизация параметров стратегии")  # Показываем подзаголовок раздела оптимизации с иконкой.
    st.write("Здесь можно перебрать множество комбинаций параметров стратегии и быстро найти самую прибыльную связку.")  # Простыми словами объясняем, что делает этот раздел.
    selected_data_file = get_selected_data_file(selected_symbol=selected_symbol, selected_timeframe=selected_timeframe)
    if not selected_data_file.exists():  # Проверяем, есть ли файл для выбранной пары и таймфрейма.
        st.warning("Сначала загрузите исторические данные именно для выбранной пары и таймфрейма во вкладке 'Данные и график'.")  # Показываем понятное предупреждение, если файл с данными еще не создан.
        return  # Прерываем дальнейний вывод, потому что оптимизацию пока запускать не на чем.
    selected_strategy_name, selected_strategy_class = render_strategy_selector(available_strategies=available_strategies, label="Стратегия для оптимизации", key="optimization_strategy_selector")  # Показываем выпадающий список всех доступных стратегий для вкладки оптимизации.
    parameter_specs = get_strategy_parameter_specs(selected_strategy_class=selected_strategy_class)
    _, _, _, active_profile_params, _ = load_strategy_profile_bundle(
        selected_symbol=selected_symbol,
        selected_strategy_name=selected_strategy_name,
        selected_strategy_class=selected_strategy_class,
    )
    strategy_param_ranges, display_ranges = render_optimization_controls(
        selected_strategy_class=selected_strategy_class,
        selected_strategy_name=selected_strategy_name,
        initial_params=active_profile_params,
    )  # Динамически рисуем диапазоны "от/до" и получаем словарь диапазонов параметров для выбранной стратегии.
    validation_error = validate_strategy_param_ranges(  # Проверяем диапазоны параметров стратегии перед оптимизацией.
        strategy_param_ranges=strategy_param_ranges, selected_strategy_class=selected_strategy_class
    )  # Проверяем диапазоны параметров стратегии перед оптимизацией.
    if validation_error is not None:  # Проверяем, нашлась ли ошибка валидации диапазонов.
        st.error(validation_error)  # Показываем понятную ошибку, если диапазоны выбраны неудачно.
        return  # Останавливаем запуск оптимизации до исправления диапазонов.
    estimated_combinations, combination_sizes = estimate_optimization_combinations(strategy_param_ranges)
    labeled_combination_sizes = {
        get_parameter_display_name(parameter_name, parameter_specs=parameter_specs): size
        for parameter_name, size in combination_sizes.items()
    }
    st.caption(
        "Размер пространства оптимизации: "
        + ", ".join([f"{parameter}={size}" for parameter, size in labeled_combination_sizes.items()])
        + f" | всего комбинаций: {estimated_combinations:,}"
    )
    method_labels = list(OPTIMIZATION_METHOD_LABEL_TO_VALUE.keys())
    method_default_index = (
        method_labels.index(OPTIMIZATION_METHOD_DEFAULT_LABEL)
        if OPTIMIZATION_METHOD_DEFAULT_LABEL in method_labels
        else 0
    )
    selected_method_label = st.selectbox(
        "Метод оптимизации",
        options=method_labels,
        index=method_default_index,
        key=f"optimization_method_{selected_strategy_name}",
    )
    optimization_mode = OPTIMIZATION_METHOD_LABEL_TO_VALUE.get(selected_method_label, "bruteforce")

    fitness_formula = st.text_input(
        "Формула fitness",
        value=OPTIMIZATION_FITNESS_DEFAULT,
        key=f"optimization_fitness_formula_{selected_strategy_name}",
        help="Например: PnL, PnL - 2*MaxRelDD, PnL/max(1, MaxRelDD).",
    )
    fitness_formula = str(fitness_formula or OPTIMIZATION_FITNESS_DEFAULT).strip() or OPTIMIZATION_FITNESS_DEFAULT

    optimization_max_iterations: int | None = None
    optimization_random_seed: int | None = None
    optimization_random_iterations: int | None = None
    optimization_genetic_settings: dict[str, Any] | None = None

    if optimization_mode == "bruteforce":
        brute_limit_value = int(
            st.number_input(
                "Лимит прогонов (0 = без лимита)",
                min_value=0,
                step=1,
                value=0,
                key=f"optimization_bruteforce_limit_{selected_strategy_name}",
            )
        )
        optimization_max_iterations = brute_limit_value if brute_limit_value > 0 else None
    elif optimization_mode == "random":
        default_random_iterations = (
            min(max(1, estimated_combinations), OPTIMIZATION_RANDOM_DEFAULT_ITERATIONS)
            if estimated_combinations > 0
            else 1
        )
        optimization_random_iterations = int(
            st.number_input(
                "Количество случайных прогонов",
                min_value=1,
                step=1,
                value=int(default_random_iterations),
                key=f"optimization_random_iterations_{selected_strategy_name}",
            )
        )
        fix_random_seed = st.checkbox(
            "Фиксировать random seed",
            value=False,
            key=f"optimization_random_seed_toggle_{selected_strategy_name}",
        )
        if fix_random_seed:
            optimization_random_seed = int(
                st.number_input(
                    "Random seed",
                    min_value=0,
                    step=1,
                    value=42,
                    key=f"optimization_random_seed_{selected_strategy_name}",
                )
            )
    else:
        default_settings = dict(OPTIMIZATION_GENETIC_DEFAULT_SETTINGS)
        with st.expander("Настройки генетического алгоритма", expanded=True):
            col_1, col_2 = st.columns(2)
            with col_1:
                population = int(
                    st.number_input(
                        "Population",
                        min_value=2,
                        step=1,
                        value=int(default_settings["population"]),
                        key=f"optimization_genetic_population_{selected_strategy_name}",
                    )
                )
                generations_max = int(
                    st.number_input(
                        "Максимум поколений",
                        min_value=1,
                        step=1,
                        value=int(default_settings["generations_max"]),
                        key=f"optimization_genetic_generations_max_{selected_strategy_name}",
                    )
                )
                generations_stagnation = int(
                    st.number_input(
                        "Остановка при стагнации (поколений)",
                        min_value=0,
                        step=1,
                        value=int(default_settings["generations_stagnation"]),
                        key=f"optimization_genetic_stagnation_{selected_strategy_name}",
                    )
                )
                tournament_size = int(
                    st.number_input(
                        "Размер турнира",
                        min_value=2,
                        step=1,
                        value=int(default_settings["tournament_size"]),
                        key=f"optimization_genetic_tournament_{selected_strategy_name}",
                    )
                )
            with col_2:
                elite_count = int(
                    st.number_input(
                        "Число элит",
                        min_value=1,
                        step=1,
                        value=int(default_settings["elite_count"]),
                        key=f"optimization_genetic_elite_{selected_strategy_name}",
                    )
                )
                mutation_probability = float(
                    st.number_input(
                        "Вероятность мутации",
                        min_value=0.0,
                        max_value=1.0,
                        step=0.01,
                        value=float(default_settings["mutation_probability"]),
                        format="%.2f",
                        key=f"optimization_genetic_mutation_{selected_strategy_name}",
                    )
                )
                crossover_probability = float(
                    st.number_input(
                        "Вероятность crossover",
                        min_value=0.0,
                        max_value=1.0,
                        step=0.01,
                        value=float(default_settings["crossover_probability"]),
                        format="%.2f",
                        key=f"optimization_genetic_crossover_{selected_strategy_name}",
                    )
                )

        if tournament_size > population:
            tournament_size = population
        if elite_count > population:
            elite_count = population

        optimization_genetic_settings = {
            "population": population,
            "generations_max": generations_max,
            "generations_stagnation": generations_stagnation,
            "mutation_probability": mutation_probability,
            "crossover_probability": crossover_probability,
            "tournament_size": tournament_size,
            "elite_count": elite_count,
        }

        max_eval_input = int(
            st.number_input(
                "Лимит вычислений (0 = без лимита)",
                min_value=0,
                step=1,
                value=0,
                key=f"optimization_genetic_max_iterations_{selected_strategy_name}",
            )
        )
        optimization_max_iterations = max_eval_input if max_eval_input > 0 else None

    expected_evaluations = estimate_expected_optimization_evaluations(
        optimization_mode=optimization_mode,
        estimated_combinations=estimated_combinations,
        brute_force_max_iterations=optimization_max_iterations if optimization_mode == "bruteforce" else None,
        random_iterations=optimization_random_iterations,
        genetic_settings=optimization_genetic_settings,
        genetic_max_iterations=optimization_max_iterations if optimization_mode == "genetic" else None,
    )

    st.caption(f"План прогона: {expected_evaluations:,} из {estimated_combinations:,} комбинаций.")

    estimated_rows = estimate_selected_rows_for_optimization(
        data_file=selected_data_file,
        symbol=selected_symbol,
        timeframe=selected_timeframe,
        start_date=selected_start_date,
        end_date=selected_end_date,
    )
    estimated_runtime_seconds = estimate_optimization_runtime_seconds(
        combinations=expected_evaluations,
        estimated_rows=estimated_rows,
    )
    if estimated_runtime_seconds is None:
        st.caption("Предварительная оценка времени: пока недоступна (нет данных для расчета).")
    else:
        seconds_per_combination = estimated_runtime_seconds / float(max(1, expected_evaluations))
        st.caption(
            "Предварительная оценка времени: "
            f"~{format_duration_mmss(estimated_runtime_seconds)} "
            f"(~{seconds_per_combination:.1f} сек/комб., ~{int(estimated_rows):,} свечей)."
        )
        st.caption("Оценка ориентировочная и может отличаться из-за нагрузки CPU и особенностей стратегии.")
    if optimization_mode in {"random", "genetic"} and expected_evaluations < estimated_combinations:
        st.caption("Используется неполный поиск: часть комбинаций будет пропущена.")

    if expected_evaluations <= 0:
        st.warning("Нет комбинаций для прогона. Укажите корректные диапазоны `от` и `до`.")
    if expected_evaluations > OPTIMIZATION_WARNING_COMBINATIONS:
        st.warning(
            f"Большой запуск: {expected_evaluations:,} комбинаций. "
            "Рекомендуется сузить диапазоны, чтобы сократить время прогона."
        )
    exceeds_hard_limit = expected_evaluations > OPTIMIZATION_MAX_COMBINATIONS
    if exceeds_hard_limit:
        st.error(
            f"Запуск заблокирован: {expected_evaluations:,} комбинаций превышают лимит "
            f"{OPTIMIZATION_MAX_COMBINATIONS:,}. Сузьте диапазоны параметров."
        )

    parameter_labels = {
        parameter_name: get_parameter_display_name(parameter_name, parameter_specs=parameter_specs)
        for parameter_name in strategy_param_ranges.keys()
    }
    labeled_display_ranges = build_labeled_parameter_ranges(display_ranges, parameter_specs=parameter_specs)
    manage_optimization_run(
        selected_strategy_class=selected_strategy_class,
        selected_strategy_name=selected_strategy_name,
        selected_symbol=selected_symbol,
        selected_timeframe=selected_timeframe,
        selected_start_date=selected_start_date,
        selected_end_date=selected_end_date,
        selected_data_file=selected_data_file,
        strategy_param_ranges=strategy_param_ranges,
        parameter_labels=parameter_labels,
        labeled_display_ranges=labeled_display_ranges,
        exceeds_hard_limit=exceeds_hard_limit,
        estimated_combinations=estimated_combinations,
        expected_evaluations=expected_evaluations,
        optimization_mode=optimization_mode,
        fitness_formula=fitness_formula,
        optimization_max_iterations=optimization_max_iterations,
        optimization_random_seed=optimization_random_seed,
        optimization_random_iterations=optimization_random_iterations,
        optimization_genetic_settings=optimization_genetic_settings,
    )
    session_result_data = st.session_state.get(OPTIMIZATION_RESULTS_KEY)
    if optimization_result_matches_scope(
        session_result_data,
        selected_symbol=selected_symbol,
        selected_timeframe=selected_timeframe,
        selected_strategy_name=selected_strategy_name,
    ):
        result_data = session_result_data
    else:
        result_data = None

    if not optimization_result_has_rows(result_data):
        expected_scope_key = build_optimization_scope_key(
            symbol=selected_symbol,
            timeframe=selected_timeframe,
            strategy_name=selected_strategy_name,
        )
        persisted_result_data = load_last_optimization_result(
            file_path=OPTIMIZATION_STORE_FILE,
            scope_key=expected_scope_key,
            ttl_hours=OPTIMIZATION_STORE_TTL_HOURS,
        )
        if (
            isinstance(persisted_result_data, dict)
            and optimization_result_matches_scope(
                persisted_result_data,
                selected_symbol=selected_symbol,
                selected_timeframe=selected_timeframe,
                selected_strategy_name=selected_strategy_name,
            )
        ):
            result_data = persisted_result_data
            st.session_state[OPTIMIZATION_RESULTS_KEY] = persisted_result_data

    if result_data is None:  # Проверяем, запускалась ли оптимизация хотя бы один раз в текущей сессии.
        st.info("После запуска оптимизации здесь появятся лучшая связка параметров и таблица всех результатов.")  # Показываем подсказку, пока результатов еще нет.
        return  # Завершаем функцию, потому что показывать пока нечего.
    show_optimization_results(result_data)  # Показываем метрики и таблицу результатов оптимизации.


def show_profiles_tab(
    available_strategies,
    selected_symbol: str,
):
    st.subheader("🗂️ Профили стратегии")
    st.write(
        "В этом разделе можно управлять active/candidate параметрами и смотреть историю оптимизаций "
        "для выбранной пары и стратегии."
    )
    selected_strategy_name, selected_strategy_class = render_strategy_selector(
        available_strategies=available_strategies,
        label="Стратегия профиля",
        key="profile_strategy_selector",
    )
    parameter_specs = get_strategy_parameter_specs(selected_strategy_class=selected_strategy_class)
    profile_store, profile, _, active_profile_params, candidate_profile_params = load_strategy_profile_bundle(
        selected_symbol=selected_symbol,
        selected_strategy_name=selected_strategy_name,
        selected_strategy_class=selected_strategy_class,
    )

    updated_at = profile.get("updated_at")
    if updated_at:
        st.caption(f"Профиль: {selected_symbol} / {selected_strategy_name} | updated_at={updated_at}")

    active_col, candidate_col = st.columns(2)
    with active_col:
        st.markdown("**Active parameters**")
        st.dataframe(build_parameters_dataframe(active_profile_params, parameter_specs=parameter_specs), width="stretch")
    with candidate_col:
        st.markdown("**Candidate parameters**")
        if candidate_profile_params:
            st.dataframe(build_parameters_dataframe(candidate_profile_params, parameter_specs=parameter_specs), width="stretch")
        else:
            st.info("Candidate-параметры пока не сохранены.")

    promote_col, sync_col, clear_col = st.columns(3)
    with promote_col:
        promote_candidate_clicked = st.button(
            "Сделать candidate активным",
            key=f"profile_promote_candidate_{selected_symbol}_{selected_strategy_name}",
            width="stretch",
            disabled=not bool(candidate_profile_params),
        )
    with sync_col:
        sync_from_backtest_clicked = st.button(
            "Взять active из последнего бектеста",
            key=f"profile_sync_backtest_{selected_symbol}_{selected_strategy_name}",
            width="stretch",
        )
    with clear_col:
        clear_candidate_clicked = st.button(
            "Очистить candidate",
            key=f"profile_clear_candidate_{selected_symbol}_{selected_strategy_name}",
            width="stretch",
            disabled=not bool(candidate_profile_params),
        )

    if promote_candidate_clicked and candidate_profile_params:
        update_active_params(profile, candidate_profile_params)
        save_profiles(profile_store, PROFILE_STORE_FILE)
        st.success("Candidate-параметры перенесены в active-профиль.")

    if sync_from_backtest_clicked:
        backtest_result = st.session_state.get(BACKTEST_RESULTS_KEY)
        if not isinstance(backtest_result, dict):
            st.warning("Нет результатов бектеста в текущей сессии для синхронизации.")
        elif (
            backtest_result.get("strategy_name") != selected_strategy_name
            or (backtest_result.get("symbol") or selected_symbol) != selected_symbol
        ):
            st.warning(
                "Последний бектест относится к другой стратегии или паре. "
                "Запусти бектест для текущего профиля и повтори синхронизацию."
            )
        else:
            strategy_kwargs = backtest_result.get("strategy_kwargs")
            if not isinstance(strategy_kwargs, dict) or not strategy_kwargs:
                st.warning("В последнем бектесте нет параметров для синхронизации.")
            else:
                update_active_params(profile, strategy_kwargs)
                save_profiles(profile_store, PROFILE_STORE_FILE)
                st.success("Active-профиль обновлен параметрами последнего бектеста.")

    if clear_candidate_clicked and candidate_profile_params:
        update_candidate_params(profile, {})
        save_profiles(profile_store, PROFILE_STORE_FILE)
        st.success("Candidate-параметры очищены.")

    optimization_history = profile.get("optimization_history")
    if isinstance(optimization_history, list) and optimization_history:
        history_dataframe = pd.DataFrame(optimization_history)
        if not history_dataframe.empty and "created_at" in history_dataframe.columns:
            history_dataframe = history_dataframe.sort_values("created_at", ascending=False).reset_index(drop=True)
        st.subheader("История оптимизаций профиля")
        st.dataframe(history_dataframe.head(200), width="stretch")
    else:
        st.info("История оптимизаций для этого профиля пока пуста.")


def main():  # Создаем главную функцию приложения Streamlit.
    configure_page()  # Сначала настраиваем страницу и выводим заголовок.
    available_strategies = get_available_strategies()  # Загружаем все доступные стратегии из папки strategies один раз на запуск страницы.
    selected_symbol, selected_timeframe, selected_start_date, selected_end_date = render_sidebar()  # Затем рисуем боковую панель и получаем выбор пользователя.
    data_tab, backtest_tab, optimization_tab, profiles_tab = st.tabs(["📊 Данные и график", "🧪 Бектест", "⚡ Оптимизация", "🗂️ Профили"])  # Создаем вкладки для данных, бектеста, оптимизации и профилей.
    with data_tab:  # Открываем контекст первой вкладки.
        show_market_data_tab(selected_symbol, selected_timeframe, selected_start_date, selected_end_date)  # Рисуем содержимое вкладки с загрузкой данных и графиком.
    with backtest_tab:  # Открываем контекст второй вкладки.
        show_backtest_tab(
            available_strategies=available_strategies,
            selected_symbol=selected_symbol,
            selected_timeframe=selected_timeframe,
            selected_start_date=selected_start_date,
            selected_end_date=selected_end_date,
        )
    with profiles_tab:
        show_profiles_tab(
            available_strategies=available_strategies,
            selected_symbol=selected_symbol,
        )
    with optimization_tab:  # Открываем контекст третьей вкладки.
        show_optimization_tab(
            available_strategies=available_strategies,
            selected_symbol=selected_symbol,
            selected_timeframe=selected_timeframe,
            selected_start_date=selected_start_date,
            selected_end_date=selected_end_date,
        )


if __name__ == "__main__":  # Проверяем, что файл app.py запущен как основной модуль.
    main()  # Запускаем приложение.
