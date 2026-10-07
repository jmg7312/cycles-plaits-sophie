/* SPDX-License-Identifier: MIT */
/*
 * hooks.S - Plaits and Sophie in the Model:Cycles machine list (OS 1.13): the entry points.
 *
 *   ml_boot          boot hook: copies the payload from the end of the OS image to its run address
 *   ml_*_entry       replace four OS accessors (the C functions of machine_list.c)
 *   ml_builder_row, ml_icon_index, ml_knob_vec
 *                    detours in the middle of three OS functions
 *
 * tools/make_firmware.py writes the jumps to these into the OS image. All addresses are OS 1.13.
 * Method and addresses: Modded-Cycles' notes 17 to 20. NOT tested on hardware.
 */
#include "machine_list.h"

/* ---------------------------------------------------------------------------------------------------------
 * Boot hook. The OS clears its BSS with the function at 0x400004b2; its first two instructions (8 bytes)
 * are replaced by a jump here. The payload sits at the end of the OS image, inside the area about to be
 * cleared: copy it to its run address above the BSS, then do the two replaced instructions and carry on.
 * The copy includes the payload's own BSS, as zeros. Uses a0, a1 and d0, which the function is free to use.
 * This code lives in the OS image itself (a freed sprite mask), not in the payload.
 * ------------------------------------------------------------------------------------------------------- */
	.section .stub, "ax"
	.globl	ml_boot
ml_boot:
	lea	_payload_src, %a0
	lea	_start, %a1
	move.l	#_payload_longs, %d0
1:	move.l	(%a0)+, (%a1)+
	subq.l	#1, %d0
	bne.s	1b
	lea	-16(%sp), %sp			/* the two replaced instructions */
	movem.l	%d4-%d7, (%sp)
	jmp	0x400004ba

/* ---------------------------------------------------------------------------------------------------------
 * Entry points of the replaced accessors. The OS functions they replace are leaves that change d0 and d1
 * only (two of them also a0). Their callers were compiled together with them, so they may count on that:
 * a0 and a1 are kept here around the C code.
 * ------------------------------------------------------------------------------------------------------- */
	.section .text.hooks, "ax"

	.macro	ENTRY name, cfunc
	.globl	\name
\name:
	move.l	%a0, -(%sp)
	move.l	%a1, -(%sp)
	move.l	12(%sp), -(%sp)			/* the caller's argument */
	jsr	\cfunc
	addq.l	#4, %sp
	movea.l	(%sp)+, %a1
	movea.l	(%sp)+, %a0
	rts
	.endm

	ENTRY	ml_state_at_entry, ml_state_at		/* replaces 0x4004df40 */
	ENTRY	ml_record_at_entry, ml_record_at	/* replaces 0x4004df5c */
	ENTRY	ml_record_of_entry, ml_record_of	/* replaces 0x4004df76 */
	ENTRY	ml_desc_machine_entry, ml_desc_machine	/* replaces 0x4005a50a */

	/* replaces 0x4004dfa2, which calls another function itself: a plain C function will do */
	.globl	ml_state_connect_entry
ml_state_connect_entry:
	jmp	ml_state_connect

/* ---------------------------------------------------------------------------------------------------------
 * In the boot-time table builder (0x4005a274), at 0x4005a340, in place of
 *     moveq #5,d0 ; cmp.l d5,d0 ; bcc.s 0x4005a384
 * d5 = the descriptor's "machine" field, d2 = the descriptor's number. Stock: a field of 0..5 puts the
 * descriptor in that machine's row (0x4005a384), anything else goes on (0x4005a346).
 * Ours carry 6 and go in their machine's row (ml_owner). Only d0 may change; a0 is in use.
 * ------------------------------------------------------------------------------------------------------- */
	.globl	ml_builder_row
ml_builder_row:
	cmpi.l	#ML_STOCK_DESCS, %d2
	bcc.s	1f
	moveq	#5, %d0				/* a stock descriptor: the stock test */
	cmp.l	%d5, %d0
	bcc.s	3f
2:	jmp	0x4005a346
1:	moveq	#6, %d0				/* one of ours: a knob (6) or the Amp Decay (7, common) */
	cmp.l	%d5, %d0
	bne.s	2b
	move.l	%a0, -(%sp)
	lea	ml_owner - ML_STOCK_DESCS, %a0
	mvs.b	(%a0,%d2.l), %d5
	movea.l	(%sp)+, %a0
3:	jmp	0x4005a384

/* ---------------------------------------------------------------------------------------------------------
 * MACHINES screen (drawn from 0x400a25e0), at 0x400a2638, in place of
 *     lsl.l #5,d4 ; pea 1
 * d3 = d4 = the machine. The stock code goes on to draw the machine's two pictures, numbered like the
 * machine: d4 = 32 * n, d0 = 4 * n, and later d4 - d0 = 28 * n, the offset of the picture. There are six
 * pictures, so the number comes from ml_icon. Does what the stock code does up to 0x400a2646.
 * ------------------------------------------------------------------------------------------------------- */
	.globl	ml_icon_index
ml_icon_index:
	lea	ml_icon, %a1
	mvz.b	(%a1,%d4.l), %d4
	move.l	%d4, %d0
	lsl.l	#2, %d0
	lsl.l	#5, %d4
	pea	1.w
	pea	0x17.w
	jmp	0x400a2646

/* ---------------------------------------------------------------------------------------------------------
 * Main screen, knob -> descriptor (0x4001e814), at 0x4001e8da, called by jsr in place of
 *     move.l 32(sp),d0 ; movea.l 104(a2),a1
 * d0 = the track's machine, a1 = the screen's vector machine -> record number, which has six entries.
 * For our machines: ml_vec. For a machine that does not exist: KICK's knobs. Changes d0 and a1 only.
 * ------------------------------------------------------------------------------------------------------- */
	.globl	ml_knob_vec
ml_knob_vec:
	move.l	36(%sp), %d0			/* the caller's 32(sp), past our return address */
	movea.l	104(%a2), %a1
	cmpi.l	#ML_STOCK_MACHINES, %d0
	bcs.s	1f
	lea	ml_vec, %a1
	cmpi.l	#ML_MACHINES, %d0
	bcs.s	1f
	moveq	#0, %d0
1:	rts

	.section .note.GNU-stack, "", @progbits
