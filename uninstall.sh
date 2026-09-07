#!/usr/bin/env bash
# Deinstalator meet-opener — usuwa ślady w systemie, zostawia Twoje dane.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

echo "==> Odinstalowywanie meet-opener..."

systemctl --user disable --now meet-opener.timer 2>/dev/null || true
rm -f "$SYSTEMD_USER_DIR/meet-opener.service" "$SYSTEMD_USER_DIR/meet-opener.timer"
systemctl --user daemon-reload
rm -f "$BIN_DIR/meet"

echo "==> Usunięto usługę systemd i symlink CLI."
echo "==> Twoje pliki (config, logi, kod) nadal są w: $APP_DIR"
echo "==> Aby usunąć wszystko całkowicie:"
echo "      rm -rf \"$APP_DIR\""
