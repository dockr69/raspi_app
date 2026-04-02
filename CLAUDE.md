# raspi_app – Audio Konfigurator (Raspberry Pi)

Headless 24/7 Audio-Appliance für Raspberry Pi 3B/4.
Flask Web-UI auf Port 80, USB-Soundkarte, GPIO-Trigger, Schedules.

---

## Infrastruktur

| Was | Wo |
|---|---|
| App/Code (Git-Repo) | `/home/pi/raspi_app/` |
| Config + Sounds | `/etc/raspi_audio/` |
| GPIO-Script (auto-generiert) | `/usr/local/bin/raspi_gpio.py` |
| PulseAudio Socket | `/run/pulse/native` |

**Services:**
- `raspi-audio-web` – Flask Web-UI
- `raspi-audio-gpio` – GPIO-Daemon
- `pulseaudio` – System-Modus (`--system`)

---

## Deploy-Workflow

```bash
cd /home/pi/raspi_app
git pull
sudo systemctl restart raspi-audio-web
```

**Wichtig:** Kein `/opt/radxa_audio/` mehr. Der Service läuft direkt aus dem Repo.
Niemals nach `/opt/` kopieren – das war früher der Hauptgrund für Bugs.

---

## Neuinstall

```bash
cd /home/pi/raspi_app
sudo bash install.sh
sudo reboot
```

---

## Architektur

- `app.py` – Flask-App (Audio, GPIO, Schedules, Netzwerk, Backup)
- `templates/index.html` – Web-UI (Single Page)
- `install.sh` – vollständiges Setup-Script
- `startup-network.sh` – setzt IP beim Service-Start (ExecStartPre)
- `/etc/raspi_audio/config.json` – zentrale Config (Audio, Netzwerk, Sounds, Schedules)
- `/usr/local/bin/raspi_gpio.py` – wird von `app.py` auto-generiert aus config.json

## Wichtige Konstanten in app.py

```python
CONFIG_FILE    = "/etc/raspi_audio/config.json"
MP3_FOLDER     = "/etc/raspi_audio/sounds"
BOARD_FILE     = "/etc/raspi_audio/board.json"
SECRET_KEY_FILE= "/etc/raspi_audio/.secret_key"
SERVICE_IP     = "10.0.0.10"
```

---

## Bekannte Eigenheiten

- PulseAudio läuft im `--system` Modus, Socket fest auf `/run/pulse/native`
- GPIO-Script wird bei jeder Trigger-Änderung über die UI neu generiert
- Loopback (Line-In → Line-Out) startet im Background-Thread beim App-Start
- Config-Writes sind atomar (`.tmp` + `os.replace`)
- Watchdog: 60s – blockierende Calls beim Start killen den Service

---

## GitHub

`dockr69/raspi_app` – main branch
