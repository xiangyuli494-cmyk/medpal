#!/usr/bin/env bash
# 树莓派 / Linux 设备端 kiosk 启动
# 用法： ./tools/start-kiosk.sh [URL]
set -euo pipefail

URL="${1:-http://127.0.0.1:5176}"
PROFILE="${MEDPAL_KIOSK_PROFILE:-$HOME/.config/medpal-kiosk}"
mkdir -p "$PROFILE"

# kiosk=1 会隐藏模拟器的联调工具条，只保留设备画面
if [[ "$URL" == *"kiosk=1"* ]]; then
  KIOSK_URL="$URL"
elif [[ "$URL" == *"?"* ]]; then
  KIOSK_URL="$URL&kiosk=1"
else
  KIOSK_URL="$URL?kiosk=1"
fi

for browser in chromium chromium-browser google-chrome google-chrome-stable; do
  if command -v "$browser" >/dev/null 2>&1; then
    echo "设备端 kiosk: $KIOSK_URL"
    echo "Browser: $(command -v "$browser")"
    exec "$browser" \
      --kiosk \
      --app="$KIOSK_URL" \
      --user-data-dir="$PROFILE" \
      --noerrdialogs \
      --disable-infobars \
      --disable-pinch \
      --overscroll-history-navigation=0
  fi
done

echo "未找到 Chromium / Chrome，请先安装。" >&2
exit 1
