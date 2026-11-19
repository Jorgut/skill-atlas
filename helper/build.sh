#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$ROOT/build}"
APP="$OUT/Skill Atlas Notify.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
swiftc -O "$ROOT/SkillAtlasNotify/main.swift" -o "$APP/Contents/MacOS/SkillAtlasNotify" -framework Cocoa
cp "$ROOT/Info.plist" "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || true
echo "$APP"
