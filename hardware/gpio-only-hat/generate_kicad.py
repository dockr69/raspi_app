#!/usr/bin/env python3
"""
GPIO-Only HAT – KiCad Schematic & PCB Generator
================================================
Simples HAT: 8x Schraubklemmen mit RC-Entprellung, kein Audio-Codec.
Audio läuft über den 3.5mm-Klinke des Raspberry Pi direkt.

Run: python3 generate_kicad.py
"""

import uuid as _uuid

_counter = 0
def uid():
    global _counter
    _counter += 1
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"gpio-only-{_counter}"))


def generate_schematic():
    root = uid()
    lib_symbols = []
    components = []
    labels = []
    wires = []
    texts = []
    pwr_idx = [0]

    def pwr_ref():
        pwr_idx[0] += 1
        return f"#PWR{pwr_idx[0]:03d}"

    # ── Symbol: 2x20 Header ──
    pins_left = []
    pins_right = []
    for i in range(20):
        y = -24.13 + i * 2.54
        pin_odd = i * 2 + 1
        pin_even = i * 2 + 2
        pins_left.append(f'      (pin passive line (at -7.62 {y:.2f} 0) (length 2.54)\n        (name "Pin_{pin_odd}" (effects (font (size 1.0 1.0))))\n        (number "{pin_odd}" (effects (font (size 1.0 1.0)))))')
        pins_right.append(f'      (pin passive line (at 7.62 {y:.2f} 180) (length 2.54)\n        (name "Pin_{pin_even}" (effects (font (size 1.0 1.0))))\n        (number "{pin_even}" (effects (font (size 1.0 1.0)))))')

    lib_symbols.append(f'''    (symbol "gpio-only-hat:Conn_02x20" (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 -27.94 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Conn_02x20" (at 0 27.94 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-only-hat:Conn_02x20_0_1"
        (rectangle (start -5.08 -25.4) (end 5.08 25.4)
          (stroke (width 0.254) (type default))
          (fill (type background)))
      )
      (symbol "gpio-only-hat:Conn_02x20_1_1"
{chr(10).join(pins_left)}
{chr(10).join(pins_right)}
      )
    )''')

    # ── Symbol: Screw Terminal 2-pin ──
    lib_symbols.append(f'''    (symbol "gpio-only-hat:Screw_Terminal_01x02" (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Screw_Terminal" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-only-hat:Screw_Terminal_01x02_0_1"
        (rectangle (start -2.54 -2.54) (end 2.54 2.54)
          (stroke (width 0.254) (type default))
          (fill (type background)))
      )
      (symbol "gpio-only-hat:Screw_Terminal_01x02_1_1"
        (pin passive line (at -5.08 1.27 0) (length 2.54)
          (name "SIG" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at -5.08 -1.27 0) (length 2.54)
          (name "GND" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # ── Symbol: R ──
    lib_symbols.append(f'''    (symbol "gpio-only-hat:R" (in_bom yes) (on_board yes)
      (property "Reference" "R" (at 1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Value" "R" (at -1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Footprint" "Resistor_SMD:R_0805_2012Metric" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-only-hat:R_0_1"
        (rectangle (start -0.762 -2.286) (end 0.762 2.286)
          (stroke (width 0.254) (type default))
          (fill (type none)))
      )
      (symbol "gpio-only-hat:R_1_1"
        (pin passive line (at 0 -3.81 90) (length 1.524)
          (name "1" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 0 3.81 270) (length 1.524)
          (name "2" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # ── Symbol: C ──
    lib_symbols.append(f'''    (symbol "gpio-only-hat:C" (in_bom yes) (on_board yes)
      (property "Reference" "C" (at 1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Value" "C" (at -1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Footprint" "Capacitor_SMD:C_0805_2012Metric" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-only-hat:C_0_1"
        (polyline (pts (xy -1.27 0.508) (xy 1.27 0.508)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -1.27 -0.508) (xy 1.27 -0.508)) (stroke (width 0.254) (type default)) (fill (type none)))
      )
      (symbol "gpio-only-hat:C_1_1"
        (pin passive line (at 0 2.54 270) (length 2.032)
          (name "1" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 0 -2.54 90) (length 2.032)
          (name "2" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # ── Power symbols ──
    for pname in ["+3V3", "+5V", "GND"]:
        direction = "270" if pname == "GND" else "90"
        lib_symbols.append(f'''    (symbol "gpio-only-hat:{pname}" (power) (in_bom yes) (on_board yes)
      (property "Reference" "#PWR" (at 0 2.54 0) (effects (font (size 1.0 1.0)) hide))
      (property "Value" "{pname}" (at 0 3.81 0) (effects (font (size 1.0 1.0))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-only-hat:{pname}_0_1"
        (polyline (pts (xy 0 0) (xy 0 1.27)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy -0.762 1.27) (xy 0.762 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
      )
      (symbol "gpio-only-hat:{pname}_1_1"
        (pin power_in line (at 0 0 {direction}) (length 0)
          (name "{pname}" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # ── Helpers ──
    def place(lib_id, ref, value, x, y, angle=0, fp="", pins=None):
        u = uid()
        pin_lines = ""
        if pins:
            pin_lines = "\n".join(f'    (pin "{p}" (uuid "{uid()}"))' for p in pins)
        components.append(f'''  (symbol (lib_id "{lib_id}")
    (at {x:.2f} {y:.2f} {angle})
    (unit 1)
    (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (uuid "{u}")
    (property "Reference" "{ref}" (at {x:.2f} {y-3.81:.2f} 0) (effects (font (size 1.27 1.27))))
    (property "Value" "{value}" (at {x:.2f} {y+3.81:.2f} 0) (effects (font (size 1.27 1.27))))
    (property "Footprint" "{fp}" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))
    (property "Datasheet" "" (at {x:.2f} {y:.2f} 0) (effects (font (size 1.27 1.27)) hide))
{pin_lines}
    (instances (project "gpio-only-hat" (path "/{root}" (reference "{ref}") (unit 1))))
  )''')

    def glabel(name, x, y, angle=0):
        labels.append(f'''  (global_label "{name}" (shape bidirectional) (at {x:.2f} {y:.2f} {angle}) (uuid "{uid()}")
    (effects (font (size 1.27 1.27)))
  )''')

    def wire(x1, y1, x2, y2):
        wires.append(f'  (wire (pts (xy {x1:.2f} {y1:.2f}) (xy {x2:.2f} {y2:.2f})))')

    def text(txt, x, y, size=2.0):
        texts.append(f'  (text "{txt}" (at {x:.2f} {y:.2f} 0) (effects (font (size {size} {size}) bold)))')

    def place_pwr(sym, x, y, angle=0):
        ref = pwr_ref()
        place(f"gpio-only-hat:{sym}", ref, sym, x, y, angle, pins=["1"])

    # ═══════════════════════════════════════════════════════════════════════
    # RPi 40-Pin Header
    # ═══════════════════════════════════════════════════════════════════════
    text("── RPi 40-Pin GPIO Header ──", 20, 20)

    hdr_x, hdr_y = 55.88, 120
    place("gpio-only-hat:Conn_02x20", "J1", "RPi_GPIO_40Pin", hdr_x, hdr_y,
          fp="Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical",
          pins=[str(p) for p in range(1, 41)])

    lx = hdr_x - 7.62
    rx = hdr_x + 7.62

    def pin_y(pin_num):
        row = (pin_num - 1) // 2 if pin_num % 2 == 1 else (pin_num - 2) // 2
        return hdr_y - 24.13 + row * 2.54

    # Power
    glabel("+3V3", lx - 2.54, pin_y(1), 180)
    wire(lx, pin_y(1), lx - 2.54, pin_y(1))
    glabel("+5V", rx + 2.54, pin_y(2), 0)
    wire(rx, pin_y(2), rx + 2.54, pin_y(2))

    # GND
    for gnd_pin in [6, 9, 14, 20, 25, 30, 34, 39]:
        if gnd_pin % 2 == 0:
            glabel("GND", rx + 2.54, pin_y(gnd_pin), 0)
            wire(rx, pin_y(gnd_pin), rx + 2.54, pin_y(gnd_pin))
        else:
            glabel("GND", lx - 2.54, pin_y(gnd_pin), 180)
            wire(lx, pin_y(gnd_pin), lx - 2.54, pin_y(gnd_pin))

    # GPIO button pins — original app pins, alle frei (kein I2S-Konflikt)
    gpio_button_pins = {
        4: 7, 17: 11, 18: 12, 22: 15,
        23: 16, 24: 18, 25: 22, 27: 13,
    }
    for gpio, phys_pin in gpio_button_pins.items():
        if phys_pin % 2 == 0:
            glabel(f"GPIO{gpio}", rx + 2.54, pin_y(phys_pin), 0)
            wire(rx, pin_y(phys_pin), rx + 2.54, pin_y(phys_pin))
        else:
            glabel(f"GPIO{gpio}", lx - 2.54, pin_y(phys_pin), 180)
            wire(lx, pin_y(phys_pin), lx - 2.54, pin_y(phys_pin))

    # ═══════════════════════════════════════════════════════════════════════
    # 8x GPIO Schraubklemmen mit RC-Entprellung
    # ═══════════════════════════════════════════════════════════════════════
    text("── GPIO Taster (Schraubklemmen + RC-Entprellung) ──", 120, 20)

    gpio_list = [4, 17, 18, 22, 23, 24, 25, 27]
    for i, gpio in enumerate(gpio_list):
        # 2 Spalten à 4
        col = i // 4
        row = i % 4
        tx = 160 + col * 90
        ty = 50 + row * 40

        jref = f"J{2+i}"

        # Screw terminal
        place("gpio-only-hat:Screw_Terminal_01x02", jref, f"GPIO{gpio}", tx, ty,
              fp="TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
              pins=["1", "2"])

        # RC debounce: 10k + 100nF
        rref = f"R{1+i}"
        cref = f"C{1+i}"

        place("gpio-only-hat:R", rref, "10k", tx + 12, ty + 1.27, 90,
              fp="Resistor_SMD:R_0805_2012Metric", pins=["1", "2"])
        place("gpio-only-hat:C", cref, "100nF", tx + 22, ty + 1.27, 0,
              fp="Capacitor_SMD:C_0805_2012Metric", pins=["1", "2"])

        # Wiring: terminal → R → node → C → GND, node → GPIO label
        wire(tx - 5.08, ty + 1.27, tx + 8.19, ty + 1.27)
        wire(tx + 15.81, ty + 1.27, tx + 22, ty + 1.27)
        glabel(f"GPIO{gpio}", tx + 22, ty - 3, 90)
        wire(tx + 22, ty + 1.27, tx + 22, ty - 1.27)
        place_pwr("GND", tx + 22, ty + 6.5, 0)
        wire(tx + 22, ty + 3.81, tx + 22, ty + 6.5)

        # Terminal GND
        place_pwr("GND", tx - 5.08, ty - 3, 0)
        wire(tx - 5.08, ty - 1.27, tx - 5.08, ty - 3)

    # Notes
    text("── Hinweise ──", 120, 220)
    texts.append(f'  (text "RC-Entprellung: 10k + 100nF → τ ≈ 1ms" (at 120 230 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "Software-Debounce (200ms) kommt zusätzlich im GPIO-Daemon" (at 120 236 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "Audio über 3.5mm Klinke des Raspberry Pi direkt" (at 120 242 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "GPIO-Pins: 4, 17, 18, 22, 23, 24, 25, 27 (identisch mit app.py)" (at 120 248 0) (effects (font (size 1.5 1.5))))')

    # ── Assemble ──
    return f'''(kicad_sch
  (version 20231120)
  (generator "eeschema")
  (generator_version "8.0")
  (uuid "{root}")
  (paper "A3")

  (lib_symbols
{chr(10).join(lib_symbols)}
  )

{chr(10).join(components)}
{chr(10).join(labels)}
{chr(10).join(wires)}
{chr(10).join(texts)}
)
'''


def generate_pcb():
    holes = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
    hole_fps = []
    for i, (hx, hy) in enumerate(holes):
        hole_fps.append(f'''  (footprint "MountingHole:MountingHole_2.7mm_M2.5"
    (layer "F.Cu")
    (uuid "{uid()}")
    (at {hx} {hy})
    (property "Reference" "H{i+1}" (at 0 -3 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1 1))))
    (property "Value" "MountingHole_M2.5" (at 0 3 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 1 1))))
    (pad "" thru_hole circle (at 0 0) (size 5.5 5.5) (drill 2.75) (layers "*.Cu" "*.Mask"))
  )''')

    return f'''(kicad_pcb
  (version 20240108)
  (generator "pcbnew")
  (generator_version "8.0")
  (general
    (thickness 1.6)
    (legacy_teardrops no)
  )
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user "B.Mask")
    (39 "F.Mask" user "F.Mask")
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user "B.Fabrication")
    (49 "F.Fab" user "F.Fabrication")
  )
  (setup
    (pad_to_mask_clearance 0.05)
    (allow_soldermask_bridges_in_footprints no)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
    )
  )
  (net 0 "")

  ;; Board outline - RPi HAT 65x56mm, 3mm corner radius
  (gr_arc (start 3 0) (mid 0.879 0.879) (end 0 3) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 3 0) (end 62 0) (layer "Edge.Cuts") (width 0.15))
  (gr_arc (start 65 3) (mid 64.121 0.879) (end 62 0) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 65 3) (end 65 53) (layer "Edge.Cuts") (width 0.15))
  (gr_arc (start 62 56) (mid 64.121 55.121) (end 65 53) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 62 56) (end 3 56) (layer "Edge.Cuts") (width 0.15))
  (gr_arc (start 0 53) (mid 0.879 55.121) (end 3 56) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 0 53) (end 0 3) (layer "Edge.Cuts") (width 0.15))

{chr(10).join(hole_fps)}

  (gr_text "GPIO-Only HAT" (at 32.5 25) (layer "F.SilkS") (uuid "{uid()}")
    (effects (font (size 2 2) (thickness 0.3)))
  )
  (gr_text "8x Schraubklemmen · RPi 3/4" (at 32.5 29) (layer "F.SilkS") (uuid "{uid()}")
    (effects (font (size 1.2 1.2) (thickness 0.2)))
  )
  (gr_text "40-Pin Header" (at 10 50) (layer "F.Fab") (uuid "{uid()}")
    (effects (font (size 1 1)))
  )
  (gr_text "Screw Terminals" (at 45 35) (layer "F.Fab") (uuid "{uid()}")
    (effects (font (size 1 1)))
  )
)
'''


if __name__ == "__main__":
    import os
    base = os.path.dirname(os.path.abspath(__file__))

    print("Generating GPIO-Only HAT...")
    with open(os.path.join(base, "gpio-only-hat.kicad_sch"), "w") as f:
        f.write(generate_schematic())
    with open(os.path.join(base, "gpio-only-hat.kicad_pcb"), "w") as f:
        f.write(generate_pcb())
    print("Done! Open gpio-only-hat.kicad_pro in KiCad 8.")
    print("\nGPIO-Pins: 4, 17, 18, 22, 23, 24, 25, 27")
    print("(Identisch mit app.py — kein I2S-Konflikt)")
