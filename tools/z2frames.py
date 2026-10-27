import sys, glob, os
sys.path.insert(0, r"S:\Roms\NES\SMB Link Hack\tools")
from z2view import load, sprites, render
seen = {}
for p in sorted(glob.glob(sys.argv[1] + "/f*.bin"), key=lambda s: int(os.path.basename(s)[1:-4])):
    dm = load(p)
    # Link = palette 0 sprites (tiles < 0x60) near the bottom half
    s = [e for e in sprites(dm, pal_filter=[0]) if e[3] < 0x60 and e[2] > 40]
    if not s: continue
    minx = min(e[1] for e in s); miny = min(e[2] for e in s)
    key = tuple(sorted((e[1] - minx, e[2] - miny, e[3], e[4]) for e in s))
    if key not in seen:
        seen[key] = p
        name = "%s/fr_%02d.png" % (sys.argv[2], len(seen))
        render(dm, s, scale=8).save(name)
        print(len(seen), os.path.basename(p), key)
