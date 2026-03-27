# Radxa Audio Konfigurator

Ein webbasiertes Konfigurationssystem für **Radxa ROCK 3A, 3C, 4C+, 4SE, 5C, 2F** und andere Boards mit 40-Pin-GPIO-Header, das Audio-Management, Netzwerkkonfiguration, Datei-Uploads und GPIO-Tasterbelegung über eine moderne Browser-Oberfläche ermöglicht – inklusive automatischem Kiosk-Modus beim Booten.

![Platform](https://img.shields.io/badge/Platform-Radxa%20ROCK%203A%20%7C%203C%20%7C%204C+%20%7C%205C%20u.a.-orange)
![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-2.3+-lightgrey?logo=flask)
![License](https://img.shields.io/badge/License-Private-red)

---

## Inhaltsverzeichnis

- [Übersicht](#übersicht)
- [Features](#features)
- [Systemanforderungen](#systemanforderungen)
- [Installation](#installation)
- [Zugang nach der Installation](#zugang-nach-der-installation)
- [Einrichtungsassistent](#einrichtungsassistent)
- [Funktionen im Detail](#funktionen-im-detail)
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
- [Abhängigkeiten](#abhängigkeiten)

---

## Übersicht

Der **Radxa Audio Konfigurator** verwandelt einen Radxa ROCK 3A, 3C, 4C+, 4SE, 5C, 2F oder kompatiblen ARM-Linux-Einplatinencomputer in ein vollständiges, netzwerkfähiges Audiowiedergabe-System. Nach der einmaligen Einrichtung über einen 5-Schritte-Assistenten steht das Gerät als eigenständiger Audio-Server bereit:

- **Immer erreichbar** unter der festen Service-IP `10.0.0.10` sowie `http://textspeicher.local`
- **Audiodateien** per Drag-and-Drop hochladen – automatische Konvertierung via ffmpeg, bis zu 4 Dateien gleichzeitig
- **Wiedergabe** per HTTP-Request (Integration in externe Systeme) oder physischem GPIO-Taster
- **Pro Sound** wählbar: HTTP-Trigger, GPIO-Trigger oder beides
- **Kiosk-Modus**: Chromium startet beim Booten automatisch im Vollbild mit der Web-UI

---

## Features

| Feature | Beschreibung |
|---|---|
| **Einrichtungsassistent** | 5-Schritte-Wizard für Erstkonfiguration |
| **Netzwerk** | Statische IP-Konfiguration mit permanenter Service-IP `10.0.0.10` |
| **Audio** | Getrennte Lautstärkeregler für Ausgang (Line-Out) und Eingang (Line-In), automatisches Mute während Wiedergabe |
| **Combo Jack** | 3,5-mm-TRRS-Konfiguration: Soundkarte & Profil wählen (z. B. Headset-Modus für Eingang + Ausgang) |
| **Datei-Upload** | Beliebige Audioformate – ffmpeg konvertiert automatisch zu MP3 (bis zu 4 parallel) |
| **HTTP-Trigger** | Audiodatei per GET-Request abspielen, kompatibel mit externen Systemen |
| **GPIO-Taster** | Physische Taster auf GPIO-Pins direkt mit Sounds verknüpfen |
| **Trigger-Typ** | Pro Sound individuell: HTTP, GPIO oder gesperrt konfigurierbar |
| **Wiederholungen** | Pro Sound einstellbar: 1–10× Wiederholen (HTTP-Trigger, GPIO und Play-Button) |
| **GPIO-Daemon** | Automatisch generiertes Python-Skript als systemd-Dienst |
| **Status-Dashboard** | Übersicht über alle IPs, Sounds, Trigger-URLs und Systemstatus |
| **Kiosk-Modus** | Chromium im Vollbild beim Booten (Openbox + LightDM) |
| **mDNS** | Erreichbar unter `textspeicher.local` im lokalen Netzwerk |
| **SSH** | OpenSSH vorkonfiguriert für Remote-Zugriff |
| **Authentifizierung** | Login-Seite mit Benutzername/Passwort, Session-basiert, Passwort jederzeit änderbar |
| **Web-Terminal** | Eingebettetes Browser-Terminal mit Command-History und persistentem Verzeichnis |

---

## Systemanforderungen

- **Betriebssystem**: Radxa Debian (Bullseye / Bookworm, arm64)
- **Zugriff**: Root- oder sudo-Berechtigung
- **Netzwerk**: Aktive Netzwerkverbindung während der Installation

### Kompatible Boards

Alle Radxa-Boards mit 40-Pin-GPIO-Header und Radxa-Debian-Image werden unterstützt. Der GPIO-Daemon nutzt `python3-gpiod` (libgpiod) und ist damit unabhängig von RPi.GPIO.

| Board | SoC | 40-Pin GPIO | Audio Jack | Combo Jack (TRRS) | Bemerkung |
|---|---|---|---|---|---|
| **ROCK 3A** | RK3568 | ✓ | 3,5 mm | ✓ | Referenzboard, vollständig getestet |
| **ROCK 3C** | RK3566 | ✓ | 3,5 mm | ✓ | Vergleichbar mit ROCK 3A |
| **ROCK 4C+** | RK3399-T | ✓ | 3,5 mm | ✓ | Vollständig kompatibel |
| **ROCK 4SE** | RK3399-T | ✓ | 3,5 mm | ✓ | Identisch mit 4C+ (anderes Layout) |
| **ROCK 5A** | RK3588S | ✓ | — | — | Kein 3,5-mm-Jack; Audio über USB-DAC oder HAT |
| **ROCK 5B** | RK3588 | ✓ | 3,5 mm | — | Nur Ausgang; kein Mic-Eingang am Jack |
| **ROCK 5C** | RK3588S | ✓ | 3,5 mm | ✓ | Combo Jack vorhanden |
| **ROCK 2F** | RK3528 | ✓ | 3,5 mm | ✓ | Kleineres Board, sonst kompatibel |
| **Zero 3W / 3E** | RK3566 | ✓ (40-Pin) | — | — | Kein Audio-Jack; kompakter Formfaktor |

> **Combo Jack (TRRS):** Boards mit TRRS-Anschluss können Eingang und Ausgang über denselben Stecker nutzen. Das richtige PulseAudio-Profil (`headset-head-unit`) muss über die Audio-Einstellungen gesetzt werden – die Web-UI unterstützt dies direkt.

---

## Installation

```bash
# Repository klonen oder Dateien auf das Gerät übertragen
git clone https://github.com/dockr69/radxa_app.git
cd radxa_app

# Installationsskript ausführen
sudo bash install.sh
```

Das Installationsskript führt folgende Schritte automatisch aus:

| Schritt | Beschreibung |
|---|---|
| Systempakete | ffmpeg, mpg123, openssh-server, avahi-daemon, chromium, openbox, lightdm |
| App-Deployment | Kopiert App nach `/opt/radxa_audio` |
| SSH | Aktiviert Passwort-Authentifizierung |
| Hostname | Setzt Hostname auf `textspeicher`, konfiguriert mDNS |
| Service-IP | Richtet `10.0.0.10/24` als permanente IP ein (3-fache Absicherung) |
| systemd | Erstellt und aktiviert alle drei Dienste (Web, GPIO, Kiosk) |
| Autologin | Konfiguriert LightDM und Openbox-Autostart für Kiosk-Modus |

Nach Abschluss einmalig neu starten:

```bash
sudo reboot
```

---

## Zugang nach der Installation

| Zugang | Adresse |
|---|---|
| **Web-UI (Service-IP)** | `http://10.0.0.10` |
| **Web-UI (mDNS)** | `http://textspeicher.local` |
| **Web-UI (statische IP)** | `http://<konfigurierte-IP>` |
| **SSH** | `ssh pi@10.0.0.10` |

> Die Web-UI ist passwortgeschützt. Beim ersten Start wird automatisch ein zufälliges Passwort generiert und in den Systemlogs ausgegeben:
> ```bash
> journalctl -u radxa-audio-web | grep Passwort
> ```
> Benutzername: **pi** · Passwort direkt nach dem ersten Login über den 🔑-Button ändern.

---

## Einrichtungsassistent

Beim ersten Aufruf der Web-UI startet automatisch ein **5-Schritte-Assistent**:

```
Schritt 1 – Willkommen
  └── Übersicht über den Einrichtungsprozess

Schritt 2 – Netzwerk
  └── Statische IP, Subnetzmaske, Gateway, DNS konfigurieren
      Statische IP konfigurieren

Schritt 3 – Audio
  └── PulseAudio-Eingangsquelle wählen, Lautstärke einstellen

Schritt 4 – Sounds
  └── MP3-Dateien hochladen (Drag & Drop, bis zu 4 parallel)
      Trigger-Typ je Datei: HTTP oder GPIO festlegen

Schritt 5 – GPIO
  └── Physische Taster auf GPIO-Pins den Sounddateien zuweisen
      → GPIO-Daemon wird automatisch generiert und gestartet
```

Nach Abschluss des Assistenten wechselt die UI automatisch in das **Status-Dashboard**.

---

## Funktionen im Detail

### Netzwerkkonfiguration

- Konfiguriert eine statische IP-Adresse auf dem gewählten Netzwerk-Interface
- Die Service-IP `10.0.0.10` ist fest eingerichtet und immer erreichbar
- Validierung von IP-Adresse, Gateway und DNS direkt im Browser

### Audio-Konfiguration

- Erkennt alle verfügbaren PulseAudio/PipeWire-Eingabequellen automatisch
- **Getrennter Lautstärkeregler für Ausgang und Eingang** (0–100 %)
  - 🔊 **Ausgang (Line-Out/Lautsprecher)** → `pactl set-sink-volume @DEFAULT_SINK@`
  - 🎙 **Eingang (Line-In/Mikrofon)** → `pactl set-source-volume <quelle>`
  - Beide Regler im Wizard-Schritt 2 und direkt auf dem Dashboard verfügbar
- Während der Audiowiedergabe wird die Eingangsquelle automatisch stummgeschaltet und danach wieder aktiviert
- Mute/Unmute-Steuerung einzelner Quellen per API
- Testfunktion zum Abspielen einer Testsequenz direkt aus der UI

### Combo Jack / 3,5-mm-TRRS

Boards wie der Radxa ROCK 3A und ROCK 4C+ haben einen kombinierten Headset-Anschluss (TRRS). Damit der Eingang (Mikrofon / Line-In) an diesem Anschluss aktiv ist, muss das richtige PulseAudio-Kartenprofil gesetzt werden:

- Alle verfügbaren Soundkarten werden automatisch erkannt
- Alle Profile der gewählten Karte werden aufgelistet; Headset-Profile sind hervorgehoben
- Empfohlenes Profil: `output:analog-stereo+input:headset-head-unit`
- Profil wird sofort per `pactl set-card-profile` aktiviert – kein Neustart erforderlich

### Sound-Bibliothek & Uploads

- Unterstützt **alle gängigen Audioformate** – ffmpeg konvertiert automatisch zu MP3
  - Konvertierungsparameter: 44.100 Hz, Mono, 128 kbps
- Drag-and-Drop-Upload mit Fortschrittsanzeige pro Datei
- **Parallele Verarbeitung**: bis zu 4 ffmpeg-Prozesse gleichzeitig via `ThreadPoolExecutor`
- Thread-sicherer Dateinamen-Konfliktschutz während paralleler Uploads
- Automatische Dateinamen-Bereinigung (Kleinbuchstaben, Unterstriche, keine Sonderzeichen)
- Duplikate werden mit `_1`, `_2` etc. durchnummeriert
- Dateien können umbenannt und gelöscht werden
- **Trigger-Typ pro Sound** wählbar (HTTP, GPIO oder gesperrt) – jederzeit änderbar
- **Wiederholungen pro Sound** einstellbar (1–10×) – gilt für HTTP-Trigger, GPIO und Play-Button
  - Ablauf: Eingang stumm → N-mal abspielen → Eingang wieder aktiv
  - Badge `🔁 ×N` in Sound-Liste und Dashboard wenn > 1×
- Thread-Mutex verhindert gleichzeitige Wiedergabe mehrerer Dateien

### HTTP-Trigger

Audiodateien können per einfachem HTTP GET-Request abgespielt werden – ideal für die Integration in andere Systeme, Automatisierungen oder externe Hardware.

**URL-Format:**
```
GET http://10.0.0.10/cgi-bin/index.cgi?webif-pass=<passwort>&spotrequest=<dateiname.mp3>
```

**Vereinfachtes Format:**
```
GET http://10.0.0.10/play/<dateiname.mp3>
```

- Das `webif-pass`-Passwort ist in den Einstellungen konfigurierbar (Standard: `1`)
- Sounds mit Trigger-Typ `gpio` lehnen HTTP-Anfragen ab
- Das Status-Dashboard zeigt fertige Trigger-URLs direkt zum Kopieren an

### GPIO-Taster

Physische Taster können direkt mit Audiodateien verknüpft werden:

**Verfügbare GPIO-Pins:** `4, 17, 18, 22, 23, 24, 25, 27`

- Jedem Sound kann ein GPIO-Pin zugewiesen werden
- Bei Tastendruck (fallende Flanke) wird die zugewiesene Datei abgespielt
- 200 ms Entprellzeit (Debounce)
- Pull-up-Widerstände werden automatisch aktiviert
- Das System generiert automatisch ein Python-Daemon-Skript (`/usr/local/bin/radxa_gpio.py`)
- Der Daemon läuft als systemd-Dienst und startet automatisch beim Booten
- Neue GPIO-Zuweisungen werden sofort übernommen – der Daemon wird neu generiert und neu gestartet
- Verwendet **`python3-gpiod`** (libgpiod) statt RPi.GPIO → kompatibel mit Radxa ROCK 3A, 4C+ und allen libgpiod-fähigen Boards
- Unterstützt automatisch gpiod 2.x (Debian Bookworm) und gpiod 1.x

---

## Status-Dashboard

Nach der Einrichtung zeigt die Hauptansicht eine vollständige Übersicht:

- **IP-Karten**: Konfigurierte statische IP und Service-IP `10.0.0.10`
- **Status-Tiles**: Anzahl Sounds, SSH-Status, mDNS, Trigger-Port
- **Sound-Bibliothek**:
  - Fertige HTTP-Trigger-URLs zum Kopieren
  - Zugewiesene GPIO-Pins mit Badge-Anzeige (`🌐 HTTP` / `🔌 GPIO [Pin]`)
  - Aktionen: Abspielen, Umbenennen, Löschen, Trigger-Typ ändern
- **Upload-Bereich** für neue Sounds direkt im Dashboard
- **Lautstärke-Karte**: Ausgang und Eingang direkt auf dem Dashboard regelbar
- **Web-Terminal**: eingebettetes Terminal (⌨-Button), Command-History, persistentes Verzeichnis

---

## API-Referenz

### Authentifizierung
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET/POST | `/login` | Login-Seite |
| GET | `/logout` | Session beenden |
| POST | `/api/auth/change-password` | Passwort ändern (`old_password`, `new_password`) |
| POST | `/api/terminal/exec` | Shell-Befehl ausführen (`cmd`) |

### System
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/status` | Systemstatus und Konfiguration |
| GET | `/api/setup/status` | Setup-Fortschritt |
| POST | `/api/setup/finish` | Setup als abgeschlossen markieren |
| POST | `/api/setup/reset` | Setup zurücksetzen |

### Netzwerk
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/network/interfaces` | Verfügbare Netzwerk-Interfaces |
| POST | `/api/network/validate` | IP-Konfiguration validieren |
| POST | `/api/network/apply` | IP-Konfiguration anwenden |
| POST | `/api/network/ping` | Verbindungstest |

### Audio
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/audio/sources` | PulseAudio-Quellen auflisten |
| GET | `/api/audio/cards` | Soundkarten mit Profilen auflisten |
| POST | `/api/audio/card-profile` | Kartenprofil setzen (z. B. Headset für Combo Jack) |
| POST | `/api/audio/save` | Audio-Konfiguration speichern (source, volume, input_volume) |
| POST | `/api/audio/mute` | Quelle stummschalten / Stummschaltung aufheben |
| POST | `/api/audio/test` | Test-Audio abspielen |

### Dateiverwaltung
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/api/mp3s` | Alle MP3s mit Trigger-Konfiguration auflisten |
| POST | `/api/upload` | Dateien hochladen & parallel konvertieren |
| POST | `/api/mp3s/play` | MP3 abspielen |
| POST | `/api/mp3s/delete` | MP3 löschen |
| POST | `/api/mp3s/rename` | MP3 umbenennen |
| POST | `/api/mp3s/trigger` | Trigger-Typ, GPIO-Pin und Wiederholungen pro Sound setzen |

### GPIO & Trigger
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| POST | `/api/gpio/save` | GPIO-Zuweisungen speichern & Daemon neu generieren |
| POST | `/api/trigger/config` | Webif-Passwort setzen |

### Wiedergabe (extern)
| Methode | Endpunkt | Beschreibung |
|---|---|---|
| GET | `/cgi-bin/index.cgi` | Trigger via `?webif-pass=X&spotrequest=Y` |
| GET | `/play/<dateiname>` | Direkter Wiedergabe-Endpunkt |

---

## Systemdienste

Nach der Installation laufen drei systemd-Dienste:

| Dienst | Beschreibung | Autostart |
|---|---|---|
| `radxa-audio-web` | Flask-Backend auf Port 80 | Ja |
| `radxa-audio-gpio` | GPIO-Taster-Daemon | Ja (nach Konfiguration) |
| `radxa-kiosk` | Chromium-Kiosk-Modus | Ja |

```bash
# Status prüfen
systemctl status radxa-audio-web
systemctl status radxa-audio-gpio
systemctl status radxa-kiosk

# Dienst neu starten
sudo systemctl restart radxa-audio-web

# Logs ansehen
journalctl -u radxa-audio-web -f
```

---

## Technische Details

### Konfigurationsdatei

Alle Einstellungen werden unter `/etc/radxa_audio/config.json` gespeichert:

```json
{
  "network": {
    "interface": "eth0",
    "ip": "192.168.1.100",
    "mask": "255.255.255.0",
    "gateway": "192.168.1.1",
    "dns": "8.8.8.8"
  },
  "audio": {
    "source": "@DEFAULT_SOURCE@",
    "volume": 80,
    "input_volume": 80
  },
  "trigger": {
    "webif_pass": "1"
  },
  "sounds": {
    "jingle": {
      "trigger_type": "http",
      "gpio_pin": null,
      "repeat": 1
    },
    "ansage": {
      "trigger_type": "gpio",
      "gpio_pin": 17,
      "repeat": 3
    }
  }
}
```

### Verzeichnisstruktur auf dem Gerät

```
/opt/radxa_audio/             → App-Verzeichnis
/etc/radxa_audio/             → Konfiguration & Sounds
  ├── config.json             → Hauptkonfiguration
  ├── .setup_done             → Setup-Abschluss-Marker
  └── sounds/                 → MP3-Dateien
/usr/local/bin/
  └── radxa_gpio.py           → Automatisch generierter GPIO-Daemon
```

### Audio-Pipeline

```
Upload (beliebiges Format)
    └── ffmpeg → MP3 (44.1 kHz, Mono, 128 kbps)
    [bis zu 4 gleichzeitig via ThreadPoolExecutor]
                    └── mpg123 → Wiedergabe
                                    │
                    PulseAudio-Quelle wird während Wiedergabe
                    automatisch stummgeschaltet
```

### GPIO-Daemon (automatisch generiert)

```python
# /usr/local/bin/radxa_gpio.py (auto-generiert)
# Bibliothek: python3-gpiod (libgpiod) — kompatibel mit Radxa ROCK 3A, 4C+ und anderen Boards
# Pull-up, Falling Edge, 200ms Debounce
# Automatische API-Erkennung: gpiod 2.x (Bookworm) mit Fallback auf gpiod 1.x
# Wird bei jeder Änderung der GPIO-Konfiguration neu erstellt
# Läuft als systemd-Dienst radxa-audio-gpio
```

### Sicherheitsmechanismen

- **Session-Authentifizierung**: Alle Seiten und API-Endpunkte erfordern Login (außer HTTP-Trigger)
- Passwort gehasht gespeichert (`werkzeug.security`) in `config.json`
- Session-Key persistent in `/etc/radxa_audio/.secret_key` (600 Permissions)
- `threading.Lock` verhindert gleichzeitige Audiowiedergabe
- Thread-sicherer Dateinamen-Konfliktschutz bei parallelen Uploads
- Pfad-Traversal-Schutz bei allen Dateioperationen
- Interface- und IP-Validierung vor Shell-Ausführung
- 20 Sekunden Standard-Timeout für Subprozesse (90 s für ffmpeg, 30 s für Terminal)
- Setup-Marker verhindert versehentliches Zurücksetzen
- Service-IP `10.0.0.10` immer verfügbar

---

## Projektstruktur

```
radxa_app/
├── app.py                  # Flask-Backend (REST API, Wiedergabe, GPIO-Generierung)
├── install.sh              # Vollautomatisches Installationsskript
├── requirements.txt        # Python-Abhängigkeiten
├── templates/
│   └── index.html         # Single-Page-App (Einrichtungsassistent + Dashboard)
├── sounds/                 # Lokales Sounds-Verzeichnis
└── static/                 # Statische Assets
```

---

## Abhängigkeiten

### Python
```
flask>=2.3
```

### System (werden durch `install.sh` installiert)

| Paket | Verwendung |
|---|---|
| `ffmpeg` | Audioformat-Konvertierung (parallel, bis zu 4 gleichzeitig) |
| `mpg123` | MP3-Wiedergabe |
| `openssh-server` | SSH-Zugriff |
| `avahi-daemon` | mDNS (`textspeicher.local`) |
| `chromium-browser` | Kiosk-Modus |
| `openbox` | Leichtgewichtige Desktop-Umgebung |
| `lightdm` | Display Manager mit Autologin |
| `python3-flask` | Web-Framework |
| `python3-gpiod` | GPIO-Steuerung (libgpiod — Radxa ROCK 3A, 4C+ und andere Boards) |

---

## Autor

Entwickelt von **Fabian** für den internen Einsatz auf Radxa-Hardware (ROCK 3A, 4C+ und weiteren).

---

*Dieses Projekt ist privat und nicht für die öffentliche Nutzung bestimmt.*
