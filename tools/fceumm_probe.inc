/* Optional instrumentation for FCEUmm x6502.c.
 * New instrumentation for Nes2Snes; when linked into FCEUmm, distribute under
 * FCEUmm's GPL-2.0-or-later terms together with its corresponding source.
 * Captures observed execution only. It does not prove complete code coverage.
 */
#include <stdlib.h>
#include <stdint.h>
#include "cart.h"
#include "ppu.h"
#include "palette.h"
static uint32_t *n2s_exec;
static uint16_t *n2s_pc, *n2s_io_min, *n2s_io_max;
static uint8_t *n2s_io_flags;
static uint32_t n2s_size, n2s_off = 0xffffffff;
static uint32_t n2s_reads[0x4000], n2s_writes[0x4000];
static uint8_t n2s_mmc5_values[0x207 * 32];
static uint8_t n2s_snapshot[8192];
extern uint8_t PALRAM[0x20], SPRAM[0x100], XOffset;
extern uint32_t TempAddr, RefreshAddr;

static void n2s_instruction(uint16_t pc) {
    uintptr_t p, base;
    n2s_off = 0xffffffff;
    if (pc < 0x8000 || !PRGptr[0] || !Page[pc >> 11]) return;
    if (!n2s_exec) {
        n2s_size = PRGsize[0];
        n2s_exec = (uint32_t*)calloc(n2s_size, sizeof(uint32_t));
        n2s_pc = (uint16_t*)calloc(n2s_size, sizeof(uint16_t));
        n2s_io_min = (uint16_t*)calloc(n2s_size, sizeof(uint16_t));
        n2s_io_max = (uint16_t*)calloc(n2s_size, sizeof(uint16_t));
        n2s_io_flags = (uint8_t*)calloc(n2s_size, 1);
        if (!n2s_exec || !n2s_pc || !n2s_io_min || !n2s_io_max || !n2s_io_flags) abort();
    }
    base = (uintptr_t)PRGptr[0];
    p = (uintptr_t)(Page[pc >> 11] + pc);
    if (p < base || p-base >= n2s_size) return;
    n2s_off = (uint32_t)(p-base);
    if (n2s_exec[n2s_off] != 0xffffffff) n2s_exec[n2s_off]++;
    n2s_pc[n2s_off] = pc;
}

static void n2s_io(uint32_t address, int write, uint8_t value) {
    if (address < 0x2000 || address >= 0x6000) return;
    if (write) {
        n2s_writes[address-0x2000]++;
        if (address >= 0x5000 && address <= 0x5206)
            n2s_mmc5_values[(address-0x5000)*32+(value>>3)] |= 1u << (value & 7);
    } else n2s_reads[address-0x2000]++;
    if (n2s_off >= n2s_size || !n2s_exec) return;
    n2s_io_flags[n2s_off] |= write ? 2 : 1;
    if (!n2s_io_min[n2s_off] || address < n2s_io_min[n2s_off]) n2s_io_min[n2s_off] = address;
    if (address > n2s_io_max[n2s_off]) n2s_io_max[n2s_off] = address;
}

__attribute__((visibility("default"))) size_t retro_n2s_size(unsigned kind) {
    switch(kind) {
        case 0:return n2s_size * 4;
        case 1:case 3:case 4:return n2s_size * 2;
        case 2:return n2s_size;
        case 5:case 6:return sizeof(n2s_reads);
        case 7:return sizeof(n2s_mmc5_values);
        case 8:return 32;
        case 9:return 4096;
        case 10:case 11:return 8192;
        case 12:return 256;
        case 13:return 4;
        case 14:return 192;
        case 15:return 5;
    }
    return 0;
}

__attribute__((visibility("default"))) const void *retro_n2s_data(unsigned kind) {
    unsigned i;
    switch(kind) {
        case 0:return n2s_exec;
        case 1:return n2s_pc;
        case 2:return n2s_io_flags;
        case 3:return n2s_io_min;
        case 4:return n2s_io_max;
        case 5:return n2s_reads;
        case 6:return n2s_writes;
        case 7:return n2s_mmc5_values;
        case 8:return PALRAM;
        case 9:
            for (i=0;i<4;i++) if(vnapage[i]) memcpy(n2s_snapshot+i*1024,vnapage[i],1024);
            return n2s_snapshot;
        case 10:case 11:
            for (i=0;i<8192;i++) {
                uint8_t *page = kind==10 ? MMC5BGVPage[i>>10] : MMC5SPRVPage[i>>10];
                n2s_snapshot[i] = page ? page[i] : 0;
            }
            return n2s_snapshot;
        case 12:return SPRAM;
        case 13:return PPU;
        case 14:return palo;
        case 15:
            n2s_snapshot[0] = TempAddr; n2s_snapshot[1] = TempAddr >> 8;
            n2s_snapshot[2] = RefreshAddr; n2s_snapshot[3] = RefreshAddr >> 8;
            n2s_snapshot[4] = XOffset;
            return n2s_snapshot;
    }
    return NULL;
}
