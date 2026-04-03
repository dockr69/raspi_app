@app.route('/api/backup/import', methods=['POST'])
def api_backup_import():
     """Importiert Config + Sounds + Texte aus ZIP."""
    if 'file' not in request.files:
        return jsonify({"ok": False, "msg": "Keine Datei"}), 400
    f = request.files['file']
    try:
        MAX_ENTRY_SIZE = 200 * 1024 * 1024   # 200 MB pro Datei
        with zipfile.ZipFile(f.stream, 'r') as zf:
             # ZIP-Bomb-Schutz: unkomprimierte Gesamtgroesse pruefen
            total_size = sum(i.file_size for i in zf.infolist())
            if total_size > 2 * 1024 * 1024 * 1024:   # 2 GB
                return jsonify({"ok": False, "msg": "ZIP zu gross (max 2 GB unkomprimiert)"}), 400
            names = zf.namelist()
             # Config importieren
            texts_imported = 0
            sounds_imported = 0
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
                if name.startswith("texts/") and name.endswith(".txt"):
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
        return jsonify({"ok": True, "msg": f"Config + {texts_imported} Texte + {sounds_imported} Sounds importiert"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"Import fehlgeschlagen: {e}"}), 400
