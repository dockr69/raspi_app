#!/usr/bin/env python3
"""
Radxa ROCK 3A – Audio Konfigurator
· CGI-Trigger:  GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=<n>.mp3
· Legacy:       GET /play/<n>
· Service-IP 10.0.0.10 immer fest, nie änderbar
· Hostname: textspeicher  →  textspeicher.local (mDNS)
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import subprocess, os, json, threading, re, secrets

app = Flask(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────────
SERVICE_IP      = "10.0.0.10"
SERVICE_MASK    = "24"
HOSTNAME        = "textspeicher"
CONFIG_FILE     = "/etc/radxa_audio/config.json"
MP3_FOLDER      = "/etc/radxa_audio/sounds"
SETUP_DONE_FILE = "/etc/radxa_audio/.setup_done"
GPIO_PINS       = [4, 17, 18, 22, 23, 24, 25, 27]

SECRET_KEY_FILE  = "/etc/radxa_audio/.secret_key"
DEFAULT_USERNAME = "pi"

os.makedirs(MP3_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

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
def get_auth():
    """Liest Credentials aus Config; legt Defaults an falls nicht vorhanden."""
    cfg = load_cfg()
    auth = cfg.get("auth", {})
    if not auth.get("username") or not auth.get("password_hash"):
        # Erstes Start: zufälliges Passwort generieren und in den Logs ausgeben
        first_pw = secrets.token_urlsafe(12)
        auth = {
            "username":      DEFAULT_USERNAME,
            "password_hash": generate_password_hash(first_pw),
        }
        cfg["auth"] = auth
        save_cfg(cfg)
        print(f"[INIT] Erstes Start – Login: {DEFAULT_USERNAME} / Passwort: {first_pw}", flush=True)
        print("[INIT] Passwort nach dem ersten Login unter Einstellungen (🔑) ändern.", flush=True)
    return auth

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
        auth = get_auth()
        if username == auth['username'] and check_password_hash(auth['password_hash'], password):
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
    if not check_password_hash(auth['password_hash'], old_pw):
        return jsonify({"ok": False, "msg": "Aktuelles Passwort falsch"}), 403
    cfg = load_cfg()
    cfg['auth'] = {
        "username":      auth['username'],
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
        run(f"pactl set-source-mute '{source}' 1")
        for _ in range(repeat):
            run(f"mpg123 -q '{path}'", timeout=300)
        run(f"pactl set-source-mute '{source}' 0")

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

    cfg_text = (
        f"# Radxa Audio Konfigurator\nauto {iface}\n"
        f"iface {iface} inet static\n"
        f"    address {ip}/{prefix}\n    gateway {gateway}\n"
        f"    dns-nameservers {dns}\n\n"
        f"# Service-IP — FEST\nauto {iface}:service\n"
        f"iface {iface}:service inet static\n"
        f"    address {SERVICE_IP}/{SERVICE_MASK}\n"
    )
    errors = []
    try:
        with open(f"/etc/network/interfaces.d/{iface}", "w") as f:
            f.write(cfg_text)
    except PermissionError:
        errors.append("Root-Rechte fehlen für /etc/network")

    run(f"ip addr add {ip}/{prefix} dev {iface} 2>/dev/null")
    run(f"ip route add default via {gateway} dev {iface} 2>/dev/null")
    ensure_service_ip(iface)

    cfg = load_cfg()
    cfg["network"] = d
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
            elif in_profiles and ":" in s:
                pname = s.split(":")[0].strip()
                if pname and not any(c.isspace() for c in pname):
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
    r = run(f"pactl set-card-profile '{card}' '{profile}'")
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
    cfg["audio"] = {
        "source":       d.get("source", "@DEFAULT_SOURCE@"),
        "volume":       vol_out,
        "input_volume": vol_in,
    }
    save_cfg(cfg)
    src = cfg["audio"]["source"]
    run(f"pactl set-sink-volume @DEFAULT_SINK@ {vol_out}%")
    run(f"pactl set-source-volume '{src}' {vol_in}%")
    return jsonify({"ok": True})

@app.route('/api/audio/mute', methods=['POST'])
def api_mute():
    d = request.json
    run(f"pactl set-source-mute '{d.get('source','@DEFAULT_SOURCE@')}' "
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
            open(out_path, 'w').close()  # Platzhalter reservieren
        jobs.append({"orig": orig, "tmp": tmp, "out_name": out_name, "out_path": out_path})

    # 2. Parallel konvertieren — max. 4 ffmpeg-Prozesse gleichzeitig
    def convert(job):
        cmd = (f"ffmpeg -y -i '{job['tmp']}' "
               f"-ar 44100 -ac 1 -b:a 128k '{job['out_path']}' 2>&1")
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
CHIP        = '/dev/gpiochip0'
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
@app.route('/api/terminal/exec', methods=['POST'])
def api_terminal_exec():
    cmd = (request.json or {}).get("cmd", "").strip()
    if not cmd:
        return jsonify({"ok": True, "out": "", "cwd": _term_cwd[0]})
    with _term_lock:
        cwd = _term_cwd[0]
        # cd separat behandeln, damit es persistent wirkt
        if re.match(r'^cd(\s|$)', cmd):
            target = cmd[2:].strip() or "/root"
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
