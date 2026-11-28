"""Make the two userdata files that select the iOS 26 render canvas on the A71.

  a71-canvas-prefs.py MG_IN DISPLAY_IN OUTDIR WxH

MG_IN       the phone's com.apple.MobileGestalt.plist (protected cache, root 0644)
DISPLAY_IN  the phone's managed com.apple.iokit.IOMobileGraphicsFamily.plist
WxH         1080x2340 or 1125x2436 (always 3x; 828x1792 is the 2x original)

Writes OUTDIR/MobileGestalt.plist (MainScreenCanvasSizes = 2 x WxH as doubles, ArtworkDeviceScaleFactor 3)
and OUTDIR/IOMobileGraphicsFamily.plist (canvas_width/height). The main-screen-scale CacheData slot is set
separately by a71-mg-native-scale.py. The display preference takes effect one boot after it is installed.
"""
import plistlib
import struct
import sys
from pathlib import Path

CANVAS_KEY = 'ybGkijAwLTwevankfVzsDQ'      # MainScreenCanvasSizes
ARTWORK_KEY = 'oPeik/9e8lQWMszEjbPzng'     # ArtworkTraits
SIZES = {'828x1792': (828, 1792, 2), '1080x2340': (1080, 2340, 3), '1125x2436': (1125, 2436, 3)}


def main():
    if len(sys.argv) != 5 or sys.argv[4] not in SIZES:
        sys.exit(__doc__)
    mg_in, display_in, outdir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    width, height, scale = SIZES[sys.argv[4]]
    outdir.mkdir(parents=True, exist_ok=True)

    cache = plistlib.loads(mg_in.read_bytes())
    extra = cache['CacheExtra']
    old = struct.unpack('<4d', extra[CANVAS_KEY])
    assert old[:2] == old[2:] and old[:2] in {(w, h) for w, h, _ in SIZES.values()}, old
    extra[CANVAS_KEY] = struct.pack('<4d', width, height, width, height)
    extra[ARTWORK_KEY]['ArtworkDeviceScaleFactor'] = scale
    (outdir / 'MobileGestalt.plist').write_bytes(plistlib.dumps(cache, fmt=plistlib.FMT_BINARY, sort_keys=False))

    display = plistlib.loads(display_in.read_bytes())
    assert isinstance(display, dict)
    display.update(canvas_width=width, canvas_height=height)
    (outdir / 'IOMobileGraphicsFamily.plist').write_bytes(plistlib.dumps(display, fmt=plistlib.FMT_BINARY))
    print(f'canvas {old[0]:.0f}x{old[1]:.0f} -> {width}x{height} @{scale}x; display prefs {display}')


if __name__ == '__main__':
    main()
