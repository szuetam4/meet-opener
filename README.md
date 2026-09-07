# meet-opener

Lokalny, samodzielny automat, który o zdefiniowanej godzinie otwiera link
do spotkania Google Meet w domyślnej przeglądarce. Działa w tle jako
usługa systemd (poziom użytkownika), bez ingerencji w system poza jednym
katalogiem jednostek systemd i opcjonalnym symlinkiem w PATH.

## Funkcje

- Lista spotkań definiowana w jednym pliku YAML (`meetings.yaml`).
- Powtarzalność: jednorazowo, codziennie, w dni robocze, albo w konkretny
  dzień tygodnia o stałej godzinie.
- Automatyczne otwarcie linku w domyślnej przeglądarce (`xdg-open`).
- Powiadomienie systemowe (`notify-send`) w momencie startu spotkania.
- Logowanie do pliku i do `journalctl --user`.
- Zarządzanie spotkaniami przez CLI (`meet add/remove/enable/disable/list/test`)
  albo ręczną edycję pliku YAML.
- Ochrona przed podwójnym otwarciem tego samego spotkania tego samego dnia.
- Walidacja wpisów — błędny wpis w konfiguracji jest logowany i pomijany,
  reszta spotkań działa normalnie.
- Wszystkie pliki aplikacji (kod, config, logi, stan) w jednym folderze —
  łatwa instalacja i deinstalacja.

## Wymagania

- Linux z systemd (testowane na CachyOS).
- Python 3.9+
- Pakiety: `python-yaml`, `libnotify` (dla `notify-send`), `xdg-utils` (dla `xdg-open`).
- Domyślna przeglądarka ustawiona w systemie (np. Zen Browser) — `xdg-open`
  korzysta właśnie z niej.
- Komputer musi być włączony i nieuśpiony o zaplanowanych godzinach —
  aplikacja nie budzi maszyny ze snu.

Instalacja zależności (Arch/CachyOS):
```bash
sudo pacman -S python python-yaml libnotify xdg-utils
```

## Instalacja

```bash
git clone <adres-repo> meet-opener   # albo po prostu skopiuj folder projektu
cd meet-opener
chmod +x install.sh uninstall.sh
./install.sh
```

`install.sh`:
1. sprawdza, czy wymagane narzędzia są zainstalowane,
2. tworzy `meetings.yaml` na bazie `meetings.example.yaml` (jeśli jeszcze nie istnieje),
3. instaluje jednostki systemd (`~/.config/systemd/user/meet-opener.service`
   i `.timer`) wskazujące na ten konkretny folder,
4. tworzy symlink `meet` w `~/.local/bin`, żeby CLI było dostępne z dowolnego miejsca,
5. włącza i uruchamia timer.

## Weryfikacja instalacji

```bash
systemctl --user list-timers | grep meet-opener   # timer aktywny?
meet list                                          # Twoje spotkania
meet test <id>                                     # natychmiastowy test otwarcia
journalctl --user -u meet-opener.service -f        # logi na żywo
```

## Konfiguracja spotkań (`meetings.yaml`)

```yaml
meetings:
  - id: standup
    name: "Codzienny standup zespołu"
    url: "https://meet.google.com/abc-defg-hij"
    time: "09:00"
    recurrence: weekdays
    enabled: true

  - id: retro
    name: "Retrospektywa sprintu"
    url: "https://meet.google.com/xyz-uvwx-rst"
    time: "15:30"
    recurrence: weekly
    day_of_week: fri
    enabled: true

  - id: kickoff-projektu-x
    name: "Kickoff projektu X"
    url: "https://meet.google.com/qqq-rrrr-sss"
    time: "11:00"
    recurrence: once
    date: "2026-09-10"
    enabled: true
```

### Pola

| Pole | Wymagane | Opis |
|---|---|---|
| `id` | zawsze | unikalny identyfikator, bez spacji |
| `name` | zawsze | nazwa widoczna w logach i powiadomieniu |
| `url` | zawsze | link do spotkania |
| `time` | zawsze | godzina `HH:MM`, 24h |
| `recurrence` | zawsze | `once` \| `daily` \| `weekdays` \| `weekly` |
| `date` | dla `once` | data `YYYY-MM-DD` |
| `day_of_week` | dla `weekly` | `mon`\|`tue`\|`wed`\|`thu`\|`fri`\|`sat`\|`sun` |
| `enabled` | opcjonalne | `true`/`false`, domyślnie `true` |

Plik można edytować ręcznie w dowolnym edytorze — zmiany są odczytywane
przy każdym uruchomieniu sprawdzenia (co minutę), bez potrzeby restartu
usługi.

## Zarządzanie przez CLI

```bash
meet list                                                          # pokaż wszystkie spotkania
meet add --name "Nazwa" --url "https://meet.google.com/xxx" \
         --time 10:00 --recurrence daily                           # dodaj spotkanie codzienne
meet add --name "Nazwa" --url "..." --time 10:00 \
         --recurrence once --date 2026-10-01                       # dodaj jednorazowe
meet add --name "Nazwa" --url "..." --time 10:00 \
         --recurrence weekly --day mon                             # dodaj cotygodniowe
meet disable <id>                                                  # wyłącz bez usuwania
meet enable <id>                                                   # włącz z powrotem
meet remove <id>                                                   # usuń na stałe
meet test <id>                                                     # otwórz link natychmiast (test)
```

## Logi i diagnostyka

```bash
tail -f data/meet-opener.log                       # log pliku (relatywny do folderu projektu)
journalctl --user -u meet-opener.service -f         # log przez systemd
systemctl --user status meet-opener.timer           # status timera
```

Błędne wpisy w `meetings.yaml` (np. zły format daty, brak wymaganego pola)
są logowane jako błąd i pomijane — reszta konfiguracji działa dalej
normalnie, aplikacja się nie zatrzymuje.

## Wayland: zmienne środowiskowe (jeśli otwieranie linku nie działa)

Jeśli `xdg-open` / `notify-send` nie działają z poziomu usługi systemd
(błąd typu "cannot open display"), dodaj w
`~/.config/systemd/user/meet-opener.service` w sekcji `[Service]`:
```ini
Environment=WAYLAND_DISPLAY=wayland-0
Environment=XDG_RUNTIME_DIR=/run/user/1000
```
Wartości sprawdzisz poleceniami `echo $WAYLAND_DISPLAY` i
`echo $XDG_RUNTIME_DIR` w aktywnej sesji graficznej. Na większości
nowoczesnych środowisk (KDE Plasma, GNOME, Hyprland+UWSM) nie jest to
potrzebne — systemd user importuje te zmienne automatycznie.

## Deinstalacja

```bash
cd meet-opener
./uninstall.sh
```

Usuwa jednostki systemd i symlink CLI. Folder projektu (kod, config,
logi) pozostaje nietknięty. Aby usunąć całkowicie:
```bash
rm -rf ~/apps/meet-opener   # dostosuj ścieżkę do swojej lokalizacji
```

## Co aplikacja zmienia w systemie

| Element | Lokalizacja | Uwagi |
|---|---|---|
| Kod, config, logi, stan | folder projektu (dowolna lokalizacja) | jedno miejsce, przenośne |
| Jednostki systemd | `~/.config/systemd/user/` | wymóg systemd, poziom użytkownika, bez `sudo` |
| Symlink `meet` | `~/.local/bin/meet` | opcjonalny, usuwany przez `uninstall.sh` |

Żadnych wpisów w systemowym crontabie, żadnych plików poza katalogiem
domowym, żadnej modyfikacji uprawnień systemowych.

## Ograniczenia

- Nie budzi komputera ze snu/hibernacji — wymaga, by maszyna była włączona
  o zaplanowanej godzinie.
- Jeśli dwa spotkania mają identyczną godzinę startu, oba linki zostaną
  otwarte (osobne karty).
- Strefa czasowa brana jest z ustawień systemowych.
