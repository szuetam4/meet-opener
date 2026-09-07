#!/usr/bin/env bash
# Instalator meet-opener — tworzy wszystko, czego skrypt potrzebuje.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"

echo "==> Instalacja meet-opener z: $APP_DIR"

# 1. Sprawdzenie zależności
command -v python3 >/dev/null || { echo "Brak python3. Zainstaluj: sudo pacman -S python"; exit 1; }
python3 -c "import yaml" 2>/dev/null || { echo "Brak PyYAML. Zainstaluj: sudo pacman -S python-yaml"; exit 1; }
command -v xdg-open >/dev/null || echo "UWAGA: brak xdg-open (sudo pacman -S xdg-utils) — otwieranie linków nie zadziała."
command -v notify-send >/dev/null || echo "UWAGA: brak notify-send (sudo pacman -S libnotify) — powiadomienia nie zadziałają."

chmod +x "$APP_DIR/meet.py"
mkdir -p "$APP_DIR/data"

# 2. Konfiguracja — nie nadpisuj, jeśli już istnieje (np. przy reinstalacji)
if [ ! -f "$APP_DIR/meetings.yaml" ]; then
    cp "$APP_DIR/meetings.example.yaml" "$APP_DIR/meetings.yaml"
    echo "Utworzono $APP_DIR/meetings.yaml na bazie przykładu."
fi

# 3. Jednostki systemd — jedyne miejsce poza tym folderem, wymagane przez systemd
mkdir -p "$SYSTEMD_USER_DIR"
sed "s#{{APP_DIR}}#$APP_DIR#g" "$APP_DIR/systemd/meet-opener.service.template" > "$SYSTEMD_USER_DIR/meet-opener.service"
cp "$APP_DIR/systemd/meet-opener.timer" "$SYSTEMD_USER_DIR/meet-opener.timer"

# 4. (opcjonalnie) symlink CLI do PATH — zakomentuj ten blok, jeśli go nie chcesz
mkdir -p "$BIN_DIR"
ln -sf "$APP_DIR/meet.py" "$BIN_DIR/meet"
if ! echo "$PATH" | grep -q "$BIN_DIR"; then
    echo "UWAGA: $BIN_DIR nie jest w PATH. Dodaj do ~/.bashrc:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

# 5. Aktywacja timera
systemctl --user daemon-reload
systemctl --user enable --now meet-opener.timer

echo "==> Gotowe."
echo "==> Sprawdź:   systemctl --user list-timers | grep meet-opener"
echo "==> Edytuj:    nano $APP_DIR/meetings.yaml"
