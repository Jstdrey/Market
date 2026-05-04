#!/usr/bin/env sh
set -eu

mkdir -p /app/output /app/data/cache

if [ ! -f /app/strategy_profiles.json ]; then
  cat <<'JSON' > /app/strategy_profiles.json
{
  "version": 1,
  "pairs": {}
}
JSON
fi

if [ ! -f /app/data.csv ]; then
  printf 'timestamp,datetime,open,high,low,close,volume\n' > /app/data.csv
fi

exec "$@"
