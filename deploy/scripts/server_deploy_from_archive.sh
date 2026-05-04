#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 /path/to/market_release_YYYYMMDD_HHMMSS.tar.gz [base_dir]"
  exit 1
fi

ARCHIVE_PATH="$1"
BASE_DIR="${2:-/opt/market}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RELEASES_DIR="${BASE_DIR}/releases"
SHARED_DIR="${BASE_DIR}/shared"
RUNTIME_DIR="${SHARED_DIR}/runtime"
ENV_FILE="${SHARED_DIR}/.env.server"
BACKUP_DIR="${BASE_DIR}/backups"
RELEASE_DIR="${RELEASES_DIR}/${TIMESTAMP}"

if [ ! -f "${ARCHIVE_PATH}" ]; then
  echo "Archive not found: ${ARCHIVE_PATH}"
  exit 1
fi

mkdir -p "${RELEASE_DIR}" "${RUNTIME_DIR}/state" "${RUNTIME_DIR}/data_cache" "${RUNTIME_DIR}/output" "${BACKUP_DIR}"

tar -xzf "${ARCHIVE_PATH}" -C "${RELEASE_DIR}"
chmod +x "${RELEASE_DIR}/deploy/scripts/"*.sh || true

if [ -d "${RELEASE_DIR}/data/cache" ]; then
  cp -an "${RELEASE_DIR}/data/cache/." "${RUNTIME_DIR}/data_cache/" || true
fi

if [ -d "${RELEASE_DIR}/output" ]; then
  cp -an "${RELEASE_DIR}/output/." "${RUNTIME_DIR}/output/" || true
fi

if [ ! -f "${RUNTIME_DIR}/state/strategy_profiles.json" ]; then
  if [ -f "${RELEASE_DIR}/strategy_profiles.json" ]; then
    cp "${RELEASE_DIR}/strategy_profiles.json" "${RUNTIME_DIR}/state/strategy_profiles.json"
  else
    cat <<'JSON' > "${RUNTIME_DIR}/state/strategy_profiles.json"
{
  "version": 1,
  "pairs": {}
}
JSON
  fi
fi

if [ ! -f "${RUNTIME_DIR}/state/data.csv" ]; then
  if [ -f "${RELEASE_DIR}/data.csv" ]; then
    cp "${RELEASE_DIR}/data.csv" "${RUNTIME_DIR}/state/data.csv"
  else
    printf 'timestamp,datetime,open,high,low,close,volume\n' > "${RUNTIME_DIR}/state/data.csv"
  fi
fi

if [ -d "${RUNTIME_DIR}" ]; then
  tar -czf "${BACKUP_DIR}/runtime_${TIMESTAMP}.tar.gz" -C "${RUNTIME_DIR}" .
fi

if [ ! -f "${ENV_FILE}" ]; then
  cat > "${ENV_FILE}" <<EOF
TZ=Europe/Moscow
STREAMLIT_SERVER_PORT=8501
MARKET_PUBLIC_PORT=8501
MARKET_IMAGE_TAG=latest
MARKET_RUNTIME_DIR=${RUNTIME_DIR}
EOF
fi

if ! grep -q '^MARKET_RUNTIME_DIR=' "${ENV_FILE}"; then
  echo "MARKET_RUNTIME_DIR=${RUNTIME_DIR}" >> "${ENV_FILE}"
fi

docker compose \
  -f "${RELEASE_DIR}/deploy/docker-compose.server.yml" \
  --env-file "${ENV_FILE}" \
  up -d --build --remove-orphans

ln -sfn "${RELEASE_DIR}" "${BASE_DIR}/current"

docker compose \
  -f "${RELEASE_DIR}/deploy/docker-compose.server.yml" \
  --env-file "${ENV_FILE}" \
  ps

echo "Deploy complete."
echo "Release: ${RELEASE_DIR}"
echo "Current symlink: ${BASE_DIR}/current"
echo "Env file: ${ENV_FILE}"
echo "Runtime backup: ${BACKUP_DIR}/runtime_${TIMESTAMP}.tar.gz"
