"""Makes a TEST copy of the hack that starts at the last stretch of World 8-4 (just before Bowser's
bridge) as red-tunic Link, to check the ending with Zelda quickly. The normal ROM is not changed."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = r"S:\Roms\NES\SMB Link Hack"
SRC = os.path.join(ROOT, "Super Mario Bros. - Link Hack.nes")
OUT = os.path.join(ROOT, "Super Mario Bros. - Link Hack (TEST start at end of 8-4).nes")


def patch(rom, addr, new, old):
    o = 16 + addr - 0x8000                       # bank 0 ($8000-$BFFF)
    assert rom[o:o + len(old)] == bytes(old), "unexpected bytes at %04X" % addr
    rom[o:o + len(new)] = bytes(new)


rom = bytearray(open(SRC, "rb").read())
# game start: world 8, level 4 (area 3)
patch(rom, 0x830E, bytes.fromhex("A9078D5F07A2038E60078E5C0760EA"),
      bytes.fromhex("8D5F078D6607A2008E60078E670760"))
patch(rom, 0x82DE, bytes.fromhex("EAEA"), bytes.fromhex("9006"))   # call it on every game start, not just continues
# every level start: begin at page 17 of the level (8-4's last stretch)
#   (world 8 only, so the title screen's own 1-1 still loads normally): lda $075F / cmp #7 / lda #0 / bcc +2 / lda #$11
patch(rom, 0x8FF3, bytes.fromhex("AD5F07C907A9009002A911"), bytes.fromhex("AD5B07AC5207F003AD5107"))
open(OUT, "wb").write(rom)
print("wrote", OUT)

# N64 (Neon64) copy for ares / EverDrive
NEON = r"S:\Roms\N64\tools\neon64\neon64bu.rom"
N64 = r"S:\Roms\N64\Super Mario Bros. - Link Hack (TEST start at end of 8-4) [Neon64].z64"
z = open(NEON, "rb").read() + bytes(rom)
open(N64, "wb").write(z + bytes(2 * 1024 * 1024 - len(z)))
print("wrote", N64)
