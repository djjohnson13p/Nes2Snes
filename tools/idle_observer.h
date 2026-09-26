/* Read-only instruction-boundary observer, authored for Nes2Snes.
 * No CPU callbacks, bus reads, timing changes or guest writes occur here.
 * When linked into an emulator, that emulator's distribution license applies.
 */
#ifndef N2S_IDLE_OBSERVER_H
#define N2S_IDLE_OBSERVER_H
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#ifdef __cplusplus
#define N2S_EXPORT extern "C" __attribute__((visibility("default")))
#else
#define N2S_EXPORT __attribute__((visibility("default")))
#endif
#define N2S_WATCH_LIMIT 32768u
#define N2S_WATCH_BYTES 16u
/* Fixed 48-byte ABI: counters precede the 16-bit fields and byte payload. */
typedef struct {
    uint64_t ticks;
    uint64_t host_frame;
    uint64_t sample;
    uint16_t pc;
    uint16_t bank;
    uint8_t values[N2S_WATCH_BYTES];
    uint8_t reserved[4];
} n2s_idle_record;
/* The actual ABI is 48 bytes; tested by the C and Python frontends. */
static n2s_idle_record *n2s_idle_records;
static uint16_t n2s_idle_addresses[N2S_WATCH_BYTES];
static uint32_t n2s_idle_count, n2s_idle_capacity, n2s_idle_nbytes;
static uint16_t n2s_idle_tick_pc, n2s_idle_sample_pc;
static uint64_t n2s_idle_ticks, n2s_idle_samples, n2s_idle_frame;
static int n2s_idle_active, n2s_idle_overflow;

N2S_EXPORT void retro_n2s_idle_disable(void) {
    n2s_idle_active = 0;
}
N2S_EXPORT int retro_n2s_idle_configure(uint32_t tick_pc, uint32_t sample_pc,
                                      const uint16_t *addresses, uint32_t count,
                                      uint32_t capacity) {
    uint32_t i, j;
    /* Invalid reconfiguration cannot silently leave an old observer enabled. */
    n2s_idle_active = 0;
    free(n2s_idle_records);
    n2s_idle_records = NULL;
    n2s_idle_count = n2s_idle_capacity = n2s_idle_nbytes = 0;
    n2s_idle_ticks = n2s_idle_samples = n2s_idle_frame = 0;
    n2s_idle_overflow = 0;
    if (tick_pc < 0x8000 || tick_pc > 0xffff || sample_pc < 0x8000 ||
        sample_pc > 0xffff || tick_pc == sample_pc || !addresses ||
        !count || count > N2S_WATCH_BYTES || !capacity || capacity > N2S_WATCH_LIMIT)
        return 0;
    for (i = 0; i < count; ++i) {
        if (addresses[i] >= 2048) return 0;
        for (j = 0; j < i; ++j) if (addresses[i] == addresses[j]) return 0;
    }
    n2s_idle_records = (n2s_idle_record *)calloc(capacity, sizeof(n2s_idle_record));
    if (!n2s_idle_records) return 0;
    memcpy(n2s_idle_addresses, addresses, count * sizeof(uint16_t));
    n2s_idle_capacity = capacity;
    n2s_idle_nbytes = count;
    n2s_idle_tick_pc = (uint16_t)tick_pc;
    n2s_idle_sample_pc = (uint16_t)sample_pc;
    n2s_idle_active = 1;
    return 1;
}
N2S_EXPORT void retro_n2s_idle_frame(uint64_t frame) { n2s_idle_frame = frame; }
N2S_EXPORT const n2s_idle_record *retro_n2s_idle_data(void) { return n2s_idle_records; }
N2S_EXPORT uint64_t retro_n2s_idle_status(unsigned field) {
    switch (field) {
        case 0: return n2s_idle_count;
        case 1: return n2s_idle_samples;
        case 2: return n2s_idle_ticks;
        case 3: return n2s_idle_overflow;
        case 4: return sizeof(n2s_idle_record);
        case 5: return n2s_idle_active;
    }
    return 0;
}
static void n2s_idle_step(uint16_t pc, uint16_t bank, const uint8_t *ram) {
    uint32_t i;
    n2s_idle_record *row;
    if (!n2s_idle_active || !ram) return;
    if (pc == n2s_idle_tick_pc) {
        if (n2s_idle_ticks == UINT64_MAX) n2s_idle_overflow = 1;
        else ++n2s_idle_ticks;
    }
    if (pc != n2s_idle_sample_pc) return;
    if (n2s_idle_samples == UINT64_MAX) { n2s_idle_overflow = 1; return; }
    ++n2s_idle_samples;
    if (n2s_idle_count == n2s_idle_capacity) { n2s_idle_overflow = 1; return; }
    row = &n2s_idle_records[n2s_idle_count++];
    row->ticks = n2s_idle_ticks;
    row->host_frame = n2s_idle_frame;
    row->sample = n2s_idle_samples;
    row->pc = pc;
    row->bank = bank;
    for (i = 0; i < n2s_idle_nbytes; ++i) row->values[i] = ram[n2s_idle_addresses[i]];
}
#endif
