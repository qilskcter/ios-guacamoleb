#!/usr/bin/env python3
"""Build a 16 GB case-sensitive journaled HFS+ iOS root image on macOS.

Usage (requires sudo):
  sudo python3 tools/mkiosroot_macos.py OS.dmg SYSTEMOS.dmg APPOS.dmg OUT.img [SIZE_GB]

Example:
  sudo python3 tools/mkiosroot_macos.py \\
    /Users/nguyendinhkhanh/Downloads/ipsw_dmgs/096-57693-083.dmg \\
    /Users/nguyendinhkhanh/Downloads/ipsw_dmgs/096-57293-083.dmg \\
    /Users/nguyendinhkhanh/Downloads/ipsw_dmgs/096-57613-084.dmg \\
    /Users/nguyendinhkhanh/Downloads/ios-root-16g.img 16
"""

import argparse
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

MOBILE_UID = 501
LOGD_UID = 272


def run_cmd(cmd, check=True, capture=True):
    print(f"[*] Running: {' '.join(cmd)}")
    p = subprocess.run(cmd, check=check, text=True, capture_output=capture)
    return p.stdout.strip() if capture else None


def attach_dmg_readonly(dmg_path):
    out = run_cmd(['hdiutil', 'attach', '-readonly', '-nobrowse', '-plist', dmg_path])
    info = plistlib.loads(out.encode())
    mount_point = None
    dev_entry = None
    for entity in info.get('system-entities', []):
        if 'mount-point' in entity:
            mount_point = entity['mount-point']
        if 'dev-entry' in entity and dev_entry is None:
            dev_entry = entity['dev-entry']
    if not mount_point:
        raise RuntimeError(f"Could not find mount point for {dmg_path}")
    print(f"[+] Attached {os.path.basename(dmg_path)} at {mount_point} ({dev_entry})")
    return dev_entry, mount_point


def detach_disk(dev_entry):
    if not dev_entry:
        return
    print(f"[*] Detaching {dev_entry}...")
    subprocess.run(['diskutil', 'eject', dev_entry], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def create_and_format_hfs(out_img, size_gb):
    if os.path.exists(out_img):
        print(f"[*] Removing existing target {out_img}")
        os.remove(out_img)

    size_bytes = size_gb * 1024 * 1024 * 1024
    print(f"[*] Allocating {size_gb} GiB ({size_bytes} bytes) for {out_img}...")
    with open(out_img, 'wb') as f:
        f.truncate(size_bytes)

    out = run_cmd(['hdiutil', 'attach', '-nomount', out_img])
    dev = out.split()[0]
    rdev = dev.replace('/dev/', '/dev/r')
    print(f"[+] Attached raw image at {dev} ({rdev})")

    print(f"[*] Formatting {rdev} as Case-sensitive Journaled HFS+ (volume name: iOSRoot)...")
    run_cmd(['newfs_hfs', '-s', '-J', '-v', 'iOSRoot', rdev], capture=False)

    return dev


def main():
    parser = argparse.ArgumentParser(description="Create iOS root HFS+ image on macOS")
    parser.add_argument('os_dmg', help="Path to OS.dmg")
    parser.add_argument('sysos_dmg', help="Path to SystemOS.dmg")
    parser.add_argument('appos_dmg', help="Path to AppOS.dmg")
    parser.add_argument('out_img', help="Output raw .img path")
    parser.add_argument('size_gb', type=int, default=16, nargs='?', help="Size in GiB (default: 16)")
    args = parser.parse_args()

    if os.geteuid() != 0:
        sys.exit("Error: This script must be run as root (use sudo) to preserve exact Apple system UIDs/GIDs.")

    for p in (args.os_dmg, args.sysos_dmg, args.appos_dmg):
        if not os.path.exists(p):
            sys.exit(f"Error: file not found: {p}")

    os_dmg = os.path.abspath(args.os_dmg)
    sysos_dmg = os.path.abspath(args.sysos_dmg)
    appos_dmg = os.path.abspath(args.appos_dmg)
    out_img = os.path.abspath(args.out_img)
    size_gb = args.size_gb

    attached_disks = []
    target_dev = None
    target_mount = None

    try:
        # 1. Create and format target image
        target_dev = create_and_format_hfs(out_img, size_gb)
        attached_disks.append(target_dev)

        # 2. Mount target image
        target_mount = tempfile.mkdtemp(prefix="ios_root_")
        print(f"[*] Mounting target image {target_dev} at {target_mount}...")
        run_cmd(['mount', '-t', 'hfs', '-o', 'owners', target_dev, target_mount], capture=False)

        # 3. Attach readonly input DMGs
        os_dev, os_mnt = attach_dmg_readonly(os_dmg)
        attached_disks.append(os_dev)

        sys_dev, sys_mnt = attach_dmg_readonly(sysos_dmg)
        attached_disks.append(sys_dev)

        app_dev, app_mnt = attach_dmg_readonly(appos_dmg)
        attached_disks.append(app_dev)

        # 4. Copy OS root
        print(f"[*] Copying OS root from {os_mnt} to target...")
        run_cmd(['rsync', '-aH', '--numeric-ids', f'{os_mnt}/', f'{target_mount}/'], capture=False)

        # 5. Copy Cryptexes
        preboot_os = os.path.join(target_mount, 'private/preboot/Cryptexes/OS')
        preboot_app = os.path.join(target_mount, 'private/preboot/Cryptexes/App')
        os.makedirs(preboot_os, exist_ok=True)
        os.makedirs(preboot_app, exist_ok=True)

        print(f"[*] Copying SystemOS cryptex to {preboot_os}...")
        run_cmd(['rsync', '-aH', '--numeric-ids', f'{sys_mnt}/', f'{preboot_os}/'], capture=False)

        print(f"[*] Copying AppOS cryptex to {preboot_app}...")
        run_cmd(['rsync', '-aH', '--numeric-ids', f'{app_mnt}/', f'{preboot_app}/'], capture=False)

        # 6. Hard-link dyld shared cache
        dsc_src = os.path.join(preboot_os, 'System/Library/Caches/com.apple.dyld')
        dsc_dst = os.path.join(target_mount, 'System/Library/Caches/com.apple.dyld')
        os.makedirs(dsc_dst, exist_ok=True)
        print(f"[*] Hard-linking dyld shared cache to {dsc_dst}...")
        if os.path.exists(dsc_src):
            for item in os.listdir(dsc_src):
                s = os.path.join(dsc_src, item)
                d = os.path.join(dsc_dst, item)
                if not os.path.exists(d):
                    os.link(s, d)

        # 7. Hard-link remaining cryptex files missing in root
        print("[*] Linking cryptex files missing in OS root...")
        for c_name, c_path in (('OS', preboot_os), ('App', preboot_app)):
            for root, dirs, files in os.walk(c_path):
                rel_dir = os.path.relpath(root, c_path)
                if rel_dir.startswith('System/Library/Caches/com.apple.dyld'):
                    continue
                for f in files:
                    s = os.path.join(root, f)
                    rel_f = os.path.relpath(s, c_path)
                    d = os.path.join(target_mount, rel_f)
                    if not os.path.exists(d) and not os.path.islink(d):
                        os.makedirs(os.path.dirname(d), exist_ok=True)
                        if os.path.islink(s):
                            link_target = os.readlink(s)
                            os.symlink(link_target, d)
                        else:
                            try:
                                os.link(s, d)
                            except OSError:
                                shutil.copy2(s, d)

        # 8. Setup logd directories and .migrated markers
        print("[*] Setting up logd diagnostics and .migrated markers...")
        db_dir = os.path.join(target_mount, 'private/var/db')
        diag_dir = os.path.join(db_dir, 'diagnostics')
        uuid_dir = os.path.join(db_dir, 'uuidtext')
        ts_dir = os.path.join(diag_dir, 'timesync')

        os.makedirs(diag_dir, exist_ok=True)
        os.chown(diag_dir, LOGD_UID, LOGD_UID)
        os.chmod(diag_dir, 0o751)

        os.makedirs(uuid_dir, exist_ok=True)
        os.chown(uuid_dir, LOGD_UID, LOGD_UID)
        os.chmod(uuid_dir, 0o755)

        os.makedirs(ts_dir, exist_ok=True)
        os.chown(ts_dir, LOGD_UID, LOGD_UID)
        os.chmod(ts_dir, 0o755)

        for d in (diag_dir, uuid_dir, ts_dir):
            marker = os.path.join(d, '.migrated')
            with open(marker, 'wb'):
                pass
            os.chown(marker, LOGD_UID, LOGD_UID)
            os.chmod(marker, 0o644)

        # 9. System keybag for AppleKeyStore (no passcode)
        print("[*] Installing system keybag...")
        kb_dir = os.path.join(target_mount, 'private/var/keybags')
        os.makedirs(kb_dir, exist_ok=True)
        os.chown(kb_dir, 0, 0)
        os.chmod(kb_dir, 0o700)
        kb_plist = b'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>\n'
        kb_file = os.path.join(kb_dir, 'systembag.kb')
        with open(kb_file, 'wb') as f:
            f.write(kb_plist)
        os.chown(kb_file, 0, 0)
        os.chmod(kb_file, 0o600)

        # 10. Run sweet-root-tweaks.py
        print("[*] Running sweet-root-tweaks.py...")
        tweaks_script = os.path.join(os.path.dirname(__file__), 'sweet-root-tweaks.py')
        run_cmd(['python3', tweaks_script, target_mount], capture=False)

        print("[+] Root creation and tweaks completed successfully!")

    finally:
        # Unmount target
        if target_mount and os.path.ismount(target_mount):
            print(f"[*] Unmounting {target_mount}...")
            subprocess.run(['umount', target_mount], check=False)
            try:
                os.rmdir(target_mount)
            except OSError:
                pass

        # Eject all attached disk devices
        for disk in reversed(attached_disks):
            detach_disk(disk)

    # Verify image integrity
    print(f"[*] Verifying HFS+ image {out_img}...")
    subprocess.run(['fsck_hfs', '-fy', out_img], check=False)
    print(f"[🎉] SUCCESS! iOS root image created: {out_img} ({os.path.getsize(out_img)} bytes)")


if __name__ == '__main__':
    main()
