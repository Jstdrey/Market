from importlib.util import module_from_spec
from importlib.util import spec_from_file_location
import inspect
import sys
from pathlib import Path

import backtrader as bt

PROJECT_DIR = Path(__file__).resolve().parent.parent
STRATEGIES_DIR = PROJECT_DIR / "strategies"
EXCLUDED_FILES = {"__init__.py", "base_strategy.py"}


def load_available_strategies() -> dict[str, type[bt.Strategy]]:
    strategies: dict[str, type[bt.Strategy]] = {}
    if not STRATEGIES_DIR.exists():
        return strategies

    for file_path in sorted(STRATEGIES_DIR.glob("*.py")):
        if file_path.name in EXCLUDED_FILES:
            continue

        module_name = f"dynamic_strategy_{file_path.stem}"
        module_spec = spec_from_file_location(module_name, file_path)
        if module_spec is None or module_spec.loader is None:
            continue

        module = module_from_spec(module_spec)
        sys.modules[module_name] = module
        module_spec.loader.exec_module(module)

        for _, member in inspect.getmembers(module, inspect.isclass):
            if member is bt.Strategy:
                continue
            if not issubclass(member, bt.Strategy):
                continue
            if member.__module__ != module.__name__:
                continue
            strategies[member.__name__] = member

    return strategies
