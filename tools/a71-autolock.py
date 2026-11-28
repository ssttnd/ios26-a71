"""Set iOS Auto-Lock (managed setting maxInactivity) in the A71's user configuration profiles.

  a71-autolock.py USER_IN EFFECTIVE_IN OUTDIR [SECONDS|never]

Reads the phone's /private/var/mobile/Library/UserConfigurationProfiles/{UserSettings,EffectiveUserSettings}.plist
(copied with a71-hfs-get.py) and writes both with restrictedValue.maxInactivity.value set. "never" is
2147483647, what Settings stores for Never. Install with a71-payload.py (file:...@644).
"""
import plistlib
import sys
from pathlib import Path

NEVER = 2147483647


def main():
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    user_in, eff_in, outdir = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    arg = sys.argv[4] if len(sys.argv) == 5 else 'never'
    value = NEVER if arg == 'never' else int(arg)
    outdir.mkdir(parents=True, exist_ok=True)
    for src in (user_in, eff_in):
        d = plistlib.loads(src.read_bytes())
        entry = d.setdefault('restrictedValue', {}).setdefault('maxInactivity', {})
        old = entry.get('value')
        entry['value'] = value
        (outdir / src.name).write_bytes(plistlib.dumps(d, fmt=plistlib.FMT_XML if src.read_bytes().startswith(b'<?xml') else plistlib.FMT_BINARY))
        print(f'{src.name}: maxInactivity {old} -> {value}')


if __name__ == '__main__':
    main()
