/* Read-only original NES instruction-duration observer. No emulated bus reads.
 * Authored for Nes2Snes; linked emulator distribution must follow its license.
 * Records actual elapsed core timestamps, not predicted opcode-table values.
 */
#ifndef N2S_CYCLE_OBSERVER_H
#define N2S_CYCLE_OBSERVER_H
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include "cart.h"
#define GC_EXPORT __attribute__((visibility("default")))
typedef struct {
    uint64_t start, end;
    uint16_t pc, operand, pointer, next_pc;
    uint8_t opcode, p, x, y, a, s, valid, reserved;
} n2s_cycle_row;
static n2s_cycle_row *n2s_cycle_rows;
static uint8_t n2s_cycle_selected[65536];
static uint32_t n2s_cycle_count, n2s_cycle_capacity;
static int n2s_cycle_active, n2s_cycle_pending, n2s_cycle_error;
GC_EXPORT int retro_n2s_cycle_configure(const uint16_t *pcs, uint32_t count, uint32_t capacity) {
    uint32_t i;
    n2s_cycle_active=n2s_cycle_pending=n2s_cycle_error=0;
    free(n2s_cycle_rows);n2s_cycle_rows=NULL;
    n2s_cycle_count=n2s_cycle_capacity=0;
    memset(n2s_cycle_selected,0,sizeof(n2s_cycle_selected));
    if (!pcs || !count || count>32766 || !capacity || capacity>1048576) return 0;
    for(i=0;i<count;i++) {
        if(pcs[i]<0x8000 || pcs[i]>0xfffd || n2s_cycle_selected[pcs[i]]) return 0;
        n2s_cycle_selected[pcs[i]]=1;
    }
    n2s_cycle_rows=(n2s_cycle_row*)calloc(capacity,sizeof(n2s_cycle_row));
    if(!n2s_cycle_rows) return 0;
    n2s_cycle_capacity=capacity;n2s_cycle_active=1;return 1;
}
GC_EXPORT void retro_n2s_cycle_disable(void){n2s_cycle_active=0;}
GC_EXPORT const n2s_cycle_row *retro_n2s_cycle_data(void){return n2s_cycle_rows;}
GC_EXPORT uint32_t retro_n2s_cycle_status(unsigned key){
    switch(key){case 0:return n2s_cycle_count;case 1:return n2s_cycle_error;
        case 2:return sizeof(n2s_cycle_row);case 3:return n2s_cycle_pending;case 4:return n2s_cycle_active;}
    return 0;
}
static void n2s_cycle_begin(uint16_t pc,uint8_t opcode,uint8_t p,uint8_t x,
                            uint8_t y,uint8_t a,uint8_t s,uint64_t now,const uint8_t *ram){
    n2s_cycle_row *row;uint16_t v1=(uint16_t)(pc+1),v2=(uint16_t)(pc+2);uint8_t lo,hi;
    if(!n2s_cycle_active)return;
    if(n2s_cycle_pending){n2s_cycle_error=1;n2s_cycle_active=0;return;}
    if(!n2s_cycle_selected[pc])return;
    if(n2s_cycle_count==n2s_cycle_capacity){n2s_cycle_error=2;n2s_cycle_active=0;return;}
    row=&n2s_cycle_rows[n2s_cycle_count];
    if(!ram || !Page[v1>>11] || !Page[v2>>11]){n2s_cycle_error=3;n2s_cycle_active=0;return;}
    lo=Page[v1>>11][v1];hi=Page[v2>>11][v2];
    row->start=now;row->pc=pc;row->opcode=opcode;row->p=p;row->x=x;row->y=y;
    row->a=a;row->s=s;row->operand=(uint16_t)(lo|((uint16_t)hi<<8));
    row->pointer=(uint16_t)(ram[lo]|((uint16_t)ram[(uint8_t)(lo+1)]<<8));
    row->valid=1;n2s_cycle_pending=1;
}
static void n2s_cycle_end(uint16_t pc,uint64_t now){
    n2s_cycle_row *row;
    if(!n2s_cycle_pending)return;
    row=&n2s_cycle_rows[n2s_cycle_count];row->end=now;row->next_pc=pc;
    if(now<=row->start){n2s_cycle_error=4;n2s_cycle_active=0;}
    n2s_cycle_pending=0;++n2s_cycle_count;
}
#endif
