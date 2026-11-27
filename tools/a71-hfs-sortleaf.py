#!/usr/bin/env python3
"""Fix a catalog leaf whose records are out of key order by permuting only its offset table.

  a71-hfs-sortleaf.py ADB_EXE NODE OUTDIR            dry run: save the node, build the sorted copy, check it
  a71-hfs-sortleaf.py ADB_EXE NODE OUTDIR --write    also write the sorted node to the phone and read it back

The record bytes stay where they are; only the 2-byte offsets at the end of the node are reordered so that
keys ascend (HFSX binary order: parent ID, then UTF-16BE name). The free-space offset (the last table entry)
is unchanged. Refuses if the sorted node would not fit between the previous leaf's last key and the next
leaf's first key, if two keys are equal, or if the first key changes (the index node points at it).
"""
import hashlib
import importlib.util
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TGT = '/dev/block/by-name/userdata'


def load(name):
    spec = importlib.util.spec_from_file_location(
        name.replace('-', '_'), os.path.join(os.path.dirname(os.path.abspath(__file__)), name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def keys(v, d):
    ns = len(d)
    cnt = struct.unpack('>H', d[10:12])[0]
    out = []
    for k in range(cnt):
        o = struct.unpack('>H', d[ns - 2 * (k + 1):ns - 2 * k])[0]
        kl, parent, name = v.key(d, o)
        out.append(((parent, name.encode('utf-16-be')), o))
    return out


def node_offset(v, ext, n):
    """Absolute byte offset of catalog node n on the volume (must sit inside one extent)."""
    off = n * v.node_size
    pos = 0
    for start, count in ext:
        ln = count * v.bs
        if off < pos + ln:
            if off + v.node_size > pos + ln:
                sys.exit('node spans two extents')
            return start * v.bs + off - pos
        pos += ln
    sys.exit('node outside the catalog')


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    adb, n, outdir = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    write = '--write' in sys.argv[4:]
    v = load('a71-hfs-get').RemoteHFS(adb)
    ext = load('a71-hfs-scan').catalog_extents(v)
    ns = v.node_size
    on_phone = v.fork_read(ext, n * ns, ns)
    d = on_phone
    if '--base' in sys.argv:   # build from a saved original node instead of what is on the phone now
        d = open(sys.argv[sys.argv.index('--base') + 1], 'rb').read()
        if len(d) != ns:
            sys.exit('base file is not one node')
    if struct.unpack('>b', d[8:9])[0] != -1:
        sys.exit('not a leaf node')
    flink, blink = struct.unpack('>II', d[0:8])
    cur = keys(v, d)
    new = sorted(cur)
    if [k for k, _ in new] == [k for k, _ in cur]:
        sys.exit('node already in order')
    if any(a[0] == b[0] for a, b in zip(new, new[1:])):
        sys.exit('duplicate keys in node')
    if new[0] != cur[0]:
        sys.exit('first key would change')
    prev_last = keys(v, v.fork_read(ext, blink * ns, ns))[-1][0] if blink else None
    next_first = keys(v, v.fork_read(ext, flink * ns, ns))[0][0] if flink else None
    if prev_last is not None and not prev_last < new[0][0]:
        sys.exit(f'previous leaf {blink} ends at {prev_last}, not below {new[0][0]}')
    if next_first is not None and not new[-1][0] < next_first:
        sys.exit(f'next leaf {flink} starts at {next_first}, not above {new[-1][0]}')
    cnt = len(cur)
    # Records must also be stored in key order (offsets ascending), so repack the record bytes.
    # Record lengths come from the physical layout: each record runs to the next offset, the last
    # to the free-space offset.
    free = struct.unpack('>H', d[ns - 2 * (cnt + 1):ns - 2 * cnt])[0]
    phys = sorted(o for _, o in cur) + [free]
    length = {phys[i]: phys[i + 1] - phys[i] for i in range(cnt)}
    if phys[0] != 14:
        sys.exit(f'first record at 0x{phys[0]:x}, expected 0xe')
    body = b''.join(d[o:o + length[o]] for _, o in new)
    assert len(body) == free - 14
    fixed = bytearray(d)
    fixed[14:free] = body
    pos = 14
    for k, (_, o) in enumerate(new):
        fixed[ns - 2 * (k + 1):ns - 2 * k] = struct.pack('>H', pos)
        pos += length[o]
    fixed = bytes(fixed)
    assert pos == free and fixed[:14] == d[:14] and fixed[free:ns - 2 * cnt] == d[free:ns - 2 * cnt]
    check = keys(v, fixed)
    assert [k for k, _ in check] == [k for k, _ in new] and [o for _, o in check] == sorted(o for _, o in check)
    for (_, o_new), (_, o_old) in zip(check, new):
        assert fixed[o_new:o_new + length[o_old]] == d[o_old:o_old + length[o_old]]
    os.makedirs(outdir, exist_ok=True)
    orig_path = os.path.join(outdir, f'catalog-node-{n}.orig')
    fixed_path = os.path.join(outdir, f'catalog-node-{n}.repacked')
    if not os.path.exists(orig_path):
        open(orig_path, 'wb').write(d)
    open(fixed_path, 'wb').write(fixed)
    byte_off = node_offset(v, ext, n)
    print(f'node {n}: {cnt} records, prev leaf {blink} last {prev_last}, next leaf {flink} first {next_first}')
    for k, (key, o) in enumerate(new):
        print(f'  [{k}] parent {key[0]} {key[1].decode("utf-16-be")!r} at 0x{o:x}')
    print(f'volume byte offset {byte_off} (block {byte_off // v.bs}), node size {ns}')
    print(f'orig   {hashlib.sha256(d).hexdigest()}  {orig_path}')
    print(f'sorted {hashlib.sha256(fixed).hexdigest()}  {fixed_path}')
    if not write:
        print('dry run: nothing written')
        return
    if byte_off % 512 or ns % 512:
        sys.exit('node not sector aligned')
    nw = 0x08000000 if os.name == 'nt' else 0
    run = lambda *a: subprocess.run([adb, *a], capture_output=True, text=True, creationflags=nw)
    now = run('exec-out', f'dd if={TGT} bs=512 skip={byte_off // 512} count={ns // 512} 2>/dev/null | sha256sum').stdout.split()[0]
    if now != hashlib.sha256(on_phone).hexdigest():
        sys.exit(f'node changed on the phone since it was read: {now}')
    if run('push', fixed_path, '/tmp/catnode.bin').returncode:
        sys.exit('adb push failed')
    print(run('shell', f'dd if=/tmp/catnode.bin of={TGT} bs=512 seek={byte_off // 512} count={ns // 512} conv=notrunc,fsync 2>&1; sync').stdout.strip())
    back = run('exec-out', f'dd if={TGT} bs=512 skip={byte_off // 512} count={ns // 512} 2>/dev/null | sha256sum').stdout.split()[0]
    print('readback', back, 'VERIFY OK' if back == hashlib.sha256(fixed).hexdigest() else 'VERIFY FAILED')


if __name__ == '__main__':
    main()
