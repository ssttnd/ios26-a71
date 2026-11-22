#!/usr/bin/env python3
"""Add LC_LOAD_WEAK_DYLIB to a thin 64-bit Mach-O that has no slack after its load commands.

  a71-addweak.py IN OUT DYLIB_PATH

23G90 SpringBoard has 16 free bytes before __text, too few for a load command. This drops the
commands dyld does not use at run time (LC_SOURCE_VERSION, LC_FUNCTION_STARTS, LC_DATA_IN_CODE),
compacts the rest and appends a weak load of DYLIB_PATH: if the dylib is absent the binary starts
as before. The signature is invalid afterwards: re-sign ad hoc keeping identifier and entitlements.
"""
import struct
import sys

DROP = {0x2a: 'LC_SOURCE_VERSION', 0x26: 'LC_FUNCTION_STARTS', 0x29: 'LC_DATA_IN_CODE'}
LC_LOAD_WEAK_DYLIB = 0x80000018


def main():
    src, dst, dylib = sys.argv[1:4]
    d = bytearray(open(src, 'rb').read())
    magic, _, _, _, ncmds, sizeofcmds, _, _ = struct.unpack_from('<8I', d, 0)
    if magic != 0xfeedfacf:
        sys.exit('thin 64-bit Mach-O only')
    off, lowest, kept = 32, len(d), []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from('<II', d, off)
        body = bytes(d[off:off + size])
        if cmd == 0x19:
            for s in range(struct.unpack_from('<I', d, off + 64)[0]):
                so = struct.unpack_from('<I', d, off + 72 + s * 80 + 48)[0]
                if so:
                    lowest = min(lowest, so)
        if cmd in (0xc, LC_LOAD_WEAK_DYLIB) and dylib.encode() in body:
            sys.exit('already loads ' + dylib)
        if cmd in DROP:
            print('dropped', DROP[cmd])
        else:
            kept.append(body)
        off += size
    name = dylib.encode() + b'\0'
    size = (24 + len(name) + 7) & ~7
    lc = struct.pack('<IIIIII', LC_LOAD_WEAK_DYLIB, size, 24, 2, 0x10000, 0x10000) + name
    kept.append(lc + b'\0' * (size - len(lc)))
    blob = b''.join(kept)
    if 32 + len(blob) > lowest:
        sys.exit('still no room: %d bytes of commands, %d available' % (len(blob), lowest - 32))
    d[32:32 + sizeofcmds] = b'\0' * sizeofcmds
    d[32:32 + len(blob)] = blob
    struct.pack_into('<II', d, 16, len(kept), len(blob))
    open(dst, 'wb').write(d)
    print('%d commands, %d bytes, %d free; weak load %s' % (len(kept), len(blob), lowest - 32 - len(blob), dylib))


if __name__ == '__main__':
    main()
