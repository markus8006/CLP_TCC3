#!/usr/bin/env bash
set -euo pipefail

python docker/wait_for_db.py

exec "$@"
