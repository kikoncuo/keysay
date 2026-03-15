#!/usr/bin/env bash
# Create a DMG installer with drag-to-Applications layout.
# Prerequisites: run build_app.sh first.

set -euo pipefail

cd "$(dirname "$0")/.."

APP="dist/keysay.app"
DMG="dist/keysay-installer.dmg"
VOLUME_NAME="keysay"
STAGING="dist/dmg-staging"

if [ ! -d "$APP" ]; then
    echo "Error: $APP not found. Run scripts/build_app.sh first."
    exit 1
fi

echo "==> Creating DMG installer..."

# Clean previous
rm -rf "$STAGING" "$DMG"

# Stage the DMG contents
mkdir -p "$STAGING"
cp -R "$APP" "$STAGING/"
ln -s /Applications "$STAGING/Applications"

# Create DMG
hdiutil create -volname "$VOLUME_NAME" \
    -srcfolder "$STAGING" \
    -ov -format UDZO \
    "$DMG"

# Clean staging
rm -rf "$STAGING"

echo "==> Done! DMG at: $DMG"
echo "    Size: $(du -h "$DMG" | cut -f1)"
