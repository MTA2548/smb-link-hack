import sys
from PIL import Image, ImageDraw
sys.path.insert(0, r"S:\Roms\NES\SMB Link Hack\tools")
from z2view import CHR, NESPAL
bank = int(sys.argv[1]); out = sys.argv[2]
pal = [None, NESPAL[0x18], NESPAL[0x36], NESPAL[0x2A]]
# 128 8x16 tiles per 4KB bank: show 16 per row, with labels
S = 4
img = Image.new("RGB", (16 * 10 * S, 8 * 22 * S), (255, 0, 255))
d = ImageDraw.Draw(img)
for n in range(128):
    base = bank * 4096 + n * 32
    gx, gy = (n % 16) * 10, (n // 16) * 22
    for half in range(2):
        for r in range(8):
            lo = CHR[base + half * 16 + r]; hi = CHR[base + half * 16 + r + 8]
            for b in range(8):
                c = ((lo >> (7 - b)) & 1) | (((hi >> (7 - b)) & 1) << 1)
                col = pal[c] if c else (40, 40, 40)
                d.rectangle([(gx + b) * S, (gy + half * 8 + r) * S, (gx + b) * S + S - 1, (gy + half * 8 + r) * S + S - 1], fill=col)
    d.text((gx * S, (gy + 16) * S + 2), "%02X" % (n * 2), fill=(255, 255, 255))
img.save(out)
