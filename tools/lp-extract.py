#!/usr/bin/env python3
"""Extract one partition from a raw (unsparsed) Android dynamic-partition super image.

  lp-extract.py SUPER.raw              list partitions
  lp-extract.py SUPER.raw NAME OUT     write partition NAME to OUT

Reads the LP metadata (geometry at 4096, primary metadata at 8192) as in AOSP liblp's
metadata_format.h, version 10.x: header, partitions, extents, groups, block devices.
Only linear extents on block device 0 are supported (normal for a stock super image).
"""
import struct
import sys

GEOMETRY_MAGIC = 0x616c4467
HEADER_MAGIC = 0x414C5030
SECTOR = 512


def main():
    if len(sys.argv) not in (2, 4):
        sys.exit(__doc__)
    f = open(sys.argv[1], 'rb')
    f.seek(4096)
    g = f.read(52)
    magic, struct_size = struct.unpack('<II', g[:8])
    if magic != GEOMETRY_MAGIC:
        sys.exit(f'no LP geometry magic: {magic:#x}')
    metadata_max_size, slot_count, logical_block_size = struct.unpack('<III', g[40:52])
    f.seek(4096 + 4096 * 2)   # primary metadata slot 0 after reserved 4K + two geometry copies
    hdr = f.read(256)
    magic, major, minor, header_size = struct.unpack('<IHHI', hdr[:12])
    if magic != HEADER_MAGIC:
        sys.exit(f'no LP header magic: {magic:#x}')
    # magic, major, minor, header_size, header_checksum[32], tables_size, tables_checksum[32], then
    # table descriptors at 80: partitions, extents, groups, block_devices (offset, num_entries, entry_size)
    tables_size = struct.unpack('<I', hdr[44:48])[0]
    desc = [struct.unpack('<III', hdr[80 + i * 12:92 + i * 12]) for i in range(4)]
    f.seek(4096 + 4096 * 2 + header_size)
    tables = f.read(tables_size)
    p_off, p_num, p_size = desc[0]
    e_off, e_num, e_size = desc[1]
    extents = []
    for i in range(e_num):
        num_sectors, target_type, target_data, target_source = struct.unpack(
            '<QIQI', tables[e_off + i * e_size:e_off + i * e_size + 24])
        extents.append((num_sectors, target_type, target_data, target_source))
    parts = {}
    for i in range(p_num):
        e = tables[p_off + i * p_size:p_off + (i + 1) * p_size]
        name = e[:36].split(b'\0')[0].decode()
        attrs, first, num = struct.unpack('<III', e[36:48])
        parts[name] = extents[first:first + num]
    if len(sys.argv) == 2:
        for name, ex in parts.items():
            print(f'{name:24} {sum(n for n, *_ in ex) * SECTOR:>14} bytes, {len(ex)} extents')
        return
    name, out = sys.argv[2], sys.argv[3]
    if name not in parts:
        sys.exit(f'{name} not in {list(parts)}')
    with open(out, 'wb') as o:
        for num_sectors, ttype, tdata, src in parts[name]:
            if ttype != 0 or src != 0:
                sys.exit('only linear extents on device 0 are supported')
            f.seek(tdata * SECTOR)
            left = num_sectors * SECTOR
            while left:
                chunk = f.read(min(left, 1 << 24))
                o.write(chunk)
                left -= len(chunk)
    print(f'{name}: wrote {out}')


if __name__ == '__main__':
    main()
