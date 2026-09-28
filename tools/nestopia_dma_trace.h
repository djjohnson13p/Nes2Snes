/* Read-only instruction timing observation for the pinned Nestopia core.
 * No bus reads, expected values, clock changes, or writes to guest state.
 * The original core's license applies when distributing a linked core.
 */
#ifndef N2S_NESTOPIA_DMA_TRACE_H
#define N2S_NESTOPIA_DMA_TRACE_H
#include <stdint.h>
#include <string.h>
struct n2s_dma_row {
    uint64_t start, end;
    uint16_t pc, next_pc;
    uint32_t clock;
    uint8_t opcode, reserved[7];
};
static n2s_dma_row n2s_dma_rows[64];
static uint32_t n2s_dma_count, n2s_dma_limit, n2s_dma_pending, n2s_dma_error;
static uint16_t n2s_dma_entry;
static bool n2s_dma_started;
extern "C" int retro_n2s_dma_configure(uint16_t entry, uint32_t count) {
    n2s_dma_count=n2s_dma_limit=n2s_dma_pending=n2s_dma_error=0;
    n2s_dma_started=false;
    memset(n2s_dma_rows,0,sizeof(n2s_dma_rows));
    if (entry<0x8000 || !count || count>64) return 0;
    n2s_dma_entry=entry;n2s_dma_limit=count;return 1;
}
extern "C" const n2s_dma_row *retro_n2s_dma_data(void) { return n2s_dma_rows; }
extern "C" uint32_t retro_n2s_dma_status(unsigned key) {
    switch(key) { case 0:return n2s_dma_count;case 1:return n2s_dma_error;
        case 2:return sizeof(n2s_dma_row);case 3:return n2s_dma_pending;
        case 4:return n2s_dma_started;default:return 0; }
}
static void n2s_dma_begin(uint16_t pc, uint64_t now, uint32_t clock) {
    if (!n2s_dma_limit || n2s_dma_error || n2s_dma_count>=n2s_dma_limit) return;
    if (!n2s_dma_started) { if(pc!=n2s_dma_entry)return; n2s_dma_started=true; }
    if(n2s_dma_pending || !clock) { n2s_dma_error=1;return; }
    n2s_dma_row &r=n2s_dma_rows[n2s_dma_count];r.start=now;r.pc=pc;r.clock=clock;
    n2s_dma_pending=1;
}
static void n2s_dma_end(uint16_t pc, uint8_t opcode, uint64_t now) {
    if(!n2s_dma_pending)return;
    n2s_dma_row &r=n2s_dma_rows[n2s_dma_count];r.end=now;r.next_pc=pc;r.opcode=opcode;
    if(now<=r.start || (now-r.start)%r.clock) n2s_dma_error=2;
    n2s_dma_pending=0;++n2s_dma_count;
}
#endif
