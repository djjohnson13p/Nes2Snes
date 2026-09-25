PYTHON ?= python3
ROM ?= original/CV3.nes
SNES_CORE ?= .tools/cores/snes9x_libretro.so
NES_CORE ?= .tools/cores/fceumm_probe_libretro.so
.PHONY: test synthetic viewer verify-synthetic verify-viewer analyze trace disassemble

test:
	$(PYTHON) -m unittest discover -s tests -v
synthetic:
	$(PYTHON) tools/build_viewer.py --synthetic --out build/synthetic
viewer:
	$(PYTHON) tools/build_viewer.py --rom "$(ROM)" --out build/cv3
verify-synthetic: synthetic
	$(PYTHON) tools/verify_viewer.py --core "$(SNES_CORE)" --sfc build/synthetic/chr-viewer.sfc --synthetic --out build/synthetic/verification
verify-viewer: viewer
	$(PYTHON) tools/verify_viewer.py --core "$(SNES_CORE)" --sfc build/cv3/chr-viewer.sfc --rom "$(ROM)" --out build/cv3/verification
analyze:
	$(PYTHON) tools/analyze_rom.py "$(ROM)" --out build/analysis
trace:
	$(PYTHON) tools/trace_rom.py --core "$(NES_CORE)" --rom "$(ROM)" --out build/trace
disassemble:
	$(PYTHON) tools/analyze_rom.py "$(ROM)" --out build/analysis --trace build/trace
