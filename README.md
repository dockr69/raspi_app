# Audio Konfigurator

Ein webbasiertes Konfigurationssystem fuer **Radxa ROCK 3A**, **Raspberry Pi 3B/4** und andere ARM-Linux-Boards mit 40-Pin-GPIO-Header. Headless-Betrieb ohne Display — Flask Web-UI auf Port 80, Audio-Management, GPIO-Tasterbelegung und HTTP-Trigger.

![Platform](https://img.shields.io/badge/Platform-Radxa%20%7C%20Raspberry%20Pi%20%7C%20generisch-orange)
![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-2.3+-lightgrey?logo=flask)
![License](https://img.shields.io/badge/License-Private-red)

---

## Uebersicht

Der **Audio Konfigurator** verwandelt einen Radxa ROCK 3A, Raspberry Pi 3B/4 oder kompatiblen ARM-Linux-Einplatinencomputer in ein vollstaendiges Audiowiedergabe-System. Headless-Betrieb auf einem Minimal-Image — kein Display, kein Kiosk, kein Desktop noetig.

- **Automatische Board-Erkennung**: Radxa ROCK 3A, Raspberry Pi 3B, RPi 4, generisch
- **USB-Soundkarten**: Werden automatisch erkannt (PulseAudio System-Modus)
- **Zwei Betriebsmodi**: **Online** (HTTP + GPIO) oder **Offline** (nur GPIO)
- **Immer erreichbar** unter der festen Service-IP `10.0.0.10`
- **Audiodateien** per Drag-and-Drop hochladen — automatische Konvertierung via ffmpeg
- **Wiedergabe** per HTTP-Request oder physischem GPIO-Taster
- **Headless**: Kein Display, kein Chromium, kein LightDM — nur Webserver

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
| **Andere ARM-Linux** | — | 40-Pin | — | ja | Generischer Modus |

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
| **Board-Erkennung** | Automatisch: RPi 3B/4, Radxa ROCK 3A, generisch |
| **USB Audio** | USB-Soundkarten automatisch erkannt (PulseAudio System-Modus) |
| **Online/Offline-Modus** | Online: HTTP + GPIO · Offline: nur GPIO |
| **Einrichtungsassistent** | 5-Schritte-Wizard beim ersten Start |
| **Settings-Seite** | Netzwerk, Audio, GPIO, Modus jederzeit aenderbar |
| **Netzwerk** | Statische IP + permanente Service-IP `10.0.0.10` (kein DHCP) |
| **Audio** | Getrennte Lautstaerke Ein/Ausgang, Combo Jack Profil |
| **Sound-Liste** | Inline-Dropdowns: HTTP oder GPIO-Pin pro Sound, Suchfeld |
| **Datei-Upload** | Beliebige Audioformate — ffmpeg konvertiert parallel |
| **HTTP-Trigger** | Sound per GET-Request abspielen |
| **GPIO-Taster** | Physische Taster auf GPIO-Pins mit Sounds verknuepfen |
| **Sound-Vorschau** | Im Browser abspielen (Streaming) |
| **Health Check** | CPU-Temperatur, RAM, Disk, Uptime |
| **Zeitgesteuerte Trigger** | Sound zu bestimmter Uhrzeit abspielen |
| **Backup & Restore** | Config + Sounds als ZIP exportieren/importieren |
| **Reboot/Restart** | SBC oder Service ueber Web-UI neu starten |
| **Terminal** | Eingebettetes Web-Terminal mit Command-Blacklist |
| **mDNS** | `textspeicher.local` |
| **SSH** | Vorkonfiguriert |
| **Login** | Session-basiert, Passwort aenderbar |

---

## Installation

```bash
git clone https://github.com/dockr69/radxa_app.git
cd radxa_app
sudo bash install.sh
```

Das Script erkennt automatisch das Board:

```
  +----------------------------------------------+
  |      Audio Konfigurator Setup (Headless)      |
  +----------------------------------------------+
  |  Board:    Raspberry Pi 4                     |
  |  GPIO:     /dev/gpiochip0                     |
  |  User:     pi                                 |
  +----------------------------------------------+
```

| Schritt | Beschreibung |
|---|---|
| Board-Erkennung | RPi 3B/4, Radxa ROCK 3A, oder generisch |
| Systempakete | ffmpeg, mpg123, pulseaudio, openssh, avahi |
| PulseAudio | System-Modus (damit root Soundkarten sieht) |
| App-Deployment | Kopiert App nach `/opt/radxa_audio`, schreibt Board-Info |
| SSH | Aktiviert Passwort-Authentifizierung |
| Hostname | `textspeicher` + mDNS |
| Netzwerk | Service-IP `10.0.0.10/24` (kein DHCP) |
| Boot-Config | RPi: `dtparam=audio=on` |
| systemd | Web-Service, GPIO-Daemon, PulseAudio System-Modus |

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

> **Login:** OS-Benutzername + OS-Passwort (z.B. `pi` / das gesetzte Passwort). Passwort kann ueber den Schluessel-Button im Web-UI geaendert werden.

---

## Einrichtungsassistent

Beim **ersten** Aufruf der Web-UI startet der Wizard:

```
Schritt 1 – Modus:     Online oder Offline waehlen
Schritt 2 – Netzwerk:  Statische IP, Gateway, DNS
Schritt 3 – Audio:     PulseAudio-Quelle, Lautstaerke, Combo Jack Profil
Schritt 4 – Sounds:    MP3s hochladen, Trigger-Typ pro Sound (HTTP/GPIO)
Schritt 5 – GPIO:      Taster auf GPIO-Pins zuweisen
```

---

## Status-Dashboard

Nach dem Setup die Hauptansicht:

- **IP-Karten**: Statische IP und Service-IP
- **Board-Info + USB-Audio-Badge**
- **System-Status**: CPU-Temperatur, RAM, Disk, Uptime
- **Sound-Liste**: Suche, Inline-Trigger-Dropdown (HTTP/GPIO Pin), Repeat, Vorschau
- **Upload**: Drag-and-Drop, parallele ffmpeg-Konvertierung
- **Lautstaerke**: Ausgang + Eingang regelbar
- **Zeitgesteuerte Trigger**: Sound zu bestimmter Uhrzeit
- **Backup & Restore**: ZIP-Export/Import
- **System**: Service-Restart, SBC-Reboot

---

## API-Referenz

### System
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/status` | Systemstatus, Board-Info, USB-Audio, GPIO-Pins |
| GET | `/api/health` | CPU-Temp, RAM, Disk, Uptime, Service-Status |
| GET/POST | `/api/mode` | Betriebsmodus |
| POST | `/api/system/reboot` | SBC neu starten |
| POST | `/api/system/restart-service` | Web-Service neu starten |

### Netzwerk
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/network/interfaces` | Netzwerk-Interfaces |
| POST | `/api/network/validate` | IP validieren |
| POST | `/api/network/apply` | Statische IP anwenden |
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
| POST | `/api/audio/preview` | 5s Line-In Aufnahme (WAV) |

### Sounds & GPIO
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/mp3s` | Alle MP3s mit Trigger-Config |
| GET | `/api/mp3s/stream/<name>` | Sound im Browser abspielen |
| POST | `/api/upload` | Dateien hochladen & konvertieren |
| POST | `/api/mp3s/play` | MP3 auf Geraet abspielen |
| POST | `/api/mp3s/delete` | MP3 loeschen |
| POST | `/api/mp3s/rename` | MP3 umbenennen |
| POST | `/api/mp3s/trigger` | Trigger-Typ setzen (HTTP/GPIO) |
| POST | `/api/gpio/save` | GPIO-Zuweisungen speichern |

### Zeitgesteuerte Trigger
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/schedules` | Alle geplanten Trigger |
| POST | `/api/schedules` | Trigger anlegen/aendern |
| POST | `/api/schedules/delete` | Trigger loeschen |

### Backup
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/backup/export` | Config + Sounds als ZIP |
| POST | `/api/backup/import` | ZIP importieren |

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
| `pulseaudio-system` | PulseAudio im System-Modus |

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
  +-- config.json       # Hauptkonfiguration (Netzwerk, Audio, Sounds, Trigger, Schedules)
  +-- board.json        # Board-Erkennung (Board, GPIO-Chip, Pins, User)
  +-- .setup_done       # Setup-Marker
  +-- .secret_key       # Session-Key (600)
  +-- sounds/           # MP3-Dateien
```

### Sicherheit

- Session-Authentifizierung (alle Routes ausser Trigger)
- Passwort gehasht (`werkzeug.security`)
- `shlex.quote()` fuer alle Shell-Aufrufe
- Pfad-Traversal-Schutz bei Dateioperationen
- Terminal-Command-Blacklist (rm -rf /, mkfs, dd, etc.)
- Interface- und IP-Validierung
- Thread-Mutex fuer Audiowiedergabe

### PulseAudio System-Modus

Da der Webserver als `root` laeuft, wird PulseAudio im System-Modus gestartet (nicht als User-Session). So kann `pactl` die Soundkarten sehen:

- `pulseaudio-system.service` startet PulseAudio mit `--system`
- `PULSE_SERVER=unix:/var/run/pulse/native` wird in den systemd-Services gesetzt
- User-Session PulseAudio wird deaktiviert

---

## Projektstruktur

```
radxa_app/
+-- app.py                  # Flask-Backend (API, Audio, GPIO, Board-Erkennung)
+-- install.sh              # Install-Script (Board-Erkennung, Pakete, Services)
+-- templates/
|   +-- index.html          # Single-Page-App (Wizard + Dashboard + Settings)
|   +-- login.html          # Login-Seite
+-- sounds/                 # Lokales Sounds-Verzeichnis
+-- README.md
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
| `pulseaudio` + `pulseaudio-utils` | Audio-System (System-Modus, USB-Soundkarten) |
| `openssh-server` | SSH-Zugriff |
| `avahi-daemon` + `avahi-utils` | mDNS (`textspeicher.local`) |
| `python3-gpiod` | GPIO (libgpiod, kein RPi.GPIO) |

---

Entwickelt von **Fabian**.
