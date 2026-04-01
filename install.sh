#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Audio Konfigurator · install.sh (Headless / Minimal)
#  Unterstuetzte Boards: Radxa ROCK 3A, Raspberry Pi 3B/4, generisch
#  · Flask Web-UI Port 80
#  · Service-IP 10.0.0.10 (fest) + optionale statische IP
#  · Kein DHCP, kein Display, kein Kiosk
#  · Hostname: textspeicher → textspeicher.local (mDNS)
#  · SSH aktiviert (Port 22)
#  · USB-Soundkarten werden automatisch erkannt
#  Als root ausfuehren: sudo bash install.sh
# ═══════════════════════════════════════════════════════════════════
set -e
cd "$(dirname "$0")"

LOG_FILE="/var/log/radxa_install.log"
touch "$LOG_FILE"
echo "=== Installations-Log gestartet: $(date) ===" > "$LOG_FILE"

APP_SRC="$(pwd)"
APP_DIR="/opt/radxa_audio"
CFG_DIR="/etc/radxa_audio"
SOUNDS_DIR="${CFG_DIR}/sounds"
WEB_SVC="radxa-audio-web"
GPIO_SVC="radxa-audio-gpio"
SERVICE_IP="192.168.1.120"
HOSTNAME_NEW="textspeicher"

# Logging
log()  { echo -e "\033[1;36m[INFO]\033[0m  $*" | tee -a "$LOG_FILE"; }
ok()   { echo -e "\033[1;32m[ OK ]\033[0m  $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m  $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "\033[1;31m[ERR ]\033[0m  $*" | tee -a "$LOG_FILE"; exit 1; }

[ "$EUID" -ne 0 ] && err "Bitte als root ausfuehren: sudo bash install.sh"

# ── 0. Board-Erkennung ──────────────────────────────────────────────
detect_board() {
  local model=""
  [ -f /proc/device-tree/model ] && model=$(tr -d '\0' < /proc/device-tree/model)
  [ -z "$model" ] && [ -f /sys/firmware/devicetree/base/model ] && model=$(tr -d '\0' < /sys/firmware/devicetree/base/model)

  if echo "$model" | grep -qi "raspberry.*pi.*4"; then
    BOARD="rpi4"; BOARD_NAME="Raspberry Pi 4"
  elif echo "$model" | grep -qi "raspberry.*pi.*3"; then
    BOARD="rpi3"; BOARD_NAME="Raspberry Pi 3B"
  elif echo "$model" | grep -qi "raspberry.*pi"; then
    BOARD="rpi"; BOARD_NAME="Raspberry Pi"
  elif echo "$model" | grep -qi "rock.*3"; then
    BOARD="rock3a"; BOARD_NAME="Radxa ROCK 3A"
  elif echo "$model" | grep -qi "radxa\|rock"; then
    BOARD="radxa"; BOARD_NAME="Radxa"
  else
    BOARD="generic"; BOARD_NAME="${model:-Unbekanntes Board}"
  fi
}

detect_gpio_chip() {
  GPIOCHIP="/dev/gpiochip0"
  [ -e /dev/gpiochip4 ] && echo "$BOARD" | grep -q "rpi" && GPIOCHIP="/dev/gpiochip4"
  GPIO_PINS="4,17,18,22,23,24,25,27"
}

detect_default_user() {
  DEFAULT_USER="${SUDO_USER:-}"
  if [ -z "$DEFAULT_USER" ] || ! id "$DEFAULT_USER" &>/dev/null 2>&1; then
    if echo "$BOARD" | grep -q "rpi"; then
      DEFAULT_USER="pi"
    elif echo "$BOARD" | grep -q "rock\|radxa"; then
      DEFAULT_USER="rock"
    fi
  fi
  if [ -z "$DEFAULT_USER" ] || ! id "$DEFAULT_USER" &>/dev/null 2>&1; then
    DEFAULT_USER=$(getent passwd | awk -F: '$3 >= 1000 && $3 < 65000 {print $1; exit}') || true
  fi
  [ -z "$DEFAULT_USER" ] && DEFAULT_USER="pi"
  return 0
}

detect_board
detect_gpio_chip
detect_default_user

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║      Audio Konfigurator Setup (Headless)     ║"
echo "  ╠══════════════════════════════════════════════╣"
printf  "  ║  Board:    %-34s║\n" "$BOARD_NAME"
printf  "  ║  GPIO:     %-34s║\n" "$GPIOCHIP"
printf  "  ║  User:     %-34s║\n" "$DEFAULT_USER"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Pakete ─────────────────────────────────────────────────────
log "Aktualisiere Paketquellen..."
apt-get update -qq >> "$LOG_FILE" 2>&1 || warn "apt-get update hatte Warnungen"

INSTALLED_PKGS=()
FAILED_PKGS=()

install_pkg() {
    if DEBIAN_FRONTEND=noninteractive apt-get install -y "$1" --no-install-recommends >> "$LOG_FILE" 2>&1; then
        ok "Installiert: $1"; INSTALLED_PKGS+=("$1")
    else
        warn "Fehlgeschlagen: $1"; FAILED_PKGS+=("$1")
    fi
}

# Nur das Noetigste — kein X11, kein Chromium, kein LightDM
PACKAGES=(
  "python3-pip" "python3-flask" "ffmpeg" "mpg123"
  "openssh-server" "avahi-daemon" "avahi-utils"
  "pulseaudio" "pulseaudio-utils"
)

log "Installiere Systempakete..."
for p in "${PACKAGES[@]}"; do install_pkg "$p"; done

# gpiod
log "Installiere gpiod..."
if DEBIAN_FRONTEND=noninteractive apt-get install -y python3-gpiod --no-install-recommends >> "$LOG_FILE" 2>&1; then
    ok "python3-gpiod via apt"
elif pip3 install gpiod --break-system-packages >> "$LOG_FILE" 2>&1; then
    ok "gpiod via pip3"
elif pip3 install gpiod >> "$LOG_FILE" 2>&1; then
    ok "gpiod via pip3 (legacy)"
else
    warn "gpiod nicht installierbar — GPIO nicht verfuegbar"
    FAILED_PKGS+=("gpiod")
fi

# Flask via pip (falls apt-Version zu alt)
pip3 install flask --break-system-packages >> "$LOG_FILE" 2>&1 \
  || pip3 install flask >> "$LOG_FILE" 2>&1 \
  || warn "Flask pip fehlgeschlagen"

# ── 2. App-Dateien ────────────────────────────────────────────────
log "Kopiere App nach ${APP_DIR}..."
mkdir -p "$APP_DIR" "$SOUNDS_DIR"
cp -r "$APP_SRC"/. "$APP_DIR/"
chmod +x "${APP_DIR}/app.py" 2>/dev/null || true

# Board-Info
cat > "${CFG_DIR}/board.json" <<EOF
{
  "board": "${BOARD}",
  "board_name": "${BOARD_NAME}",
  "gpiochip": "${GPIOCHIP}",
  "gpio_pins": [${GPIO_PINS}],
  "default_user": "${DEFAULT_USER}"
}
EOF
ok "App + Board-Info kopiert"

# ── 3. SSH ────────────────────────────────────────────────────────
log "Aktiviere SSH..."
systemctl enable ssh >> "$LOG_FILE" 2>&1 || systemctl enable sshd >> "$LOG_FILE" 2>&1 || true
systemctl start  ssh >> "$LOG_FILE" 2>&1 || systemctl start  sshd >> "$LOG_FILE" 2>&1 || true
SSHD_CFG="/etc/ssh/sshd_config"
if grep -q "^PasswordAuthentication no" "$SSHD_CFG" 2>/dev/null; then
  sed -i "s/^PasswordAuthentication no/PasswordAuthentication yes/" "$SSHD_CFG"
  systemctl restart ssh >> "$LOG_FILE" 2>&1 || systemctl restart sshd >> "$LOG_FILE" 2>&1 || true
fi
ok "SSH aktiv"

# ── 4. Hostname + mDNS ───────────────────────────────────────────
log "Setze Hostname: ${HOSTNAME_NEW}..."
hostnamectl set-hostname "$HOSTNAME_NEW" 2>/dev/null || hostname "$HOSTNAME_NEW"
grep -q "$HOSTNAME_NEW" /etc/hosts || {
  sed -i "s/127\.0\.1\.1.*/127.0.1.1\t${HOSTNAME_NEW}/" /etc/hosts
  grep -q "127.0.1.1.*${HOSTNAME_NEW}" /etc/hosts || echo -e "127.0.1.1\t${HOSTNAME_NEW}" >> /etc/hosts
}
systemctl enable avahi-daemon >> "$LOG_FILE" 2>&1 || true
systemctl start  avahi-daemon >> "$LOG_FILE" 2>&1 || true
cat > "/etc/avahi/services/radxa-audio.service" <<'EOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">Audio Konfigurator (%h)</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
  </service>
</service-group>
EOF
systemctl restart avahi-daemon >> "$LOG_FILE" 2>&1 || true
ok "Hostname + mDNS: ${HOSTNAME_NEW}.local"

# ── 5. Netzwerk: Service-IP (kein DHCP) ──────────────────────────
log "Konfiguriere Service-IP ${SERVICE_IP}..."
IFACE=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $5; exit}' || true)
[ -z "$IFACE" ] && IFACE=$(ip -o link show | awk '{print $2}' | sed 's/://' | grep -v lo | head -1)
[ -z "$IFACE" ] && IFACE="eth0"

# Sofort setzen
ip addr add "${SERVICE_IP}/24" dev "$IFACE" label "${IFACE}:service" >> "$LOG_FILE" 2>&1 || true

# Persistent
mkdir -p /etc/network/interfaces.d
rm -f "/etc/network/interfaces.d/${IFACE}"  # alte DHCP-Config weg
cat > "/etc/network/interfaces.d/${IFACE}-service" <<EOF
auto ${IFACE}:service
iface ${IFACE}:service inet static
    address ${SERVICE_IP}/24
EOF

# rc.local Fallback
RC="/etc/rc.local"
MARKER="# radxa-service-ip"
if [ -f "$RC" ] && ! grep -q "$MARKER" "$RC"; then
  sed -i "s@^exit 0@${MARKER}\nip addr add ${SERVICE_IP}/24 dev ${IFACE} label ${IFACE}:service 2>/dev/null || true\n\nexit 0@" "$RC"
elif [ ! -f "$RC" ]; then
  printf '#!/bin/bash\n%s\nip addr add %s/24 dev %s label %s:service 2>/dev/null || true\nexit 0\n' \
    "$MARKER" "$SERVICE_IP" "$IFACE" "$IFACE" > "$RC"
  chmod +x "$RC"
fi
ok "Service-IP: ${SERVICE_IP} auf ${IFACE}"

# ── 6. PulseAudio System-Modus (damit root Soundkarten sieht) ────
log "Konfiguriere PulseAudio im System-Modus..."
PA_SYS_CFG="/etc/pulse/system.pa"
PA_DAEMON_CFG="/etc/pulse/daemon.conf"

# System-Modus erlauben
if [ -f "$PA_DAEMON_CFG" ]; then
    # daemonize=no: systemd verwaltet den Prozess, kein selbst-Daemonisieren
    sed -i 's/^daemonize = yes/daemonize = no/' "$PA_DAEMON_CFG" 2>/dev/null || true
    grep -q "^daemonize" "$PA_DAEMON_CFG" || echo "daemonize = no" >> "$PA_DAEMON_CFG"
    grep -q "^allow-exit" "$PA_DAEMON_CFG" || echo "allow-exit = no" >> "$PA_DAEMON_CFG"
fi

# root zur pulse-Gruppe hinzufuegen
usermod -aG pulse,pulse-access,audio root 2>/dev/null || true
if [ -n "$DEFAULT_USER" ] && id "$DEFAULT_USER" &>/dev/null 2>&1; then
    usermod -aG pulse,pulse-access,audio "$DEFAULT_USER" 2>/dev/null || true
fi

# system.pa: Karten einzeln mit .nofail laden – HDMI-Fehler crashen PA nicht mehr.
cat > "$PA_SYS_CFG" << 'PASYSPA'
#!/usr/bin/pulseaudio -nF
# PulseAudio system-mode – Radxa/RPi Audio-Appliance
# Jede ALSA-Karte wird einzeln geladen. Fehler (z.B. HDMI ohne Display)
# werden mit .nofail ignoriert, sodass PulseAudio stabil bleibt.

load-module module-device-restore
load-module module-stream-restore
load-module module-card-restore

# Karten 0-3 einzeln laden; Fehler werden ignoriert.
.nofail
load-module module-alsa-card device_id=0 tsched=no
load-module module-alsa-card device_id=1 tsched=no
load-module module-alsa-card device_id=2 tsched=no
load-module module-alsa-card device_id=3 tsched=no
.fail

load-module module-native-protocol-unix
load-module module-default-device-restore
load-module module-always-sink
load-module module-suspend-on-idle
PASYSPA

# systemd-Service fuer PulseAudio im System-Modus
cat > "/etc/systemd/system/pulseaudio-system.service" <<'PASVC'
[Unit]
Description=PulseAudio System-Wide Server
After=sound.target

[Service]
ExecStart=/usr/bin/pulseaudio --system --disallow-exit --disallow-module-loading=0 --log-target=journal
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
PASVC
systemctl daemon-reload >> "$LOG_FILE" 2>&1
systemctl enable pulseaudio-system >> "$LOG_FILE" 2>&1
systemctl start  pulseaudio-system >> "$LOG_FILE" 2>&1 || true
# User-Session PulseAudio deaktivieren (verhindert Konflikte)
systemctl --global disable pulseaudio.service pulseaudio.socket 2>/dev/null || true
ok "PulseAudio System-Modus aktiv"

# ── 7. RPi Audio-Overlay (falls Raspberry Pi) ──────────────────
if echo "$BOARD" | grep -q "rpi"; then
    RPI_CONFIG=""
    [ -f /boot/firmware/config.txt ] && RPI_CONFIG="/boot/firmware/config.txt"
    [ -f /boot/config.txt ] && RPI_CONFIG="/boot/config.txt"
    if [ -n "$RPI_CONFIG" ]; then
        grep -q "^dtparam=audio=on" "$RPI_CONFIG" || echo "dtparam=audio=on" >> "$RPI_CONFIG"
        ok "RPi Audio-Overlay: $RPI_CONFIG"
    fi
fi

# ── 8. systemd: Web-Service ─────────────────────────────────────
log "Erstelle Web-Service..."
cat > "/etc/systemd/system/${WEB_SVC}.service" <<EOF
[Unit]
Description=Audio Konfigurator (Web-UI Port 80)
After=network.target sound.target avahi-daemon.service pulseaudio-system.service
Wants=avahi-daemon.service pulseaudio-system.service

[Service]
ExecStartPre=/bin/bash -c "ip addr add ${SERVICE_IP}/24 dev ${IFACE} label ${IFACE}:service 2>/dev/null || true"
ExecStart=/usr/bin/python3 ${APP_DIR}/app.py
WorkingDirectory=${APP_DIR}
Restart=always
RestartSec=3
User=root
Environment=PYTHONUNBUFFERED=1
Environment=PULSE_SERVER=unix:/var/run/pulse/native

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload >> "$LOG_FILE" 2>&1
systemctl enable "$WEB_SVC" >> "$LOG_FILE" 2>&1
systemctl start  "$WEB_SVC" >> "$LOG_FILE" 2>&1
ok "Web-Service: Port 80"

# ── 9. systemd: GPIO-Daemon ─────────────────────────────────────
log "Erstelle GPIO-Service..."
cat > "/etc/systemd/system/${GPIO_SVC}.service" <<EOF
[Unit]
Description=Audio GPIO Daemon
After=${WEB_SVC}.service pulseaudio-system.service
ConditionPathExists=/usr/local/bin/radxa_gpio.py

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/radxa_gpio.py
Restart=always
RestartSec=5
User=root
Environment=PULSE_SERVER=unix:/var/run/pulse/native

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload >> "$LOG_FILE" 2>&1
systemctl enable "$GPIO_SVC" >> "$LOG_FILE" 2>&1 || true
ok "GPIO-Service bereit"

# ── 10. Alte Kiosk-Dienste entfernen (falls vorhanden) ───────────
for svc in radxa-kiosk; do
  if systemctl is-enabled "$svc" 2>/dev/null | grep -q enabled; then
    systemctl disable "$svc" >> "$LOG_FILE" 2>&1 || true
    systemctl stop "$svc" >> "$LOG_FILE" 2>&1 || true
    rm -f "/etc/systemd/system/${svc}.service"
    ok "Alter Dienst entfernt: $svc"
  fi
done
systemctl daemon-reload >> "$LOG_FILE" 2>&1

# ── 11. Zusammenfassung ─────────────────────────────────────────
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║           Setup abgeschlossen                ║"
echo "  ╠══════════════════════════════════════════════╣"
printf  "  ║  Board:       %-31s║\n" "${BOARD_NAME}"
printf  "  ║  GPIO:        %-31s║\n" "${GPIOCHIP}"
printf  "  ║  Web-UI:      http://%-24s║\n" "${SERVICE_IP}"
printf  "  ║  mDNS:        http://%-24s║\n" "${HOSTNAME_NEW}.local"
printf  "  ║  SSH:         ssh %s@%-19s║\n" "${DEFAULT_USER}" "${SERVICE_IP}"
echo "  ║  Log:         /var/log/radxa_install.log     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

if [ ${#FAILED_PKGS[@]} -ne 0 ]; then
    warn "Fehlgeschlagene Pakete: ${FAILED_PKGS[*]}"
fi

warn "Neustart empfohlen: sudo reboot"
echo ""
