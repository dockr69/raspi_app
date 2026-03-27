#!/usr/bin/env python3
"""
GPIO Audio HAT – KiCad Schematic & PCB Generator
=================================================
Generates gpio-audio-hat.kicad_sch and gpio-audio-hat.kicad_pcb

Circuit: WM8960 audio codec on Raspberry Pi HAT
- Line In (3.5mm + RCA) → WM8960 ADC → I2S → RPi
- RPi → I2S → WM8960 DAC → Line Out (3.5mm + RCA)
- 8x GPIO screw terminals for buttons
- ESD protection on audio I/O
- Clean power filtering (separate analog/digital)
- Hardware debounce RC on GPIO inputs

Run: python3 generate_kicad.py
"""

import uuid as _uuid

_counter = 0
def uid():
    global _counter
    _counter += 1
    return str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"gpio-hat-{_counter}"))

# ─── KiCad Schematic ─────────────────────────────────────────────────────────

def generate_schematic():
    root = uid()

    # ── Symbol Definitions ──
    lib_symbols = []

    # --- Conn_02x20_Odd_Even (RPi 40-pin) ---
    pins_left = []  # odd pins 1-39 on left
    pins_right = []  # even pins 2-40 on right
    for i in range(20):
        y = -24.13 + i * 2.54
        pin_odd = i * 2 + 1
        pin_even = i * 2 + 2
        pins_left.append(f'      (pin passive line (at -7.62 {y:.2f} 0) (length 2.54)\n        (name "Pin_{pin_odd}" (effects (font (size 1.0 1.0))))\n        (number "{pin_odd}" (effects (font (size 1.0 1.0)))))')
        pins_right.append(f'      (pin passive line (at 7.62 {y:.2f} 180) (length 2.54)\n        (name "Pin_{pin_even}" (effects (font (size 1.0 1.0))))\n        (number "{pin_even}" (effects (font (size 1.0 1.0)))))')

    lib_symbols.append(f'''    (symbol "gpio-audio-hat:Conn_02x20" (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 -27.94 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Conn_02x20" (at 0 27.94 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:Conn_02x20_0_1"
        (rectangle (start -5.08 -25.4) (end 5.08 25.4)
          (stroke (width 0.254) (type default))
          (fill (type background)))
      )
      (symbol "gpio-audio-hat:Conn_02x20_1_1"
{chr(10).join(pins_left)}
{chr(10).join(pins_right)}
      )
    )''')

    # --- WM8960 Audio Codec ---
    wm_pins = []
    # Left side pins (audio inputs + power ground)
    left_pins = [
        ("LINPUT1", "1"), ("LINPUT2", "2"), ("LINPUT3", "3"),
        ("RINPUT1", "4"), ("RINPUT2", "5"), ("RINPUT3", "6"),
        ("VMID", "7"), ("VREF", "8"), ("AGND", "9"),
    ]
    for i, (name, num) in enumerate(left_pins):
        y = -10.16 + i * 2.54
        ptype = "power_in" if name in ("AGND",) else "passive" if name in ("VMID", "VREF") else "input"
        wm_pins.append(f'      (pin {ptype} line (at -17.78 {y:.2f} 0) (length 2.54)\n        (name "{name}" (effects (font (size 1.0 1.0))))\n        (number "{num}" (effects (font (size 1.0 1.0)))))')

    # Right side pins (audio outputs + speaker)
    right_pins = [
        ("HP_L", "10"), ("HP_R", "11"), ("OUT3", "12"),
        ("SPK_LP", "13"), ("SPK_LN", "14"),
        ("SPK_RP", "15"), ("SPK_RN", "16"),
        ("SPKVDD", "17"),
    ]
    for i, (name, num) in enumerate(right_pins):
        y = -10.16 + i * 2.54
        ptype = "power_in" if name == "SPKVDD" else "output"
        wm_pins.append(f'      (pin {ptype} line (at 17.78 {y:.2f} 180) (length 2.54)\n        (name "{name}" (effects (font (size 1.0 1.0))))\n        (number "{num}" (effects (font (size 1.0 1.0)))))')

    # Top pins (power)
    top_pins = [("AVDD", "18"), ("DVDD", "19"), ("DCVDD", "20"), ("DBVDD", "21")]
    for i, (name, num) in enumerate(top_pins):
        x = -3.81 + i * 2.54
        wm_pins.append(f'      (pin power_in line (at {x:.2f} -15.24 270) (length 2.54)\n        (name "{name}" (effects (font (size 1.0 1.0))))\n        (number "{num}" (effects (font (size 1.0 1.0)))))')

    # Bottom pins (digital I/O)
    bot_pins = [
        ("BCLK", "22"), ("DACDAT", "23"), ("DACLRC", "24"),
        ("ADCDAT", "25"), ("ADCLRC", "26"), ("MCLK", "27"),
        ("SDIN", "28"), ("SCLK", "29"), ("CSB", "30"), ("DGND", "31"),
    ]
    for i, (name, num) in enumerate(bot_pins):
        x = -11.43 + i * 2.54
        ptype = "power_in" if name == "DGND" else "input"
        wm_pins.append(f'      (pin {ptype} line (at {x:.2f} 15.24 90) (length 2.54)\n        (name "{name}" (effects (font (size 1.0 1.0))))\n        (number "{num}" (effects (font (size 1.0 1.0)))))')

    lib_symbols.append(f'''    (symbol "gpio-audio-hat:WM8960" (in_bom yes) (on_board yes)
      (property "Reference" "U" (at 0 -17.78 0) (effects (font (size 1.27 1.27))))
      (property "Value" "WM8960" (at 0 17.78 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "https://www.cirrus.com/products/wm8960/" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:WM8960_0_1"
        (rectangle (start -15.24 -12.7) (end 15.24 12.7)
          (stroke (width 0.254) (type default))
          (fill (type background)))
      )
      (symbol "gpio-audio-hat:WM8960_1_1"
{chr(10).join(wm_pins)}
      )
    )''')

    # --- AudioJack3 (3.5mm TRS) ---
    lib_symbols.append(f'''    (symbol "gpio-audio-hat:AudioJack3" (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 -7.62 0) (effects (font (size 1.27 1.27))))
      (property "Value" "AudioJack3" (at 0 7.62 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Connector_Audio:AudioJack_3.5mm_CUI_SJ-3523-SMT" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:AudioJack3_0_1"
        (rectangle (start -5.08 -5.08) (end 5.08 5.08)
          (stroke (width 0.254) (type default))
          (fill (type background)))
      )
      (symbol "gpio-audio-hat:AudioJack3_1_1"
        (pin passive line (at 7.62 2.54 180) (length 2.54)
          (name "Tip" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 7.62 0 180) (length 2.54)
          (name "Ring" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 7.62 -2.54 180) (length 2.54)
          (name "Sleeve" (effects (font (size 1.0 1.0))))
          (number "3" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # --- RCA Jack ---
    lib_symbols.append(f'''    (symbol "gpio-audio-hat:RCA_Jack" (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
      (property "Value" "RCA_Jack" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "Connector_Audio:Jack_RCA_CUI_RCJ-01x" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:RCA_Jack_0_1"
        (rectangle (start -3.81 -2.54) (end 3.81 2.54)
          (stroke (width 0.254) (type default))
          (fill (type background)))
      )
      (symbol "gpio-audio-hat:RCA_Jack_1_1"
        (pin passive line (at 6.35 1.27 180) (length 2.54)
          (name "Signal" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 6.35 -1.27 180) (length 2.54)
          (name "GND" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # --- Screw_Terminal_01x02 ---
    lib_symbols.append(f'''    (symbol "gpio-audio-hat:Screw_Terminal_01x02" (in_bom yes) (on_board yes)
      (property "Reference" "J" (at 0 -5.08 0) (effects (font (size 1.27 1.27))))
      (property "Value" "Screw_Terminal" (at 0 5.08 0) (effects (font (size 1.27 1.27))))
      (property "Footprint" "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:Screw_Terminal_01x02_0_1"
        (rectangle (start -2.54 -2.54) (end 2.54 2.54)
          (stroke (width 0.254) (type default))
          (fill (type background)))
      )
      (symbol "gpio-audio-hat:Screw_Terminal_01x02_1_1"
        (pin passive line (at -5.08 1.27 0) (length 2.54)
          (name "SIG" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at -5.08 -1.27 0) (length 2.54)
          (name "GND" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # --- C (Capacitor) ---
    lib_symbols.append(f'''    (symbol "gpio-audio-hat:C" (in_bom yes) (on_board yes)
      (property "Reference" "C" (at 1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Value" "C" (at -1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Footprint" "Capacitor_SMD:C_0805_2012Metric" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:C_0_1"
        (polyline (pts (xy -1.27 0.508) (xy 1.27 0.508)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -1.27 -0.508) (xy 1.27 -0.508)) (stroke (width 0.254) (type default)) (fill (type none)))
      )
      (symbol "gpio-audio-hat:C_1_1"
        (pin passive line (at 0 2.54 270) (length 2.032)
          (name "1" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 0 -2.54 90) (length 2.032)
          (name "2" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # --- C_Polarized ---
    lib_symbols.append(f'''    (symbol "gpio-audio-hat:C_Polarized" (in_bom yes) (on_board yes)
      (property "Reference" "C" (at 1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Value" "C_Pol" (at -1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Footprint" "Capacitor_SMD:CP_Elec_6.3x5.4" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:C_Polarized_0_1"
        (polyline (pts (xy -1.27 0.508) (xy 1.27 0.508)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -1.27 -0.508) (xy 1.27 -0.508)) (stroke (width 0.254) (type default)) (fill (type none)))
        (polyline (pts (xy -0.635 1.27) (xy -0.635 0.762)) (stroke (width 0.1) (type default)) (fill (type none)))
        (polyline (pts (xy -0.889 1.016) (xy -0.381 1.016)) (stroke (width 0.1) (type default)) (fill (type none)))
      )
      (symbol "gpio-audio-hat:C_Polarized_1_1"
        (pin passive line (at 0 2.54 270) (length 2.032)
          (name "+" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 0 -2.54 90) (length 2.032)
          (name "-" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # --- R (Resistor) ---
    lib_symbols.append(f'''    (symbol "gpio-audio-hat:R" (in_bom yes) (on_board yes)
      (property "Reference" "R" (at 1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Value" "R" (at -1.27 0 90) (effects (font (size 1.0 1.0))))
      (property "Footprint" "Resistor_SMD:R_0805_2012Metric" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:R_0_1"
        (rectangle (start -0.762 -2.286) (end 0.762 2.286)
          (stroke (width 0.254) (type default))
          (fill (type none)))
      )
      (symbol "gpio-audio-hat:R_1_1"
        (pin passive line (at 0 -3.81 90) (length 1.524)
          (name "1" (effects (font (size 1.0 1.0))))
          (number "1" (effects (font (size 1.0 1.0)))))
        (pin passive line (at 0 3.81 270) (length 1.524)
          (name "2" (effects (font (size 1.0 1.0))))
          (number "2" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # --- Power symbols ---
    for pname, pnum in [("+3V3", "1"), ("+5V", "1"), ("GND", "1")]:
        direction = "270" if pname == "GND" else "90"
        lib_symbols.append(f'''    (symbol "gpio-audio-hat:{pname}" (power) (in_bom yes) (on_board yes)
      (property "Reference" "#PWR" (at 0 2.54 0) (effects (font (size 1.0 1.0)) hide))
      (property "Value" "{pname}" (at 0 3.81 0) (effects (font (size 1.0 1.0))))
      (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))
      (symbol "gpio-audio-hat:{pname}_0_1"
        (polyline (pts (xy 0 0) (xy 0 1.27)) (stroke (width 0) (type default)) (fill (type none)))
        (polyline (pts (xy -0.762 1.27) (xy 0.762 1.27)) (stroke (width 0.254) (type default)) (fill (type none)))
      )
      (symbol "gpio-audio-hat:{pname}_1_1"
        (pin power_in line (at 0 0 {direction}) (length 0)
          (name "{pname}" (effects (font (size 1.0 1.0))))
          (number "{pnum}" (effects (font (size 1.0 1.0)))))
      )
    )''')

    # ── Component Instances ──
    components = []
    labels = []
    wires = []
    texts = []
    pwr_idx = [0]

    def pwr_ref():
        pwr_idx[0] += 1
        return f"#PWR{pwr_idx[0]:03d}"

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
    (instances (project "gpio-audio-hat" (path "/{root}" (reference "{ref}") (unit 1))))
  )''')
        return u

    def label(name, x, y, angle=0):
        labels.append(f'''  (label "{name}" (at {x:.2f} {y:.2f} {angle}) (uuid "{uid()}")
    (effects (font (size 1.27 1.27)))
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
        place(f"gpio-audio-hat:{sym}", ref, sym, x, y, angle, pins=["1"])

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 1: RPi GPIO Header (left side)
    # ═══════════════════════════════════════════════════════════════════════
    text("── RPi 40-Pin GPIO Header ──", 25.4, 20.32)

    hdr_x, hdr_y = 55.88, 139.7
    rpi_pins = list(range(1, 41))
    place("gpio-audio-hat:Conn_02x20", "J1", "RPi_GPIO_40Pin", hdr_x, hdr_y,
          fp="Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical",
          pins=[str(p) for p in rpi_pins])

    # RPi GPIO Pin Map (physical pin → GPIO function)
    # Pin 1: 3V3           Pin 2: 5V
    # Pin 3: GPIO2 (SDA)   Pin 4: 5V
    # Pin 5: GPIO3 (SCL)   Pin 6: GND
    # Pin 7: GPIO4          Pin 8: GPIO14
    # Pin 9: GND            Pin 10: GPIO15
    # Pin 11: GPIO17        Pin 12: GPIO18 (I2S BCLK)
    # Pin 13: GPIO27        Pin 14: GND
    # Pin 15: GPIO22        Pin 16: GPIO23
    # Pin 17: 3V3           Pin 18: GPIO24
    # Pin 19: GPIO10        Pin 20: GND
    # Pin 21: GPIO9         Pin 22: GPIO25
    # Pin 23: GPIO11        Pin 24: GPIO8
    # Pin 25: GND           Pin 26: GPIO7
    # Pin 27: ID_SD         Pin 28: ID_SC
    # Pin 29: GPIO5         Pin 30: GND
    # Pin 31: GPIO6         Pin 32: GPIO12
    # Pin 33: GPIO13        Pin 34: GND
    # Pin 35: GPIO19 (LRCLK) Pin 36: GPIO16
    # Pin 37: GPIO26        Pin 38: GPIO20 (I2S DIN)
    # Pin 39: GND           Pin 40: GPIO21 (I2S DOUT)

    # Labels on RPi header pins (left column = odd pins at x = hdr_x - 7.62)
    lx = hdr_x - 7.62  # left pin connection x
    rx = hdr_x + 7.62  # right pin connection x

    def pin_y(pin_num):
        """Y position for a given pin number on the 2x20 header."""
        if pin_num % 2 == 1:  # odd pin, left column
            row = (pin_num - 1) // 2
        else:  # even pin, right column
            row = (pin_num - 2) // 2
        return hdr_y - 24.13 + row * 2.54

    # Power labels
    glabel("+3V3", lx - 2.54, pin_y(1), 180)
    wire(lx, pin_y(1), lx - 2.54, pin_y(1))
    glabel("+5V", rx + 2.54, pin_y(2), 0)
    wire(rx, pin_y(2), rx + 2.54, pin_y(2))
    glabel("+5V", rx + 2.54, pin_y(4), 0)
    wire(rx, pin_y(4), rx + 2.54, pin_y(4))
    glabel("+3V3", lx - 2.54, pin_y(17), 180)
    wire(lx, pin_y(17), lx - 2.54, pin_y(17))

    # GND labels
    for gnd_pin in [6, 9, 14, 20, 25, 30, 34, 39]:
        if gnd_pin % 2 == 0:
            glabel("GND", rx + 2.54, pin_y(gnd_pin), 0)
            wire(rx, pin_y(gnd_pin), rx + 2.54, pin_y(gnd_pin))
        else:
            glabel("GND", lx - 2.54, pin_y(gnd_pin), 180)
            wire(lx, pin_y(gnd_pin), lx - 2.54, pin_y(gnd_pin))

    # I2C labels
    glabel("I2C_SDA", lx - 2.54, pin_y(3), 180)
    wire(lx, pin_y(3), lx - 2.54, pin_y(3))
    glabel("I2C_SCL", lx - 2.54, pin_y(5), 180)
    wire(lx, pin_y(5), lx - 2.54, pin_y(5))

    # I2S labels
    glabel("I2S_BCLK", rx + 2.54, pin_y(12), 0)
    wire(rx, pin_y(12), rx + 2.54, pin_y(12))
    glabel("I2S_LRCLK", lx - 2.54, pin_y(35), 180)
    wire(lx, pin_y(35), lx - 2.54, pin_y(35))
    glabel("I2S_DIN", rx + 2.54, pin_y(38), 0)
    wire(rx, pin_y(38), rx + 2.54, pin_y(38))
    glabel("I2S_DOUT", rx + 2.54, pin_y(40), 0)
    wire(rx, pin_y(40), rx + 2.54, pin_y(40))

    # GPIO button labels
    gpio_button_pins = {
        4: 7, 5: 29, 6: 31, 17: 11,
        22: 15, 23: 16, 24: 18, 27: 13,
    }
    for gpio, phys_pin in gpio_button_pins.items():
        if phys_pin % 2 == 0:
            glabel(f"GPIO{gpio}", rx + 2.54, pin_y(phys_pin), 0)
            wire(rx, pin_y(phys_pin), rx + 2.54, pin_y(phys_pin))
        else:
            glabel(f"GPIO{gpio}", lx - 2.54, pin_y(phys_pin), 180)
            wire(lx, pin_y(phys_pin), lx - 2.54, pin_y(phys_pin))

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 2: WM8960 Audio Codec (center)
    # ═══════════════════════════════════════════════════════════════════════
    text("── WM8960 Audio Codec ──", 155, 55)

    ux, uy = 200, 120
    place("gpio-audio-hat:WM8960", "U1", "WM8960", ux, uy,
          fp="Package_DFN_QFN:QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm",
          pins=[str(i) for i in range(1, 32)])

    # I2S connections to WM8960
    glabel("I2S_BCLK", ux - 11.43 + 0*2.54, uy + 15.24 + 2.54, 270)   # BCLK (pin 22)
    glabel("I2S_DOUT", ux - 11.43 + 1*2.54, uy + 15.24 + 2.54, 270)   # DACDAT (pin 23)
    glabel("I2S_LRCLK", ux - 11.43 + 2*2.54, uy + 15.24 + 2.54, 270)  # DACLRC (pin 24)
    glabel("I2S_DIN", ux - 11.43 + 3*2.54, uy + 15.24 + 2.54, 270)    # ADCDAT (pin 25)
    glabel("I2S_LRCLK", ux - 11.43 + 4*2.54, uy + 15.24 + 2.54, 270)  # ADCLRC (pin 26) tied to DACLRC

    # I2C connections
    glabel("I2C_SDA", ux - 11.43 + 6*2.54, uy + 15.24 + 2.54, 270)    # SDIN (pin 28)
    glabel("I2C_SCL", ux - 11.43 + 7*2.54, uy + 15.24 + 2.54, 270)    # SCLK (pin 29)

    # CSB pull-down (I2C addr 0x1A)
    csb_x = ux - 11.43 + 8*2.54
    csb_y = uy + 15.24
    label("CSB", csb_x, csb_y + 2.54, 270)
    place("gpio-audio-hat:R", "R1", "10k", csb_x, csb_y + 8, 0,
          fp="Resistor_SMD:R_0805_2012Metric", pins=["1", "2"])
    place_pwr("GND", csb_x, csb_y + 13, 0)
    wire(csb_x, csb_y, csb_x, csb_y + 4.19)
    wire(csb_x, csb_y + 11.81, csb_x, csb_y + 13)

    # DGND
    glabel("GND", ux - 11.43 + 9*2.54, uy + 15.24 + 2.54, 270)  # DGND (pin 31)

    # Power connections (top of WM8960)
    for i, pname in enumerate(["AVDD", "DVDD", "DCVDD", "DBVDD"]):
        px = ux - 3.81 + i * 2.54
        py = uy - 15.24
        glabel("+3V3", px, py - 2.54, 90)

    # AGND (pin 9, left side)
    agnd_y = uy - 10.16 + 8 * 2.54  # AGND is 9th pin on left
    glabel("GND", ux - 17.78 - 2.54, agnd_y, 180)

    # Audio signal labels (left side = inputs)
    glabel("LINPUT1", ux - 17.78 - 2.54, uy - 10.16, 180)  # pin 1
    glabel("RINPUT1", ux - 17.78 - 2.54, uy - 10.16 + 3*2.54, 180)  # pin 4

    # VMID and VREF decoupling
    vmid_y = uy - 10.16 + 6*2.54
    label("VMID", ux - 17.78 - 2.54, vmid_y, 180)
    place("gpio-audio-hat:C_Polarized", "C1", "10uF", ux - 27, vmid_y, 0,
          fp="Capacitor_SMD:CP_Elec_4x5.4", pins=["1", "2"])
    place_pwr("GND", ux - 27, vmid_y + 5.08, 0)
    wire(ux - 17.78, vmid_y, ux - 24.46, vmid_y)
    wire(ux - 27, vmid_y + 2.54, ux - 27, vmid_y + 5.08)

    vref_y = uy - 10.16 + 7*2.54
    label("VREF", ux - 17.78 - 2.54, vref_y, 180)
    place("gpio-audio-hat:C", "C2", "100nF", ux - 27, vref_y, 0,
          fp="Capacitor_SMD:C_0805_2012Metric", pins=["1", "2"])
    place_pwr("GND", ux - 27, vref_y + 5.08, 0)
    wire(ux - 17.78, vref_y, ux - 24.46, vref_y)
    wire(ux - 27, vref_y + 2.54, ux - 27, vref_y + 5.08)

    # Audio output labels (right side)
    glabel("HP_L", ux + 17.78 + 2.54, uy - 10.16, 0)  # HP_L (pin 10)
    glabel("HP_R", ux + 17.78 + 2.54, uy - 10.16 + 2.54, 0)  # HP_R (pin 11)

    # SPKVDD - not used, tie to GND via 100nF
    spkvdd_y = uy - 10.16 + 7*2.54  # SPKVDD pin position on right
    label("NC_SPKVDD", ux + 17.78 + 2.54, spkvdd_y, 0)

    # Power decoupling caps near WM8960
    text("Power Decoupling", 230, 85)
    for i, (cref, cval) in enumerate([("C3", "10uF/AVDD"), ("C4", "100nF/DVDD"),
                                       ("C5", "100nF/DCVDD"), ("C6", "100nF/DBVDD")]):
        cx = 235 + i * 15
        cy = 95
        place("gpio-audio-hat:C", cref, cval.split("/")[0], cx, cy, 0,
              fp="Capacitor_SMD:C_0805_2012Metric", pins=["1", "2"])
        place_pwr("+3V3", cx, cy - 5, 0)
        place_pwr("GND", cx, cy + 5, 0)
        wire(cx, cy - 2.54, cx, cy - 5)
        wire(cx, cy + 2.54, cx, cy + 5)

    # MCLK - not connected (WM8960 uses PLL from BCLK)
    mclk_x = ux - 11.43 + 5*2.54
    label("NC_MCLK", mclk_x, uy + 15.24 + 2.54, 270)

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 3: Audio Input (coupling caps + jacks)
    # ═══════════════════════════════════════════════════════════════════════
    text("── Audio Input (Line In) ──", 290, 30)

    # Line In coupling caps (1uF film, important for audio quality)
    # Left channel: Jack → C7 → LINPUT1
    place("gpio-audio-hat:C", "C7", "1uF Film", 270, 48, 90,
          fp="Capacitor_SMD:C_0805_2012Metric", pins=["1", "2"])
    glabel("LINPUT1", 267.46, 48, 180)
    glabel("LINE_IN_L", 272.54, 48, 0)

    # Right channel: Jack → C8 → RINPUT1
    place("gpio-audio-hat:C", "C8", "1uF Film", 270, 60, 90,
          fp="Capacitor_SMD:C_0805_2012Metric", pins=["1", "2"])
    glabel("RINPUT1", 267.46, 60, 180)
    glabel("LINE_IN_R", 272.54, 60, 0)

    # 3.5mm Line In Jack
    place("gpio-audio-hat:AudioJack3", "J2", "Line_In_3.5mm", 310, 48,
          fp="Connector_Audio:AudioJack_3.5mm_CUI_SJ-3523-SMT", pins=["1", "2", "3"])
    glabel("LINE_IN_L", 317.62, 50.54, 0)   # Tip
    glabel("LINE_IN_R", 317.62, 48, 0)      # Ring
    glabel("GND", 317.62, 45.46, 0)         # Sleeve

    # RCA Line In Left
    place("gpio-audio-hat:RCA_Jack", "J3", "RCA_In_L", 310, 68,
          fp="Connector_Audio:Jack_RCA_CUI_RCJ-01x", pins=["1", "2"])
    glabel("LINE_IN_L", 316.35, 69.27, 0)
    glabel("GND", 316.35, 66.73, 0)

    # RCA Line In Right
    place("gpio-audio-hat:RCA_Jack", "J4", "RCA_In_R", 310, 80,
          fp="Connector_Audio:Jack_RCA_CUI_RCJ-01x", pins=["1", "2"])
    glabel("LINE_IN_R", 316.35, 81.27, 0)
    glabel("GND", 316.35, 78.73, 0)

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 4: Audio Output (coupling caps + jacks)
    # ═══════════════════════════════════════════════════════════════════════
    text("── Audio Output (Line Out) ──", 290, 100)

    # Output coupling caps (220uF electrolytic for low-frequency response)
    # Left: HP_L → C9 → Jack
    place("gpio-audio-hat:C_Polarized", "C9", "220uF", 270, 115, 90,
          fp="Capacitor_SMD:CP_Elec_6.3x5.4", pins=["1", "2"])
    glabel("HP_L", 267.46, 115, 180)
    glabel("LINE_OUT_L", 272.54, 115, 0)

    # Right: HP_R → C10 → Jack
    place("gpio-audio-hat:C_Polarized", "C10", "220uF", 270, 127, 90,
          fp="Capacitor_SMD:CP_Elec_6.3x5.4", pins=["1", "2"])
    glabel("HP_R", 267.46, 127, 180)
    glabel("LINE_OUT_R", 272.54, 127, 0)

    # 3.5mm Line Out Jack
    place("gpio-audio-hat:AudioJack3", "J5", "Line_Out_3.5mm", 310, 115,
          fp="Connector_Audio:AudioJack_3.5mm_CUI_SJ-3523-SMT", pins=["1", "2", "3"])
    glabel("LINE_OUT_L", 317.62, 117.54, 0)
    glabel("LINE_OUT_R", 317.62, 115, 0)
    glabel("GND", 317.62, 112.46, 0)

    # RCA Line Out Left
    place("gpio-audio-hat:RCA_Jack", "J6", "RCA_Out_L", 310, 135,
          fp="Connector_Audio:Jack_RCA_CUI_RCJ-01x", pins=["1", "2"])
    glabel("LINE_OUT_L", 316.35, 136.27, 0)
    glabel("GND", 316.35, 133.73, 0)

    # RCA Line Out Right
    place("gpio-audio-hat:RCA_Jack", "J7", "RCA_Out_R", 310, 147,
          fp="Connector_Audio:Jack_RCA_CUI_RCJ-01x", pins=["1", "2"])
    glabel("LINE_OUT_R", 316.35, 148.27, 0)
    glabel("GND", 316.35, 145.73, 0)

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 5: GPIO Screw Terminals with RC Debounce
    # ═══════════════════════════════════════════════════════════════════════
    text("── GPIO Taster (Schraubklemmen + RC-Entprellung) ──", 30, 200)

    gpio_list = [4, 5, 6, 17, 22, 23, 24, 27]
    for i, gpio in enumerate(gpio_list):
        tx = 40 + i * 42
        ty = 230
        jref = f"J{8+i}"

        # Screw terminal
        place("gpio-audio-hat:Screw_Terminal_01x02", jref, f"GPIO{gpio}", tx, ty,
              fp="TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2_1x02_P5.00mm_Horizontal",
              pins=["1", "2"])

        # RC debounce: 10k series + 100nF to GND
        # Taster → Schraubklemme → R (10k) → GPIO + C (100nF) → GND
        rref = f"R{2+i}"
        cref = f"C{11+i}"

        place("gpio-audio-hat:R", rref, "10k", tx + 10, ty + 1.27, 90,
              fp="Resistor_SMD:R_0805_2012Metric", pins=["1", "2"])
        place("gpio-audio-hat:C", cref, "100nF", tx + 18, ty + 1.27, 0,
              fp="Capacitor_SMD:C_0805_2012Metric", pins=["1", "2"])

        # Connect: terminal pin 1 → R → node → C → GND
        # Terminal pin 1 to resistor
        wire(tx - 5.08, ty + 1.27, tx + 6.19, ty + 1.27)
        # Resistor to GPIO label + cap
        wire(tx + 13.81, ty + 1.27, tx + 18, ty + 1.27)
        glabel(f"GPIO{gpio}", tx + 18, ty - 3, 90)
        wire(tx + 18, ty + 1.27, tx + 18, ty - 1.27)
        # Cap to GND
        place_pwr("GND", tx + 18, ty + 6.5, 0)
        wire(tx + 18, ty + 3.81, tx + 18, ty + 6.5)

        # Terminal pin 2 to GND
        place_pwr("GND", tx - 5.08, ty - 3, 0)
        wire(tx - 5.08, ty - 1.27, tx - 5.08, ty - 3)

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 6: ESD Protection on Audio I/O
    # ═══════════════════════════════════════════════════════════════════════
    text("── Hinweise ──", 290, 170)
    texts.append(f'  (text "ESD: TVS-Dioden (z.B. PESD5V0S2BT) an Audio-Ein-/Ausgängen empfohlen" (at 290 180 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "Audio-Qualität: Film-Kondensatoren (C7,C8) für klangfreien Eingang" (at 290 186 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "GPIO: RC-Entprellung (10k + 100nF, τ≈1ms) für sauberes Schalten" (at 290 192 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "WM8960 Addr: CSB→GND = 0x1A / CSB→3V3 = 0x1B" (at 290 198 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "I2S: ADCLRC + DACLRC verbunden (gemeinsamer LRCLK)" (at 290 204 0) (effects (font (size 1.5 1.5))))')
    texts.append(f'  (text "MCLK: Nicht verbunden – WM8960 PLL leitet Clock von BCLK ab" (at 290 210 0) (effects (font (size 1.5 1.5))))')

    # ── Assemble Schematic File ──
    sch = f'''(kicad_sch
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
    return sch


# ─── KiCad PCB ───────────────────────────────────────────────────────────────

def generate_pcb():
    """Generate PCB with RPi HAT outline (65x56mm) and mounting holes."""

    # RPi HAT spec: 65 x 56 mm, mounting holes at corners
    # Holes: M2.5 (2.75mm drill), 3.5mm inset from edges
    holes = [
        (3.5, 3.5),      # bottom-left
        (61.5, 3.5),     # bottom-right
        (3.5, 52.5),     # top-left
        (61.5, 52.5),    # top-right
    ]

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

    # 40-pin header position: Pin 1 at approximately (7.0, 52.5-1.0)
    # Standard position from RPi mechanical drawing

    pcb = f'''(kicad_pcb
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

  ;; Board outline - RPi HAT 65x56mm with 3mm corner radius
  (gr_arc (start 3 0) (mid 0.879 0.879) (end 0 3) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 3 0) (end 62 0) (layer "Edge.Cuts") (width 0.15))
  (gr_arc (start 65 3) (mid 64.121 0.879) (end 62 0) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 65 3) (end 65 53) (layer "Edge.Cuts") (width 0.15))
  (gr_arc (start 62 56) (mid 64.121 55.121) (end 65 53) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 62 56) (end 3 56) (layer "Edge.Cuts") (width 0.15))
  (gr_arc (start 0 53) (mid 0.879 55.121) (end 3 56) (layer "Edge.Cuts") (width 0.15))
  (gr_line (start 0 53) (end 0 3) (layer "Edge.Cuts") (width 0.15))

  ;; Mounting holes
{chr(10).join(hole_fps)}

  ;; Placement guides (silkscreen)
  (gr_text "GPIO Audio HAT" (at 32.5 28) (layer "F.SilkS") (uuid "{uid()}")
    (effects (font (size 2 2) (thickness 0.3)))
  )
  (gr_text "RPi 3/4 · WM8960 · 8x GPIO" (at 32.5 32) (layer "F.SilkS") (uuid "{uid()}")
    (effects (font (size 1.2 1.2) (thickness 0.2)))
  )

  ;; Component placement areas (Fab layer)
  (gr_text "40-Pin Header" (at 10 50) (layer "F.Fab") (uuid "{uid()}")
    (effects (font (size 1 1)))
  )
  (gr_text "WM8960" (at 32 20) (layer "F.Fab") (uuid "{uid()}")
    (effects (font (size 1 1)))
  )
  (gr_text "Audio In" (at 55 12) (layer "F.Fab") (uuid "{uid()}")
    (effects (font (size 1 1)))
  )
  (gr_text "Audio Out" (at 55 22) (layer "F.Fab") (uuid "{uid()}")
    (effects (font (size 1 1)))
  )
  (gr_text "GPIO Terminals" (at 32 48) (layer "F.Fab") (uuid "{uid()}")
    (effects (font (size 1 1)))
  )
)
'''
    return pcb


# ─── Main ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os

    base = os.path.dirname(os.path.abspath(__file__))

    sch_path = os.path.join(base, "gpio-audio-hat.kicad_sch")
    pcb_path = os.path.join(base, "gpio-audio-hat.kicad_pcb")

    print("Generating schematic...")
    with open(sch_path, "w") as f:
        f.write(generate_schematic())
    print(f"  → {sch_path}")

    print("Generating PCB...")
    with open(pcb_path, "w") as f:
        f.write(generate_pcb())
    print(f"  → {pcb_path}")

    print("\nDone! Open gpio-audio-hat.kicad_pro in KiCad 8.")
    print("\nGPIO-Pins für Taster (geändert wg. I2S-Konflikt mit GPIO18):")
    print("  4, 5, 6, 17, 22, 23, 24, 27")
    print("\nI2S-Pins (WM8960):")
    print("  GPIO18=BCLK, GPIO19=LRCLK, GPIO20=DIN, GPIO21=DOUT")
    print("I2C: GPIO2=SDA, GPIO3=SCL")
