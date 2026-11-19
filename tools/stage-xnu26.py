#!/usr/bin/env python3
"""Stage the pinned donor series and A71 patches in darwin-xnu-build."""

import argparse
import re
from hashlib import sha256
from pathlib import Path


def stage(builder, donor, adreno_donor=None):
    xnu = Path(__file__).resolve().parents[1] / 'xnu'
    patches = builder / 'patches' / '26.0'
    staged = []
    donor_series = donor / 'xnu' / 'patches-12377'
    if not donor_series.is_dir() or not patches.is_dir():
        raise SystemExit('expected Bergamota and darwin-xnu-build checkouts')

    file = builder / 'build.sh'
    source = file.read_text(encoding='utf-8')
    firehose = 'ARCHS="x86_64 arm64e" VALID_ARCHS="x86_64 arm64e"'
    rejected = '                warning "Skipping patch ${PATCH}'
    if source.count(firehose) != 1 or source.count(rejected) != 1:
        raise SystemExit('unexpected darwin-xnu-build layout, use the pinned revision')
    guard = (
        '                case "${PATCH##*/}" in\n'
        '                    sweet-*) printf "Required project patch rejected: %s\\n%s\\n" '
        '"$PATCH" "$APPLY_CHECK" >&2; exit 1 ;;\n'
        '                esac\n'
    )
    file.write_text(source.replace(firehose, firehose.replace('arm64e', 'arm64e arm64'))
                    .replace(rejected, guard + rejected), encoding='utf-8', newline='\n')

    sources = [p for d in (donor_series, xnu / 'patches-12377')
               for p in sorted(d.iterdir()) if p.suffix in ('.sh', '.patch')]
    if adreno_donor:
        series = adreno_donor / 'xnu' / 'patches-12377'
        sources.extend(next(series.glob(f'{n:04d}-*.patch')) for n in range(2000, 2012))
        sources.extend(sorted((xnu / 'patches-12377-adreno').glob('*.patch')))
    for patch in sources:
        dest = patches / f'sweet-{patch.name}'
        if dest.exists():
            raise SystemExit(f'duplicate patch: {patch.name}')
        data = patch.read_bytes().replace(b'\r\n', b'\n')
        if patch.name == '2001-sweet-ios16-drivers.patch':
            # Keep the A71 SEC_TS polling code from the base A71 series.
            touch = b'diff --git a/bsd/dev/sweet_touch.c b/bsd/dev/sweet_touch.c\n'
            parts = re.split(rb'(?m)(?=^diff --git )', data)
            if sum(part.startswith(touch) for part in parts) != 1:
                raise SystemExit('expected the Redmi touch diff in patch 2001')
            data = b''.join(part for part in parts if not part.startswith(touch))
        dest.write_bytes(data)
        staged.append(dest)
    (builder / 'series-SHA256SUMS').write_text(
        ''.join(f'{sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(staged)),
        encoding='utf-8', newline='\n',
    )
    print(f'Staged {len(staged)} project files in {patches}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('builder', type=Path)
    parser.add_argument('donor', type=Path)
    parser.add_argument('--adreno-donor', type=Path)
    args = parser.parse_args()
    stage(args.builder, args.donor, args.adreno_donor)
