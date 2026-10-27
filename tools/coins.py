"""Coins become green rupees.

SMB's coins share background palette 3 with the ? blocks (shimmering gold), so they can't simply be
recoloured. Instead the coin blocks move to palette 0 (green and light green in overworld and
underground levels, white/grey in castles): SMB picks a block's palette from its number, so the
rupee blocks get new numbers $27 (coin) and $28 (underwater coin) in a relocated palette-0 block
table, and every place that checks for a coin block is pointed at the new numbers.
The coin popping out of a ? block (a sprite) and the status-bar icon become rupees too.
"""


def parse(text):
    return [[".123".index(c) for c in row.strip()] for row in text.strip().splitlines()]


# 16x16 rupee for the level (palette 0: 1 = light green, 2 = green, 3 = dark outline)
RUPEE = parse("""
......3333......
.....312223.....
....31122223....
...3112222223...
...3112222223...
...3112222223...
...3112222223...
...3112222223...
...3112222223...
...3112222223...
...3112222223...
...3112222223...
....31122223....
.....312223.....
......3333......
................""")

# status-bar icon (8x8, same colours)
HUD = parse("""
...33...
..3123..
..3123..
..3123..
..3123..
..3123..
...33...
........""")

# spinning rupee sprite: top halves of an 8x16 sprite (SMB mirrors the bottom). Sprite palette 1:
# 1 = green, 2 = white
SPIN = [parse(t) for t in ("""
...11...
..1211..
.122111.
.122111.
.122111.
.122111.
.122111.
.122111.""", """
...11...
...121..
..1211..
..1211..
..1211..
..1211..
..1211..
..1211..""", """
...11...
...11...
...11...
...11...
...11...
...11...
...11...
...11...""", """
...11...
..121...
..1121..
..1121..
..1121..
..1121..
..1121..
..1121..""")]

PAL0_TABLE = 0x8B10        # SMB's palette-0 block table: 39 blocks ($00-$26)
PAL0_COUNT = 39
COIN, WATER_COIN = 0x27, 0x28
RUPEE_TILES = [0xA5, 0xA6, 0xA7, 0xA8]   # SMB's coin tiles (top-left, bottom-left, top-right, bottom-right)


def encode(t):
    b = bytearray(16)
    for y in range(8):
        for x in range(8):
            c = t[y][x]
            if c & 1: b[y] |= 0x80 >> x
            if c & 2: b[y + 8] |= 0x80 >> x
    return bytes(b)


def quarter(g, tx, ty):
    return [row[tx * 8:tx * 8 + 8] for row in g[ty * 8:ty * 8 + 8]]


def table_src(lo_bank):
    """Assembly for the relocated palette-0 block table with the two rupee blocks added."""
    old = lo_bank[PAL0_TABLE - 0x8000:PAL0_TABLE - 0x8000 + PAL0_COUNT * 4]
    t = RUPEE_TILES
    data = bytes(old) + bytes([t[0], t[1], t[2], t[3]]) * 2
    return "Pal0Blocks: .db " + ",".join("$%02X" % b for b in data) + "\n"


# SMB's solid and climbable checks look up a block's palette group ($DFB0) and compare the block
# number with that group's thresholds. In palette 0, everything from $10 up is solid and from $24 up
# is climbable (flagpole, vines), which would make the rupee blocks walls or flagpoles. So the lookup
# reports group 1 for them (thresholds $61/$6D): neither solid nor climbable, like SMB's coins.
# The new tail lives in SMB's old injury-blink routine ($B245-$B254), unused since LinkHurt replaced it.
RUPEE_ATTR_AT = 0xB245
RUPEE_ATTR_SRC = """
RupeeAttr:
          rol
          tax
          tya
          cmp #$27
          beq RA_Pal1
          cmp #$28
          bne RA_Done
RA_Pal1:  ldx #1
RA_Done:  rts
"""


# Down + Left/Right on the ground (what a slightly-off N64 analog stick sends through Neon64).
# SMB cancels both, so Link just stalls. Zelda II crouches, turns to face the pressed direction and
# stops walking. Big Link now does that; small Link (who can't crouch in SMB) ignores Down and walks.
# Lives in SMB's old fireball-burst code ($ED09-$ED16), unused since the beam sparkle replaced it.
DPAD_AT = 0xED09
DPAD_SRC = """
DownSide: ldy $0754           ; 0 = big, 1 = small
          bne DS_Small
          sta $33             ; big: face the pressed direction...
          sty $0C             ; ...crouch, don't walk (Y = 0)
          rts
DS_Small: dey
          sty $0B             ; small: forget Down, keep walking
          rts
"""


def patch_dpad(patch):
    from asm6502 import assemble
    code, _ = assemble(DPAD_SRC, DPAD_AT)
    assert len(code) <= 14
    patch(DPAD_AT, code, expect=bytes.fromhex("BCEC06B524F6244A2907C903B04A")[:len(code)])
    patch(0xB121, bytes.fromhex("A50CF006") + bytes([0x20, DPAD_AT & 0xFF, DPAD_AT >> 8]) + b"\xEA" * 3,
          expect=bytes.fromhex("A40CF006A900850C850B"))


def patch_code(patch, table_addr, sym=None):
    from asm6502 import assemble
    code, _ = assemble(RUPEE_ATTR_SRC, RUPEE_ATTR_AT)
    assert len(code) <= 16
    patch(RUPEE_ATTR_AT, code, expect=bytes.fromhex("AD4707C9F0B007C9C8F0234CE9B0D013")[:len(code)])
    patch(0xDFB0, bytes.fromhex("A829C00A2A4C") + bytes([RUPEE_ATTR_AT & 0xFF, RUPEE_ATTR_AT >> 8]),
          expect=bytes.fromhex("A829C00A2A2AAA98"))
    patch(0x8B08, bytes([table_addr & 0xFF]), expect=bytes([PAL0_TABLE & 0xFF]))   # block table pointers
    patch(0x8B0C, bytes([table_addr >> 8]), expect=bytes([PAL0_TABLE >> 8]))
    patch(0x99EE, bytes([WATER_COIN, COIN, COIN, COIN]), expect=bytes.fromhex("C3C2C2C2"))   # rows of coins
    patch(0xDFA2, bytes([COIN]), expect=b"\xC2")          # player collects coins
    patch(0xDFA6, bytes([WATER_COIN]), expect=b"\xC3")
    patch(0xE1BA, bytes([COIN]), expect=b"\xC2")          # coins are not solid (enemies, beams)
    patch(0xE1BE, bytes([WATER_COIN]), expect=b"\xC3")
    patch(0xBE30, bytes([COIN]), expect=b"\xC2")          # coin on top of a bumped block
    patch(0xE6B2, b"\x01", expect=b"\x02")                # spinning rupee: sprite palette 1 (green)
    patch(0xE6B7, b"\x81", expect=b"\x82")
    patch(0x8777, b"\x2A", expect=b"\xEA")                # status-bar icon: background palette 0 (green)


def apply_bg(bank):
    bg = bytearray(bank)
    for n, (tx, ty) in zip(RUPEE_TILES, [(0, 0), (0, 1), (1, 0), (1, 1)]):
        bg[n * 16:n * 16 + 16] = encode(quarter(RUPEE, tx, ty))
    bg[0x2E * 16:0x2E * 16 + 16] = encode(HUD)
    return bytes(bg)


def apply_title_bg(bank):
    """The title-only bank keeps its logo tiles; it just needs the status-bar icon."""
    bg = bytearray(bank)
    bg[0x2E * 16:0x2E * 16 + 16] = encode(HUD)
    return bytes(bg)


def apply_spr(bank):
    spr = bytearray(bank)
    for n, t in zip(range(0x60, 0x64), SPIN):
        spr[n * 16:n * 16 + 16] = encode(t)
    return bytes(spr)
