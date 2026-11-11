#!/usr/bin/env bash
#
# Capture the three Skill Atlas showcase pages with headless Chrome.
#
# Usage:
#   scripts/screenshot.sh [output-dir] [base-url]
#
#   output-dir   Where the PNGs go (default: ./screenshots)
#   base-url     Site root (default: https://jorgut.github.io/skill-atlas/)
#
# Environment:
#   CHROME               Path to the Chrome/Chromium binary.
#   WINDOW_SIZE          Chrome window size (default: 1440,3200).
#   VIRTUAL_TIME_BUDGET  Virtual milliseconds to let CSS/JS finish
#                        (default: 12000, enough for the terminal demo to finish).
#                        Lower it for faster, early-state shots.
#
# A throwaway --user-data-dir is always used: headless Chrome cannot share a
# profile with a running browser, and sandboxed sessions may not write the
# default profile directory.
#
# Examples:
#   scripts/screenshot.sh
#   scripts/screenshot.sh /tmp/shots http://127.0.0.1:8000/
#   WINDOW_SIZE=390,1400 scripts/screenshot.sh /tmp/shots-mobile http://127.0.0.1:8000/

set -euo pipefail

OUT_DIR="${1:-./screenshots}"
BASE_URL="${2:-https://jorgut.github.io/skill-atlas/}"
WINDOW_SIZE="${WINDOW_SIZE:-1440,3200}"
VIRTUAL_TIME_BUDGET="${VIRTUAL_TIME_BUDGET:-12000}"

DEFAULT_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
CHROME="${CHROME:-$DEFAULT_CHROME}"

if [[ ! -x "$CHROME" ]]; then
  cat >&2 <<EOF
error: Chrome was not found (or is not executable):
  $CHROME

Install Google Chrome, or point CHROME at a Chromium binary, for example:
  CHROME="/Applications/Chromium.app/Contents/MacOS/Chromium" $(basename "$0")
EOF
  exit 1
fi

if [[ ! -d "$OUT_DIR" ]]; then
  mkdir -p "$OUT_DIR"
fi
OUT_DIR_ABS="$(cd "$OUT_DIR" && pwd)"

BASE_URL="${BASE_URL%/}"

# Headless Chrome clamps the layout viewport to a minimum width of 500 CSS px.
# The image keeps the requested size, so anything narrower is a crop of a 500 px
# layout, not a phone-width rendering. Warn instead of shipping a misleading shot.
WINDOW_WIDTH="${WINDOW_SIZE%%,*}"
if [[ "$WINDOW_WIDTH" =~ ^[0-9]+$ ]] && (( WINDOW_WIDTH < 500 )); then
  cat >&2 <<EOF
warning: WINDOW_SIZE=${WINDOW_SIZE} is narrower than 500 px.
         Headless Chrome lays the page out at a minimum width of 500 px and
         crops the image, so this is NOT a true ${WINDOW_WIDTH} px rendering.
         Use Chrome DevTools device emulation (or a CDP script with
         Emulation.setDeviceMetricsOverride) for phone-width captures.
EOF
fi

PROFILE_DIR="$(mktemp -d "${TMPDIR:-/tmp}/skill-atlas-chrome.XXXXXX")"
CHROME_LOG="$(mktemp "${TMPDIR:-/tmp}/skill-atlas-chrome-log.XXXXXX")"

cleanup() {
  rm -rf "$PROFILE_DIR"
  rm -f "$CHROME_LOG"
}
trap cleanup EXIT

capture() {
  local path="$1"
  local name="$2"
  local url="${BASE_URL}${path}"
  local target="${OUT_DIR_ABS}/${name}.png"

  rm -f "$target"

  if ! "$CHROME" \
    --headless=new \
    --disable-gpu \
    --no-sandbox \
    --hide-scrollbars \
    --no-first-run \
    --no-default-browser-check \
    --disable-extensions \
    --disable-dev-shm-usage \
    --force-device-scale-factor=1 \
    --run-all-compositor-stages-before-draw \
    --virtual-time-budget="$VIRTUAL_TIME_BUDGET" \
    --user-data-dir="$PROFILE_DIR" \
    --window-size="$WINDOW_SIZE" \
    --screenshot="$target" \
    "$url" >"$CHROME_LOG" 2>&1; then
    echo "error: headless Chrome failed for $url" >&2
    sed 's/^/  /' "$CHROME_LOG" >&2
    exit 1
  fi

  if [[ ! -s "$target" ]]; then
    echo "error: Chrome did not produce $target for $url" >&2
    sed 's/^/  /' "$CHROME_LOG" >&2
    exit 1
  fi

  echo "$target"
}

echo "Capturing ${BASE_URL} at ${WINDOW_SIZE} into ${OUT_DIR_ABS} ..." >&2

EN_PNG="$(capture "" "en")"
ZH_PNG="$(capture "/zh-CN/" "zh")"
RU_PNG="$(capture "/ru/" "ru")"

echo "Screenshots written:"
echo "  $EN_PNG"
echo "  $ZH_PNG"
echo "  $RU_PNG"
