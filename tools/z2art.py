"""Pull Link's side-view frames out of Zelda II CHR (bank 2, 8x16 sprite tiles)."""
import os
# folder with the two original ROMs: set the SMB_LINK_ROMS environment variable to use another one
ROM_DIR = os.environ.get("SMB_LINK_ROMS", r"S:\Roms\NES")
ROM = os.path.join(ROM_DIR, "Zelda II - The Adventure of Link (USA).nes")
_rom = open(ROM, "rb").read()
CHR = _rom[16 + 131072:]
BANK = 2

def tile816(t):
    base = BANK * 4096 + (t & 0xFE) * 16
    rows = []
    for half in range(2):
        for r in range(8):
            lo = CHR[base + half * 16 + r]; hi = CHR[base + half * 16 + r + 8]
            rows.append([((lo >> (7 - b)) & 1) | (((hi >> (7 - b)) & 1) << 1) for b in range(8)])
    return rows

def compose(cols, rows_n=2):
    """cols: list of rows; each row a list of 8x16 tile ids (None = blank). Returns grid[y][x]."""
    h = 16 * len(cols); w = 8 * max(len(r) for r in cols)
    g = [[0] * w for _ in range(h)]
    for ri, row in enumerate(cols):
        for ci, t in enumerate(row):
            if t is None: continue
            px = tile816(t)
            for y in range(16):
                for x in range(8):
                    g[ri * 16 + y][ci * 8 + x] = px[y][x]
    return g

FRAMES = {
    "stand":  [[0x00, 0x02], [0x26, 0x06]],
    "walkA":  [[0x08, 0x0A], [0x0C, 0x0E]],
    "walkB":  [[0x00, 0x02], [0x10, 0x12]],
    "walkC":  [[0x00, 0x02], [0x04, 0x06]],
    "crouch": [[0x46, 0x48], [0x4A, 0x4C]],
    "windup": [[0x28, 0x2A, 0x30], [0x2C, 0x2E, None]],
    "thrust": [[0x32, 0x34, 0x36, 0x38], [None, None, 0x3A, 0x3C]],
    "death":  [[0x14, 0x16], [0x18, 0x1A]],
}

def show(g):
    return "\n".join("".join(".123"[c] for c in row) for row in g)

if __name__ == "__main__":
    import sys
    for n in (sys.argv[1:] or FRAMES):
        print(n); print(show(compose(FRAMES[n]))); print()
