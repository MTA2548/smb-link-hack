"""Builds 'Super Mario Bros. - Link Hack.nes' and its IPS patch from the untouched original ROMs.

ROM layout (MMC1, 64 KB PRG + 16 KB CHR):
  PRG bank 0  = SMB $8000-$BFFF (fixed at $8000)
  PRG bank 1  = SMB $C000-$FFFF plus the hack's code in areas SMB no longer uses (see FREE below)
                and Link's hurt sample
  PRG bank 2  = bank 1 plus the music data moved to $C000; swapped in only while the sound engine runs
  PRG bank 3  = copy of bank 1 (MMC1 power-on safety)
  CHR bank 0  = sprites with big-Link tiles,  CHR bank 1 = background (with the LINK title logo)
  CHR bank 2  = sprites with small-Link tiles, CHR bank 3 = background (same as bank 1)

Usage: build.py            build the hack
       build.py --previous build without the latest changes (attack pose fix, title logo, new items)
                           into work\\previous.nes, to check this script against an older build
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from asm6502 import assemble
from dis6502 import dis
import linkart
import titlelogo
import items
import coins
from z2art import tile816

PREVIOUS = "--previous" in sys.argv

from z2art import ROM_DIR as NES_DIR           # the two original ROMs (environment variable SMB_LINK_ROMS)
SMB = os.path.join(NES_DIR, "Super Mario Bros. (World).nes")
Z2 = os.path.join(NES_DIR, "Zelda II - The Adventure of Link (USA).nes")
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # the project folder
OUT = os.path.join(OUT_DIR, "Super Mario Bros. - Link Hack.nes")
IPS = os.path.join(OUT_DIR, "Super Mario Bros. - Link Hack.ips")
NEON64 = r"S:\Roms\N64\tools\neon64\neon64bu.rom"
N64_OUT = r"S:\Roms\N64\Super Mario Bros. - Link Hack [Neon64].z64"
if PREVIOUS:
    OUT = os.path.join(OUT_DIR, "work", "previous.nes")
    IPS = os.path.join(OUT_DIR, "work", "previous.ips")

smb = open(SMB, "rb").read()
z2 = open(Z2, "rb").read()
assert len(smb) == 40976 and smb[:4] == b"NES\x1a"
LO = bytearray(smb[16:16 + 0x4000])
HI = bytearray(smb[16 + 0x4000:16 + 0x8000])
CHR = smb[16 + 0x8000:]


def patch(addr, data, expect=None):
    """Write bytes at a CPU address in the original SMB layout; optionally check what is replaced."""
    data = bytes(data)
    buf, off = (LO, addr - 0x8000) if addr < 0xC000 else (HI, addr - 0xC000)
    if expect is not None:
        old = bytes(buf[off:off + len(expect)])
        assert old == bytes(expect), "unexpected bytes at %04X: %s" % (addr, old.hex())
    buf[off:off + len(data)] = data


def w16(v):
    return bytes([v & 0xFF, v >> 8])


# ------------------------------------------------------------------ graphics
PLAYER_SLOTS = list(range(0x00, 0x50)) + [0x58, 0x59, 0x5A, 0x5C, 0x5D, 0x5E, 0x5F, 0x90, 0x91, 0x92, 0x93, 0x9E, 0x9F]
BLANK = 0xFC


def mirror(g):
    return [list(reversed(r)) for r in g]


def tiles_of(g, rows):
    """Split a 16-wide grid into 8x8 tiles, row-major (L,R per row); rows = number of 8px rows."""
    out = []
    for ty in range(rows):
        for tx in range(2):
            out.append(tuple(tuple(g[ty * 8 + y][tx * 8 + x] for x in range(8)) for y in range(8)))
    return out


def encode_tile(t):
    b = bytearray(16)
    for y in range(8):
        for x in range(8):
            c = t[y][x]
            if c & 1: b[y] |= 0x80 >> x
            if c & 2: b[y + 8] |= 0x80 >> x
    return bytes(b)


EMPTY = tuple(tuple(0 for _ in range(8)) for _ in range(8))

# Every SMB frame: offset -> (grid, which bank set, number of 8px rows drawn from the bottom)
B, S = linkart.BIG, linkart.SMALL
F = lambda g: mirror(g)            # Link faces left in Zelda II; SMB's player art faces right
FRAMES = [
    (0x00, F(B["walk1"]), "big", 4), (0x08, F(B["walk2"]), "big", 4), (0x10, F(B["walk3"]), "big", 4),
    (0x18, F(B["skid"]), "big", 4), (0x20, F(B["jump"]), "big", 4),
    (0x28, F(B["swim1"]), "big", 4), (0x30, F(B["swim2"]), "big", 4), (0x38, F(B["swim3"]), "big", 4),
    (0x40, F(B["climb1"]), "big", 4), (0x48, F(B["climb2"]), "big", 4),
    (0x50, F(B["crouch"]), "big", 4), (0x58, F(B["throw"]), "big", 4),
    (0x60, F(S["walk1"]), "small", 2), (0x68, F(S["walk2"]), "small", 2), (0x70, F(S["walk3"]), "small", 2),
    (0x78, F(S["skid"]), "small", 2), (0x80, F(S["jump"]), "small", 2),
    (0x88, F(S["swim1"]), "small", 2), (0x90, F(S["swim2"]), "small", 2), (0x98, F(S["swim3"]), "small", 2),
    (0xA0, F(S["climb1"]), "small", 2), (0xA8, F(S["climb2"]), "small", 2), (0xB0, F(S["killed"]), "small", 2),
    (0xB8, F(S["stand"]), "both", 2), (0xC0, F(B["grow"])[8:], "both", 3), (0xC8, F(B["stand"]), "both", 4),
    (0xD0, F(B["death"]), "big", 4),                 # death silhouette and knockback (hurt) pose
    (0xD8, F(B["cthrust"]), "big", 4),               # crouching sword thrust
    (0xE0, F(S["thrust"]), "small", 2),              # small Link's sword thrust
]
BEAM_TILE = mirror(linkart.BEAM)
SPARKS = [[[2 if c else 0 for c in row] for row in tile816(t)[8:16]] for t in (0x78, 0x7A)]   # beam-hit sparkle


def build_chr():
    assign = {"big": {}, "small": {}}      # tile pattern -> slot, per bank
    free = {"big": list(PLAYER_SLOTS), "small": list(PLAYER_SLOTS)}

    def alloc(banks, pat):
        if pat == EMPTY:
            return BLANK
        for k in banks:
            if pat in assign[k]:
                slot = assign[k][pat]
                if all(assign[b].get(pat) == slot for b in banks):
                    return slot
        common = [s for s in free[banks[0]] if all(s in free[b] for b in banks)]
        if not common:
            raise SystemExit("out of sprite tile slots in bank(s) %s" % (banks,))
        slot = common[0]
        for b in banks:
            free[b].remove(slot); assign[b][pat] = slot
        return slot

    beam = tuple(tuple(r) for r in BEAM_TILE)
    beam_slot = alloc(["big", "small"], beam)
    spark_slots = [alloc(["big", "small"], tuple(tuple(r) for r in t)) for t in SPARKS]
    table = bytearray([BLANK] * 0xE8)
    # shared frames first so they land on the same slot numbers in both banks
    for off, g, bank, rows in sorted(FRAMES, key=lambda f: f[2] != "both"):
        banks = ["big", "small"] if bank == "both" else [bank]
        ts = tiles_of(g[len(g) - rows * 8:], rows)
        slots = [alloc(banks, t) for t in ts]
        table[off + 8 - len(slots):off + 8] = bytes(slots)
    item_slots = None
    if not PREVIOUS:                       # Master Sword and Magic Jar power-ups (visible in both banks)
        item_slots = {name: [alloc(["big", "small"], tuple(tuple(r) for r in t)) for t in tiles]
                      for name, tiles in items.TILES.items()}
    out = {}
    for k in ("big", "small"):
        spr = bytearray(CHR[:0x1000])
        for slot in PLAYER_SLOTS:                       # clear Mario leftovers
            spr[slot * 16:slot * 16 + 16] = bytes(16)
        for pat, slot in assign[k].items():
            spr[slot * 16:slot * 16 + 16] = encode_tile(pat)
        out[k] = bytes(spr)
    used = {k: len(PLAYER_SLOTS) - len(free[k]) for k in free}
    return out, bytes(table), beam_slot, spark_slots, item_slots, used


SPR, GFX_TABLE, BEAM_SLOT, SPARK_SLOTS, ITEM_SLOTS, TILES_USED = build_chr()

# ------------------------------------------------------------------ sound data from Zelda II
Z2_FIXED = 16 + 7 * 0x4000
HURT_SAMPLE = z2[Z2_FIXED + 0x3300:Z2_FIXED + 0x3300 + 0x0C * 16 + 1]   # DMC sample at $F300, 193 bytes
SAMPLE_ADDR = 0xFE00


# Zelda II's death tone on pulse 1: $4000 value for each frame (captured from the game), plus 4 pitches.
def death_volumes():
    vals = [0x5F]
    for k in range(1, 191):
        g, j = (k - 1) >> 2, (k - 1) & 3
        duty = 0x50 if g % 2 == 0 else 0x90
        vals.append(duty | max(0, 0xE - g // 6 - j))
    return vals
DEATH_VOL = death_volumes()
# stored compactly: one value per 4-frame step; frame k>=1 plays DEATH_BASE[(k-1)>>2] - ((k-1)&3)
DEATH_BASE = [(0x50 if g % 2 == 0 else 0x90) | (0xE - g // 6) for g in range(48)]
assert all(DEATH_BASE[(k - 1) >> 2] - ((k - 1) & 3) == DEATH_VOL[k] for k in range(1, 191))
DEATH_PERIODS = [0x0B50, 0x0AFF, 0x0B30, 0x0ADF]
# Zelda II's knockback hop: pixels above the starting height for each frame
DEATH_HOP = [0, 3, 5, 7, 8, 9, 10, 10, 10, 10, 9, 8, 7, 6, 4, 2, 0]

# ------------------------------------------------------------------ new code
COLORS = [0x22, 0x18, 0x36, 0x2A,    # Link
          0x22, 0x0F, 0x10, 0x2D,    # Dark Link
          0x22, 0x18, 0x36, 0x16,    # red-tunic (fire) Link
          0x22, 0x0F, 0x10, 0x06]    # fire Dark Link
# new layout, indexed by (status * 2 + player) * 4: small and big share colours; status 3 (hammer) is blue
COLORS_HAMMER = COLORS[0:8] + COLORS[0:8] + COLORS[8:16] + \
                [0x22, 0x18, 0x36, 0x12,    # blue-tunic (hammer) Link
                 0x22, 0x0F, 0x10, 0x02]    # hammer Dark Link

SRC = """
DeathSnd = $07D0               ; frame counter of the Zelda II death tone (0 = off); unused SMB RAM
SwordSnd = $07D1               ; frame counter of the Zelda II sword/beam sound (0 = off)
LandTimer = $07D2              ; frames of landing crouch left after a jump
DeathY = $07D3                 ; Link's height when hit (landing point for the death knockback)
MeleeCnt = $07D4               ; per sword shot: frames left of a short stab (0 = real beam)
MeleeSnd = $07D6               ; 1 = sword sound without the beam tone
TimerControl = $0747
InjuryTimer = $079E
CrouchFlag = $0714
PlayerSpeedX = $57
PlayerSpeedY = $9F
PlayerFacing = $33
SavedJoypad = $06FC
PlayerCtrlRoutine = $B0E9
PlayerSize = $0754
CurrentPlayer = $0753
PlayerStatus = $0756
EventMusicQueue = $FC
Engine = $0E
VRAM_Offset = $0300
SoundEngine = $F2D0

; ---- MMC1 register writers (A = value, 5 serial writes)
SetCtrl:  sta $8000
          lsr
          sta $8000
          lsr
          sta $8000
          lsr
          sta $8000
          lsr
          sta $8000
          rts
SetChr0:  sta $A000
          lsr
          sta $A000
          lsr
          sta $A000
          lsr
          sta $A000
          lsr
          sta $A000
          rts
SetChr1:  sta $C000
          lsr
          sta $C000
          lsr
          sta $C000
          lsr
          sta $C000
          lsr
          sta $C000
          rts
SetPrg:   sta $E000
          lsr
          sta $E000
          lsr
          sta $E000
          lsr
          sta $E000
          lsr
          sta $E000
          rts

; ---- power-on / reset: put MMC1 in a known state, then run SMB's reset code
ResetStub:
          sei
          cld
          lda #$80
          sta $8000           ; reset MMC1: last bank fixed at $C000 (bank 3 = copy of this bank)
          lda #1
          jsr SetPrg
          lda #$1A            ; 4 KB CHR banks, $8000 fixed, $C000 switchable, vertical mirroring
          jsr SetCtrl         ; now $8000 = bank 0 (SMB), $C000 = bank 1 (this code)
          lda #0
          jsr SetChr0
          lda #1
          jsr SetChr1
          jmp $8000

; ---- called from the NMI instead of SMB's sound engine
SoundWrap:
          lda PlayerSize      ; pick the sprite tile bank: big Link (0) or small Link (2)
          asl
          jsr SetChr0
          lda #2              ; bank 2 has the music data in it
          jsr SetPrg
          jsr SoundEngine
          lda $0776           ; paused: leave the channels alone
          lsr
          bcs SW_Paused
          jsr SwordSound
          jsr DeathSound      ; after the sword sound, so the death tone wins
SW_Paused:
          lda #1
          jsr SetPrg
          rts

; SMB rewrites $4015 every frame; keep the sample channel (bit 4) running while it plays
ApuEnF:   lda $4015
          and #$10
          ora #$0F
          sta $4015
          rts
ApuEnB:   lda $4015
          and #$10
          ora #$0B
          sta $4015
          rts

; ---- Link's hurt grunt (Zelda II's DMC sample)
PlayHurt: lda #$0F
          sta $4010
          lda #SAMPLE_REG
          sta $4012
          lda #$0C
          sta $4013
          lda #$0F
          sta $4015
          lda #$1F
          sta $4015
          rts

; ---- Link is hit (big/red: hurt, small: killed): grunt and knockback away from where he faces
HurtStart:
          jsr PlayHurt
          lda $07F8          ; time ran out (timer digits all 0): no knockback
          ora $07F9
          ora $07FA
          beq HS_Done
          ldy PlayerFacing
          lda KnockSpd-1,y
          sta PlayerSpeedX
          lda $CE
          sta DeathY          ; height to land back on if this hit kills him
          lda #KNOCK_VY       ; Zelda II hop: up a little, then back down
          sta PlayerSpeedY
          lda #KNOCK_GRAV
          sta $0709          ; SMB's rising and falling gravity
          sta $070A
          lda #0
          sta $0433          ; vertical sub-pixel speed
          lda #1
          sta $1D            ; airborne
HS_Done:  rts
KnockSpd: .db $E8,$18

; ---- game engine routine $0A (replaces SMB's shrink): knockback in the hurt pose, then small
LinkHurt:
          lda TimerControl
          cmp #$E0            ; 31 frames of knockback
          bcc LH_Done
          lda #0
          sta SavedJoypad     ; no control while knocked back
          jsr KnockKeep
          jsr PlayerCtrlRoutine
          jmp ClampLeft
LH_Done:  lda #1
          sta PlayerSize      ; now small Link
          lda #0
          sta TimerControl
          lda #$08
          sta Engine
          rts

; start of the death flash: silence the music, start the death tone
FlashStart:
          lda #$80
          sta EventMusicQueue
          lda #1
          sta DeathSnd
          lda #0
          sta SwordSnd
          sta InjuryTimer     ; stop flickering: solid silhouette
          rts

; falling into a pit: grunt, then straight to the death flash
PitDeath: pha
          lda #1
          sta $0712           ; DeathMusicLoaded, so this only runs once
          jsr PlayHurt
          lda #$0B
          sta Engine
          lda #$E0            ; skip the knockback part
          sta TimerControl
          pla
          rts

; ---- game engine routine $0B: Zelda II style death (replaces Mario's hop and fall)
LinkDeath:
          lda TimerControl    ; counts down from $FF once per frame
          eor #$FF            ; A = frames since death
          cmp #32
          bcs LD_Flash
          lda #8
          sta InjuryTimer     ; flicker like Zelda II while knocked back
          jmp DeathKnock
LD_Flash: bne LD_Go
          jsr FlashStart
          lda #32
LD_Go:    sec
          sbc #32             ; A = frames since the flash began
          cmp #146
          bcc LD_Run
          lda #$06            ; done: lose a life
          sta Engine
          rts
LD_Run:   ldy #$0F            ; first frames: everything black
          cmp #5
          bcc LD_Pal
          and #3
          tay
          lda FlashCols,y
          tay
LD_Pal:   sty $00
          ldx VRAM_Offset
          lda #$3F
          sta $0301,x
          lda #$00
          sta $0302,x
          lda #$20
          sta $0303,x
          ldy #0
LD_Loop:  lda $00             ; every colour = flash colour (hides level and enemies)...
          cpy #$11
          bcc LD_Put
          cpy #$14
          bcs LD_Put
          lda #$0F            ; ...except Link's palette: black silhouette
LD_Put:   sta $0304,x
          inx
          iny
          cpy #$20
          bne LD_Loop
          lda #0
          sta $0304,x
          txa
          clc
          adc #3
          sta VRAM_Offset
          rts
FlashCols: .db $16,$12,$16,$2A

; death pose: small or big silhouette frame
DeathGfx: lda #$B0
          ldy PlayerSize
          bne DG_Done
          lda #$D0
DG_Done:  rts

; ---- per-frame player of the Zelda II death tone (pulse 1)
DeathSound:
          ldx DeathSnd
          beq DS_Done
          dex
          cpx #191
          bcc DS_Play
          lda #$10
          sta $4000
          lda #0
          sta DeathSnd
          rts
DS_Play:  lda #$5F
          cpx #0
          beq DS_Vol
          txa
          sec
          sbc #1
          pha
          and #3
          sta $00            ; frame within the 4-frame step
          pla
          lsr
          lsr
          tay
          lda DeathBase,y
          sec
          sbc $00
DS_Vol:   sta $4000
          txa
          and #3
          bne DS_Next
          lda #$CA
          sta $4001
          txa
          lsr
          lsr
          and #3
          tay
          lda DeathPerLo,y
          sta $4002
          lda DeathPerHi,y
          sta $4003
DS_Next:  inc DeathSnd
DS_Done:  rts

; ---- sword beam (SMB fireball)
BeamInit: ldy $33             ; PlayerFacingDir: 1 = right, 2 = left
          lda $86
          clc
          adc BeamXOfs-1,y
          sta $8D,x
          lda $6D
          adc BeamXHi-1,y
          sta $74,x
          lda $CE
          clc
          adc #BEAM_YOFS
          ldy CrouchFlag      ; crouching: the blade is lower
          beq BI_Y
          clc
          adc #BEAM_YCROUCH
BI_Y:     ldy PlayerSize      ; small Link's sword is lower
          beq BI_Big
          clc
          adc #SMALL_YOFS
BI_Big:   sta $D5,x
          lda PlayerStatus    ; red tunic: real beam; otherwise a short stab
          cmp #2
          lda #0
          bcs BI_Set
          lda #MELEE_FRAMES
BI_Set:   sta MeleeCnt,x
          rts
BeamXOfs: .db BEAM_XR, BEAM_XL
BeamXHi:  .db 0, $FF

; ---- Zelda II jump animation: crouched while rising, legs apart while falling, crouch on landing
JumpFrame:
          lda #8
          sta LandTimer
          lda #0
          sta $070D
          lda #$20            ; crouched pose
          ldy CrouchFlag
          bne JF_Size
          ldy PlayerSpeedY
          bmi JF_Size         ; still rising
          lda #$08            ; falling: legs apart
JF_Size:  ldy PlayerSize
          beq JF_Done
          clc
          adc #$60            ; same poses from the small set
JF_Done:  rts

DrawBeam: ldy $06F1,x
          lda MeleeCnt,x      ; a stab: the blade in Link's colours, gone after a few frames
          beq DB_Beam
          dec MeleeCnt,x
          bne DB_Stab
          lda #0
          sta $24,x
          lda #$F8
          sta $0200,y
          rts
DB_Stab:  lda $03BA            ; blade held in Link's hand (the hitbox itself reaches further)
          sta $0200,y
          lda #BEAM_TILE
          sta $0201,y
          ldx PlayerFacing
          lda $03AD
          clc
          adc StabXOfs-1,x
          sta $0203,y
          lda StabAttr-1,x    ; palette 0, flipped when facing left
          sta $0202,y
          rts
StabXOfs: .db 16,$F8
StabAttr: .db $00,$40
DB_Beam:  lda $09            ; beam: flicker between two palettes every frame, like Zelda II
          and #1
          ora #2
DB_Draw:  sta $00
          lda $03BA
          sta $0200,y
          lda $03AF
          sta $0203,y
          lda #BEAM_TILE
          sta $0201,y
          lda $5E,x           ; moving left -> flip horizontally
          and #$80
          lsr
          ora $00
          sta $0202,y
          rts

; Zelda II keeps the push going for a while before Link slows down
KnockKeep:
          lda TimerControl
          cmp #$F0           ; first 16 frames
          bcc KK_Done
          lda $0759
          bne KK_Done
          ldy PlayerFacing
          lda KnockSpd-1,y
          sta PlayerSpeedX
KK_Done:  rts

; SMB doesn't stop the player at the left screen edge in these states, so do it here
ClampLeft:
          lda $86            ; player X - screen left X
          sec
          sbc $071C
          sta $00
          lda $6D
          sbc $071A
          bmi CL_Clamp        ; left of the screen
          bne CL_Done
          lda $00
          cmp #8
          bcs CL_Done
CL_Clamp: lda $071C
          clc
          adc #8
          sta $86
          lda $071A
          adc #0
          sta $6D
          lda #0
          sta PlayerSpeedX
CL_Done:  rts

; ---- overflow area after the hurt sample ($FEC1-$FEFF)
          .org SAMPLE_END
; SMB's ?-block colour cycling would show through the death flash: skip it while Link is dying
ColorRotCheck:
          lda Engine
          cmp #$0B
          bne CR_Normal
          lda #1              ; Z=0: skip the rotation
          rts
CR_Normal:
          lda $09
          and #7
          rts

; death knockback: SMB lets a dying player fall through the floor, so hold Link's height
DeathKnock:
          jsr KnockKeep
          jsr PlayerCtrlRoutine   ; knockback (engine $0B ignores the controller)
          lda TimerControl    ; a dying player has no floor and weak gravity in SMB,
          eor #$FF            ; so play Zelda II's hop from a height table instead
          tay
          lda DeathY
          cpy #17
          bcs DK_Set
          sec
          sbc DeathHop,y
DK_Set:   sta $CE
          lda #0
          sta PlayerSpeedY
          jmp ClampLeft
"""

# Free areas for new code (everything else in $EE17-$FEFF is SMB code, data or the sample):
#   $EE17-$EEE6  SMB's player graphics table (moved to GfxTable so it could grow)
#   $EF0D-$EF32  SMB's swim-kick tile swapping (switched off by an RTS at $EF0C)
#   $F0EA-$F128  SMB's player-mirroring routine (switched off by an RTS at $F0E9)
#   $F90D-$FDFF  SMB's music data (moved to bank 2), then the sample, then $FEC1-$FEFF
CODE_ORG = 0xEE17
FREE = [(0xEE17, 0xEEE7), (0xEF0D, 0xEF33), (0xF0EA, 0xF129), (0xF90D, SAMPLE_ADDR), (SAMPLE_ADDR + len(HURT_SAMPLE), 0xFF00)]
GAPS = [(FREE[n][1], FREE[n + 1][0]) for n in range(len(FREE) - 1)]

BLOCK_EE17 = """
; replaces the fireball sound: start Zelda II's sword swish (+ beam tone when a beam is fired)
SwordStart:
          lda #1
          sta SwordSnd
          lda PlayerStatus    ; small/big Link: the swish only (no beam, no beam tone)
          cmp #2
          lda #0
          bcs SWS_Set
          lda #1
SWS_Set:  sta MeleeSnd
          rts

; per-frame player of the sword sound (noise swish for 15 frames, pulse-1 beam tone for 58)
SwordSound:
          ldx SwordSnd
          beq SS_Done
          dex                 ; X = frame of the sound
          cpx #15
          bcs SS_Sq
          lda NoiseVol,x
          sta $400C
          lda NoisePer,x
          sta $400E
          lda #$08
          sta $400F
SS_Sq:    lda MeleeSnd
          beq SS_Tone
          cpx #15
          bcc SS_Next
          lda #0              ; swish finished, leave pulse 1 alone
          sta SwordSnd
          rts
SS_Tone:  txa
          beq SS_Next
          cpx #59
          bcs SS_End
          dex
          txa
          lsr
          lsr
          tay                 ; 4-frame step of the tone
          lda SqVol,y
          sta $4000
          lda #$8A
          sta $4001
          tya
          and #1
          tay
          lda SqPer,y
          sta $4002
          lda #$08
          sta $4003
SS_Next:  inc SwordSnd
SS_Done:  rts
SS_End:   lda #$90
          sta $4000
          lda #0
          sta SwordSnd
          rts
NoiseVol: .db $13,$16,$19,$1F,$1F,$10,$10,$10,$10,$10,$10,$10,$10,$10,$10
NoisePer: .db $0D,$0C,$0B,$07,$09,$0D,$0C,$0B,$07,$09,$0D,$0C,$0B,$07,$09
SqVol:    .db $5F,$9E,$5D,$9C,$5B,$9A,$59,$98,$57,$96,$55,$94,$53,$92,$51
SqPer:    .db $35,$50

; sword thrust frame: standing, crouching or small
ThrowGfx: lda #$58
          ldy CrouchFlag
          beq TG_Size
          lda #$D8
TG_Size:  ldy PlayerSize
          beq TG_Done
          lda #$E0            ; small Link's thrust
TG_Done:  rts
"""

BLOCK_EF0D = """
; hurt pose while knocked back or dying (sets Z like the 'cmp #$0B' it replaces)
IsHurt:   lda Engine
          cmp #$0B
          beq IH_Done
          cmp #$0A
IH_Done:  rts

; on the ground: show the landing crouch for a few frames (Y/Z as SMB's crouch check expects)
GroundHook:
          lda LandTimer
          beq GH_Norm
          dec LandTimer
          ldy #6              ; big crouch
          lda PlayerSize
          beq GH_Big
          ldy #0              ; small: the crouched jump pose
GH_Big:   lda #1
          rts
GH_Norm:  ldy #6
          lda CrouchFlag
          rts
"""

BLOCK_F0EA = """
; Zelda II's beam-hit sparkle instead of Mario's fireball burst: cross for 3 frames, dots for 4
BeamHit:  ldy $06F1,x         ; the beam's own sprite
          lda MeleeCnt,x      ; a stab leaves no sparkle
          bne BH_End
          lda $24,x
          inc $24,x
          and #$7F            ; frames since the hit
          cmp #7
          bcs BH_End
          cmp #3
          lda #SPARK1
          bcc BH_Tile
          lda #SPARK2
BH_Tile:  sta $0201,y
          lda $03BA
          sta $0200,y
          lda $03AF
          sta $0203,y
          lda #$02            ; palette 2: white sparkle
          sta $0202,y
          rts
BH_End:   lda #0
          sta $24,x
          sta MeleeCnt,x
          lda #$F8
          sta $0200,y
          rts
"""


TITLE_BANK_SRC = """          lda #1              ; background tiles: the title-only copy (bank 3, with the LINK logo)
          ldy $0770           ; while on the title screen / attract demo, the normal bank otherwise
          bne SW_Game
          lda #3
SW_Game:  jsr SetChr1
"""


# Hammer upgrade, bank 2 (reached through the stubs in HAMMER_MAIN_SRC): Hammer Bros drop a hammer,
# and the thrown hammer's sprites
HAMMER_BANK2_SRC = """
HamDrop = $07CF                ; one bit per enemy slot: this defeated Hammer Bro already dropped its hammer
HamX1 = $E4C0                  ; SMB's spinning-hammer sprite tables (DrawHammer)
HamY1 = $E4C4
HamX2 = $E4C8
HamY2 = $E4CC
HamT1 = $E4D0
HamT2 = $E4D4
HamAttr = $E4D8

; ---- every frame, before the enemies run: a defeated Hammer Bro leaves a hammer behind
HamCheck: ldx #4
HC_Loop:  lda $0F,x           ; enemy slot in use,
          beq HC_Clear
          lda $16,x           ; a Hammer Bro,
          cmp #5
          bne HC_Clear
          lda $1E,x           ; and defeated (stomped, slashed, hit by a beam or hammer...)
          and #$20
          beq HC_Clear
          lda HamBit,x
          bit HamDrop
          bne HC_Next         ; its hammer was already dropped
          ora HamDrop
          sta HamDrop
          lda $14             ; the power-up slot is busy: no hammer this time
          bne HC_Next
          lda #$2E            ; power-up object in slot 5, where the Hammer Bro was
          sta $1B
          lda $6E,x
          sta $73
          lda $87,x
          sta $8C
          lda $CF,x
          sta $D4
          lda $B6,x
          sta $BB
          lda #4              ; power-up type 4: hammer
          sta $39
          lda #$80            ; already out (no rising out of a block)
          sta $23
          lda #1
          sta $14
          lda #3
          sta $049F           ; bounding box like the other power-ups
          lda #0
          sta $03CA           ; in front of the background
          sta $5D             ; no walking: it just drops to the ground
          sta $A5
          beq HC_Next
HC_Clear: lda HamBit,x
          eor #$FF
          and HamDrop
          sta HamDrop
HC_Next:  dex
          bpl HC_Loop
          rts
HamBit:   .db 1,2,4,8,16

; ---- the thrown hammer (X = fireball slot, Y = its sprite) (an SMB fireball slot): two sprites, spinning like the Hammer Bros' hammers
DrawHam:  stx $01
          lda $09
          lsr
          lsr
          and #3
          tax                 ; spin frame
          lda $03BA
          clc
          adc HamY1,x
          sta $0200,y
          lda $03AF
          clc
          adc HamX1,x
          sta $0203,y
          lda HamT1,x
          sta $0201,y
          lda HamAttr,x
          sta $0202,y
          pha
          lda $0200,y         ; second sprite, from SMB's hammer tables
          clc
          adc HamY2,x
          pha
          lda $0203,y
          clc
          adc HamX2,x
          pha
          lda HamT2,x
          ldx $01
          ldy $06EC,x
          sta $0201,y
          pla
          sta $0203,y
          pla
          sta $0200,y
          pla
          sta $0202,y
          rts
"""

# Hammer upgrade, main code area: stubs that run the bank-2 routines
# the old death knockback: a fixed hop curve at the height Link was hit (SMB lets a dying player
# fall through floors); replaced by real falling with collision (DeathCol / DeathAir)
DEATH_HOP_SRC = """          lda TimerControl    ; a dying player has no floor and weak gravity in SMB,
          eor #$FF            ; so play Zelda II's hop from a height table instead
          tay
          lda DeathY
          cpy #17
          bcs DK_Set
          sec
          sbc DeathHop,y
DK_Set:   sta $CE
          lda #0
          sta PlayerSpeedY
          jmp ClampLeft
"""

DEATH_COL_SRC = """
; SMB gives a dying player no floor collision and weak gravity. During the death knockback (the first
; 32 frames, longer while still falling) Link collides and falls like a live player instead.
; Returns Z=1 for SMB's dying-player behaviour, otherwise Z=0 and A = engine routine.
DeathCol: lda Engine
          cmp #$0B
          bne DC_Ret
          lda TimerControl
          cmp #$E0
          lda #$0B
          bcs DC_Ret
          cmp #$0B
DC_Ret:   rts

"""

HAMMER_MAIN_SRC = """
HamFar:   lda #2
          jsr SetPrg
          jsr HAM_CHECK
          lda #1
          jsr SetPrg
          jmp $B624           ; what the patched call did: SMB's fireball (sword) routine
DrawHamFar:
          lda #2
          jsr SetPrg
          jsr DRAW_HAM
          lda #1
          jmp SetPrg
"""

# Hammer upgrade, small routines in the $EE17 block
HAMMER_EE17_SRC = """
HamPrev = $07CE                ; Link's form before the hammer (0 small, 1 big, 2 red): a hit returns to it
; ---- power-up collision, types 3 and up (patched over SMB's 'cmp #3 / beq 1-up')
PupMore:  cmp #3
          bne PM_Ham
          jmp $D83A           ; 1-up
PM_Ham:   cmp #4
          beq HammerGet
          jmp $D816           ; star
HammerGet:
          lda PlayerStatus
          cmp #3
          beq HG_Done         ; already has it: just the points
          sta HamPrev
          pha
          lda #3              ; blue tunic, hammers
          sta PlayerStatus
          jsr $85F1           ; SMB: load the player's colours
          ldx $08
          pla
          bne HG_Flash
          lda #$09            ; small Link grows first
          jmp $D847
HG_Flash: lda #$0C            ; big Link: the fire flower's flashing
          jmp $D847
HG_Done:  rts

; hit while blue: back to the form he had before the hammer (SMB stores 0 = small here)
HurtStatus:
          cpx #3
          bne HS2_Set
          lda HamPrev
HS2_Set:  sta PlayerStatus
          rts

; knockback over but Link still in the air: keep falling until he lands (Zelda II), C=1
DeathAir: lda $1D
          beq DA_No           ; on the ground
          cmp #3
          beq DA_No           ; on a vine
          lda $0704
          bne DA_No           ; swimming
          lda $B5
          cmp #1
          bne DA_No           ; fell below the screen (pit)
          inc TimerControl    ; hold the death timer in the knockback part
          sec
          rts
DA_No:    clc
          rts

; thrown hammer: no walls or floors stop it
HamBG:    lda PlayerStatus
          cmp #3
          beq HB2_Done
          jmp $E1C8           ; SMB: fireball/beam hits a wall or floor
HB2_Done: rts

; thrown hammer: start upwards, at a hammer's speed (the beam: straight, 2 px per frame)
HamInit:  lda #0
          ldy PlayerStatus
          cpy #3
          bne HI_Set
          ldy PlayerFacing
          lda HamXSpd-1,y
          sta $5E,x
          lda #HAM_VY
HI_Set:   sta $A6,x
          rts
HamXSpd:  .db HAM_VX, $100-HAM_VX
; thrown hammer: gravity (the beam: none)
HamGrav:  lda #0
          ldy PlayerStatus
          cpy #3
          bne HGr_Set
          lda #HAM_GRAV
HGr_Set:  sta $00
          rts
"""


HOLD_BLADE_SRC = """
; while Link shows a thrust pose and a beam flies, draw the blade in his hand too (Zelda II's thrust
; frame is 32 px wide; SMB's player is 16), using the spare sprite of Mario's old 4-sprite fireball burst
HoldBlade:
          lda $06D5
          and #$7F            ; $58 standing thrust, $D8 crouching thrust
          cmp #$58
          bne HB_Done
          ldy $06EC,x
          jmp DB_Stab
HB_Done:  rts
"""


def assemble_code():
    syms = {"SAMPLE_REG": (SAMPLE_ADDR - 0xC000) // 64, "SAMPLE_END": SAMPLE_ADDR + len(HURT_SAMPLE), "BEAM_TILE": BEAM_SLOT,
            "KNOCK_VY": 0xFD, "SMALL_YOFS": 14, "MELEE_FRAMES": 5, "SPARK1": SPARK_SLOTS[0], "SPARK2": SPARK_SLOTS[1],
            "KNOCK_GRAV": 0x60, "BEAM_YOFS": 8, "BEAM_YCROUCH": 10, "BEAM_XR": 10, "BEAM_XL": 0xFE}
    if not PREVIOUS:                       # the beam leaves from the tip of the held blade
        syms.update(BEAM_XR=20, BEAM_XL=0xF4, ZELDA_SKIN=items.ZELDA_SKIN_AT)
    src = SRC
    if not PREVIOUS:
        marker = "          asl\n          jsr SetChr0\n"
        assert src.count(marker) == 1
        src = src.replace(marker, marker + TITLE_BANK_SRC)
        marker = "          ora $00\n          sta $0202,y\n          rts\n"
        assert src.count(marker) == 1
        src = src.replace(marker, "          ora $00\n          sta $0202,y\n          jmp HoldBlade\n")
        src += HOLD_BLADE_SRC
        src += DEATH_COL_SRC                # overflow block, after the sample
    block_ee17 = BLOCK_EE17 if PREVIOUS else BLOCK_EE17 + items.JAR_ATTR_SRC + items.ZELDA_FAR_SRC
    death_tables = "DeathBase: .db " + ",".join("$%02X" % v for v in DEATH_BASE) + "\n"
    death_tables += "DeathPerLo: .db " + ",".join("$%02X" % (p & 0xFF) for p in DEATH_PERIODS) + "\n"
    death_tables += "DeathPerHi: .db " + ",".join("$%02X" % (p >> 8) for p in DEATH_PERIODS) + "\n"
    bank2_code = b""
    if not PREVIOUS:
        # Room for the hammer upgrade: the sword and death sound players only ever run from SoundWrap,
        # while bank 2 is mapped, so they move there (with the Hammer Bro check and hammer drawing).
        src, death_snd = cut(src, "; ---- per-frame player of the Zelda II death tone", "; ---- sword beam (SMB fireball)")
        block_ee17, sword_snd = cut(block_ee17, "; per-frame player of the sword sound", "; sword thrust frame")
        ram = "".join(l + "\n" for l in SRC.splitlines() if re.match(r"^\w+ = \$", l))
        bank2_code, s2 = assemble(ram + death_snd + death_tables + sword_snd + HAMMER_BANK2_SRC, BANK2_CODE_AT)
        syms.update(DeathSound=s2["DeathSound"], SwordSound=s2["SwordSound"], HAM_CHECK=s2["HamCheck"],
                    DRAW_HAM=s2["DrawHam"], HAM_VX=0x18, HAM_VY=0xFC, HAM_GRAV=0x40)
        death_tables = ""
        # small/big Link and the hammer: the swish only; the red tunic's beam: swish and beam tone
        src_ss = ("          lda PlayerStatus    ; small/big Link: the swish only (no beam, no beam tone)\n"
                  "          cmp #2\n          lda #0\n          bcs SWS_Set\n")
        assert block_ee17.count(src_ss) == 1
        block_ee17 = block_ee17.replace(src_ss, "          ldy PlayerStatus    ; the red tunic's beam: swish and beam tone\n"
                                        "          lda #0\n          cpy #2\n          beq SWS_Set\n")
        block_ee17 += HAMMER_EE17_SRC
        for old, new in [("DB_Beam:  lda $09",                 # blue Link's beam is a hammer
                          "DB_Beam:  lda PlayerStatus\n          cmp #3\n          bne DB_Flick\n"
                          "          jmp DrawHamFar\nDB_Flick: lda $09"),
                         ("LH_Done:  lda #1\n          sta PlayerSize      ; now small Link\n",
                          "LH_Done:  lda PlayerStatus    ; hit while blue, back to big or red: stays big\n          bne LH_Keep\n"
                          "          lda #1\n          sta PlayerSize      ; now small Link\nLH_Keep:\n"),
                         # dying in mid-air: fall with real collision until landing, then the flash
                         ("          bcs LD_Flash\n          lda #8\n", "          bcs LD_Flash\nLD_Knock: lda #8\n"),
                         ("LD_Flash: bne LD_Go\n", "LD_Flash: bne LD_Go\n          jsr DeathAir\n          bcs LD_Knock\n"),
                         (DEATH_HOP_SRC, "          jmp ClampLeft\n")]:
            assert src.count(old) == 1, old
            src = src.replace(old, new)
    tables = ""
    tables += "PlayerColors: .db " + ",".join("$%02X" % c for c in (COLORS if PREVIOUS else COLORS_HAMMER)) + "\n"
    tables += death_tables
    tables += "DeathHop: .db " + ",".join(str(v) for v in DEATH_HOP) + "\n"
    tables += "GfxTable: .db " + ",".join("$%02X" % v for v in GFX_TABLE) + "\n"
    if not PREVIOUS:
        tables += coins.table_src(smb[16:16 + 0x4000])                 # palette-0 blocks + rupee blocks
        tables += HAMMER_MAIN_SRC
        tables += "PupAttr: .db $01,$02,$02,$02,$03\n"   # sword, jar, star, heart (as patched in items.py), hammer
    # tables go before the .org so the main block stays below the sample
    src = src.replace("          .org SAMPLE_END", tables + "          .org SAMPLE_END")
    src = block_ee17 + "          .org $EF0D\n" + BLOCK_EF0D + "          .org $F0EA\n" + BLOCK_F0EA + "          .org $F90D\n" + src
    code, s = assemble(src, CODE_ORG, syms)
    assert CODE_ORG + len(code) <= 0xFF00, "new code too large: ends at %04X" % (CODE_ORG + len(code))
    for lo, hi in GAPS:                         # SMB code / the sample between the free areas
        assert not any(code[lo - CODE_ORG:hi - CODE_ORG]), "code spills into %04X-%04X" % (lo, hi - 1)
    return code, s, bank2_code


def cut(src, start, end):
    """Remove the text from marker 'start' up to (not including) marker 'end'; return (rest, removed)."""
    a, b = src.index(start), src.index(end)
    assert a < b
    return src[:a] + src[b:], src[a:b]


BANK2_CODE_AT = 0xC640          # bank 2, after Zelda's skin routine ($C600)
CODE, SYM, BANK2_CODE = assemble_code()

# ------------------------------------------------------------------ patches to SMB's code
J = lambda a: bytes([0x20]) + w16(a)            # JSR
NOP = b"\xEA"

# bank 0 ($8000-$BFFF)
patch(0x80E4, J(SYM["SoundWrap"]), expect=J(0xF2D0))
if PREVIOUS:
    patch(0x85F4, bytes.fromhex("AD5307" "0A0A" "AC5607" "C002" "D002" "0908" "A8") + NOP * 3,
          expect=bytes.fromhex("A000AD5307F002A004AD5607C902D002A008"))   # Y = player*4 (+8 if fiery)
else:
    patch(0x85F4, bytes.fromhex("AD5607" "0A" "0D5307" "0A0A" "A8") + NOP * 8,
          expect=bytes.fromhex("A000AD5307F002A004AD5607C902D002A008"))   # Y = (status*2 + player)*4
patch(0x860A, b"\xB9" + w16(SYM["PlayerColors"]), expect=bytes.fromhex("B9D785"))
patch(0x89E1, J(SYM["ColorRotCheck"]) + NOP, expect=bytes.fromhex("A5092907"))   # no ?-block colour cycling during death
patch(0xB065, w16(SYM["LinkDeath"]), expect=w16(0xB269))                # engine routine $0B
patch(0xB063, w16(SYM["LinkHurt"]), expect=w16(0xB245))                 # engine routine $0A (hit while big)
patch(0xB624, NOP * 7, expect=bytes.fromhex("AD5607C9029043"))         # sword in every form, not just red
patch(0xB644, NOP * 5, expect=bytes.fromhex("AD1407D01B"))             # allow the sword while crouching
patch(0xB64F, J(SYM["SwordStart"]) + NOP, expect=bytes.fromhex("A92085FF"))   # Zelda II sword sound
patch(0xB687, bytes.fromhex("20E0"), expect=bytes.fromhex("40C0"))       # beam speed: 2 px/frame like Zelda II
patch(0xB1A0, J(SYM["PitDeath"]) + NOP * 3, expect=bytes.fromhex("C884FC8C1207"))
patch(0xB51A, NOP * 2, expect=bytes.fromhex("85FF"))                    # no jump sound
patch(0xB697, J(SYM["BeamInit"]) + NOP * 13, expect=bytes.fromhex("A5866904958DA56D69009574A5CE95D5"))
patch(0xB6B3, b"\xA9\x00", expect=b"\xA9\x04")                          # beam: no vertical speed
patch(0xB6C3, b"\xA9\x00", expect=b"\xA9\x50")                          # beam: no gravity
patch(0xB6EB, b"\x4C" + w16(SYM["DrawBeam"]), expect=b"\x4C" + w16(0xECDE))
patch(0xB6F6, b"\x4C" + w16(SYM["BeamHit"]), expect=b"\x4C" + w16(0xED09))   # beam hit: Zelda II sparkle


# text: MARIO -> LINK, LUIGI -> DARK
def txt(s):
    return bytes(0x24 if c == " " else (int(c) if c.isdigit() else 0x2B if c == "!" else ord(c) - 55) for c in s)
for a in (0x8755, 0x879B, 0x87AE):
    patch(a, txt("LINK "), expect=txt("MARIO"))
patch(0x87ED, txt("DARK "), expect=txt("LUIGI"))
patch(0x8D61, txt("LINK! "), expect=txt("MARIO!"))
patch(0x8D75, txt("DARK! " if PREVIOUS else "LINK! "), expect=txt("LUIGI!"))   # Toad thanks player 2 too

# bank 1 ($C000-$FFFF)
patch(0xD93E, J(SYM["HurtStart"]), expect=bytes.fromhex("0A85FF"))     # hit: grunt + knockback
patch(0xD95A, J(SYM["HurtStart"]), expect=bytes.fromhex("E886FC"))     # killed: grunt + knockback
patch(0xD95D, NOP * 4, expect=bytes.fromhex("A9FC859F"))               # keep the knockback hop set by HurtStart
patch(0xE1D8, b"\x4C" + w16(0xE1F4) + NOP, expect=bytes.fromhex("B5A63018"))   # beam explodes on any wall/floor
patch(0xE1F8, NOP * 4, expect=bytes.fromhex("A90285FF"))               # no bump sound when the beam hits a wall
patch(0xEEF3, J(SYM["IsHurt"]) + NOP, expect=bytes.fromhex("A50EC90B"))   # hurt pose while knocked back
patch(0xEF0C, b"\x60", expect=b"\xA5")                                  # no swim-kick tile swapping
patch(0xEF40, J(SYM["DeathGfx"]) + NOP * 2, expect=bytes.fromhex("A00EB907EE"))
patch(0xEF65, J(SYM["ThrowGfx"]) + NOP * 2, expect=bytes.fromhex("A007B907EE"))   # standing/crouching/small thrust
if not PREVIOUS:
    patch(0xEF75, NOP, expect=b"\x88")                                  # attack pose: always draw all 4 rows
patch(0xEFB5, b"\x60", expect=b"\xAD")                                  # no mirrored feet on lives screen
patch(0xEFDC, b"\xBD" + w16(SYM["GfxTable"]), expect=bytes.fromhex("BD17EE"))
patch(0xEFE1, b"\xBD" + w16(SYM["GfxTable"] + 1), expect=bytes.fromhex("BD18EE"))
patch(0xEFFF, b"\x4C" + w16(SYM["JumpFrame"]), expect=bytes.fromhex("A006AD14"))   # jumping
patch(0xF034, b"\x4C" + w16(SYM["JumpFrame"]), expect=bytes.fromhex("A00420"))     # falling
patch(0xF00B, J(SYM["GroundHook"]) + NOP * 2, expect=bytes.fromhex("A006AD1407"))   # landing crouch
patch(0xF0E9, b"\x60", expect=b"\xAC")                                  # no forced mirroring of frames
patch(0xF0DC, b"\xA0\x0F", expect=b"\xA0\x09")                          # shrinking: small stand...
patch(0xF0E3, b"\xA0\x02", expect=b"\xA0\x01")                          # ...and big stand frames
patch(0xF2DE, J(SYM["ApuEnF"]) + NOP * 2, expect=bytes.fromhex("A90F8D1540"))
patch(0xF730, J(SYM["ApuEnB"]) + J(SYM["ApuEnF"]) + NOP * 4, expect=bytes.fromhex("A90B8D1540A90F8D1540"))
patch(0xFFFC, w16(SYM["ResetStub"]), expect=w16(0x8000))
if not PREVIOUS:
    items.apply(patch, ITEM_SLOTS, SYM)                                 # Master Sword and Magic Jar power-ups
    coins.patch_code(patch, SYM["Pal0Blocks"], SYM)                     # coins -> green rupees
    coins.patch_dpad(patch)                                             # Down+direction like Zelda II
    patch(0xC8D4, w16(SYM["ZeldaFar"]), expect=w16(0xC8D7))            # princess routine: skin colour
    # hammer upgrade
    patch(0xAEFE, J(SYM["HamFar"]), expect=J(0xB624))     # every frame of play: Hammer Bro drops
    patch(0xBC9B, b"\xB0", expect=b"\xF0")             # power-up type 4 (hammer) moves like a mushroom...
    patch(0xE70E, b"\xB0", expect=b"\xF0")             # ...and is drawn like one (no flashing or mirroring)
    patch(0xE6E5, w16(SYM["PupAttr"]), expect=w16(0xE6CE))                  # power-up palettes: moved...
    patch(0xE6CE, bytes(ITEM_SLOTS["hammer"]), expect=bytes([1, 2, 2, 2]))  # ...so the tile table has room
    patch(0xD812, b"\x4C" + w16(SYM["PupMore"]) + NOP, expect=bytes.fromhex("C903F024"))   # grabbing it
    patch(0xD936, J(SYM["HurtStatus"]), expect=bytes.fromhex("8D5607"))     # hit while blue: red tunic
    patch(0xB6B3, J(SYM["HamInit"]) + NOP, expect=bytes.fromhex("A90095A6"))   # thrown hammer: arc...
    patch(0xB6C3, J(SYM["HamGrav"]) + NOP, expect=bytes.fromhex("A9008500"))
    patch(0xB6DE, J(SYM["HamBG"]), expect=J(0xE1C8))                       # ...through walls
    patch(0xDC69, J(SYM["DeathCol"]) + NOP, expect=bytes.fromhex("A50EC90B"))   # dying: floor collision...
    patch(0xB3B9, J(SYM["DeathCol"]) + NOP, expect=bytes.fromhex("A50EC90B"))   # ...and normal gravity

# new code + sample into the free areas
MUSIC = bytes(HI[0xF90C - 0xC000:0xFF00 - 0xC000])       # $F90C (RTS) .. $FEFF
for lo, hi in FREE:
    HI[lo - 0xC000:hi - 0xC000] = CODE[lo - CODE_ORG:hi - CODE_ORG].ljust(hi - lo, b"\x00")
HI[SAMPLE_ADDR - 0xC000:SAMPLE_ADDR - 0xC000 + len(HURT_SAMPLE)] = HURT_SAMPLE
BANK1 = bytes(HI)

# bank 2: same, plus the music data at $C000 and the sound engine pointed at it
MUS_NEW = 0xC000
D = MUS_NEW - 0xF90C
bank2 = bytearray(BANK1)
bank2[0:len(MUSIC)] = MUSIC
for site in (0xF6F5, 0xF6F9, 0xF6FE, 0xF703, 0xF708, 0xF70D, 0xF712):
    o = site - 0xC000
    assert bank2[o] == 0xB9
    old = bank2[o + 1] | bank2[o + 2] << 8
    bank2[o + 1:o + 3] = w16(old + D)
offsets = set(MUSIC[1:0x32])                   # header offset table ($F90D..$F93D)
for off in offsets:
    p = (0xF90E + off) - 0xF90C + 0             # pointer lo position within MUSIC
    ptr = MUSIC[p] | MUSIC[p + 1] << 8
    assert 0xF90D <= ptr < 0xFF00, "header pointer out of range: %04X" % ptr
    bank2[p:p + 2] = w16(ptr + D)
if not PREVIOUS:                                   # Zelda's skin-colour routine lives only in bank 2
    _zs, _ = assemble(items.ZELDA_SKIN_SRC, items.ZELDA_SKIN_AT)
    _o = items.ZELDA_SKIN_AT - 0xC000
    assert _o >= len(MUSIC) and _o + len(_zs) <= 0xF2D0 - 0xC000
    bank2[_o:_o + len(_zs)] = _zs
    assert items.ZELDA_SKIN_AT + len(_zs) <= BANK2_CODE_AT
    _o = BANK2_CODE_AT - 0xC000                    # sound players, Hammer Bro check, hammer drawing
    assert _o + len(BANK2_CODE) <= 0xEE17 - 0xC000
    bank2[_o:_o + len(BANK2_CODE)] = BANK2_CODE

# make sure the sound engine never jumps into code that bank 2 overwrote
lines = dis(BANK1, 0xF2D0 - 0xC000, 0xF2D0, 900).splitlines()
for ln in lines:
    addr = int(ln[:4], 16)
    if addr >= 0xF90C: break
    if " JSR $" in ln or " JMP $" in ln:
        tgt = int(ln.split("$")[1][:4], 16)
        assert not (MUS_NEW <= tgt < MUS_NEW + len(MUSIC)), "sound engine calls %04X" % tgt

PRG = bytes(LO) + BANK1 + bytes(bank2) + BANK1
if PREVIOUS:
    BG, BG_TITLE, LOGO_TILES, LOGO_BYTES = CHR[0x1000:], CHR[0x1000:], 0, 0
else:
    BG, BG_TITLE, LOGO_TILES, LOGO_BYTES = titlelogo.build(CHR[0x1000:])   # title: LINK instead of SUPER MARIO BROS.
    BG, BG_TITLE = coins.apply_bg(BG), coins.apply_title_bg(BG_TITLE)
    SPR = {k: items.apply_spr(coins.apply_spr(v)) for k, v in SPR.items()}
CHRROM = SPR["big"] + BG + SPR["small"] + BG_TITLE
header = bytes([0x4E, 0x45, 0x53, 0x1A, 4, 2, 0x10, 0x00]) + bytes(8)
rom = header + PRG + CHRROM


def make_ips(old, new):
    out = bytearray(b"PATCH")
    i, n = 0, len(new)
    while i < n:
        if i < len(old) and old[i] == new[i]:
            i += 1; continue
        j = i
        while j < n and j - i < 0xFFFF and not (j < len(old) and old[j] == new[j] and
                                                 all(k >= n or (k < len(old) and old[k] == new[k]) for k in range(j, j + 6))):
            j += 1
        if i == 0x454F46:                       # the "EOF" offset can't be used
            i -= 1
        out += bytes([i >> 16, (i >> 8) & 0xFF, i & 0xFF, (j - i) >> 8, (j - i) & 0xFF]) + new[i:j]
        i = j
    return bytes(out + b"EOF")


def apply_ips(old, ips):
    data = bytearray(old); p = 5
    while ips[p:p + 3] != b"EOF":
        off = int.from_bytes(ips[p:p + 3], "big"); size = int.from_bytes(ips[p + 3:p + 5], "big"); p += 5
        if size == 0:
            size = int.from_bytes(ips[p:p + 2], "big"); val = ips[p + 2]; p += 3; chunk = bytes([val]) * size
        else:
            chunk = ips[p:p + size]; p += size
        if len(data) < off + size: data += bytes(off + size - len(data))
        data[off:off + size] = chunk
    return bytes(data)


if __name__ == "__main__":
    os.makedirs(OUT_DIR, exist_ok=True)
    open(OUT, "wb").write(rom)
    ips = make_ips(smb, rom)
    assert apply_ips(smb, ips) == rom
    open(IPS, "wb").write(ips)
    print("wrote %s (%d bytes)" % (OUT, len(rom)))
    print("wrote %s (%d bytes)" % (IPS, len(ips)))
    if not PREVIOUS and os.path.exists(NEON64):       # N64 copy (Neon64 emulator + this ROM, 2 MB)
        neon = open(NEON64, "rb").read() + rom
        open(N64_OUT, "wb").write(neon + bytes(2 * 1024 * 1024 - len(neon)))
        print("wrote %s" % N64_OUT)
    for lo, hi in FREE:
        chunk = CODE[lo - CODE_ORG:hi - CODE_ORG]
        last = max([n for n, v in enumerate(chunk) if v] or [-1])
        print("code area $%04X-$%04X: %3d of %3d bytes used" % (lo, hi - 1, last + 1, hi - lo))
    print("hurt sample at $%04X, beam tile $%02X" % (SAMPLE_ADDR, BEAM_SLOT))
    print("sprite tiles used: big bank %d, small bank %d of %d" % (TILES_USED["big"], TILES_USED["small"], len(PLAYER_SLOTS)))
    if not PREVIOUS:
        print("title logo: %d tiles, %d layout bytes" % (LOGO_TILES, LOGO_BYTES))
