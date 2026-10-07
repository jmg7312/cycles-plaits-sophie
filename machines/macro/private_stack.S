/* SPDX-License-Identifier: MIT */
/*
 * private_stack.S - call a function on a stack of our own.
 *
 * Why: the Model:Cycles' audio interrupt does not switch stacks. It runs on the stack of whatever task it
 * interrupted, and the smallest task stack of OS 1.13 is 2 048 bytes. The stock machines use about 250 bytes
 * below the voice loop; macro_render() uses up to 1 700. So the Plaits adapter calls it through here, on a
 * 4 096-byte area of its own (macro_cycles.c).
 *
 *     void macro_on_private_stack(void *stack_top, void (*fn)(), a, b, c, d, e);    calls fn(a, b, c, d, e)
 *
 * The stack pointer changes in one instruction each way, so an interrupt can arrive at any point: it finds
 * a valid stack either side. One area is enough: the six voices are rendered one after the other, inside
 * the same interrupt. Only a0, a1 and what fn itself changes are changed.
 */
	.section .text.macro_on_private_stack, "ax"
	.globl	macro_on_private_stack
macro_on_private_stack:
	movea.l	4(%sp), %a1
	move.l	%sp, -(%a1)			/* the caller's stack pointer, kept at the top */
	move.l	28(%sp), -(%a1)			/* e */
	move.l	24(%sp), -(%a1)
	move.l	20(%sp), -(%a1)
	move.l	16(%sp), -(%a1)
	move.l	12(%sp), -(%a1)			/* a */
	movea.l	8(%sp), %a0
	movea.l	%a1, %sp
	jsr	(%a0)
	movea.l	20(%sp), %sp
	rts

	.section .note.GNU-stack, "", @progbits
