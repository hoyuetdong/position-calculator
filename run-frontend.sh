#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
set -a
source .env
set +a
export HOSTNAME=0.0.0.0 PORT=3000
cd .next/standalone
exec node server.js
