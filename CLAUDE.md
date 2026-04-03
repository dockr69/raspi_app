# raspi_app – Audio Konfigurator (Raspberry Pi 3B/4)

Headless audio appliance. Web UI on port 80.

## Infrastructure

| Component | Path |
|-----------|------|
| App code | `/home/pi/raspi_app/` |
| Config | `/etc/raspi_audio/` |
| GPIO script | `/usr/local/bin/raspi_gpio.py` |
| PulseAudio | `/run/pulse/native` |

Services: `raspi-audio-web`, `raspi-audio-gpio`, `pulseaudio`

## Deploy

```bash
cd /home/pi/raspi_app
git pull
sudo systemctl restart raspi-audio-web
```

## Quick Start

```bash
git clone https://github.com/dockr69/raspi_app.git
cd raspi_app
sudo bash install.sh
sudo reboot
```

Web UI: `http://10.0.0.10`

## Audio Trigger

```bash
curl "http://10.0.0.10/cgi-bin/index.cgi?webif-pass=1&spotrequest=sound.mp3"
```

## GPIO

Buttons: GPIO pin + GND. Debounce 200ms.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mp3s` | GET | List sounds |
| `/api/mp3s/upload` | POST | Upload MP3/ZIP |
| `/api/mp3s/trigger` | POST | Set trigger, repeat, timeout |
| `/api/mp3s/play-id` | POST | Play by ID |
| `/api/mp3s/delete` | POST | Delete |
| `/api/mp3s/rename` | POST | Rename |
| `/api/schedules` | GET/POST | Schedules |
| `/api/audio/volume` | GET/POST | Volume |
| `/api/backup/export` | GET | Download backup.zip |
| `/api/backup/import` | POST | Upload backup.zip |

## Config

- `config.json` – Main config
- `board.json` – GPIO pins  
- `texts/*.txt` – Text files
- `sounds/*.mp3` – Audio files

## Services

```bash
sudo systemctl status raspi-audio-web
sudo systemctl status raspi-audio-gpio
sudo journalctl -u raspi-audio-web -f
```

## Update

```bash
cd /home/pi/raspi_app
git pull
sudo systemctl restart raspi-audio-web
```

## Hardware

- Raspberry Pi 3B/4
- USB sound card (C-Media CM108)
- Ethernet
- GPIO buttons (optional)

## Important Notes

- **Never use `Write` tool for large code blocks** – destroys file
- **Always use `Edit` tool** for changes
- For complex changes: create in temp file, test syntax, then insert
- Backup functions: `_backup_export_zip()` and `_backup_import_zip()`

## GitHub

`dockr69/raspi_app` – main branch
