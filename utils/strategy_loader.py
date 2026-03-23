from importlib.util import module_from_spec  # Импортируем инструмент, который помогает создать модуль из найденной спецификации файла.
from importlib.util import spec_from_file_location  # Импортируем инструмент, который позволяет безопасно импортировать Python-файл по пути.
import inspect  # Импортируем inspect, чтобы находить классы внутри загруженных модулей.
from pathlib import Path  # Импортируем Path, чтобы удобно работать с путями к файлам.

import backtrader as bt  # Импортируем Backtrader, чтобы проверять наследование от bt.Strategy.

PROJECT_DIR = Path(__file__).resolve().parent.parent  # Находим корневую папку проекта относительно текущего файла.
STRATEGIES_DIR = PROJECT_DIR / "strategies"  # Указываем путь к папке, где лежат файлы стратегий.
EXCLUDED_FILES = {"__init__.py", "base_strategy.py"}  # Создаем набор файлов, которые не нужно рассматривать как отдельные стратегии.


def load_available_strategies():  # Создаем функцию, которая сканирует папку strategies и возвращает все найденные классы стратегий.
    strategies = {}  # Создаем пустой словарь, в который будем складывать найденные стратегии.
    if not STRATEGIES_DIR.exists():  # Проверяем, существует ли папка strategies в проекте.
        return strategies  # Если папки нет, сразу возвращаем пустой словарь.
    for file_path in sorted(STRATEGIES_DIR.glob("*.py")):  # Проходим по всем Python-файлам в папке strategies в отсортированном порядке.
        if file_path.name in EXCLUDED_FILES:  # Проверяем, не относится ли файл к списку исключений.
            continue  # Пропускаем служебные файлы, которые не должны появляться в списке стратегий.
        module_name = f"dynamic_strategy_{file_path.stem}"  # Создаем уникальное имя модуля, чтобы безопасно загрузить файл по пути.
        module_spec = spec_from_file_location(module_name, file_path)  # Получаем спецификацию для динамического импорта файла стратегии.
        if module_spec is None or module_spec.loader is None:  # Проверяем, удалось ли создать корректную спецификацию модуля.
            continue  # Если спецификацию создать не удалось, просто пропускаем файл.
        module = module_from_spec(module_spec)  # Создаем объект модуля на основе найденной спецификации.
        module_spec.loader.exec_module(module)  # Выполняем код файла стратегии и загружаем его как модуль.
        for _, member in inspect.getmembers(module, inspect.isclass):  # Проходим по всем классам, найденным внутри загруженного модуля.
            if member is bt.Strategy:  # Проверяем, не является ли найденный класс самим базовым классом Backtrader.
                continue  # Пропускаем базовый класс bt.Strategy, потому что он не является пользовательской стратегией.
            if not issubclass(member, bt.Strategy):  # Проверяем, наследуется ли найденный класс от bt.Strategy.
                continue  # Пропускаем все классы, которые не являются стратегиями Backtrader.
            if member.__module__ != module.__name__:  # Проверяем, действительно ли класс объявлен в текущем файле, а не импортирован из другого места.
                continue  # Пропускаем импортированные классы, чтобы не получить дубликаты или лишние стратегии.
            strategies[member.__name__] = member  # Добавляем найденный класс стратегии в словарь по имени класса.
    return strategies  # Возвращаем словарь всех найденных стратегий наружу.
