/* SPDX-License-Identifier: MIT */
/* Sizes of the machine list, shared by machine_list.c and hooks.S. tools/make_firmware.py has the same
 * numbers and checks them against the symbols of the built payload. */
#ifndef MACHINE_LIST_H
#define MACHINE_LIST_H

#define ML_STOCK_MACHINES 6         /* KICK SNARE METAL PERC TONE CHORD */
#define ML_ADDED          2         /* Plaits (machine 6), Sophie (machine 7) */
#define ML_MACHINES       8
#define ML_STOCK_DESCS    76        /* parameter descriptors of the stock OS */
#define ML_DESC_EACH      5         /* per added machine: COLOR SHAPE SWEEP CONTOUR, Amp Decay */
#define ML_DESCS          86
#define ML_DESC_SIZE      0x38
#define ML_STRINGS        192       /* room for our machine and knob names */

#endif
