"""Render the sprites from an emulator dump of Zelda II (OAM + palette + MMC1 state)."""
import sys
from PIL import Image

ROM = r"S:\Roms\NES\Zelda II - The Adventure of Link (USA).nes"
NESPAL = [(84,84,84),(0,30,116),(8,16,144),(48,0,136),(68,0,100),(92,0,48),(84,4,0),(60,24,0),(32,42,0),(8,58,0),(0,64,0),(0,60,0),(0,50,60),(0,0,0),(0,0,0),(0,0,0),
(152,150,152),(8,76,196),(48,50,236),(92,30,228),(136,20,176),(160,20,100),(152,34,32),(120,60,0),(84,90,0),(40,114,0),(8,124,0),(0,118,40),(0,102,120),(0,0,0),(0,0,0),(0,0,0),
(236,238,236),(76,154,236),(120,124,236),(176,98,236),(228,84,236),(236,88,180),(236,106,100),(212,136,32),(160,170,0),(116,196,0),(76,208,32),(56,204,108),(56,180,204),(60,60,60),(0,0,0),(0,0,0),
(236,238,236),(168,204,236),(188,188,236),(212,178,236),(236,174,236),(236,174,212),(236,180,176),(228,196,144),(204,210,120),(180,222,120),(168,226,144),(152,226,180),(160,214,228),(160,162,160),(0,0,0),(0,0,0)]

rom = open(ROM, "rb").read()
CHR = rom[16 + 131072:]


def load(path):
    d = open(path, "rb").read()
    st = d[2048 + 256 + 32 + 2048:]
    return dict(ram=d[:2048], oam=d[2048:2304], pal=d[2304:2336], ctrl=st[0], m1ctrl=st[2], chr0=st[3], chr1=st[4])


def chroff(dm, half):
    if dm["m1ctrl"] & 0x10:
        return (dm["chr0"] if half == 0 else dm["chr1"]) * 4096
    return (dm["chr0"] & 0x1E) * 4096 + half * 4096


def tile_pixels(dm, tile16):
    """8x16 sprite tile -> 16 rows of 8 color indices."""
    base = chroff(dm, tile16 & 1) + (tile16 & 0xFE) * 16
    rows = []
    for half in range(2):
        for r in range(8):
            lo = CHR[base + half * 16 + r]; hi = CHR[base + half * 16 + r + 8]
            rows.append([((lo >> (7 - b)) & 1) | (((hi >> (7 - b)) & 1) << 1) for b in range(8)])
    return rows


def sprites(dm, pal_filter=None):
    out = []
    for i in range(64):
        y, t, a, x = dm["oam"][i * 4:i * 4 + 4]
        if y >= 0xEF:
            continue
        if pal_filter is not None and (a & 3) not in pal_filter:
            continue
        out.append((i, x, y + 1, t, a))
    return out


def render(dm, sprs, scale=6, pad=4):
    xs = [s[1] for s in sprs]; ys = [s[2] for s in sprs]
    x0, y0 = min(xs) - pad, min(ys) - pad
    W, H = max(xs) + 8 + pad - x0, max(ys) + 16 + pad - y0
    img = Image.new("RGB", (W, H), (255, 0, 255))
    for (i, x, y, t, a) in reversed(sprs):
        px = tile_pixels(dm, t)
        for r in range(16):
            rr = 15 - r if a & 0x80 else r
            for b in range(8):
                bb = 7 - b if a & 0x40 else b
                c = px[rr][bb]
                if c:
                    img.putpixel((x - x0 + b, y - y0 + r), NESPAL[dm["pal"][0x10 + (a & 3) * 4 + c] & 63])
    return img.resize((W * scale, H * scale), Image.NEAREST)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        dm = load(p)
        s = sprites(dm)
        print(p, "pal", " ".join("%02X" % v for v in dm["pal"][16:]), "chr", dm["m1ctrl"], dm["chr0"], dm["chr1"])
        for e in s:
            print("  oam%02d x=%3d y=%3d t=%02X a=%02X" % e)
        if s:
            render(dm, s).save(p.replace(".bin", ".png"))
