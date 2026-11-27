#!/usr/bin/env python3
"""Print the records of one catalog B-tree node of the A71 iOS root (read only), with folder paths.

  a71-hfs-node.py ADB_EXE NODE [NODE...]
  a71-hfs-node.py --image IMAGE NODE [NODE...]

Marks keys that are not in ascending order (what fsck_hfs reports as "Keys out of order (4, NODE)").
"""
import importlib.util
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hfsread


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace('-', '_'), os.path.join(os.path.dirname(os.path.abspath(__file__)), name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    if sys.argv[1] == '--image':
        v, nodes = hfsread.HFS(sys.argv[2]), sys.argv[3:]
    else:
        v, nodes = load('a71-hfs-get').RemoteHFS(sys.argv[1]), sys.argv[2:]
    scan = load('a71-hfs-scan')
    ext = scan.catalog_extents(v)
    ns = v.node_size
    for n in map(int, nodes):
        d = v.fork_read(ext, n * ns, ns)
        flink, blink = struct.unpack('>II', d[0:8])
        kind, height = struct.unpack('>bB', d[8:10])
        cnt = struct.unpack('>H', d[10:12])[0]
        print(f'node {n}: kind {kind} height {height} records {cnt} fLink {flink} bLink {blink}')
        prev = None
        for k in range(cnt):
            o = struct.unpack('>H', d[ns - 2 * (k + 1):ns - 2 * k])[0]
            kl, parent, name = v.key(d, o)
            rec = d[o + 2 + kl:o + 2 + kl + 16]
            rt = struct.unpack('>h', rec[:2])[0] if kind == -1 else None
            cur = (parent, name.encode('utf-16-be'))
            mark = '  <-- OUT OF ORDER' if prev is not None and cur <= prev else ''
            info = ''
            if kind == -1 and rt in (1, 2):
                info = f' {"dir" if rt == 1 else "file"} cnid {struct.unpack(">I", rec[8:12])[0]}'
            elif kind == -1 and rt in (3, 4):
                info = f' thread'
            elif kind == 0:
                info = f' -> child {struct.unpack(">I", d[o + 2 + kl:o + 6 + kl])[0]}'
            print(f'  [{k}] parent {parent} {name!r}{info}{mark}')
            prev = cur


if __name__ == '__main__':
    main()
