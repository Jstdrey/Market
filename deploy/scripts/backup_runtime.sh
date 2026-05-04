#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${1:-/opt/market}"
RUNTIME_DIR="${BASE_DIR}/shared/runtime"
BACKUP_DIR="${BASE_DIR}/backups"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

if [ ! -d "${RUNTIME_DIR}" ]; then
  echo "Runtime directory does not exist: ${RUNTIME_DIR}"
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
ARCHIVE_PATH="${BACKUP_DIR}/runtime_${TIMESTAMP}.tar.gz"
tar -czf "${ARCHIVE_PATH}" -C "${RUNTIME_DIR}" .

echo "Backup created: ${ARCHIVE_PATH}"
