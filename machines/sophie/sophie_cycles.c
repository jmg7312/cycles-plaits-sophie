/* SPDX-License-Identifier: MIT */
/*
 * sophie_cycles.c - Sophie's four models as Model:Cycles machines (OS 1.13).
 *
 * This file is only the adapter between the Model:Cycles voice loop and the synthesis code. The synthesis
 * is third_party/digisophie/sophie.c: Sophie for Digitakt by soejrd (MIT), a fixed-point adaptation of
 * Sophie for Schwung by Matt Estela (MIT). That code is used unmodified.
 *
 * Same machine contract as machines/plaits/plaits_cycles.c: update(pmod, v, p), then render(out, v).
 *
 * One machine per model: FUSE, BOOM, PIPE, SHARD (the model does not take a knob).
 * Knobs:
 *   COLOR   = COLOR
 *   SHAPE   = METAL
 *   SWEEP   = SWEEP      bipolar, 64 = centre
 *   CONTOUR = FBK        oscillator feedback
 *   PITCH, FINE TUNE, DECAY, PUNCH and GATE keep their stock meaning (stock amp envelope, VCA and punch
 *   stage, set up as the stock TONE machine does).
 * Not mapped yet: FOLD (Sophie's wavefolder) is off, and velocity is fixed at 127. The plan for FOLD is a
 * second layer on the SHAPE knob (hold the PRESET MENU key and turn SHAPE), the way Model-TG adds Attack
 * on the DECAY knob.
 *
 * Status: runs in emulation (Modded-Cycles' tools/emu/mcengine.py). NOT tested on hardware.
 */
#include "sophie.h"

typedef int int32;
typedef unsigned int uint32;
typedef short int16;
typedef unsigned char uint8;

uint32_t mono_pitch_inc(int32_t pitch);         /* digi1_mods mono.c: pitch (semitones, Q7) -> 32-bit phase step */

#define VOICE0   0x42308828u
#define VSTRIDE  0x31c
#define NVOICES  6

#define OS_AMP_ENV   ((void (*)(void *))0x400a9252)
#define OS_AMP_VCA   ((void (*)(int32 *, void *))0x400a9430)
#define OS_PUNCH     ((void (*)(int32 *, void *))0x400a967a)
#define OS_DECAY_TAB ((const int32 *)0x4011d84c)

#define V32(v, off) (*(int32 *)((char *)(v) + (off)))
#define P16(p, off) (*(const int16 *)((const char *)(p) + (off)))

struct track {
    struct ds_voice dv;
    struct ds_params prm;
    int32 trig;
    int32 init;
};

static struct track tracks[NVOICES];

static int32 clamp7(int32 x)
{
    return x < 0 ? 0 : x > 127 ? 127 : x;
}

static void update(int32 pmod, void *v, const void *p, int32 model)
{
    uint32 t = ((uint32)v - VOICE0) / VSTRIDE;
    struct track *d;
    int32 semis, inc;

    if (t >= NVOICES)
        return;
    d = &tracks[t];
    if (!d->init) {
        ds_voice_init(&d->dv);
        d->init = 1;
    }

    semis = pmod + ((int32)P16(p, 0x14) << 8) - (64 << 16) + (((int32)P16(p, 0x22) - 16384) << 3);
    if (semis < 0)
        semis = 0;
    else if (semis > (127 << 16))
        semis = 127 << 16;
    inc = (int32)(mono_pitch_inc(semis >> 9) >> 16);     /* Sophie: a 16-bit phase step per sample */
    d->prm.phase_inc = (uint16_t)(inc < 8 ? 8 : inc > 65535 ? 65535 : inc);
    d->prm.model = (uint8)model;
    d->prm.color = (uint8)clamp7(P16(p, 0x16) >> 8);
    d->prm.metal = (uint8)clamp7(P16(p, 0x18) >> 8);
    d->prm.sweep = (int8_t)(clamp7(P16(p, 0x1a) >> 8) - 64);
    d->prm.feedback = (uint8)clamp7(P16(p, 0x1c) >> 8);
    d->prm.velocity = 127;
    d->prm.fold = 0;

    /* The stock amp envelope, set up as the stock TONE machine does (0x400aa7b8). */
    V32(v, 592) = OS_DECAY_TAB[clamp7(P16(p, 0x24) >> 8)];
    d->trig = 0;
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
        d->trig = 1;
    }
}

void sophie_update_fuse(int32 pmod, void *v, const void *p)  { update(pmod, v, p, 0); }
void sophie_update_boom(int32 pmod, void *v, const void *p)  { update(pmod, v, p, 1); }
void sophie_update_pipe(int32 pmod, void *v, const void *p)  { update(pmod, v, p, 2); }
void sophie_update_shard(int32 pmod, void *v, const void *p) { update(pmod, v, p, 3); }

void sophie_render(int32 *out, void *v)
{
    uint32 t = ((uint32)v - VOICE0) / VSTRIDE;
    struct track *d;
    int32 i;

    if (t >= NVOICES || !tracks[t].init) {
        for (i = 0; i < 32; i++)
            out[i] = 0;
        return;
    }
    d = &tracks[t];
    /* Sophie goes to sleep once the level has died away: give it the stock amp envelope's level. */
    ds_voice_gate(&d->dv, V32(v, 560), 0);
    ds_voice_render(&d->dv, &d->prm, d->trig, out, 32);
    ds_fold_block(out, 32, d->prm.fold);

    /* Output level: twice Sophie's own, clipped. Measured in emulation at default knobs: peaks
     * 0.055-0.068 of full scale after the stock amp chain (stock machines: 0.076-0.212). */
    for (i = 0; i < 32; i++) {
        int32 x = out[i];
        if (x > 0x3fffffff)
            x = 0x3fffffff;
        else if (x < -0x3fffffff)
            x = -0x3fffffff;
        out[i] = x << 1;
    }

    OS_AMP_ENV(v);
    OS_AMP_VCA(out, v);
    OS_PUNCH(out, v);
}
