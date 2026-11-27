#!/usr/bin/env python3
"""Find which files of an original HFS+ image differ on the phone's volume (read only).

  a71-hfs-diffmap.py ADB_EXE IMAGE [--chunk-mib 4] [--prefix /System] [--out FILE]

Hashes every chunk of the volume on the phone (one adb shell loop) and in IMAGE, then maps the differing
chunks to the files of IMAGE whose extents touch them. Files are listed with the number of differing
blocks inside their own extents (compared block by block for the chunks that differ).
"""
import argparse
import hashlib
import importlib.util
import os
import struct
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


def file_extents(v):
    """[(start, count, path)] for every data/rsrc fork extent in the image (incl. live overflow)."""
    scan = load('a71-hfs-scan')
    over = scan.overflow_blocks(v)
    ext = scan.catalog_extents(v)
    ns = v.node_size
    i = struct.unpack('>I', v.fork_read(ext, 0, 512)[14 + 10:14 + 14])[0]
    names, files = {}, []
    while i:
        d = v.fork_read(ext, i * ns, ns)
        for k in range(struct.unpack('>H', d[10:12])[0]):
            o = struct.unpack('>H', d[ns - 2 * (k + 1):ns - 2 * k])[0]
            kl, parent, name = v.key(d, o)
            rec = d[o + 2 + kl:o + 2 + kl + 248]
            rt = struct.unpack('>h', rec[:2])[0]
            if rt == 1:
                names[struct.unpack('>I', rec[8:12])[0]] = (parent, name)
            elif rt == 2:
                cnid = struct.unpack('>I', rec[8:12])[0]
                for ft, off in ((0, 88), (0xff, 168)):
                    total = struct.unpack('>I', rec[off + 12:off + 16])[0]
                    pairs = [(s, c) for s, c in v.fork_extents(rec[off:off + 80]) if c]
                    pairs += scan.live_overflow(over, ft, cnid, total)
                    files.append((parent, name, pairs))
        i = struct.unpack('>I', d[0:4])[0]

    def path(parent, name):
        parts, n = [name], 0
        while parent in names and parent != 2 and n < 80:
            parent, nm = names[parent]
            parts.append(nm)
            n += 1
        return '/' + '/'.join(reversed(parts))
    out = []
    for parent, name, pairs in files:
        p = path(parent, name)
        out.extend((s, c, p) for s, c in pairs)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('adb')
    ap.add_argument('image')
    ap.add_argument('--chunk-mib', type=int, default=4)
    ap.add_argument('--prefix', default='')
    ap.add_argument('--out')
    ap.add_argument('--chunks-from', help='reuse the "chunks" line of an earlier --out file instead of hashing')
    a = ap.parse_args()
    v = hfsread.HFS(a.image)
    size = v.total * v.bs
    chunk = a.chunk_mib << 20
    n = size // chunk
    print(f'volume {size} bytes, {n} chunks of {a.chunk_mib} MiB', flush=True)
    if a.chunks_from:
        first = open(a.chunks_from, encoding='utf-8').readline().split()
        report(v, a, chunk, [int(x) for x in first[1:]])
        return
    cmd = (f'i=0; while [ $i -lt {n} ]; do echo "$i $(dd if={TGT} bs={chunk} skip=$i count=1 2>/dev/null | sha256sum)"; '
           f'i=$((i+1)); done')
    phone = {}
    proc = subprocess.Popen([a.adb, 'shell', cmd], stdout=subprocess.PIPE, text=True, creationflags=NW)
    for line in proc.stdout:
        parts = line.split()
        if len(parts) >= 2:
            phone[int(parts[0])] = parts[1]
    proc.wait()
    if len(phone) != n:
        sys.exit(f'phone returned {len(phone)} of {n} chunk hashes')
    diff = []
    with open(a.image, 'rb') as f:
        for i in range(n):
            if hashlib.sha256(f.read(chunk)).hexdigest() != phone[i]:
                diff.append(i)
    print(f'{len(diff)} chunks differ', flush=True)
    report(v, a, chunk, diff)


def report(v, a, chunk, diff):
    bpc = chunk // v.bs
    dchunks = set(diff)
    hits = {}
    for s, c, p in file_extents(v):
        if a.prefix and not p.startswith(a.prefix):
            continue
        for ch in range(s // bpc, (s + c - 1) // bpc + 1):
            if ch in dchunks:
                hits.setdefault(p, []).append((s, c))
                break
    lines = [f'{p}' for p in sorted(hits)]
    print(f'{len(hits)} image files{" under " + a.prefix if a.prefix else ""} touch differing chunks')
    if a.out:
        with open(a.out, 'w', encoding='utf-8') as o:
            o.write('chunks ' + ' '.join(map(str, diff)) + '\n')
            o.write('\n'.join(lines) + '\n')
    for p in lines[:200]:
        print(p)


if __name__ == '__main__':
    main()
