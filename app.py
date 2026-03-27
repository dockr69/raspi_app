#!/usr/bin/env python3
"""
Radxa ROCK 3A – Audio Konfigurator
· CGI-Trigger:  GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=<n>.mp3
· Legacy:       GET /play/<n>
· Service-IP 10.0.0.10 immer fest, nie änderbar
· Hostname: textspeicher  →  textspeicher.local (mDNS)
"""

from flask import Flask, render_template, request, jsonify
import subprocess, os, json, threading, re

app = Flask(__name__)

# ── Konstanten ────────────────────────────────────────────────────────────────
SERVICE_IP      = "10.0.0.10"
SERVICE_MASK    = "24"
HOSTNAME        = "textspeicher"
CONFIG_FILE     = "/etc/radxa_audio/config.json"
MP3_FOLDER      = "/etc/radxa_audio/sounds"
SETUP_DONE_FILE = "/etc/radxa_audio/.setup_done"
GPIO_PINS       = [4, 17, 18, 22, 23, 24, 25, 27]

os.makedirs(MP3_FOLDER, exist_ok=True)
os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

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
        })
    return result

_play_lock = threading.Lock()

def _play_thread(path, source):
    with _play_lock:
        run(f"pactl set-source-mute '{source}' 1")
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

    threading.Thread(target=_play_thread, args=(path, src), daemon=True).start()
    return True, os.path.basename(path)

# Service-IP beim Start setzen
ensure_service_ip()

# ── Trigger-Routen ────────────────────────────────────────────────────────────
@app.route('/cgi-bin/index.cgi')
def cgi_trigger():
    """
    WiFi-Button Format:
    GET /cgi-bin/index.cgi?webif-pass=1&spotrequest=test1.mp3
    """
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
        "config":        cfg,
    })

# ── API: Netzwerk ─────────────────────────────────────────────────────────────
@app.route('/api/network/interfaces')
def api_interfaces():
    return jsonify(get_interfaces())

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
@app.route('/api/audio/sources')
def api_sources():
    return jsonify(detect_sources())

@app.route('/api/audio/save', methods=['POST'])
def api_audio_save():
    d   = request.json
    cfg = load_cfg()
    cfg["audio"] = {
        "source": d.get("source", "@DEFAULT_SOURCE@"),
        "volume": d.get("volume", 80)
    }
    save_cfg(cfg)
    run(f"pactl set-sink-volume @DEFAULT_SINK@ {cfg['audio']['volume']}%")
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
    cfg = load_cfg()
    src = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    threading.Thread(target=_play_thread, args=(path, src), daemon=True).start()
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
    if ttype == "gpio":
        try:
            if int(pin) not in GPIO_PINS:
                return jsonify({"ok": False, "msg": f"Ungültiger GPIO-Pin: {pin}"}), 400
        except (TypeError, ValueError):
            return jsonify({"ok": False, "msg": "GPIO-Pin muss eine Zahl sein"}), 400
    cfg = load_cfg()
    if "sounds" not in cfg:
        cfg["sounds"] = {}
    cfg["sounds"][stem] = {
        "trigger_type": ttype,
        "gpio_pin":     pin if ttype == "gpio" else None,
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
            gpio_map[sc["gpio_pin"]] = stem
    if not gpio_map:
        # Keine GPIO-Sounds mehr → Daemon stoppen
        run("systemctl stop radxa-audio-gpio 2>/dev/null")
        return
    src = cfg.get("audio", {}).get("source", "@DEFAULT_SOURCE@")
    lines = [
        "#!/usr/bin/env python3",
        "# GPIO-Daemon – auto-generiert von Radxa Audio Konfigurator",
        "import RPi.GPIO as GPIO, subprocess, time, os",
        f"MP3_FOLDER  = '{MP3_FOLDER}'",
        f"LINE_SOURCE = {repr(src)}",
        f"GPIO_MAP    = {repr(gpio_map)}",
        "GPIO.setmode(GPIO.BCM)",
        "for p in GPIO_MAP: GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)",
        "def cb(ch):",
        "    stem = GPIO_MAP.get(ch)",
        "    if not stem: return",
        "    path = os.path.join(MP3_FOLDER, stem + '.mp3')",
        "    if not os.path.isfile(path): return",
        "    subprocess.run(['pactl','set-source-mute', LINE_SOURCE,'1'])",
        "    subprocess.run(['mpg123','-q', path])",
        "    subprocess.run(['pactl','set-source-mute', LINE_SOURCE,'0'])",
        "for p in GPIO_MAP:",
        "    GPIO.add_event_detect(p, GPIO.FALLING, callback=cb, bouncetime=200)",
        "try:",
        "    while True: time.sleep(0.5)",
        "finally: GPIO.cleanup()",
    ]
    with open("/usr/local/bin/radxa_gpio.py", "w") as f:
        f.write("\n".join(lines) + "\n")
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

# ── Frontend ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html',
                           service_ip=SERVICE_IP,
                           hostname=HOSTNAME,
                           setup_done=str(is_setup_done()).lower())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
