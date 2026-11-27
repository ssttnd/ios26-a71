#!/usr/bin/env python3
"""Symbolicate kernel stack-sampler lines (`SMP NAME[pid] slide .. mh ..`, `SMP NAME tN pc .. lr .. sp .. bt ..`).

  a71-smp-symbolicate.py LOG NAME CACHE [--samples 0,5,-1] [--threads 0,2]

CACHE is the dyld_shared_cache_arm64e of the root (research/ios26/dsc/...). Needs `ipsw` on PATH
(research/ipsw-cli). Addresses outside the shared cache are shown as main-binary offsets (addr - mh + 0x100000000).
Pieces glued onto one console line are split first.
"""
import argparse
import functools
import re
import subprocess

CACHE_LO, CACHE_HI = 0x180000000, 0x300000000


@functools.lru_cache(maxsize=None)
def a2s(cache, addr):
    r = subprocess.run(['ipsw', 'dyld', 'a2s', cache, hex(addr)], capture_output=True, text=True)
    lines = [l for l in r.stdout.splitlines() if l.startswith('0x')]
    return lines[-1].split(': ', 1)[1].strip() if lines else '?'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('log')
    ap.add_argument('name')
    ap.add_argument('cache')
    ap.add_argument('--samples', default='0,-1')
    ap.add_argument('--threads', default='')
    a = ap.parse_args()
    text = open(a.log, 'rb').read().decode('utf-8', 'replace')
    text = re.sub(r'(?<!^)(?<!\n)SMP ', '\nSMP ', text)
    samples, cur, head = [], None, None
    for line in text.splitlines():
        m = re.match(r'SMP --- sample (\d+)', line)
        if m:
            cur = {'n': int(m.group(1)), 'head': None, 'threads': {}}
            samples.append(cur)
            continue
        if cur is None:
            continue
        m = re.match(r'SMP ' + re.escape(a.name) + r'\[(\d+)\] slide (0x[0-9a-f]+) mh (0x[0-9a-f]+)', line)
        if m:
            cur['head'] = (int(m.group(1)), int(m.group(2), 16), int(m.group(3), 16))
            continue
        m = re.match(r'SMP ' + re.escape(a.name) + r' t(\d+) pc (0x[0-9a-f]+) lr (0x[0-9a-f]+) sp \S+ bt ?([0-9a-fx ]*)', line)
        if m:
            cur['threads'][int(m.group(1))] = [int(m.group(2), 16), int(m.group(3), 16)] + \
                [int(x, 16) for x in m.group(4).split() if re.fullmatch(r'0x[0-9a-f]+', x)]
    samples = [s for s in samples if s['head']]
    print(f'{len(samples)} samples of {a.name}')
    pick = [samples[int(i)] for i in a.samples.split(',') if samples]
    want = {int(t) for t in a.threads.split(',') if t}
    for s in pick:
        pid, slide, mh = s['head']
        print(f'=== sample {s["n"]} pid {pid} slide {slide:#x}')
        for t, addrs in sorted(s['threads'].items()):
            if want and t not in want:
                continue
            print(f'  t{t}')
            for i, x in enumerate(addrs):
                if not x:
                    continue
                if CACHE_LO <= x - slide < CACHE_HI:
                    sym = a2s(a.cache, x - slide)
                else:
                    sym = f'main+{x - mh + 0x100000000:#x}'
                print(f'    {"pc" if i == 0 else "lr" if i == 1 else "  "} {x:#x} {sym}')


if __name__ == '__main__':
    main()
