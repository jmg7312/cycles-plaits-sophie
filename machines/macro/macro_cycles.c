/* SPDX-License-Identifier: MIT */
/*
 * macro_cycles.c - the Plaits machine of the Model:Cycles (OS 1.13): digi1_mods' MACRO engines.
 *
 * This file is only the adapter between the Model:Cycles voice loop and the synthesis code. The synthesis
 * is not here: it is third_party/digi1_mods/macro.c, digi1_mods' MACRO machine for the Digitakt mk1 (MIT):
 * engines ported to fixed point from Plaits by Emilie Gillet (MIT). That code is used unmodified, and the
 * engines keep the names digi1_mods gave them.
 *
 * Machine contract of the Model:Cycles (OS 1.13), as documented in Modded-Cycles (notes/14) and checked
 * against the stock machines:
 *   update(pmod, v, p) : once per 32-sample block, before render.
 *                        pmod = the trig's note (semitones << 16), v = voice state (0x31c bytes),
 *                        p = the track's parameters, 8.8 words:
 *                        +0x14 PITCH, +0x16 COLOR, +0x18 SHAPE, +0x1a SWEEP, +0x1c CONTOUR,
 *                        +0x1e PUNCH, +0x22 FINE TUNE, +0x24 DECAY.
 *   render(out, v)     : writes 32 samples (int32, Q31) to out.
 *   v + 0x38 != 0      : the block where a note starts.
 *
 * One machine, eight engines, as on the Digitakt (digi1_mods' MACRO): the first sound knob picks the engine,
 * so a parameter lock on it changes the engine per step. The OS allows few added machines (see
 * docs/MODEL-CYCLES-NOTES.md, section 5), so a family of engines shares one machine.
 *   WSHAPE, 2OP FM, NOISE, PARTCL, BDRUM, SNARE, HIHAT, GRAIN.
 * Knobs:
 *   COLOR   = ENGN       the engine, in zones of 8 values (0-7 WSHAPE, 8-15 2OP FM, ...), as digi1_mods'
 *                        knob B; read at each note start
 *   SHAPE   = HARMONICS
 *   SWEEP   = TIMBRE
 *   CONTOUR = MORPH
 *   PITCH, FINE TUNE, DECAY, PUNCH and GATE keep their stock meaning: the amp envelope, its VCA and the
 *   punch stage are the stock OS blocks, set up the way the stock TONE machine sets them up.
 *
 * Status: runs in emulation (Modded-Cycles' tools/emu/mcengine.py). NOT tested on hardware.
 */
#include "macro.h"

typedef int int32;
typedef unsigned int uint32;
typedef short int16;
typedef unsigned char uint8;

uint32_t mono_pitch_inc(int32_t pitch);         /* digi1_mods mono.c: pitch (semitones, Q7) -> phase step */

#define VOICE0   0x42308828u                    /* first voice; a voice is 0x31c bytes */
#define VSTRIDE  0x31c
#define NVOICES  6

/* stock OS blocks (OS 1.13) */
#define OS_AMP_ENV   ((void (*)(void *))0x400a9252)             /* amp envelope                 */
#define OS_AMP_VCA   ((void (*)(int32 *, void *))0x400a9430)    /* its VCA                      */
#define OS_PUNCH     ((void (*)(int32 *, void *))0x400a967a)    /* punch stage                  */
#define OS_DECAY_TAB ((const int32 *)0x4011d84c)                /* DECAY knob curve (TONE's)    */

#define V32(v, off) (*(int32 *)((char *)(v) + (off)))
#define P16(p, off) (*(const int16 *)((const char *)(p) + (off)))

struct track {
    struct macro_voice mv;
    uint8 prm[MACRO_PARAMS];
    uint32 inc;
    int32 init;
};

static struct track tracks[NVOICES];

/* macro_render() runs on a stack of our own (private_stack.S says why). 4 096 bytes; it uses up to about
 * 1 700. One for all voices: they are rendered one after the other. */
#define STACK_BYTES 4096
static uint32 macro_stack[STACK_BYTES / 4];
void macro_on_private_stack(void *stack_top, void *fn, void *a, void *b, uint32 c, void *d, int32 e);

/* Output level. macro_render() gives 16-bit samples; the OS works in 32 bits. With a shift of 16, its
 * full scale is the OS's full scale, so nothing can overflow. Measured in emulation at default knobs:
 * peaks 0.044-0.125 of full scale after the stock amp chain (stock machines: 0.076-0.212). */
#define OUT_SHIFT 16

static int32 clamp7(int32 x)
{
    return x < 0 ? 0 : x > 127 ? 127 : x;
}

void macro_cycles_update(int32 pmod, void *v, const void *p)
{
    uint32 t = ((uint32)v - VOICE0) / VSTRIDE;
    struct track *d;
    int32 semis;

    if (t >= NVOICES)
        return;
    d = &tracks[t];
    if (!d->init) {
        macro_init(&d->mv);
        d->mv.rng ^= (t + 1) * 0x9e3779b9u;
        d->init = 1;
    }

    d->prm[MACRO_P_ENGINE] = (uint8)clamp7(P16(p, 0x16) >> 8);
    d->prm[MACRO_P_HARM]   = (uint8)clamp7(P16(p, 0x18) >> 8);
    d->prm[MACRO_P_TIMB]   = (uint8)clamp7(P16(p, 0x1a) >> 8);
    d->prm[MACRO_P_MORPH]  = (uint8)clamp7(P16(p, 0x1c) >> 8);
    d->prm[MACRO_P_AUX]    = 0;                 /* the engine's OUT; its AUX output is not mapped yet */

    /* Pitch, as the stock pitch code (0x400a7e6c) computes it: the trig's note + PITCH (8.8, 64 = centre,
     * semitones) + FINE TUNE (8.8, 64 = centre). Q16 semitones. */
    semis = pmod + ((int32)P16(p, 0x14) << 8) - (64 << 16) + (((int32)P16(p, 0x22) - 16384) << 3);
    if (semis < 0)
        semis = 0;
    else if (semis > (127 << 16))
        semis = 127 << 16;
    d->inc = mono_pitch_inc(semis >> 9);

    /* The stock amp envelope, set up as the stock TONE machine does (0x400aa7b8). */
    V32(v, 592) = OS_DECAY_TAB[clamp7(P16(p, 0x24) >> 8)];
    if (V32(v, 0x38) != 0) {
        int32 i, *z;
        V32(v, 40) = 0;
        V32(v, 628) = 19664678;
        V32(v, 632) = 19664678;
        V32(v, 636) = -2108154293;
        V32(v, 640) = 2063452;
        V32(v, 644) = 2063452;
        V32(v, 648) = -2143356744;
        V32(v, 656) = 2147483647;
        V32(v, 660) = 2147483647;
        if (P16(p, 0x1e) != 0) {                /* PUNCH on */
            V32(v, 668) = 536870912;
            V32(v, 676) = 536870912;
            V32(v, 672) = 1610612736;
            V32(v, 72) = 1;
        } else {
            V32(v, 668) = 2147483647;
            V32(v, 672) = 536870912;
            V32(v, 676) = 536870912;
            V32(v, 72) = 0;
        }
        z = (int32 *)V32(v, 792);
        for (i = 0; i < 12; i++)
            z[i] = 0;
        macro_trig(&d->mv);
    }
}

void macro_cycles_render(int32 *out, void *v)
{
    uint32 t = ((uint32)v - VOICE0) / VSTRIDE;
    int16 buf[32];
    int32 i;

    if (t >= NVOICES || !tracks[t].init) {
        for (i = 0; i < 32; i++)
            out[i] = 0;
        return;
    }
    macro_on_private_stack(macro_stack + STACK_BYTES / 4, macro_render,
                           &tracks[t].mv, tracks[t].prm, tracks[t].inc, buf, 32);
    for (i = 0; i < 32; i++)
        out[i] = (int32)buf[i] << OUT_SHIFT;

    OS_AMP_ENV(v);
    OS_AMP_VCA(out, v);
    OS_PUNCH(out, v);
}
