#!/usr/bin/env python3
"""
meet.py — lokalny automat do otwierania linków Google Meet o zadanej godzinie.

WERSJA "ALL-IN-ONE": wszystkie pliki (config, log, stan) trzymane są
w tym samym folderze co skrypt — nic nie jest rozrzucone po systemie.

Ten sam skrypt pełni dwie role:
  1) "checker" (subkomenda `check`) — uruchamiany co minutę przez systemd timer.
  2) CLI do zarządzania listą spotkań (list / add / remove / enable / disable / test).

Wymagania: Python 3.9+, PyYAML, libnotify (notify-send), xdg-utils (xdg-open).
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Brakuje modułu PyYAML. Zainstaluj: sudo pacman -S python-yaml", file=sys.stderr)
    sys.exit(1)

# --- Ścieżki: WSZYSTKO względem lokalizacji tego pliku (self-contained) --------
# Path(__file__).resolve() rozwiązuje też symlink z ~/.local/bin/meet
# do prawdziwej lokalizacji w folderze aplikacji — dlatego działa niezależnie
# od tego, czy skrypt wołasz bezpośrednio, czy przez symlink w PATH.

APP_DIR = Path(__file__).resolve().parent
CONFIG_FILE = APP_DIR / "meetings.yaml"
DATA_DIR = APP_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = DATA_DIR / "meet-opener.log"

VALID_RECURRENCE = {"once", "daily", "weekdays", "weekly"}
VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
WEEKDAY_INDEX_TO_CODE = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}

# --- Logowanie -------------------------------------------------------------------

def setup_logging():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("meet-opener")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    logger.addHandler(stream_handler)

    return logger

log = setup_logging()

# --- Wczytywanie / zapisywanie konfiguracji --------------------------------------

def load_config():
    if not CONFIG_FILE.exists():
        log.warning(f"Plik konfiguracyjny nie istnieje: {CONFIG_FILE}")
        return {"meetings": []}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        log.error(f"Błąd parsowania YAML w {CONFIG_FILE}: {e}")
        return {"meetings": []}

    if not data.get("meetings"):
        data["meetings"] = []
    return data


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def validate_meeting(m, index):
    errors = []
    for field in ("id", "name", "url", "time", "recurrence"):
        if not m.get(field):
            errors.append(f"wpis #{index}: brak wymaganego pola '{field}'")
    if errors:
        return errors

    try:
        datetime.strptime(m["time"], "%H:%M")
    except ValueError:
        errors.append(f"wpis '{m['id']}': pole 'time' musi mieć format HH:MM, jest '{m['time']}'")

    if m["recurrence"] not in VALID_RECURRENCE:
        errors.append(f"wpis '{m['id']}': recurrence musi być jednym z {VALID_RECURRENCE}")
    elif m["recurrence"] == "once":
        if not m.get("date"):
            errors.append(f"wpis '{m['id']}': recurrence=once wymaga pola 'date' (YYYY-MM-DD)")
        else:
            try:
                datetime.strptime(str(m["date"]), "%Y-%m-%d")
            except ValueError:
                errors.append(f"wpis '{m['id']}': pole 'date' musi mieć format YYYY-MM-DD")
    elif m["recurrence"] == "weekly" and m.get("day_of_week") not in VALID_DAYS:
        errors.append(f"wpis '{m['id']}': recurrence=weekly wymaga 'day_of_week' z {VALID_DAYS}")

    return errors

# --- Logika: czy dane spotkanie ma się odpalić w bieżącej minucie? --------------

def meeting_matches_now(m, now: datetime) -> bool:
    if m.get("enabled") is False:
        return False
    if m["time"] != now.strftime("%H:%M"):
        return False

    rec = m["recurrence"]
    if rec == "daily":
        return True
    if rec == "weekdays":
        return now.weekday() < 5
    if rec == "weekly":
        return WEEKDAY_INDEX_TO_CODE[now.weekday()] == m["day_of_week"]
    if rec == "once":
        return str(m["date"]) == now.strftime("%Y-%m-%d")
    return False

# --- Stan (zapobiega podwójnemu otwarciu tego samego spotkania danego dnia) ----

def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Nie udało się wczytać state.json ({e}) — zaczynam od czystego stanu")
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

# --- Akcje: otwarcie przeglądarki + powiadomienie systemowe --------------------

def open_link(url: str):
    subprocess.run(["xdg-open", url], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def send_notification(title: str, body: str):
    try:
        subprocess.run(["notify-send", title, body], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        log.warning(f"Nie udało się wysłać powiadomienia: {e}")

# --- Subkomenda: check (wołana przez systemd timer co minutę) ------------------

def cmd_check(args):
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    data = load_config()
    state = load_state()

    meetings = data.get("meetings", [])
    if not meetings:
        log.info("Brak zdefiniowanych spotkań w konfiguracji — nic do zrobienia.")
        return

    any_fired = False
    for i, m in enumerate(meetings):
        errors = validate_meeting(m, i)
        if errors:
            for e in errors:
                log.error(f"Pomijam błędny wpis: {e}")
            continue

        if not meeting_matches_now(m, now):
            continue

        if state.get(m["id"]) == today_str:
            continue

        try:
            open_link(m["url"])
            state[m["id"]] = today_str
            any_fired = True
            log.info(f"Otworzono spotkanie '{m['name']}' ({m['id']}) -> {m['url']}")
            send_notification("Spotkanie startuje", m["name"])
        except Exception as e:
            log.error(f"Nie udało się otworzyć linku dla '{m['id']}': {e}")

    if any_fired:
        save_state(state)

# --- Subkomendy CLI --------------------------------------------------------------

def cmd_list(args):
    meetings = load_config().get("meetings", [])
    if not meetings:
        print("Brak zdefiniowanych spotkań.")
        return
    for m in meetings:
        status = "✓" if m.get("enabled", True) else "✗ (wyłączone)"
        rec = m.get("recurrence", "?")
        extra = f" data={m.get('date')}" if rec == "once" else (f" dzień={m.get('day_of_week')}" if rec == "weekly" else "")
        print(f"[{status}] {m.get('id')}: \"{m.get('name')}\" — {m.get('time')} ({rec}{extra})")
        print(f"      {m.get('url')}")


def cmd_add(args):
    data = load_config()
    meetings = data.setdefault("meetings", [])

    meeting_id = args.id or str(uuid.uuid4())[:8]
    if any(m["id"] == meeting_id for m in meetings):
        print(f"Błąd: wpis o id '{meeting_id}' już istnieje.", file=sys.stderr)
        sys.exit(1)

    new_meeting = {
        "id": meeting_id, "name": args.name, "url": args.url,
        "time": args.time, "recurrence": args.recurrence, "enabled": True,
    }
    if args.recurrence == "once":
        if not args.date:
            print("Błąd: recurrence=once wymaga --date YYYY-MM-DD", file=sys.stderr); sys.exit(1)
        new_meeting["date"] = args.date
    if args.recurrence == "weekly":
        if not args.day:
            print("Błąd: recurrence=weekly wymaga --day (mon/tue/.../sun)", file=sys.stderr); sys.exit(1)
        new_meeting["day_of_week"] = args.day

    errors = validate_meeting(new_meeting, len(meetings))
    if errors:
        for e in errors:
            print(f"Błąd walidacji: {e}", file=sys.stderr)
        sys.exit(1)

    meetings.append(new_meeting)
    save_config(data)
    print(f"Dodano spotkanie '{meeting_id}'.")


def cmd_remove(args):
    data = load_config()
    meetings = data.get("meetings", [])
    new_meetings = [m for m in meetings if m["id"] != args.id]
    if len(new_meetings) == len(meetings):
        print(f"Nie znaleziono wpisu o id '{args.id}'.", file=sys.stderr); sys.exit(1)
    data["meetings"] = new_meetings
    save_config(data)
    print(f"Usunięto '{args.id}'.")


def cmd_set_enabled(args, enabled: bool):
    data = load_config()
    for m in data.get("meetings", []):
        if m["id"] == args.id:
            m["enabled"] = enabled
            save_config(data)
            print(f"{'Włączono' if enabled else 'Wyłączono'} '{args.id}'.")
            return
    print(f"Nie znaleziono wpisu o id '{args.id}'.", file=sys.stderr)
    sys.exit(1)


def cmd_test(args):
    for m in load_config().get("meetings", []):
        if m["id"] == args.id:
            print(f"Testowo otwieram: {m['url']}")
            open_link(m["url"])
            return
    print(f"Nie znaleziono wpisu o id '{args.id}'.", file=sys.stderr)
    sys.exit(1)

# --- Parser argumentów CLI --------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(prog="meet", description="Automat do otwierania linków Google Meet.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Sprawdź, czy jakieś spotkanie ma się teraz odpalić (używane przez timer)")
    sub.add_parser("list", help="Wyświetl listę skonfigurowanych spotkań")

    p_add = sub.add_parser("add", help="Dodaj nowe spotkanie")
    p_add.add_argument("--id", help="Unikalny identyfikator (opcjonalnie, generowany automatycznie)")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--url", required=True)
    p_add.add_argument("--time", required=True, help="Format HH:MM")
    p_add.add_argument("--recurrence", required=True, choices=sorted(VALID_RECURRENCE))
    p_add.add_argument("--date", help="Wymagane dla recurrence=once, YYYY-MM-DD")
    p_add.add_argument("--day", choices=sorted(VALID_DAYS), help="Wymagane dla recurrence=weekly")

    for name, help_txt in [("remove", "Usuń spotkanie po id"), ("enable", "Włącz po id"),
                            ("disable", "Wyłącz po id (zostaje w configu)"), ("test", "Otwórz link natychmiast (test)")]:
        sp = sub.add_parser(name, help=help_txt)
        sp.add_argument("id")

    return p


def main():
    args = build_parser().parse_args()
    {
        "check": cmd_check, "list": cmd_list, "add": cmd_add, "remove": cmd_remove,
        "enable": lambda a: cmd_set_enabled(a, True),
        "disable": lambda a: cmd_set_enabled(a, False),
        "test": cmd_test,
    }[args.command](args)


if __name__ == "__main__":
    main()
