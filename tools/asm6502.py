"""Minimal two-pass 6502 assembler used by the hack builder.

assemble(src, org, symbols) -> (bytes, symbols)
Syntax: 'label:' , 'NAME = expr', mnemonics with standard operands,
'.db a,b,...', '.dw a,...'. Expressions: $hex, %bin, decimal, labels, + - , <lo >hi.
"""
import re
from dis6502 import M, LEN

OPS = {}
for code, (mn, mode) in M.items():
    OPS.setdefault(mn, {})[mode] = code


class AsmError(Exception):
    pass


def _num(tok, syms, final):
    tok = tok.strip()
    if tok.startswith("$"): return int(tok[1:], 16)
    if tok.startswith("%"): return int(tok[1:], 2)
    if tok.isdigit(): return int(tok)
    if tok in syms: return syms[tok]
    if final: raise AsmError("undefined symbol " + tok)
    return None


def evaluate(expr, syms, final):
    expr = expr.strip()
    if expr.startswith("<"):
        v = evaluate(expr[1:], syms, final); return None if v is None else v & 0xFF
    if expr.startswith(">"):
        v = evaluate(expr[1:], syms, final); return None if v is None else (v >> 8) & 0xFF
    parts = re.split(r"([+-])", expr)
    total, sign = 0, 1
    for p in parts:
        p = p.strip()
        if p == "+": sign = 1; continue
        if p == "-": sign = -1; continue
        if p == "": continue
        v = _num(p, syms, final)
        if v is None: return None
        total += sign * v
    return total


def _parse_operand(mn, arg):
    """Return (mode, expr)."""
    arg = arg.strip()
    if arg == "":
        return ("acc" if "acc" in OPS[mn] and "imp" not in OPS[mn] else "imp"), None
    if arg.upper() == "A": return "acc", None
    if arg.startswith("#"): return "imm", arg[1:]
    m = re.match(r"^\((.*),\s*[xX]\)$", arg)
    if m: return "izx", m.group(1)
    m = re.match(r"^\((.*)\)\s*,\s*[yY]$", arg)
    if m: return "izy", m.group(1)
    m = re.match(r"^\((.*)\)$", arg)
    if m: return "ind", m.group(1)
    m = re.match(r"^(.*),\s*([xXyY])$", arg)
    if m: return ("x" if m.group(2) in "xX" else "y"), m.group(1)
    return "addr", arg


def assemble(src, org, symbols=None):
    syms = dict(symbols or {})
    lines = [l.split(";")[0].rstrip() for l in src.splitlines()]
    out = b""
    # Repeat passes until every label stops moving (a symbol defined later can shrink an
    # instruction from 3 to 2 bytes), then do a final, strict pass.
    labels_prev = None
    for npass in range(10):
        final = npass == 9
        if not final and npass > 0 and labels_prev == labels:
            final = True
        if npass > 0: labels_prev = labels
        labels = {}
        pc = org; out = bytearray()
        for raw in lines:
            line = raw.strip()
            if not line: continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line)
            if m:
                v = evaluate(m.group(2), syms, final)
                if v is not None: syms[m.group(1)] = v
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
            if m:
                if m.group(1) in labels:
                    raise AsmError("duplicate label " + m.group(1))
                labels[m.group(1)] = pc
                syms[m.group(1)] = pc; line = m.group(2).strip()
                if not line: continue
            if line.startswith(".org"):
                target = evaluate(line[4:], syms, True)
                if target < pc: raise AsmError(".org goes backwards: " + line)
                out += bytes(target - pc); pc = target
                continue
            if line.startswith(".db") or line.startswith(".dw"):
                w = 2 if line.startswith(".dw") else 1
                for item in line[3:].split(","):
                    v = evaluate(item, syms, final) or 0
                    if w == 1:
                        if final and not -128 <= v <= 255: raise AsmError("byte out of range: " + item)
                        out.append(v & 0xFF)
                    else:
                        out += bytes([v & 0xFF, (v >> 8) & 0xFF])
                    pc += w
                continue
            parts = line.split(None, 1)
            mn = parts[0].upper(); arg = parts[1] if len(parts) > 1 else ""
            if mn not in OPS: raise AsmError("bad mnemonic: " + line)
            modes = OPS[mn]
            mode, expr = _parse_operand(mn, arg)
            val = evaluate(expr, syms, final) if expr is not None else 0
            if "rel" in modes:
                mode = "rel"
            elif mode == "addr":
                mode = "zp" if (val is not None and val < 256 and "zp" in modes) else "abs"
            elif mode in ("x", "y"):
                zpm, absm = ("zpx", "abx") if mode == "x" else ("zpy", "aby")
                mode = zpm if (val is not None and val < 256 and zpm in modes) else absm
            if mode not in modes: raise AsmError("bad mode %s for %s" % (mode, line))
            code = modes[mode]; n = LEN[mode]
            out.append(code)
            v = val or 0
            if mode == "rel":
                off = v - (pc + 2)
                if final and not -128 <= off <= 127: raise AsmError("branch out of range: " + line)
                out.append(off & 0xFF)
            elif n == 2:
                if final and not 0 <= v <= 255: raise AsmError("operand out of range: " + line)
                out.append(v & 0xFF)
            elif n == 3:
                out += bytes([v & 0xFF, (v >> 8) & 0xFF])
            pc += n
        if final:
            if labels != labels_prev:
                raise AsmError("label addresses did not settle")
            break
    return bytes(out), syms
