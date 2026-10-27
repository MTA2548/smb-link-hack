"""Builds the 'LINK' title logo that replaces 'SUPER MARIO BROS.' on SMB's title screen.

The title screen layout is stored in the background CHR bank at $1EC0 (SMB copies $13A bytes of it
into RAM at boot). The logo letters use tiles that appear nowhere else, so they can be redrawn.
Letters follow the original style: pink face (colour 1) on the brown board (2), with a black
shadow (3) one pixel to the right and four pixels below, offset two pixels.
"""

LAYOUT_AT = 0xEC0          # offset of the layout inside the 4 KB background bank
LAYOUT_MAX = 0x13A         # bytes SMB copies
# Tiles free for the logo in the title-only background bank: the old logo's own tiles, then tiles
# that never appear on the title screen or in the attract demo (measured by running both).
FREE_TILES = (list(range(0xD0, 0xE9)) + [0x42, 0x43] + list(range(0xC0, 0xCE)) + list(range(0x80, 0x95))
              + list(range(0xA0, 0xB4)))
BOARD = 0x26               # plain board tile

ROW0, ROWS = 5, 10         # board inner area: rows 5-13, plus its bottom edge (row 14)
COL0, COLS = 6, 20         # columns 6-25
TOP = 8                    # letters start one tile down (row 6) and are 56 px tall
STROKE = 12                # stroke width in pixels
LETTER_X = [8, 48, 72, 120]   # left edge of L, I, N, K inside the board


def letter_mask():
    """Pixel shapes of L, I, N, K: 12 px strokes, diagonals at 2 px down per 1 px across."""
    H = 56
    shapes = []
    L = lambda x, y: x < STROKE or y >= H - STROKE
    shapes.append((32, L))
    shapes.append((12, lambda x, y: True))                                   # I
    shapes.append((40, lambda x, y: x < STROKE or x >= 40 - STROKE or y // 2 <= x < y // 2 + STROKE))   # N
    def K(x, y):
        if x < STROKE:
            return True
        start = STROKE + (28 - y) // 2 if y < 28 else STROKE + (y - 28) // 2
        return start - 2 <= x < start + STROKE - 2
    shapes.append((38, K))
    W = COLS * 8
    mask = [[False] * W for _ in range(ROWS * 8)]
    for (w, f), x0 in zip(shapes, LETTER_X):        # letters start on tile boundaries (fewer tiles)
        for y in range(H):
            for x in range(w):
                if f(x, y):
                    mask[TOP + y][x0 + x] = True
    return mask


def pixels():
    face = letter_mask()
    W, H = COLS * 8, ROWS * 8
    img = [[2] * W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if face[y][x]:
                img[y][x] = 1
            elif (x >= 1 and face[y][x - 1]) or any(x >= 2 and y - k >= 0 and face[y - k][x - 2] for k in range(1, 5)):
                img[y][x] = 3
    for x in range(W):                      # bottom edge of the board: dark line
        img[H - 1][x] = 3
    return img


def encode(tile):
    b = bytearray(16)
    for y in range(8):
        for x in range(8):
            c = tile[y][x]
            if c & 1: b[y] |= 0x80 >> x
            if c & 2: b[y + 8] |= 0x80 >> x
    return bytes(b)


def build(bg_bank):
    """Return (game bank, title bank): both get the new layout; only the title bank gets the logo tiles,
    since some of the tiles it reuses are needed in other levels."""
    bg = bytearray(bg_bank)
    img = pixels()
    board_pat = encode([[2] * 8 for _ in range(8)])
    assert bytes(bg[BOARD * 16:BOARD * 16 + 16]) == board_pat
    names = {board_pat: BOARD}
    free = list(FREE_TILES)
    rows = []
    for r in range(ROWS):
        line = []
        for c in range(COLS):
            t = [row[c * 8:c * 8 + 8] for row in img[r * 8:r * 8 + 8]]
            pat = encode(t)
            if pat not in names:
                if not free:
                    raise SystemExit("title logo needs too many tiles")
                n = free.pop(0)
                names[pat] = n
                bg[n * 16:n * 16 + 16] = pat
            line.append(names[pat])
        rows.append(line)

    # parse the original layout records
    recs, p = [], LAYOUT_AT
    while bg[p]:
        hi, lo, n = bg[p], bg[p + 1], bg[p + 2]
        size = 1 if n & 0x40 else n & 0x3F
        recs.append(bytes(bg[p:p + 3 + size]))
        p += 3 + size
    addr = lambda rec: (rec[0] << 8) | rec[1]
    rowcol = lambda a: ((a - 0x2000) // 32, (a - 0x2000) % 32)

    def is_logo(rec):
        r, c = rowcol(addr(rec))
        return addr(rec) < 0x2400 and ROW0 <= r < ROW0 + ROWS and c >= COL0 - 1 and not (rec[2] & 0x80)
    keep_before = [rec for rec in recs if rowcol(addr(rec))[0] == 4 or rec[2] & 0x80]   # top border, sides
    keep_after = [rec for rec in recs if rec not in keep_before and not is_logo(rec)]

    out = bytearray()
    for rec in keep_before:
        out += rec
    for r, line in enumerate(rows):
        a = 0x2000 + (ROW0 + r) * 32 + COL0
        if all(t == line[0] for t in line):              # one tile repeated: a short repeat record
            out += bytes([a >> 8, a & 0xFF, 0x40 | COLS, line[0]])
        else:
            out += bytes([a >> 8, a & 0xFF, COLS]) + bytes(line)
    a = 0x2000 + (ROW0 + ROWS - 1) * 32 + COL0 - 1           # bottom corners of the board
    out += bytes([a >> 8, a & 0xFF, 1, 0x5F])
    out += bytes([a >> 8, (a + 1 + COLS) & 0xFF, 1, 0x7A])
    for rec in keep_after:
        out += rec
    out += b"\x00"
    assert len(out) <= LAYOUT_MAX, "title layout too long: %d bytes" % len(out)
    bg[LAYOUT_AT:LAYOUT_AT + len(out)] = out
    game = bytearray(bg_bank)
    game[LAYOUT_AT:LAYOUT_AT + len(out)] = out
    used = len(FREE_TILES) - len(free)
    return bytes(game), bytes(bg), used, len(out)


if __name__ == "__main__":
    import os
    from z2art import ROM_DIR
    rom = open(os.path.join(ROM_DIR, "Super Mario Bros. (World).nes"), "rb").read()
    game, bg, used, n = build(rom[16 + 0x8000 + 0x1000:16 + 0x8000 + 0x2000])
    print("logo tiles used:", used, "layout bytes:", n)
    for row in pixels():
        print("".join(".#-x"[c] for c in row))
