#!/usr/bin/env bash
# Build keysay.app using PyInstaller.
#
# Usage:
#   ./scripts/build_app.sh
#
# Output: dist/keysay.app

set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Cleaning previous builds..."
rm -rf build dist

echo "==> Building keysay.app..."
python3 -m PyInstaller keysay.spec --noconfirm

echo ""
echo "==> Done! App bundle at: dist/keysay.app"
echo "    Launch with: open dist/keysay.app"
