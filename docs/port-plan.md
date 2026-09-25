# Port plan and acceptance gates

## 1. Preserve the reference

Keep the supplied ROM private and identify every run by hash. Extend repeatable input scripts and capture RAM, execution coverage, graphics mappings and audio-register writes. Preserve matching reconstruction while assigning semantic names only with evidence.

## 2. Native scene renderer

Use converted SNES 2bpp backgrounds and 4bpp sprites. Expand NES attribute bytes to SNES tilemap palette fields. Convert 8x16 NES sprites into an appropriate SNES representation, accounting for vertical flip, clipping, priority and OAM order. Recover palettes from runtime state, not CHR bytes. Reproduce one scene with a frame comparison, then scrolling and a HUD split. DMA is available in the current viewer; its existence alone does not prove a whole-game speedup.

## 3. Original logic on SNES

Choose an address/bank organization after wider mapper traces. The observed 16 KiB switchable window, separately selected `$C000` window, fixed entry bank and nametable changes must be represented. Copying large banks into WRAM on every bank switch may be too costly; do not assume more RAM automatically makes that strategy efficient.

A first acceptance target is original player-update and collision behavior in one room, driven by SNES input and rendered natively. Compare game-state snapshots under identical frame-indexed input. A movable unrelated sprite or prerecorded screen is not this milestone.

## 4. Timing, content and audio

Preserve the game's update cadence while replacing NES register accesses and mapper IRQ timing. Expand coverage to enemies, weapons, alternate characters, transitions, bosses and menus. Develop or adapt an SPC700 driver and translate the observed NES sound sequencing; do not assume MMC5 expansion audio merely from mapper number.

## 5. Optimize only with evidence

Measure worst-case frame budgets and compare gameplay state before and after each change. Candidate improvements include DMA scheduling, sprite output, asset layout and avoiding redundant graphics transfers. Native 16-bit arithmetic is appropriate only where changing 8-bit wrap/flags does not change the game. Keep performance results separate from guesses about available hardware headroom.

## Hardware facts to keep straight

SNES CGRAM has 256 color entries (512 bytes), not 512 entries. Mode 0 supports native 2bpp backgrounds; converting all background art to 4bpp is not mandatory. NES and SNES 2bpp tile layouts differ in plane ordering, which the tested converter handles.

## Completion criteria

A port is not complete until the original game runs through its supported content, audiovisual behavior is validated, known regressions are documented, and representative physical-hardware tests are performed. Current artifacts meet the earlier extraction/reconstruction/viewer gates only.
