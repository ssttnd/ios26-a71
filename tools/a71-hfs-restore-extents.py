#!/usr/bin/env python3
"""Restore files of the original HFS+ image onto the phone's volume by rewriting their own extents.

  a71-hfs-restore-extents.py ADB_EXE IMAGE PATH [PATH...] [--write]

Only for files whose extents and size on the phone equal those in the image (not relocated). For each
extent: copy the image's blocks to /tmp in TWRP, dd them to the same blocks of userdata, read back and
compare SHA-256. Without --write it only prints what it would do.
"""
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hfsread

TGT = '/dev/block/by-name/userdata'
NW = 0x08000000 if os.name == 'nt' else 0


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace('-', '_'), os.path.join(os.path.dirname(os.path.abspath(__file__)), name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    args = [x for x in sys.argv[1:] if x != '--write']
    write = '--write' in sys.argv
    if len(args) < 3:
        sys.exit(__doc__)
    adb, image, paths = args[0], args[1], args[2:]
    cmp = load('a71-hfs-filecmp')
    img = hfsread.HFS(image)
    phone = load('a71-hfs-get').RemoteHFS(adb)
    run = lambda *a: subprocess.run([adb, *a], capture_output=True, text=True, creationflags=NW)
    plan = []
    for p in paths:
        ii, pi = img.info(p), phone.info(p)
        if not ii or not pi or ii['type'] != 'file' or pi['type'] != 'file':
            sys.exit(f'{p}: missing')
        ie, pe = cmp.extents(img, ii), cmp.extents(phone, pi)
        if ie != pe or ii['size'] != pi['size']:
            sys.exit(f'{p}: relocated or resized on the phone, refusing')
        plan.append((p, ie))
        print(f'{p}: {ii["size"]} bytes, extents {ie}')
    if not write:
        print('dry run: nothing written')
        return
    tmpdir = tempfile.mkdtemp()
    for p, ie in plan:
        for s, c in ie:
            img.f.seek(s * img.bs)
            data = img.f.read(c * img.bs)
            want = hashlib.sha256(data).hexdigest()
            local = os.path.join(tmpdir, 'extent.bin')
            open(local, 'wb').write(data)
            if run('push', local, '/tmp/extent.bin').returncode:
                sys.exit('adb push failed')
            run('shell', f'dd if=/tmp/extent.bin of={TGT} bs={img.bs} seek={s} count={c} conv=notrunc,fsync 2>/dev/null; rm -f /tmp/extent.bin; sync')
            back = run('shell', f'dd if={TGT} bs={img.bs} skip={s} count={c} 2>/dev/null | sha256sum').stdout.split()[0]
            print(f'{p} extent {s}+{c}: {"VERIFY OK" if back == want else "VERIFY FAILED " + back}', flush=True)
            if back != want:
                sys.exit(1)
    os.remove(os.path.join(tmpdir, 'extent.bin'))
    os.rmdir(tmpdir)


if __name__ == '__main__':
    main()
