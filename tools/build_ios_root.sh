#!/bin/bash
set -euo pipefail

DMG_DIR="/Users/nguyendinhkhanh/Downloads/ipsw_dmgs"
OUT_RAW="/Users/nguyendinhkhanh/Downloads/ios-root-16g.img"
OUT_SIMG="/Users/nguyendinhkhanh/Downloads/ios-root-16g.simg"

if [ "$(id -u)" -ne 0 ]; then
  echo "Error: Please run this script with sudo: sudo ./tools/build_ios_root.sh"
  exit 1
fi

echo "=========================================================="
echo " Building iOS 16 Root Image for OnePlus 7 (GM1901)"
echo " Skipping DataMigration & Pre-seeding Activation"
echo "=========================================================="

echo "[0/3] Ejecting any lingering DMG mounts..."
for m in /Volumes/SydneyG20G81* /Volumes/AppCryptex* /Volumes/iOSRoot*; do
  if [ -d "$m" ]; then
    diskutil eject "$m" 2>/dev/null || true
  fi
done

echo "[1/3] Creating and patching 16 GiB HFS+ image..."
python3 tools/mkiosroot_macos.py \
  "$DMG_DIR/096-57693-083.dmg" \
  "$DMG_DIR/096-57293-083.dmg" \
  "$DMG_DIR/096-57613-084.dmg" \
  "$OUT_RAW" 16

echo "[2/3] Converting raw image to sparse image (.simg)..."
python3 tools/img2simg.py "$OUT_RAW" "$OUT_SIMG"

echo "[3/3] Removing raw image to save 16 GiB SSD space..."
rm -f "$OUT_RAW"

echo "=========================================================="
echo "🎉 SUCCESS: Generated $OUT_SIMG"
echo "Ready to flash via: fastboot flash -S 512M userdata $OUT_SIMG"
echo "=========================================================="
