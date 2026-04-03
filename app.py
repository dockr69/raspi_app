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
CONFIG_FILE     = "/etc/raspi_audio/config.json"
MP3_FOLDER      = "/etc/raspi_audio/sounds"
BOARD_FILE      = "/etc/raspi_audio/board.json"

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

SECRET_KEY_FILE  = "/etc/raspi_audio/.secret_key"
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
    sink   = cfg.get("audio", {}).get("sink",   "@DEFAULT_SINK@")
    # Fallback auf auto-erkannte USB-Geräte wenn Config-Gerät nicht mehr existiert
    live_sources = detect_sources()
    live_sinks   = _detect_sinks()
    if source not in live_sources and live_sources and live_sources[0] != "@DEFAULT_SOURCE@":
        source = live_sources[0]
        cfg.setdefault("audio", {})["source"] = source
        save_cfg(cfg)
        print(f"[AUDIO] Source auto-updated: {source}", flush=True)
    if sink not in live_sinks and live_sinks and live_sinks[0] != "@DEFAULT_SINK@":
        sink = live_sinks[0]
        cfg.setdefault("audio", {})["sink"] = sink
        save_cfg(cfg)
        print(f"[AUDIO] Sink auto-updated: {sink}", flush=True)
    r = run(f"pactl load-module module-loopback "
            f"source={shlex.quote(source)} "
            f"sink={shlex.quote(sink)} "
            f"latency_msec=200")
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
      # Ensure USB audio is preferred when config exists but device is invalid
    elif cfg.get("audio", {}).get("source") == "@DEFAULT_SOURCE@" or cfg.get("audio", {}).get("sink") == "@DEFAULT_SINK@":
        sources = detect_sources()
        sinks = _detect_sinks()
        if sources and sources[0] != "@DEFAULT_SOURCE@":
            cfg["audio"]["source"] = sources[0]
            changed = True
        if sinks and sinks[0] != "@DEFAULT_SINK@":
            cfg["audio"]["sink"] = sinks[0]
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
    if "mode" not in cfg:
        cfg["mode"] = "online"
        changed = True
    if changed:
        save_cfg(cfg)
    return cfg

_cfg_lock = threading.Lock()
_secret_lock = threading.Lock()

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
        try:
            with open(tmp, 'w') as f:
                f.write(k)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, SECRET_KEY_FILE)
            os.chmod(SECRET_KEY_FILE, 0o600)
        except PermissionError:
            pass
        return k

app.secret_key = _load_secret_key()

# ── Helpers ───────────────────────────────────────────────────────────────────
def run(cmd, timeout=20, env=None):
    """Execute shell command with optional custom environment."""
    try:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        # Ensure PULSE_SERVER is set for system-mode PulseAudio (fixed socket path)
        if not run_env.get("PULSE_SERVER"):
            for _sock in ("/run/pulse/native", "/var/run/pulse/native"):
                if os.path.exists(_sock):
                    run_env["PULSE_SERVER"] = f"unix:{_sock}"
                    break
        r = subprocess.run(cmd, shell=True, capture_output=True,
                           text=True, timeout=timeout, env=run_env)
        return {"out": r.stdout.strip(), "err": r.stderr.strip(),
                "ok": r.returncode == 0}
    except subprocess.TimeoutExpired:
        return {"out": "", "err": "timeout", "ok": False}
    except Exception as e:
        return {"out": "", "err": str(e), "ok": False}

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

_EXCLUDE_CARDS = ("alsa_output.platform-", "alsa_input.platform-", "alsa_output.bcm", "alsa_input.bcm")

_audio_cache = {"sources": None, "sinks": None, "ts": 0.0}
_AUDIO_CACHE_TTL = 30.0  # Sekunden

def _audio_cache_valid():
    return (time.time() - _audio_cache["ts"]) < _AUDIO_CACHE_TTL

def _refresh_audio_cache():
    sources_out = run("pactl list sources short 2>/dev/null")["out"]
    sinks_out   = run("pactl list sinks short 2>/dev/null")["out"]

    sources = [l.split()[1] for l in sources_out.splitlines()
               if len(l.split()) >= 2
               and "monitor" not in l.split()[1].lower()
               and not l.split()[1].startswith(_EXCLUDE_CARDS)]
    sources = [s for s in sources if "hdmi" not in s.lower() and "vc4" not in s.lower()]
    usb_sources = [s for s in sources if ".1." in s or "usb" in s.lower()]
    if usb_sources:
        sources = usb_sources + [s for s in sources if s not in usb_sources]
    _audio_cache["sources"] = sources or ["@DEFAULT_SOURCE@"]

    sinks = [l.split()[1] for l in sinks_out.splitlines()
             if len(l.split()) >= 2
             and not l.split()[1].startswith(_EXCLUDE_CARDS)]
    sinks = [s for s in sinks if "hdmi" not in s.lower() and "vc4" not in s.lower()]
    usb_sinks = [s for s in sinks if ".1." in s or "usb" in s.lower()]
    if usb_sinks:
        sinks = usb_sinks + [s for s in sinks if s not in usb_sinks]
    _audio_cache["sinks"] = sinks or ["@DEFAULT_SINK@"]

    _audio_cache["ts"] = time.time()

def detect_sources():
    """Detect PulseAudio sources with caching."""
    if not _audio_cache_valid():
        _refresh_audio_cache()
    return _audio_cache["sources"]

def _detect_sinks():
    """Detect PulseAudio sinks with caching."""
    if not _audio_cache_valid():
        _refresh_audio_cache()
    return _audio_cache["sinks"]

def list_mp3s():
    cfg = load_cfg()
    sounds = cfg.get("sounds", {})
    result = []
    for idx, f in enumerate(sorted(os.listdir(MP3_FOLDER)), start=1):
        if not f.lower().endswith('.mp3'):
            continue
        stem = f[:-4]
        sc   = sounds.get(stem, {})
        result.append({
              "id":           idx,
              "name":         f,
              "stem":         stem,
              "size_kb":      os.path.getsize(os.path.join(MP3_FOLDER, f)) // 1024,
              "trigger_type": sc.get("trigger_type", "http"),
              "gpio_pin":     sc.get("gpio_pin", None),
              "repeat":       max(1, min(10, int(sc.get("repeat", 1)))),
              "timeout":      max(0, min(300, int(sc.get("timeout", 30)))),
          })
    return result

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
    # ID-basiert: '1' → erste MP3, '1.mp3' → erste MP3
    name_clean = name.strip()
    if name_clean.isdigit():
        sounds = list_mp3s()
        try:
            sound = next(s for s in sounds if str(s['id']) == name_clean)
            stem = sound['stem']
            path = os.path.join(MP3_FOLDER, stem + ".mp3")
        except StopIteration:
            return False, f"MP3 mit ID {name_clean} nicht gefunden"
    else:
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
    sc   = cfg.get("sounds", {}).get(stem, {})

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

# Audio-Loopback sicherstellen (Line-In → Line-Out Passthrough)
# In background thread to avoid blocking startup / watchdog timeout
def _startup_loopback():
    for attempt in range(10):
        time.sleep(2)
        if _get_loopback_id():
            break
        ensure_loopback()
        if _loopback_module_id:
            break
threading.Thread(target=_startup_loopback, daemon=True).start()

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

# Service-IP, Volume und Sleep-Mask im Hintergrund – nicht blockierend beim Start
def _startup_tasks():
    time.sleep(0.5)
    ensure_service_ip()
    _restore_volume()
    run("systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null")
threading.Thread(target=_startup_tasks, daemon=True).start()

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
    sound_id      = request.args.get('id', '')
    if not spotrequest and not sound_id:
        return 'ERROR: missing spotrequest or id', 400
    cfg = load_cfg()
    expected = str(cfg.get("trigger", {}).get("webif_pass", "1"))
    if webif_pass != expected:
        return 'ERROR: unauthorized', 403
     # ID-Trigger priorisieren
    if sound_id and sound_id.isdigit():
        ok, msg = trigger_play(sound_id)
    else:
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
    # Loopback-Status
    loopback_active = _get_loopback_id() is not None
    # Config ohne sensible Daten (auth) ans Frontend geben
    safe_cfg = {k: v for k, v in cfg.items() if k != "auth"}
    # Audio-Platzhalter auflösen
    if safe_cfg.get("audio", {}).get("source") == "@DEFAULT_SOURCE@":
        safe_cfg.setdefault("audio", {})["source"] = _resolve_default_source("@DEFAULT_SOURCE@")
    if safe_cfg.get("audio", {}).get("sink") == "@DEFAULT_SINK@":
        safe_cfg.setdefault("audio", {})["sink"] = _resolve_default_sink("@DEFAULT_SINK@")
    return jsonify({
        "setup_done":    True,
        "service_ip":    SERVICE_IP,
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
def _resolve_default_source(src):
    """Resolve @DEFAULT_SOURCE@ placeholder to actual device name."""
    if src == "@DEFAULT_SOURCE@":
        sources = detect_sources()
        return sources[0] if sources else "@DEFAULT_SOURCE@"
    return src

def _resolve_default_sink(sink):
    """Resolve @DEFAULT_SINK@ placeholder to actual device name."""
    if sink == "@DEFAULT_SINK@":
        sinks = _detect_sinks()
        return sinks[0] if sinks else "@DEFAULT_SINK@"
    return sink

@app.route('/api/audio/sources')
def api_sources():
    sources = detect_sources()
    if len(sources) == 1:
        cfg = load_cfg()
        stored_source = cfg.get("audio", {}).get("source")
        if not stored_source or stored_source == "@DEFAULT_SOURCE@":
            cfg.setdefault("audio", {})["source"] = sources[0]
            save_cfg(cfg)
    return jsonify([{"name": s, "alias": _audio_alias(s)} for s in sources])

@app.route('/api/audio/sinks')
def api_sinks():
    sinks = _detect_sinks()
    if len(sinks) == 1:
        cfg = load_cfg()
        stored_sink = cfg.get("audio", {}).get("sink")
        if not stored_sink or stored_sink == "@DEFAULT_SINK@":
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

@app.route('/api/usb/import', methods=['POST'])
def api_usb_import():
    """Scannt gemountete USB-Sticks nach MP3s und importiert sie."""
    imported, skipped = [], []
    mount_dirs = []
    # Alle gemounteten USB-Massenspeicher finden
    mounts = run("lsblk -o MOUNTPOINT,TRAN -J 2>/dev/null")
    try:
        import json as _json
        devs = _json.loads(mounts["out"]).get("blockdevices", [])
        def _collect(devs):
            for d in devs:
                if d.get("tran") == "usb" and d.get("mountpoint"):
                    mount_dirs.append(d["mountpoint"])
                for child in d.get("children") or []:
                    _collect([child])
        _collect(devs)
    except Exception:
        pass
    # Fallback: /media und /mnt durchsuchen
    if not mount_dirs:
        for base in ("/media", "/mnt"):
            if os.path.isdir(base):
                for entry in os.listdir(base):
                    p = os.path.join(base, entry)
                    if os.path.ismount(p):
                        mount_dirs.append(p)
    if not mount_dirs:
        return jsonify({"ok": False, "msg": "Kein USB-Stick gefunden"}), 404
    import shutil
    audio_exts = {'.mp3','.wav','.ogg','.flac','.aac','.m4a','.wma','.opus','.aiff','.aif'}
    for mdir in mount_dirs:
        for root, _, files in os.walk(mdir):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in audio_exts:
                    continue
                src_path = os.path.join(root, fname)
                stem = sanitize(os.path.splitext(fname)[0])
                if not stem:
                    skipped.append(fname)
                    continue
                dst = os.path.join(MP3_FOLDER, stem + ".mp3")
                if os.path.exists(dst):
                    skipped.append(fname)
                    continue
                try:
                    if ext == '.mp3':
                        shutil.copy2(src_path, dst)
                    else:
                        r = run(f"ffmpeg -i {shlex.quote(src_path)} -codec:a libmp3lame -qscale:a 4 -y {shlex.quote(dst)} 2>/dev/null", timeout=120)
                        if not r["ok"]:
                            skipped.append(f"{fname} (ffmpeg error)")
                            continue
                    imported.append(stem + ".mp3")
                except Exception as e:
                    skipped.append(f"{fname} ({e})")
    return jsonify({"ok": True, "imported": len(imported), "skipped": len(skipped),
                    "files": imported, "msg": f"{len(imported)} importiert, {len(skipped)} übersprungen"})

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


@app.route('/api/mp3s/play-id', methods=['POST'])
def api_mp3_play_id():
    """Play sound by ID."""
    sound_id = request.json.get("id", 0)
    sounds = list_mp3s()
    try:
        sound = next(s for s in sounds if s['id'] == sound_id)
    except StopIteration:
        return jsonify({"ok": False, "msg": f"Sound mit ID {sound_id} nicht gefunden"}), 404
    path = os.path.join(MP3_FOLDER, sound['stem'] + ".mp3")
    cfg     = load_cfg()
    src     = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    repeat = max(1, min(10, int(cfg.get("sounds", {}).get(sound['stem'], {}).get("repeat", 1))))
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
        print(f"[GPIO] Invalid repeat value for {stem}: {d.get('repeat')}, using default 1", file=sys.stderr)
    try:
        timeout = max(0, min(300, int(d.get("timeout", 30))))
    except (TypeError, ValueError):
        timeout = 30
        print(f"[GPIO] Invalid timeout value for {stem}: {d.get('timeout')}, using default 30", file=sys.stderr)
    cfg["sounds"][stem] = {
        "trigger_type": ttype,
        "gpio_pin":     pin if ttype == "gpio" else None,
        "repeat":       repeat,
        "timeout":      timeout,
    }
    save_cfg(cfg)
    # GPIO-Script neu generieren
    _write_gpio_script(cfg)
    return jsonify({"ok": True})

# Max Dateigroesse fuer Uploads (500MB, fuer grosse ZIPs)
MAX_UPLOAD_SIZE = 500 * 1024 * 1024

_AUDIO_EXTS = {'.mp3','.wav','.ogg','.flac','.aac','.m4a','.wma','.opus','.mp4','.aiff','.aif'}

@app.route('/api/upload', methods=['POST'])
def api_upload():
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if 'file' not in request.files:
        return jsonify([{"ok": False, "error": "kein file"}]), 400

    # 1. Alle Uploads auf Disk sichern; ZIPs entpacken
    _name_lock = threading.Lock()
    jobs = []

    def _add_job(orig, tmp_path):
        stem = sanitize(os.path.splitext(orig)[0]) or "audio"
        with _name_lock:
            out_name = stem + ".mp3"
            out_path = os.path.join(MP3_FOLDER, out_name)
            c = 1
            while os.path.exists(out_path):
                out_name = f"{stem}_{c}.mp3"
                out_path = os.path.join(MP3_FOLDER, out_name)
                c += 1
            with open(out_path, 'wb') as _ph:
                _ph.write(b'\x00')
        jobs.append({"orig": orig, "tmp": tmp_path, "out_name": out_name, "out_path": out_path})

    for f in request.files.getlist('file'):
        orig = f.filename or "audio"
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        if size > MAX_UPLOAD_SIZE:
            jobs.append({"orig": orig, "error": f"Datei zu gross ({size//1024//1024}MB)"})
            continue
        ext = os.path.splitext(orig)[1].lower()
        tmp = f"/tmp/_radxa_{sanitize(os.path.splitext(orig)[0]) or 'audio'}_{os.getpid()}_{len(jobs)}{re.sub(r'[^a-zA-Z0-9.]','',ext)}"
        f.save(tmp)
        if ext == '.zip':
            # ZIP entpacken und alle Audio-Dateien als Jobs hinzufügen
            try:
                with zipfile.ZipFile(tmp, 'r') as zf:
                    for entry in zf.namelist():
                        entry_ext = os.path.splitext(entry)[1].lower()
                        if entry_ext not in _AUDIO_EXTS:
                            continue
                        entry_base = os.path.basename(entry)
                        if not entry_base:
                            continue
                        entry_tmp = f"/tmp/_radxa_zip_{sanitize(os.path.splitext(entry_base)[0]) or 'audio'}_{os.getpid()}_{len(jobs)}{re.sub(r'[^a-zA-Z0-9.]','',entry_ext)}"
                        with zf.open(entry) as src, open(entry_tmp, 'wb') as dst:
                            dst.write(src.read())
                        _add_job(entry_base, entry_tmp)
            except Exception as e:
                jobs.append({"orig": orig, "error": f"ZIP-Fehler: {e}"})
                print(f"[ZIP] Extraction failed for {orig}: {e}", file=sys.stderr)
            finally:
                try: os.remove(tmp)
                except Exception: pass
        elif ext in _AUDIO_EXTS:
            _add_job(orig, tmp)
        else:
            try: os.remove(tmp)
            except Exception: pass
            jobs.append({"orig": orig, "error": f"Format nicht unterstützt: {ext}"})

    # 2. Parallel konvertieren — max. 4 ffmpeg-Prozesse gleichzeitig
    def convert(job):
        try:
            cmd = (f"ffmpeg -y -i {shlex.quote(job['tmp'])} "
                   f"-ar 44100 -ac 1 -b:a 128k {shlex.quote(job['out_path'])} 2>&1")
            r = run(cmd, timeout=120)
            if r["ok"] and os.path.isfile(job["out_path"]) and os.path.getsize(job["out_path"]) > 0:
                return {"ok": True, "original": job["orig"],
                        "saved_as": job["out_name"],
                        "size_kb": os.path.getsize(job["out_path"]) // 1024}
            else:
                try: os.remove(job["out_path"])
                except Exception: pass
                print(f"[FFMPEG] Conversion failed for {job['orig']}: {(r['out'] or r['err'])[:300]}", file=sys.stderr)
                return {"ok": False, "original": job["orig"],
                        "error": (r["out"] or r["err"])[:300]}
        finally:
            try: os.remove(job["tmp"])
            except Exception: pass

    results_map = {j["orig"]: j for j in jobs if "error" in j}  # Vorab-Fehler direkt
    convert_jobs = [j for j in jobs if "tmp" in j]
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_to_job = {pool.submit(convert, j): j for j in convert_jobs}
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
                "stem":    stem,
                "repeat":  max(1, min(10, int(sc.get("repeat", 1)))),
                "timeout": max(0, min(300, int(sc.get("timeout", 30)))),
            }
    if not gpio_map:
        run("systemctl stop raspi-audio-gpio 2>/dev/null")
        return
    src = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    # Uses python3-gpiod (works on Radxa ROCK 3A, 4C+ and all libgpiod boards)
    # Supports gpiod 2.x API (Debian Bookworm+) with automatic fallback to gpiod 1.x
    script = f"""#!/usr/bin/env python3
# GPIO-Daemon – auto-generiert von Raspi Audio Konfigurator
import subprocess, time, os, sys, threading

os.environ['PULSE_SERVER'] = 'unix:/run/pulse/native'

MP3_FOLDER  = {repr(str(MP3_FOLDER))}
LINE_SOURCE = {repr(src)}
GPIO_MAP    = {repr(gpio_map)}
CHIP        = {repr(GPIOCHIP)}
DEBOUNCE    = 0.3  # 300ms Hardware-Debounce gegen Prellen

print(f"[GPIO] Daemon gestartet | Pins={{list(GPIO_MAP.keys())}} | Chip={{CHIP}}", flush=True)

def _source_exists():
    '''Prueft ob LINE_SOURCE in PulseAudio vorhanden ist.'''
    try:
        r = subprocess.run(['pactl', 'list', 'sources', 'short'],
                           capture_output=True, timeout=2)
        return LINE_SOURCE in r.stdout.decode()
    except Exception:
        return False

def pactl_available():
    try:
        r = subprocess.run(['pactl', 'info'], capture_output=True, timeout=2)
        return r.returncode == 0
    except Exception:
        return False

_last  = {{}}
_busy  = {{}}
_lock  = threading.Lock()

def _can_trigger(pin, timeout_sec):
    '''True wenn Pin nicht busy und ausserhalb des Timeout-Fensters.'''
    now = time.monotonic()
    cooldown = max(DEBOUNCE, timeout_sec if timeout_sec > 0 else DEBOUNCE)
    with _lock:
        if _busy.get(pin):
            return False
        if now - _last.get(pin, 0) < cooldown:
            return False
        _last[pin] = now
        _busy[pin] = True
    return True

def play(pin, entry):
    stem    = entry['stem']
    repeat  = entry.get('repeat', 1)
    timeout = entry.get('timeout', 0)
    path    = os.path.join(MP3_FOLDER, stem + '.mp3')
    print(f"[GPIO] Pin {{pin}} ausgeloest → {{stem}}", flush=True)
    try:
        if not os.path.isfile(path):
            print(f"[GPIO] Datei nicht gefunden: {{path}}", file=sys.stderr, flush=True)
            return
        if not pactl_available():
            print(f"[GPIO] PulseAudio nicht erreichbar", file=sys.stderr, flush=True)
            return
        has_source = _source_exists()
        if has_source:
            try:
                subprocess.run(['pactl', 'set-source-mute', LINE_SOURCE, '1'], timeout=2)
            except Exception as e:
                print(f"[GPIO] Mute fehlgeschlagen: {{e}}", file=sys.stderr, flush=True)
        for i in range(repeat):
            try:
                r = subprocess.run(['mpg123', '-q', path], timeout=300)
                if r.returncode != 0:
                    print(f"[GPIO] mpg123 Fehler exit={{r.returncode}}", file=sys.stderr, flush=True)
            except subprocess.TimeoutExpired:
                print(f"[GPIO] Playback Timeout", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"[GPIO] Playback Fehler: {{e}}", file=sys.stderr, flush=True)
        if has_source:
            try:
                subprocess.run(['pactl', 'set-source-mute', LINE_SOURCE, '0'], timeout=2)
            except Exception as e:
                print(f"[GPIO] Unmute fehlgeschlagen: {{e}}", file=sys.stderr, flush=True)
        print(f"[GPIO] Pin {{pin}} fertig", flush=True)
        # Timeout abwarten bevor Pin wieder freigegeben wird
        if timeout > 0:
            time.sleep(timeout)
    finally:
        with _lock:
            _busy[pin] = False

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
        consumer='raspi-audio',
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
                    pin   = ev.line_offset
                    entry = GPIO_MAP.get(pin)
                    if entry and _can_trigger(pin, entry.get('timeout', 0)):
                        threading.Thread(target=play, args=(pin, entry), daemon=True).start()
else:
    # gpiod 1.x
    chip  = gpiod.Chip(CHIP)
    lines = chip.get_lines(list(GPIO_MAP.keys()))
    lines.request(
        consumer='raspi-audio',
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
                        if entry and _can_trigger(pin, entry.get('timeout', 0)):
                            threading.Thread(target=play, args=(pin, entry), daemon=True).start()
    finally:
        lines.release()
"""
    with open("/usr/local/bin/raspi_gpio.py", "w") as f:
        f.write(script)
    os.chmod("/usr/local/bin/raspi_gpio.py", 0o755)
    run("systemctl restart raspi-audio-gpio 2>/dev/null")

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
    web_ok   = "active" in run("systemctl is-active raspi-audio-web 2>/dev/null")["out"]
    gpio_ok  = "active" in run("systemctl is-active raspi-audio-gpio 2>/dev/null")["out"]
    pulse_ok = run("pactl info 2>/dev/null")["ok"]
    loopback = _get_loopback_id() is not None
    # Disk-Warnstufe
    disk_warn = False
    try:
        disk_warn = int(disk_pct.rstrip('%')) >= 85
    except Exception:
        pass
    return jsonify({
        "cpu_temp":     temp,
        "ram_total":    ram_total,
        "ram_used":     ram_used,
        "disk_total":   disk_total,
        "disk_used":    disk_used,
        "disk_pct":     disk_pct,
        "disk_warn":    disk_warn,
        "uptime":       uptime,
        "web_service":  web_ok,
        "gpio_service": gpio_ok,
        "pulse_ok":     pulse_ok,
        "loopback":     loopback,
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
            timeout=5)
    if os.path.isfile(tmp) and os.path.getsize(tmp) > 100:
        resp = send_file(tmp, mimetype='audio/wav')
        threading.Thread(target=lambda: (time.sleep(2), os.remove(tmp)),
                         daemon=True).start()
        return resp
    return jsonify({"ok": False, "msg": "Aufnahme fehlgeschlagen"}), 500

# ── API: Reboot / Restart ───────────────────────────────────────────────────
@app.route('/api/system/restart-service', methods=['POST'])
def api_restart_service():
    run("systemctl restart raspi-audio-web 2>/dev/null")
    return jsonify({"ok": True, "msg": "Service wird neu gestartet..."})

@app.route('/api/system/reboot', methods=['POST'])
def api_reboot():
    threading.Thread(target=lambda: (time.sleep(1), os.system("reboot")),
                     daemon=True).start()
    return jsonify({"ok": True, "msg": "Neustart in 1 Sekunde..."})

# ── API: Update (git pull) ──────────────────────────────────────────────────
_GIT = "/usr/bin/git"

@app.route('/api/update/status')
def api_update_status():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    commit     = run(f"{_GIT} -C {shlex.quote(app_dir)} log -1 --format=%h|%s|%ci")["out"].strip()
    parts      = commit.split("|", 2)
    current_hash = parts[0] if len(parts) > 0 else "?"
    current_msg    = parts[1] if len(parts) > 1 else "?"
    current_date = parts[2][:10] if len(parts) > 2 else "?"
    current_date = parts[2][:10] if len(parts) > 2 else "?"

    # Skip network fetch - just show current commit (GitHub may be unreachable)
    behind = run(f"{_GIT} -C {shlex.quote(app_dir)} rev-list HEAD..origin/main --count")["out"].strip()
    try:
        behind_count = int(behind)
    except ValueError:
        behind_count = 0
    return jsonify({
          "hash": current_hash,
          "message": current_msg,
          "date": current_date,
          "behind": behind_count,
            "test": "Update-Test"
      })

@app.route('/api/update/pull', methods=['POST'])
def api_update_pull():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    r = run(f"{_GIT} -C {shlex.quote(app_dir)} pull origin main 2>&1", timeout=60)
    if not r["ok"]:
        return jsonify({"ok": False, "msg": r["out"] or r["err"]})
    threading.Thread(
        target=lambda: (time.sleep(2), os.system("systemctl restart raspi-audio-web")),
        daemon=True
    ).start()
    return jsonify({"ok": True, "msg": r["out"].strip()})

# ── API: Backup / Restore ───────────────────────────────────────────────────
def _backup_export_zip():
    """Exportiert Config + Board + Texte + Sounds als ZIP. Returns BytesIO."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Config
        if os.path.isfile(CONFIG_FILE):
            zf.write(CONFIG_FILE, "config.json")
        # Board Config
        if os.path.isfile(BOARD_FILE):
            zf.write(BOARD_FILE, "board.json")
        # Text-Dateien
        cfg_dir = os.path.dirname(CONFIG_FILE)
        if os.path.isdir(cfg_dir):
            for fn in os.listdir(cfg_dir):
                fp = os.path.join(cfg_dir, fn)
                if os.path.isfile(fp) and fn.endswith('.txt'):
                    zf.write(fp, f"texts/{fn}")
        # Sounds
        for f in os.listdir(MP3_FOLDER):
            fp = os.path.join(MP3_FOLDER, f)
            if os.path.isfile(fp):
                zf.write(fp, f"sounds/{f}")
    buf.seek(0)
    return buf

def _backup_import_zip(zip_file):
    """Importiert Config, Board, Texts, Sounds aus ZIP. Returns (ok, msg, texts_count, sounds_count)."""
    try:
        MAX_ENTRY_SIZE = 200 * 1024 * 1024  # 200 MB pro Datei
        with zipfile.ZipFile(zip_file.stream, 'r') as zf:
            # ZIP-Bomb-Schutz
            total_size = sum(i.file_size for i in zf.infolist())
            if total_size > 2 * 1024 * 1024 * 1024:  # 2 GB
                return False, "ZIP zu gross (max 2 GB unkomprimiert)", 0, 0
            names = zf.namelist()
            texts_imported = 0
            sounds_imported = 0
            # Config importieren
            if "config.json" in names:
                cfg_data = json.loads(zf.read("config.json"))
                save_cfg(cfg_data)
            # Board Config importieren
            if "board.json" in names:
                board_data = json.loads(zf.read("board.json"))
                save_cfg(board_data)
            # Text-Dateien importieren
            cfg_dir = os.path.dirname(CONFIG_FILE)
            for name in names:
                if name.startswith("texts/") and name.endswith('.txt'):
                    basename = os.path.basename(name)
                    if basename:
                        target = os.path.join(cfg_dir, basename)
                        with open(target, "wb") as out:
                            out.write(zf.read(name))
                        texts_imported += 1
            # Sounds importieren
            for name in names:
                if name.startswith("sounds/") and name.endswith(".mp3"):
                    info = zf.getinfo(name)
                    if info.file_size > MAX_ENTRY_SIZE:
                        continue
                    basename = os.path.basename(name)
                    if basename:
                        target = os.path.join(MP3_FOLDER, basename)
                        with open(target, "wb") as out:
                            out.write(zf.read(name))
                        sounds_imported += 1
        return True, f"Config + {texts_imported} Texte + {sounds_imported} Sounds importiert", texts_imported, sounds_imported
    except Exception as e:
        return False, f"Import fehlgeschlagen: {e}", 0, 0

@app.route('/api/backup/export')
def api_backup_export():
    """Exportiert Config + Board + Texte + Sounds als ZIP."""
    return send_file(_backup_export_zip(), mimetype='application/zip',
                     as_attachment=True, download_name='radxa_backup.zip')

@app.route('/api/backup/import', methods=['POST'])
def api_backup_import():
    """Importiert Config + Board + Texte + Sounds aus ZIP."""
    if 'file' not in request.files:
        return jsonify({"ok": False, "msg": "Keine Datei"}), 400
    ok, msg, texts, sounds = _backup_import_zip(request.files['file'])
    if ok:
        return jsonify({"ok": True, "msg": msg, "texts": texts, "sounds": sounds})
    return jsonify({"ok": False, "msg": msg}), 400
