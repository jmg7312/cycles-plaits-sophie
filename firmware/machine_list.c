/* SPDX-License-Identifier: MIT */
/*
 * machine_list.c - Plaits and Sophie in the Model:Cycles machine list (OS 1.13): the C part.
 *
 * The stock OS has six machines, and several of its tables and functions stop at six. This file holds the
 * tables that had to grow and the functions that replace four small OS accessors. hooks.S holds their
 * entry points and the three detours placed in the middle of OS functions; tools/make_firmware.py fills
 * the tables marked "filled by the tool" and writes the patches into the OS image.
 *
 * Method and addresses: Modded-Cycles' notes 18 to 20 (github.com/18nelli18/Modded-Cycles), which add
 * Syntakt engines to the list the same way and were tested on hardware. This implementation is our own.
 * NOT tested on hardware.
 */
#include "machine_list.h"

typedef unsigned int u32;
typedef int s32;
typedef unsigned char u8;
typedef signed char s8;

/* ---- tables filled by tools/make_firmware.py (from the user's own OS file, plus our entries) ---------- */
#define TABLE __attribute__((section(".tables"), used))

TABLE u8  ml_desc[ML_DESCS * ML_DESC_SIZE];     /* the OS's 76 parameter descriptors, then ours (5 a machine) */
TABLE u32 ml_names[ML_MACHINES];                /* machine names, MACHINES screen                              */
TABLE u32 ml_update[ML_MACHINES];               /* voice loop: update functions                                */
TABLE u32 ml_render[ML_MACHINES];               /* voice loop: render functions                                */
TABLE char ml_strings[ML_STRINGS];              /* our names: machines, knobs (long and short)                 */

/* ---- tables the OS builds at boot (0x4005a274), one row of 8 per machine; zero until then ------------- */
/* machine, knob slot -> descriptor. The rows start one row into the area: the OS reads a machine's Amp Decay
 * from row "machine" without checking the machine, and it could be asked for machine -1 (no sound) or for a
 * machine saved by another firmware. One empty row before and eight after make those read 0, the "Error"
 * descriptor, as the OS's own bound checks answer. */
u32 ml_rows_area[(1 + ML_MACHINES + 8) * 8] __attribute__((aligned(4)));
u32 ml_ccrows[ML_MACHINES * 8] __attribute__((aligned(4)));       /* machine, CC 16..23 -> descriptor */

/* ---- constant tables ---------------------------------------------------------------------------------- */
/* Machine -> per-machine record number, for the main screen's knobs. The OS's own vector stops at 6. */
const u32 ml_vec[ML_MACHINES] = { 1, 2, 3, 4, 5, 6, 7, 8 };
/* Machine -> picture shown on the MACHINES screen. The OS has six pictures; ours show CHORD's, which is
 * also what the OS's other screens show for any machine above CHORD. */
const u8 ml_icon[ML_MACHINES] = { 0, 1, 2, 3, 4, 5, 5, 5 };
/* Our descriptors -> the machine they belong to (-1: the Amp Decay, common to all machines as in the OS).
 * A descriptor's own "machine" field cannot say 7: there 7 means "every machine". Ours carry 6 and this
 * table tells them apart. */
const s8 ml_owner[ML_ADDED * ML_DESC_EACH] = { 6, 6, 6, 6, -1, 7, 7, 7, 7, -1 };

/* ---- the OS (1.13) ------------------------------------------------------------------------------------ */
struct record {                                 /* per-machine record, 76 bytes */
    void *str[2];                               /* two C++ strings (copy on write) */
    s32 id[17];                                 /* the descriptors of the machine's parameter page */
};
#define OS_RECORDS      ((struct record *)0x40a71540)   /* 7 records: 0 = none, 1..6 = machines 0..5 */
#define OS_REC_INDEX    ((const s8 *)0x401091b4)        /* machine 0..5 -> record number             */
#define OS_STRING_COPY  ((void (*)(void *, const void *))0x400f8f02)
#define OS_STATE        0x40a71754u                     /* per-descriptor state objects, 100 bytes   */
#define OS_STATE_OWNER  0x40a71500u
#define OS_CONNECT      ((void (*)(u32, u32, u32))0x400ddf60)
#define SNARE_RECORD    2
#define SNARE_DESC      51                              /* SNARE's COLOR, SHAPE, SWEEP, CONTOUR, Amp Decay */

static struct record ml_rec[ML_ADDED];
static u8 ml_rec_built[ML_ADDED];

/* A record for one of our machines: SNARE's, with SNARE's five descriptors replaced by ours. Built on first
 * use: the OS builds its own records after the boot hook has run. */
static struct record *added_record(u32 k)
{
    struct record *r = &ml_rec[k];
    const struct record *s = &OS_RECORDS[SNARE_RECORD];
    s32 i, id;

    if (ml_rec_built[k])
        return r;
    if (!s->str[0])                             /* the OS has not built its records yet */
        return &OS_RECORDS[SNARE_RECORD];
    OS_STRING_COPY(&r->str[0], &s->str[0]);
    OS_STRING_COPY(&r->str[1], &s->str[1]);
    for (i = 0; i < 17; i++) {
        id = s->id[i];
        if (id >= SNARE_DESC && id < SNARE_DESC + ML_DESC_EACH)
            id += ML_STOCK_DESCS - SNARE_DESC + ML_DESC_EACH * k;
        r->id[i] = id;
    }
    ml_rec_built[k] = 1;
    return r;
}

/* Replaces 0x4004df5c: record number -> record. Stock: 0..6, anything else reads 76 bytes before the
 * table. Here 7 and 8 are ours, and anything else gives KICK's. */
void *ml_record_at(u32 n)
{
    if (n <= ML_STOCK_MACHINES)
        return &OS_RECORDS[n];
    if (n <= ML_MACHINES)
        return added_record(n - ML_STOCK_MACHINES - 1);
    return &OS_RECORDS[1];
}

/* Replaces 0x4004df76: machine -> record. */
void *ml_record_of(u32 m)
{
    if (m < ML_STOCK_MACHINES)
        return ml_record_at((u32)(s32)OS_REC_INDEX[m]);
    if (m < ML_MACHINES)
        return added_record(m - ML_STOCK_MACHINES);
    return &OS_RECORDS[1];
}

/* The OS keeps one state object per descriptor, 76 of them, built one by one at boot. Our descriptors use
 * SNARE's: a track has one machine at a time. */
static u32 state_index(u32 d)
{
    if (d < ML_STOCK_DESCS)
        return d;
    if (d >= ML_DESCS)
        return 0;                               /* as the OS does past the end */
    d -= ML_STOCK_DESCS;
    while (d >= ML_DESC_EACH)
        d -= ML_DESC_EACH;
    return SNARE_DESC + d;
}

/* Replaces 0x4004df40. */
u32 ml_state_at(u32 d)
{
    return OS_STATE + 100 * state_index(d);
}

/* Replaces 0x4004dfa2. */
u32 ml_state_connect(u32 d, u32 arg)
{
    OS_CONNECT(OS_STATE + 20 + 100 * state_index(d), arg, OS_STATE_OWNER);
    return OS_STATE_OWNER;
}

/* Replaces 0x4005a50a: the machine a descriptor belongs to (its first field), which the OS compares with
 * the track's machine to know whether the descriptor applies to the track. */
s32 ml_desc_machine(u32 d)
{
    if (d >= ML_DESCS)
        d = 0;                                  /* as the OS does past the end */
    else if (d >= ML_STOCK_DESCS && ml_owner[d - ML_STOCK_DESCS] >= 0)
        return ml_owner[d - ML_STOCK_DESCS];
    return *(const s32 *)(ml_desc + d * ML_DESC_SIZE);
}
