#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
"${NODE:-node}" --version
"${JAVA:-java}" -version
"${GO:-go}" version
npm ci --ignore-scripts --prefix providers/typescript
(
  cd providers/go
  "${GO:-go}" mod verify
  "${GO:-go}" build -buildvcs=false -mod=readonly -o graph .
)
