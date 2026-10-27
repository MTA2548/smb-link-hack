"""Power-ups: the Super Mushroom becomes the Master Sword, the Fire Flower becomes Zelda II's magic jar.

SMB's power-up table ($E6BE) gives four tiles per item; the fire flower (and star) slot draws its
right half as a mirror of the left, so the jar only needs a left half. The 1-up mushroom keeps the
original mushroom tiles.
"""
from z2art import tile816


def parse(text):
    return [[".123".index(c) for c in row.strip()] for row in text.strip().splitlines()]


def split(g, cols):
    """Cut a grid into 8x8 tiles, row-major."""
    return [[row[c * 8:c * 8 + 8] for row in g[r * 8:r * 8 + 8]] for r in range(len(g) // 8) for c in range(cols)]


# Master Sword (hand-drawn; Zelda II has no Master Sword sprite). Palette 1: 1 grip, 2 blade, 3 guard.
SWORD = parse("""
.......22.......
......2222......
......2222......
......2222......
......2222......
......2222......
......2222......
......2222......
......2222......
...3333333333...
....33333333....
......1111......
......1111......
......1111......
.....111111.....
......1111......""")

# Zelda II's magic jar (8x16 tile $8A), centred in a 16-wide slot: left half only, SMB mirrors the right.
# Zelda II draws it with red/orange/white; SMB's palette 2 is red/white/orange, so swap colours 2 and 3.
_jar = [[{0: 0, 1: 1, 2: 3, 3: 2}[c] for c in row] for row in tile816(0x8A)]
JAR_LEFT = [[0] * 4 + row[:4] for row in _jar]            # 8 wide x 16 tall

def z2tile(bank, n):
    """8x16 tile n (0-127) of Zelda II CHR bank 'bank' as 16 rows of 8 colour indices."""
    from z2art import CHR
    base, rows = bank * 4096 + n * 32, []
    for half in range(2):
        for r in range(8):
            lo, hi = CHR[base + half * 16 + r], CHR[base + half * 16 + r + 8]
            rows.append([((lo >> (7 - b)) & 1) | (((hi >> (7 - b)) & 1) << 1) for b in range(8)])
    return rows


def recolor(g, m):
    return [[m[c] for c in row] for row in g]


# 1-Up: Zelda II's heart container (left half in CHR bank 1, mirrored). Fill red, outline white
# (SMB's palette 2 is red/white/orange).
_heart = recolor(z2tile(1, 0x40), {0: 0, 1: 1, 2: 3, 3: 2})
HEART = [row + row[::-1] for row in _heart]

# Princess: Zelda, traced from her sprite in Zelda II's ending (CHR bank 14, tiles $D8/$DA over
# $DC/$DE) and touched up by hand. SMB's princess is 16x24 (Zelda II's is 16x32), so the empty top
# row, one sleeve row and seven rows of her long dress are left out. Palette 2: 1 red (dress,
# headband), 2 skin, 3 orange (hair; dark brown in Zelda II). Zelda II outlines her face, shoulder,
# arm and dress in the hair colour, which looks odd in orange, so those outlines are gone, her
# shoulder and the dress behind her elbow are plain red and her arm is redrawn two pixels thick.
ZELDA = parse("""
....33333.......
..31333333......
..33133333......
..333132333.....
....2332333.....
...223223333....
...223233333....
...222333333....
.....2333333....
......1133333...
.....11113333...
.....11113333...
....11222333....
.....1221113....
.22222221113....
222222211113....
........11111...
........11111...
........111111..
.......1111111..
.......11111111.
......111111111.
......1111111111
....111111111111""")
assert len(ZELDA) == 24
# Her face and arms (colour 2) become skin-coloured in world 8: see ZELDA_SKIN_SRC.
ZELDA_SKIN_AT = 0xC600     # in PRG bank 2, past the music data; nothing there runs while it is mapped
ZELDA_SKIN_SRC = """
; the princess (world 8): SMB's routine, then set sprite palette 2, colour 2 to skin for her face
ZeldaSkin:
          jsr $C8D7           ; SMB: position and draw the retainer
          lda $075F
          cmp #7
          bcc ZS_Done         ; worlds 1-7: Toad
          ldy $0300
          lda #$3F
          sta $0301,y
          lda #$1A
          sta $0302,y
          lda #$01
          sta $0303,y
          lda #$36            ; skin (white in SMB's castle palette)
          sta $0304,y
          lda #$00
          sta $0305,y
          iny
          iny
          iny
          iny
          sty $0300
ZS_Done:  rts
"""
# stub in the always-visible bank: swap in bank 2, run ZeldaSkin, swap back
ZELDA_FAR_SRC = """
ZeldaFar: lda #2
          jsr SetPrg
          jsr ZELDA_SKIN
          lda #1
          jmp SetPrg
"""

# SMB always flips the princess's bottom-right tile (her dress hem is drawn as one mirrored tile),
# so that tile is stored pre-mirrored and comes out the right way round.
_zt = split(ZELDA, 2)
_zt[5] = [list(reversed(r)) for r in _zt[5]]

# Hammer (dropped by defeated Hammer Bros): Zelda II's own hammer item (8x16 tile $4C of CHR bank 2),
# centred in a 16-wide slot. Drawn with sprite palette 3, the one SMB's hammers use.
HAMMER = [[0] * 4 + row + [0] * 4 for row in z2tile(2, 0x4C)]

TILES = {"sword": split(SWORD, 2), "jar": split(JAR_LEFT, 1), "zelda": _zt, "hammer": split(HAMMER, 2)}

# Flag emblem: a small gold Triforce on the white flag (palette 1: 2 = white cloth, 3 = gold)
TRIFORCE_FLAG = parse("""
22222222
22222222
22223222
22233322
22322232
23332333
22222222
22222222""")
HEART_TILES = [0x76, 0x77, 0x78, 0x79]   # SMB's mushroom tiles: now used only by the 1-Up

JAR_ATTR_SRC = """
; magic jar: steady red (SMB flashes the fire flower's colours); the star still flashes
JarAttr:  lda $04
          ldx $00
          dex
          beq JA_Done
          lda $09
          lsr
          and #3
          ora $03CA
JA_Done:  rts
"""


def apply(patch, slots, sym):
    s, j = slots["sword"], slots["jar"]
    patch(0xE6BE, bytes(s), expect=bytes.fromhex("76777879"))                 # mushroom -> Master Sword
    patch(0xE6C2, bytes([j[0], j[0], j[1], j[1]]), expect=bytes.fromhex("D6D6D9D9"))   # flower -> magic jar
    patch(0xE6CE, b"\x01\x02", expect=b"\x02\x01")                            # sword: palette 1, jar: palette 2
    patch(0xE712, bytes([0x20, sym["JarAttr"] & 0xFF, sym["JarAttr"] >> 8]) + b"\xEA" * 5,
          expect=bytes.fromhex("A5094A29030DCA03"))
    patch(0xE6D1, b"\x02", expect=b"\x01")                                    # 1-Up heart: red palette
    z = slots["zelda"]
    patch(0xE7DA, bytes(z), expect=bytes.fromhex("7A7BDADBD8D8"))             # princess -> Zelda


def apply_spr(bank):
    """Heart container over the old mushroom tiles, Triforce on the flag."""
    spr = bytearray(bank)
    for n, (tx, ty) in zip(HEART_TILES, [(0, 0), (1, 0), (0, 1), (1, 1)]):
        spr[n * 16:n * 16 + 16] = encode([row[tx * 8:tx * 8 + 8] for row in HEART[ty * 8:ty * 8 + 8]])
    spr[0x7F * 16:0x7F * 16 + 16] = encode(TRIFORCE_FLAG)
    return bytes(spr)


def encode(t):
    b = bytearray(16)
    for y in range(8):
        for x in range(8):
            c = t[y][x]
            if c & 1: b[y] |= 0x80 >> x
            if c & 2: b[y + 8] |= 0x80 >> x
    return bytes(b)
