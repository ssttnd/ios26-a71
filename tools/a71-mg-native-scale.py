"""Set MobileGestalt's cached main-screen-scale in the A71's protected cache.

The cache is installed root 0644 so MobileGestaltHelper cannot drop our CacheExtra overrides. It also keeps
the screen scale in CacheData from the first 828x1792 @2x boots, so a 1080x2340 @3x device tree still ran
as 540x1170 @2x (FrontBoard display mode).

A CacheExtra entry for main-screen-scale does NOT work: on 2026-11-28 a real 3.0 there gave SpringBoard
`infxinf@0x` and a crash loop. CacheData is a table of 8-byte slots; in the 23G90 cache the scale is the
only 2.0 (float32 in the low half of its slot), right after main-screen-pitch 458. This tool rewrites that
slot only, after checking both neighbours.

  a71-mg-native-scale.py IN.plist OUT.plist [SCALE]    (SCALE 3 default, or 2)
"""
import plistlib
import struct
import sys
from pathlib import Path

PITCH = 458


def main():
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    scale = float(sys.argv[3]) if len(sys.argv) == 4 else 3.0
    if scale not in (2.0, 3.0):
        sys.exit('scale must be 2 or 3')
    cache = plistlib.loads(source.read_bytes())
    data = bytearray(cache['CacheData'])
    slots = [i for i in range(8, len(data) - 7, 8)
             if struct.unpack_from('<Q', data, i - 8)[0] == PITCH
             and struct.unpack_from('<f', data, i)[0] in (2.0, 3.0)
             and struct.unpack_from('<I', data, i + 4)[0] == 0]
    if len(slots) != 1:
        sys.exit(f'expected one scale slot after pitch {PITCH}, found {slots}')
    slot = slots[0]
    old = struct.unpack_from('<f', data, slot)[0]
    struct.pack_into('<f', data, slot, scale)
    cache['CacheData'] = bytes(data)
    output.write_bytes(plistlib.dumps(cache, fmt=plistlib.FMT_BINARY, sort_keys=False))
    check = plistlib.loads(output.read_bytes())
    assert check['CacheExtra'] == cache['CacheExtra'] and len(check['CacheData']) == len(data)
    print(f'CacheData slot {slot // 8} (byte {slot}): main-screen-scale {old} -> {scale}, '
          f'{output.stat().st_size} bytes')


if __name__ == '__main__':
    main()
