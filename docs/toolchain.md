# Toolchain: the CSR/Qualcomm ADK this project needs, and how to lay it out

This project builds on top of Qualcomm/CSR's own development kit for CSR867x-family Bluetooth chips (ADK). **The ADK is vendor-licensed software and is not included in this repository** — you need to obtain it yourself from Qualcomm/CSR's own distribution channel for BlueCore/CSR867x development. Everything below assumes you already have the installer packages and only describes how this project's scripts expect them laid out, so the tooling works the same on a fresh machine as it did here.

## Two ADK versions are both needed, for different reasons

| version | why |
|---|---|
| **4.4** | the DSP (Kalimba) assembler/linker/packer (`kas`, `klink`, `kobjcopy`, `elf2kap`) and the application-CPU toolchain and simulator; the conventions used by the scripts here are version-independent, so 4.4 is used for all of this |
| **4.3.1** | naming the speaker's firmware trap stubs correctly. The speaker's application-CPU firmware major version keys the trap numbering, and this unit's firmware needs the 4.3.1 table, not 4.4's. Both trap-number tables this project derived are committed in `tools/traps-bluelab73.json` and `tools/traps-bluelab74.json`, so **a fresh clone of this repository does not need to re-extract either ADK just to read or reference trap names** — only to build or sign a new image |

## Unpacking (the installers are Inno Setup packages)

```sh
# innoextract (not included; get it separately) extracts an Inno Setup .exe without installing it system-wide
IE=/path/to/innoextract
$IE -e -d adk/4.4        ADK_CSR867x.WIN.4.4.0.21.exe
$IE -e -d adk/bluelab74  adk/4.4/tmp/BlueLab-7.4-Release.exe   # nested compiler package
mkdir -p adk/root
cp -r adk/bluelab74/app/. adk/root/     # compilers, make, firmware headers
cp -r adk/4.4/app/.       adk/root/     # apps, libs sources, config tools

$IE -e -d adk/4.3.1      ADK_CSR867x.WIN4.3.1.5.exe
```

`adk/root` is then the ADK's own install root. Always invoke `adk/root/tools/bin/make.exe` (the GNU make the ADK ships) with `adk/root/tools/bin` first on `PATH` — a system `make` will not work with these makefiles.

## What's in it, and what this project's tooling actually calls

- `kas.exe` (the Kalimba assembler — note this is *not* the older `kalasm`), `klink.exe`, `kar.exe`, `elf2kap.exe` (`-b` for the bootstrap form), `kobjdump.exe`/`kobjcopy.exe`/`kreadelf.exe` (Kalimba binutils), `kalsim_csr8670.exe` (the DSP simulator).
- `dfubuild.exe` and its DLLs — the vendor's own filesystem-packing/signing tool. This project's `tools/fsedit.py` uses it purely as a checksum oracle (see `docs/dfu-signature-scheme.md`), not for anything requiring vendor credentials.
- `xap-local-xap-gcc.exe` (an XAP2 GCC build), `vmbuilder.exe`, `packfile`/`unpackfile.exe` — the application-CPU (VM) toolchain.
- `tools/include/firmware/` — the VM trap headers (`message.h`, `stream.h`, `pio.h`, ...).
- `kalimba/`, `src/kalimba/` — DSP library sources; `src/lib/` — VM profile library sources.

## Building the libraries once

Neither library set ships prebuilt:

```sh
R=/path/to/adk/root; export PATH="$R/tools/bin:$PATH"
(cd $R/src/kalimba && "$R/tools/bin/make.exe" -R BLUELAB="$R/tools" TARGET_CORES=gordon)
(cd $R/src/lib     && "$R/tools/bin/make.exe" -R BLUELAB="$R/tools" install)
```

Do not pass `-j`: the Kalimba makefile races on its own `createpath` step.

## Building a project without a chip attached

The ADK's build tools default to querying a real chip over a hardware debug transport and fail ("Unable to query BlueCore over SPI") if none is attached. Generate the project's `.release.mak` once, then build by naming the target chip explicitly:

```sh
"$R/tools/bin/make.exe" -R BLUELAB="$R/tools" HARDWARE=gordon -f <project>.release.mak build
```

`gordon` is the chip codename for the CSR8670 family this product uses; `FLASHSIZE=16384` is this product's flash size if a build step asks for it.

## What this repository's build scripts expect

Every script that touches the ADK expects it at `adk/root` relative to the repository root (configurable at the top of each script if you keep it elsewhere). None of this project's own committed files depend on the ADK being present — only running a *new* build, patch, or simulation does.
