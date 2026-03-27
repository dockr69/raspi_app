# GPIO Audio HAT – Raspberry Pi 3/4

HAT-Board mit WM8960 Audio-Codec, Line-In/Out (3,5mm + Cinch) und 8 GPIO-Schraubklemmen für Taster.

---

## Schaltung

```
RPi GPIO Header (40-Pin)
  │
  ├── I2S ──────── WM8960 Audio Codec
  │   BCLK (GPIO18)     ├── LINPUT1 ←(1µF Film)← Line In L ── 3.5mm / RCA
  │   LRCLK (GPIO19)    ├── RINPUT1 ←(1µF Film)← Line In R ── 3.5mm / RCA
  │   DIN (GPIO20)      ├── HP_L →(220µF Elko)→ Line Out L ── 3.5mm / RCA
  │   DOUT (GPIO21)     └── HP_R →(220µF Elko)→ Line Out R ── 3.5mm / RCA
  │
  ├── I2C ──────── WM8960 Steuerung (Addr 0x1A, CSB→GND)
  │   SDA (GPIO2)
  │   SCL (GPIO3)
  │
  ├── 3V3 ──────── WM8960 (AVDD, DVDD, DCVDD, DBVDD) + Decoupling
  ├── 5V ───────── Reserve
  │
  └── GPIO ─────── 8x Schraubklemmen (mit RC-Entprellung)
      GPIO4, 5, 6, 17, 22, 23, 24, 27
```

---

## Bauteil-Empfehlungen

### Audio-Codec

| Bauteil | Empfehlung | Warum |
|---------|-----------|-------|
| **U1** WM8960 | Cirrus Logic WM8960CGEFL/RV (QFN-32) | 24-bit ADC/DAC, interner Headphone-Amp, I2S, I2C, gut dokumentierter Linux-Treiber (`snd-soc-wm8960`). PLL kann Clock aus BCLK ableiten → kein externer Quarz nötig |

### Kondensatoren – Eingang (Soundqualität!)

| Bauteil | Wert | Empfehlung | Warum |
|---------|------|-----------|-------|
| **C7, C8** Eingangs-Kopplung | **1µF** | **WIMA MKS2** oder **Kemet C0805C105K** (X7R MLCC, min. 50V) | Film-Caps = kein Piezo-Effekt, kein Mikrofonie-Problem. Bei MLCC: X7R statt Y5V (Y5V verliert 80% Kapazität bei Betriebsspannung). Für besten Klang: Film-Kondensatoren |
| **C1** VMID | **10µF** Elko | Nichicon UWT oder Panasonic FC | Niedrig-ESR Elko für saubere Referenzspannung |
| **C2** VREF | **100nF** | Kemet X7R 0805 | Stützt die interne Referenz, filtert HF |

### Kondensatoren – Ausgang

| Bauteil | Wert | Empfehlung | Warum |
|---------|------|-----------|-------|
| **C9, C10** Ausgangs-Kopplung | **220µF / 10V** | **Nichicon UKA** oder **Panasonic FR** (Low-ESR) | Große Koppel-Elkos für tiefe Frequenzen (f_c ≈ 22 Hz bei 32Ω Last). Niedrig-ESR ist wichtig für klaren Bass. Alternativ: 2x 100µF Film parallel für High-End |

### Kondensatoren – Power (Entkopplung)

| Bauteil | Wert | Empfehlung | Warum |
|---------|------|-----------|-------|
| **C3** AVDD | **10µF** | Kemet X5R 0805 | Analoge Versorgung braucht mehr Puffer |
| **C4** DVDD | **100nF** | Kemet X7R 0805 | HF-Entkopplung digital |
| **C5** DCVDD | **100nF** | Kemet X7R 0805 | Core-Spannung |
| **C6** DBVDD | **100nF** | Kemet X7R 0805 | Buffer-Spannung |

> **Tipp:** Alle Entkopplungs-Cs so nah wie möglich an die WM8960-Pins platzieren. AVDD und AGND getrennt von DVDD/DGND routen (Star-GND oder getrennte Kupferflächen).

### Widerstände

| Bauteil | Wert | Empfehlung | Warum |
|---------|------|-----------|-------|
| **R1** CSB Pull-Down | **10kΩ** 0805 | Beliebig, 1% | Setzt I2C-Adresse auf 0x1A |
| **R2–R9** GPIO-Entprellung | **10kΩ** 0805 | Beliebig, 1% | RC-Tiefpass zusammen mit C11-C18 für saubere Flanken |

### Kondensatoren – GPIO-Entprellung

| Bauteil | Wert | Empfehlung | Warum |
|---------|------|-----------|-------|
| **C11–C18** | **100nF** 0805 | Kemet X7R | Mit 10kΩ ergibt sich τ ≈ 1ms. Prellt bis ~5ms → sauber entprellt. Software-Debounce (200ms) kommt obendrauf als zweite Stufe |

### Steckverbinder

| Bauteil | Empfehlung | Warum |
|---------|-----------|-------|
| **J1** 40-Pin Header | Samtec SSW-120-01-G-D oder Standard 2x20 Female Header (2,54mm) | Stacking Header falls man den Pi-GPIO noch nutzen will |
| **J2, J5** 3,5mm Klinke | CUI SJ-3523-SMT oder Lumberg 1503 09 | TRS-Buchse, guter Kontakt, SMD-Montage möglich |
| **J3-J4, J6-J7** RCA/Cinch | CUI RCJ-01x oder Switchcraft 3501FRA | Vergoldeter Kontakt für geringstes Rauschen |
| **J8–J15** Schraubklemmen | Phoenix Contact MKDS 1,5/2 (5mm Raster) oder Wago 236-102 | Industriequalität, werkzeuglos (Wago) oder klassisch (Phoenix) |

### Optionale Verbesserungen

| Bauteil | Empfehlung | Warum |
|---------|-----------|-------|
| **TVS-Dioden** | PESD5V0S2BT (SOT-23) | ESD-Schutz an Audio-Ein-/Ausgängen. Bipolar, 5V Clamp |
| **Ferritperlen** | BLM18PG121 (120Ω @ 100MHz) | In 3V3-Leitung zwischen digital und analog für Entkopplung |
| **EEPROM** | CAT24C32 (I2C, SOT-23) | Für echte HAT-Kompatibilität (Device Tree auf ID_SD/ID_SC Pins 27/28). Optional |

---

## GPIO-Pin-Belegung

**Wichtig:** GPIO18 wird für I2S (BCLK) benötigt und steht NICHT als Taster-GPIO zur Verfügung!

| Funktion | GPIO | RPi Pin | Richtung |
|----------|------|---------|----------|
| I2C SDA | 2 | 3 | Bidirektional |
| I2C SCL | 3 | 5 | Bidirektional |
| **Taster 1** | **4** | 7 | Input (Pull-Up) |
| **Taster 2** | **5** | 29 | Input (Pull-Up) |
| **Taster 3** | **6** | 31 | Input (Pull-Up) |
| **Taster 4** | **17** | 11 | Input (Pull-Up) |
| I2S BCLK | 18 | 12 | Output → WM8960 |
| I2S LRCLK | 19 | 35 | Output → WM8960 |
| I2S DIN | 20 | 38 | Input ← WM8960 |
| I2S DOUT | 21 | 40 | Output → WM8960 |
| **Taster 5** | **22** | 15 | Input (Pull-Up) |
| **Taster 6** | **23** | 16 | Input (Pull-Up) |
| **Taster 7** | **24** | 18 | Input (Pull-Up) |
| **Taster 8** | **27** | 13 | Input (Pull-Up) |

---

## PCB Layout-Tipps

1. **Getrennte Ground-Planes**: AGND und DGND unter dem WM8960 getrennt führen, erst an EINEM Punkt verbinden (Star-Ground)
2. **Kurze Audio-Traces**: Coupling-Caps so nah wie möglich an die WM8960-Pins
3. **Keine I2S-Leitungen unter Audio-Bereich**: Digitale Signale erzeugen HF-Störungen
4. **Schraubklemmen am Rand**: Für einfachen Zugang, möglichst weit vom Audio-Codec entfernt
5. **Via-Stitching**: Ground-Vias rund um den Codec für niedrige Impedanz
6. **Massefläche unter Klinken-/Cinch-Buchsen**: Schirmt Störeinstrahlung ab

---

## Anpassung der Software

Die GPIO-Pins für Taster ändern sich von `[4, 17, 18, 22, 23, 24, 25, 27]` zu `[4, 5, 6, 17, 22, 23, 24, 27]`, weil GPIO18 für I2S benötigt wird.

In `app.py` muss `GPIO_PINS` angepasst werden:
```python
GPIO_PINS = [4, 5, 6, 17, 22, 23, 24, 27]
```

Für den WM8960 Linux-Treiber muss ein Device Tree Overlay geladen werden:
```bash
# /boot/config.txt (Raspberry Pi)
dtoverlay=wm8960-soundcard

# Oder manuelles Overlay erstellen für I2C-Adresse 0x1A
```

---

## KiCad-Projekt

```
hardware/gpio-audio-hat/
├── gpio-audio-hat.kicad_pro    # KiCad 8 Projektdatei
├── gpio-audio-hat.kicad_sch    # Schaltplan (komplett)
├── gpio-audio-hat.kicad_pcb    # PCB-Outline (65×56mm HAT)
├── generate_kicad.py           # Generator-Script (bei Änderungen erneut ausführen)
└── README.md                   # Diese Datei
```

Projekt in KiCad 8 öffnen → `gpio-audio-hat.kicad_pro`

---

## Stückliste (BOM)

| # | Ref | Wert | Footprint | Stück |
|---|-----|------|-----------|-------|
| 1 | U1 | WM8960 | QFN-32 5×5mm | 1 |
| 2 | J1 | 2x20 Female Header | 2.54mm | 1 |
| 3 | J2, J5 | 3.5mm TRS Jack | SMD | 2 |
| 4 | J3, J4, J6, J7 | RCA Jack | THT | 4 |
| 5 | J8–J15 | Schraubklemme 2-pol | 5mm | 8 |
| 6 | C1 | 10µF Elko | SMD 4×5.4 | 1 |
| 7 | C2, C4–C6, C11–C18 | 100nF X7R | 0805 | 12 |
| 8 | C3 | 10µF X5R | 0805 | 1 |
| 9 | C7, C8 | 1µF Film/X7R | 0805 | 2 |
| 10 | C9, C10 | 220µF Low-ESR | Elko 6.3×5.4 | 2 |
| 11 | R1 | 10kΩ | 0805 | 1 |
| 12 | R2–R9 | 10kΩ | 0805 | 8 |
| | | | **Gesamt:** | **41** |
