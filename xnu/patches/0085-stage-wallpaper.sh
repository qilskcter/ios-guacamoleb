#!/bin/bash
# dxb runs patches/*.sh from the XNU source root before applying *.patch.
set -euo pipefail

[[ "${MACHINE_CONFIG:-}" == SWEET ]] || exit 0

if [[ -f ../patches/wallpaper.lz4 ]]; then
    mkdir -p EXTERNAL_HEADERS osfmk iokit/Kernel/arm bsd libkern
    cp ../patches/wallpaper.lz4 EXTERNAL_HEADERS/wallpaper.lz4
    cp ../patches/wallpaper.lz4 osfmk/wallpaper.lz4
    cp ../patches/wallpaper.lz4 bsd/wallpaper.lz4
    cp ../patches/wallpaper.lz4 libkern/wallpaper.lz4
    cp ../patches/wallpaper.lz4 iokit/Kernel/arm/wallpaper.lz4
    cp ../patches/wallpaper.lz4 wallpaper.lz4
    echo "SWEET: staged wallpaper.lz4 to EXTERNAL_HEADERS, osfmk, bsd, libkern, iokit successfully"
else
    echo "SWEET: error: ../patches/wallpaper.lz4 not found" >&2
    exit 1
fi
