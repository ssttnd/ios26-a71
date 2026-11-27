#!/usr/bin/env python3
"""Print the HFS+ journal state of the iOS root on the A71's userdata, from TWRP (read only).

  a71-hfs-journal.py ADB_EXE
  a71-hfs-journal.py --image IMAGE

start == end means the journal is empty: the on-disk B-trees are current and tools/hfsread.py reads
them correctly. start != end means transactions are not yet replayed into the B-trees.
"""
import importlib.util
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hfsread


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == '--image':
        v = hfsread.HFS(sys.argv[2])
    else:
        spec = importlib.util.spec_from_file_location(
            'a71_hfs_get', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'a71-hfs-get.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        v = mod.RemoteHFS(sys.argv[1])
    h = v.read(1024, 512)
    attrs = struct.unpack('>I', h[4:8])[0]
    jib = struct.unpack('>I', h[12:16])[0]
    # hfs_format.h: bit 8 unmounted cleanly, 11 boot volume inconsistent, 13 journaled,
    # 14 volume inconsistent (hfs_mark_inconsistent), 31 unused node fix
    print(f'attributes 0x{attrs:08x} journaled={bool(attrs & 0x2000)} unmounted={bool(attrs & 0x100)} '
          f'inconsistent={bool(attrs & 0x4000)} boot_inconsistent={bool(attrs & 0x800)} '
          f'journal_info_block={jib} block_size={v.bs}')
    if not attrs & 0x2000:
        return
    info = v.read(jib * v.bs, 52)
    flags = struct.unpack('>I', info[0:4])[0]
    offset, size = struct.unpack('>QQ', info[36:52])
    print(f'journal info flags 0x{flags:x} offset {offset} size {size}')
    jh = v.read(offset, 44)
    magic = struct.unpack('<I', jh[0:4])[0]
    endian = '<' if magic == 0x4A4E4C78 else '>'
    magic, endian_tag, start, end, jsize, blhdr, cksum, jhdr = struct.unpack(endian + 'IIQQQIII', jh[:44])
    print(f'journal header magic 0x{magic:08x} start {start} end {end} size {jsize} '
          f'{"EMPTY" if start == end else "HAS UNREPLAYED TRANSACTIONS (%d bytes)" % ((end - start) % jsize)}')


if __name__ == '__main__':
    main()
