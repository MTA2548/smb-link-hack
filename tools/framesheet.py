"""Render every player frame from the built ROM (graphics table + CHR banks) for checking."""
import sys
from PIL import Image, ImageDraw
sys.path.insert(0, r"S:\Roms\NES\SMB Link Hack\tools")
from z2view import NESPAL
rom = open(r"S:\Roms\NES\SMB Link Hack\Super Mario Bros. - Link Hack.nes", "rb").read()
prg = rom[16:16 + 65536]; chr_ = rom[16 + 65536:]
bank1 = prg[0x4000:0x8000]
gt = int(sys.argv[1], 16)                    # GfxTable address
table = bank1[gt - 0xC000:gt - 0xC000 + 0xD8]
pc = int(sys.argv[2], 16)                    # PlayerColors address
cols = bank1[pc - 0xC000:pc - 0xC000 + 16]
names = ["walk1", "walk2", "walk3", "skid", "jump", "swim1", "swim2", "swim3", "climb1", "climb2", "crouch", "throw",
         "s.walk1", "s.walk2", "s.walk3", "s.skid", "s.jump", "s.swim1", "s.swim2", "s.swim3", "s.climb1", "s.climb2", "s.killed",
         "s.stand", "grow", "stand", "death"]
S = 4
img = Image.new("RGB", (27 * 20 * S, 4 * 40 * S), (0x50, 0x50, 0x90))
d = ImageDraw.Draw(img)
for row, palrow in enumerate(range(4)):
    pal = [None] + [NESPAL[c] for c in cols[palrow * 4 + 1:palrow * 4 + 4]]
    for i, off in enumerate(range(0, 0xD8, 8)):
        small = 0x60 <= off < 0xB8
        bank = 2 if small else 0
        for k in range(8):
            t = table[off + k]
            base = bank * 0x1000 + t * 16
            for y in range(8):
                lo, hi = chr_[base + y], chr_[base + y + 8]
                for x in range(8):
                    c = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
                    if c:
                        px = i * 20 + (k & 1) * 8 + x; py = row * 40 + (k >> 1) * 8 + y + 2
                        d.rectangle([px * S, py * S, px * S + S - 1, py * S + S - 1], fill=pal[c])
        if row == 0:
            d.text((i * 20 * S, 0), names[i], fill=(255, 255, 255))
img.save("framesheet.png")
