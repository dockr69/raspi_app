#!/bin/bash
# ═══════════════════════════════════════════════════════════════════
#  Radxa ROCK 3A – Audio Konfigurator · install.sh (2026 Edition)
#  · Flask Web-UI Port 80
#  · Service-IP 10.0.0.10 permanent (3-fach abgesichert)
#  · Hostname: textspeicher  →  textspeicher.local (mDNS)
#  · Chromium Kiosk-Fullscreen beim Boot
#  · SSH aktiviert (Port 22)
#  · Logging: /var/log/radxa_install.log
#  Als root ausführen: sudo bash install.sh
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
KIOSK_SVC="radxa-kiosk"
SERVICE_IP="10.0.0.10"
HOSTNAME_NEW="textspeicher"
WEB_URL="http://${SERVICE_IP}"

# Logging Funktionen (Ausgabe auf Konsole + Logdatei)
log()  { echo -e "\033[1;36m[INFO]\033[0m  $*" | tee -a "$LOG_FILE"; }
ok()   { echo -e "\033[1;32m[ OK ]\033[0m  $*" | tee -a "$LOG_FILE"; }
warn() { echo -e "\033[1;33m[WARN]\033[0m  $*" | tee -a "$LOG_FILE"; }
err()  { echo -e "\033[1;31m[ERR ]\033[0m  $*" | tee -a "$LOG_FILE"; exit 1; }

[ "$EUID" -ne 0 ] && err "Bitte als root ausführen: sudo bash install.sh"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   Radxa ROCK 3A · Audio Konfigurator Setup   ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Pakete & Logging ───────────────────────────────────────────
log "Aktualisiere Paketquellen..."
apt-get update -qq >> "$LOG_FILE" 2>&1 || warn "apt-get update hatte Warnungen, siehe Log."

INSTALLED_PKGS=()
FAILED_PKGS=()

# Funktion zum Installieren und Loggen einzelner Pakete
install_pkg() {
    PKG=$1
    if DEBIAN_FRONTEND=noninteractive apt-get install -y "$PKG" --no-install-recommends >> "$LOG_FILE" 2>&1; then
        ok "Installiert: $PKG"
        INSTALLED_PKGS+=("$PKG")
    else
        warn "Fehlgeschlagen: $PKG"
        FAILED_PKGS+=("$PKG")
    fi
}

# Liste der benötigten Pakete (chromium statt chromium-browser)
PACKAGES=(
  "python3-pip" "python3-flask" "ffmpeg" "mpg123"
  "openssh-server" "avahi-daemon" "avahi-utils"
  "python3-gpiod" "x11-xserver-utils" "openbox"
  "lightdm" "lightdm-gtk-greeter" "chromium"
)

log "Installiere Systempakete..."
for p in "${PACKAGES[@]}"; do
    install_pkg "$p"
done

# FIX: Erstelle Symlink falls 'chromium' installiert wurde, aber 'chromium-browser' fehlt
if [ -f /usr/bin/chromium ] && [ ! -f /usr/bin/chromium-browser ]; then
    ln -s /usr/bin/chromium /usr/bin/chromium-browser
    ok "Symlink für chromium-browser erstellt (Fix für Radxa Repo)."
elif [ ! -f /usr/bin/chromium-browser ]; then
    warn "Weder chromium noch chromium-browser gefunden. Kiosk-Modus könnte fehlschlagen."
fi

log "Installiere Flask via pip3..."
if pip3 install flask --break-system-packages >> "$LOG_FILE" 2>&1; then
    ok "Flask via pip (break-system-packages) installiert."
elif pip3 install flask >> "$LOG_FILE" 2>&1; then
    ok "Flask via pip installiert."
else
    warn "Pip Installation fehlgeschlagen. Prüfe Log."
fi

# ── 2. App-Dateien ────────────────────────────────────────────────
log "Kopiere App nach ${APP_DIR}..."
mkdir -p "$APP_DIR" "$SOUNDS_DIR"
cp -r "$APP_SRC"/. "$APP_DIR/"
chmod +x "${APP_DIR}/app.py" >> "$LOG_FILE" 2>&1 || true
ok "App-Dateien kopiert"

# ── 3. SSH ────────────────────────────────────────────────────────
log "Aktiviere SSH..."
systemctl enable ssh  >> "$LOG_FILE" 2>&1 || systemctl enable sshd  >> "$LOG_FILE" 2>&1 || true
systemctl start  ssh  >> "$LOG_FILE" 2>&1 || systemctl start  sshd  >> "$LOG_FILE" 2>&1 || true
# PasswordAuthentication sicherstellen
SSHD_CFG="/etc/ssh/sshd_config"
if grep -q "^PasswordAuthentication no" "$SSHD_CFG" 2>/dev/null; then
  sed -i "s/^PasswordAuthentication no/PasswordAuthentication yes/" "$SSHD_CFG"
  systemctl restart ssh >> "$LOG_FILE" 2>&1 || systemctl restart sshd >> "$LOG_FILE" 2>&1 || true
fi
ok "SSH aktiv auf Port 22"

# ── 4. Hostname ────────────────────────────────────────────────────
log "Setze Hostname auf '${HOSTNAME_NEW}'..."
hostnamectl set-hostname "$HOSTNAME_NEW" 2>/dev/null || hostname "$HOSTNAME_NEW"
if ! grep -q "$HOSTNAME_NEW" /etc/hosts; then
  sed -i "s/127\.0\.1\.1.*/127.0.1.1\t${HOSTNAME_NEW}/" /etc/hosts
  grep -q "127.0.1.1.*${HOSTNAME_NEW}" /etc/hosts \
    || echo -e "127.0.1.1\t${HOSTNAME_NEW}" >> /etc/hosts
fi
ok "Hostname: ${HOSTNAME_NEW}"

# ── 5. mDNS (Avahi) ────────────────────────────────────────────────
log "Konfiguriere mDNS (${HOSTNAME_NEW}.local)..."
systemctl enable avahi-daemon >> "$LOG_FILE" 2>&1 || true
systemctl start  avahi-daemon >> "$LOG_FILE" 2>&1 || true
cat > "/etc/avahi/services/radxa-audio.service" <<'EOF'
<?xml version="1.0" standalone='no'?>
<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
  <name replace-wildcards="yes">Radxa Audio (%h)</name>
  <service>
    <type>_http._tcp</type>
    <port>80</port>
  </service>
</service-group>
EOF
systemctl restart avahi-daemon >> "$LOG_FILE" 2>&1 || true
ok "mDNS: ${HOSTNAME_NEW}.local → Port 80"

# ── 6. Service-IP permanent ────────────────────────────────────────
log "Setze Service-IP ${SERVICE_IP}..."
IFACE=$(ip route get 8.8.8.8 2>/dev/null | awk '{print $5; exit}' || true)
[ -z "$IFACE" ] && IFACE=$(ip -o link show | awk '{print $2}' | sed 's/://' | grep -v lo | head -1)
[ -z "$IFACE" ] && IFACE="eth0"

# Sofort setzen
ip addr add "${SERVICE_IP}/24" dev "$IFACE" label "${IFACE}:service" >> "$LOG_FILE" 2>&1 || true

# /etc/network/interfaces.d (persistent)
cat > "/etc/network/interfaces.d/${IFACE}-service" <<EOF
# Service-IP Radxa Audio — NICHT ENTFERNEN
auto ${IFACE}:service
iface ${IFACE}:service inet static
    address ${SERVICE_IP}/24
EOF

# rc.local Fallback
RC="/etc/rc.local"
MARKER="# radxa-service-ip"
if [ -f "$RC" ] && ! grep -q "$MARKER" "$RC"; then
  sed -i "s|^exit 0|${MARKER}\nip addr add ${SERVICE_IP}/24 dev ${IFACE} label ${IFACE}:service 2>/dev/null || true\n\nexit 0|" "$RC"
elif [ ! -f "$RC" ]; then
  printf '#!/bin/bash\n%s\nip addr add %s/24 dev %s label %s:service 2>/dev/null || true\nexit 0\n' \
    "$MARKER" "$SERVICE_IP" "$IFACE" "$IFACE" > "$RC"
  chmod +x "$RC"
fi
ok "Service-IP ${SERVICE_IP} gesetzt (${IFACE}:service)"

# ── 7. systemd: Web-Service ─────────────────────────────────────────
log "Erstelle systemd-Service: ${WEB_SVC}..."
cat > "/etc/systemd/system/${WEB_SVC}.service" <<EOF
[Unit]
Description=Radxa Audio Konfigurator (Web-UI Port 80)
After=network.target sound.target avahi-daemon.service
Wants=avahi-daemon.service

[Service]
ExecStartPre=/bin/bash -c "ip addr add ${SERVICE_IP}/24 dev ${IFACE} label ${IFACE}:service 2>/dev/null || true"
ExecStart=/usr/bin/python3 ${APP_DIR}/app.py
WorkingDirectory=${APP_DIR}
Restart=always
RestartSec=3
User=root
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload >> "$LOG_FILE" 2>&1
systemctl enable "$WEB_SVC" >> "$LOG_FILE" 2>&1
systemctl start  "$WEB_SVC" >> "$LOG_FILE" 2>&1
ok "Web-Service konfiguriert"

# ── 8. systemd: GPIO-Daemon ─────────────────────────────────────────
log "Erstelle systemd-Service: ${GPIO_SVC}..."
cat > "/etc/systemd/system/${GPIO_SVC}.service" <<EOF
[Unit]
Description=Radxa Audio GPIO Daemon
After=${WEB_SVC}.service
ConditionPathExists=/usr/local/bin/radxa_gpio.py

[Service]
ExecStart=/usr/bin/python3 /usr/local/bin/radxa_gpio.py
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload >> "$LOG_FILE" 2>&1
systemctl enable "$GPIO_SVC" >> "$LOG_FILE" 2>&1 || true
ok "GPIO-Service eingerichtet"

# ── 9. Kiosk-Modus ─────────────────────────────────────────────────
log "Konfiguriere Chromium Kiosk-Modus..."
KIOSK_USER="${SUDO_USER:-rock}"
if [ -z "$KIOSK_USER" ] || ! id "$KIOSK_USER" &>/dev/null; then
  KIOSK_USER="rock"
  if ! id "$KIOSK_USER" &>/dev/null; then
     KIOSK_USER="pi"
  fi
fi
KIOSK_HOME=$(getent passwd "$KIOSK_USER" 2>/dev/null | cut -d: -f6 || echo "/home/$KIOSK_USER")

# LightDM Autologin
if [ -f /etc/lightdm/lightdm.conf ]; then
  sed -i "s/^#\?autologin-user=.*/autologin-user=${KIOSK_USER}/" /etc/lightdm/lightdm.conf
  sed -i "s/^#\?autologin-user-timeout=.*/autologin-user-timeout=0/" /etc/lightdm/lightdm.conf
fi

# Openbox Autostart
mkdir -p "${KIOSK_HOME}/.config/openbox"
cat > "${KIOSK_HOME}/.config/openbox/autostart" <<EOF
xset s off &
xset s noblank &
xset -dpms &
sleep 5
chromium-browser --kiosk --no-first-run --noerrdialogs \
  --disable-infobars --disable-session-crashed-bubble \
  --disable-translate --disable-features=TranslateUI \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  "${WEB_URL}" &
EOF
chown -R "${KIOSK_USER}:" "${KIOSK_HOME}/.config" >> "$LOG_FILE" 2>&1 || true

# systemd Kiosk-Service (Fallback)
cat > "/etc/systemd/system/${KIOSK_SVC}.service" <<EOF
[Unit]
Description=Radxa Kiosk Browser
After=${WEB_SVC}.service graphical.target
Wants=graphical.target

[Service]
Environment=DISPLAY=:0
Environment=XAUTHORITY=${KIOSK_HOME}/.Xauthority
ExecStartPre=/bin/sleep 6
ExecStart=/usr/bin/chromium-browser --kiosk --no-first-run --noerrdialogs \
  --disable-infobars --disable-session-crashed-bubble \
  --disable-translate --disable-features=TranslateUI \
  --overscroll-history-navigation=0 \
  --check-for-update-interval=31536000 \
  ${WEB_URL}
Restart=on-failure
RestartSec=10
User=${KIOSK_USER}

[Install]
WantedBy=graphical.target
EOF
systemctl daemon-reload >> "$LOG_FILE" 2>&1
systemctl enable "$KIOSK_SVC" >> "$LOG_FILE" 2>&1 || true
ok "Kiosk konfiguriert für User: ${KIOSK_USER}"

# ── 10. Zusammenfassung ─────────────────────────────────────────────
DEVICE_IP=$(hostname -I | awk '{print $1}' || echo "Unbekannt")
echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║           Setup abgeschlossen ✓              ║"
echo "  ╠══════════════════════════════════════════════╣"
printf  "  ║  Web-UI:      http://%-24s║\n" "${DEVICE_IP}"
printf  "  ║  Service-IP:  http://%-24s║\n" "${SERVICE_IP}"
printf  "  ║  mDNS:        http://%-24s║\n" "${HOSTNAME_NEW}.local"
printf  "  ║  SSH:         ssh ${KIOSK_USER}@%-23s║\n" "${SERVICE_IP}"
echo "  ║  Log-Datei:   /var/log/radxa_install.log     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

if [ ${#FAILED_PKGS[@]} -ne 0 ]; then
    warn "Achtung: Folgende Pakete konnten nicht installiert werden:"
    warn "${FAILED_PKGS[*]}"
    warn "Details dazu findest du in: /var/log/radxa_install.log"
else
    ok "Alle Pakete wurden erfolgreich installiert!"
fi

echo ""
warn "Neustart empfohlen: sudo reboot"
echo ""
