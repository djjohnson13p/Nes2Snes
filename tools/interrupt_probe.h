/* Boundary-request TEST harness for authored NES fixtures only.
 * This is not a read-only probe: it asserts an external IRQ or an NMI latch at
 * a selected instruction completion. It never writes guest RAM/registers or
 * rewrites the emulator's interrupt decision/entry implementation.
 * Not a physical phi2/pin sampling oracle. Never use on acceptance gameplay.
 */
#ifndef N2S_INTERRUPT_PROBE_H
#define N2S_INTERRUPT_PROBE_H
#include <stdint.h>
#include <string.h>
#define IB_EXPORT __attribute__((visibility("default")))
typedef struct {
    uint64_t boundary_time, next_time;
    uint16_t pc, next_pc;
    uint8_t before_p, after_p, next_p, s, next_s, a, x, y;
    uint8_t next_a, next_x, next_y, complete;
    uint8_t before_stack[256], after_stack[256];
} n2s_interrupt_row;
static n2s_interrupt_row n2s_ib_row;
static uint16_t n2s_ib_target;
static uint8_t n2s_ib_opcode, n2s_ib_irq, n2s_ib_nmi;
static unsigned n2s_ib_stage, n2s_ib_executing, n2s_ib_error;
IB_EXPORT int retro_n2s_interrupt_configure(unsigned pc, unsigned opcode, unsigned irq, unsigned nmi) {
    memset(&n2s_ib_row,0,sizeof(n2s_ib_row));
    n2s_ib_stage=n2s_ib_executing=n2s_ib_error=0;
    if(pc<0x8000 || pc>0xfffd || opcode>255 || irq>1 || nmi>1) return 0;
    n2s_ib_target=(uint16_t)pc; n2s_ib_opcode=(uint8_t)opcode;
    n2s_ib_irq=(uint8_t)irq; n2s_ib_nmi=(uint8_t)nmi; n2s_ib_stage=1;
    return 1;
}
IB_EXPORT const n2s_interrupt_row *retro_n2s_interrupt_data(void) {return &n2s_ib_row;}
IB_EXPORT unsigned retro_n2s_interrupt_status(unsigned key) {
    switch(key) {case 0:return n2s_ib_stage;case 1:return n2s_ib_error;
                case 2:return sizeof(n2s_interrupt_row);}
    return 0;
}
static void n2s_ib_before(uint16_t pc,uint8_t p,uint8_t s,uint8_t a,uint8_t x,uint8_t y,
                          uint64_t time,const uint8_t *ram) {
    if(n2s_ib_stage==2) {
        n2s_ib_row.next_time=time; n2s_ib_row.next_pc=pc; n2s_ib_row.next_p=p;
        n2s_ib_row.next_s=s; n2s_ib_row.next_a=a; n2s_ib_row.next_x=x; n2s_ib_row.next_y=y;
        memcpy(n2s_ib_row.after_stack,ram+0x100,256);
        n2s_ib_row.complete=1; n2s_ib_stage=3;
    } else if(n2s_ib_stage==1 && pc==n2s_ib_target) {
        n2s_ib_row.before_p=p; n2s_ib_executing=1;
    }
}
static void n2s_ib_after(uint8_t opcode,uint16_t pc,uint8_t p,uint8_t s,uint8_t a,uint8_t x,uint8_t y,
                         uint64_t time,const uint8_t *ram) {
    if(!n2s_ib_executing) return;
    n2s_ib_executing=0;
    if(opcode!=n2s_ib_opcode) {n2s_ib_error=1;n2s_ib_stage=0;return;}
    n2s_ib_row.boundary_time=time; n2s_ib_row.pc=pc; n2s_ib_row.after_p=p;
    n2s_ib_row.s=s; n2s_ib_row.a=a; n2s_ib_row.x=x; n2s_ib_row.y=y;
    memcpy(n2s_ib_row.before_stack,ram+0x100,256); n2s_ib_stage=2;
    if(n2s_ib_irq) X6502_IRQBegin(FCEU_IQEXT);
    if(n2s_ib_nmi) TriggerNMI();
}
#endif
