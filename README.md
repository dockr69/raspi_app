# raspi_app – Raspberry Pi Audio Trigger System

Headless audio appliance for Raspberry Pi 3B/4. Trigger audio via HTTP or GPIO.

## Quick Start

```bash
git clone https://github.com/dockr69/raspi_app.git
cd raspi_app
sudo bash install.sh
sudo reboot
```

Web UI: `http://10.0.0.10`

## Features

- **HTTP Trigger** – `GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=sound.mp3`
- **GPIO Trigger** – Physical buttons on GPIO pins
- **Schedules** – Auto-play at specific times
- **Audio Passthrough** – Line-In → Line-Out (USB sound card)
- **Backup** – Export/Import config + sounds + text files

## Audio Trigger

```bash
# Simple trigger
curl "http://10.0.0.10/cgi-bin/index.cgi?webif-pass=1&spotrequest=alarm.mp3"

# With ID
curl "http://10.0.0.10/play/1.mp3"
```

## GPIO

Buttons between GPIO pin + GND. Debounce: 200ms.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/mp3s` | GET | List sounds |
| `/api/mp3s/upload` | POST | Upload MP3/ZIP |
| `/api/mp3s/trigger` | POST | Set trigger type, repeat, timeout |
| `/api/mp3s/play-id` | POST | Play by ID |
| `/api/mp3s/delete` | POST | Delete sound |
| `/api/mp3s/rename` | POST | Rename sound |
| `/api/schedules` | GET/POST | List/create schedules |
| `/api/audio/volume` | GET/POST | Volume control |
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

## Install

```bash
sudo bash install.sh
```

Installs: Python3, Flask, ffmpeg, pulseaudio, git
Sets: Static IP, PulseAudio system mode, systemd services

## Hardware

- Raspberry Pi 3B/4
- USB sound card (C-Media CM108)
- Ethernet
- GPIO buttons (optional)
