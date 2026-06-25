#!/usr/bin/env bash
set -euo pipefail

# Live Apache log monitor via SSH + tail.
#
# Usage:
#   ./scripts/remote-watch.sh user@host /var/log/apache2/access_ssl.log
#   ./scripts/remote-watch.sh user@host \
#     /var/log/apache2/access_ssl.log /var/log/apache2/error_ssl.log

SSH_HOST="${1:?SSH host required, e.g. user@server}"
shift
LOG_FILES=("$@")
if [ "${#LOG_FILES[@]}" -eq 0 ]; then
  LOG_FILES=(
    /var/log/apache2/access_ssl.log
    /var/log/apache2/error_ssl.log
  )
fi

GEOIP_DB="${GEOIP_DB:-GeoLite2-Country_20260612/GeoLite2-Country.mmdb}"
TAIL_CMD="sudo tail -F ${LOG_FILES[*]}"

exec ssh -o ServerAliveInterval=30 "${SSH_HOST}" "${TAIL_CMD}" \
  | uv run python main.py watch --geoip-db "${GEOIP_DB}"
