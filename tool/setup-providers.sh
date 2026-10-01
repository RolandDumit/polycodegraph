#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${DART:-dart}" run tool/setup_providers.dart "$@"
