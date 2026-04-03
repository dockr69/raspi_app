#!/bin/bash
# Liest Netzwerk-Config und setzt IP + Gateway beim Start
CFG="/etc/raspi_audio/config.json"
SERVICE_IP="10.0.0.10"

IFACE=$(python3 -c "import json; print(json.load(open('$CFG')).get('network',{}).get('interface','eth0'))" 2>/dev/null || echo eth0)
IP=$(python3 -c "import json; print(json.load(open('$CFG')).get('network',{}).get('ip',''))" 2>/dev/null || true)
GW=$(python3 -c "import json; print(json.load(open('$CFG')).get('network',{}).get('gateway',''))" 2>/dev/null || true)
MASK=$(python3 -c "import json; m=json.load(open('$CFG')).get('network',{}).get('mask','255.255.255.0'); print(sum(bin(int(x)).count('1') for x in m.split('.')))" 2>/dev/null || echo 24)

[ -n "$IP" ] && ip addr add "${IP}/${MASK}" dev "$IFACE" 2>/dev/null || true
ip addr add "${SERVICE_IP}/24" dev "$IFACE" label "${IFACE}:service" 2>/dev/null || true
if [ -n "$GW" ]; then
    ip route del default 2>/dev/null
    ip route add default via "$GW" dev "$IFACE" 2>/dev/null || true
fi
