/* External request stream for authored instruction-timeline tests only.
 * This harness asserts requests AFTER completed instructions using elapsed core
 * timestamps. It is not a pin sampler, a read-only gameplay probe, or a clock
 * oracle for the production port. Original interrupt dispatch remains unchanged.
 */
#ifndef N2S_TIMELINE_PROBE_H
#define N2S_TIMELINE_PROBE_H
#include <stdint.h>
#include <string.h>
#define TL_EXPORT __attribute__((visibility("default")))
#define TL_MAX_ROWS 113
#define TL_MAX_EVENTS 64
typedef struct { uint32_t cycle; uint8_t irq, nmi, reserved[2]; } tl_event;
typedef struct {
    uint32_t cycle;
    uint16_t pc;
    uint8_t a,x,y,p,s,irq,nmi,event_index,cost,entry,kind,opcode;
    uint16_t ordinal;
    uint8_t reserved[12];
    uint8_t ram[512];
} tl_row;
static tl_row tl_rows[TL_MAX_ROWS];
static tl_event tl_events[TL_MAX_EVENTS];
static uint32_t tl_count,tl_limit,tl_event_count,tl_event_index,tl_error;
static uint64_t tl_origin,tl_before_time,tl_after_time;
static uint16_t tl_start;
static uint8_t tl_active,tl_started,tl_opcode,tl_pending;
TL_EXPORT unsigned retro_n2s_timeline_status(unsigned key) {
    switch(key){case 0:return tl_count;case 1:return tl_error;case 2:return sizeof(tl_row);
        case 3:return tl_active;case 4:return tl_event_index;case 5:return sizeof(tl_event);}
    return 0;
}
TL_EXPORT const tl_row *retro_n2s_timeline_data(void){return tl_rows;}
TL_EXPORT int retro_n2s_timeline_configure(unsigned pc, unsigned steps, const tl_event *events, unsigned count) {
    unsigned i;tl_active=tl_started=tl_pending=0;tl_count=tl_error=tl_event_index=0;
    memset(tl_rows,0,sizeof(tl_rows));memset(tl_events,0,sizeof(tl_events));
    if(pc<0x8000 || pc>0xfffd || !steps || steps>=TL_MAX_ROWS || count>TL_MAX_EVENTS || (count && !events))return 0;
    for(i=0;i<count;i++) {
        if(!events[i].cycle || events[i].irq>1 || events[i].nmi>1 || events[i].reserved[0] || events[i].reserved[1] || (i && events[i].cycle<=events[i-1].cycle))return 0;
        tl_events[i]=events[i];
    }
    tl_start=(uint16_t)pc;tl_limit=steps+1;tl_event_count=count;tl_active=1;return 1;
}
static void tl_before(uint16_t pc,uint8_t a,uint8_t x,uint8_t y,uint8_t p,uint8_t s,
                       uint64_t time,unsigned requests,const uint8_t *ram) {
    tl_row *r;uint64_t gap;
    if(!tl_active)return;
    if(!tl_started) {
        if(pc!=tl_start)return;
        tl_started=1;tl_origin=time;
    }
    if(!ram || time<tl_origin || time-tl_origin>UINT32_MAX || tl_count>=tl_limit){tl_error=1;tl_active=0;return;}
    r=&tl_rows[tl_count];r->cycle=(uint32_t)(time-tl_origin);r->pc=pc;
    r->a=a;r->x=x;r->y=y;r->p=p;r->s=s;
    r->irq=!!(requests&FCEU_IQEXT);r->nmi=!!(requests&FCEU_IQNMI);r->event_index=(uint8_t)tl_event_index;
    r->ordinal=(uint16_t)tl_count;
    if(tl_count) {
        if(!tl_pending || time<tl_after_time){tl_error=2;tl_active=0;return;}
        gap=time-tl_after_time;
        if(gap!=0 && gap!=7){tl_error=3;tl_active=0;return;}
        r->cost=(uint8_t)(tl_after_time-tl_before_time);r->entry=(uint8_t)gap;
        /* Entry is identified by the vector the UNMODIFIED core selected. */
        r->kind=gap ? ((pc==(uint16_t)(Page[0xFFFA>>11][0xFFFA]|(Page[0xFFFB>>11][0xFFFB]<<8)))?2:1) : 0;
        r->opcode=tl_opcode;
    }
    memcpy(r->ram,ram,512);tl_count++;tl_pending=0;tl_before_time=time;
    if(tl_count==tl_limit)tl_active=0;
}
static void tl_after(uint8_t opcode,uint64_t time) {
    uint64_t elapsed;
    if(!tl_active || !tl_started)return;
    if(time<=tl_before_time || time-tl_before_time>255){tl_error=4;tl_active=0;return;}
    tl_after_time=time;tl_opcode=opcode;tl_pending=1;elapsed=time-tl_origin;
    while(tl_event_index<tl_event_count && tl_events[tl_event_index].cycle<=elapsed) {
        const tl_event *e=&tl_events[tl_event_index++];
        if(e->irq)X6502_IRQBegin(FCEU_IQEXT);else X6502_IRQEnd(FCEU_IQEXT);
        if(e->nmi)TriggerNMI();
    }
}
#endif
