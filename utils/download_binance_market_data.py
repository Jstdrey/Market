from __future__ import annotations

import argparse
import io
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


BINANCE_ARCHIVE_BASE = "https://data.binance.vision/data/spot/monthly/klines"
COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]
DTYPES = {
    "open_time": "int64",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "float64",
    "close_time": "int64",
    "quote_asset_volume": "float64",
    "number_of_trades": "int64",
    "taker_buy_base_asset_volume": "float64",
    "taker_buy_quote_asset_volume": "float64",
    "ignore": "float64",
}
DIRECT_INTERVALS = ("1m", "5m", "15m")
TARGET_INTERVALS = ("1m", "5m", "7m", "10m", "15m")


@dataclass
class DownloadResult:
    frame: pd.DataFrame
    warnings: list[str]


def month_list(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    month_start = pd.Timestamp(year=start.year, month=start.month, day=1, tz="UTC")
    month_end = pd.Timestamp(year=end.year, month=end.month, day=1, tz="UTC")
    values: list[str] = []
    cursor = month_start
    while cursor <= month_end:
        values.append(cursor.strftime("%Y-%m"))
        cursor += pd.offsets.MonthBegin(1)
    return values


def _fetch_month_zip(
    session: requests.Session,
    symbol: str,
    interval: str,
    ym: str,
    retries: int = 4,
) -> tuple[bytes | None, str | None]:
    url = f"{BINANCE_ARCHIVE_BASE}/{symbol}/{interval}/{symbol}-{interval}-{ym}.zip"
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, timeout=60)
        except requests.RequestException as exc:
            if attempt == retries:
                return None, f"{symbol} {interval} {ym}: request error: {exc}"
            time.sleep(min(2**attempt, 20))
            continue

        if response.status_code == 200:
            return response.content, None
        if response.status_code == 404:
            return None, f"{symbol} {interval} {ym}: source file not found (404)"
        if attempt == retries:
            return None, (
                f"{symbol} {interval} {ym}: http {response.status_code} "
                f"{response.text[:180]}"
            )
        time.sleep(min(2**attempt, 20))

    return None, f"{symbol} {interval} {ym}: unknown download error"


def _zip_csv_to_frame(payload: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        if not names:
            raise ValueError("empty zip archive")
        with zf.open(names[0]) as handle:
            df = pd.read_csv(
                handle,
                header=None,
                names=COLUMNS,
                usecols=list(range(len(COLUMNS))),
                dtype=DTYPES,
            )
    return df


def load_interval_data(
    session: requests.Session,
    symbol: str,
    interval: str,
    months: Iterable[str],
    start_ms: int,
    end_ms: int,
) -> DownloadResult:
    parts: list[pd.DataFrame] = []
    warnings: list[str] = []
    for ym in months:
        payload, warn = _fetch_month_zip(session, symbol, interval, ym)
        if warn:
            warnings.append(warn)
            continue
        try:
            parts.append(_zip_csv_to_frame(payload))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{symbol} {interval} {ym}: failed to parse archive: {exc}")

    if not parts:
        empty = pd.DataFrame(columns=COLUMNS)
        return DownloadResult(empty, warnings)

    merged = pd.concat(parts, ignore_index=True)
    filtered = merged[(merged["open_time"] >= start_ms) & (merged["open_time"] <= end_ms)].copy()
    filtered = filtered.sort_values("open_time", kind="mergesort").drop_duplicates("open_time")
    return DownloadResult(filtered, warnings)


def build_derived_interval(one_minute: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if one_minute.empty:
        return pd.DataFrame(columns=COLUMNS)

    dt_index = pd.to_datetime(one_minute["open_time"], unit="ms", utc=True)
    source = one_minute.set_index(dt_index)
    agg = source.resample(
        f"{minutes}min",
        origin="epoch",
        label="left",
        closed="left",
    ).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "quote_asset_volume": "sum",
            "number_of_trades": "sum",
            "taker_buy_base_asset_volume": "sum",
            "taker_buy_quote_asset_volume": "sum",
        }
    )
    agg = agg.dropna(subset=["open", "high", "low", "close"]).copy()
    agg["open_time"] = (agg.index.view("int64") // 1_000_000).astype("int64")
    agg["close_time"] = (agg["open_time"] + minutes * 60_000 - 1).astype("int64")
    agg["ignore"] = 0.0
    agg["number_of_trades"] = agg["number_of_trades"].round().astype("int64")

    result = agg.reset_index(drop=True)[COLUMNS]
    return result


def append_context_columns(df: pd.DataFrame, symbol: str, interval: str) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "symbol", symbol)
    out.insert(1, "timeframe", interval)
    return out


def save_symbol_file(symbol: str, frame: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{symbol}_market_20221030_20260301.csv.gz"
    frame.to_csv(path, index=False, compression="gzip")
    return path


def download_for_symbol(
    session: requests.Session,
    symbol: str,
    months: list[str],
    start_ms: int,
    end_ms: int,
) -> tuple[Path | None, list[str], dict[str, int]]:
    warnings: list[str] = []
    data_by_interval: dict[str, pd.DataFrame] = {}

    for interval in DIRECT_INTERVALS:
        loaded = load_interval_data(
            session=session,
            symbol=symbol,
            interval=interval,
            months=months,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        data_by_interval[interval] = loaded.frame
        warnings.extend(loaded.warnings)

    data_by_interval["7m"] = build_derived_interval(data_by_interval["1m"], 7)
    data_by_interval["10m"] = build_derived_interval(data_by_interval["1m"], 10)

    for derived in ("7m", "10m"):
        df = data_by_interval[derived]
        if not df.empty:
            df = df[(df["open_time"] >= start_ms) & (df["open_time"] <= end_ms)].copy()
            data_by_interval[derived] = df

    combined_parts: list[pd.DataFrame] = []
    row_stats: dict[str, int] = {}
    for interval in TARGET_INTERVALS:
        frame = data_by_interval[interval]
        row_stats[interval] = int(len(frame))
        if frame.empty:
            warnings.append(f"{symbol} {interval}: no rows in requested range")
            continue
        combined_parts.append(append_context_columns(frame, symbol, interval))

    if not combined_parts:
        return None, warnings, row_stats

    combined = pd.concat(combined_parts, ignore_index=True)
    combined = combined.sort_values(["timeframe", "open_time"], kind="mergesort").reset_index(drop=True)
    output_path = save_symbol_file(symbol, combined, output_dir=Path("output") / "binance_market_data")
    return output_path, warnings, row_stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=[
            "XTZUSDT",
            "XLMUSDT",
            "SOLUSDT",
            "LUNAUSDT",
            "KSMUSDT",
            "FTMUSDT",
            "DOTUSDT",
            "C98USDT",
            "AXSUSDT",
            "AVAXUSDT",
            "ATOMUSDT",
            "ADAUSDT",
            "AAVEUSDT",
            "1INCHUSDT",
        ],
    )
    parser.add_argument("--start", default="2022-10-30")
    parser.add_argument("--end", default="2026-03-01")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_ts = pd.Timestamp(args.start, tz="UTC")
    end_ts = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
    start_ms = int(start_ts.timestamp() * 1000)
    end_ms = int(end_ts.timestamp() * 1000)
    months = month_list(start_ts, end_ts)

    all_warnings: list[str] = []
    outputs: list[str] = []

    with requests.Session() as session:
        session.headers.update({"User-Agent": "market-data-downloader/1.0"})
        for idx, symbol in enumerate(args.symbols, start=1):
            print(f"[{idx}/{len(args.symbols)}] {symbol}: download started")
            out_path, warnings, row_stats = download_for_symbol(
                session=session,
                symbol=symbol,
                months=months,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            if out_path is None:
                all_warnings.append(f"{symbol}: file not generated (no data)")
                all_warnings.extend(warnings)
                print(f"[{idx}/{len(args.symbols)}] {symbol}: failed, no data")
                continue

            outputs.append(str(out_path.resolve()))
            all_warnings.extend(warnings)
            stats_text = ", ".join(f"{k}={v}" for k, v in row_stats.items())
            print(f"[{idx}/{len(args.symbols)}] {symbol}: saved -> {out_path} | {stats_text}")

    print("=== OUTPUT FILES ===")
    for path in outputs:
        print(path)
    print("=== WARNINGS ===")
    if not all_warnings:
        print("NONE")
    else:
        for item in all_warnings:
            print(item)


if __name__ == "__main__":
    main()
