from __future__ import annotations

import argparse
import io
import time
import zipfile
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests


BINANCE_ARCHIVE_BASE = "https://data.binance.vision/data/spot/monthly/klines"
TARGET_INTERVALS = ("1m", "5m", "7m", "10m", "15m")
DIRECT_INTERVALS = ("1m", "5m", "15m")
DEFAULT_SYMBOLS = [
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
]
BASE_COLUMNS = [
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
FINAL_COLUMNS = ["symbol", "timeframe", *BASE_COLUMNS]
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


def month_list(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    month_start = pd.Timestamp(year=start.year, month=start.month, day=1, tz="UTC")
    month_end = pd.Timestamp(year=end.year, month=end.month, day=1, tz="UTC")
    values: list[str] = []
    cursor = month_start
    while cursor <= month_end:
        values.append(cursor.strftime("%Y-%m"))
        cursor += pd.offsets.MonthBegin(1)
    return values


def compute_expected_counts_by_month(
    start_ts: pd.Timestamp,
    end_ts: pd.Timestamp,
    interval_minutes: int,
) -> dict[str, int]:
    idx = pd.date_range(start=start_ts, end=end_ts, freq=f"{interval_minutes}min", tz="UTC")
    as_series = pd.Series(1, index=idx)
    period_index = as_series.index.tz_localize(None).to_period("M")
    grouped = as_series.groupby(period_index).sum()
    return {period.strftime("%Y-%m"): int(val) for period, val in grouped.items()}


def normalize_time_unit(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    max_abs = int(out["open_time"].abs().max())
    if max_abs >= 10**14:
        out["open_time"] = (out["open_time"] // 1000).astype("int64")
        out["close_time"] = (out["close_time"] // 1000).astype("int64")
    elif max_abs >= 10**17:
        out["open_time"] = (out["open_time"] // 1_000_000).astype("int64")
        out["close_time"] = (out["close_time"] // 1_000_000).astype("int64")
    return out


def fetch_month_zip(
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


def zip_csv_to_frame(payload: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        names = zf.namelist()
        if not names:
            raise ValueError("empty zip archive")
        with zf.open(names[0]) as handle:
            df = pd.read_csv(
                handle,
                header=None,
                names=BASE_COLUMNS,
                usecols=list(range(len(BASE_COLUMNS))),
                dtype=DTYPES,
            )
    return normalize_time_unit(df)


def expected_months_to_redownload(
    existing: pd.DataFrame,
    expected_counts: dict[str, int],
) -> list[str]:
    if existing.empty:
        return sorted(expected_counts.keys())

    open_ts = pd.to_datetime(existing["open_time"], unit="ms", utc=True)
    month_keys = open_ts.dt.tz_localize(None).dt.to_period("M")
    month_counts = month_keys.value_counts()
    actual = {p.strftime("%Y-%m"): int(v) for p, v in month_counts.items()}
    missing: list[str] = []
    for ym, needed in expected_counts.items():
        if actual.get(ym, 0) < needed:
            missing.append(ym)
    return missing


def filter_time_range(df: pd.DataFrame, start_ms: int, end_ms: int) -> pd.DataFrame:
    if df.empty:
        return df
    out = df[(df["open_time"] >= start_ms) & (df["open_time"] <= end_ms)].copy()
    out = out.sort_values("open_time", kind="mergesort").drop_duplicates("open_time")
    return out


def build_derived_interval(one_minute: pd.DataFrame, minutes: int) -> pd.DataFrame:
    if one_minute.empty:
        return pd.DataFrame(columns=BASE_COLUMNS)

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
    return agg.reset_index(drop=True)[BASE_COLUMNS]


def load_existing_symbol_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=FINAL_COLUMNS)
    df = pd.read_csv(path)
    missing_cols = [c for c in FINAL_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"{path} missing columns: {missing_cols}")
    return df[FINAL_COLUMNS].copy()


def append_meta(df: pd.DataFrame, symbol: str, timeframe: str) -> pd.DataFrame:
    out = df.copy()
    out.insert(0, "symbol", symbol)
    out.insert(1, "timeframe", timeframe)
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--start", default="2022-10-30")
    parser.add_argument("--end", default="2026-03-01")
    parser.add_argument("--output-dir", default="output/binance_market_data")
    return parser.parse_args()


def interval_minutes(interval: str) -> int:
    return int(interval.rstrip("m"))


def download_missing_months(
    session: requests.Session,
    symbol: str,
    interval: str,
    months: Iterable[str],
    start_ms: int,
    end_ms: int,
) -> tuple[pd.DataFrame, list[str]]:
    chunks: list[pd.DataFrame] = []
    warnings: list[str] = []
    for ym in months:
        payload, warn = fetch_month_zip(session, symbol, interval, ym)
        if warn:
            warnings.append(warn)
            continue
        try:
            chunk = zip_csv_to_frame(payload)
            chunk = filter_time_range(chunk, start_ms=start_ms, end_ms=end_ms)
            if not chunk.empty:
                chunks.append(chunk)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"{symbol} {interval} {ym}: failed to parse archive: {exc}")
    if not chunks:
        return pd.DataFrame(columns=BASE_COLUMNS), warnings
    merged = pd.concat(chunks, ignore_index=True)
    merged = merged.sort_values("open_time", kind="mergesort").drop_duplicates("open_time")
    return merged, warnings


def main() -> None:
    args = parse_args()
    start_ts = pd.Timestamp(args.start, tz="UTC")
    end_ts = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1) - pd.Timedelta(minutes=1)
    start_ms = int(start_ts.timestamp() * 1000)
    end_ms = int(end_ts.timestamp() * 1000)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    expected_month_counts: dict[str, dict[str, int]] = {}
    for interval in DIRECT_INTERVALS:
        expected_month_counts[interval] = compute_expected_counts_by_month(
            start_ts=start_ts,
            end_ts=end_ts,
            interval_minutes=interval_minutes(interval),
        )

    all_warnings: list[str] = []
    all_outputs: list[str] = []

    with requests.Session() as session:
        session.headers.update({"User-Agent": "market-data-resume/1.0"})
        for idx, symbol in enumerate(args.symbols, start=1):
            print(f"[{idx}/{len(args.symbols)}] {symbol}: start")
            path = out_dir / f"{symbol}_market_20221030_20260301.csv.gz"
            existing = load_existing_symbol_file(path)

            by_tf: dict[str, pd.DataFrame] = {}
            for tf in TARGET_INTERVALS:
                part = existing[existing["timeframe"] == tf]
                by_tf[tf] = part[BASE_COLUMNS].copy()

            symbol_warnings: list[str] = []
            for tf in DIRECT_INTERVALS:
                current = filter_time_range(by_tf[tf], start_ms=start_ms, end_ms=end_ms)
                missing_months = expected_months_to_redownload(
                    existing=current,
                    expected_counts=expected_month_counts[tf],
                )

                if missing_months:
                    print(
                        f"[{idx}/{len(args.symbols)}] {symbol}: {tf} "
                        f"missing months -> {len(missing_months)}"
                    )
                    fetched, warns = download_missing_months(
                        session=session,
                        symbol=symbol,
                        interval=tf,
                        months=missing_months,
                        start_ms=start_ms,
                        end_ms=end_ms,
                    )
                    symbol_warnings.extend(warns)
                    current = pd.concat([current, fetched], ignore_index=True)
                    current = current.sort_values("open_time", kind="mergesort").drop_duplicates(
                        "open_time"
                    )
                by_tf[tf] = current

            by_tf["7m"] = build_derived_interval(by_tf["1m"], 7)
            by_tf["10m"] = build_derived_interval(by_tf["1m"], 10)
            by_tf["7m"] = filter_time_range(by_tf["7m"], start_ms=start_ms, end_ms=end_ms)
            by_tf["10m"] = filter_time_range(by_tf["10m"], start_ms=start_ms, end_ms=end_ms)

            frames: list[pd.DataFrame] = []
            for tf in TARGET_INTERVALS:
                frame = by_tf[tf]
                if frame.empty:
                    symbol_warnings.append(f"{symbol} {tf}: no rows in range")
                    continue
                frames.append(append_meta(frame, symbol=symbol, timeframe=tf))

            if not frames:
                symbol_warnings.append(f"{symbol}: output skipped, no rows")
                all_warnings.extend(symbol_warnings)
                print(f"[{idx}/{len(args.symbols)}] {symbol}: no data")
                continue

            merged = pd.concat(frames, ignore_index=True)
            merged = merged.sort_values(["timeframe", "open_time"], kind="mergesort").reset_index(drop=True)
            merged.to_csv(path, index=False, compression="gzip")

            stats = {tf: int(len(by_tf[tf])) for tf in TARGET_INTERVALS}
            stat_text = ", ".join(f"{k}={v}" for k, v in stats.items())
            print(f"[{idx}/{len(args.symbols)}] {symbol}: saved {path.name} | {stat_text}")

            all_outputs.append(str(path.resolve()))
            all_warnings.extend(symbol_warnings)

    print("=== OUTPUT FILES ===")
    for item in all_outputs:
        print(item)
    print("=== WARNINGS ===")
    if not all_warnings:
        print("NONE")
    else:
        for warn in all_warnings:
            print(warn)


if __name__ == "__main__":
    main()
