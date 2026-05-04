# Готовый промпт для Codex (вставить на сервере)

```text
Ты работаешь на Linux-сервере и должен развернуть проект Market из релизного архива.

Контекст:
- Базовая папка деплоя: /opt/market
- Входящие архивы: /opt/market/incoming/market_release_*.tar.gz
- Нужен самый новый архив.

Сделай строго по шагам:
1) Найди самый свежий архив в /opt/market/incoming.
2) Если архив не найден — остановись и сообщи, что нужно загрузить архив.
3) Распакуй архив во временную папку /opt/market/bootstrap (создай при необходимости).
4) Запусти скрипт деплоя из распакованного релиза:
   bash /opt/market/bootstrap/deploy/scripts/server_deploy_from_archive.sh "<ARCHIVE_PATH>" /opt/market
5) Проверь состояние:
   - docker compose -f /opt/market/current/deploy/docker-compose.server.yml --env-file /opt/market/shared/.env.server ps
   - curl -f http://127.0.0.1:8501/_stcore/health
6) Выведи краткий отчёт:
   - какой архив развернут
   - текущий релиз (/opt/market/current -> ...)
   - статус контейнера
   - результат health-check
   - путь к backup-файлу runtime.

Ограничения:
- Не удаляй /opt/market/shared/runtime.
- Не выполняй destructive-команды (rm -rf по /opt/market/shared и т.п.).
- Если шаг падает — остановись, покажи ошибку и предложи безопасный следующий шаг.
```
