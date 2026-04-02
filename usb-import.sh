#!/bin/bash
# USB-Stick Auto-Import: wird von udev beim Einstecken aufgerufen.
# Importiert MP3s direkt (kein API-Call nötig, läuft als root).

sleep 5  # Warten bis udev den Mount abgeschlossen hat

MP3_FOLDER="/etc/raspi_audio/sounds"
LOG="/var/log/raspi-usb-import.log"
CONVERTED=0
IMPORTED=0

echo "$(date): USB-Import gestartet" >> "$LOG"

# Alle USB-Partitionen finden
for dev in $(lsblk -o NAME,TRAN -J 2>/dev/null | python3 -c "
import json,sys
devs=json.load(sys.stdin).get('blockdevices',[])
def walk(d):
    if d.get('tran')=='usb' and d.get('name'): print('/dev/'+d['name'])
    for c in d.get('children') or []: walk(c)
[walk(d) for d in devs]
" 2>/dev/null); do
    # Mount-Punkt finden oder temporär mounten
    MPOINT=$(lsblk -o MOUNTPOINT "$dev" -n 2>/dev/null | head -1 | tr -d ' ')
    TEMP_MOUNT=0
    if [ -z "$MPOINT" ]; then
        MPOINT="/tmp/raspi-usb-$$"
        mkdir -p "$MPOINT"
        if mount -o ro "$dev" "$MPOINT" 2>/dev/null; then
            TEMP_MOUNT=1
        else
            rmdir "$MPOINT" 2>/dev/null
            continue
        fi
    fi

    # MP3s und konvertierbare Audio-Dateien suchen
    while IFS= read -r -d '' file; do
        fname=$(basename "$file")
        ext="${fname##*.}"
        stem="${fname%.*}"
        safe_stem=$(echo "$stem" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/_/g' | sed 's/__*/_/g' | cut -c1-80)
        [ -z "$safe_stem" ] && continue

        dst="$MP3_FOLDER/${safe_stem}.mp3"
        [ -f "$dst" ] && continue  # bereits vorhanden

        case "${ext,,}" in
            mp3)
                cp "$file" "$dst" 2>/dev/null && IMPORTED=$((IMPORTED+1))
                echo "$(date): Kopiert: $fname" >> "$LOG"
                ;;
            wav|ogg|flac|aac|m4a|wma|opus|aiff|aif)
                if command -v ffmpeg &>/dev/null; then
                    ffmpeg -i "$file" -codec:a libmp3lame -qscale:a 4 -y "$dst" >> "$LOG" 2>&1 \
                        && CONVERTED=$((CONVERTED+1)) \
                        && echo "$(date): Konvertiert: $fname → ${safe_stem}.mp3" >> "$LOG"
                fi
                ;;
        esac
    done < <(find "$MPOINT" -maxdepth 3 -type f \
        \( -iname "*.mp3" -o -iname "*.wav" -o -iname "*.ogg" -o -iname "*.flac" \
           -o -iname "*.aac" -o -iname "*.m4a" -o -iname "*.wma" \
           -o -iname "*.opus" -o -iname "*.aiff" -o -iname "*.aif" \) \
        -print0 2>/dev/null)

    [ "$TEMP_MOUNT" = "1" ] && umount "$MPOINT" 2>/dev/null && rmdir "$MPOINT" 2>/dev/null
done

echo "$(date): Fertig – $IMPORTED kopiert, $CONVERTED konvertiert" >> "$LOG"
