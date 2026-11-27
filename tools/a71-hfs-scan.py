#!/usr/bin/env python3
"""Find HFS+ catalog file records that the A71 kernel rejects in hfs_getnewvnode (SWEET HFSINC at
hfs_cnode.c:946): a fork whose logicalSize needs more allocation blocks than its totalBlocks, or a
symlink longer than MAXPATHLEN. Such files fail every open with EINVAL and mark the volume inconsistent.

  a71-hfs-scan.py ADB_EXE              scan the iOS root on userdata from TWRP (read only)
  a71-hfs-scan.py --image IMAGE        scan a raw HFS+ image file

Prints one line per bad record: path, cnid, fork, logicalSize, totalBlocks, blocks needed.
The journal is not replayed (tools/hfsread.py), so the result reflects the last checkpoint.
"""
import importlib.util
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hfsread

S_IFMT, S_IFLNK = 0o170000, 0o120000
MAXPATHLEN = 1024


def open_volume(argv):
    if argv[:1] == ['--image']:
        return hfsread.HFS(argv[1])
    spec = importlib.util.spec_from_file_location(
        'a71_hfs_get', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'a71-hfs-get.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RemoteHFS(argv[0])


def catalog_extents(v):
    ext = v.cat_ext
    total = struct.unpack('>I', v.catfork[12:16])[0]
    if sum(c for _, c in ext) < total:
        ext = v.overflow_extents(4, ext)
    return ext


def scan(v):
    ext = catalog_extents(v)
    hdr = v.fork_read(ext, 0, 512)
    first_leaf = struct.unpack('>I', hdr[14 + 10:14 + 14])[0]
    ns = v.node_size
    names = {}      # cnid -> (parent, name) for folders
    bad = []
    files = 0
    i = first_leaf
    while i:
        d = v.fork_read(ext, i * ns, ns)
        cnt = struct.unpack('>H', d[10:12])[0]
        for k in range(cnt):
            o = struct.unpack('>H', d[ns - 2 * (k + 1):ns - 2 * k])[0]
            kl, parent, name = v.key(d, o)
            rec = d[o + 2 + kl:o + 2 + kl + 248]
            rt = struct.unpack('>h', rec[:2])[0]
            if rt == 1:
                names[struct.unpack('>I', rec[8:12])[0]] = (parent, name)
            elif rt == 2:
                files += 1
                cnid = struct.unpack('>I', rec[8:12])[0]
                mode = struct.unpack('>H', rec[42:44])[0]
                for fork_name, off in (('data', 88), ('rsrc', 168)):
                    size = struct.unpack('>Q', rec[off:off + 8])[0]
                    blocks = struct.unpack('>I', rec[off + 12:off + 16])[0]
                    need = -(-size // v.bs)
                    if need > blocks:
                        bad.append((parent, name, cnid, fork_name, size, blocks, need, 'size>blocks'))
                if mode & S_IFMT == S_IFLNK and struct.unpack('>Q', rec[88:96])[0] > MAXPATHLEN:
                    bad.append((parent, name, cnid, 'data', struct.unpack('>Q', rec[88:96])[0], 0, 0, 'long symlink'))
        i = struct.unpack('>I', d[0:4])[0]

    def path(parent, name):
        parts = [name]
        seen = 0
        while parent in names and parent != 2 and seen < 64:
            parent, n = names[parent]
            parts.append(n)
            seen += 1
        return '/' + '/'.join(reversed(parts))

    print(f'{files} file records, {len(bad)} bad')
    for parent, name, cnid, fork_name, size, blocks, need, why in bad:
        print(f'{path(parent, name)}\tcnid={cnid}\t{fork_name}\tsize={size}\tblocks={blocks}\tneed={need}\t{why}')


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    scan(open_volume(sys.argv[1:]))


if __name__ == '__main__':
    main()
