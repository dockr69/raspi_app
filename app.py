#!/usr/bin/env python3
"""
Radxa ROCK 3A – Audio Konfigurator
· CGI-Trigger:  GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=<n>.mp3
· Legacy:       GET /play/<n>
· Service-IP 10.0.0.10 immer fest, nie änderbar
· Hostname: textspeicher  →  textspeicher.local (mDNS)
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess, os, json, threading, re, secrets, shlex, time, glob as globmod, zipfile, io

app = Flask(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────────
SERVICE_IP      = "10.0.0.10"
SERVICE_MASK    = "24"
HOSTNAME        = "textspeicher"
CONFIG_FILE     = "/etc/radxa_audio/config.json"
MP3_FOLDER      = "/etc/radxa_audio/sounds"
SETUP_DONE_FILE = "/etc/radxa_audio/.setup_done"
BOARD_FILE      = "/etc/radxa_audio/board.json"

# ── Board-Erkennung (gesetzt vom install.sh oder automatisch erkannt) ────────
def _load_board_info():
    """Liest Board-Info aus board.json oder erkennt automatisch."""
    defaults = {
        "board": "generic",
        "board_name": "Unbekannt",
        "gpiochip": "/dev/gpiochip0",
        "gpio_pins": [4, 17, 18, 22, 23, 24, 25, 27],
        "default_user": "pi",
    }
    try:
        with open(BOARD_FILE) as f:
            info = json.load(f)
            # Merge mit defaults
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
        if "raspberry" in model.lower():
            if "pi 4" in model.lower():
                defaults["board"] = "rpi4"
                defaults["board_name"] = "Raspberry Pi 4"
            elif "pi 3" in model.lower():
                defaults["board"] = "rpi3"
                defaults["board_name"] = "Raspberry Pi 3B"
            else:
                defaults["board"] = "rpi"
                defaults["board_name"] = model
        elif "rock" in model.lower() or "radxa" in model.lower():
            defaults["board"] = "rock3a"
            defaults["board_name"] = model
        else:
            defaults["board_name"] = model
    except Exception:
        pass
    # GPIO-Chip: RPi 5 nutzt gpiochip4
    if os.path.exists("/dev/gpiochip4") and "rpi" in defaults["board"]:
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

# ── Secret Key (persistent, damit Sessions nach Neustart gültig bleiben) ──────
def _load_secret_key():
    if os.path.exists(SECRET_KEY_FILE):
        with open(SECRET_KEY_FILE) as f:
            k = f.read().strip()
            if k:
                return k
    k = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w') as f:
        f.write(k)
    os.chmod(SECRET_KEY_FILE, 0o600)
    return k

app.secret_key = _load_secret_key()

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

def load_cfg():
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_cfg(data):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
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
    return os.path.isfile(SETUP_DONE_FILE)

def mark_setup_done():
    with open(SETUP_DONE_FILE, "w") as f:
        f.write("1")

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
    with _play_lock:
        run(f"pactl set-source-mute {shlex.quote(source)} 1")
        for _ in range(repeat):
            run(f"mpg123 -q {shlex.quote(path)}", timeout=300)
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

# Service-IP beim Start setzen
ensure_service_ip()

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
    # SSH-Status
    ssh = run("systemctl is-active ssh 2>/dev/null || systemctl is-active sshd 2>/dev/null")
    # USB-Soundkarten erkennen
    usb_audio = run("lsusb 2>/dev/null | grep -i audio")
    return jsonify({
        "setup_done":    is_setup_done(),
        "service_ip":    SERVICE_IP,
        "hostname":      HOSTNAME,
        "static_ip":     net.get("ip", ""),
        "static_iface":  net.get("interface", ""),
        "current_ips":   get_current_ips(),
        "mp3_count":     len(list_mp3s()),
        "ssh_active":    "active" in ssh["out"],
        "mode":          cfg.get("mode", "online"),
        "config":        cfg,
        "board":         BOARD_INFO,
        "usb_audio":     bool(usb_audio["ok"] and usb_audio["out"]),
        "gpio_pins":     GPIO_PINS,
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

    # ── interfaces.d Config aufbauen ──────────────────────────────────
    try:
        iface_dir = "/etc/network/interfaces.d"

        # Alte Configs entfernen (clean slate)
        for suffix in ("", "-static", "-service"):
            old = os.path.join(iface_dir, f"{iface}{suffix}")
            if os.path.exists(old):
                os.remove(old)

        # Statische IP (kein DHCP)
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

        # Service-IP immer als Alias
        cfg_service = (
            f"# Service-IP Radxa Audio — NICHT ENTFERNEN\n"
            f"auto {iface}:service\n"
            f"iface {iface}:service inet static\n"
            f"    address {SERVICE_IP}/{SERVICE_MASK}\n"
        )
        with open(os.path.join(iface_dir, f"{iface}-service"), "w") as f:
            f.write(cfg_service)

    except PermissionError:
        errors.append("Root-Rechte fehlen für /etc/network")

    # ── Sofort anwenden ───────────────────────────────────────────────
    run(f"ip addr add {shlex.quote(ip)}/{prefix} dev {shlex.quote(iface)} 2>/dev/null")
    run(f"ip route add default via {shlex.quote(gateway)} dev {shlex.quote(iface)} 2>/dev/null")
    try:
        with open("/etc/resolv.conf", "w") as f:
            f.write(f"nameserver {dns}\n")
    except Exception:
        errors.append("DNS konnte nicht gesetzt werden")

    ensure_service_ip(iface)

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
    # Bei nur einer Quelle: automatisch in Config speichern
    if len(sources) == 1:
        cfg = load_cfg()
        if not cfg.get("audio", {}).get("source"):
            cfg.setdefault("audio", {})["source"] = sources[0]
            save_cfg(cfg)
    return jsonify(sources)

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
    if not _valid_pa_name(src):
        return jsonify({"ok": False, "msg": "Ungültige Quelle"}), 400
    cfg["audio"] = {
        "source":       src,
        "volume":       vol_out,
        "input_volume": vol_in,
    }
    save_cfg(cfg)
    run(f"pactl set-sink-volume @DEFAULT_SINK@ {vol_out}%")
    run(f"pactl set-source-volume {shlex.quote(src)} {vol_in}%")
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

def play(entry):
    stem   = entry['stem']
    repeat = entry.get('repeat', 1)
    path   = os.path.join(MP3_FOLDER, stem + '.mp3')
    if not os.path.isfile(path):
        return
    subprocess.run(['pactl', 'set-source-mute', LINE_SOURCE, '1'])
    for _ in range(repeat):
        subprocess.run(['mpg123', '-q', path])
    subprocess.run(['pactl', 'set-source-mute', LINE_SOURCE, '0'])

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

# ── API: Setup ────────────────────────────────────────────────────────────────
@app.route('/api/setup/finish', methods=['POST'])
def api_setup_finish():
    mark_setup_done()
    return jsonify({"ok": True})

@app.route('/api/setup/reset', methods=['POST'])
def api_setup_reset():
    if os.path.exists(SETUP_DONE_FILE):
        os.remove(SETUP_DONE_FILE)
    return jsonify({"ok": True})

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
_sched_lock = threading.Lock()
_sched_timers = {}

def _load_schedules():
    return load_cfg().get("schedules", [])

def _run_scheduled(sched_id):
    """Fuehrt geplanten Trigger aus und plant den naechsten."""
    schedules = _load_schedules()
    for s in schedules:
        if s.get("id") == sched_id and s.get("enabled", True):
            trigger_play(s["sound"])
            break
    _schedule_next(sched_id)

def _schedule_next(sched_id):
    """Plant den naechsten Lauf basierend auf der Konfiguration."""
    import datetime
    schedules = _load_schedules()
    sched = None
    for s in schedules:
        if s.get("id") == sched_id:
            sched = s
            break
    if not sched or not sched.get("enabled", True):
        return
    try:
        now = datetime.datetime.now()
        h, m = map(int, sched["time"].split(":"))
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        # Wochentag-Filter (0=Mo, 6=So)
        days = sched.get("days", [0,1,2,3,4,5,6])
        while target.weekday() not in days:
            target += datetime.timedelta(days=1)
        delay = (target - now).total_seconds()
        with _sched_lock:
            old = _sched_timers.pop(sched_id, None)
            if old:
                old.cancel()
            t = threading.Timer(delay, _run_scheduled, args=[sched_id])
            t.daemon = True
            t.start()
            _sched_timers[sched_id] = t
    except Exception:
        pass

def _init_schedules():
    for s in _load_schedules():
        if s.get("enabled", True):
            _schedule_next(s["id"])

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
    _schedule_next(sid)
    return jsonify({"ok": True, "id": sid})

@app.route('/api/schedules/delete', methods=['POST'])
def api_schedules_delete():
    sid = (request.json or {}).get("id", "")
    cfg = load_cfg()
    cfg["schedules"] = [s for s in cfg.get("schedules", []) if s.get("id") != sid]
    save_cfg(cfg)
    with _sched_lock:
        old = _sched_timers.pop(sid, None)
        if old:
            old.cancel()
    return jsonify({"ok": True})

# Schedules beim Start laden
_init_schedules()

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
    return render_template('index.html',
                           service_ip=SERVICE_IP,
                           hostname=HOSTNAME,
                           setup_done=str(is_setup_done()).lower(),
                           mode=cfg.get("mode", "online"))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
