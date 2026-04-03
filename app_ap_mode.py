# ── API: AP Mode (WiFi Access Point) ───────────────────────────────────────────
@app.route('/api/network/ap', methods=['GET', 'POST'])
def api_ap_mode():
    """GET: AP Status, POST: AP aktivieren/deaktivieren"""
    cfg = load_cfg()
    ap = cfg.get("ap_mode", {"enabled": False, "ssid": "raspi-ap", "password": "raspi123"})

    if request.method == 'POST':
        d = request.json or {}
        enabled = d.get("enabled", False)
        ssid = d.get("ssid", "raspi-ap")
        password = d.get("password", "raspi123")

        # Validierung
        if not ssid or len(ssid) < 4:
            return jsonify({"ok": False, "msg": "SSID zu kurz (min. 4 Zeichen)"}), 400
        if enabled and (not password or len(password) < 8):
            return jsonify({"ok": False, "msg": "Passwort zu kurz (min. 8 Zeichen)"}), 400

        # Config speichern
        cfg["ap_mode"] = {
            "enabled": enabled,
            "ssid": ssid,
            "password": password,
        }
        save_cfg(cfg)

        # AP starten/stoppen
        if enabled:
            _start_ap(ssid, password)
        else:
            _stop_ap()

        return jsonify({"ok": True, "enabled": enabled, "ssid": ssid})

    return jsonify({
        "enabled": ap.get("enabled", False),
        "ssid": ap.get("ssid", "raspi-ap"),
        "password": ap.get("password", "raspi123"),
    })


# ── AP Mode Helpers ───────────────────────────────────────────────────────────
def _start_ap(ssid, password):
    """Startet WiFi Access Point auf wlan0 mit hostapd + dnsmasq."""
    # wlan0 Interface erstellen
    run("ip link set wlan0 up 2>/dev/null")

    # WLAN-Interface konfigurieren (10.0.0.1 als Gateway)
    run("ip addr add 10.0.0.1/24 dev wlan0 2>/dev/null || true")

    # hostapd Config erstellen
    hostapd_conf = "/etc/hostapd/hostapd.conf"
    os.makedirs(os.path.dirname(hostapd_conf), exist_ok=True)
    with open(hostapd_conf, 'w') as f:
        f.write(f"""interface=wlan0
driver=nl80211
ssid={ssid}
hw_mode=g
channel=7
wmm_mode=1
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase={password}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
""")

    # dnsmasq Config erstellen (DHCP Server)
    dnsmasd_conf = "/etc/dnsmasq.d/raspi-ap.conf"
    os.makedirs(os.path.dirname(dnsmasd_conf), exist_ok=True)
    with open(dnsmasd_conf, 'w') as f:
        f.write(f"""interface=wlan0
dhcp-range=10.0.0.2,10.0.0.254,255.255.255.0,12h
dhcp-option=3,10.0.0.1
dhcp-option=6,8.8.8.8
""")

    # hostapd starten
    run("systemctl enable hostapd 2>/dev/null")
    run("systemctl restart hostapd 2>/dev/null || true")

    # dnsmasq starten
    run("systemctl enable dnsmasq 2>/dev/null")
    run("systemctl restart dnsmasq 2>/dev/null || true")

    print(f"[AP] Access Point gestartet: SSID={ssid}", flush=True)


def _stop_ap():
    """Stoppt WiFi Access Point."""
    run("systemctl stop hostapd 2>/dev/null || true")
    run("systemctl stop dnsmasq 2>/dev/null || true")
    run("ip link set wlan0 down 2>/dev/null || true")
    run("ip addr flush dev wlan0 2>/dev/null || true")
    print("[AP] Access Point gestoppt", flush=True)
