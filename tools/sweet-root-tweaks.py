#!/usr/bin/env python3
"""Apply the SWEET bring-up changes to an iOS root made by tools/mkiosroot.sh.

  sudo sweet-root-tweaks.py MOUNTED_ROOT

MOUNTED_ROOT is the HFS+ image mounted read-write (Linux: run
`fsck.hfsplus -fy` on the image, then `mount -t hfsplus -o loop,force`).
Run as root (it writes root/mobile owned files). Idempotent. This is what
turned the plain mkiosroot.sh output into the images that reach the home
screen (image versions v8-v14 in NOTES.md):

  launchd.plist   _PanicOnCrash -> _PanicOnCrasX (a crashing daemon must not
                  panic the system); CommCenter jobs removed (no baseband: it
                  crash-loops and Setup blocks on its CoreTelephony XPC)
  containers      /private/var/containers/{Bundle,Data/System,Shared/SystemGroup,Temp}
                  (on iOS they live on the data volume)
  migration       LastSystemVersion so DataMigration does not run for an hour
                  on every boot
  audio           VirtualAudio HAL plug-in disabled (mediaserverd crash)
  MediaToolbox    StartRecorderServer=false (camera filter prewarm calls a
                  NULL OpenGL function without a GPU -> mediaserverd crash loop)
  SpringBoard     BKNoWatchdogs (one slow CPU path, no scene-create watchdog
                  kills), no cloud-configuration UI
  Setup           skipped: SetupDone, SetupFinishedAllSteps, SetupVersion 11,
                  mini-buddy flags off
  activation      mobileactivationd data ark seeded; the actual Activated state
                  comes from its Hactivation branch, selected by the /chosen
                  security-status properties in tools/mkadt.py
"""
import glob, os, plistlib, shutil, subprocess, sys

BUILD, VERSION = '20G81', '16.6.1'
MOBILE = 501


PLATFORM_UUID = 'A9683613-3704-53F2-95D0-98A8FB574E78'
ACTIVATION_CONTAINER_UUID = 'D90C94C4-F94E-4FCF-8A28-A93BE3846D8E'


def load(path):
    with open(path, 'rb') as f:
        return plistlib.load(f)


def save(path, data, uid, gid, mode, fmt=plistlib.FMT_BINARY):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        plistlib.dump(data, f, fmt=fmt)
    os.chown(path, uid, gid)
    os.chmod(path, mode)


def merge_pref(root, name, values):
    """Merge keys into /var/mobile/Library/Preferences/NAME.plist (mobile, 0600)."""
    path = os.path.join(root, 'private/var/mobile/Library/Preferences', name + '.plist')
    data = load(path) if os.path.exists(path) else {}
    data.update(values)
    save(path, data, MOBILE, MOBILE, 0o600)
    print('pref', name, sorted(values))


def byhost_pref(root, name, values):
    """Write ByHost preference plists for both upper and lower case platform UUID."""
    byhost_dir = os.path.join(root, 'private/var/mobile/Library/Preferences/ByHost')
    os.makedirs(byhost_dir, exist_ok=True)
    os.chown(byhost_dir, MOBILE, MOBILE)
    os.chmod(byhost_dir, 0o755)
    for uuid_str in (PLATFORM_UUID, PLATFORM_UUID.lower()):
        p = os.path.join(byhost_dir, f'{name}.{uuid_str}.plist')
        save(p, values, MOBILE, MOBILE, 0o600)
        print('byhost pref', os.path.basename(p))


def launchd(root):
    path = os.path.join(root, 'System/Library/xpc/launchd.plist')
    st = os.stat(path)
    plist = load(path)
    jobs = plist['LaunchDaemons']
    renamed = 0
    for job in jobs.values():
        if '_PanicOnCrash' in job:
            job['_PanicOnCrasX'] = job.pop('_PanicOnCrash')
            renamed += 1
    removed = [k for k, j in jobs.items() if j.get('Label') == 'com.apple.CommCenter']
    for k in removed:
        del jobs[k]
    save(path, plist, st.st_uid, st.st_gid, st.st_mode & 0o7777)
    print(f'launchd.plist: {renamed} _PanicOnCrash renamed, {len(removed)} CommCenter jobs removed')


def containers(root):
    base = os.path.join(root, 'private/var/containers')
    for sub, uid in (('Bundle', 33), ('Data/System', 0), ('Shared/SystemGroup', 0), ('Temp', 0)):
        d = os.path.join(base, sub)
        if not os.path.isdir(d):
            os.makedirs(d)
            os.chown(d, uid, uid)
            os.chmod(d, 0o755)
            print('mkdir', d)


def find_container(root, kind, identifier):
    for meta in glob.glob(os.path.join(root, 'private/var/containers', kind, '*',
                                       '.com.apple.mobile_container_manager.metadata.plist')):
        if load(meta).get('MCMMetadataIdentifier') == identifier:
            return os.path.dirname(meta)
    return None


def activation(root):
    c = find_container(root, 'Data/System', 'com.apple.mobileactivationd')
    if c is None:
        c = os.path.join(root, 'private/var/containers/Data/System', ACTIVATION_CONTAINER_UUID)
        os.makedirs(c, exist_ok=True)
        os.chown(c, 0, 0)
        os.chmod(c, 0o755)
        meta_file = os.path.join(c, '.com.apple.mobile_container_manager.metadata.plist')
        save(meta_file, {
            'MCMMetadataIdentifier': 'com.apple.mobileactivationd',
            'MCMMetadataContainerClass': 13,
            'MCMMetadataSchemaVersion': 1,
        }, 0, 0, 0o644)
        print('created mobileactivationd container', c)

    d = os.path.join(c, 'Library/internal')
    os.makedirs(d, exist_ok=True)
    os.chown(d, MOBILE, MOBILE)
    os.chmod(d, 0o755)
    save(os.path.join(d, 'data_ark.plist'), {
        '-ActivationState': 'Activated', '-BrickState': False,
        '-BuildVersion': BUILD, '-ProductVersion': VERSION,
        '-DataMigrationCompleted': True, '-PreSydroDataMigrationCompleted': True,
    }, MOBILE, MOBILE, 0o600)
    print('data ark', d)


def audio(root):
    src = os.path.join(root, 'Library/Audio/Plug-Ins/HAL/VirtualAudio.plugin')
    dst_dir = os.path.join(root, 'Library/Audio/Plug-Ins/HAL.disabled')
    if os.path.exists(src):
        os.makedirs(dst_dir, exist_ok=True)
        shutil.move(src, dst_dir)
        print('VirtualAudio.plugin disabled')
    for conf in glob.glob(os.path.join(root, 'System/Library/Frameworks/MediaToolbox.framework/*/SubServerConfiguration.plist')):
        st = os.stat(conf)
        data = load(conf)
        data['StartRecorderServer'] = False
        save(conf, data, st.st_uid, st.st_gid, st.st_mode & 0o7777, plistlib.FMT_XML)
        print('StartRecorderServer off', os.path.relpath(conf, root))


def springboard_assets(root):
    sb_dir = os.path.join(root, 'private/var/mobile/Library/SpringBoard')
    os.makedirs(sb_dir, exist_ok=True)
    os.chown(sb_dir, MOBILE, MOBILE)
    os.chmod(sb_dir, 0o755)

    # 1. Icons layout: IconState.plist and DesiredIconState.plist
    default_icon_plist = os.path.join(root, 'System/Library/CoreServices/SpringBoard.app/DefaultIconState~iphone.plist')
    if not os.path.exists(default_icon_plist):
        default_icon_plist = os.path.join(root, 'System/Library/CoreServices/SpringBoard.app/DefaultIconState.plist')

    if os.path.exists(default_icon_plist):
        icon_data = load(default_icon_plist)
        for name in ('IconState.plist', 'DesiredIconState.plist'):
            dst = os.path.join(sb_dir, name)
            save(dst, icon_data, MOBILE, MOBILE, 0o600)
            print('springboard icon state:', dst)

    # 2. Official iOS 16 Wallpaper
    wallpaper_src = '/private/tmp/ios16_wallpaper.jpg'
    if os.path.exists(wallpaper_src):
        try:
            from PIL import Image
            import struct
            im = Image.open(wallpaper_src).convert('RGBA')
            w, h = im.size

            # Save thumbnails
            for name in ('HomeBackgroundThumbnail.jpg', 'LockBackgroundThumbnail.jpg'):
                dst = os.path.join(sb_dir, name)
                shutil.copy2(wallpaper_src, dst)
                os.chown(dst, MOBILE, MOBILE)
                os.chmod(dst, 0o644)
                print('wallpaper thumb:', dst)

            # Generate cpbitmap with 24-byte trailer
            r, g, b, a = im.split()
            bgra = Image.merge('RGBA', (b, g, r, a))
            raw = bgra.tobytes()
            trailer = struct.pack('<6i', 1, w, h, 0, 0, 0)
            cpbitmap_data = raw + trailer

            for name in ('HomeBackground.cpbitmap', 'LockBackground.cpbitmap',
                         'OriginalHomeBackground.cpbitmap', 'OriginalLockBackground.cpbitmap'):
                dst = os.path.join(sb_dir, name)
                with open(dst, 'wb') as f:
                    f.write(cpbitmap_data)
                os.chown(dst, MOBILE, MOBILE)
                os.chmod(dst, 0o644)
                print('wallpaper cpbitmap:', dst)
        except Exception as e:
            print('Warning: could not generate wallpaper cpbitmap:', e)


def main():
    global BUILD, VERSION
    if len(sys.argv) != 2 or not os.path.isdir(os.path.join(sys.argv[1], 'System/Library/xpc')):
        sys.exit(__doc__)
    root = sys.argv[1]
    sys_ver_path = os.path.join(root, 'System/Library/CoreServices/SystemVersion.plist')
    if os.path.exists(sys_ver_path):
        ver_info = load(sys_ver_path)
        BUILD = ver_info.get('ProductBuildVersion', BUILD)
        VERSION = ver_info.get('ProductVersion', VERSION)
        print(f'Detected OS target: iOS {VERSION} (Build {BUILD})')
    launchd(root)
    containers(root)
    activation(root)
    audio(root)
    springboard_assets(root)
    merge_pref(root, 'com.apple.migration', {
        'LastSystemVersion': BUILD,
        'DMUserDataDisposition': {'SyntheticDidUpgrade': False, 'buildVersion': BUILD}})
    merge_pref(root, 'com.apple.DataMigration', {
        'LastSystemVersion': BUILD})
    byhost_pref(root, 'com.apple.migration', {
        'LastSystemVersion': BUILD})
    merge_pref(root, 'com.apple.springboard', {
        'BKNoWatchdogs': True,
        'FBLaunchWatchdogExceptions': {'com.apple.purplebuddy': 100.0},
        'MCForceShowCloudConfigurationUI': False,
        'SBShowNonDefaultSystemApps': True,
        'SBShowInternalApps': True})
    merge_pref(root, 'com.apple.purplebuddy', {
        'SetupDone': True, 'SetupFinishedAllSteps': True, 'SetupVersion': 11,
        'daemonizeNeedsToRun': False})
    merge_pref(root, 'com.apple.purplebuddy.notbackedup', {
        k: False for k in ('ShouldRunDiagnosticsMiniBuddy', 'ShouldRunHSA2MiniBuddy',
                           'ShouldRunKeychainSyncMiniBuddy', 'ShouldRunMesaMiniBuddy',
                           'ShouldRunPaymentMiniBuddy', 'ShouldRunStandardMiniBuddy',
                           'SilentICDPUpgrade')})
    merge_pref(root, 'com.apple.managedconfiguration.notbackedup', {
        'LockdownActivationIndicatesCloudConfigurationAvailable': False})


if __name__ == '__main__':
    main()
