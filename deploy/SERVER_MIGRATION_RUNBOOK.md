# Market: полный перенос проекта на сервер

## Что подготовлено

- `Dockerfile` и `.dockerignore` для воспроизводимой сборки.
- `deploy/docker-compose.server.yml` для запуска приложения.
- `deploy/.env.server.example` с переменными окружения.
- `deploy/scripts/local_package_release.ps1` для сборки релизного архива на локальной машине.
- `deploy/scripts/local_upload_release.ps1` для загрузки архива на сервер.
- `deploy/scripts/server_deploy_from_archive.sh` для деплоя, бэкапа runtime и запуска Docker Compose.
- `deploy/scripts/backup_runtime.sh` для ручного backup.
- `deploy/CODEX_DEPLOY_PROMPT.md` с готовым промптом для Codex.

## Требования к серверу

- Linux (Ubuntu/Debian), Docker Engine и Docker Compose plugin.
- Открытый порт `8501` (или свой порт через `MARKET_PUBLIC_PORT`).
- Рекомендация: 2+ vCPU, 4+ GB RAM, 20+ GB SSD.

Если Docker не установлен:

```bash
sudo bash deploy/scripts/install_docker_ubuntu.sh
```

## Шаг 1. Сборка релизного архива (локально)

Из корня проекта:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\local_package_release.ps1 -IncludeOutput -IncludeDataCache
```

Архив появится в `deploy/artifacts/market_release_YYYYMMDD_HHMMSS.tar.gz`.

Если не нужно переносить тяжелые исторические данные, запускайте без `-IncludeOutput -IncludeDataCache`.

## Шаг 2. Загрузка архива на сервер

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\local_upload_release.ps1 `
  -ArchivePath .\deploy\artifacts\market_release_YYYYMMDD_HHMMSS.tar.gz `
  -ServerHost YOUR_SERVER_IP `
  -ServerUser root `
  -RemoteDir /opt/market/incoming
```

## Шаг 3. Первый деплой на сервере

```bash
mkdir -p /opt/market/incoming /opt/market/bootstrap
ARCHIVE="$(ls -1t /opt/market/incoming/market_release_*.tar.gz | head -n 1)"
tar -xzf "$ARCHIVE" -C /opt/market/bootstrap
bash /opt/market/bootstrap/deploy/scripts/server_deploy_from_archive.sh "$ARCHIVE" /opt/market
```

Что произойдет:

- создастся новый релиз в `/opt/market/releases/<timestamp>`
- создастся/обновится symlink `/opt/market/current`
- persistent runtime будет в `/opt/market/shared/runtime`
- env-файл будет в `/opt/market/shared/.env.server`
- backup runtime будет в `/opt/market/backups/runtime_<timestamp>.tar.gz`

## Шаг 4. Проверка запуска

```bash
docker compose -f /opt/market/current/deploy/docker-compose.server.yml --env-file /opt/market/shared/.env.server ps
curl -f http://127.0.0.1:8501/_stcore/health
```

Если используется внешний домен/порт, проверьте доступ снаружи.

## Обновление на новый релиз

После загрузки нового архива:

```bash
ARCHIVE="$(ls -1t /opt/market/incoming/market_release_*.tar.gz | head -n 1)"
bash /opt/market/current/deploy/scripts/server_deploy_from_archive.sh "$ARCHIVE" /opt/market
```

## Rollback

Откат на предыдущий релиз:

```bash
PREV_RELEASE="$(ls -1dt /opt/market/releases/* | sed -n '2p')"
docker compose -f "$PREV_RELEASE/deploy/docker-compose.server.yml" --env-file /opt/market/shared/.env.server up -d --build --remove-orphans
ln -sfn "$PREV_RELEASE" /opt/market/current
```

Runtime-данные не теряются, так как лежат отдельно: `/opt/market/shared/runtime`.
