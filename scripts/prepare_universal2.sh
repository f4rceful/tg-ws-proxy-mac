#!/bin/bash
set -euo pipefail

# Run inside a Python 3.12 universal2 virtual environment on macOS.
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
BUILD_PYTHON="${BUILD_PYTHON:-python3}"
"$BUILD_PYTHON" -c 'import sys; assert sys.platform == "darwin" and sys.version_info[:2] == (3, 12), "Use Python 3.12 on macOS"'
"$BUILD_PYTHON" -m pip install delocate==0.13.0
mkdir -p wheelhouse/arm64 wheelhouse/x86_64 wheelhouse/universal2
"$BUILD_PYTHON" -m pip download --only-binary=:all: --no-deps \
  --platform macosx_11_0_arm64 --python-version 3.12 --implementation cp \
  -d wheelhouse/arm64 cffi==2.0.0
"$BUILD_PYTHON" -m pip download --only-binary=:all: --no-deps \
  --platform macosx_10_13_x86_64 --python-version 3.12 --implementation cp \
  -d wheelhouse/x86_64 cffi==2.0.0
"$BUILD_PYTHON" -m delocate.cmd.delocate_merge \
  wheelhouse/arm64/cffi-*.whl wheelhouse/x86_64/cffi-*.whl -w wheelhouse/universal2
"$BUILD_PYTHON" -m pip install --no-deps wheelhouse/universal2/cffi-*.whl
"$BUILD_PYTHON" -m pip install '.[build]'
