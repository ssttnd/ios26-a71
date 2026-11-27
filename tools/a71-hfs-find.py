#!/usr/bin/env python3
"""Find catalog entries whose name contains TEXT on the A71 iOS root (read only, from TWRP).

  a71-hfs-find.py ADB_EXE TEXT [TEXT...]
  a71-hfs-find.py --image IMAGE TEXT [TEXT...]

Prints type, size (files) and full path of every match.
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
        v, texts = hfsread.HFS(sys.argv[2]), sys.argv[3:]
    else:
        v, texts = load('a71-hfs-get').RemoteHFS(sys.argv[1]), sys.argv[2:]
    ext = load('a71-hfs-scan').catalog_extents(v)
    ns = v.node_size
    i = struct.unpack('>I', v.fork_read(ext, 0, 512)[14 + 10:14 + 14])[0]
    names, hits = {}, []
    while i:
        d = v.fork_read(ext, i * ns, ns)
        for k in range(struct.unpack('>H', d[10:12])[0]):
            o = struct.unpack('>H', d[ns - 2 * (k + 1):ns - 2 * k])[0]
            kl, parent, name = v.key(d, o)
            rec = d[o + 2 + kl:o + 2 + kl + 248]
            rt = struct.unpack('>h', rec[:2])[0]
            if rt == 1:
                names[struct.unpack('>I', rec[8:12])[0]] = (parent, name)
            if rt in (1, 2) and any(t in name for t in texts):
                size = struct.unpack('>Q', rec[88:96])[0] if rt == 2 else 0
                hits.append(('dir' if rt == 1 else 'file', size, parent, name))
        i = struct.unpack('>I', d[0:4])[0]

    def path(parent, name):
        parts, n = [name], 0
        while parent in names and parent != 2 and n < 80:
            parent, nm = names[parent]
            parts.append(nm)
            n += 1
        return '/' + '/'.join(reversed(parts))
    for kind, size, parent, name in hits:
        print(f'{kind:4} {size:>12} {path(parent, name)}')


if __name__ == '__main__':
    main()
