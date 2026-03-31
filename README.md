# Audio Konfigurator

Ein webbasiertes Konfigurationssystem fuer **Radxa ROCK 3A**, **Raspberry Pi 3B/4** und andere ARM-Linux-Boards mit 40-Pin-GPIO-Header. Audio-Management, Netzwerkkonfiguration, Datei-Uploads und GPIO-Tasterbelegung ueber eine moderne Browser-Oberflaeche — inklusive automatischem Kiosk-Modus beim Booten.

![Platform](https://img.shields.io/badge/Platform-Radxa%20%7C%20Raspberry%20Pi%20%7C%20generisch-orange)
![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-2.3+-lightgrey?logo=flask)
![License](https://img.shields.io/badge/License-Private-red)

---

## Inhaltsverzeichnis

- [Uebersicht](#uebersicht)
- [Unterstuetzte Hardware](#unterstuetzte-hardware)
- [Features](#features)
- [Installation](#installation)
- [Zugang nach der Installation](#zugang-nach-der-installation)
- [Einrichtungsassistent](#einrichtungsassistent)
- [Settings-Seite](#settings-seite)
- [Funktionen im Detail](#funktionen-im-detail)
  - [Board-Erkennung](#board-erkennung)
  - [USB-Soundkarten](#usb-soundkarten)
  - [Betriebsmodus (Online / Offline)](#betriebsmodus-online--offline)
  - [Netzwerkkonfiguration](#netzwerkkonfiguration)
  - [Audio-Konfiguration](#audio-konfiguration)
  - [Sound-Bibliothek & Uploads](#sound-bibliothek--uploads)
  - [HTTP-Trigger](#http-trigger)
  - [GPIO-Taster](#gpio-taster)
- [Status-Dashboard](#status-dashboard)
- [API-Referenz](#api-referenz)
- [Systemdienste](#systemdienste)
- [Technische Details](#technische-details)
- [Projektstruktur](#projektstruktur)
- [Abhaengigkeiten](#abhaengigkeiten)

---

## Uebersicht

Der **Audio Konfigurator** verwandelt einen Radxa ROCK 3A, Raspberry Pi 3B/4 oder kompatiblen ARM-Linux-Einplatinencomputer in ein vollstaendiges Audiowiedergabe-System. Das Board wird automatisch erkannt und GPIO, Audio und Boot-Konfiguration entsprechend angepasst.

- **Automatische Board-Erkennung**: Radxa ROCK 3A, Raspberry Pi 3B, RPi 4, generisch
- **USB-Soundkarten**: Werden automatisch erkannt und in PulseAudio eingebunden
- **Zwei Betriebsmodi**: **Online** (HTTP + GPIO) oder **Offline** (nur GPIO)
- **Immer erreichbar** unter der festen Service-IP `10.0.0.10`
- **Audiodateien** per Drag-and-Drop hochladen — automatische Konvertierung via ffmpeg
- **Wiedergabe** per HTTP-Request oder physischem GPIO-Taster
- **Kiosk-Modus**: Chromium startet beim Booten automatisch im Vollbild

---

## Unterstuetzte Hardware

### Boards

| Board | SoC | GPIO | Audio Jack | USB Audio | Status |
|---|---|---|---|---|---|
| **Raspberry Pi 4** | BCM2711 | 40-Pin | 3,5 mm | ja | Unterstuetzt |
| **Raspberry Pi 3B** | BCM2837 | 40-Pin | 3,5 mm | ja | Unterstuetzt |
| **Radxa ROCK 3A** | RK3568 | 40-Pin | 3,5 mm TRRS | ja | Referenzboard |
| **Radxa ROCK 3C** | RK3566 | 40-Pin | 3,5 mm TRRS | ja | Kompatibel |
| **Radxa ROCK 4C+** | RK3399-T | 40-Pin | 3,5 mm TRRS | ja | Kompatibel |
| **Radxa ROCK 5B** | RK3588 | 40-Pin | 3,5 mm | ja | Kompatibel |
| **Andere ARM-Linux** | — | 40-Pin | — | ja | Generischer Modus |

> **GPIO-Pins** `4, 17, 18, 22, 23, 24, 25, 27` sind auf allen 40-Pin-Boards identisch (BCM-Nummerierung).

### Audio-Geraete

| Typ | Unterstuetzung |
|---|---|
| **Onboard 3,5 mm Jack** | Automatisch erkannt |
| **USB-Soundkarte** | Automatisch erkannt via PulseAudio |
| **USB-DAC** | Automatisch erkannt |
| **HDMI Audio** | Automatisch erkannt |
| **Combo Jack (TRRS)** | Headset-Profil in Audio-Settings waehlbar |

---

## Features

| Feature | Beschreibung |
|---|---|
| **Board-Erkennung** | Automatisch: RPi 3B/4, Radxa ROCK 3A, generisch — GPIO-Chip, User, Boot-Config werden angepasst |
| **USB Audio** | USB-Soundkarten werden automatisch erkannt und im Dashboard angezeigt |
| **Online/Offline-Modus** | Online: HTTP + GPIO · Offline: nur GPIO, kein Router noetig |
| **Einrichtungsassistent** | 5-Schritte-Wizard beim ersten Start |
| **Settings-Seite** | Nach Setup: Netzwerk, Audio, GPIO, Modus jederzeit aenderbar |
| **Netzwerk** | DHCP aktiv + optionale statische IP + permanente Service-IP `10.0.0.10` |
| **DHCP-Steuerung** | Checkbox: DHCP aktiv lassen oder nach Setup abschalten |
| **Audio** | Getrennte Lautstaerkeregler fuer Ausgang und Eingang, Combo Jack/Headset-Profil |
| **Datei-Upload** | Beliebige Audioformate — ffmpeg konvertiert parallel (bis zu 4 gleichzeitig) |
| **HTTP-Trigger** | Sound per GET-Request abspielen |
| **GPIO-Taster** | Physische Taster auf GPIO-Pins mit Sounds verknuepfen |
| **Wiederholungen** | Pro Sound 1-10x einstellbar |
| **GPIO-Daemon** | Automatisch generiert, unterstuetzt gpiod 1.x und 2.x |
| **Status-Dashboard** | IPs, Sounds, Board-Info, USB-Audio-Status, Trigger-URLs |
| **Kiosk-Modus** | Chromium Vollbild, Screensaver/Sleep deaktiviert |
| **mDNS** | `textspeicher.local` |
| **SSH** | Vorkonfiguriert |
| **Login** | Session-basiert, Passwort aenderbar |
| **Web-Terminal** | Eingebettetes Terminal im Browser |

---

## Installation

```bash
git clone https://github.com/dockr69/radxa_app.git
cd radxa_app
sudo bash install.sh
```

Das Script erkennt automatisch das Board und passt alles an:

```
  ╔══════════════════════════════════════════════╗
  ║      Audio Konfigurator Setup                ║
  ╠══════════════════════════════════════════════╣
  ║  Board:    Raspberry Pi 4                    ║
  ║  GPIO:     /dev/gpiochip0                    ║
  ║  User:     pi                                ║
  ╚══════════════════════════════════════════════╝
```

| Schritt | Beschreibung |
|---|---|
| Board-Erkennung | Erkennt RPi 3B/4, Radxa ROCK 3A, oder generisches Board |
| Systempakete | ffmpeg, mpg123, pulseaudio, openssh, avahi, chromium, openbox, lightdm |
| App-Deployment | Kopiert App nach `/opt/radxa_audio`, schreibt Board-Info |
| SSH | Aktiviert Passwort-Authentifizierung |
| Hostname | `textspeicher` + mDNS |
| Netzwerk | Service-IP `10.0.0.10/24` (DHCP bleibt unangetastet) |
| Boot-Config | RPi: `/boot/firmware/config.txt`, Armbian: `/boot/armbianEnv.txt` |
| Idle-Schutz | Screensaver, DPMS, Sleep, Suspend deaktiviert |
| systemd | Web-Service, GPIO-Daemon, Kiosk-Browser |

```bash
sudo reboot
```

---

## Zugang nach der Installation

| Zugang | Adresse |
|---|---|
| **Web-UI (Service-IP)** | `http://10.0.0.10` |
| **Web-UI (mDNS)** | `http://textspeicher.local` |
| **SSH** | `ssh pi@10.0.0.10` |

> **Standard-Login:** `pi` / `Gerade24632@` — Passwort aenderbar ueber den Schluessel-Button.

---

## Einrichtungsassistent

Beim **ersten** Aufruf der Web-UI startet der Wizard:

```
Schritt 1 – Modus:     Online oder Offline waehlen
Schritt 2 – Netzwerk:  Statische IP, Gateway, DNS, DHCP-Checkbox
Schritt 3 – Audio:     PulseAudio-Quelle, Lautstaerke, Combo Jack Profil
Schritt 4 – Sounds:    MP3s hochladen, Trigger-Typ pro Sound (HTTP/GPIO)
Schritt 5 – GPIO:      Taster auf GPIO-Pins zuweisen
```

> Im Offline-Modus wird der Netzwerk-Schritt uebersprungen.

---

## Settings-Seite

Nach dem Wizard ist die **Settings-Seite** ueber das Zahnrad-Symbol erreichbar (kein Wizard mehr). Vier Tabs:

| Tab | Inhalt |
|---|---|
| **Netzwerk** | Interface, statische IP, Gateway, DNS, DHCP-Checkbox |
| **Audio** | Quelle, Lautstaerke (Ein/Ausgang), Combo Jack/Headset-Profil |
| **GPIO** | Pin-Mapping (nur Sounds mit GPIO-Trigger) |
| **Modus** | Online/Offline umschalten |

---

## Funktionen im Detail

### Board-Erkennung

Das Install-Script und die App erkennen das Board automatisch:

| Erkennungsmethode | Quelle |
|---|---|
| `/proc/device-tree/model` | Primaer |
| `/sys/firmware/devicetree/base/model` | Fallback |
| Keyword-Matching | `raspberry pi 4`, `rock 3`, etc. |

Erkannte Werte werden in `/etc/radxa_audio/board.json` gespeichert:

```json
{
  "board": "rpi4",
  "board_name": "Raspberry Pi 4",
  "gpiochip": "/dev/gpiochip0",
  "gpio_pins": [4, 17, 18, 22, 23, 24, 25, 27],
  "default_user": "pi"
}
```

Board-spezifische Anpassungen:
- **GPIO-Chip**: `/dev/gpiochip0` (Standard), `/dev/gpiochip4` (RPi 5)
- **Default-User**: `pi` (RPi), `rock` (Radxa), oder erster User >= UID 1000
- **Boot-Config**: `/boot/firmware/config.txt` (RPi Bookworm), `/boot/armbianEnv.txt` (Armbian)
- **Chromium-Paket**: `chromium-browser` (RPi OS), `chromium` (Armbian)
- **Audio-Overlay**: `dtparam=audio=on` wird auf RPi automatisch gesetzt

### USB-Soundkarten

USB-Soundkarten werden automatisch erkannt:

- PulseAudio listet alle angeschlossenen Audio-Geraete
- Im Audio-Setup (Wizard oder Settings) erscheinen USB-Karten als Quellen
- Im Dashboard wird ein USB-Audio-Badge angezeigt wenn erkannt
- Kein manuelles Konfigurieren noetig — einstecken genuegt

### Betriebsmodus (Online / Offline)

| Modus | Trigger | Netzwerk | Einsatz |
|---|---|---|---|
| **Online** | HTTP + GPIO | Statische IP + Service-IP | Geraet im Netzwerk |
| **Offline** | Nur GPIO | Nur Service-IP `10.0.0.10` | Standalone, kein Router |

### Netzwerkkonfiguration

- **DHCP ist standardmaessig aktiv** — Geraet bekommt automatisch eine IP
- **DHCP-Checkbox**: Nach Wizard kann DHCP aktiv bleiben oder abgeschaltet werden
- Optionale statische IP als Alias parallel zu DHCP
- Service-IP `10.0.0.10` ist fest und immer erreichbar
- Validierung von IP, Gateway und DNS im Browser

### Audio-Konfiguration

- Erkennt alle PulseAudio/PipeWire-Quellen automatisch (inkl. USB)
- Getrennte Lautstaerkeregler fuer Ausgang und Eingang (0-100%)
- Combo Jack: Soundkarte + Profil waehlbar (Headset-Modus)
- Waehrend Wiedergabe wird Eingang automatisch stummgeschaltet

### Sound-Bibliothek & Uploads

- Alle gaengigen Audioformate — ffmpeg konvertiert zu MP3 (44.1 kHz, Mono, 128k)
- Drag-and-Drop mit Fortschrittsanzeige
- Bis zu 4 parallele ffmpeg-Konvertierungen
- Trigger-Typ pro Sound: HTTP, GPIO oder gesperrt
- Wiederholungen pro Sound: 1-10x

### HTTP-Trigger

```
GET http://10.0.0.10/cgi-bin/index.cgi?webif-pass=1&spotrequest=datei.mp3
GET http://10.0.0.10/play/datei.mp3
```

### GPIO-Taster

- **Pins:** `4, 17, 18, 22, 23, 24, 25, 27` (BCM, identisch auf RPi und Radxa)
- Pull-Up intern, Falling Edge, 200ms Debounce
- Nutzt `python3-gpiod` (libgpiod) — kein RPi.GPIO noetig
- Unterstuetzt gpiod 1.x und 2.x automatisch
- GPIO-Chip wird automatisch erkannt

---

## Status-Dashboard

- **Board-Info**: Erkanntes Board wird angezeigt
- **USB-Audio-Badge**: Zeigt an ob USB-Soundkarte erkannt
- **IP-Karten**: Statische IP und Service-IP
- **Status-Tiles**: Sounds, SSH, mDNS, Trigger-Port
- **Sound-Bibliothek**: Trigger-URLs, GPIO-Pins, Play/Rename/Delete
- **Upload-Bereich**: Direkt im Dashboard
- **Lautstaerke**: Ausgang + Eingang regelbar
- **Settings**: Zahnrad-Button oeffnet Settings-Seite (nicht den Wizard)

---

## API-Referenz

### Authentifizierung
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET/POST | `/login` | Login-Seite |
| GET | `/logout` | Session beenden |
| POST | `/api/auth/change-password` | Passwort aendern |
| POST | `/api/terminal/exec` | Shell-Befehl ausfuehren |

### System
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/status` | Systemstatus, Board-Info, USB-Audio, GPIO-Pins |
| GET/POST | `/api/mode` | Betriebsmodus |
| POST | `/api/setup/finish` | Setup abschliessen |
| POST | `/api/setup/reset` | Setup zuruecksetzen |

### Netzwerk
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/network/interfaces` | Netzwerk-Interfaces |
| POST | `/api/network/validate` | IP validieren |
| POST | `/api/network/apply` | IP anwenden (mit `keep_dhcp` Option) |
| POST | `/api/network/ping` | Verbindungstest |

### Audio
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/audio/sources` | PulseAudio-Quellen (inkl. USB) |
| GET | `/api/audio/cards` | Soundkarten mit Profilen |
| POST | `/api/audio/card-profile` | Kartenprofil setzen |
| POST | `/api/audio/save` | Audio-Konfiguration speichern |
| POST | `/api/audio/mute` | Mute/Unmute |
| POST | `/api/audio/test` | Test-Audio |

### Dateien & GPIO
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/mp3s` | Alle MP3s mit Trigger-Config |
| POST | `/api/upload` | Dateien hochladen & konvertieren |
| POST | `/api/mp3s/play` | MP3 abspielen |
| POST | `/api/mp3s/delete` | MP3 loeschen |
| POST | `/api/mp3s/rename` | MP3 umbenennen |
| POST | `/api/mp3s/trigger` | Trigger-Typ setzen |
| POST | `/api/gpio/save` | GPIO-Zuweisungen speichern |
| POST | `/api/trigger/config` | Webif-Passwort setzen |

### Wiedergabe (extern)
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/cgi-bin/index.cgi` | Trigger via `?webif-pass=X&spotrequest=Y` |
| GET | `/play/<dateiname>` | Direkter Wiedergabe-Endpunkt |

---

## Systemdienste

| Dienst | Beschreibung |
|---|---|
| `radxa-audio-web` | Flask-Backend auf Port 80 |
| `radxa-audio-gpio` | GPIO-Taster-Daemon |
| `radxa-kiosk` | Chromium-Kiosk-Modus |

```bash
systemctl status radxa-audio-web
journalctl -u radxa-audio-web -f
sudo systemctl restart radxa-audio-web
```

---

## Technische Details

### Konfigurationsdateien

```
/etc/radxa_audio/
  ├── config.json       # Hauptkonfiguration (Netzwerk, Audio, Sounds, Trigger)
  ├── board.json        # Board-Erkennung (Board, GPIO-Chip, Pins, User)
  ├── .setup_done       # Setup-Marker
  ├── .secret_key       # Session-Key (600)
  └── sounds/           # MP3-Dateien
```

### Board-spezifische Anpassungen

| Aspekt | Raspberry Pi | Radxa | Generisch |
|---|---|---|---|
| GPIO-Chip | `/dev/gpiochip0` | `/dev/gpiochip0` | `/dev/gpiochip0` |
| Default-User | `pi` | `rock` | erster User >= UID 1000 |
| Chromium-Paket | `chromium-browser` | `chromium` | beides versucht |
| Boot-Config | `/boot/firmware/config.txt` | `/boot/armbianEnv.txt` | `/boot/cmdline.txt` |
| Audio-Overlay | `dtparam=audio=on` | nicht noetig | — |

### Sicherheit

- Session-Authentifizierung (alle Routes ausser Trigger)
- Passwort gehasht (`werkzeug.security`)
- `shlex.quote()` fuer alle Shell-Aufrufe
- Pfad-Traversal-Schutz bei Dateioperationen
- Interface- und IP-Validierung
- Thread-Mutex fuer Audiowiedergabe

---

## Projektstruktur

```
radxa_app/
├── app.py                  # Flask-Backend (API, Audio, GPIO, Board-Erkennung)
├── install.sh              # Install-Script (Board-Erkennung, Pakete, Services)
├── templates/
│   ├── index.html          # Single-Page-App (Wizard + Dashboard + Settings)
│   └── login.html          # Login-Seite
├── sounds/                 # Lokales Sounds-Verzeichnis
└── README.md
```

---

## Abhaengigkeiten

### Python
```
flask>=2.3
```

### System (automatisch installiert)

| Paket | Verwendung |
|---|---|
| `ffmpeg` | Audio-Konvertierung |
| `mpg123` | MP3-Wiedergabe |
| `pulseaudio` + `pulseaudio-utils` | Audio-System (USB-Soundkarten) |
| `openssh-server` | SSH-Zugriff |
| `avahi-daemon` | mDNS (`textspeicher.local`) |
| `chromium` / `chromium-browser` | Kiosk-Modus |
| `openbox` + `lightdm` | Desktop fuer Kiosk |
| `unclutter` + `xdotool` | Cursor verstecken |
| `python3-gpiod` | GPIO (libgpiod, kein RPi.GPIO) |

---

Entwickelt von **Fabian**.
