#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
DEPLOY_DIR="${ROOT_DIR}/deploy"
RUNTIME_DIR="${DEPLOY_DIR}/runtime"
STATE_DIR="${RUNTIME_DIR}/state"
CACHE_DIR="${RUNTIME_DIR}/data_cache"
OUTPUT_DIR="${RUNTIME_DIR}/output"

mkdir -p "${STATE_DIR}" "${CACHE_DIR}" "${OUTPUT_DIR}"

if [ -d "${ROOT_DIR}/data/cache" ]; then
  cp -an "${ROOT_DIR}/data/cache/." "${CACHE_DIR}/" || true
fi

if [ -d "${ROOT_DIR}/output" ]; then
  cp -an "${ROOT_DIR}/output/." "${OUTPUT_DIR}/" || true
fi

if [ ! -f "${STATE_DIR}/strategy_profiles.json" ]; then
  if [ -f "${ROOT_DIR}/strategy_profiles.json" ]; then
    cp "${ROOT_DIR}/strategy_profiles.json" "${STATE_DIR}/strategy_profiles.json"
  else
    cat <<'JSON' > "${STATE_DIR}/strategy_profiles.json"
{
  "version": 1,
  "pairs": {}
}
JSON
  fi
fi

if [ ! -f "${STATE_DIR}/data.csv" ]; then
  if [ -f "${ROOT_DIR}/data.csv" ]; then
    cp "${ROOT_DIR}/data.csv" "${STATE_DIR}/data.csv"
  else
    printf 'timestamp,datetime,open,high,low,close,volume\n' > "${STATE_DIR}/data.csv"
  fi
fi

if [ ! -f "${DEPLOY_DIR}/.env.server" ]; then
  cat > "${DEPLOY_DIR}/.env.server" <<EOF
TZ=Europe/Moscow
STREAMLIT_SERVER_PORT=8501
MARKET_PUBLIC_PORT=8501
MARKET_IMAGE_TAG=latest
MARKET_RUNTIME_DIR=${RUNTIME_DIR}
EOF
fi

echo "Runtime prepared:"
echo "  ROOT_DIR=${ROOT_DIR}"
echo "  RUNTIME_DIR=${RUNTIME_DIR}"
echo "  ENV_FILE=${DEPLOY_DIR}/.env.server"
