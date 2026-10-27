"""Search inputs that get Link through the last stretch of 8-4 in the test emulator (for testing the
ending). Builds a script, runs nesemu, and reports how far Link got."""
import subprocess, sys, os, itertools

ROOT = r"S:\Roms\NES\SMB Link Hack"
EMU = os.path.join(ROOT, "tools", "nesemu.exe")
ROM = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "Super Mario Bros. - Link Hack.nes")
WORK = os.path.join(ROOT, "work", "route")
os.makedirs(WORK, exist_ok=True)

START = ["60 in1 S", "66 in1 -"] + [
    "%d poke %s" % (f, p) for f in range(60, 141)
    for p in ("075F 07", "075C 03", "0760 03", "0751 11", "0752 02", "0756 02", "0754 00")]


def run(events, end=900, dumps=()):
    """events: list of (frame, buttons). Returns list of (frame, page, x, y, engine) for dump frames."""
    lines = list(START)
    lines += ["%d poke 079F 20" % f for f in range(340, end, 2)]       # star: enemies can't hurt
    lines += ["%d in1 %s" % e for e in events]
    frames = dumps or range(360, end, 10)
    lines += ["%d dump r%d.bin" % (f, f) for f in frames]
    lines.append("%d end" % end)
    script = os.path.join(WORK, "s.txt")
    open(script, "w").write("\n".join(lines) + "\n")
    subprocess.run([EMU, ROM, "s.txt"], capture_output=True, timeout=60, cwd=WORK)
    out = []
    for f in frames:
        r = open(os.path.join(WORK, "r%d.bin" % f), "rb").read()
        out.append((f, r[0x6D], r[0x86], r[0xCE], r[0x0E], r[0x770]))
    return out


def progress(res):
    """furthest position reached while still alive (engine 8 or victory)"""
    best = 0
    for f, page, x, y, eng, mode in res:
        if mode == 2:
            return 10**6
        if eng in (0x08,):
            best = max(best, page * 256 + x)
        if eng in (0x0B, 0x06):
            break
    return best


if __name__ == "__main__":
    prefix = []
    t = 340
    prefix.append((t, "RB"))
    best_events = list(prefix)
    for stage in range(6):
        cands = []
        base_t = max(e[0] for e in best_events)
        for off, hold in itertools.product(range(4, 64, 4), (20, 30, 40)):
            ev = best_events + [(base_t + off, "RBA"), (base_t + off + hold, "RB")]
            res = run(ev, end=base_t + 400)
            cands.append((progress(res), ev))
        cands.sort(key=lambda c: -c[0])
        score, best_events = cands[0]
        print("stage", stage, "best progress", score, best_events[-2:], flush=True)
        if score >= 10**6:
            print("VICTORY with", best_events)
            break
    open(os.path.join(WORK, "best.txt"), "w").write(repr(best_events))
