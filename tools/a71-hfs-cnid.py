#!/usr/bin/env python3
"""Print the path of catalog node IDs on the A71 iOS root (read only), by walking every catalog leaf.

  a71-hfs-cnid.py ADB_EXE CNID [CNID...]
  a71-hfs-cnid.py --image IMAGE CNID [CNID...]
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
        v, want = hfsread.HFS(sys.argv[2]), sys.argv[3:]
    else:
        v, want = load('a71-hfs-get').RemoteHFS(sys.argv[1]), sys.argv[2:]
    want = set(map(int, want))
    ext = load('a71-hfs-scan').catalog_extents(v)
    ns = v.node_size
    i = struct.unpack('>I', v.fork_read(ext, 0, 512)[14 + 10:14 + 14])[0]
    names, kinds, threads = {}, {}, {}
    while i:
        d = v.fork_read(ext, i * ns, ns)
        for k in range(struct.unpack('>H', d[10:12])[0]):
            o = struct.unpack('>H', d[ns - 2 * (k + 1):ns - 2 * k])[0]
            kl, parent, name = v.key(d, o)
            rec = d[o + 2 + kl:o + 2 + kl + 520]
            rt = struct.unpack('>h', rec[:2])[0]
            if rt in (1, 2):
                c = struct.unpack('>I', rec[8:12])[0]
                names[c], kinds[c] = (parent, name), ('dir' if rt == 1 else 'file')
            elif rt in (3, 4) and parent in want:
                p = struct.unpack('>I', rec[4:8])[0]
                nl = struct.unpack('>H', rec[8:10])[0]
                threads[parent] = (p, rec[10:10 + 2 * nl].decode('utf-16-be', 'replace'))
        i = struct.unpack('>I', d[0:4])[0]

    def path(c):
        parts, n = [], 0
        while c in names and c != 2 and n < 80:
            c, nm = names[c]
            parts.append(nm)
            n += 1
        return '/' + '/'.join(reversed(parts))

    for c in sorted(want):
        t = threads.get(c)
        print(f'{c}: {kinds.get(c, "NO RECORD")} {path(c) if c in names else ""}'
              f'{"  thread -> parent %d %r" % t if t else "  (no thread record)"}')


if __name__ == '__main__':
    main()
