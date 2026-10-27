import sys
sys.path.insert(0, r"S:\Roms\NES\SMB Link Hack\tools")
from PIL import Image
from linkart import BIG, SMALL, BEAM
from z2view import NESPAL
def render(frames, pal, out, S=6):
    W = sum(len(g[0]) + 4 for g in frames); H = 34
    img = Image.new("RGB", (W, H), NESPAL[0x22]); x = 0
    for g in frames:
        for yy, row in enumerate(g):
            for xx, c in enumerate(row):
                if c: img.putpixel((x + xx, 34 - len(g) + yy - 1), NESPAL[pal[c]])
        x += len(g[0]) + 4
    img.resize((W * S, H * S), Image.NEAREST).save(out)
pal = [0, 0x18, 0x36, 0x2A]
render(list(BIG.values()), pal, "prev_big.png")
render(list(SMALL.values()) + [BEAM], pal, "prev_small.png")
print(list(BIG), list(SMALL))
