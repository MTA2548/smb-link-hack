# Super Mario Bros. - Link Hack

Source code for a Super Mario Bros. (NES) hack that replaces Mario with Link from
*Zelda II: The Adventure of Link*: Link's sprites, sword and sword beam, sounds, knockback and death,
Princess Zelda, rupees, a heart-container 1-Up, and a new Hammer upgrade dropped by Hammer Bros.

**This repository contains no Nintendo ROM data.** The build script reads your own copies of the two
original games and takes Link's graphics and sounds from Zelda II at build time. Only hand-drawn art
(small Link, the Master Sword, the LINK title logo, etc.) is stored here.

To just play the hack, use the IPS patch from the releases instead.

## Building

Requirements: Python 3 (nothing else for the build; some preview helpers use Pillow).

Put these two ROMs in one folder:

| File name | MD5 |
|---|---|
| `Super Mario Bros. (World).nes` | `f94bb9bb55f325d9af8a0fff80b9376d` |
| `Zelda II - The Adventure of Link (USA).nes` | |

Point the `SMB_LINK_ROMS` environment variable at that folder and run the build:

```
set SMB_LINK_ROMS=C:\path\to\roms
python tools\build.py
```

It writes `Super Mario Bros. - Link Hack.nes` and `Super Mario Bros. - Link Hack.ips` in the project
folder.

## What's in `tools/`

| File | Purpose |
|---|---|
| `build.py` | Main builder: converts SMB to the MMC1 mapper, adds the new 6502 code, patches SMB, builds the graphics, writes the ROM and IPS |
| `asm6502.py`, `dis6502.py` | Small 6502 assembler and disassembler used by the builder |
| `linkart.py`, `z2art.py` | Link's frames (from Zelda II, plus hand-drawn small Link and swim frames) |
| `items.py` | Master Sword, magic jar, heart container, hammer, Triforce flag, Princess Zelda |
| `coins.py` | Coins to green rupees, Down+direction handling |
| `titlelogo.py` | The "LINK" title logo |
| `nesemu.c` | Minimal NES emulator for scripted testing (screenshots, RAM dumps, no sound) |
| `make_test84.py` | Makes a test copy that starts at the end of World 8-4 |
| other `.py` files | Debugging and preview helpers |

## Credits

Super Mario Bros. and Zelda II: The Adventure of Link are © Nintendo. This is an unofficial fan
project and is not affiliated with Nintendo.
