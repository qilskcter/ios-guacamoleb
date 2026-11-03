#!/bin/bash
# One-click helper to boot OnePlus 7 into iOS 16 via fastboot
set -e
cd "$(dirname "$0")/.."

echo "=========================================================="
echo " Booting OnePlus 7 (GM1901) into iOS 16"
echo "=========================================================="

if ! command -v fastboot >/dev/null 2>&1; then
  echo "Error: fastboot not found in PATH."
  exit 1
fi

echo "[*] Waiting for device in Fastboot Mode..."
fastboot wait-for-device

echo "[*] Sending boot image (shim-boot-0083.img)..."
fastboot boot shim/out/shim-boot-0083.img

echo "=========================================================="
echo "🎉 Boot command sent successfully! Device is starting iOS 16."
echo "=========================================================="
