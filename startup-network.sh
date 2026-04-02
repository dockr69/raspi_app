#!/bin/bash
# Startup-Netzwerk-Skript für Audio Konfigurator
# Wird vom Web-Service (ExecStartPre) aufgerufen
CFG="/etc/raspi_audio/config.json"
SERVICE_IP="10.0.0.10"
LOG="/var/log/radxa-network.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG" 2>/dev/null; }

log "Startup-Netzwerk gestartet"

# Interface erkennen
IFACE=$(ip -o link show 2>/dev/null | awk '{print $2}' | sed 's/://' | grep -E '^(eth|en)' | head -1)
[ -z "$IFACE" ] && IFACE=$(ip -o link show 2>/dev/null | awk '{print $2}' | sed 's/://' | grep -v lo | head -1)
[ -z "$IFACE" ] && IFACE="eth0"

# Warten bis Interface bereit ist (max 30 Sekunden)
for i in $(seq 1 30); do
    if ip link show "$IFACE" &>/dev/null; then
        log "Interface $IFACE ist bereit"
        break
    fi
    log "Warte auf Interface $IFACE... ($i/30)"
    sleep 1
done

# Statische IP setzen (falls konfiguriert)
IP="192.168.1.120"
GW="192.168.1.1"
MASK="24"

if [ -n "$IP" ]; then
    # Prüfen ob IP schon gesetzt
    if ! ip addr show "$IFACE" | grep -q "$IP"; then
        ip addr add "${IP}/${MASK}" dev "$IFACE" 2>/dev/null && log "IP ${IP}/${MASK} gesetzt" || log "IP setzen fehlgeschlagen"
    else
        log "IP ${IP} bereits gesetzt"
    fi
fi

# Service-IP setzen (falls noch nicht vorhanden)
SERVICE_IP="10.0.0.10"
if ! ip addr show "$IFACE" | grep -q "$SERVICE_IP"; then
    ip addr add "${SERVICE_IP}/24" dev "$IFACE" label "${IFACE}:service" 2>/dev/null && log "Service-IP ${SERVICE_IP} gesetzt" || log "Service-IP setzen fehlgeschlagen"
else
    log "Service-IP bereits gesetzt"
fi

# Default-Gateway setzen
if [ -n "$GW" ]; then
    ip route del default 2>/dev/null || true
    ip route add default via "$GW" dev "$IFACE" 2>/dev/null && log "Gateway $GW gesetzt" || log "Gateway setzen fehlgeschlagen"
fi

# DNS setzen
DNS="8.8.8.8"
if [ -n "$DNS" ] && ! grep -q "$DNS" /etc/resolv.conf 2>/dev/null; then
    echo "nameserver ${DNS}" > /etc/resolv.conf && log "DNS auf $DNS gesetzt" || log "DNS setzen fehlgeschlagen"
fi

log "Interface: $IFACE"

# Config lesen falls vorhanden
if [ -f "$CFG" ]; then
    IP=$(python3 -c "import json; print(json.load(open('$CFG')).get('network',{}).get('ip',''))" 2>/dev/null || true)
    GW=$(python3 -c "import json; print(json.load(open('$CFG')).get('network',{}).get('gateway',''))" 2>/dev/null || true)
    DNS=$(python3 -c "import json; print(json.load(open('$CFG')).get('network',{}).get('dns','8.8.8.8'))" 2>/dev/null || echo 8.8.8.8)
    MASK=$(python3 -c "import json; m=json.load(open('$CFG')).get('network',{}).get('mask','255.255.255.0'); print(sum(bin(int(x)).count('1') for x in m.split('.')))" 2>/dev/null || echo 24)
    log "Config: IP=$IP, GW=$GW, DNS=$DNS, MASK=$MASK"
else
    log "Keine Config gefunden, verwende Defaults"
    IP="192.168.1.120"
    GW="192.168.1.1"
    DNS="8.8.8.8"
    MASK="24"
fi

# Warten bis Interface bereit ist (max 30 Sekunden)
for i in $(seq 1 30); do
    if ip link show "$IFACE" &>/dev/null; then
        log "Interface $IFACE ist bereit"
        break
    fi
    log "Warte auf Interface $IFACE... ($i/30)"
    sleep 1
done

# Statische IP setzen (falls konfiguriert)
if [ -n "$IP" ]; then
    # Prüfen ob IP schon gesetzt
    if ! ip addr show "$IFACE" | grep -q "$IP"; then
        ip addr add "${IP}/${MASK}" dev "$IFACE" 2>/dev/null && log "IP ${IP}/${MASK} gesetzt" || log "IP setzen fehlgeschlagen"
    else
        log "IP ${IP} bereits gesetzt"
    fi
fi

# Service-IP setzen (falls noch nicht vorhanden)
if ! ip addr show "$IFACE" | grep -q "$SERVICE_IP"; then
    ip addr add "${SERVICE_IP}/24" dev "$IFACE" label "${IFACE}:service" 2>/dev/null && log "Service-IP ${SERVICE_IP} gesetzt" || log "Service-IP setzen fehlgeschlagen"
else
    log "Service-IP bereits gesetzt"
fi

# Default-Gateway setzen
if [ -n "$GW" ]; then
    ip route del default 2>/dev/null || true
    ip route add default via "$GW" dev "$IFACE" 2>/dev/null && log "Gateway $GW gesetzt" || log "Gateway setzen fehlgeschlagen"
fi

# DNS setzen
if [ -n "$DNS" ] && ! grep -q "$DNS" /etc/resolv.conf 2>/dev/null; then
    echo "nameserver ${DNS}" > /etc/resolv.conf && log "DNS auf $DNS gesetzt" || log "DNS setzen fehlgeschlagen"
fi

log "Startup-Netzwerk abgeschlossen"
