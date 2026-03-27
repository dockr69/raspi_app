# GPIO-Only HAT – Raspberry Pi 3/4

Minimales HAT: Nur 8 Schraubklemmen für Taster mit RC-Entprellung. Kein Audio-Codec — Audio läuft über den 3,5mm-Klinke des Pi/Radxa direkt.

---

## Schaltung

```
RPi GPIO Header (40-Pin)
  │
  ├── 3V3, 5V ──── Stromversorgung
  ├── GND ──────── Gemeinsame Masse
  │
  └── 8x GPIO ──── je: Schraubklemme → R(10k) → GPIO + C(100nF) → GND
      GPIO 4, 17, 18, 22, 23, 24, 25, 27
```

Pro Kanal:
```
Schraubklemme Pin 1 ──── R 10kΩ ────┬──── GPIO (zum Pi)
                                     │
Schraubklemme Pin 2 ──── GND    C 100nF
                                     │
                                    GND
```

---

## Stückliste

| # | Ref | Wert | Footprint | Stück |
|---|-----|------|-----------|-------|
| 1 | J1 | 2x20 Female Header | 2.54mm | 1 |
| 2 | J2–J9 | Schraubklemme 2-pol | Phoenix MKDS 1,5/2 (5mm) | 8 |
| 3 | R1–R8 | 10kΩ | 0805 | 8 |
| 4 | C1–C8 | 100nF X7R | 0805 | 8 |
| | | | **Gesamt:** | **25** |

---

## Bauteil-Tipps

| Bauteil | Empfehlung | Warum |
|---------|-----------|-------|
| **Schraubklemmen** | Phoenix MKDS 1,5/2 oder Wago 236-102 | Robust, 5mm Raster passt gut aufs HAT |
| **Widerstände** | Beliebig 0805, 1% | Serienwiderstand für RC-Entprellung |
| **Kondensatoren** | Kemet X7R 0805 | τ = 10k × 100nF = 1ms → prellt bis ~5ms sauber |
| **Header** | Samtec SSW-120-01-G-D | Stacking Header falls GPIO durchgeschleift werden soll |

---

## GPIO-Pins

Identisch mit `GPIO_PINS` in `app.py` — keine Software-Änderung nötig.

| GPIO | RPi Pin | Schraubklemme |
|------|---------|---------------|
| 4 | 7 | J2 |
| 17 | 11 | J3 |
| 18 | 12 | J4 |
| 22 | 15 | J5 |
| 23 | 16 | J6 |
| 24 | 18 | J7 |
| 25 | 22 | J8 |
| 27 | 13 | J9 |

---

## Alternative: Lochrasterplatine

Diese Schaltung ist so einfach, dass sie problemlos auf einer **Streifenrasterplatine** aufgebaut werden kann:
- 2x20 Buchsenleiste auflöten
- 8x 2er-Schraubklemmen am Rand
- 8x 10kΩ + 100nF pro Kanal
- Fertig in ~30 Minuten
