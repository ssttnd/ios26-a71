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


def overflow_blocks(v):
    """{(forkType, cnid): [(fileStartBlock, [(start, count) x8]), ...]} from the extents overflow B-tree.
    Callers use only records with fileStartBlock < the fork's totalBlocks: records past the end are
    stale and allocate nothing (fsck_hfs ignores them too)."""
    ext = v.fork_extents(v.extfork)
    hdr = v.fork_read(ext, 0, 512)
    ns = struct.unpack('>H', hdr[14 + 18:14 + 20])[0]
    i = struct.unpack('>I', hdr[14 + 10:14 + 14])[0]
    out = {}
    while i:
        d = v.fork_read(ext, i * ns, ns)
        for k in range(struct.unpack('>H', d[10:12])[0]):
            o = struct.unpack('>H', d[ns - 2 * (k + 1):ns - 2 * k])[0]
            kl = struct.unpack('>H', d[o:o + 2])[0]
            key = (d[o + 2], struct.unpack('>I', d[o + 4:o + 8])[0])
            fstart = struct.unpack('>I', d[o + 8:o + 12])[0]
            r = o + 2 + kl
            pairs = [struct.unpack('>II', d[r + j * 8:r + j * 8 + 8]) for j in range(8)]
            out.setdefault(key, []).append((fstart, pairs))
        i = struct.unpack('>I', d[0:4])[0]
    for cnid in (3, 4, 6, 7, 8):   # special files: count every overflow record
        for _, pairs in out.get((0, cnid), []):
            EXTENTS.extend((s, c, cnid) for s, c in pairs if c)
    return out


def live_overflow(over, fork_type, cnid, total):
    pairs = [p for fstart, ps in over.get((fork_type, cnid), []) if fstart < total for p in ps]
    return [(s, c) for s, c in pairs if c]


EXTENTS = []    # (startBlock, blockCount, cnid) of every allocated extent seen


def cross_links(v, names_of):
    """Extents claimed by two files (or by a file and a B-tree / special file)."""
    for cnid, fork in ((3, v.extfork), (4, v.catfork)):
        EXTENTS.extend((s, c, cnid) for s, c in v.fork_extents(fork) if c)
    h = v.read(1024, 512)
    for cnid, off in ((6, 112), (7, 352), (8, 432)):   # allocation, attributes, startup files
        EXTENTS.extend((s, c, cnid) for s, c in v.fork_extents(h[off:off + 80]) if c)
    EXTENTS.sort()
    hits = []
    end, owner = -1, None
    for s, c, cnid in EXTENTS:
        if s < end and cnid != owner:
            hits.append((s, c, cnid, owner))
        if s + c > end:
            end, owner = s + c, cnid
    print(f'{len(EXTENTS)} extents, {len(hits)} overlapping, {v.total} blocks on the volume')
    for s, c, a, b in hits[:200]:
        print(f'overlap at block {s}+{c}: {names_of(a)} <-> {names_of(b)}')


def scan(v):
    over = overflow_blocks(v)
    ext = catalog_extents(v)
    hdr = v.fork_read(ext, 0, 512)
    first_leaf = struct.unpack('>I', hdr[14 + 10:14 + 14])[0]
    ns = v.node_size
    names = {}      # cnid -> (parent, name) for folders
    file_names = {}
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
                file_names[cnid] = (parent, name)
                mode = struct.unpack('>H', rec[42:44])[0]
                for fork_name, off in (('data', 88), ('rsrc', 168)):
                    EXTENTS.extend((s, c, cnid) for s, c in v.fork_extents(rec[off:off + 80]) if c)
                    size = struct.unpack('>Q', rec[off:off + 8])[0]
                    blocks = struct.unpack('>I', rec[off + 12:off + 16])[0]
                    need = -(-size // v.bs)
                    if need > blocks:
                        bad.append((parent, name, cnid, fork_name, size, blocks, need, 'size>blocks'))
                    mapped = sum(struct.unpack('>I', rec[off + 20 + j * 8:off + 24 + j * 8])[0] for j in range(8))
                    extra = live_overflow(over, 0 if fork_name == 'data' else 0xff, cnid, blocks)
                    EXTENTS.extend((s, c, cnid) for s, c in extra)
                    mapped += sum(c for _, c in extra)
                    if mapped != blocks:
                        bad.append((parent, name, cnid, fork_name, size, blocks, mapped,
                                    'extents map %d blocks (not an open error, but a damaged or unreplayed record)' % mapped))
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
    special = {3: '[extents B-tree]', 4: '[catalog B-tree]', 6: '[allocation file]', 7: '[attributes B-tree]',
               8: '[startup file]'}
    cross_links(v, lambda c: special.get(c) or (path(*file_names[c]) if c in file_names else f'cnid {c}'))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    scan(open_volume(sys.argv[1:]))


if __name__ == '__main__':
    main()
