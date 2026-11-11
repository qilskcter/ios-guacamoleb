#!/bin/bash
# dxb runs patches/*.sh from the XNU source root before applying *.patch.
set -euo pipefail

[[ "${MACHINE_CONFIG:-}" == SWEET ]] || exit 0

src=""
if [[ -f ../patches/wallpaper.lz4 ]]; then
    src="../patches/wallpaper.lz4"
elif [[ -f patches/wallpaper.lz4 ]]; then
    src="patches/wallpaper.lz4"
elif [[ -f wallpaper.lz4 ]]; then
    src="wallpaper.lz4"
fi

if [[ -n "$src" ]]; then
    mkdir -p EXTERNAL_HEADERS osfmk bsd libkern iokit/Kernel/arm
    cp "$src" EXTERNAL_HEADERS/wallpaper.lz4
    cp "$src" osfmk/wallpaper.lz4
    cp "$src" bsd/wallpaper.lz4
    cp "$src" libkern/wallpaper.lz4
    cp "$src" iokit/wallpaper.lz4 2>/dev/null || true
    cp "$src" iokit/Kernel/wallpaper.lz4 2>/dev/null || true
    cp "$src" iokit/Kernel/arm/wallpaper.lz4
    cp "$src" wallpaper.lz4
    echo "SWEET: staged wallpaper.lz4 from $src to all include paths successfully"
else
    echo "SWEET: error: wallpaper.lz4 not found in expected locations" >&2
    exit 1
fi
