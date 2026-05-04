from __future__ import annotations

import ast
import math
import operator
import random
from itertools import product
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import backtrader as bt
import pandas as pd

from utils.strategy_loader import load_available_strategies

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_DIR / "data.csv"
INITIAL_CASH = 10_000.0
COMMISSION = 0.001
DEFAULT_FAST_PERIOD = 10
DEFAULT_SLOW_PERIOD = 20
DEFAULT_STRATEGY_NAME = "MovingAverageCrossStrategy"
MAX_INDICATOR_POINTS_PER_LINE = 12_000
MAX_EQUITY_CURVE_POINTS = 20_000
OPTIMIZATION_MEMORY_SAFE_WORKLOAD = 5_000_000
OPTIMIZATION_MODE_BRUTE_FORCE = "bruteforce"
OPTIMIZATION_MODE_RANDOM = "random"
OPTIMIZATION_MODE_GENETIC = "genetic"

_FORMULA_BIN_OPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_FORMULA_UNARY_OPS: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}
_FORMULA_FUNCTIONS: dict[str, Callable[..., float]] = {
    "abs": abs,
    "min": min,
    "max": max,
    "round": round,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "pow": pow,
}


class OptimizationCancelledError(RuntimeError):
    """Raised when optimization is cancelled from the UI controls."""


def _to_float_or_none(value: Any) -> float | None:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(normalized) or not math.isfinite(normalized):
        return None
    return normalized


def _infer_indicator_panel(indicator_name: str) -> str:
    normalized_name = indicator_name.lower()
    if any(token in normalized_name for token in ("rsi", "smi", "stoch", "macd", "momentum", "roc", "adx", "cci", "mfi")):
        return "oscillator"
    if any(token in normalized_name for token in ("cross", "signal", "hist")):
        return "oscillator"
    return "price"


def _indicator_lines_to_points(indicator_line, data_length: int, market_data_index: pd.Index) -> list[dict[str, Any]]:
    try:
        line_values = list(indicator_line.array)
    except Exception:
        line_values = []

    max_points = max(0, min(len(line_values), data_length))
    points: list[dict[str, Any]] = []
    for index in range(data_length):
        if index >= max_points:
            continue
        value = _to_float_or_none(line_values[index])
        if value is None:
            continue
        points.append(
            {
                "datetime": market_data_index[index],
                "value": value,
            }
        )
    return points


def _normalize_line_aliases(lines_obj: Any) -> list[str]:
    aliases: list[str] = []
    for getter_name in ("getlinealiases", "_getlines"):
        getter = getattr(lines_obj, getter_name, None)
        if not callable(getter):
            continue
        try:
            raw_aliases = getter()
        except Exception:
            continue
        if not isinstance(raw_aliases, (list, tuple)):
            continue
        aliases = [str(alias).strip() for alias in raw_aliases if str(alias).strip()]
        if aliases:
            break
    return aliases


def _iter_indicator_lines(indicator_value: Any) -> list[tuple[int, str | None, Any]]:
    lines_obj = getattr(indicator_value, "lines", None)
    if lines_obj is None:
        return []

    line_entries: list[tuple[int, str | None, Any]] = []
    line_aliases = _normalize_line_aliases(lines_obj)
    if line_aliases:
        for line_index, line_alias in enumerate(line_aliases):
            try:
                line_value = lines_obj[line_index]
            except Exception:
                continue
            line_entries.append((line_index, line_alias, line_value))
        if line_entries:
            return line_entries

    if isinstance(lines_obj, (list, tuple)):
        for line_index, line_value in enumerate(lines_obj):
            line_entries.append((line_index, None, line_value))
        return line_entries

    try:
        first_line = lines_obj[0]
    except Exception:
        return []
    return [(0, None, first_line)]


def _collect_indicator_metadata(
    indicator_name: str,
    indicator_config: dict[str, Any] | None,
    line_index: int,
    line_count: int,
    line_alias: str | None = None,
) -> dict[str, Any]:
    metadata = indicator_config or {}
    if line_count > 1:
        line_labels = metadata.get("line_labels", {})
        label = metadata.get("label", indicator_name).replace("_", " ").title()
        if isinstance(line_labels, dict):
            explicit_label = line_labels.get(line_index) or line_labels.get(str(line_index))
            if explicit_label is None and line_alias:
                explicit_label = line_labels.get(line_alias)
            if explicit_label:
                label = str(explicit_label)
        elif line_alias:
            label = f"{label} {line_alias}"
        else:
            label = f"{label} line {line_index + 1}"
    else:
        label = str(metadata.get("label", indicator_name)).replace("_", " ").title()

    return {
        "id": indicator_name if line_count == 1 else f"{indicator_name}_line_{line_index}",
        "label": label,
        "panel": str(metadata.get("panel", _infer_indicator_panel(indicator_name))),
        "color": str(metadata.get("color", "#38bdf8")),
        "default_visible": bool(metadata.get("default_visible", True)),
        "line_width": float(metadata.get("line_width", 1.2)),
        "source_attr": indicator_name,
        "line_index": line_index,
    }


def _downsample_records(records: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
    if max_points <= 0:
        return []

    records_count = len(records)
    if records_count <= max_points:
        return records
    if max_points == 1:
        return [records[-1]]

    last_index = records_count - 1
    sampled_records: list[dict[str, Any]] = []
    for target_index in range(max_points):
        source_index = int(target_index * last_index / (max_points - 1))
        sampled_records.append(records[source_index])
    return sampled_records


def _summarize_indicator_sampling(indicator_payloads: list[dict[str, Any]], max_points_per_indicator: int) -> dict[str, Any]:
    total_original_points = 0
    total_stored_points = 0
    sampled_series_count = 0

    for payload in indicator_payloads:
        if not isinstance(payload, dict):
            continue
        sampling_info = payload.get("sampling")
        if not isinstance(sampling_info, dict):
            stored_points = len(payload.get("points", [])) if isinstance(payload.get("points"), list) else 0
            original_points = stored_points
        else:
            original_points = int(sampling_info.get("original_points", 0) or 0)
            stored_points = int(sampling_info.get("stored_points", 0) or 0)

        total_original_points += original_points
        total_stored_points += stored_points
        if original_points > stored_points:
            sampled_series_count += 1

    return {
        "max_points_per_indicator": int(max_points_per_indicator),
        "total_original_points": int(total_original_points),
        "total_stored_points": int(total_stored_points),
        "sampled_series_count": int(sampled_series_count),
    }


def collect_strategy_indicators(
    strategy: bt.Strategy,
    market_data_index: pd.Index,
    max_points_per_indicator: int = MAX_INDICATOR_POINTS_PER_LINE,
) -> list[dict[str, Any]]:
    strategy_config = getattr(strategy.__class__, "CHART_INDICATOR_CONFIG", {})
    if not isinstance(strategy_config, dict):
        return []

    data_length = len(market_data_index)
    if data_length == 0:
        return []

    strategy_indicators: list[dict[str, Any]] = []
    for attribute_name, indicator_config in strategy_config.items():
        if not isinstance(attribute_name, str) or not attribute_name.strip():
            continue

        if not isinstance(indicator_config, dict):
            indicator_config = {}

        attribute_value = getattr(strategy, attribute_name, None)
        if attribute_value is None:
            continue

        indicator_lines = _iter_indicator_lines(attribute_value)
        if not indicator_lines:
            continue
        line_count = len(indicator_lines)

        for line_index, line_alias, line_value in indicator_lines:
            try:
                points = _indicator_lines_to_points(line_value, data_length=data_length, market_data_index=market_data_index)
            except Exception:
                points = []
            if not points:
                continue

            metadata = _collect_indicator_metadata(
                indicator_name=attribute_name,
                indicator_config=indicator_config,
                line_index=line_index,
                line_count=line_count,
                line_alias=line_alias,
            )
            original_points = len(points)
            sampled_points = _downsample_records(points, max_points=max_points_per_indicator)
            metadata["points"] = sampled_points
            metadata["sampling"] = {
                "original_points": int(original_points),
                "stored_points": int(len(sampled_points)),
                "max_points": int(max_points_per_indicator),
            }
            strategy_indicators.append(metadata)

    return strategy_indicators


def load_market_data(
    data_file: Path,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    if not data_file.exists():
        raise FileNotFoundError(
            "Market data file not found. Download required data first or adjust cache context."
        )

    dataframe = pd.read_csv(data_file)
    required_columns = ["datetime", "open", "high", "low", "close", "volume"]
    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(f"Market data file is missing columns: {', '.join(missing_columns)}")

    dataframe["datetime"] = pd.to_datetime(dataframe["datetime"], utc=True)
    dataframe["datetime"] = dataframe["datetime"].dt.tz_convert(None)
    dataframe = dataframe.sort_values("datetime").reset_index(drop=True)
    dataframe = dataframe[["datetime", "open", "high", "low", "close", "volume"]].copy()
    dataframe[["open", "high", "low", "close", "volume"]] = dataframe[
        ["open", "high", "low", "close", "volume"]
    ].astype(float)
    if start_date is not None:
        start_time = datetime.combine(start_date, datetime.min.time())
        dataframe = dataframe[dataframe["datetime"] >= start_time]

    if end_date is not None:
        end_time = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
        dataframe = dataframe[dataframe["datetime"] < end_time]

    dataframe = dataframe.set_index("datetime")
    return dataframe


def ensure_market_data_not_empty(
    dataframe: pd.DataFrame,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
) -> None:
    if dataframe.empty:
        if start_date is not None and end_date is not None:
            raise ValueError(
                "No market data available for the selected date range. "
                f"Please select a different period: from {start_date} to {end_date}."
            )
        raise ValueError("Market data file is empty.")


def _insufficient_market_data_message(start_date: date | None = None, end_date: date | None = None) -> str:
    if start_date is not None and end_date is not None:
        return (
            "Not enough market data to evaluate the selected strategy in the requested range. "
            f"Please expand the period from {start_date} to {end_date} or reduce indicator periods."
        )
    return (
        "Not enough market data to evaluate the selected strategy. "
        "Please expand the date range or reduce indicator periods."
    )


def _run_cerebro_with_short_data_fallback(
    build_cerebro: Callable[[], bt.Cerebro],
    *,
    run_kwargs: dict[str, Any] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[bt.Cerebro, Any]:
    base_run_kwargs = dict(run_kwargs or {})
    attempts = [base_run_kwargs]
    if base_run_kwargs.get("runonce", True):
        attempts.append({**base_run_kwargs, "runonce": False})

    last_index_error: IndexError | None = None
    for attempt_kwargs in attempts:
        cerebro = build_cerebro()
        try:
            return cerebro, cerebro.run(**attempt_kwargs)
        except IndexError as exc:
            last_index_error = exc

    raise ValueError(_insufficient_market_data_message(start_date=start_date, end_date=end_date)) from last_index_error


def create_cerebro_with_data(market_data: pd.DataFrame, initial_cash: float, commission: float) -> bt.Cerebro:
    # Disable default Backtrader observers/stats to reduce UI backtest latency.
    cerebro = bt.Cerebro(stdstats=False)
    data_feed = bt.feeds.PandasData(dataname=market_data.copy())
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(initial_cash)
    cerebro.broker.setcommission(commission=commission)
    return cerebro


def prepare_strategy_kwargs(strategy_kwargs: dict[str, Any] | None, commission: float) -> dict[str, Any]:
    prepared_kwargs = dict(strategy_kwargs or {})
    prepared_kwargs.setdefault("commission", commission)
    return prepared_kwargs


def _normalize_scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return value
    if value is None:
        return None

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _normalize_scalar(item_method())
        except Exception:
            pass

    try:
        return float(value)
    except Exception:
        return str(value)


def _normalize_range_values(values: Any) -> list[Any]:
    if values is None:
        return []

    if isinstance(values, range):
        return [_normalize_scalar(item) for item in values]

    if isinstance(values, (list, tuple, set)):
        return [_normalize_scalar(item) for item in values]

    return [_normalize_scalar(values)]


def _compute_drawdown_metrics(equity_curve: list[dict[str, Any]] | None, initial_cash: float) -> tuple[float, float]:
    peak = float(initial_cash)
    max_drawdown_abs = 0.0
    max_drawdown_pct = 0.0

    for point in equity_curve or []:
        if not isinstance(point, dict):
            continue
        equity_value = _to_float_or_none(point.get("equity"))
        if equity_value is None:
            continue
        if equity_value > peak:
            peak = float(equity_value)
            continue
        drawdown_abs = float(peak - equity_value)
        if drawdown_abs > max_drawdown_abs:
            max_drawdown_abs = drawdown_abs
        if peak > 0:
            drawdown_pct = 100.0 * drawdown_abs / float(peak)
            if drawdown_pct > max_drawdown_pct:
                max_drawdown_pct = float(drawdown_pct)

    return float(max_drawdown_abs), float(max_drawdown_pct)


def _extract_trade_metrics(strategy: bt.Strategy) -> dict[str, Any]:
    raw_trades = getattr(strategy, "trades_log", [])
    if not isinstance(raw_trades, list):
        raw_trades = []

    trade_count = 0
    winning_trades = 0
    losing_trades = 0
    gross_profit = 0.0
    gross_loss_abs = 0.0
    take_profit_trades = 0
    stop_loss_trades = 0
    other_exit_trades = 0
    close_after_entry_count = 0
    close_after_dca1_count = 0
    close_after_dca2_count = 0
    close_after_dca3plus_count = 0
    has_exit_reason_stats = False
    has_averaging_stats = False

    for trade in raw_trades:
        if not isinstance(trade, dict):
            continue
        pnl_value = _to_float_or_none(trade.get("pnl_after_commission"))
        if pnl_value is None:
            pnl_value = _to_float_or_none(trade.get("pnl"))
        if pnl_value is None:
            continue
        trade_count += 1
        if pnl_value > 0:
            winning_trades += 1
            gross_profit += float(pnl_value)
        elif pnl_value < 0:
            losing_trades += 1
            gross_loss_abs += abs(float(pnl_value))

        exit_reason = trade.get("exit_reason")
        if isinstance(exit_reason, str) and exit_reason.strip():
            has_exit_reason_stats = True
            normalized_exit_reason = exit_reason.strip().lower()
            if normalized_exit_reason == "take_profit":
                take_profit_trades += 1
            elif normalized_exit_reason == "stop_loss":
                stop_loss_trades += 1
            else:
                other_exit_trades += 1

        averaging_count_raw = _to_float_or_none(trade.get("averaging_count"))
        if averaging_count_raw is not None:
            has_averaging_stats = True
            averaging_count = max(0, int(round(float(averaging_count_raw))))
            if averaging_count <= 0:
                close_after_entry_count += 1
            elif averaging_count == 1:
                close_after_dca1_count += 1
            elif averaging_count == 2:
                close_after_dca2_count += 1
            else:
                close_after_dca3plus_count += 1

    if has_exit_reason_stats:
        assigned_exit_count = take_profit_trades + stop_loss_trades + other_exit_trades
        if assigned_exit_count < trade_count:
            other_exit_trades += int(trade_count - assigned_exit_count)
    else:
        take_profit_trades = 0
        stop_loss_trades = 0
        other_exit_trades = 0

    if has_averaging_stats:
        assigned_averaging_count = (
            close_after_entry_count
            + close_after_dca1_count
            + close_after_dca2_count
            + close_after_dca3plus_count
        )
        if assigned_averaging_count < trade_count:
            close_after_entry_count += int(trade_count - assigned_averaging_count)
    else:
        close_after_entry_count = 0
        close_after_dca1_count = 0
        close_after_dca2_count = 0
        close_after_dca3plus_count = 0

    win_rate = 100.0 * float(winning_trades) / float(trade_count) if trade_count > 0 else 0.0
    return {
        "trade_count": int(trade_count),
        "winning_trades": int(winning_trades),
        "losing_trades": int(losing_trades),
        "gross_profit": float(gross_profit),
        "gross_loss_abs": float(gross_loss_abs),
        "win_rate": float(win_rate),
        "take_profit_trades": int(take_profit_trades),
        "stop_loss_trades": int(stop_loss_trades),
        "other_exit_trades": int(other_exit_trades),
        "close_after_entry_count": int(close_after_entry_count),
        "close_after_dca1_count": int(close_after_dca1_count),
        "close_after_dca2_count": int(close_after_dca2_count),
        "close_after_dca3plus_count": int(close_after_dca3plus_count),
        "has_exit_reason_stats": bool(has_exit_reason_stats),
        "has_averaging_stats": bool(has_averaging_stats),
    }


def _collect_strategy_metrics(strategy: bt.Strategy, initial_cash: float, final_balance: float) -> dict[str, Any]:
    pnl = float(final_balance) - float(initial_cash)
    return_pct = 100.0 * pnl / float(initial_cash) if float(initial_cash) else 0.0
    max_drawdown_abs, max_drawdown_pct = _compute_drawdown_metrics(
        getattr(strategy, "equity_curve", None),
        initial_cash=float(initial_cash),
    )
    trade_metrics = _extract_trade_metrics(strategy)
    trade_count = int(trade_metrics.get("trade_count", 0) or 0)
    winning_trades = int(trade_metrics.get("winning_trades", 0) or 0)
    losing_trades = int(trade_metrics.get("losing_trades", 0) or 0)
    gross_profit = float(trade_metrics.get("gross_profit", 0.0) or 0.0)
    gross_loss_abs = float(trade_metrics.get("gross_loss_abs", 0.0) or 0.0)
    win_rate = float(trade_metrics.get("win_rate", 0.0) or 0.0)

    if gross_loss_abs > 0:
        profit_factor = float(gross_profit) / float(gross_loss_abs)
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    avg_trade_pnl = pnl / float(trade_count) if trade_count > 0 else 0.0

    if max_drawdown_abs > 0:
        recovery_factor = pnl / float(max_drawdown_abs)
    elif pnl > 0:
        recovery_factor = float("inf")
    else:
        recovery_factor = 0.0

    return {
        "return_pct": float(return_pct),
        "max_drawdown_abs": float(max_drawdown_abs),
        "max_drawdown_pct": float(max_drawdown_pct),
        "trade_count": int(trade_count),
        "winning_trades": int(winning_trades),
        "losing_trades": int(losing_trades),
        "win_rate": float(win_rate),
        "gross_profit": float(gross_profit),
        "gross_loss_abs": float(gross_loss_abs),
        "profit_factor": float(profit_factor),
        "avg_trade_pnl": float(avg_trade_pnl),
        "recovery_factor": float(recovery_factor),
        "take_profit_trades": int(trade_metrics.get("take_profit_trades", 0) or 0),
        "stop_loss_trades": int(trade_metrics.get("stop_loss_trades", 0) or 0),
        "other_exit_trades": int(trade_metrics.get("other_exit_trades", 0) or 0),
        "close_after_entry_count": int(trade_metrics.get("close_after_entry_count", 0) or 0),
        "close_after_dca1_count": int(trade_metrics.get("close_after_dca1_count", 0) or 0),
        "close_after_dca2_count": int(trade_metrics.get("close_after_dca2_count", 0) or 0),
        "close_after_dca3plus_count": int(trade_metrics.get("close_after_dca3plus_count", 0) or 0),
        "has_exit_reason_stats": bool(trade_metrics.get("has_exit_reason_stats", False)),
        "has_averaging_stats": bool(trade_metrics.get("has_averaging_stats", False)),
    }


def _validate_formula_ast(node: ast.AST) -> None:
    if isinstance(node, ast.Expression):
        _validate_formula_ast(node.body)
        return

    if isinstance(node, ast.BinOp):
        if type(node.op) not in _FORMULA_BIN_OPS:
            raise ValueError(f"Unsupported operator in fitness formula: {type(node.op).__name__}")
        _validate_formula_ast(node.left)
        _validate_formula_ast(node.right)
        return

    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _FORMULA_UNARY_OPS:
            raise ValueError(f"Unsupported unary operator in fitness formula: {type(node.op).__name__}")
        _validate_formula_ast(node.operand)
        return

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FORMULA_FUNCTIONS:
            raise ValueError("Unsupported function in fitness formula.")
        if node.keywords:
            raise ValueError("Keyword arguments are not supported in fitness formula.")
        for argument in node.args:
            _validate_formula_ast(argument)
        return

    if isinstance(node, ast.Name):
        return

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return
        raise ValueError("Only numeric constants are supported in fitness formula.")

    raise ValueError(f"Unsupported syntax in fitness formula: {type(node).__name__}")


def _eval_formula_ast(node: ast.AST, variables: dict[str, float]) -> float:
    if isinstance(node, ast.Expression):
        return _eval_formula_ast(node.body, variables)

    if isinstance(node, ast.BinOp):
        operation = _FORMULA_BIN_OPS[type(node.op)]
        left_value = _eval_formula_ast(node.left, variables)
        right_value = _eval_formula_ast(node.right, variables)
        return float(operation(left_value, right_value))

    if isinstance(node, ast.UnaryOp):
        operation = _FORMULA_UNARY_OPS[type(node.op)]
        operand_value = _eval_formula_ast(node.operand, variables)
        return float(operation(operand_value))

    if isinstance(node, ast.Call):
        function_name = node.func.id
        function = _FORMULA_FUNCTIONS[function_name]
        arguments = [_eval_formula_ast(argument, variables) for argument in node.args]
        return float(function(*arguments))

    if isinstance(node, ast.Name):
        return float(variables.get(node.id, 0.0))

    if isinstance(node, ast.Constant):
        return float(node.value)

    raise ValueError(f"Unsupported syntax in fitness formula: {type(node).__name__}")


def _build_fitness_variables(result_record: dict[str, Any]) -> dict[str, float]:
    pnl = _to_float_or_none(result_record.get("pnl")) or 0.0
    final_balance = _to_float_or_none(result_record.get("final_balance")) or 0.0
    return_pct = _to_float_or_none(result_record.get("return_pct")) or 0.0
    max_drawdown_abs = _to_float_or_none(result_record.get("max_drawdown_abs")) or 0.0
    max_drawdown_pct = _to_float_or_none(result_record.get("max_drawdown_pct")) or 0.0
    trade_count = _to_float_or_none(result_record.get("trade_count")) or 0.0
    winning_trades = _to_float_or_none(result_record.get("winning_trades")) or 0.0
    losing_trades = _to_float_or_none(result_record.get("losing_trades")) or 0.0
    win_rate = _to_float_or_none(result_record.get("win_rate")) or 0.0
    gross_profit = _to_float_or_none(result_record.get("gross_profit")) or 0.0
    gross_loss_abs = _to_float_or_none(result_record.get("gross_loss_abs")) or 0.0
    profit_factor = _to_float_or_none(result_record.get("profit_factor"))
    avg_trade_pnl = _to_float_or_none(result_record.get("avg_trade_pnl")) or 0.0
    recovery_factor = _to_float_or_none(result_record.get("recovery_factor"))

    variables = {
        "PnL": float(pnl),
        "pnl": float(pnl),
        "Profit": float(pnl),
        "profit": float(pnl),
        "FinalBalance": float(final_balance),
        "final_balance": float(final_balance),
        "Ret": float(return_pct),
        "ReturnPct": float(return_pct),
        "return_pct": float(return_pct),
        "MaxDD": float(max_drawdown_abs),
        "max_drawdown_abs": float(max_drawdown_abs),
        "MaxRelDD": float(max_drawdown_pct),
        "max_drawdown_pct": float(max_drawdown_pct),
        "TCount": float(trade_count),
        "TradeCount": float(trade_count),
        "trade_count": float(trade_count),
        "WinTrades": float(winning_trades),
        "winning_trades": float(winning_trades),
        "LosTrades": float(losing_trades),
        "losing_trades": float(losing_trades),
        "WinRate": float(win_rate),
        "win_rate": float(win_rate),
        "GrossProfit": float(gross_profit),
        "gross_profit": float(gross_profit),
        "GrossLoss": float(gross_loss_abs),
        "gross_loss_abs": float(gross_loss_abs),
        "AvgTPnL": float(avg_trade_pnl),
        "avg_trade_pnl": float(avg_trade_pnl),
    }

    if profit_factor is not None and math.isfinite(float(profit_factor)):
        variables["ProfitFactor"] = float(profit_factor)
        variables["profit_factor"] = float(profit_factor)
    if recovery_factor is not None and math.isfinite(float(recovery_factor)):
        variables["Recovery"] = float(recovery_factor)
        variables["recovery_factor"] = float(recovery_factor)

    return variables


def _build_fitness_evaluator(fitness_formula: str | None) -> Callable[[dict[str, Any]], float]:
    normalized_formula = str(fitness_formula or "").strip()
    if not normalized_formula:
        normalized_formula = "PnL"

    parsed_formula = ast.parse(normalized_formula, mode="eval")
    _validate_formula_ast(parsed_formula)

    def evaluate(result_record: dict[str, Any]) -> float:
        variables = _build_fitness_variables(result_record)
        try:
            value = _eval_formula_ast(parsed_formula, variables)
        except ZeroDivisionError:
            return float("-inf")
        if not math.isfinite(value):
            return float("-inf")
        return float(value)

    return evaluate


def _generate_random_combinations(
    *,
    parameter_values: list[list[Any]],
    sample_size: int,
    rng: random.Random,
) -> list[tuple[Any, ...]]:
    if sample_size <= 0 or not parameter_values:
        return []

    total_combinations = 1
    for values in parameter_values:
        current_size = len(values)
        if current_size <= 0:
            return []
        total_combinations *= current_size

    target_size = min(int(sample_size), int(total_combinations))
    if target_size <= 0:
        return []

    if total_combinations <= 200_000 and target_size >= total_combinations:
        combinations = list(product(*parameter_values))
        rng.shuffle(combinations)
        return combinations[:target_size]

    seen: set[tuple[Any, ...]] = set()
    attempts_limit = max(1_000, target_size * 40)
    attempts = 0

    while len(seen) < target_size and attempts < attempts_limit:
        candidate = tuple(rng.choice(values) for values in parameter_values)
        seen.add(candidate)
        attempts += 1

    if len(seen) < target_size and total_combinations <= 250_000:
        for candidate in product(*parameter_values):
            seen.add(tuple(candidate))
            if len(seen) >= target_size:
                break

    sampled = list(seen)
    rng.shuffle(sampled)
    return sampled[:target_size]


def _estimate_genetic_evaluations(
    *,
    combinations_total: int,
    max_iterations: int | None,
    genetic_settings: dict[str, Any] | None,
) -> int:
    settings = genetic_settings if isinstance(genetic_settings, dict) else {}
    population = int(settings.get("population", 8) or 8)
    generations_max = int(settings.get("generations_max", 20) or 20)
    estimated = max(1, population) * max(1, generations_max)

    if max_iterations is not None and int(max_iterations) > 0:
        estimated = min(estimated, int(max_iterations))

    if combinations_total > 0:
        estimated = min(estimated, int(combinations_total))

    return max(1, int(estimated))


def estimate_optimization_combinations(normalized_ranges: dict[str, list[Any]]) -> int:
    if not normalized_ranges:
        return 0

    combinations_total = 1
    for values in normalized_ranges.values():
        current_size = len(values)
        if current_size <= 0:
            return 0
        combinations_total *= current_size
    return combinations_total


def _collect_strategy_params(strategy: bt.Strategy) -> dict[str, Any]:
    collected: dict[str, Any] = {}
    params_obj = getattr(strategy, "params", None)
    if params_obj is None:
        return collected

    keys_method = getattr(params_obj, "_getkeys", None)
    if callable(keys_method):
        for name in keys_method():
            collected[name] = _normalize_scalar(getattr(params_obj, name))
        return collected

    for name in dir(params_obj):
        if name.startswith("_"):
            continue
        value = getattr(params_obj, name)
        if callable(value):
            continue
        collected[name] = _normalize_scalar(value)
    return collected


def _extract_strategy_final_balance(strategy: bt.Strategy, initial_cash: float) -> float:
    # In Backtrader optimization all strategy instances can end up pointing to a shared broker
    # object after the run. Prefer per-strategy snapshots captured during/at the end of each run.
    final_snapshot = _to_float_or_none(getattr(strategy, "final_portfolio_value", None))
    if final_snapshot is not None:
        return float(final_snapshot)

    equity_curve = getattr(strategy, "equity_curve", None)
    if isinstance(equity_curve, list) and equity_curve:
        last_point = equity_curve[-1]
        if isinstance(last_point, dict):
            equity_value = _to_float_or_none(last_point.get("equity"))
            if equity_value is not None:
                return float(equity_value)

    try:
        return float(strategy.broker.getvalue())
    except Exception:
        return float(initial_cash)


def run_backtest(
    strategy_class: type[bt.Strategy],
    data_file: Path = DATA_FILE,
    initial_cash: float = INITIAL_CASH,
    commission: float = COMMISSION,
    strategy_kwargs: dict[str, Any] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    strategy_kwargs = prepare_strategy_kwargs(strategy_kwargs=strategy_kwargs, commission=commission)
    market_data = load_market_data(data_file=data_file, start_date=start_date, end_date=end_date)
    ensure_market_data_not_empty(market_data, start_date=start_date, end_date=end_date)

    def build_cerebro() -> bt.Cerebro:
        cerebro = create_cerebro_with_data(market_data=market_data, initial_cash=initial_cash, commission=commission)
        cerebro.addstrategy(strategy_class, **strategy_kwargs)
        return cerebro

    starting_balance = float(initial_cash)
    cerebro, strategies = _run_cerebro_with_short_data_fallback(
        build_cerebro,
        start_date=start_date,
        end_date=end_date,
    )
    strategy = strategies[0]
    final_balance = float(cerebro.broker.getvalue())

    trades_log = list(getattr(strategy, "trades_log", []))
    raw_equity_curve = list(getattr(strategy, "equity_curve", []))
    raw_equity_points = len(raw_equity_curve)
    equity_curve = _downsample_records(raw_equity_curve, max_points=MAX_EQUITY_CURVE_POINTS)
    strategy_indicators = collect_strategy_indicators(
        strategy=strategy,
        market_data_index=market_data.index,
        max_points_per_indicator=MAX_INDICATOR_POINTS_PER_LINE,
    )
    sampling_metadata = {
        "equity_curve": {
            "original_points": int(raw_equity_points),
            "stored_points": int(len(equity_curve)),
            "max_points": int(MAX_EQUITY_CURVE_POINTS),
        },
        "indicators": _summarize_indicator_sampling(
            indicator_payloads=strategy_indicators,
            max_points_per_indicator=MAX_INDICATOR_POINTS_PER_LINE,
        ),
    }

    return starting_balance, final_balance, trades_log, equity_curve, strategy_indicators, sampling_metadata


def run_optimization(
    strategy_class: type[bt.Strategy],
    data_file: Path = DATA_FILE,
    strategy_param_ranges: dict[str, Any] | None = None,
    initial_cash: float = INITIAL_CASH,
    commission: float = COMMISSION,
    strategy_kwargs: dict[str, Any] | None = None,
    target_param: str | None = None,
    fixed_params: dict[str, Any] | None = None,
    symbol: str | None = None,
    strategy_name: str | None = None,
    source: str = "manual",
    timeframe: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    max_combinations: int | None = None,
    optimization_mode: str = OPTIMIZATION_MODE_BRUTE_FORCE,
    fitness_formula: str | None = "PnL",
    max_iterations: int | None = None,
    random_seed: int | None = None,
    random_iterations: int | None = None,
    genetic_settings: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    control_callback: Callable[[], None] | None = None,
) -> list[dict[str, Any]]:
    base_strategy_kwargs = prepare_strategy_kwargs(strategy_kwargs=strategy_kwargs, commission=commission)
    if fixed_params:
        base_strategy_kwargs.update(dict(fixed_params))

    mode_aliases = {
        "": OPTIMIZATION_MODE_BRUTE_FORCE,
        "auto": OPTIMIZATION_MODE_BRUTE_FORCE,
        "default": OPTIMIZATION_MODE_BRUTE_FORCE,
        OPTIMIZATION_MODE_BRUTE_FORCE: OPTIMIZATION_MODE_BRUTE_FORCE,
        "brute_force": OPTIMIZATION_MODE_BRUTE_FORCE,
        "brute-force": OPTIMIZATION_MODE_BRUTE_FORCE,
        OPTIMIZATION_MODE_RANDOM: OPTIMIZATION_MODE_RANDOM,
        "random_search": OPTIMIZATION_MODE_RANDOM,
        "random-search": OPTIMIZATION_MODE_RANDOM,
        OPTIMIZATION_MODE_GENETIC: OPTIMIZATION_MODE_GENETIC,
    }
    normalized_mode_key = str(optimization_mode or "").strip().lower()
    normalized_mode = mode_aliases.get(normalized_mode_key)
    if normalized_mode is None:
        raise ValueError(f"Unknown optimization mode '{optimization_mode}'.")

    normalized_max_iterations = int(max_iterations) if max_iterations is not None else 0
    if normalized_max_iterations < 0:
        raise ValueError("max_iterations cannot be negative.")
    brute_force_iteration_limit = (
        normalized_max_iterations
        if normalized_mode == OPTIMIZATION_MODE_BRUTE_FORCE and normalized_max_iterations > 0
        else None
    )

    raw_ranges = dict(strategy_param_ranges or {})
    if target_param is not None:
        if target_param not in raw_ranges:
            raise ValueError(f"Target parameter '{target_param}' was not provided in strategy_param_ranges.")
        raw_ranges = {target_param: raw_ranges[target_param]}

    normalized_ranges: dict[str, list[Any]] = {}
    for parameter_name, values in raw_ranges.items():
        normalized_values = _normalize_range_values(values)
        if normalized_values:
            normalized_ranges[parameter_name] = normalized_values

    if not normalized_ranges:
        return []

    combinations_total = estimate_optimization_combinations(normalized_ranges)
    if combinations_total <= 0:
        return []
    if (
        normalized_mode == OPTIMIZATION_MODE_BRUTE_FORCE
        and brute_force_iteration_limit is None
        and max_combinations is not None
        and combinations_total > max_combinations
    ):
        raise ValueError(
            f"Optimization combinations limit exceeded: {combinations_total:,} > {int(max_combinations):,}."
        )

    parameter_names = list(normalized_ranges.keys())
    parameter_values = [normalized_ranges[name] for name in parameter_names]

    if normalized_mode == OPTIMIZATION_MODE_RANDOM:
        requested_random_iterations = int(random_iterations) if random_iterations is not None else 0
        if requested_random_iterations <= 0:
            requested_random_iterations = (
                normalized_max_iterations if normalized_max_iterations > 0 else min(combinations_total, 5_000)
            )
        progress_total = min(combinations_total, max(1, requested_random_iterations))
    elif normalized_mode == OPTIMIZATION_MODE_GENETIC:
        progress_total = _estimate_genetic_evaluations(
            combinations_total=combinations_total,
            max_iterations=normalized_max_iterations if normalized_max_iterations > 0 else None,
            genetic_settings=genetic_settings,
        )
    elif brute_force_iteration_limit is not None:
        progress_total = min(combinations_total, int(brute_force_iteration_limit))
    else:
        progress_total = combinations_total

    market_data = load_market_data(data_file=data_file, start_date=start_date, end_date=end_date)
    ensure_market_data_not_empty(market_data, start_date=start_date, end_date=end_date)
    first_market_date: date | None = None
    if len(market_data.index):
        try:
            first_market_date = pd.Timestamp(market_data.index[0]).date()
        except Exception:
            first_market_date = None
    default_stage_date = start_date or first_market_date
    progress_runs_completed = 0

    def check_control_signal() -> None:
        if not callable(control_callback):
            return
        control_callback()

    def emit_progress(completed_runs: int, stage_date_value: date | None = None) -> None:
        if not callable(progress_callback):
            return
        safe_total = max(1, int(progress_total))
        safe_completed = max(0, min(int(completed_runs), safe_total))
        payload: dict[str, Any] = {
            "completed": safe_completed,
            "total": safe_total,
            "progress": float(safe_completed) / float(safe_total),
        }
        normalized_stage_date = stage_date_value or default_stage_date
        if normalized_stage_date is not None:
            payload["stage_date"] = normalized_stage_date
        try:
            progress_callback(payload)
        except Exception:
            return

    emit_progress(0, default_stage_date)
    check_control_signal()

    strategy_display_name = strategy_name or strategy_class.__name__
    optimized_param_name = target_param or ",".join(normalized_ranges.keys())
    created_at = datetime.now(timezone.utc).isoformat()
    normalized_fitness_formula = str(fitness_formula or "PnL").strip() or "PnL"

    try:
        fitness_evaluator = _build_fitness_evaluator(normalized_fitness_formula)
    except Exception as exc:
        raise ValueError(f"Failed to parse fitness formula '{normalized_fitness_formula}': {exc}") from exc

    evaluated_cache: dict[tuple[Any, ...], tuple[dict[str, Any] | None, date | None]] = {}

    def _extract_stage_date_from_strategy(strategy_obj: Any) -> date | None:
        stage_date_value: date | None = default_stage_date
        try:
            strategy_data = getattr(strategy_obj, "data", None)
            if strategy_data is not None:
                stage_datetime = bt.num2date(strategy_data.datetime[0])
                stage_date_value = stage_datetime.date()
        except Exception:
            stage_date_value = default_stage_date
        return stage_date_value

    def _build_result_record(strategy: bt.Strategy) -> dict[str, Any] | None:
        params_snapshot = _collect_strategy_params(strategy)
        params_snapshot.pop("commission", None)

        if (
            "fast_period" in params_snapshot
            and "slow_period" in params_snapshot
            and float(params_snapshot["fast_period"]) >= float(params_snapshot["slow_period"])
        ):
            return None

        final_balance = _extract_strategy_final_balance(strategy, initial_cash=float(initial_cash))
        pnl = final_balance - float(initial_cash)
        metrics = _collect_strategy_metrics(strategy, initial_cash=float(initial_cash), final_balance=float(final_balance))

        result_record: dict[str, Any] = {
            "run_id": uuid4().hex[:12],
            "symbol": symbol or "",
            "strategy_name": strategy_display_name,
            "optimized_param": optimized_param_name,
            "params_snapshot": params_snapshot,
            "final_balance": final_balance,
            "pnl": pnl,
            "source": source,
            "created_at": created_at,
            "optimization_mode": normalized_mode,
            "fitness_formula": normalized_fitness_formula,
        }

        if timeframe is not None:
            result_record["timeframe"] = timeframe
        if start_date is not None:
            result_record["start_date"] = start_date.isoformat()
        if end_date is not None:
            result_record["end_date"] = end_date.isoformat()

        result_record.update(metrics)
        for parameter_name, parameter_value in params_snapshot.items():
            result_record[parameter_name] = parameter_value

        result_record["fitness"] = float(fitness_evaluator(result_record))
        return result_record

    def _evaluate_params(current_params: dict[str, Any]) -> tuple[dict[str, Any] | None, date | None, bool]:
        nonlocal progress_runs_completed

        cache_key = tuple(current_params.get(name) for name in parameter_names)
        if cache_key in evaluated_cache:
            cached_result, cached_stage_date = evaluated_cache[cache_key]
            return cached_result, cached_stage_date, False

        check_control_signal()
        current_strategy_kwargs = dict(base_strategy_kwargs)
        current_strategy_kwargs.update(current_params)

        def build_cerebro_single() -> bt.Cerebro:
            cerebro = create_cerebro_with_data(
                market_data=market_data,
                initial_cash=initial_cash,
                commission=commission,
            )
            cerebro.addstrategy(strategy_class, **current_strategy_kwargs)
            return cerebro

        _, strategies = _run_cerebro_with_short_data_fallback(
            build_cerebro_single,
            start_date=start_date,
            end_date=end_date,
        )
        check_control_signal()

        strategy = strategies[0]
        stage_date = _extract_stage_date_from_strategy(strategy)
        result_record = _build_result_record(strategy)
        evaluated_cache[cache_key] = (result_record, stage_date)

        progress_runs_completed += 1
        emit_progress(progress_runs_completed, stage_date)
        return result_record, stage_date, True

    def _run_memory_safe_optimization(
        *,
        combinations_iterable: Any = None,
        max_runs: int | None = None,
    ) -> list[dict[str, Any]]:
        optimization_results: list[dict[str, Any]] = []
        combinations_source = combinations_iterable if combinations_iterable is not None else product(*parameter_values)

        for run_index, combination_values in enumerate(combinations_source):
            if max_runs is not None and run_index >= max_runs:
                break
            check_control_signal()
            current_params = {name: value for name, value in zip(parameter_names, combination_values)}
            result_record, _, _ = _evaluate_params(current_params)
            if result_record is not None:
                optimization_results.append(result_record)

        if progress_runs_completed < progress_total:
            emit_progress(progress_total, default_stage_date)
        return optimization_results

    def _run_optstrategy_optimization() -> list[dict[str, Any]]:
        nonlocal progress_runs_completed

        def build_cerebro() -> bt.Cerebro:
            cerebro = create_cerebro_with_data(market_data=market_data, initial_cash=initial_cash, commission=commission)
            cerebro.optstrategy(strategy_class, **base_strategy_kwargs, **normalized_ranges)
            if callable(progress_callback):
                def on_optimization_run(progress_strategy: Any) -> None:
                    nonlocal progress_runs_completed
                    check_control_signal()
                    if progress_runs_completed >= progress_total:
                        return

                    strategy_obj = progress_strategy
                    if isinstance(strategy_obj, (list, tuple)) and strategy_obj:
                        strategy_obj = strategy_obj[0]

                    progress_runs_completed += 1
                    emit_progress(progress_runs_completed, _extract_stage_date_from_strategy(strategy_obj))

                cerebro.optcallback(on_optimization_run)
            return cerebro

        _, optimization_runs = _run_cerebro_with_short_data_fallback(
            build_cerebro,
            run_kwargs={"maxcpus": 1, "optreturn": False},
            start_date=start_date,
            end_date=end_date,
        )

        optimization_results: list[dict[str, Any]] = []
        for run in optimization_runs:
            check_control_signal()
            strategy = run[0]
            result_record = _build_result_record(strategy)
            if result_record is not None:
                optimization_results.append(result_record)

        if progress_runs_completed < progress_total:
            emit_progress(progress_total, default_stage_date)
        return optimization_results

    def _run_random_optimization() -> list[dict[str, Any]]:
        rng = random.Random(random_seed)
        requested_iterations = int(random_iterations) if random_iterations is not None else 0
        if requested_iterations <= 0:
            requested_iterations = normalized_max_iterations if normalized_max_iterations > 0 else progress_total
        requested_iterations = max(1, requested_iterations)

        sampled_combinations = _generate_random_combinations(
            parameter_values=parameter_values,
            sample_size=requested_iterations,
            rng=rng,
        )
        if not sampled_combinations:
            return []

        return _run_memory_safe_optimization(
            combinations_iterable=sampled_combinations,
            max_runs=len(sampled_combinations),
        )

    def _run_genetic_optimization() -> list[dict[str, Any]]:
        rng = random.Random(random_seed)
        settings = genetic_settings if isinstance(genetic_settings, dict) else {}

        population_size = max(2, int(settings.get("population", 8) or 8))
        generations_max = max(1, int(settings.get("generations_max", 20) or 20))
        stagnation_generations = max(0, int(settings.get("generations_stagnation", 5) or 5))
        tournament_size = max(2, int(settings.get("tournament_size", 3) or 3))
        elite_count = max(1, int(settings.get("elite_count", 1) or 1))
        mutation_probability = float(settings.get("mutation_probability", 0.1) or 0.1)
        crossover_probability = float(settings.get("crossover_probability", 0.9) or 0.9)
        mutation_probability = min(1.0, max(0.0, mutation_probability))
        crossover_probability = min(1.0, max(0.0, crossover_probability))

        gene_sizes = [len(values) for values in parameter_values]
        if not gene_sizes or any(size <= 0 for size in gene_sizes):
            return []

        total_possible = 1
        for size in gene_sizes:
            total_possible *= int(size)

        max_evaluations = normalized_max_iterations if normalized_max_iterations > 0 else None
        if max_evaluations is not None:
            max_evaluations = min(max_evaluations, total_possible)

        def random_genome() -> tuple[int, ...]:
            return tuple(rng.randrange(size) for size in gene_sizes)

        def decode_genome(genome: tuple[int, ...]) -> dict[str, Any]:
            return {
                parameter_names[index]: parameter_values[index][gene_index]
                for index, gene_index in enumerate(genome)
            }

        def mutate(genome: tuple[int, ...]) -> tuple[int, ...]:
            genes = list(genome)
            for index, size in enumerate(gene_sizes):
                if size <= 1:
                    continue
                if rng.random() < mutation_probability:
                    new_gene = rng.randrange(size)
                    if new_gene == genes[index]:
                        new_gene = (new_gene + 1 + rng.randrange(size - 1)) % size
                    genes[index] = new_gene
            return tuple(genes)

        def crossover(parent_a: tuple[int, ...], parent_b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
            if len(parent_a) <= 1 or rng.random() >= crossover_probability:
                return parent_a, parent_b
            split_point = rng.randrange(1, len(parent_a))
            child_a = parent_a[:split_point] + parent_b[split_point:]
            child_b = parent_b[:split_point] + parent_a[split_point:]
            return child_a, child_b

        genome_cache: dict[tuple[int, ...], tuple[float, dict[str, Any] | None]] = {}

        def evaluate_genome(genome: tuple[int, ...]) -> tuple[float, dict[str, Any] | None]:
            if genome in genome_cache:
                return genome_cache[genome]

            if max_evaluations is not None and progress_runs_completed >= max_evaluations:
                genome_cache[genome] = (float("-inf"), None)
                return genome_cache[genome]

            params = decode_genome(genome)
            result_record, _, _ = _evaluate_params(params)
            fitness_value = (
                float(result_record.get("fitness", float("-inf")))
                if isinstance(result_record, dict)
                else float("-inf")
            )
            if not math.isfinite(fitness_value):
                fitness_value = float("-inf")
            genome_cache[genome] = (fitness_value, result_record)
            return genome_cache[genome]

        population: list[tuple[int, ...]] = []
        population_seen: set[tuple[int, ...]] = set()
        initialization_attempts = 0
        max_initialization_attempts = max(100, population_size * 20)
        while len(population) < population_size and initialization_attempts < max_initialization_attempts:
            candidate = random_genome()
            initialization_attempts += 1
            if candidate in population_seen:
                continue
            population_seen.add(candidate)
            population.append(candidate)
        if not population:
            return []

        best_fitness = float("-inf")
        stagnation_counter = 0

        for _ in range(generations_max):
            check_control_signal()
            scored_population: list[tuple[tuple[int, ...], float, dict[str, Any] | None]] = []
            for genome in population:
                check_control_signal()
                fitness_value, result_record = evaluate_genome(genome)
                scored_population.append((genome, fitness_value, result_record))

            scored_population.sort(key=lambda item: item[1], reverse=True)
            if not scored_population:
                break

            current_best = scored_population[0][1]
            if current_best > best_fitness:
                best_fitness = current_best
                stagnation_counter = 0
            else:
                stagnation_counter += 1

            if max_evaluations is not None and progress_runs_completed >= max_evaluations:
                break
            if stagnation_generations > 0 and stagnation_counter >= stagnation_generations:
                break

            def select_parent() -> tuple[int, ...]:
                effective_tournament = min(len(scored_population), tournament_size)
                candidates = (
                    rng.sample(scored_population, effective_tournament)
                    if len(scored_population) > effective_tournament
                    else scored_population
                )
                candidates = sorted(candidates, key=lambda item: item[1], reverse=True)
                return candidates[0][0]

            next_population: list[tuple[int, ...]] = [
                item[0] for item in scored_population[: min(elite_count, len(scored_population))]
            ]
            while len(next_population) < population_size:
                parent_a = select_parent()
                parent_b = select_parent()
                child_a, child_b = crossover(parent_a, parent_b)
                child_a = mutate(child_a)
                child_b = mutate(child_b)
                next_population.append(child_a)
                if len(next_population) < population_size:
                    next_population.append(child_b)

            population = next_population[:population_size]

        optimization_results = [
            result_record
            for fitness_value, result_record in genome_cache.values()
            if isinstance(result_record, dict) and math.isfinite(fitness_value)
        ]
        optimization_results.sort(key=lambda row: float(row.get("fitness", float("-inf"))), reverse=True)

        if progress_runs_completed < progress_total:
            emit_progress(progress_total, default_stage_date)
        return optimization_results

    if normalized_mode == OPTIMIZATION_MODE_RANDOM:
        optimization_results = _run_random_optimization()
    elif normalized_mode == OPTIMIZATION_MODE_GENETIC:
        optimization_results = _run_genetic_optimization()
    else:
        workload = int(max(1, len(market_data.index))) * int(combinations_total)
        prefer_memory_safe = workload >= int(OPTIMIZATION_MEMORY_SAFE_WORKLOAD) or brute_force_iteration_limit is not None
        if prefer_memory_safe:
            optimization_results = _run_memory_safe_optimization(max_runs=brute_force_iteration_limit)
        else:
            try:
                optimization_results = _run_optstrategy_optimization()
            except MemoryError:
                progress_runs_completed = 0
                emit_progress(0, default_stage_date)
                optimization_results = _run_memory_safe_optimization(max_runs=brute_force_iteration_limit)

    check_control_signal()
    emit_progress(progress_total, default_stage_date)
    return optimization_results

def format_balance(value: float) -> str:
    return f"{value:,.2f} USDT"


def get_default_strategy_class() -> type[bt.Strategy]:
    available_strategies = load_available_strategies()
    if DEFAULT_STRATEGY_NAME in available_strategies:
        return available_strategies[DEFAULT_STRATEGY_NAME]
    if not available_strategies:
        raise ValueError("No Backtrader strategies found in the strategies directory.")
    return next(iter(available_strategies.values()))


def main() -> None:
    strategy_class = get_default_strategy_class()
    (
        starting_balance,
        final_balance,
        trades_log,
        equity_curve,
        strategy_indicators,
        sampling_metadata,
    ) = run_backtest(
        strategy_class=strategy_class,
        strategy_kwargs={"fast_period": DEFAULT_FAST_PERIOD, "slow_period": DEFAULT_SLOW_PERIOD},
    )
    profit = final_balance - starting_balance
    print(f"Backtest finished for strategy {strategy_class.__name__}.")
    print(f"Starting balance: {format_balance(starting_balance)}")
    print(f"Final balance: {format_balance(final_balance)}")
    print(f"Profit/loss: {format_balance(profit)}")
    print(f"Closed trades: {len(trades_log)}")
    print(f"Equity points: {len(equity_curve)}")
    print(f"Indicators captured: {len(strategy_indicators)}")
    print(f"Sampling metadata: {sampling_metadata}")


if __name__ == "__main__":
    main()
