"""Link's frames for the SMB hack, as pixel grids (0 = clear, 1 = outline, 2 = skin, 3 = tunic).

Big frames are 16x32 and come straight from Zelda II's side-view Link (bank 2 tiles).
Small frames are 16x16; Zelda II has no small Link, so these are hand-drawn, reusing big Link's head.
All art here faces LEFT (Zelda II's native direction); the builder mirrors it to face right like Mario.
"""
from z2art import compose, tile816, FRAMES


def crop(g, x0, w=16):
    return [row[x0:x0 + w] for row in g]


def parse(text):
    rows = [r.strip() for r in text.strip().splitlines()]
    return [[".123".index(c) for c in r] for r in rows]


def stack(*parts):
    g = []
    for p in parts:
        g += [list(r) for r in p]
    return g


Z = {k: compose(v) for k, v in FRAMES.items()}

# ---------------------------------------------------------------- big Link (16x32)
stand = Z["stand"]
walkA, walkB, walkC = Z["walkA"], Z["walkB"], Z["walkC"]
crouch = Z["crouch"]
death = Z["death"]
thrust = crop(Z["thrust"], 13)          # body only; the sword itself becomes the beam
windup = crop(Z["windup"], 0)           # sword-arm raised: reused as a climbing reach
cthrust = crop(compose([[None, 0x56, 0x58, None], [0x54, 0x5A, 0x5C, 0x5E]]), 12)   # crouching stab, body only

# Custom swimming: stand's head and torso (rows 0-20) with kicking legs (rows 21-31).
swim_legs = [parse("""
....11111111111.
....12221122211.
...122221.12221.
..12221....12211
.12221......1221
.1111........111
.1131.........11
.1111...........
................
................
................"""), parse("""
....11111111111.
....12221122211.
....12221.12221.
....12221.122211
....1221...1221.
...12221...1221.
...1111....1111.
...1131....1131.
...1111....1111.
................
................"""), parse("""
....11111111111.
....122212221...
...12222.12221..
..12221...12211.
..1221.....1221.
.12221.....12211
.1111.......1111
.1131.......1131
.1111.......1111
................
................""")]
swim = [stack(stand[:21], legs) for legs in swim_legs]

BIG = {
    "walk1": walkA, "walk2": walkB, "walk3": walkC,
    "skid": stand, "jump": crouch,
    "swim1": swim[0], "swim2": swim[1], "swim3": swim[2],
    "climb1": windup, "climb2": stand,
    "crouch": crouch, "throw": thrust,
    "stand": stand, "death": death, "cthrust": cthrust,
    "grow": crouch,                       # intermediate grow frame (bottom 24 rows used)
}

# ---------------------------------------------------------------- small Link (16x16)
head = [row[:] for row in stand[:9]]     # cap, hair, face and shield top from big Link

small_bodies = {
    "stand": """
131.13333311....
131.13333331....
1111.1111111....
.1...1221221....
.....1221221....
....11111111....
....1131.1131...""",
    "walk1": """
131.13333311....
131.13333331....
1111.1111111....
.1..12211.1221..
...12221...1221.
...1111....1111.
...1131....1131.""",
    "walk2": """
131.13333311....
131.13333331....
1111.1111111....
.1...12211221...
.....1221.1221..
....11111.1111..
....1131..1131..""",
    "walk3": """
131.13333311....
131.13333331....
1111.1111111....
.1...1221221....
....12211221....
...111111111....
...1131.1131....""",
    "jump": """
131.13333311....
131.133333311...
1111.11111221...
.1..12211.1221..
...12221...111..
...1111....1131.
...1131.........""",
    "swim1": """
131.13333311....
131.13333331....
1111.11111111...
.1...12221.1221.
....12221...1221
...1111......111
...1131.......11""",
    "swim2": """
131.13333311....
131.13333331....
1111.1111111....
.1...1221.1221..
.....1221..1221.
....1111...1111.
....1131...1131.""",
    "swim3": """
131.13333311....
131.13333331....
1111.11111111...
.1...12221.12211
....1221....1221
...12221....1111
...1111.....1131""",
    "climb1": """
131.13333311....
131.13333331....
1111.1111111....
.1...1221221....
.....1221.1221..
....11111.1111..
....1131..1131..""",
    "skid": """
131.13333311....
131.13333331....
1111.1111111....
.1..12211221....
...1221.1221....
..1111..1111....
..1131..1131....""",
}

SMALL = {k: stack(head, parse(v)) for k, v in small_bodies.items()}
# small sword thrust: no shield, sword arm pushed forward (hand-drawn)
SMALL["thrust"] = parse("""
.......111111...
....1113331331..
...111113121331.
...1111111213131
....122112213111
...11212122111..
..12221212211...
...12222221111..
....11222211....
11111113333311..
12222213333331..
11111111111111..
.....1221221....
....12211221....
...111111111....
...1131.1131....""")
# climbing frame 2: reaching pose from the raised-sword frame, squeezed into 16 rows
SMALL["climb2"] = stack(crop(Z["windup"], 0)[:9], parse(small_bodies["climb1"]))
# small death pose: big death silhouette head with a crouched body (drawn black during death)
SMALL["killed"] = stack(death[1:10], parse("""
.12222221222113.
122222221222111.
.11111111221331.
....1221221111..
...12221.1221...
...1111..1111...
...1131..1131..."""))

BEAM = tile816(0x32)[8:16]   # Zelda II's sword beam: the blade from the thrust frame (pointing left)


def check():
    for name, g in list(BIG.items()) + list(SMALL.items()):
        h = 32 if name in BIG and g is BIG.get(name) else 16
        assert all(len(r) == 16 for r in g), (name, [len(r) for r in g])
    for name, g in SMALL.items():
        assert len(g) == 16, (name, len(g))
    for name, g in BIG.items():
        assert len(g) == 32, (name, len(g))


check()
