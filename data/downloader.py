from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
import re
import sys
import hashlib

import ccxt
import pandas as pd

LIMIT = 1000
PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = PROJECT_DIR / "data.csv"
DATA_CACHE_DIR = PROJECT_DIR / "data" / "cache"
DATA_FILE_CONTEXT_VERSION = "1"
EXCHANGE_LOAD_TIMEOUT_RETRIES_MS = (45000, 90000)
DATA_FILE_CONTEXT_MODES = {"light", "full"}


def normalize_symbol_for_filename(symbol: str) -> str:
    normalized_symbol = symbol.replace("/", "_")
    normalized_symbol = re.sub(r"[^A-Za-z0-9._-]", "_", normalized_symbol)
    return normalized_symbol or "symbol"


def get_market_data_file(symbol: str, timeframe: str, cache_dir: Path | str | None = None) -> Path:
    cache_directory = Path(cache_dir or DATA_CACHE_DIR)
    cache_directory.mkdir(parents=True, exist_ok=True)
    normalized_symbol = normalize_symbol_for_filename(symbol)
    normalized_timeframe = normalize_symbol_for_filename(timeframe)
    return cache_directory / f"{normalized_symbol}_{normalized_timeframe}.csv"


def create_exchange(symbol: str) -> ccxt.binance:
    last_network_error: Exception | None = None
    for timeout_ms in EXCHANGE_LOAD_TIMEOUT_RETRIES_MS:
        exchange = ccxt.binance(
            {
                "enableRateLimit": True,
                "timeout": timeout_ms,
                "defaultType": "spot",
                "options": {"defaultType": "spot"},
            }
        )
        # Keep explicit overrides to avoid defaulting to futures/delivery endpoints.
        exchange.options["defaultType"] = "spot"

        try:
            exchange.load_markets(params={"type": "spot"})
        except (ccxt.NetworkError, ccxt.RequestTimeout) as error:
            last_network_error = error
            continue

        if not exchange.has.get("fetchOHLCV"):
            raise RuntimeError("Binance API does not support fetch_ohlcv endpoint.")
        if symbol not in exchange.symbols:
            raise ValueError(f"Symbol {symbol} is not available on Binance spot.")
        return exchange

    if last_network_error is not None:
        raise RuntimeError(
            "Не удалось подключиться к Binance (таймаут/сетевая ошибка). "
            f"Последняя ошибка: {last_network_error}"
        )
    if not exchange.has.get("fetchOHLCV"):
        raise RuntimeError("Binance API does not support fetch_ohlcv endpoint.")
    if symbol not in exchange.symbols:
        raise ValueError(f"Symbol {symbol} is not available on Binance.")
    return exchange


def align_datetime_to_timeframe(target_datetime_utc: datetime, timeframe: str) -> datetime:
    timeframe_seconds = ccxt.Exchange.parse_timeframe(timeframe)
    target_timestamp = int(target_datetime_utc.timestamp())
    aligned_timestamp = target_timestamp - (target_timestamp % timeframe_seconds)
    return datetime.fromtimestamp(aligned_timestamp, tz=timezone.utc)


def get_period_boundaries(start_date: date, end_date: date, timeframe: str) -> tuple[datetime, datetime, int, int]:
    if start_date is None or end_date is None:
        raise ValueError("Both start_date and end_date must be provided.")
    if start_date > end_date:
        raise ValueError("Start date must be before or equal end date.")

    start_time_utc = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    raw_end_time_utc = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    end_time_utc = align_datetime_to_timeframe(raw_end_time_utc, timeframe)
    if end_time_utc <= start_time_utc:
        raise ValueError("Invalid date range after alignment. Please try a narrower date range.")

    start_ms = int(start_time_utc.timestamp() * 1000)
    end_ms = int(end_time_utc.timestamp() * 1000)
    return start_time_utc, end_time_utc, start_ms, end_ms


def get_timeframe_step_ms(timeframe: str) -> int:
    timeframe_seconds = ccxt.Exchange.parse_timeframe(timeframe)
    return timeframe_seconds * 1000


def download_ohlcv(exchange: ccxt.Exchange, symbol: str, timeframe: str, start_ms: int, end_ms: int) -> list[list[float]]:
    all_candles: list[list[float]] = []
    current_since = start_ms
    timeframe_step_ms = get_timeframe_step_ms(timeframe)

    while current_since < end_ms:
        candles = exchange.fetch_ohlcv(symbol=symbol, timeframe=timeframe, since=current_since, limit=LIMIT)
        if not candles:
            break

        all_candles.extend(candles)
        last_candle_open_ms = int(candles[-1][0])
        next_since = last_candle_open_ms + timeframe_step_ms
        if next_since <= current_since:
            break
        current_since = next_since

        if len(candles) < LIMIT:
            break

    return all_candles


def _to_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def build_dataframe(candles: list[list[float]], start_ms: int, end_ms: int) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(columns=["timestamp", "datetime", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset=["timestamp"])
    df["timestamp"] = _to_numeric_series(df["timestamp"]).astype("Int64")
    df["open"] = _to_numeric_series(df["open"])
    df["high"] = _to_numeric_series(df["high"])
    df["low"] = _to_numeric_series(df["low"])
    df["close"] = _to_numeric_series(df["close"])
    df["volume"] = _to_numeric_series(df["volume"])
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = df["timestamp"].astype(int)

    df = df[(df["timestamp"] >= start_ms) & (df["timestamp"] < end_ms)].copy()
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    df = df[["timestamp", "datetime", "open", "high", "low", "close", "volume"]]
    return df.sort_values("timestamp").reset_index(drop=True)


def read_cached_market_data(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame(columns=["timestamp", "datetime", "open", "high", "low", "close", "volume"])

    dataframe = pd.read_csv(file_path)
    required_columns = ["timestamp", "open", "high", "low", "close", "volume"]
    if not set(required_columns).issubset(dataframe.columns):
        missing = sorted(set(required_columns) - set(dataframe.columns))
        raise ValueError(f"Cached data file '{file_path}' is missing columns: {', '.join(missing)}")

    dataframe["timestamp"] = _to_numeric_series(dataframe["timestamp"]).astype("Int64")
    dataframe["open"] = _to_numeric_series(dataframe["open"])
    dataframe["high"] = _to_numeric_series(dataframe["high"])
    dataframe["low"] = _to_numeric_series(dataframe["low"])
    dataframe["close"] = _to_numeric_series(dataframe["close"])
    dataframe["volume"] = _to_numeric_series(dataframe["volume"])
    dataframe = dataframe.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    if dataframe.empty:
        return pd.DataFrame(columns=["timestamp", "datetime", "open", "high", "low", "close", "volume"])

    dataframe["timestamp"] = dataframe["timestamp"].astype(int)
    if "datetime" in dataframe.columns:
        dataframe["datetime"] = pd.to_datetime(dataframe["datetime"], utc=True, errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
        dataframe["datetime"] = dataframe["datetime"].fillna("")
    else:
        dataframe["datetime"] = pd.to_datetime(dataframe["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")

    return dataframe[["timestamp", "datetime", "open", "high", "low", "close", "volume"]].drop_duplicates(
        subset=["timestamp"]
    ).sort_values("timestamp").reset_index(drop=True)


def build_cache_intervals(timestamps: pd.Series, timeframe: str) -> list[tuple[int, int]]:
    if timestamps.empty:
        return []

    step_ms = get_timeframe_step_ms(timeframe)
    ordered = sorted(int(value) for value in pd.to_numeric(timestamps, errors="coerce").dropna().astype(int).unique())
    if not ordered:
        return []

    intervals: list[tuple[int, int]] = []
    segment_start = ordered[0]
    segment_end = segment_start + step_ms

    for current in ordered[1:]:
        current_end = current + step_ms
        if current <= segment_end:
            segment_end = max(segment_end, current_end)
            continue
        intervals.append((segment_start, segment_end))
        segment_start = current
        segment_end = current_end

    intervals.append((segment_start, segment_end))
    return intervals


def compute_missing_ranges(
    start_ms: int,
    end_ms: int,
    cached_timestamps: pd.Series,
    timeframe: str,
) -> list[tuple[int, int]]:
    if start_ms >= end_ms:
        return []

    if cached_timestamps is None or len(cached_timestamps) == 0:
        return [(start_ms, end_ms)]

    intervals = build_cache_intervals(cached_timestamps, timeframe)
    if not intervals:
        return [(start_ms, end_ms)]

    missing: list[tuple[int, int]] = []
    cursor = start_ms

    for interval_start, interval_end in intervals:
        if interval_end <= cursor:
            continue
        if interval_start > cursor:
            missing.append((cursor, min(interval_start, end_ms)))
        cursor = max(cursor, interval_end)
        if cursor >= end_ms:
            break

    if cursor < end_ms:
        missing.append((cursor, end_ms))

    merged: list[tuple[int, int]] = []
    for missing_start, missing_end in missing:
        if missing_start >= missing_end:
            continue
        if not merged:
            merged.append((missing_start, missing_end))
            continue
        last_start, last_end = merged[-1]
        if missing_start <= last_end:
            merged[-1] = (last_start, max(last_end, missing_end))
        else:
            merged.append((missing_start, missing_end))
    return merged


def merge_market_data_frames(data_frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not data_frames:
        return pd.DataFrame(columns=["timestamp", "datetime", "open", "high", "low", "close", "volume"])

    combined = pd.concat(data_frames, ignore_index=True)
    if combined.empty:
        return pd.DataFrame(columns=["timestamp", "datetime", "open", "high", "low", "close", "volume"])

    combined["timestamp"] = _to_numeric_series(combined["timestamp"]).astype("Int64")
    combined = combined.dropna(subset=["timestamp"])
    combined["timestamp"] = combined["timestamp"].astype(int)
    for field in ["open", "high", "low", "close", "volume"]:
        combined[field] = _to_numeric_series(combined[field])
    combined = combined.dropna(subset=["timestamp", "open", "high", "low", "close", "volume"])
    combined["datetime"] = pd.to_datetime(combined["timestamp"], unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M:%S")
    combined = combined.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return combined[["timestamp", "datetime", "open", "high", "low", "close", "volume"]]


def save_csv(df: pd.DataFrame, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df = df.copy()
    for field in ["timestamp", "open", "high", "low", "close", "volume"]:
        if field in df.columns:
            df[field] = _to_numeric_series(df[field])
    df.to_csv(output_file, index=False)
    print(f"Market data file saved: {output_file}")


def _resolve_context_mode(mode: str) -> str:
    normalized_mode = str(mode or "light").strip().lower()
    if normalized_mode not in DATA_FILE_CONTEXT_MODES:
        raise ValueError(f"Unsupported market data context mode: {mode}")
    return normalized_mode


def _build_light_context(
    file_path: Path,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    file_stats = file_path.stat()
    timestamp_column = pd.read_csv(file_path, usecols=["timestamp"])
    numeric_timestamps = pd.to_numeric(timestamp_column["timestamp"], errors="coerce").dropna()

    if numeric_timestamps.empty:
        rows = 0
        first_timestamp = None
        last_timestamp = None
    else:
        rows = int(len(numeric_timestamps))
        first_timestamp = int(numeric_timestamps.min())
        last_timestamp = int(numeric_timestamps.max())

    fingerprint_seed = (
        f"{DATA_FILE_CONTEXT_VERSION}|{file_path.resolve()}|{int(file_stats.st_size)}|"
        f"{int(file_stats.st_mtime_ns)}|{rows}|{first_timestamp}|{last_timestamp}"
    )
    light_signature = hashlib.blake2s(fingerprint_seed.encode("utf-8"), digest_size=8).hexdigest()

    return {
        "context_version": DATA_FILE_CONTEXT_VERSION,
        "mode": "light",
        "path": str(file_path),
        "symbol": symbol or "",
        "timeframe": timeframe or "",
        "rows": rows,
        "checksum": light_signature,
        "checksum_algorithm": "blake2s-64",
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "modified_at": datetime.fromtimestamp(file_stats.st_mtime, tz=timezone.utc).isoformat(),
        "size_bytes": int(file_stats.st_size),
    }


def _build_full_context(
    file_path: Path,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> dict[str, Any]:
    file_stats = file_path.stat()
    dataframe = read_cached_market_data(file_path)

    if dataframe.empty:
        return {
            "context_version": DATA_FILE_CONTEXT_VERSION,
            "mode": "full",
            "path": str(file_path),
            "symbol": symbol or "",
            "timeframe": timeframe or "",
            "rows": 0,
            "checksum": "",
            "checksum_algorithm": "sha256",
            "first_timestamp": None,
            "last_timestamp": None,
            "modified_at": datetime.fromtimestamp(file_stats.st_mtime, tz=timezone.utc).isoformat(),
            "size_bytes": int(file_stats.st_size),
        }

    normalized = dataframe.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).copy()
    normalized = normalized[["timestamp", "open", "high", "low", "close", "volume"]]
    for field in ["timestamp", "open", "high", "low", "close", "volume"]:
        normalized[field] = _to_numeric_series(normalized[field])

    checksum_bytes = normalized.to_csv(index=False).encode("utf-8")
    data_signature = hashlib.sha256(checksum_bytes).hexdigest()

    return {
        "context_version": DATA_FILE_CONTEXT_VERSION,
        "mode": "full",
        "path": str(file_path),
        "symbol": symbol or "",
        "timeframe": timeframe or "",
        "rows": int(len(normalized)),
        "checksum": data_signature,
        "checksum_algorithm": "sha256",
        "first_timestamp": int(normalized["timestamp"].min()) if not normalized.empty else None,
        "last_timestamp": int(normalized["timestamp"].max()) if not normalized.empty else None,
        "modified_at": datetime.fromtimestamp(file_stats.st_mtime, tz=timezone.utc).isoformat(),
        "size_bytes": int(file_stats.st_size),
    }


def build_market_data_file_context(
    data_file: Path,
    *,
    symbol: str | None = None,
    timeframe: str | None = None,
    mode: str = "light",
) -> dict[str, Any]:
    resolved_mode = _resolve_context_mode(mode)
    file_path = Path(data_file)
    if not file_path.exists():
        return {
            "context_version": DATA_FILE_CONTEXT_VERSION,
            "mode": resolved_mode,
            "path": str(file_path),
            "symbol": symbol or "",
            "timeframe": timeframe or "",
            "rows": 0,
            "checksum": "",
            "checksum_algorithm": "none",
            "first_timestamp": None,
            "last_timestamp": None,
            "modified_at": None,
            "size_bytes": 0,
        }

    if resolved_mode == "light":
        return _build_light_context(file_path, symbol=symbol, timeframe=timeframe)
    return _build_full_context(file_path, symbol=symbol, timeframe=timeframe)


def run_downloader(
    symbol: str,
    timeframe: str,
    start_date: date,
    end_date: date,
    output_file: Path = OUTPUT_FILE,
) -> pd.DataFrame:
    exchange = create_exchange(symbol=symbol)
    _, _, start_ms, end_ms = get_period_boundaries(start_date=start_date, end_date=end_date, timeframe=timeframe)
    cache_path = get_market_data_file(symbol=symbol, timeframe=timeframe)
    output_path = Path(output_file)

    cached_df = read_cached_market_data(cache_path)
    missing_ranges = compute_missing_ranges(
        start_ms=start_ms,
        end_ms=end_ms,
        cached_timestamps=cached_df["timestamp"] if not cached_df.empty else pd.Series(dtype="int64"),
        timeframe=timeframe,
    )

    downloaded_frames: list[pd.DataFrame] = []
    if not missing_ranges:
        print(f"Market data cache is already up-to-date for {symbol} {timeframe}.")
    else:
        print(f"Preparing market data for {symbol} on {timeframe}.")
        for missing_start_ms, missing_end_ms in missing_ranges:
            candles = download_ohlcv(
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                start_ms=missing_start_ms,
                end_ms=missing_end_ms,
            )
            if not candles:
                continue
            downloaded_frames.append(build_dataframe(candles=candles, start_ms=missing_start_ms, end_ms=missing_end_ms))

    all_frames = [cached_df] + downloaded_frames if not cached_df.empty else downloaded_frames
    merged = merge_market_data_frames(all_frames)
    if merged.empty:
        raise ValueError(f"No data returned from Binance for {symbol} {timeframe} in requested range.")

    remaining_ranges = compute_missing_ranges(
        start_ms=start_ms,
        end_ms=end_ms,
        cached_timestamps=merged["timestamp"],
        timeframe=timeframe,
    )
    if remaining_ranges:
        formatted_ranges = ", ".join(
            f"{datetime.fromtimestamp(start / 1000, tz=timezone.utc):%Y-%m-%d %H:%M} -> "
            f"{datetime.fromtimestamp(end / 1000, tz=timezone.utc):%Y-%m-%d %H:%M}"
            for start, end in remaining_ranges
        )
        raise ValueError(
            f"Could not fill requested range for {symbol} {timeframe}. Missing windows: {formatted_ranges}"
        )

    save_csv(df=merged, output_file=cache_path)
    if output_path.resolve() != cache_path.resolve():
        save_csv(df=merged, output_file=output_path)
    print(f"Market data file now contains {len(merged)} rows.")
    return merged


def main(
    symbol: str = "BTC/USDT",
    timeframe: str = "1h",
    start_date: date | None = None,
    end_date: date | None = None,
    output_file: Path = OUTPUT_FILE,
) -> None:
    try:
        if start_date is None or end_date is None:
            today = datetime.now(timezone.utc).date()
            end_date = today if end_date is None else end_date
            start_date = (end_date - timedelta(days=365)) if start_date is None else start_date
        run_downloader(
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            output_file=output_file,
        )
    except ccxt.NetworkError as error:
        print(f"Network error: {error}")
        sys.exit(1)
    except ccxt.ExchangeError as error:
        print(f"Exchange error: {error}")
        sys.exit(1)
    except Exception as error:
        print(f"Unexpected error: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
