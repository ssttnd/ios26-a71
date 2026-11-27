#!/usr/bin/env python3
"""Compare files of an original HFS+ image with the phone's volume, extent by extent (read only).

  a71-hfs-filecmp.py ADB_EXE IMAGE LISTFILE [--out FILE]

LISTFILE holds one absolute path per line (lines not starting with '/' are ignored). For each path the
image's extents are checked against the phone's catalog record (same extents = file not relocated); then
every extent is hashed on the phone with dd and compared with the same blocks of the image.
Prints SAME, DIFF (with differing extents), MOVED (catalog extents differ) or MISSING per file.
"""
import argparse
import hashlib
import importlib.util
import os
import subprocess
import sys

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


def extents(v, info):
    ext = [(s, c) for s, c in info['ext'] if c]
    need = -(-info['size'] // v.bs)
    if sum(c for _, c in ext) < need:
        ext = [(s, c) for s, c in v.overflow_extents(info['cnid'], info['ext']) if c]
    out, left = [], need
    for s, c in ext:
        if left <= 0:
            break
        out.append((s, min(c, left)))
        left -= c
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('adb')
    ap.add_argument('image')
    ap.add_argument('listfile')
    ap.add_argument('--out')
    a = ap.parse_args()
    img = hfsread.HFS(a.image)
    phone = load('a71-hfs-get').RemoteHFS(a.adb)
    paths = [l.strip() for l in open(a.listfile, encoding='utf-8') if l.startswith('/')]
    jobs, results = [], {}
    for p in paths:
        ii, pi = img.info(p), phone.info(p)
        if not ii or ii['type'] != 'file':
            continue
        if not pi or pi['type'] != 'file':
            results[p] = 'MISSING'
            continue
        ie, pe = extents(img, ii), extents(phone, pi)
        if ie != pe or ii['size'] != pi['size']:
            results[p] = f'MOVED (image {ii["size"]} bytes {ie[:3]}, phone {pi["size"]} bytes {pe[:3]})'
            continue
        jobs.append((p, ie))
    script = ''.join(f'echo "{n} {k} $(dd if={TGT} bs={img.bs} skip={s} count={c} 2>/dev/null | sha256sum)"\n'
                     for n, (p, ie) in enumerate(jobs) for k, (s, c) in enumerate(ie))
    local = os.path.join(os.path.dirname(os.path.abspath(a.out or a.listfile)), 'filecmp-job.sh')
    with open(local, 'w', newline='\n') as f:
        f.write(script)
    if subprocess.run([a.adb, 'push', local, '/tmp/filecmp-job.sh'], capture_output=True, creationflags=NW).returncode:
        sys.exit('adb push failed')
    out = subprocess.run([a.adb, 'shell', 'sh /tmp/filecmp-job.sh; rm -f /tmp/filecmp-job.sh'],
                         capture_output=True, text=True, creationflags=NW).stdout
    got = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            got[(int(parts[0]), int(parts[1]))] = parts[2]
    for n, (p, ie) in enumerate(jobs):
        bad = []
        for k, (s, c) in enumerate(ie):
            img.f.seek(s * img.bs)
            if hashlib.sha256(img.f.read(c * img.bs)).hexdigest() != got.get((n, k)):
                bad.append((s, c))
        results[p] = 'SAME' if not bad else f'DIFF {len(bad)}/{len(ie)} extents {bad[:4]}'
    lines = [f'{r}\t{p}' for p, r in sorted(results.items())]
    if a.out:
        open(a.out, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    counts = {}
    for r in results.values():
        counts[r.split()[0]] = counts.get(r.split()[0], 0) + 1
    print(counts)
    for l in lines:
        if not l.startswith('SAME'):
            print(l)


if __name__ == '__main__':
    main()
