#!/usr/bin/env python3
"""Stage the pinned donor series and A71 patches in darwin-xnu-build."""

import argparse
from hashlib import sha256
from pathlib import Path
from shutil import copyfile


def stage(builder, donor):
    project = Path(__file__).resolve().parents[1] / 'xnu' / 'patches-12377'
    patches = builder / 'patches' / '26.0'
    scripts = []
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

    for directory in (donor_series, project):
        for patch in sorted(directory.glob('*')):
            if patch.suffix not in ('.sh', '.patch'):
                continue
            dest = patches / f'sweet-{patch.name}'
            if dest.exists():
                raise SystemExit(f'duplicate patch: {patch.name}')
            copyfile(patch, dest)
            scripts.append(dest)
    (builder / 'series-SHA256SUMS').write_text(
        ''.join(f'{sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in sorted(scripts)),
        encoding='utf-8', newline='\n',
    )
    print(f'Staged {len(scripts)} project files in {patches}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('builder', type=Path)
    parser.add_argument('donor', type=Path)
    args = parser.parse_args()
    stage(args.builder, args.donor)
