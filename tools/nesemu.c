// nesemu.c - small headless NES emulator used to test the SMB Link hack.
// Supports mapper 0 (NROM) and mapper 1 (MMC1). Scanline-based PPU.
// Usage: nesemu rom.nes script.txt
// Script lines: "<frame> <cmd> [args]"   (frame numbers in decimal, values in hex)
//   in1 BUTTONS / in2 BUTTONS   buttons held from this frame on: A B s(elect) S(tart) U D L R, '-' = none
//   shot file.png [scale]       save the screen
//   poke ADDR VAL               write a CPU byte
//   dump file.bin               RAM(2K) + OAM(256) + palette(32) + nametables(2K)
//   pt file.png                 dump both pattern tables as currently mapped
//   watch ADDR                  print a line each time the CPU executes ADDR
//   apulog file.txt             start logging APU writes ($4000-$4017) as "frame addr val"
//   apuoff                      stop logging
//   end                         stop
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32;

static u8 *prg, *chr; static int prgsz, chrsz, mapper, mirrorV, chrram;
static u8 chrRAM[8192], ram[2048], wram[8192], vram[2048], pal[32], oam[256];
static u8 m1shift = 0x10, m1ctrl = 0x0C, m1chr0, m1chr1, m1prg;
static int prgoff[2], chroff[2];
static u8 pctrl, pmask, pstatus, oamaddr, fx, w, rbuf, openbus; static u16 v, t;
static int nmi_pending;
static u8 pad[2], padsh[2], strobe;
static u8 A, X, Y, S = 0xFD, P = 0x24; static u16 PC; static long long cyc; static int pagex;
static u8 fb[256 * 240];
static int frame;
static int watch[64], nwatch; static int watchcount;
static FILE *apulog;
static u8 wcount[2048];
static long long dmc_end; static u8 dmc_rate, dmc_len;
static const int dmc_rates[16] = {428,380,340,320,286,254,226,214,190,160,142,128,106,84,72,54};
static int rw_lo = -1, rw_hi = -1, rw_pclo, rw_pchi, rw_n; static u16 curpc;
static int ww_lo = -1, ww_hi = -1, ww_n;

static void m1update(void) {
  int nprg = prgsz / 16384, mode = (m1ctrl >> 2) & 3, bank = m1prg & 0x0F;
  if (mode < 2) { prgoff[0] = ((bank & 0xE) % nprg) * 16384; prgoff[1] = prgoff[0] + 16384; }
  else if (mode == 2) { prgoff[0] = 0; prgoff[1] = (bank % nprg) * 16384; }
  else { prgoff[0] = (bank % nprg) * 16384; prgoff[1] = (nprg - 1) * 16384; }
  int nchr = chrsz / 4096; if (nchr == 0) nchr = 2;
  if (m1ctrl & 0x10) { chroff[0] = (m1chr0 % nchr) * 4096; chroff[1] = (m1chr1 % nchr) * 4096; }
  else { chroff[0] = ((m1chr0 & 0x1E) % nchr) * 4096; chroff[1] = chroff[0] + 4096; }
}

static int ntmap(u16 a) {
  a &= 0x0FFF; int tt = a >> 10, o = a & 0x3FF, m;
  if (mapper == 1) { switch (m1ctrl & 3) { case 0: m = 0; break; case 1: m = 1; break; case 2: m = tt & 1; break; default: m = tt >> 1; } }
  else m = mirrorV ? (tt & 1) : (tt >> 1);
  return m * 1024 + o;
}
static u8 chrrd(u16 a) {
  if (chrram) return chrRAM[a & 0x1FFF];
  if (mapper == 1) return chr[chroff[(a >> 12) & 1] + (a & 0xFFF)];
  return chr[a & 0x1FFF];
}
static int palidx(u16 a) { a &= 0x1F; if ((a & 0x13) == 0x10) a &= ~0x10; return a; }
static u8 ppurd(u16 a) { a &= 0x3FFF; if (a < 0x2000) return chrrd(a); if (a < 0x3F00) return vram[ntmap(a)]; return pal[palidx(a)]; }
static void ppuwr(u16 a, u8 val) {
  a &= 0x3FFF;
  if (a < 0x2000) { if (chrram) chrRAM[a] = val; }
  else if (a < 0x3F00) vram[ntmap(a)] = val;
  else pal[palidx(a)] = val & 0x3F;
}
static u8 ppureg_rd(int r) {
  u8 x = openbus;
  switch (r) {
  case 2: x = (pstatus & 0xE0) | (openbus & 0x1F); pstatus &= 0x7F; w = 0; break;
  case 4: x = oam[oamaddr]; break;
  case 7: { u16 a = v & 0x3FFF;
    if (a >= 0x3F00) { x = pal[palidx(a)]; rbuf = ppurd(a - 0x1000); } else { x = rbuf; rbuf = ppurd(a); }
    v += (pctrl & 4) ? 32 : 1; } break;
  }
  openbus = x; return x;
}
static void ppureg_wr(int r, u8 val) {
  openbus = val;
  switch (r) {
  case 0: { u8 old = pctrl; pctrl = val; t = (t & 0xF3FF) | ((val & 3) << 10);
    if (!(old & 0x80) && (val & 0x80) && (pstatus & 0x80)) nmi_pending = 1; } break;
  case 1: pmask = val; break;
  case 3: oamaddr = val; break;
  case 4: oam[oamaddr++] = val; break;
  case 5: if (!w) { t = (t & 0xFFE0) | (val >> 3); fx = val & 7; w = 1; }
          else { t = (t & 0x8C1F) | ((val & 7) << 12) | ((val & 0xF8) << 2); w = 0; } break;
  case 6: if (!w) { t = (t & 0x80FF) | ((val & 0x3F) << 8); w = 1; } else { t = (t & 0xFF00) | val; v = t; w = 0; } break;
  case 7: ppuwr(v, val); v += (pctrl & 4) ? 32 : 1; break;
  }
}

static u8 rd(u16 a) {
  if (a >= rw_lo && a <= rw_hi && !(curpc >= rw_pclo && curpc <= rw_pchi) && rw_n < 50) { rw_n++; printf("read %04X by PC=%04X frame %d\n", a, curpc, frame); }
  if (a < 0x2000) return ram[a & 0x7FF];
  if (a < 0x4000) return ppureg_rd(a & 7);
  if (a == 0x4016 || a == 0x4017) { int i = a & 1; u8 r = (padsh[i] & 1) | 0x40; if (!strobe) padsh[i] = (padsh[i] >> 1) | 0x80; return r; }
  if (a == 0x4015) return (cyc < dmc_end) ? 0x10 : 0;
  if (a < 0x6000) return 0;
  if (a < 0x8000) return wram[a - 0x6000];
  if (mapper == 0) return prg[(a - 0x8000) % prgsz];
  return prg[prgoff[(a >> 14) & 1] + (a & 0x3FFF)];
}
static void wr(u16 a, u8 val) {
  if (a < 0x2000 && (int)(a & 0x7FF) >= ww_lo && (int)(a & 0x7FF) <= ww_hi && ww_n < 60) { ww_n++; printf("write %04X=%02X by PC=%04X frame %d\n", a & 0x7FF, val, curpc, frame); }
  if (a < 0x2000) { ram[a & 0x7FF] = val; if (wcount[a & 0x7FF] < 255) wcount[a & 0x7FF]++; }
  else if (a >= 0x8000 && mapper == 0) { static int romw; if (romw++ < 20) fprintf(stderr, "ROM write %04X=%02X PC=%04X frame %d\n", a, val, PC, frame); }
  else if (a < 0x4000) ppureg_wr(a & 7, val);
  else if (a == 0x4014) { for (int i = 0; i < 256; i++) oam[(oamaddr + i) & 255] = rd((val << 8) | i); cyc += 513; }
  else if (a == 0x4016) { strobe = val & 1; if (strobe) { padsh[0] = pad[0]; padsh[1] = pad[1]; } }
  else if (a == 0x4010 || a == 0x4013 || a == 0x4015) {
    if (a == 0x4010) dmc_rate = val & 15; else if (a == 0x4013) dmc_len = val;
    else { if (!(val & 0x10)) dmc_end = 0; else if (cyc >= dmc_end) dmc_end = cyc + (long long)(dmc_len * 16 + 1) * 8 * dmc_rates[dmc_rate]; }
    if (apulog) fprintf(apulog, "%d %04X %02X\n", frame, a, val); }
  else if (a < 0x4018) { if (apulog) fprintf(apulog, "%d %04X %02X\n", frame, a, val); }
  else if (a >= 0x6000 && a < 0x8000) wram[a - 0x6000] = val;
  else if (a >= 0x8000 && mapper == 1) {
    if (val & 0x80) { m1shift = 0x10; m1ctrl |= 0x0C; m1update(); return; }
    int done = m1shift & 1; m1shift = (m1shift >> 1) | ((val & 1) << 4);
    if (done) {
      u8 d = m1shift; m1shift = 0x10;
      switch ((a >> 13) & 3) { case 0: m1ctrl = d; break; case 1: m1chr0 = d; break; case 2: m1chr1 = d; break; case 3: m1prg = d; break; }
      m1update();
    }
  }
}

// ---- CPU ----
static void setzn(u8 x) { P = (P & ~0x82) | (x & 0x80) | (x ? 0 : 2); }
static void push(u8 x) { wr(0x100 | S--, x); }
static u8 pop(void) { return rd(0x100 | ++S); }
static u16 rd16(u16 a) { return rd(a) | (rd(a + 1) << 8); }
static void nmi(void) { push(PC >> 8); push(PC & 0xFF); push((P & ~0x10) | 0x20); P |= 4; PC = rd16(0xFFFA); cyc += 7; }

static u16 imm(void) { return PC++; }
static u16 zp(void) { return rd(PC++); }
static u16 zpx(void) { return (rd(PC++) + X) & 0xFF; }
static u16 zpy(void) { return (rd(PC++) + Y) & 0xFF; }
static u16 ab(void) { u16 a = rd16(PC); PC += 2; return a; }
static u16 abx(void) { u16 b = ab(), a = b + X; if ((a ^ b) & 0x100) pagex = 1; return a; }
static u16 aby(void) { u16 b = ab(), a = b + Y; if ((a ^ b) & 0x100) pagex = 1; return a; }
static u16 izx(void) { u8 z = rd(PC++) + X; return rd(z) | (rd((u8)(z + 1)) << 8); }
static u16 izy(void) { u8 z = rd(PC++); u16 b = rd(z) | (rd((u8)(z + 1)) << 8), a = b + Y; if ((a ^ b) & 0x100) pagex = 1; return a; }

static const u8 cyctab[256] = {
7,6,2,8,3,3,5,5,3,2,2,2,4,4,6,6, 2,5,2,8,4,4,6,6,2,4,2,7,4,4,7,7,
6,6,2,8,3,3,5,5,4,2,2,2,4,4,6,6, 2,5,2,8,4,4,6,6,2,4,2,7,4,4,7,7,
6,6,2,8,3,3,5,5,3,2,2,2,3,4,6,6, 2,5,2,8,4,4,6,6,2,4,2,7,4,4,7,7,
6,6,2,8,3,3,5,5,4,2,2,2,5,4,6,6, 2,5,2,8,4,4,6,6,2,4,2,7,4,4,7,7,
2,6,2,6,3,3,3,3,2,2,2,2,4,4,4,4, 2,6,2,6,4,4,4,4,2,5,2,5,5,5,5,5,
2,6,2,6,3,3,3,3,2,2,2,2,4,4,4,4, 2,5,2,5,4,4,4,4,2,4,2,4,4,4,4,4,
2,6,2,8,3,3,5,5,2,2,2,2,4,4,6,6, 2,5,2,8,4,4,6,6,2,4,2,7,4,4,7,7,
2,6,2,8,3,3,5,5,2,2,2,2,4,4,6,6, 2,5,2,8,4,4,6,6,2,4,2,7,4,4,7,7 };

static void adc(u8 x) { u16 s = A + x + (P & 1); P = (P & ~0x41) | (s > 0xFF) | ((~(A ^ x) & (A ^ s) & 0x80) ? 0x40 : 0); A = (u8)s; setzn(A); }
static void cmp(u8 r, u8 x) { P = (P & ~1) | (r >= x); setzn((u8)(r - x)); }
static void branch(int cond) { int8_t o = (int8_t)rd(PC++); if (cond) { u16 n = PC + o; cyc += 1 + (((n ^ PC) & 0x100) ? 1 : 0); PC = n; } }
static u8 asl_(u8 x) { P = (P & ~1) | (x >> 7); x <<= 1; setzn(x); return x; }
static u8 lsr_(u8 x) { P = (P & ~1) | (x & 1); x >>= 1; setzn(x); return x; }
static u8 rol_(u8 x) { u8 c = P & 1; P = (P & ~1) | (x >> 7); x = (x << 1) | c; setzn(x); return x; }
static u8 ror_(u8 x) { u8 c = P & 1; P = (P & ~1) | (x & 1); x = (x >> 1) | (c << 7); setzn(x); return x; }

#define RD(mode, body) { u16 a = mode(); u8 m = rd(a); body; } break
#define RMW(mode, fn) { u16 a = mode(); u8 m = rd(a); wr(a, fn(m)); } break
#define ST(mode, reg) { u16 a = mode(); wr(a, reg); } break
static u8 inc_(u8 x) { x++; setzn(x); return x; }
static u8 dec_(u8 x) { x--; setzn(x); return x; }
static int badops;
static u16 pchist[32]; static int pchi;

static void step(void) {
  for (int i = 0; i < nwatch; i++) if (watch[i] == PC && watchcount < 4000) { watchcount++; printf("watch f=%d PC=%04X A=%02X X=%02X Y=%02X S=%02X stack:", frame, PC, A, X, Y, S);
    for (int k = 1; k <= 8 && S + k <= 0xFF; k++) printf(" %02X", ram[0x100 + S + k]);
    printf(" recent:"); for (int k = 16; k < 32; k++) printf(" %04X", pchist[(pchi + k) & 31]); printf("\n"); }
  curpc = PC; pchist[pchi++ & 31] = PC; u8 op = rd(PC++); pagex = 0;
  switch (op) {
  case 0x00: PC++; push(PC >> 8); push(PC & 0xFF); push(P | 0x30); P |= 4; PC = rd16(0xFFFE); break;
  case 0x01: RD(izx, A |= m; setzn(A)); case 0x05: RD(zp, A |= m; setzn(A)); case 0x09: RD(imm, A |= m; setzn(A));
  case 0x0D: RD(ab, A |= m; setzn(A)); case 0x11: RD(izy, A |= m; setzn(A)); case 0x15: RD(zpx, A |= m; setzn(A));
  case 0x19: RD(aby, A |= m; setzn(A)); case 0x1D: RD(abx, A |= m; setzn(A));
  case 0x21: RD(izx, A &= m; setzn(A)); case 0x25: RD(zp, A &= m; setzn(A)); case 0x29: RD(imm, A &= m; setzn(A));
  case 0x2D: RD(ab, A &= m; setzn(A)); case 0x31: RD(izy, A &= m; setzn(A)); case 0x35: RD(zpx, A &= m; setzn(A));
  case 0x39: RD(aby, A &= m; setzn(A)); case 0x3D: RD(abx, A &= m; setzn(A));
  case 0x41: RD(izx, A ^= m; setzn(A)); case 0x45: RD(zp, A ^= m; setzn(A)); case 0x49: RD(imm, A ^= m; setzn(A));
  case 0x4D: RD(ab, A ^= m; setzn(A)); case 0x51: RD(izy, A ^= m; setzn(A)); case 0x55: RD(zpx, A ^= m; setzn(A));
  case 0x59: RD(aby, A ^= m; setzn(A)); case 0x5D: RD(abx, A ^= m; setzn(A));
  case 0x61: RD(izx, adc(m)); case 0x65: RD(zp, adc(m)); case 0x69: RD(imm, adc(m)); case 0x6D: RD(ab, adc(m));
  case 0x71: RD(izy, adc(m)); case 0x75: RD(zpx, adc(m)); case 0x79: RD(aby, adc(m)); case 0x7D: RD(abx, adc(m));
  case 0xE1: RD(izx, adc(m ^ 0xFF)); case 0xE5: RD(zp, adc(m ^ 0xFF)); case 0xE9: RD(imm, adc(m ^ 0xFF)); case 0xED: RD(ab, adc(m ^ 0xFF));
  case 0xF1: RD(izy, adc(m ^ 0xFF)); case 0xF5: RD(zpx, adc(m ^ 0xFF)); case 0xF9: RD(aby, adc(m ^ 0xFF)); case 0xFD: RD(abx, adc(m ^ 0xFF));
  case 0xC1: RD(izx, cmp(A, m)); case 0xC5: RD(zp, cmp(A, m)); case 0xC9: RD(imm, cmp(A, m)); case 0xCD: RD(ab, cmp(A, m));
  case 0xD1: RD(izy, cmp(A, m)); case 0xD5: RD(zpx, cmp(A, m)); case 0xD9: RD(aby, cmp(A, m)); case 0xDD: RD(abx, cmp(A, m));
  case 0xE0: RD(imm, cmp(X, m)); case 0xE4: RD(zp, cmp(X, m)); case 0xEC: RD(ab, cmp(X, m));
  case 0xC0: RD(imm, cmp(Y, m)); case 0xC4: RD(zp, cmp(Y, m)); case 0xCC: RD(ab, cmp(Y, m));
  case 0x24: case 0x2C: { u16 a = (op == 0x24) ? zp() : ab(); u8 m = rd(a); P = (P & ~0xC2) | (m & 0xC0) | ((A & m) ? 0 : 2); } break;
  case 0xA1: RD(izx, A = m; setzn(A)); case 0xA5: RD(zp, A = m; setzn(A)); case 0xA9: RD(imm, A = m; setzn(A));
  case 0xAD: RD(ab, A = m; setzn(A)); case 0xB1: RD(izy, A = m; setzn(A)); case 0xB5: RD(zpx, A = m; setzn(A));
  case 0xB9: RD(aby, A = m; setzn(A)); case 0xBD: RD(abx, A = m; setzn(A));
  case 0xA2: RD(imm, X = m; setzn(X)); case 0xA6: RD(zp, X = m; setzn(X)); case 0xAE: RD(ab, X = m; setzn(X));
  case 0xB6: RD(zpy, X = m; setzn(X)); case 0xBE: RD(aby, X = m; setzn(X));
  case 0xA0: RD(imm, Y = m; setzn(Y)); case 0xA4: RD(zp, Y = m; setzn(Y)); case 0xAC: RD(ab, Y = m; setzn(Y));
  case 0xB4: RD(zpx, Y = m; setzn(Y)); case 0xBC: RD(abx, Y = m; setzn(Y));
  case 0x81: ST(izx, A); case 0x85: ST(zp, A); case 0x8D: ST(ab, A); case 0x91: ST(izy, A);
  case 0x95: ST(zpx, A); case 0x99: ST(aby, A); case 0x9D: ST(abx, A);
  case 0x86: ST(zp, X); case 0x8E: ST(ab, X); case 0x96: ST(zpy, X);
  case 0x84: ST(zp, Y); case 0x8C: ST(ab, Y); case 0x94: ST(zpx, Y);
  case 0x06: RMW(zp, asl_); case 0x0E: RMW(ab, asl_); case 0x16: RMW(zpx, asl_); case 0x1E: RMW(abx, asl_);
  case 0x46: RMW(zp, lsr_); case 0x4E: RMW(ab, lsr_); case 0x56: RMW(zpx, lsr_); case 0x5E: RMW(abx, lsr_);
  case 0x26: RMW(zp, rol_); case 0x2E: RMW(ab, rol_); case 0x36: RMW(zpx, rol_); case 0x3E: RMW(abx, rol_);
  case 0x66: RMW(zp, ror_); case 0x6E: RMW(ab, ror_); case 0x76: RMW(zpx, ror_); case 0x7E: RMW(abx, ror_);
  case 0xE6: RMW(zp, inc_); case 0xEE: RMW(ab, inc_); case 0xF6: RMW(zpx, inc_); case 0xFE: RMW(abx, inc_);
  case 0xC6: RMW(zp, dec_); case 0xCE: RMW(ab, dec_); case 0xD6: RMW(zpx, dec_); case 0xDE: RMW(abx, dec_);
  case 0x0A: A = asl_(A); break; case 0x4A: A = lsr_(A); break; case 0x2A: A = rol_(A); break; case 0x6A: A = ror_(A); break;
  case 0x10: branch(!(P & 0x80)); break; case 0x30: branch(P & 0x80); break;
  case 0x50: branch(!(P & 0x40)); break; case 0x70: branch(P & 0x40); break;
  case 0x90: branch(!(P & 1)); break; case 0xB0: branch(P & 1); break;
  case 0xD0: branch(!(P & 2)); break; case 0xF0: branch(P & 2); break;
  case 0x4C: PC = ab(); break;
  case 0x6C: { u16 a = ab(); PC = rd(a) | (rd((a & 0xFF00) | ((a + 1) & 0xFF)) << 8); } break;
  case 0x20: { u16 a = ab(); u16 r = PC - 1; push(r >> 8); push(r & 0xFF); PC = a; } break;
  case 0x60: { u16 lo = pop(); u16 hi = pop(); PC = ((hi << 8) | lo) + 1; } break;
  case 0x40: { P = (pop() & ~0x10) | 0x20; u16 lo = pop(); u16 hi = pop(); PC = (hi << 8) | lo; } break;
  case 0x08: push(P | 0x30); break; case 0x28: P = (pop() & ~0x10) | 0x20; break;
  case 0x48: push(A); break; case 0x68: A = pop(); setzn(A); break;
  case 0x18: P &= ~1; break; case 0x38: P |= 1; break; case 0x58: P &= ~4; break; case 0x78: P |= 4; break;
  case 0xB8: P &= ~0x40; break; case 0xD8: P &= ~8; break; case 0xF8: P |= 8; break;
  case 0xAA: X = A; setzn(X); break; case 0xA8: Y = A; setzn(Y); break; case 0x8A: A = X; setzn(A); break;
  case 0x98: A = Y; setzn(A); break; case 0xBA: X = S; setzn(X); break; case 0x9A: S = X; break;
  case 0xE8: X++; setzn(X); break; case 0xC8: Y++; setzn(Y); break; case 0xCA: X--; setzn(X); break; case 0x88: Y--; setzn(Y); break;
  case 0xEA: break;
  default: if (badops++ < 10) { fprintf(stderr, "bad opcode %02X at %04X frame %d; recent PCs:", op, PC - 1, frame);
             for (int k = 0; k < 32; k++) fprintf(stderr, " %04X", pchist[(pchi + k) & 31]); fprintf(stderr, "\n"); } break;
  }
  cyc += cyctab[op] + pagex;
}

// ---- PPU rendering ----
static void render_line(int L) {
  u8 bgp[256], line[256], spx[256]; u8 univ = pal[0];
  memset(bgp, 0, sizeof bgp); memset(spx, 0, sizeof spx);
  for (int i = 0; i < 256; i++) line[i] = univ;
  if (pmask & 8) {
    u16 vv = v; int fy = (vv >> 12) & 7; u16 pt = (pctrl & 0x10) ? 0x1000 : 0;
    for (int tl = 0; tl < 33; tl++) {
      u8 nt = ppurd(0x2000 | (vv & 0xFFF));
      u8 at = ppurd(0x23C0 | (vv & 0x0C00) | ((vv >> 4) & 0x38) | ((vv >> 2) & 7));
      int sh = ((vv >> 4) & 4) | (vv & 2); int ph = (at >> sh) & 3;
      u8 lo = ppurd(pt + nt * 16 + fy), hi = ppurd(pt + nt * 16 + fy + 8);
      for (int b = 0; b < 8; b++) {
        int px = tl * 8 + b - fx; if (px < 0 || px > 255) continue;
        int c = ((lo >> (7 - b)) & 1) | (((hi >> (7 - b)) & 1) << 1);
        if (!(pmask & 2) && px < 8) c = 0;
        bgp[px] = c; line[px] = c ? pal[ph * 4 + c] : univ;
      }
      if ((vv & 0x1F) == 31) { vv &= ~0x1F; vv ^= 0x400; } else vv++;
    }
  }
  if (pmask & 0x10) {
    int h = (pctrl & 0x20) ? 16 : 8, n = 0; int list[8];
    for (int i = 0; i < 64; i++) { int row = L - (oam[i * 4] + 1); if (row >= 0 && row < h) { if (n < 8) list[n++] = i; else { pstatus |= 0x20; break; } } }
    for (int k = 0; k < n; k++) {
      int i = list[k]; u8 y = oam[i * 4], tile = oam[i * 4 + 1], at = oam[i * 4 + 2], x = oam[i * 4 + 3];
      int row = L - (y + 1); if (at & 0x80) row = h - 1 - row;
      u16 addr = (h == 8) ? (((pctrl & 8) ? 0x1000 : 0) + tile * 16 + row)
                          : (((tile & 1) ? 0x1000 : 0) + (tile & 0xFE) * 16 + (row >= 8 ? 16 : 0) + (row & 7));
      u8 lo = ppurd(addr), hi = ppurd(addr + 8);
      for (int b = 0; b < 8; b++) {
        int bit = (at & 0x40) ? b : 7 - b; int c = ((lo >> bit) & 1) | (((hi >> bit) & 1) << 1);
        int px = x + b; if (px > 255 || !c) continue; if (!(pmask & 4) && px < 8) continue;
        if (i == 0 && bgp[px] && px != 255) pstatus |= 0x40;
        if (spx[px]) continue; spx[px] = 1;
        if (!(at & 0x20) || !bgp[px]) line[px] = pal[0x10 + (at & 3) * 4 + c];
      }
    }
  }
  memcpy(fb + L * 256, line, 256);
}
static void incy(void) {
  if ((v & 0x7000) != 0x7000) v += 0x1000;
  else { v &= ~0x7000; int y = (v & 0x3E0) >> 5; if (y == 29) { y = 0; v ^= 0x800; } else if (y == 31) y = 0; else y++; v = (v & ~0x3E0) | (y << 5); }
}
static long long dots;
static void run_frame(void) {
  for (int L = 0; L < 262; L++) {
    int rendering = pmask & 0x18;
    if (L < 240) { if (rendering) render_line(L); else memset(fb + L * 256, pal[0], 256); }
    if (L == 241) { pstatus |= 0x80; if (pctrl & 0x80) nmi_pending = 1; }
    if (L == 261) pstatus &= 0x1F;
    dots += 341;
    while (cyc * 3 < dots) { if (nmi_pending) { nmi_pending = 0; nmi(); } step(); }
    if (rendering && (L < 240 || L == 261)) {
      if (L < 240) incy();
      v = (v & ~0x041F) | (t & 0x041F);
      if (L == 261) v = (v & 0x041F) | (t & 0x7BE0);
    }
  }
}

// ---- PNG output (uncompressed deflate) ----
static const u8 nespal[64][3] = {
{84,84,84},{0,30,116},{8,16,144},{48,0,136},{68,0,100},{92,0,48},{84,4,0},{60,24,0},{32,42,0},{8,58,0},{0,64,0},{0,60,0},{0,50,60},{0,0,0},{0,0,0},{0,0,0},
{152,150,152},{8,76,196},{48,50,236},{92,30,228},{136,20,176},{160,20,100},{152,34,32},{120,60,0},{84,90,0},{40,114,0},{8,124,0},{0,118,40},{0,102,120},{0,0,0},{0,0,0},{0,0,0},
{236,238,236},{76,154,236},{120,124,236},{176,98,236},{228,84,236},{236,88,180},{236,106,100},{212,136,32},{160,170,0},{116,196,0},{76,208,32},{56,204,108},{56,180,204},{60,60,60},{0,0,0},{0,0,0},
{236,238,236},{168,204,236},{188,188,236},{212,178,236},{236,174,236},{236,174,212},{236,180,176},{228,196,144},{204,210,120},{180,222,120},{168,226,144},{152,226,180},{160,214,228},{160,162,160},{0,0,0},{0,0,0}};
static u32 crctab[256];
static u32 crc(u32 c, const u8 *b, size_t n) { c = ~c; for (size_t i = 0; i < n; i++) c = crctab[(c ^ b[i]) & 255] ^ (c >> 8); return ~c; }
static void be32(u8 *p, u32 x) { p[0] = x >> 24; p[1] = x >> 16; p[2] = x >> 8; p[3] = x; }
static void chunk(FILE *f, const char *type, const u8 *d, u32 n) {
  u8 h[8]; be32(h, n); memcpy(h + 4, type, 4); fwrite(h, 1, 8, f); fwrite(d, 1, n, f);
  u32 c = crc(0, (const u8 *)type, 4); c = crc(c, d, n); be32(h, c); fwrite(h, 1, 4, f);
}
static void write_png(const char *fn, const u8 *rgb, int W, int H) {
  for (u32 i = 0; i < 256; i++) { u32 c = i; for (int k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320 ^ (c >> 1) : c >> 1; crctab[i] = c; }
  size_t rawn = (size_t)H * (W * 3 + 1); u8 *raw = malloc(rawn);
  for (int y = 0; y < H; y++) { raw[y * (W * 3 + 1)] = 0; memcpy(raw + y * (W * 3 + 1) + 1, rgb + y * W * 3, W * 3); }
  size_t nb = (rawn + 65534) / 65535; size_t zn = 2 + rawn + nb * 5 + 4; u8 *z = malloc(zn), *p = z;
  *p++ = 0x78; *p++ = 0x01; u32 a1 = 1, a2 = 0;
  for (size_t i = 0; i < rawn; i++) { a1 = (a1 + raw[i]) % 65521; a2 = (a2 + a1) % 65521; }
  for (size_t off = 0; off < rawn; off += 65535) {
    u32 len = (rawn - off > 65535) ? 65535 : (u32)(rawn - off);
    *p++ = (off + len >= rawn); *p++ = len & 255; *p++ = len >> 8; *p++ = ~len & 255; *p++ = (~len >> 8) & 255;
    memcpy(p, raw + off, len); p += len;
  }
  be32(p, (a2 << 16) | a1); p += 4;
  FILE *f = fopen(fn, "wb"); if (!f) { perror(fn); return; }
  static const u8 sig[8] = {137,80,78,71,13,10,26,10}; fwrite(sig, 1, 8, f);
  u8 ih[13]; be32(ih, W); be32(ih + 4, H); ih[8] = 8; ih[9] = 2; ih[10] = ih[11] = ih[12] = 0;
  chunk(f, "IHDR", ih, 13); chunk(f, "IDAT", z, (u32)(p - z)); chunk(f, "IEND", NULL, 0); fclose(f);
  free(raw); free(z);
}
static void shot(const char *fn, int sc) {
  int W = 256 * sc, H = 240 * sc; u8 *rgb = malloc(W * H * 3);
  for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) memcpy(rgb + (y * W + x) * 3, nespal[fb[(y / sc) * 256 + x / sc] & 63], 3);
  write_png(fn, rgb, W, H); free(rgb);
}
static void ptdump(const char *fn) {
  static const u8 g[4][3] = {{0,0,0},{90,90,90},{170,170,170},{255,255,255}};
  int W = 256, H = 128; u8 *rgb = malloc(W * H * 3);
  for (int tb = 0; tb < 2; tb++) for (int tile = 0; tile < 256; tile++) for (int r = 0; r < 8; r++) {
    u8 lo = chrrd(tb * 0x1000 + tile * 16 + r), hi = chrrd(tb * 0x1000 + tile * 16 + r + 8);
    for (int b = 0; b < 8; b++) { int c = ((lo >> (7 - b)) & 1) | (((hi >> (7 - b)) & 1) << 1);
      int x = tb * 128 + (tile % 16) * 8 + b, y = (tile / 16) * 8 + r; memcpy(rgb + (y * W + x) * 3, g[c], 3); }
  }
  write_png(fn, rgb, W, H); free(rgb);
}

typedef struct { int frame; char cmd[16]; char a1[260]; char a2[64]; } Cmd;
static int parsebtn(const char *s) {
  int b = 0; for (; *s; s++) switch (*s) { case 'A': b |= 1; break; case 'B': b |= 2; break; case 's': b |= 4; break; case 'S': b |= 8; break;
    case 'U': b |= 16; break; case 'D': b |= 32; break; case 'L': b |= 64; break; case 'R': b |= 128; break; }
  return b;
}
int main(int argc, char **argv) {
  if (argc < 3) { fprintf(stderr, "usage: nesemu rom.nes script.txt\n"); return 1; }
  FILE *f = fopen(argv[1], "rb"); if (!f) { perror(argv[1]); return 1; }
  u8 hdr[16]; fread(hdr, 1, 16, f);
  prgsz = hdr[4] * 16384; chrsz = hdr[5] * 8192; mapper = (hdr[6] >> 4) | (hdr[7] & 0xF0); mirrorV = hdr[6] & 1;
  if (hdr[6] & 4) fseek(f, 512, SEEK_CUR);
  prg = malloc(prgsz); fread(prg, 1, prgsz, f);
  if (chrsz) { chr = malloc(chrsz); fread(chr, 1, chrsz, f); } else chrram = 1;
  fclose(f);
  if (mapper != 0 && mapper != 1) { fprintf(stderr, "mapper %d unsupported\n", mapper); return 1; }
  if (mapper == 1) m1update();
  Cmd *cmds = calloc(4096, sizeof(Cmd)); int nc = 0;
  FILE *sf = fopen(argv[2], "r"); char ln[512];
  while (sf && fgets(ln, sizeof ln, sf) && nc < 4096) {
    if (ln[0] == '#' || ln[0] == '\n') continue;
    Cmd *c = &cmds[nc]; c->a1[0] = c->a2[0] = 0;
    if (sscanf(ln, "%d %15s %259s %63s", &c->frame, c->cmd, c->a1, c->a2) >= 2) nc++;
  }
  if (sf) fclose(sf);
  for (int i = 1; i < nc; i++) { Cmd c = cmds[i]; int j = i - 1; while (j >= 0 && cmds[j].frame > c.frame) { cmds[j + 1] = cmds[j]; j--; } cmds[j + 1] = c; }
  PC = rd16(0xFFFC);
  int ci = 0;
  for (frame = 0; frame < 1000000; frame++) {
    while (ci < nc && cmds[ci].frame <= frame) {
      Cmd *c = &cmds[ci++];
      if (!strcmp(c->cmd, "in1")) pad[0] = parsebtn(c->a1);
      else if (!strcmp(c->cmd, "in2")) pad[1] = parsebtn(c->a1);
      else if (!strcmp(c->cmd, "shot")) shot(c->a1, c->a2[0] ? atoi(c->a2) : 1);
      else if (!strcmp(c->cmd, "poke")) wr((u16)strtol(c->a1, 0, 16), (u8)strtol(c->a2, 0, 16));
      else if (!strcmp(c->cmd, "pt")) ptdump(c->a1);
      else if (!strcmp(c->cmd, "watch")) watch[nwatch++] = (int)strtol(c->a1, 0, 16);
      else if (!strcmp(c->cmd, "unwatch")) nwatch = 0;
      else if (!strcmp(c->cmd, "apulog")) apulog = fopen(c->a1, "w");
      else if (!strcmp(c->cmd, "apuoff")) { if (apulog) fclose(apulog); apulog = NULL; }
      else if (!strcmp(c->cmd, "dump")) { FILE *o = fopen(c->a1, "wb"); fwrite(ram, 1, 2048, o); fwrite(oam, 1, 256, o); fwrite(pal, 1, 32, o); fwrite(vram, 1, 2048, o);
        u8 st[8] = {pctrl, pmask, m1ctrl, m1chr0, m1chr1, m1prg, 0, 0}; fwrite(st, 1, 8, o); fclose(o); }
      else if (!strcmp(c->cmd, "rwatch")) { sscanf(c->a1, "%x-%x", &rw_lo, &rw_hi); sscanf(c->a2, "%x-%x", &rw_pclo, &rw_pchi); }
      else if (!strcmp(c->cmd, "wwatch")) sscanf(c->a1, "%x-%x", &ww_lo, &ww_hi);
      else if (!strcmp(c->cmd, "wtrack")) memset(wcount, 0, sizeof wcount);
      else if (!strcmp(c->cmd, "wdump")) { FILE *o = fopen(c->a1, "wb"); fwrite(wcount, 1, 2048, o); fclose(o); }
      else if (!strcmp(c->cmd, "end")) { if (apulog) fclose(apulog); return 0; }
    }
    run_frame();
  }
  return 0;
}
