; Optional performance bookkeeping. This macro is only used where the
; caller restores guest flags or immediately overwrites host N/Z. It does not
; gate frame IDs, fault handling, audio state, or mapper/PPU semantics.
.macro CountRuntime address
    .if USE_RUNTIME_COUNTERS
        inc address
        bne :+
        inc address+2
    :
    .endif
.endmacro
