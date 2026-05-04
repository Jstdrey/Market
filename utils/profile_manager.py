from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROFILE_SCHEMA_VERSION = 1
MAX_HISTORY_ITEMS = 2000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_store() -> dict[str, Any]:
    return {
        "version": PROFILE_SCHEMA_VERSION,
        "pairs": {},
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def load_profiles(file_path: Path) -> dict[str, Any]:
    if not file_path.exists():
        return _base_store()

    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return _base_store()

    if not isinstance(raw, dict):
        return _base_store()

    pairs = raw.get("pairs")
    if not isinstance(pairs, dict):
        pairs = {}

    return {
        "version": int(raw.get("version", PROFILE_SCHEMA_VERSION)),
        "pairs": pairs,
    }


def save_profiles(store: dict[str, Any], file_path: Path) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = _json_safe(store)
    file_path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2), encoding="utf-8")


def merge_params_with_defaults(default_params: dict[str, Any], current_params: dict[str, Any] | None) -> dict[str, Any]:
    merged = deepcopy(default_params)
    if not isinstance(current_params, dict):
        return merged

    for parameter_name in default_params.keys():
        if parameter_name in current_params:
            merged[parameter_name] = current_params[parameter_name]
    return merged


def get_or_init_profile(
    store: dict[str, Any],
    symbol: str,
    strategy_name: str,
    default_params: dict[str, Any],
) -> dict[str, Any]:
    pairs = store.setdefault("pairs", {})
    if not isinstance(pairs, dict):
        store["pairs"] = {}
        pairs = store["pairs"]

    symbol_profiles = pairs.setdefault(symbol, {})
    if not isinstance(symbol_profiles, dict):
        pairs[symbol] = {}
        symbol_profiles = pairs[symbol]

    profile = symbol_profiles.get(strategy_name)
    if not isinstance(profile, dict):
        profile = {
            "active_params": deepcopy(default_params),
            "candidate_params": {},
            "optimization_history": [],
            "updated_at": _now_iso(),
        }
        symbol_profiles[strategy_name] = profile
        return profile

    profile["active_params"] = merge_params_with_defaults(default_params, profile.get("active_params"))
    candidate = profile.get("candidate_params")
    profile["candidate_params"] = candidate if isinstance(candidate, dict) else {}
    history = profile.get("optimization_history")
    profile["optimization_history"] = history if isinstance(history, list) else []
    profile["updated_at"] = str(profile.get("updated_at", _now_iso()))
    return profile


def update_active_params(profile: dict[str, Any], params: dict[str, Any]) -> None:
    profile["active_params"] = _json_safe(params)
    profile["updated_at"] = _now_iso()


def update_candidate_params(profile: dict[str, Any], params: dict[str, Any] | None) -> None:
    profile["candidate_params"] = _json_safe(params or {})
    profile["updated_at"] = _now_iso()


def append_optimization_history(profile: dict[str, Any], result_rows: list[dict[str, Any]]) -> None:
    history = profile.get("optimization_history")
    if not isinstance(history, list):
        history = []

    for row in result_rows:
        history.append(_json_safe(row))

    if len(history) > MAX_HISTORY_ITEMS:
        history = history[-MAX_HISTORY_ITEMS:]

    profile["optimization_history"] = history
    profile["updated_at"] = _now_iso()
