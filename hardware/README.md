# Hardware-Ideen

Konzepte für HAT-Boards (Raspberry Pi 3/4), passend zum Audio Konfigurator.

## Varianten

| Variante | Beschreibung | Komplexität |
|----------|-------------|-------------|
| **[gpio-only-hat](gpio-only-hat/)** | 8x Schraubklemmen + RC-Entprellung, kein Audio-Codec | Einfach (auch Lochraster) |
| **[gpio-audio-hat](gpio-audio-hat/)** | WM8960 Codec + Line-In/Out (3.5mm + Cinch) + 8x Schraubklemmen | Mittel (PCB nötig) |

Beide als KiCad 8 Projekte mit Generator-Scripts.
