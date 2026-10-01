#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
DART=${DART:-dart}
providers=false
flutter=false
build=false
for arg in "$@"; do
  case "$arg" in
    --providers) providers=true ;;
    --flutter) flutter=true ;;
    --build) build=true ;;
    *) echo "Usage: bash tool/check.sh [--providers] [--flutter] [--build]" >&2; exit 64 ;;
  esac
done
if "$flutter"; then
  test -f examples/flutter_fixture/.dart_tool/package_config.json || { echo 'Resolve Flutter fixture dependencies first.' >&2; exit 78; }
  export POLYCODEGRAPH_REQUIRE_FLUTTER=1
fi
if "$providers"; then
  "${NODE:-node}" --check providers/typescript/index.cjs
  test -f providers/typescript/node_modules/typescript/package.json
  test -f providers/go/graph || test -f providers/go/graph.exe
  export POLYCODEGRAPH_REQUIRE_PROVIDERS=1
fi
"$DART" format --output=none --set-exit-if-changed bin lib test
"$DART" analyze --fatal-infos
"$DART" test --reporter expanded
if "$build"; then
  mkdir -p build
  "$DART" compile exe bin/polycodegraph.dart -o build/polycodegraph
  ./build/polycodegraph --version
fi
