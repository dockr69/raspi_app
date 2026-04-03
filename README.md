# raspi_app – Raspberry Pi Audio Konfigurator

Ein vollwertiges, headless Audio-System für Raspberry Pi 3B/4, das als systemd-Service läuft und über eine Web-UI gesteuert wird. Ideal für Audio-Ansagen, Sprachdurchsagen und triggered Audio-Ereignisse.

## Features

### Audio-Funktionen
- **Audio-Passthrough** – Line-In → Line-Out via PulseAudio Loopback (USB-Soundkarte)
- **MP3-Upload & Konverter** – Einzeldateien oder ZIP-Archive (bis 500 MB), automatische Konvertierung zu MP3 via ffmpeg
- **Lautstärkeregelung** – Ein- und Ausgang getrennt einstellbar (0–100%)

### Trigger-Systeme
- **HTTP-Trigger** – Ansagen per GET-Request auslösen (kompatibel mit WiFi-Buttons, Home Assistant, etc.)
- **GPIO-Trigger** – Taster direkt an GPIO-Pins (26-Pin Header, Pins 1–27)
- **Zeitplan-Schedules** – Sounds zu festen Zeiten/Wochentagen automatisch abspielen

### Verwaltung
- **Backup/Restore** – Config + Sounds als ZIP exportieren/importieren
- **USB Plug & Play** – Neue USB-Soundkarte wird automatisch erkannt
- **Git-Integration** – Automatische Updates vom GitHub-Repository
- **Passwort-Schutz** – Login erforderlich für Konfiguration

## Hardware-Anforderungen

| Komponente | Beschreibung |
|------------|------------|
| **Raspberry Pi** | Pi 3B oder Pi 4 (4GB empfohlen) |
| **USB-Soundkarte** | C-Media CM108, Sabrent, Unitek oder ähnlich |
| **Ethernet** | Für Netzwerk-Zugriff (WiFi nicht unterstützt) |
| **GPIO-Taster** | Optional, für Hardware-Trigger |

## Installation

```bash
# Repository klonen
git clone https://github.com/dockr69/raspi_app.git
cd raspi_app

# Installation ausführen
sudo bash install.sh

# System neu starten
sudo reboot
```

### Was das Install-Script macht:

1. **Abhängigkeiten installieren**: Python3, Flask, ffmpeg, pulseaudio, git
2. **PulseAudio konfigurieren**: System-Modus mit USB-Audio-Unterstützung
3. **Netzwerk einrichten**: Statische IP `10.0.0.10` konfigurieren
4. **Services einrichten**: `raspi-audio-web` und `raspi-audio-gpio` als systemd-Services
5. **GPIO-Script generieren**: Automatisches Script für GPIO-Trigger

## Netzwerk-Konfiguration

| Adresse | Zweck |
|---------|-------|
| `10.0.0.10` | **Service-IP** – Web-UI und API |
| `192.168.1.120` | **Statische IP** – Optional konfigurierbar |

Web-UI unter **http://10.0.0.10** aufrufen.

## Schnellstart

### 1. Audio-Upload
- Zum Tab **"Sounds"** navigieren
- MP3-Dateien per Drag&Drop oder Upload-Button hochladen
- Automatische Konvertierung zu MP3 (128kbps, 44.1kHz, Mono)

### 2. Trigger konfigurieren
- Pro Sound Trigger-Typ wählen: **HTTP** oder **GPIO**
- Bei GPIO: Pin auswählen (1–27)
- Repeat-Wert setzen (1–10×)
- Timeout setzen (0–300s) – steuert GPIO-Blockade nach Trigger

### 3. Audio testen
- Play-Button (▶) zum Testen
- Preview-Button (🔊) zum Abspielen ohne Trigger
- Lautstärke in **"Settings"** anpassen

### 4. HTTP-Trigger verwenden

```bash
# Einfacher Sound
curl "http://10.0.0.10/cgi-bin/index.cgi?webif-pass=1&spotrequest=ansage.mp3"

# Mit URL-Encoding
curl "http://10.0.0.10/cgi-bin/index.cgi?webif-pass=1&spotrequest=alarm.mp3"
```

### 5. GPIO-Trigger verwenden

```bash
# Taster zwischen GPIO-Pin und GND anschließen
# Sound wird automatisch abgespielt
```

## Web-UI Übersicht

### Sounds-Tab
- **Sound-Liste**: Alle hochgeladenen MP3s mit Metadaten
- **Trigger-Select**: HTTP oder GPIO (Pin 1–27)
- **Repeat-Select**: 1–10× Abspiel-Wiederholungen
- **Timeout-Select**: 0s, 10s, 30s (Default), 60s, 120s, 300s
- **Grösse**: Dateigrösse in KB
- **Actions**: Umbenennen, Löschen

### Upload-Tab
- Drag&Drop oder Dateiauswahl
- ZIP-Unterstützung (wird entpackt und konvertiert)
- Konvertierungsstatus anzeigen
- Max. 500 MB pro Upload

### Schedules-Tab
- Zeitplan für automatische Abspielung
- Wochentags-Auswahl (Mo–So)
- Zeit im 24h-Format (HH:MM)
- Sound-Auswahl pro Zeitplan

### Settings-Tab
- **Lautstärke**: Input/Output getrennt (0–100%)
- **Passwort ändern**: Login-Passwort aktualisieren
- **GPIO-Status**: Aktuelle GPIO-Pins und Trigger-Status
- **Audio-Status**: PulseAudio-Informationen

### Update-Tab
- Git-Status anzeigen (Branch, Commit)
- Update ausführen (pull origin main + restart)
- Fehler bei Update anzeigen

### Backup-Tab
- Config + Sounds als ZIP exportieren
- ZIP hochladen und importieren
- Config-Reset (Factory Reset)

## API-Endpoints

### Audio-Trigger
```http
GET /cgi-bin/index.cgi?webif-pass=<PASSWORD>&spotrequest=<SOUND>.mp3
GET /play/<SOUND>.mp3
POST /api/mp3s/play-id {"id": 123}
```

### Sound-Verwaltung
```http
GET  /api/mp3s                    # Alle Sounds
POST /api/mp3s/trigger            # Trigger ändern
       {stem, trigger_type, gpio_pin, repeat, timeout}
POST /api/mp3s/rename             # Umbenennen
       {old: "alt.mp3", new: "neu.mp3"}
POST /api/mp3s/play-id            # Abspielen
       {id: 123}
POST /api/mp3s/delete             # Löschen
       {name: "sound.mp3"}
```

### Schedules
```http
GET  /api/schedules               # Alle Schedules
POST /api/schedules               # Neuen Schedule
       {time, day_of_week, sound_name, enabled}
DELETE /api/schedules/<id>         # Löschen
```

### Audio-Steuerung
```http
GET  /api/audio/volume/input      # Input-Lautstärke
GET  /api/audio/volume/output     # Output-Lautstärke
POST /api/audio/volume            # Setzen
       {input: 50, output: 75}
POST /api/audio/loopback/start    # Loopback starten
POST /api/audio/loopback/stop     # Loopback stoppen
```

### GPIO
```http
GET  /api/gpio/status             # GPIO-Status
GET  /api/gpio/list               # Alle GPIO-Pins
```

### Netzwerk
```http
GET  /api/network/status          # Netzwerk-Status
GET  /api/network/commit          # Git-Commit-Info
POST /api/network/update          # Git-Pull ausführen
```

### Backup
```http
GET  /api/backup/download         # Config+Sounds als ZIP
POST /api/backup/upload           # ZIP hochladen und importieren
POST /api/backup/factory-reset    # Factory Reset
```

### Login
```http
POST /api/login       {username: "pi", password: "..."}
POST /api/logout
```

## GPIO-Pin-Mapping

| Pin | Funktion |
|-----|----------|
| 1   | 3.3V Power |
| 2   | 5V Power |
| 3   | GPIO2 (SDA) |
| 4   | 5V Power |
| 5   | GPIO3 (SCL) |
| 6   | GND |
| 7   | GPIO4 |
| 8   | GPIO14 (TXD) |
| 9   | GPIO15 (RXD) |
| 10  | GPIO17 |
| 11  | GPIO18 |
| 12  | GPIO27 |
| 13  | GPIO22 |
| 14  | GND |
| 15  | GPIO23 |
| 16  | GPIO23 |
| 17  | 3.3V Power |
| 18  | GPIO24 |
| 19  | GPIO10 (MOSI) |
| 20  | GND |
| 21  | GPIO9 (MISO) |
| 22  | GPIO25 |
| 23  | GPIO11 (SCLK) |
| 24  | GPIO8 (CE0) |
| 25  | GND |
| 26  | GPIO7 (CE1) |
| 27  | GPIO0 |

**Wichtig**: Taster zwischen GPIO-Pin und GND anschließen. Pull-Up resistor ist intern aktiviert.

## Timeout-Erklärung

Das **Timeout-Feld** steuert, wie lange ein GPIO-Pin nach einem Trigger blockiert wird:

| Timeout | Verhalten |
|---------|-----------|
| **0s**  | Kein Timeout – Pin bleibt unbeschränkt blockiert |
| **10s** | 10 Sekunden Blockade nach Trigger |
| **30s** | **Standard** – 30 Sekunden Blockade |
| **60s** | 60 Sekunden Blockade |
| **120s** | 2 Minuten Blockade |
| **300s** | 5 Minuten Blockade |

**Warum?** Verhindert Mehrfachauslösung bei Taster-Kontakten (Bounce-Effekt).

## Config-Dateien

| Datei | Zweck |
|-------|-------|
| `/etc/raspi_audio/config.json` | Zentrale Config (Sounds, Schedules, Audio, Network) |
| `/etc/raspi_audio/board.json` | GPIO-Pin-Konfiguration |
| `/etc/raspi_audio/.secret_key` | Flask-Session-Secret |
| `/etc/raspi_audio/sounds/` | MP3-Dateien |
| `/usr/local/bin/raspi_gpio.py` | GPIO-Daemon (auto-generiert) |

## Services

```bash
# Status prüfen
systemctl status raspi-audio-web
systemctl status raspi-audio-gpio
systemctl status pulseaudio

# Neustart
sudo systemctl restart raspi-audio-web
sudo systemctl restart raspi-audio-gpio

# Logs anzeigen
sudo journalctl -u raspi-audio-web -f
sudo journalctl -u raspi-audio-gpio -f
```

## Troubleshooting

### Audio wird nicht abgespielt
```bash
# PulseAudio-Status prüfen
pactl info

# USB-Soundkarte prüfen
aplay -l
arecord -l

# Loopback manuell starten
pactl load-module module-loopback source=usb-input@00:00.0.analog-stereo+ sink=usb-output@00:00.0.analog-stereo
```

### GPIO-Triggers funktionieren nicht
```bash
# GPIO-Script prüfen
cat /usr/local/bin/raspi_gpio.py

# GPIO-Status prüfen
cat /sys/class/gpio/gpio*/value

# Logs anschauen
sudo journalctl -u raspi-audio-gpio -f
```

### Web-UI nicht erreichbar
```bash
# Netzwerk-Status prüfen
ip addr show

# Firewall prüfen
sudo ufw status

# Service-Status prüfen
systemctl status raspi-audio-web
```

### Update fehlgeschlagen
```bash
# Manuelles Pull
cd /home/pi/raspi_app
git pull origin main

# Service neu starten
sudo systemctl restart raspi-audio-web
```

## Software-Update

Über die Web-UI im **"Update"-Tab**:
1. Auf **"Update ausführen"** klicken
2. Git-Pull wird ausgeführt
3. Service automatisch neu gestartet

Manuell:
```bash
cd /home/pi/raspi_app
git pull origin main
sudo systemctl restart raspi-audio-web
```

## Sicherheit

- **Login erforderlich** für alle Konfigurationsänderungen
- **Passwort-Schutz** für HTTP-Trigger (`webif-pass` Parameter)
- **GPIO-Zugriff** nur über systemd-Service (root)
- **Netzwerk** nur im lokalen Netzwerk erreichbar

## Lizenz

MIT License – frei verwendbar und modifizierbar.

## Support

Bei Problemen bitte Issues auf GitHub erstellen oder die Logs prüfen:
```bash
sudo journalctl -u raspi-audio-web -f
sudo journalctl -u raspi-audio-gpio -f
```

---

**Version**: main branch  
**Repository**: [`dockr69/raspi_app`](https://github.com/dockr69/raspi_app)
