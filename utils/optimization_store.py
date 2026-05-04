from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


STORE_SCHEMA_VERSION = 1
DEFAULT_TTL_HOURS = 72


def build_optimization_scope_key(symbol: str, timeframe: str, strategy_name: str) -> str:
    normalized_symbol = str(symbol or "").strip().upper()
    normalized_timeframe = str(timeframe or "").strip().lower()
    normalized_strategy = str(strategy_name or "").strip()
    return f"{normalized_symbol}|{normalized_timeframe}|{normalized_strategy}"


def _base_store(ttl_hours: int = DEFAULT_TTL_HOURS) -> dict[str, Any]:
    return {
        "version": STORE_SCHEMA_VERSION,
        "ttl_hours": int(ttl_hours),
        "records": {},
    }


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return float(value)
        return str(value)

    item_method = getattr(value, "item", None)
    if callable(item_method):
        try:
            return _json_safe(item_method())
        except Exception:
            return str(value)

    return str(value)


def _load_store(file_path: Path, *, ttl_hours: int = DEFAULT_TTL_HOURS) -> dict[str, Any]:
    if not file_path.exists():
        return _base_store(ttl_hours=ttl_hours)

    try:
        raw_store = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return _base_store(ttl_hours=ttl_hours)

    if not isinstance(raw_store, dict):
        return _base_store(ttl_hours=ttl_hours)

    raw_records = raw_store.get("records")
    records = raw_records if isinstance(raw_records, dict) else {}

    try:
        raw_ttl_hours = int(raw_store.get("ttl_hours", ttl_hours))
    except (TypeError, ValueError):
        raw_ttl_hours = int(ttl_hours)

    return {
        "version": int(raw_store.get("version", STORE_SCHEMA_VERSION)),
        "ttl_hours": max(1, raw_ttl_hours),
        "records": records,
    }


def _write_store_atomic(file_path: Path, store: dict[str, Any]) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_file_path = file_path.with_suffix(f"{file_path.suffix}.tmp")
    serialized_store = json.dumps(_json_safe(store), ensure_ascii=False, indent=2)
    tmp_file_path.write_text(serialized_store, encoding="utf-8")
    tmp_file_path.replace(file_path)


def prune_expired_records(
    store: dict[str, Any],
    *,
    now_utc: datetime | None = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> bool:
    safe_now_utc = now_utc or datetime.now(timezone.utc)
    normalized_ttl_hours = max(1, int(ttl_hours))
    raw_records = store.get("records")
    records = raw_records if isinstance(raw_records, dict) else {}
    changed = records is not raw_records

    for scope_key, payload in list(records.items()):
        if not isinstance(payload, dict):
            records.pop(scope_key, None)
            changed = True
            continue

        expires_at = _parse_iso_datetime(payload.get("expires_at"))
        saved_at = _parse_iso_datetime(payload.get("saved_at"))
        if expires_at is None and saved_at is not None:
            expires_at = saved_at + timedelta(hours=normalized_ttl_hours)

        if expires_at is None or safe_now_utc >= expires_at:
            records.pop(scope_key, None)
            changed = True

    if store.get("ttl_hours") != normalized_ttl_hours:
        store["ttl_hours"] = normalized_ttl_hours
        changed = True
    if store.get("records") is not records:
        store["records"] = records
        changed = True
    return changed


def save_last_optimization_result(
    file_path: Path,
    *,
    scope_key: str,
    result_data: dict[str, Any],
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> None:
    normalized_scope_key = str(scope_key or "").strip()
    if not normalized_scope_key:
        return

    try:
        safe_now_utc = datetime.now(timezone.utc)
        normalized_ttl_hours = max(1, int(ttl_hours))
        store = _load_store(file_path=file_path, ttl_hours=normalized_ttl_hours)
        prune_expired_records(
            store=store,
            now_utc=safe_now_utc,
            ttl_hours=normalized_ttl_hours,
        )
        records = store.setdefault("records", {})
        records[normalized_scope_key] = {
            "saved_at": safe_now_utc.isoformat(),
            "expires_at": (safe_now_utc + timedelta(hours=normalized_ttl_hours)).isoformat(),
            "result_data": _json_safe(result_data),
        }
        _write_store_atomic(file_path=file_path, store=store)
    except Exception:
        return


def load_last_optimization_result(
    file_path: Path,
    *,
    scope_key: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> dict[str, Any] | None:
    normalized_scope_key = str(scope_key or "").strip()
    if not normalized_scope_key:
        return None

    try:
        normalized_ttl_hours = max(1, int(ttl_hours))
        store = _load_store(file_path=file_path, ttl_hours=normalized_ttl_hours)
        was_pruned = prune_expired_records(store=store, ttl_hours=normalized_ttl_hours)

        records = store.get("records")
        if not isinstance(records, dict):
            if was_pruned:
                _write_store_atomic(file_path=file_path, store=store)
            return None

        payload = records.get(normalized_scope_key)
        if not isinstance(payload, dict):
            if was_pruned:
                _write_store_atomic(file_path=file_path, store=store)
            return None

        result_data = payload.get("result_data")
        if was_pruned:
            _write_store_atomic(file_path=file_path, store=store)

        return result_data if isinstance(result_data, dict) else None
    except Exception:
        return None
