# Radxa Audio Konfigurator

Web-basiertes Tool zur Verwaltung von Audio-Ansagen auf einem Raspberry Pi (3B/4). Läuft als systemd-Service, erreichbar über Browser im lokalen Netzwerk.

## Features

- **Audio-Passthrough** — Line-In → Line-Out via PulseAudio Loopback (USB Soundkarte)
- **MP3-Upload & Konverter** — Einzeldateien oder ZIP-Archive (bis 500 MB), ffmpeg konvertiert automatisch zu MP3
- **HTTP-Trigger** — Ansagen per GET-Request auslösen (kompatibel mit WiFi-Buttons u.ä.)
- **GPIO-Trigger** — Taster direkt an GPIO-Pins (Pin → Sound Mapping per Dropdown)
- **Zeitplan** — Sounds zu festen Zeiten / Wochentagen automatisch abspielen
- **Lautstärke** — Ein- und Ausgang getrennt regelbar
- **Backup/Restore** — Config + Sounds als ZIP exportieren/importieren
- **USB Plug & Play** — Neue USB-Soundkarte wird automatisch erkannt und Config aktualisiert

## Hardware

- Raspberry Pi 3B / 4
- USB-Soundkarte (getestet mit C-Media CM108, z.B. Sabrent, Unitek)
- Ethernet-Anschluss

## Installation

```bash
git clone https://github.com/dockr69/radxa_app.git
cd radxa_app
sudo bash install.sh
```

Das Script installiert alle Abhängigkeiten, richtet PulseAudio im System-Modus ein, setzt die statische IP und startet alle Services.

## Netzwerk

| Adresse | Zweck |
|---|---|
| `192.168.1.120` | Statische IP (konfigurierbar) |
| `10.0.0.10` | Service-IP (fest) |

Web-UI erreichbar unter `http://192.168.1.120` oder `http://10.0.0.10`.

## HTTP-Trigger

```
GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=dateiname.mp3
GET /play/dateiname.mp3
```

`webif-pass` muss mit dem in den Einstellungen gesetzten Wert übereinstimmen (Default: `1`).

## Services

| Service | Beschreibung |
|---|---|
| `radxa-audio-web` | Flask Web-UI auf Port 80 |
| `radxa-audio-gpio` | GPIO-Daemon (wird automatisch generiert) |
| `pulseaudio` | Audio-Server (System-Modus) |

```bash
systemctl status radxa-audio-web
systemctl status radxa-audio-gpio
systemctl status pulseaudio
```

## GPIO-Verkabelung

Taster zwischen GPIO-Pin und GND. Pull-Up intern, Debounce 200 ms.
Pin-Mapping wird per Dropdown im Sound-Tab gesetzt — Script wird automatisch generiert.

## Sounds

MP3s liegen in `/etc/radxa_audio/sounds/`. Config in `/etc/radxa_audio/config.json`.

Unterstützte Upload-Formate: MP3, WAV, OGG, FLAC, AAC, M4A, WMA, OPUS, MP4, AIFF — auch als ZIP.

## Login

Standard-Login: Benutzername `pi`, Passwort = OS-Passwort des Pi-Users.
Passwort kann in der Web-UI unter dem Schloss-Symbol geändert werden.

## Software-Update

Klicke auf \"Update\" im Update-Tab. Der Service wird automatisch neu gestartet.

Hinweis: Bei Netzwerkproblemen wird der aktuelle Commit angezeigt.
