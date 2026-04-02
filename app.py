#!/usr/bin/env python3
"""
Audio Konfigurator – Raspberry Pi 3B / 4
· CGI-Trigger:  GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=<n>.mp3
· Legacy:       GET /play/<n>
· Statische IP + Service-IP 10.0.0.10 (parallel auf eth0)
· Hostname: konfigurierbar, Default textspeicher → textspeicher.local (mDNS)
· Audio-Passthrough: Line-In → Line-Out via PulseAudio module-loopback
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess, os, json, threading, re, secrets, shlex, time, glob as globmod, zipfile, io

app = Flask(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────────
SERVICE_IP      = "10.0.0.10"
SERVICE_MASK    = "24"
DEFAULT_HOSTNAME = "textspeicher"
CONFIG_FILE     = "/etc/radxa_audio/config.json"
MP3_FOLDER      = "/etc/radxa_audio/sounds"
BOARD_FILE      = "/etc/radxa_audio/board.json"

# ── Board-Erkennung (Raspberry Pi 3B/4) ─────────────────────────────────────
def _load_board_info():
    """Liest Board-Info aus board.json oder erkennt automatisch."""
    defaults = {
        "board": "rpi",
        "board_name": "Raspberry Pi",
        "gpiochip": "/dev/gpiochip0",
        "gpio_pins": [4, 17, 18, 22, 23, 24, 25, 27],
        "default_user": "pi",
    }
    try:
        with open(BOARD_FILE) as f:
            info = json.load(f)
            for k, v in defaults.items():
                if k not in info:
                    info[k] = v
            return info
    except Exception:
        pass
    # Fallback: automatische Erkennung
    try:
        with open("/proc/device-tree/model") as f:
            model = f.read().strip("\x00").strip()
        if "pi 4" in model.lower():
            defaults["board"] = "rpi4"
            defaults["board_name"] = "Raspberry Pi 4"
        elif "pi 3" in model.lower():
            defaults["board"] = "rpi3"
            defaults["board_name"] = "Raspberry Pi 3B"
        else:
            defaults["board_name"] = model
    except Exception:
        pass
    if os.path.exists("/dev/gpiochip4"):
        defaults["gpiochip"] = "/dev/gpiochip4"
    return defaults

BOARD_INFO = _load_board_info()
GPIO_PINS  = BOARD_INFO["gpio_pins"]
GPIOCHIP   = BOARD_INFO["gpiochip"]
print(f"[BOARD] {BOARD_INFO['board_name']} | GPIO: {GPIOCHIP} | Pins: {GPIO_PINS}", flush=True)

SECRET_KEY_FILE  = "/etc/radxa_audio/.secret_key"
DEFAULT_USER = BOARD_INFO.get("default_user", "pi")

os.makedirs(MP3_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

# PulseAudio System-Modus: Socket setzen falls nicht in Umgebung
if not os.environ.get("PULSE_SERVER"):
    pa_socket = "/var/run/pulse/native"
    if os.path.exists(pa_socket):
        os.environ["PULSE_SERVER"] = f"unix:{pa_socket}"

# ── Audio-Aliase ─────────────────────────────────────────────────────────────
AUDIO_ALIASES = {
    "alsa_input.1.mono-fallback":       "USB Audio (Eingang)",
    "alsa_input.1.analog-stereo":       "USB Audio (Eingang Stereo)",
    "alsa_output.1.analog-stereo":      "USB Audio (Ausgang)",
    "alsa_output.0.stereo-fallback":    "Internal 3.5mm Audio Jack",
    "alsa_output.0.analog-stereo":      "Internal 3.5mm Audio Jack",
}

def _audio_alias(pa_name):
    """Gibt freundlichen Alias für PulseAudio-Namen zurück."""
    if pa_name in AUDIO_ALIASES:
        return AUDIO_ALIASES[pa_name]
    # Generische Aliase
    if "usb" in pa_name.lower() or ".1." in pa_name:
        if "input" in pa_name or "source" in pa_name:
            return "USB Audio (Eingang)"
        return "USB Audio (Ausgang)"
    if ".0." in pa_name:
        if "monitor" in pa_name:
            return "Internal Monitor"
        return "Internal 3.5mm Audio Jack"
    return pa_name

# ── Hostname aus Config ──────────────────────────────────────────────────────
def get_hostname():
    cfg = load_cfg()
    # Config hat Vorrang; Fallback: echter System-Hostname
    h = cfg.get("hostname", "")
    if not h:
        try:
            import socket
            h = socket.gethostname().split('.')[0]
        except Exception:
            h = DEFAULT_HOSTNAME
    return h

# ── Loopback-Management ─────────────────────────────────────────────────────
_loopback_module_id = None

def _get_loopback_id():
    """Findet die aktuelle Loopback-Modul-ID (oder None)."""
    r = run("pactl list modules short 2>/dev/null")
    for line in r["out"].splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and "module-loopback" in parts[1]:
            return parts[0]
    return None

def ensure_loopback():
    """Stellt sicher, dass module-loopback geladen ist."""
    global _loopback_module_id
    existing = _get_loopback_id()
    if existing:
        _loopback_module_id = existing
        return
    cfg = load_cfg()
    source = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    sink = cfg.get("audio", {}).get("sink", "@DEFAULT_SINK@")
    r = run(f"pactl load-module module-loopback "
            f"source={shlex.quote(source)} "
            f"sink={shlex.quote(sink)} "
            f"latency_msec=50")
    if r["ok"]:
        _loopback_module_id = r["out"].strip()
        print(f"[AUDIO] Loopback geladen: {source} → {sink} (ID {_loopback_module_id})", flush=True)
    else:
        print(f"[AUDIO] Loopback Fehler: {r['err']}", flush=True)

def reload_loopback():
    """Entlädt und lädt Loopback mit aktueller Config neu."""
    global _loopback_module_id
    existing = _get_loopback_id()
    if existing:
        run(f"pactl unload-module {existing}")
    _loopback_module_id = None
    ensure_loopback()

# ── Default-Config ───────────────────────────────────────────────────────────
def _ensure_default_config():
    """Erstellt sinnvolle Default-Config wenn keine existiert."""
    cfg = load_cfg()
    changed = False
    if "audio" not in cfg:
        # USB Audio als Default (card 1)
        sources = detect_sources()
        sinks = _detect_sinks()
        cfg["audio"] = {
            "source": sources[0] if sources else "@DEFAULT_SOURCE@",
            "sink": sinks[0] if sinks else "@DEFAULT_SINK@",
            "volume": 100,
            "input_volume": 100,
        }
        changed = True
    elif "sink" not in cfg.get("audio", {}):
        sinks = _detect_sinks()
        cfg["audio"]["sink"] = sinks[0] if sinks else "@DEFAULT_SINK@"
        changed = True
    if "network" not in cfg:
        cfg["network"] = {
            "interface": "eth0",
            "ip": "192.168.1.120",
            "mask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns": "8.8.8.8",
        }
        changed = True
    if "hostname" not in cfg:
        cfg["hostname"] = DEFAULT_HOSTNAME
        changed = True
    if "mode" not in cfg:
        cfg["mode"] = "online"
        changed = True
    if changed:
        save_cfg(cfg)
    return cfg

# ── Secret Key (persistent, damit Sessions nach Neustart gültig bleiben) ──────
def _load_secret_key():
    """Liest oder erstellt Secret Key mit Lock fuer Thread-Safety."""
    with _secret_lock:
        if os.path.exists(SECRET_KEY_FILE):
            try:
                with open(SECRET_KEY_FILE) as f:
                    k = f.read().strip()
                    if k:
                        return k
            except Exception:
                pass
        k = secrets.token_hex(32)
        tmp = SECRET_KEY_FILE + ".tmp"
        with open(tmp, 'w') as f:
            f.write(k)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, SECRET_KEY_FILE)
        os.chmod(SECRET_KEY_FILE, 0o600)
        return k

# Secret Key wird nach _secret_lock Definition gesetzt (siehe unten)

# ── Helpers ───────────────────────────────────────────────────────────────────
def run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout)
        return {"out": r.stdout.strip(), "err": r.stderr.strip(),
                "ok": r.returncode == 0}
    except subprocess.TimeoutExpired:
        return {"out": "", "err": "timeout", "ok": False}
    except Exception as e:
        return {"out": "", "err": str(e), "ok": False}

_cfg_lock = threading.Lock()
_secret_lock = threading.Lock()

app.secret_key = _load_secret_key()

def load_cfg():
    """Liest Config mit Lock fuer Thread-Safety."""
    try:
        with _cfg_lock:
            with open(CONFIG_FILE) as f:
                return json.load(f)
    except Exception:
        return {}

def save_cfg(data):
    """Speichert Config atomar mit Lock."""
    with _cfg_lock:
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, CONFIG_FILE)

def sanitize(name):
    name = re.sub(r'\s+', '_', name.strip())
    return re.sub(r'[^a-zA-Z0-9_\-]', '', name).lower()

# ── Auth ──────────────────────────────────────────────────────────────────────
def _check_os_password(username, password):
    """Prueft Passwort gegen OS (PAM). Gibt True zurueck wenn korrekt."""
    # crypt/spwd seit Python 3.13 entfernt — verwende su
    try:
        p = subprocess.run(
            ['su', '-c', 'true', '--', username],
            input=password + '\n', capture_output=True, text=True, timeout=5
        )
        return p.returncode == 0
    except Exception:
        return False

def get_auth():
    """Liest Credentials aus Config; legt Defaults an falls nicht vorhanden."""
    cfg = load_cfg()
    auth = cfg.get("auth", {})
    if not auth.get("username"):
        auth["username"] = DEFAULT_USER
        cfg["auth"] = auth
        save_cfg(cfg)
    # password_hash ist optional — wenn nicht gesetzt, wird OS-Passwort genutzt
    return auth

def verify_login(username, password):
    """Prueft Login: zuerst Web-Passwort (falls gesetzt), dann OS-Passwort."""
    auth = get_auth()
    if username != auth.get("username", DEFAULT_USER):
        return False
    # Wenn ein Web-Passwort gesetzt wurde (ueber Einstellungen geaendert)
    if auth.get("password_hash"):
        if check_password_hash(auth["password_hash"], password):
            return True
    # OS-Passwort pruefen
    if _check_os_password(username, password):
        return True
    return False

@app.before_request
def check_auth():
    """Alle Routes außer Login/Logout/CGI-Trigger erfordern eine Session."""
    public_paths = {'/login', '/logout'}
    if (request.path in public_paths
            or request.path.startswith('/play/')
            or request.path.startswith('/cgi-bin/')):
        return
    if not session.get('logged_in'):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({"ok": False, "msg": "Nicht angemeldet"}), 401
        return redirect(url_for('login_page'))

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if session.get('logged_in'):
        return redirect(url_for('index'))
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if verify_login(username, password):
            session['logged_in'] = True
            session.permanent = False
            return redirect(url_for('index'))
        error = "Falscher Benutzername oder Passwort"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

@app.route('/api/auth/change-password', methods=['POST'])
def api_change_password():
    d        = request.json or {}
    old_pw   = d.get('old_password', '')
    new_pw   = d.get('new_password', '')
    if not new_pw or len(new_pw) < 6:
        return jsonify({"ok": False, "msg": "Neues Passwort zu kurz (min. 6 Zeichen)"}), 400
    auth = get_auth()
    username = auth.get("username", DEFAULT_USER)
    if not verify_login(username, old_pw):
        return jsonify({"ok": False, "msg": "Aktuelles Passwort falsch"}), 403
    cfg = load_cfg()
    cfg['auth'] = {
        "username":      username,
        "password_hash": generate_password_hash(new_pw),
    }
    save_cfg(cfg)
    return jsonify({"ok": True})

# ── API: Modus (online/offline) ──────────────────────────────────────────────
@app.route('/api/mode', methods=['GET', 'POST'])
def api_mode():
    if request.method == 'POST':
        mode = (request.json or {}).get("mode", "online")
        if mode not in ("online", "offline"):
            return jsonify({"ok": False, "msg": "Ungültiger Modus"}), 400
        cfg = load_cfg()
        cfg["mode"] = mode
        # Offline-Modus: alle Sounds auf GPIO umstellen
        if mode == "offline":
            for stem, sc in cfg.get("sounds", {}).items():
                sc["trigger_type"] = "gpio"
        save_cfg(cfg)
        _write_gpio_script(cfg)
        return jsonify({"ok": True, "mode": mode})
    return jsonify({"mode": load_cfg().get("mode", "online")})

def valid_ip(ip):
    m = re.match(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$", ip)
    return bool(m) and all(0 <= int(g) <= 255 for g in m.groups())

def _safe_mp3_path(name):
    """Gibt absoluten Pfad zurück wenn er innerhalb MP3_FOLDER liegt, sonst None."""
    base = os.path.realpath(MP3_FOLDER)
    path = os.path.realpath(os.path.join(MP3_FOLDER, name))
    if path.startswith(base + os.sep) and path != base:
        return path
    return None

def is_setup_done():
    return True  # Wizard entfernt — immer "fertig"

def mark_setup_done():
    pass  # Wizard entfernt

def get_interfaces():
    out = run("ip -o link show | awk '{print $2}' | sed 's/://' | grep -v lo")["out"]
    return [i.strip() for i in out.splitlines()
            if i.strip() and not i.strip().endswith(':0')] or ["eth0"]

def get_current_ips():
    """Gibt alle aktuell gesetzten IPs zurück (außer loopback)."""
    out = run("ip -o -4 addr show | awk '{print $2, $4}'")["out"]
    ips = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2:
            iface, cidr = parts
            ip = cidr.split('/')[0]
            if not ip.startswith('127.'):
                ips.append({"iface": iface, "ip": ip, "cidr": cidr})
    return ips

def ensure_service_ip(iface=None):
    check = run(f"ip addr show | grep '{SERVICE_IP}/'")
    if not (check["ok"] and SERVICE_IP in check["out"]):
        if iface is None:
            cfg = load_cfg()
            iface = cfg.get("network", {}).get("interface") or get_interfaces()[0]
        run(f"ip addr add {SERVICE_IP}/{SERVICE_MASK} dev {iface} "
            f"label {iface}:service 2>/dev/null")

def detect_sources():
    out = run("pactl list sources short 2>/dev/null")["out"]
    sources = [l.split()[1] for l in out.splitlines()
               if len(l.split()) >= 2 and "monitor" not in l.split()[1].lower()]
    return sources or ["@DEFAULT_SOURCE@"]

def _detect_sinks():
    """Erkennt alle PulseAudio-Ausgänge (Sinks)."""
    out = run("pactl list sinks short 2>/dev/null")["out"]
    sinks = [l.split()[1] for l in out.splitlines()
             if len(l.split()) >= 2]
    return sinks or ["@DEFAULT_SINK@"]

def list_mp3s():
    cfg = load_cfg()
    sounds = cfg.get("sounds", {})
    result = []
    for f in sorted(os.listdir(MP3_FOLDER)):
        if not f.lower().endswith('.mp3'):
            continue
        stem = f[:-4]
        sc   = sounds.get(stem, {})
        result.append({
            "name":         f,
            "stem":         stem,
            "size_kb":      os.path.getsize(os.path.join(MP3_FOLDER, f)) // 1024,
            "trigger_type": sc.get("trigger_type", "http"),  # "http" | "gpio"
            "gpio_pin":     sc.get("gpio_pin", None),
            "repeat":       max(1, min(10, int(sc.get("repeat", 1)))),
        })
    return result

_play_lock = threading.Lock()

def _play_thread(path, source, repeat=1):
    repeat = max(1, min(10, int(repeat)))
    cfg = load_cfg()
    sink = cfg.get("audio", {}).get("sink", "@DEFAULT_SINK@")
    with _play_lock:
        run(f"pactl set-source-mute {shlex.quote(source)} 1")
        try:
            for _ in range(repeat):
                run(f"PULSE_SINK={shlex.quote(sink)} mpg123 -q {shlex.quote(path)}", timeout=300)
        finally:
            run(f"pactl set-source-mute {shlex.quote(source)} 0")

def trigger_play(name):
    """Zentraler Play-Einstiegspunkt. Gibt (ok, msg) zurück."""
    # MP3 suchen
    stem = sanitize(os.path.splitext(name)[0])
    path = os.path.join(MP3_FOLDER, stem + ".mp3")
    if not os.path.isfile(path):
        # Fallback: unsanitized, aber sicher
        safe_name = os.path.basename(name if name.endswith('.mp3') else name + '.mp3')
        p2 = _safe_mp3_path(safe_name)
        if p2 and os.path.isfile(p2):
            path = p2
            stem = os.path.basename(path)[:-4]
        else:
            return False, f"MP3 nicht gefunden: {name}"

    cfg = load_cfg()
    src = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    sc  = cfg.get("sounds", {}).get(stem, {})

    # Wenn GPIO-only → HTTP-Trigger blockieren
    if sc.get("trigger_type") == "gpio":
        return False, f"'{stem}' ist GPIO-only — kein HTTP-Trigger erlaubt"

    repeat = max(1, min(10, int(sc.get("repeat", 1))))
    threading.Thread(target=_play_thread, args=(path, src, repeat), daemon=True).start()
    return True, os.path.basename(path)

# ── Terminal-State ────────────────────────────────────────────────────────────
_term_cwd  = ["/root"]
_term_lock = threading.Lock()

# ── Startup ──────────────────────────────────────────────────────────────────
# Default-Config erstellen falls nicht vorhanden
_ensure_default_config()

# Service-IP beim Start setzen
ensure_service_ip()

# Audio-Loopback sicherstellen (Line-In → Line-Out Passthrough)
ensure_loopback()

# Lautstärke beim Start aus Config wiederherstellen
def _restore_volume():
    cfg = load_cfg()
    a = cfg.get("audio", {})
    sink = a.get("sink", "@DEFAULT_SINK@")
    src  = a.get("source", "@DEFAULT_SOURCE@")
    vol_out = a.get("volume", 100)
    vol_in  = a.get("input_volume", 100)
    run(f"pactl set-sink-volume {shlex.quote(sink)} {vol_out}%")
    run(f"pactl set-source-volume {shlex.quote(src)} {vol_in}%")
    print(f"[AUDIO] Volume restored: out={vol_out}% in={vol_in}%", flush=True)

_restore_volume()

# Sleep/Suspend beim Start deaktivieren (headless, kein Display)
run("systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null")

# ── Trigger-Routen ────────────────────────────────────────────────────────────
@app.route('/cgi-bin/index.cgi')
def cgi_trigger():
    """
    WiFi-Button Format:
    GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=test1.mp3
    """
    if load_cfg().get("mode") == "offline":
        return 'ERROR: Offline-Modus – kein HTTP-Trigger', 403
    webif_pass  = request.args.get('webif-pass', '')
    spotrequest = request.args.get('spotrequest', '')
    if not spotrequest:
        return 'ERROR: missing spotrequest', 400
    # Optionaler Passwortschutz
    cfg = load_cfg()
    expected = str(cfg.get("trigger", {}).get("webif_pass", "1"))
    if webif_pass != expected:
        return 'ERROR: unauthorized', 403
    ok, msg = trigger_play(spotrequest)
    return (f"OK:{msg}", 200) if ok else (f"ERROR:{msg}", 404)

@app.route('/play/<mp3name>')
def play_legacy(mp3name):
    if load_cfg().get("mode") == "offline":
        return jsonify({"ok": False, "msg": "Offline-Modus: kein HTTP-Trigger"}), 403
    ok, msg = trigger_play(mp3name)
    return jsonify({"ok": ok, "msg": msg}), (200 if ok else 404)

# ── API: Status ───────────────────────────────────────────────────────────────
@app.route('/api/status')
def api_status():
    cfg = load_cfg()
    net = cfg.get("network", {})
    hostname = cfg.get("hostname", DEFAULT_HOSTNAME)
    # SSH-Status
    ssh = run("systemctl is-active ssh 2>/dev/null || systemctl is-active sshd 2>/dev/null")
    # USB-Soundkarten erkennen
    usb_audio = run("lsusb 2>/dev/null | grep -i audio")
    # Loopback-Status
    loopback_active = _get_loopback_id() is not None
    # Config ohne sensible Daten (auth) ans Frontend geben
    safe_cfg = {k: v for k, v in cfg.items() if k != "auth"}
    return jsonify({
        "setup_done":    True,
        "service_ip":    SERVICE_IP,
        "hostname":      hostname,
        "static_ip":     net.get("ip", ""),
        "static_iface":  net.get("interface", ""),
        "current_ips":   get_current_ips(),
        "mp3_count":     len(list_mp3s()),
        "ssh_active":    "active" in ssh["out"],
        "mode":          cfg.get("mode", "online"),
        "config":        safe_cfg,
        "board":         BOARD_INFO,
        "usb_audio":     bool(usb_audio["ok"] and usb_audio["out"]),
        "gpio_pins":     GPIO_PINS,
        "loopback_active": loopback_active,
        "audio_aliases": {name: _audio_alias(name) for name in
                          detect_sources() + _detect_sinks()},
    })

# ── API: Netzwerk ─────────────────────────────────────────────────────────────
@app.route('/api/network/interfaces')
def api_interfaces():
    ifaces = get_interfaces()
    # Bei nur einem Interface: automatisch in Config speichern
    if len(ifaces) == 1:
        cfg = load_cfg()
        if not cfg.get("network", {}).get("interface"):
            cfg.setdefault("network", {})["interface"] = ifaces[0]
            save_cfg(cfg)
    return jsonify(ifaces)

@app.route('/api/network/validate', methods=['POST'])
def api_net_validate():
    d   = request.json
    ip  = d.get("ip", "")
    gw  = d.get("gateway", "")
    dns = d.get("dns", "")
    errors = []
    if not valid_ip(ip):           errors.append("IP-Adresse ungültig")
    if not valid_ip(gw):           errors.append("Gateway ungültig")
    if dns and not valid_ip(dns):  errors.append("DNS-Server ungültig")
    if ip == SERVICE_IP:            errors.append(f"{SERVICE_IP} ist reserviert")
    return jsonify({"ok": not errors, "errors": errors})

@app.route('/api/network/apply', methods=['POST'])
def api_net_apply():
    d       = request.json
    iface   = d.get("interface", "eth0")
    ip      = d.get("ip", "")
    mask    = d.get("mask", "255.255.255.0")
    gateway = d.get("gateway", "")
    dns     = d.get("dns", "8.8.8.8")

    # Interface-Name absichern (Dateiname + Shell-Argument)
    if not re.match(r'^[a-zA-Z0-9_:-]+$', iface):
        return jsonify({"ok": False, "errors": ["Ungültiges Interface"]}), 400
    # IP-Adressen serverseitig validieren
    if not valid_ip(ip) or not valid_ip(gateway):
        return jsonify({"ok": False, "errors": ["Ungültige IP oder Gateway"]}), 400
    try:
        prefix = sum(bin(int(x)).count("1") for x in mask.split("."))
    except Exception:
        prefix = 24

    errors = []

    # ── Prüfen ob NetworkManager läuft ───────────────────────────────
    nm_active = run("systemctl is-active NetworkManager 2>/dev/null")["ok"]

    if nm_active:
        # NetworkManager Connection erstellen/aktualisieren
        nm_dir = "/etc/NetworkManager/system-connections"
        nm_file = os.path.join(nm_dir, f"{iface}.nmconnection")

        try:
            os.makedirs(nm_dir, exist_ok=True)
            # Alte unmanaged-Config entfernen falls vorhanden
            unmanaged_conf = "/etc/NetworkManager/conf.d/99-radxa-unmanaged.conf"
            if os.path.exists(unmanaged_conf):
                os.remove(unmanaged_conf)

            # NM Connection mit statischer IP + Service-IP
            nm_conn = f"""[connection]
id={iface}
type=ethernet
interface-name={iface}
autoconnect=true

[ipv4]
method=manual
address1={ip}/{prefix},{gateway}
address2={SERVICE_IP}/{SERVICE_MASK}
dns={dns};
ignore-auto-dns=true

[ipv6]
method=ignore
"""
            with open(nm_file, "w") as f:
                f.write(nm_conn)
            os.chmod(nm_file, 0o600)

            # Connection neu laden und aktivieren
            run("nmcli connection reload 2>/dev/null")
            run(f"nmcli connection up {iface} 2>/dev/null")
        except Exception as e:
            errors.append(f"NetworkManager Config fehlgeschlagen: {e}")
    else:
        # Kein NetworkManager – dhcpcd oder interfaces.d verwenden
        if run("systemctl is-active dhcpcd 2>/dev/null")["ok"]:
            # dhcpcd.conf aktualisieren
            try:
                dhcpcd_conf = "/etc/dhcpcd.conf"
                backup = f"{dhcpcd_conf}.bak.{int(time.time())}"
                if os.path.exists(dhcpcd_conf):
                    run(f"cp {dhcpcd_conf} {backup}")

                # Existierende eth0-Config entfernen
                with open(dhcpcd_conf) as f:
                    lines = f.readlines()
                new_lines = []
                skip = False
                for line in lines:
                    if line.strip().startswith("interface eth0"):
                        skip = True
                    elif skip and line.strip() and not line.strip().startswith("#"):
                        if line.startswith(" ") or line.startswith("\t") or line.strip().startswith("static"):
                            continue
                        skip = False
                    if not skip:
                        new_lines.append(line)

                with open(dhcpcd_conf, "w") as f:
                    f.writelines(new_lines)
                    f.write(f"\n# Radxa Audio — statische IP\n")
                    f.write(f"interface {iface}\n")
                    f.write(f"    static ip_address={ip}/{prefix}\n")
                    f.write(f"    static routers={gateway}\n")
                    f.write(f"    static domain_name_servers={dns}\n")
                    f.write(f"\n# Fallback auf DHCP\n")
                    f.write(f"fallback default\n")
            except Exception as e:
                errors.append(f"dhcpcd Config fehlgeschlagen: {e}")
        else:
            # Fallback: interfaces.d (klassisches ifupdown)
            try:
                iface_dir = "/etc/network/interfaces.d"
                os.makedirs(iface_dir, exist_ok=True)

                for suffix in ("", "-static", "-service"):
                    old = os.path.join(iface_dir, f"{iface}{suffix}")
                    if os.path.exists(old):
                        os.remove(old)

                cfg_main = (
                    f"# Radxa Audio — statische IP\n"
                    f"auto {iface}\n"
                    f"iface {iface} inet static\n"
                    f"    address {ip}/{prefix}\n"
                    f"    gateway {gateway}\n"
                    f"    dns-nameservers {dns}\n"
                )
                with open(os.path.join(iface_dir, f"{iface}-static"), "w") as f:
                    f.write(cfg_main)

                cfg_service = (
                    f"# Service-IP Radxa Audio — NICHT ENTFERNEN\n"
                    f"auto {iface}:service\n"
                    f"iface {iface}:service inet static\n"
                    f"    address {SERVICE_IP}/{SERVICE_MASK}\n"
                )
                with open(os.path.join(iface_dir, f"{iface}-service"), "w") as f:
                    f.write(cfg_service)
            except Exception as e:
                errors.append(f"interfaces.d Config fehlgeschlagen: {e}")

    # ── Sofort anwenden ───────────────────────────────────────────────
    run(f"ip addr add {shlex.quote(ip)}/{prefix} dev {shlex.quote(iface)} 2>/dev/null")
    run(f"ip addr add {SERVICE_IP}/{SERVICE_MASK} dev {shlex.quote(iface)} label {shlex.quote(iface)}:service 2>/dev/null")
    run("ip route del default 2>/dev/null")
    run(f"ip route add default via {shlex.quote(gateway)} dev {shlex.quote(iface)} 2>/dev/null")
    try:
        with open("/etc/resolv.conf", "w") as f:
            f.write(f"nameserver {dns}\n")
    except Exception:
        errors.append("DNS konnte nicht gesetzt werden")

    # ── Config speichern ──────────────────────────────────────────────
    cfg = load_cfg()
    cfg["network"] = {
        "interface": iface,
        "ip":        ip,
        "mask":      mask,
        "gateway":   gateway,
        "dns":       dns,
    }
    save_cfg(cfg)
    return jsonify({"ok": not errors, "errors": errors, "service_ip": SERVICE_IP})

@app.route('/api/network/ping', methods=['POST'])
def api_ping():
    target = request.json.get("target", "8.8.8.8")
    if not valid_ip(target):
        return jsonify({"ok": False, "msg": "Ungültiges Ziel"}), 400
    r = run(f"ping -c 2 -W 2 {target}")
    return jsonify({"ok": r["ok"], "msg": r["out"] or r["err"]})

# ── API: Audio ────────────────────────────────────────────────────────────────
def detect_cards():
    """Returns list of {name, profiles, active_profile} for all PulseAudio cards."""
    out = run("pactl list cards 2>/dev/null")["out"]
    cards = []
    cur = None
    in_profiles = False
    for line in out.splitlines():
        if line.startswith("Card #"):
            if cur and cur["name"]:
                cards.append(cur)
            cur = {"name": "", "profiles": [], "active_profile": ""}
            in_profiles = False
        elif cur is not None:
            s = line.strip()
            if s.startswith("Name:"):
                cur["name"] = s[5:].strip()
            elif s == "Profiles:":
                in_profiles = True
            elif s.startswith("Active Profile:"):
                cur["active_profile"] = s[15:].strip()
                in_profiles = False
            elif s.startswith(("Ports:", "Properties:", "Formats:")):
                in_profiles = False
            elif in_profiles and ": " in s:
                # Profile format: "output:analog-stereo: Description (sinks: ...)"
                # Split on ": " to get full profile name before description
                parts = s.split(": ", 1)
                pname = parts[0].strip()
                if pname:
                    cur["profiles"].append(pname)
    if cur and cur["name"]:
        cards.append(cur)
    return cards

@app.route('/api/audio/cards')
def api_cards():
    return jsonify(detect_cards())

@app.route('/api/audio/card-profile', methods=['POST'])
def api_card_profile():
    d = request.json
    card = d.get("card", "")
    profile = d.get("profile", "")
    # Validate: no shell special chars
    if not re.match(r'^[\w@.:+-]+$', card) or not re.match(r'^[\w@.:+/-]+$', profile):
        return jsonify({"ok": False, "msg": "Ungültiger Wert"}), 400
    r = run(f"pactl set-card-profile {shlex.quote(card)} {shlex.quote(profile)}")
    return jsonify({"ok": r["ok"], "msg": r["err"] if not r["ok"] else "Profil gesetzt"})

@app.route('/api/audio/sources')
def api_sources():
    sources = detect_sources()
    if len(sources) == 1:
        cfg = load_cfg()
        if not cfg.get("audio", {}).get("source"):
            cfg.setdefault("audio", {})["source"] = sources[0]
            save_cfg(cfg)
    return jsonify([{"name": s, "alias": _audio_alias(s)} for s in sources])

@app.route('/api/audio/sinks')
def api_sinks():
    sinks = _detect_sinks()
    if len(sinks) == 1:
        cfg = load_cfg()
        if not cfg.get("audio", {}).get("sink"):
            cfg.setdefault("audio", {})["sink"] = sinks[0]
            save_cfg(cfg)
    return jsonify([{"name": s, "alias": _audio_alias(s)} for s in sinks])

@app.route('/api/audio/loopback', methods=['GET', 'POST'])
def api_loopback():
    """GET: Status, POST: Loopback neu laden."""
    if request.method == 'POST':
        reload_loopback()
        active = _get_loopback_id() is not None
        return jsonify({"ok": active, "active": active})
    return jsonify({"active": _get_loopback_id() is not None})

@app.route('/api/audio/save', methods=['POST'])
def api_audio_save():
    d   = request.json
    cfg = load_cfg()
    try:
        vol_out = max(0, min(100, int(d.get("volume", 80))))
        vol_in  = max(0, min(100, int(d.get("input_volume", 80))))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "msg": "Ungültige Lautstärke"}), 400
    src = d.get("source", "@DEFAULT_SOURCE@")
    sink = d.get("sink", cfg.get("audio", {}).get("sink", "@DEFAULT_SINK@"))
    if not _valid_pa_name(src):
        return jsonify({"ok": False, "msg": "Ungültige Quelle"}), 400
    if not _valid_pa_name(sink):
        return jsonify({"ok": False, "msg": "Ungültige Senke"}), 400
    old_src = cfg.get("audio", {}).get("source")
    old_sink = cfg.get("audio", {}).get("sink")
    cfg["audio"] = {
        "source":       src,
        "sink":         sink,
        "volume":       vol_out,
        "input_volume": vol_in,
    }
    save_cfg(cfg)
    run(f"pactl set-sink-volume {shlex.quote(sink)} {vol_out}%")
    run(f"pactl set-source-volume {shlex.quote(src)} {vol_in}%")
    # Loopback neu laden wenn Source oder Sink geändert
    if src != old_src or sink != old_sink:
        reload_loopback()
    return jsonify({"ok": True})

def _valid_pa_name(name):
    """PulseAudio-Namen dürfen nur Wort-Zeichen, @, . : + - enthalten."""
    return bool(name) and bool(re.match(r'^[\w@.:+\-]+$', name))

@app.route('/api/audio/mute', methods=['POST'])
def api_mute():
    d = request.json
    src = d.get('source', '@DEFAULT_SOURCE@')
    if not _valid_pa_name(src):
        return jsonify({"ok": False, "msg": "Ungültige Quelle"}), 400
    run(f"pactl set-source-mute {shlex.quote(src)} "
        f"{'1' if d.get('mute') else '0'}")
    return jsonify({"ok": True})

@app.route('/api/audio/test', methods=['POST'])
def api_audio_test():
    cfg  = load_cfg()
    src  = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    mp3s = list_mp3s()
    if not mp3s:
        return jsonify({"ok": False, "msg": "Keine MP3s vorhanden"})
    path = os.path.join(MP3_FOLDER, mp3s[0]["name"])
    threading.Thread(target=_play_thread, args=(path, src), daemon=True).start()
    return jsonify({"ok": True, "playing": mp3s[0]["name"]})

# ── API: Trigger-Config ───────────────────────────────────────────────────────
@app.route('/api/trigger/config', methods=['POST'])
def api_trigger_config():
    """Speichert webif-pass und globale Trigger-Einstellungen."""
    d   = request.json
    cfg = load_cfg()
    cfg["trigger"] = {
        "webif_pass": d.get("webif_pass", "1"),
    }
    save_cfg(cfg)
    return jsonify({"ok": True})

# ── API: MP3s ─────────────────────────────────────────────────────────────────
@app.route('/api/mp3s')
def api_mp3s():
    return jsonify(list_mp3s())

@app.route('/api/mp3s/play', methods=['POST'])
def api_mp3_play():
    name = request.json.get("name", "")
    path = _safe_mp3_path(name)
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "msg": "nicht gefunden"}), 404
    cfg    = load_cfg()
    src    = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    stem   = os.path.basename(path)[:-4]
    repeat = max(1, min(10, int(cfg.get("sounds", {}).get(stem, {}).get("repeat", 1))))
    threading.Thread(target=_play_thread, args=(path, src, repeat), daemon=True).start()
    return jsonify({"ok": True})

@app.route('/api/mp3s/delete', methods=['POST'])
def api_mp3_delete():
    name = request.json.get("name", "")
    path = _safe_mp3_path(name)
    if not path or not os.path.isfile(path):
        return jsonify({"ok": False, "msg": "nicht gefunden"}), 404
    stem = os.path.basename(path)[:-4]
    os.remove(path)
    # Sound-Config bereinigen
    cfg = load_cfg()
    cfg.get("sounds", {}).pop(stem, None)
    save_cfg(cfg)
    return jsonify({"ok": True})

@app.route('/api/mp3s/rename', methods=['POST'])
def api_mp3_rename():
    old     = request.json.get("old", "")
    new_san = sanitize(request.json.get("new", "")) + ".mp3"
    old_p   = _safe_mp3_path(old)
    new_p   = _safe_mp3_path(new_san)
    if not old_p or not os.path.isfile(old_p):
        return jsonify({"ok": False, "msg": "nicht gefunden"}), 404
    if not new_p:
        return jsonify({"ok": False, "msg": "Ungültiger Name"}), 400
    if os.path.exists(new_p):
        return jsonify({"ok": False, "msg": "Name bereits vergeben"}), 409
    os.rename(old_p, new_p)
    # Sound-Config mitumbenennen
    cfg    = load_cfg()
    sounds = cfg.get("sounds", {})
    old_stem = os.path.basename(old_p)[:-4]
    new_stem = new_san[:-4]
    if old_stem in sounds:
        sounds[new_stem] = sounds.pop(old_stem)
    save_cfg(cfg)
    return jsonify({"ok": True, "new_name": new_san})

@app.route('/api/mp3s/trigger', methods=['POST'])
def api_mp3_trigger():
    """Setzt Trigger-Typ (http/gpio) und ggf. GPIO-Pin für einen Sound."""
    d    = request.json
    stem = d.get("stem", "")
    ttype = d.get("trigger_type", "http")   # "http" | "gpio"
    pin   = d.get("gpio_pin", None)
    if not stem:
        return jsonify({"ok": False, "msg": "stem fehlt"}), 400
    cfg = load_cfg()
    # Offline-Modus: nur GPIO erlaubt
    if cfg.get("mode") == "offline":
        ttype = "gpio"
    if ttype == "gpio":
        try:
            if int(pin) not in GPIO_PINS:
                return jsonify({"ok": False, "msg": f"Ungültiger GPIO-Pin: {pin}"}), 400
        except (TypeError, ValueError):
            return jsonify({"ok": False, "msg": "GPIO-Pin muss eine Zahl sein"}), 400
    if "sounds" not in cfg:
        cfg["sounds"] = {}
    try:
        repeat = max(1, min(10, int(d.get("repeat", 1))))
    except (TypeError, ValueError):
        repeat = 1
    cfg["sounds"][stem] = {
        "trigger_type": ttype,
        "gpio_pin":     pin if ttype == "gpio" else None,
        "repeat":       repeat,
    }
    save_cfg(cfg)
    # GPIO-Script neu generieren
    _write_gpio_script(cfg)
    return jsonify({"ok": True})

# Max Dateigroesse fuer Uploads (50MB)
MAX_UPLOAD_SIZE = 50 * 1024 * 1024

@app.route('/api/upload', methods=['POST'])
def api_upload():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if 'file' not in request.files:
        return jsonify([{"ok": False, "error": "kein file"}]), 400

    # 1. Alle Uploads erst auf Disk sichern (Werkzeug-Streams nicht thread-safe)
    _name_lock = threading.Lock()
    jobs = []
    for f in request.files.getlist('file'):
        orig = f.filename or "audio"
        # Dateigroesse pruefen BEFORE speichern
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        if size > MAX_UPLOAD_SIZE:
            jobs.append({"orig": orig, "error": f"Datei zu gross ({size//1024}KB > 50MB)"})
            continue
        stem = sanitize(os.path.splitext(orig)[0]) or "audio"
        ext  = re.sub(r'[^a-zA-Z0-9.]', '', os.path.splitext(orig)[1].lower())
        tmp  = f"/tmp/_radxa_{stem}_{os.getpid()}_{len(jobs)}{ext}"
        f.save(tmp)
        # Ausgabe-Namen unter Lock reservieren → kein Namenskonflikt zwischen Threads
        with _name_lock:
            out_name = stem + ".mp3"
            out_path = os.path.join(MP3_FOLDER, out_name)
            c = 1
            while os.path.exists(out_path):
                out_name = f"{stem}_{c}.mp3"
                out_path = os.path.join(MP3_FOLDER, out_name)
                c += 1
            with open(out_path, 'wb') as _ph:
                _ph.write(b'\x00')  # 1-Byte Platzhalter reservieren
        jobs.append({"orig": orig, "tmp": tmp, "out_name": out_name, "out_path": out_path})

    # 2. Parallel konvertieren — max. 4 ffmpeg-Prozesse gleichzeitig
    def convert(job):
        cmd = (f"ffmpeg -y -i {shlex.quote(job['tmp'])} "
               f"-ar 44100 -ac 1 -b:a 128k {shlex.quote(job['out_path'])} 2>&1")
        r = run(cmd, timeout=120)
        try: os.remove(job["tmp"])
        except Exception: pass
        if r["ok"] and os.path.isfile(job["out_path"]) and os.path.getsize(job["out_path"]) > 0:
            return {"ok": True, "original": job["orig"],
                    "saved_as": job["out_name"],
                    "size_kb": os.path.getsize(job["out_path"]) // 1024}
        else:
            try: os.remove(job["out_path"])
            except Exception: pass
            return {"ok": False, "original": job["orig"],
                    "error": (r["out"] or r["err"])[:300]}

    results_map = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_to_job = {pool.submit(convert, j): j for j in jobs}
        for future in as_completed(future_to_job):
            job = future_to_job[future]
            try:
                results_map[job["orig"]] = future.result()
            except Exception as e:
                results_map[job["orig"]] = {"ok": False, "original": job["orig"], "error": str(e)}

    # Reihenfolge wie hochgeladen erhalten
    return jsonify([results_map[j["orig"]] for j in jobs])

# ── API: GPIO ─────────────────────────────────────────────────────────────────
@app.route('/api/gpio/save', methods=['POST'])
def api_gpio_save():
    """Speichert GPIO-Mappings und generiert den Daemon-Script."""
    gpio = request.json.get("gpio", {})  # {pin: stem}
    cfg  = load_cfg()

    # sounds-Config updaten
    if "sounds" not in cfg:
        cfg["sounds"] = {}

    # Stems die neu zugewiesen werden
    new_gpio_stems = {stem for stem in gpio.values() if stem and stem != "— keiner —"}

    # Nur GPIO-Sounds resetten die nicht mehr zugewiesen werden
    for stem, sc in cfg["sounds"].items():
        if sc.get("trigger_type") == "gpio" and stem not in new_gpio_stems:
            sc["trigger_type"] = "http"
            sc["gpio_pin"] = None

    # Neue GPIO-Mappings setzen
    for pin, stem in gpio.items():
        if stem and stem != "— keiner —":
            try:
                pin_int = int(pin)
            except (TypeError, ValueError):
                continue
            if pin_int not in GPIO_PINS:
                continue
            cfg["sounds"].setdefault(stem, {})
            cfg["sounds"][stem]["trigger_type"] = "gpio"
            cfg["sounds"][stem]["gpio_pin"] = pin_int

    save_cfg(cfg)
    _write_gpio_script(cfg)
    return jsonify({"ok": True})

def _write_gpio_script(cfg):
    gpio_map = {}
    for stem, sc in cfg.get("sounds", {}).items():
        if sc.get("trigger_type") == "gpio" and sc.get("gpio_pin") is not None:
            gpio_map[sc["gpio_pin"]] = {
                "stem":   stem,
                "repeat": max(1, min(10, int(sc.get("repeat", 1)))),
            }
    if not gpio_map:
        run("systemctl stop radxa-audio-gpio 2>/dev/null")
        return
    src = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    # Uses python3-gpiod (works on Radxa ROCK 3A, 4C+ and all libgpiod boards)
    # Supports gpiod 2.x API (Debian Bookworm+) with automatic fallback to gpiod 1.x
    script = f"""#!/usr/bin/env python3
# GPIO-Daemon – auto-generiert von Radxa Audio Konfigurator
# Kompatibel mit Radxa ROCK 3A, 4C+ und anderen Boards (gpiod 1.x + 2.x)
import subprocess, time, os, sys, threading

MP3_FOLDER  = {repr(str(MP3_FOLDER))}
LINE_SOURCE = {repr(src)}
GPIO_MAP    = {repr(gpio_map)}
CHIP        = {repr(GPIOCHIP)}
DEBOUNCE    = 0.2

def pactl_available():
    """Prueft ob PulseAudio erreichbar ist."""
    try:
        r = subprocess.run(['pactl', 'info'], capture_output=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False

def play(entry):
    stem   = entry['stem']
    repeat = entry.get('repeat', 1)
    path   = os.path.join(MP3_FOLDER, stem + '.mp3')
    if not os.path.isfile(path):
        print(f"[GPIO] File not found: {path}", file=sys.stderr)
        return
    # PulseAudio verfuegbarkeit pruefen
    if not pactl_available():
        print(f"[GPIO] PulseAudio nicht erreichbar, ueberspringe", file=sys.stderr)
        return
    try:
        subprocess.run(['pactl', 'set-source-mute', LINE_SOURCE, '1'], timeout=2)
    except Exception as e:
        print(f"[GPIO] Mute failed: {e}", file=sys.stderr)
    for i in range(repeat):
        try:
            r = subprocess.run(['mpg123', '-q', path], timeout=300)
        except subprocess.TimeoutExpired:
            print(f"[GPIO] Playback timeout", file=sys.stderr)
        except Exception as e:
            print(f"[GPIO] Playback error: {e}", file=sys.stderr)
    try:
        subprocess.run(['pactl', 'set-source-mute', LINE_SOURCE, '0'], timeout=2)
    except Exception as e:
        print(f"[GPIO] Unmute failed: {e}", file=sys.stderr)

_last = {{}}
_lock = threading.Lock()

def _debounce(pin):
    now = time.monotonic()
    with _lock:
        if now - _last.get(pin, 0) < DEBOUNCE:
            return False
        _last[pin] = now
    return True

try:
    import gpiod
except ImportError:
    print('python3-gpiod fehlt: sudo apt install python3-gpiod', file=sys.stderr)
    sys.exit(1)

if hasattr(gpiod, 'request_lines'):
    # gpiod >= 2.0
    from gpiod.line import Direction, Bias, Edge
    from datetime import timedelta
    with gpiod.request_lines(
        CHIP,
        consumer='radxa-audio',
        config={{
            tuple(GPIO_MAP.keys()): gpiod.LineSettings(
                direction=Direction.INPUT,
                bias=Bias.PULL_UP,
                edge_detection=Edge.FALLING,
                debounce_period=timedelta(milliseconds=int(DEBOUNCE * 1000)),
            )
        }}
    ) as req:
        while True:
            if req.wait_edge_events(timeout=timedelta(seconds=1)):
                for ev in req.read_edge_events():
                    entry = GPIO_MAP.get(ev.line_offset)
                    if entry and _debounce(ev.line_offset):
                        threading.Thread(target=play, args=(entry,), daemon=True).start()
else:
    # gpiod 1.x
    chip  = gpiod.Chip(CHIP)
    lines = chip.get_lines(list(GPIO_MAP.keys()))
    lines.request(
        consumer='radxa-audio',
        type=gpiod.LINE_REQ_EV_FALLING_EDGE,
        flags=gpiod.LINE_REQ_FLAG_BIAS_PULL_UP,
    )
    try:
        while True:
            ev_bulk = lines.event_wait(sec=1)
            if ev_bulk:
                for line in ev_bulk:
                    ev = line.event_read()
                    if ev.type == gpiod.LineEvent.FALLING_EDGE:
                        pin   = line.offset()
                        entry = GPIO_MAP.get(pin)
                        if entry and _debounce(pin):
                            threading.Thread(target=play, args=(entry,), daemon=True).start()
    finally:
        lines.release()
"""
    with open("/usr/local/bin/radxa_gpio.py", "w") as f:
        f.write(script)
    os.chmod("/usr/local/bin/radxa_gpio.py", 0o755)
    run("systemctl restart radxa-audio-gpio 2>/dev/null")

# ── API: Hostname ────────────────────────────────────────────────────────────
@app.route('/api/hostname', methods=['GET', 'POST'])
def api_hostname():
    if request.method == 'GET':
        return jsonify({"hostname": get_hostname()})
    d = request.json or {}
    new_hostname = re.sub(r'[^a-zA-Z0-9\-]', '', d.get("hostname", "").strip().lower())
    if not new_hostname or len(new_hostname) < 2:
        return jsonify({"ok": False, "msg": "Hostname zu kurz (min. 2 Zeichen)"}), 400
    if len(new_hostname) > 63:
        return jsonify({"ok": False, "msg": "Hostname zu lang (max. 63 Zeichen)"}), 400
    cfg = load_cfg()
    cfg["hostname"] = new_hostname
    save_cfg(cfg)
    # System-Hostname setzen
    run(f"hostnamectl set-hostname {shlex.quote(new_hostname)} 2>/dev/null")
    # /etc/hosts aktualisieren
    run(f"sed -i 's/127\\.0\\.1\\.1.*/127.0.1.1\\t{new_hostname}/' /etc/hosts")
    # Avahi neustarten für mDNS
    run("systemctl restart avahi-daemon 2>/dev/null")
    return jsonify({"ok": True, "hostname": new_hostname})

# ── API: Terminal ─────────────────────────────────────────────────────────────
_TERM_BLOCKED = re.compile(
    r'(rm\s+-rf\s+/|mkfs\b|dd\s+if=|:\(\)\s*\{|fork\s*bomb'
    r'|>\s*/dev/sd|>\s*/dev/nvme|shutdown\b|halt\b|init\s+0)', re.IGNORECASE
)

@app.route('/api/terminal/exec', methods=['POST'])
def api_terminal_exec():
    cmd = (request.json or {}).get("cmd", "").strip()
    if not cmd:
        return jsonify({"ok": True, "out": "", "cwd": _term_cwd[0]})
    # Gefaehrliche Befehle blockieren
    if _TERM_BLOCKED.search(cmd):
        return jsonify({"ok": False, "out": "Befehl blockiert (gefaehrlich)", "cwd": _term_cwd[0]})
    with _term_lock:
        cwd = _term_cwd[0]
        # cd separat behandeln, damit es persistent wirkt
        if re.match(r'^cd(\s|$)', cmd):
            target = cmd[2:].strip() or "/root"
            target = target.replace("~", "/root")
            if not os.path.isabs(target):
                target = os.path.normpath(os.path.join(cwd, target))
            if os.path.isdir(target):
                _term_cwd[0] = target
                return jsonify({"ok": True, "out": "", "cwd": target})
            return jsonify({"ok": True, "out": f"cd: {target}: No such file or directory", "cwd": cwd})
        try:
            r = subprocess.run(
                cmd, shell=True, cwd=cwd,
                capture_output=True, text=True, timeout=30
            )
            out = (r.stdout + r.stderr).rstrip()
        except subprocess.TimeoutExpired:
            out = "Timeout (30 s)"
        return jsonify({"ok": True, "out": out, "cwd": _term_cwd[0]})

# ── API: Health Check ────────────────────────────────────────────────────────
@app.route('/api/health')
def api_health():
    # CPU-Temperatur
    temp = "?"
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp = f"{int(f.read().strip()) / 1000:.1f}"
    except Exception:
        pass
    # RAM
    mem = run("free -m | awk '/Mem:/{print $2,$3,$4}'")["out"].split()
    ram_total = int(mem[0]) if len(mem) >= 1 else 0
    ram_used  = int(mem[1]) if len(mem) >= 2 else 0
    # Disk
    disk = run("df -m / | awk 'NR==2{print $2,$3,$5}'")["out"].split()
    disk_total  = int(disk[0]) if len(disk) >= 1 else 0
    disk_used   = int(disk[1]) if len(disk) >= 2 else 0
    disk_pct    = disk[2] if len(disk) >= 3 else "?"
    # Uptime
    uptime = run("uptime -p 2>/dev/null || uptime")["out"]
    # Services
    web_ok  = "active" in run("systemctl is-active radxa-audio-web 2>/dev/null")["out"]
    gpio_ok = "active" in run("systemctl is-active radxa-audio-gpio 2>/dev/null")["out"]
    return jsonify({
        "cpu_temp":   temp,
        "ram_total":  ram_total,
        "ram_used":   ram_used,
        "disk_total": disk_total,
        "disk_used":  disk_used,
        "disk_pct":   disk_pct,
        "uptime":     uptime,
        "web_service":  web_ok,
        "gpio_service": gpio_ok,
    })

# ── API: Sound Preview (Browser-Streaming) ───────────────────────────────────
@app.route('/api/mp3s/stream/<name>')
def api_mp3_stream(name):
    path = _safe_mp3_path(name if name.endswith('.mp3') else name + '.mp3')
    if not path or not os.path.isfile(path):
        return "Not found", 404
    return send_file(path, mimetype='audio/mpeg')

# ── API: Live Audio Preview (Line-In Aufnahme) ──────────────────────────────
@app.route('/api/audio/preview', methods=['POST'])
def api_audio_preview():
    """Nimmt 5 Sekunden vom Line-In auf und gibt WAV zurueck."""
    cfg = load_cfg()
    src = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    tmp = f"/tmp/_radxa_preview_{os.getpid()}.wav"
    r = run(f"parecord --channels=1 --rate=22050 --format=s16le "
            f"-d {shlex.quote(src)} --file-format=wav {shlex.quote(tmp)} &"
            f" RPID=$!; sleep 5; kill $RPID 2>/dev/null; wait $RPID 2>/dev/null",
            timeout=15)
    if os.path.isfile(tmp) and os.path.getsize(tmp) > 100:
        resp = send_file(tmp, mimetype='audio/wav')
        threading.Thread(target=lambda: (time.sleep(2), os.remove(tmp)),
                         daemon=True).start()
        return resp
    return jsonify({"ok": False, "msg": "Aufnahme fehlgeschlagen"}), 500

# ── API: Reboot / Restart ───────────────────────────────────────────────────
@app.route('/api/system/restart-service', methods=['POST'])
def api_restart_service():
    run("systemctl restart radxa-audio-web 2>/dev/null")
    return jsonify({"ok": True, "msg": "Service wird neu gestartet..."})

@app.route('/api/system/reboot', methods=['POST'])
def api_reboot():
    threading.Thread(target=lambda: (time.sleep(1), os.system("reboot")),
                     daemon=True).start()
    return jsonify({"ok": True, "msg": "Neustart in 1 Sekunde..."})

# ── API: Backup / Restore ───────────────────────────────────────────────────
@app.route('/api/backup/export')
def api_backup_export():
    """Exportiert Config + alle MP3s als ZIP."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Config
        if os.path.isfile(CONFIG_FILE):
            zf.write(CONFIG_FILE, "config.json")
        # Sounds
        for f in os.listdir(MP3_FOLDER):
            fp = os.path.join(MP3_FOLDER, f)
            if os.path.isfile(fp):
                zf.write(fp, f"sounds/{f}")
    buf.seek(0)
    return send_file(buf, mimetype='application/zip',
                     as_attachment=True, download_name='radxa_backup.zip')

@app.route('/api/backup/import', methods=['POST'])
def api_backup_import():
    """Importiert Config + Sounds aus ZIP."""
    if 'file' not in request.files:
        return jsonify({"ok": False, "msg": "Keine Datei"}), 400
    f = request.files['file']
    try:
        with zipfile.ZipFile(f.stream, 'r') as zf:
            names = zf.namelist()
            # Config importieren
            if "config.json" in names:
                cfg_data = json.loads(zf.read("config.json"))
                save_cfg(cfg_data)
            # Sounds importieren
            imported = 0
            for name in names:
                if name.startswith("sounds/") and name.endswith(".mp3"):
                    basename = os.path.basename(name)
                    if basename:
                        target = os.path.join(MP3_FOLDER, basename)
                        with open(target, "wb") as out:
                            out.write(zf.read(name))
                        imported += 1
        return jsonify({"ok": True, "msg": f"Config + {imported} Sounds importiert"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Import fehlgeschlagen: {e}"}), 400

# ── API: Scheduled Triggers ─────────────────────────────────────────────────
# Verwende APScheduler statt threading.Timer fuer robuste 24/7-Schedules
_sched_lock = threading.Lock()
_sched_jobstore = {}  # {sched_id: next_run_time}

def _load_schedules():
    return load_cfg().get("schedules", [])

def _run_scheduled(sched_id):
    """Fuehrt geplanten Trigger aus."""
    schedules = _load_schedules()
    for s in schedules:
        if s.get("id") == sched_id and s.get("enabled", True):
            print(f"[SCHEDULE] Triggering: {s['sound']} (id={sched_id})", flush=True)
            trigger_play(s["sound"])
            break

def _schedule_all():
    """Initialisiert alle Schedules beim Start."""
    schedules = _load_schedules()
    with _sched_lock:
        _sched_jobstore.clear()
        for s in schedules:
            if s.get("enabled", True) and s.get("id"):
                _sched_jobstore[s["id"]] = None
    print(f"[SCHEDULE] Loaded {len(schedules)} schedules", flush=True)

def _get_cron_delay(time_s, days):
    """Berechnet Sekunden bis zum naechsten Termin."""
    import datetime
    now = datetime.datetime.now()
    h, m = map(int, time_s.split(":"))
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    while target.weekday() not in (days or [0,1,2,3,4,5,6]):
        target += datetime.timedelta(days=1)
    return (target - now).total_seconds(), target

# Hintergrund-Thread fuer Schedules (robuster als threading.Timer)
def _schedule_runner():
    """Laueft im Hintergrund und fuehrt Schedules aus."""
    import datetime
    last_check = None
    while True:
        time.sleep(30)  # Alle 30s pruefen
        now = datetime.datetime.now()
        if last_check and now - last_check < datetime.timedelta(seconds=25):
            continue
        last_check = now
        schedules = _load_schedules()
        for s in schedules:
            if not s.get("enabled", True) or not s.get("id"):
                continue
            sched_id = s["id"]
            time_s = s.get("time", "")
            days = s.get("days", [0,1,2,3,4,5,6])
            if not time_s:
                continue
            delay, target = _get_cron_delay(time_s, days)
            # Wenn Zielzeit erreicht (Toleranz 60s)
            if delay < 60:
                # Check ob schon ausgefuehrt in dieser Minute
                last_run = _sched_jobstore.get(sched_id)
                if last_run and abs((target - last_run).total_seconds()) < 120:
                    continue
                print(f"[SCHEDULE] Running: {s['sound']} at {target}", flush=True)
                _run_scheduled(sched_id)
                _sched_jobstore[sched_id] = target

# Schedule-Runner als Daemon-Thread starten
_schedule_thread = threading.Thread(target=_schedule_runner, daemon=True)
_schedule_thread.start()

@app.route('/api/schedules', methods=['GET', 'POST'])
def api_schedules():
    if request.method == 'GET':
        return jsonify(_load_schedules())
    d = request.json or {}
    sound   = d.get("sound", "")
    time_s  = d.get("time", "")
    days    = d.get("days", [0,1,2,3,4,5,6])
    enabled = d.get("enabled", True)
    if not sound or not re.match(r'^\d{1,2}:\d{2}$', time_s):
        return jsonify({"ok": False, "msg": "Sound und Zeit (HH:MM) erforderlich"}), 400
    cfg = load_cfg()
    schedules = cfg.get("schedules", [])
    sid = d.get("id") or secrets.token_hex(4)
    # Update oder neu
    found = False
    for s in schedules:
        if s["id"] == sid:
            s.update({"sound": sound, "time": time_s, "days": days, "enabled": enabled})
            found = True
            break
    if not found:
        schedules.append({"id": sid, "sound": sound, "time": time_s, "days": days, "enabled": enabled})
    cfg["schedules"] = schedules
    save_cfg(cfg)
    return jsonify({"ok": True, "id": sid})

@app.route('/api/schedules/delete', methods=['POST'])
def api_schedules_delete():
    sid = (request.json or {}).get("id", "")
    cfg = load_cfg()
    cfg["schedules"] = [s for s in cfg.get("schedules", []) if s.get("id") != sid]
    save_cfg(cfg)
    with _sched_lock:
        _sched_jobstore.pop(sid, None)
    return jsonify({"ok": True})

# Schedules beim Start laden
_schedule_all()

# ── Tmp-Cleanup beim Start ──────────────────────────────────────────────────
for _tmp in globmod.glob("/tmp/_radxa_*"):
    try:
        os.remove(_tmp)
    except Exception:
        pass

# ── Frontend ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    cfg = load_cfg()
    hostname = cfg.get("hostname", DEFAULT_HOSTNAME)
    return render_template('index.html',
                           service_ip=SERVICE_IP,
                           hostname=hostname,
                           mode=cfg.get("mode", "online"))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
