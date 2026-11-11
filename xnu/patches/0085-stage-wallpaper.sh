#!/bin/bash
# dxb runs patches/*.sh from the XNU source root before applying *.patch.
set -euo pipefail

[[ "${MACHINE_CONFIG:-}" == SWEET ]] || exit 0

if [[ -f ../patches/wallpaper.lz4 ]]; then
    cp ../patches/wallpaper.lz4 iokit/Kernel/arm/wallpaper.lz4
    cp ../patches/wallpaper.lz4 wallpaper.lz4
    echo "SWEET: staged wallpaper.lz4 successfully"
else
    echo "SWEET: warning: ../patches/wallpaper.lz4 not found"
fi
