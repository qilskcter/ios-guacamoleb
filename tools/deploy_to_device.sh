#!/bin/bash
# Deploy HakiosMetal.bundle and libhakios.sb.dylib to iOS root filesystem.
#
# Usage:
#   1. Offline / Mounted Rootfs:
#      sudo ./tools/deploy_to_device.sh /Volumes/iOSRoot
#
#   2. Online via Recovery (OrangeFox/TWRP) with ADB:
#      ./tools/deploy_to_device.sh
#      (Device booted into recovery via: fastboot boot recovery/recovery.img)

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
METAL_BUNDLE="$REPO_DIR/assets/HakiosMetal.bundle"
SB_DYLIB="$REPO_DIR/assets/libhakios.sb.dylib"

if [ ! -d "$METAL_BUNDLE" ]; then
    echo "[-] Error: $METAL_BUNDLE not found. Build it first." >&2
    exit 1
fi

if [ $# -ge 1 ]; then
    TARGET_ROOT="$1"
    echo "[*] Deploying to local rootfs mount: $TARGET_ROOT"
    if [ ! -d "$TARGET_ROOT/System/Library" ]; then
        echo "[-] Error: $TARGET_ROOT does not look like an iOS rootfs (missing System/Library)." >&2
        exit 1
    fi

    # Install HakiosMetal.bundle
    DST_EXT="$TARGET_ROOT/System/Library/Extensions/HakiosMetal.bundle"
    echo "[*] Copying HakiosMetal.bundle to $DST_EXT..."
    mkdir -p "$(dirname "$DST_EXT")"
    rm -rf "$DST_EXT"
    cp -R "$METAL_BUNDLE" "$DST_EXT"
    chown -R 0:0 "$DST_EXT"
    chmod -R 755 "$DST_EXT"

    # Install libhakios.sb.dylib
    if [ -f "$SB_DYLIB" ]; then
        DST_DYLIB="$TARGET_ROOT/usr/lib/libhakios.sb.dylib"
        echo "[*] Copying libhakios.sb.dylib to $DST_DYLIB..."
        mkdir -p "$(dirname "$DST_DYLIB")"
        cp "$SB_DYLIB" "$DST_DYLIB"
        chown 0:0 "$DST_DYLIB"
        chmod 755 "$DST_DYLIB"
    fi

    echo "[*] Running sweet-root-tweaks.py on $TARGET_ROOT..."
    python3 "$REPO_DIR/tools/sweet-root-tweaks.py" "$TARGET_ROOT"
    sync
    echo "[+] Deployment to $TARGET_ROOT completed successfully!"
    exit 0
fi

# ADB Recovery Deployment
echo "=========================================================="
echo " HakiosMetal & UI Optimizations ADB Deployment"
echo "=========================================================="
command -v adb >/dev/null 2>&1 || { echo "[-] Error: adb not found in PATH" >&2; exit 1; }

echo "[*] Waiting for recovery device over ADB..."
adb wait-for-device
adb root
adb wait-for-device

USERDATA_DEV=$(adb shell 'for d in /dev/block/by-name/userdata /dev/block/bootdevice/by-name/userdata /dev/block/sda19; do [ -e $d ] && readlink -f $d && break; done' 2>/dev/null | tr -d '\r')
if [ -z "$USERDATA_DEV" ]; then
    echo "[-] Error: userdata block device not found on connected device." >&2
    exit 1
fi
echo "[+] Detected userdata partition: $USERDATA_DEV"

echo "[*] Creating temporary mountpoint /mnt/ios on device..."
adb shell 'mkdir -p /mnt/ios'
adb shell "mount -t hfsplus -o rw,force $USERDATA_DEV /mnt/ios || mount -o rw $USERDATA_DEV /mnt/ios"

echo "[*] Pushing HakiosMetal.bundle to /mnt/ios/System/Library/Extensions/..."
adb shell 'mkdir -p /mnt/ios/System/Library/Extensions'
adb shell 'rm -rf /mnt/ios/System/Library/Extensions/HakiosMetal.bundle'
adb push "$METAL_BUNDLE" /mnt/ios/System/Library/Extensions/
adb shell 'chmod -R 755 /mnt/ios/System/Library/Extensions/HakiosMetal.bundle && chown -R 0:0 /mnt/ios/System/Library/Extensions/HakiosMetal.bundle'

if [ -f "$SB_DYLIB" ]; then
    echo "[*] Pushing libhakios.sb.dylib to /mnt/ios/usr/lib/..."
    adb shell 'mkdir -p /mnt/ios/usr/lib'
    adb push "$SB_DYLIB" /mnt/ios/usr/lib/libhakios.sb.dylib
    adb shell 'chmod 755 /mnt/ios/usr/lib/libhakios.sb.dylib && chown 0:0 /mnt/ios/usr/lib/libhakios.sb.dylib'
fi

echo "[*] Syncing and unmounting /mnt/ios..."
adb shell 'sync'
adb shell 'umount /mnt/ios'
echo "[+] Deployment via ADB completed successfully!"
