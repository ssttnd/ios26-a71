#!/usr/bin/env python3
"""Read files from the iOS HFS+ root on the A71's userdata, from TWRP, without mounting it.

  a71-hfs-get.py ADB_EXE /path/on/root [OUT]       copy one file (OUT default: its name)
  a71-hfs-get.py ADB_EXE --stat /path [/path...]   print type and size
  a71-hfs-get.py ADB_EXE --ls /dir [/dir...]       list a folder (name, type, size)

Read only: every access is `dd if=/dev/block/by-name/userdata` through `adb exec-out`. The journal is
not replayed (tools/hfsread.py), so a file changed shortly before a forced restart may read as its
older version: check what comes back (a plist must parse).
"""
import os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hfsread

TGT = "/dev/block/by-name/userdata"
CHUNK = 1 << 20
NW = 0x08000000 if os.name == "nt" else 0


class Remote:
    """File-like reader of the raw partition, 1 MiB chunks cached."""

    def __init__(self, adb):
        self.adb, self.pos, self.cache = adb, 0, {}
        if subprocess.run([adb, "get-state"], capture_output=True, text=True, creationflags=NW).stdout.strip() != "recovery":
            sys.exit("phone is not in TWRP")

    def chunk(self, i):
        if i not in self.cache:
            d = subprocess.run([self.adb, "exec-out", f"dd if={TGT} bs={CHUNK} skip={i} count=1 2>/dev/null"],
                               capture_output=True, timeout=120, creationflags=NW).stdout
            if len(d) != CHUNK:
                sys.exit(f"short read at chunk {i}: {len(d)} bytes")
            self.cache[i] = d
        return self.cache[i]

    def seek(self, off):
        self.pos = off

    def read(self, n):
        out = b""
        while n > 0:
            i, o = divmod(self.pos, CHUNK)
            part = self.chunk(i)[o:o + n]
            out += part
            self.pos += len(part)
            n -= len(part)
        return out

    def close(self):
        pass


class RemoteHFS(hfsread.HFS):
    def __init__(self, adb):
        self.f = Remote(adb)
        self._init()


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    h = RemoteHFS(sys.argv[1])
    if sys.argv[2] == "--stat":
        for p in sys.argv[3:]:
            print(p, h.info(p))
        return
    if sys.argv[2] == "--ls":
        for p in sys.argv[3:]:
            i = h.info(p)
            if not i or i["type"] != "dir":
                print(p, i)
                continue
            for name, kind, cnid, size in h.listdir(i["cnid"]):
                print(f"{kind:4} {size:>12} {name}")
        return
    path = sys.argv[2]
    info = h.info(path)
    if not info or info["type"] != "file":
        sys.exit(f"{path}: {info}")
    out = sys.argv[3] if len(sys.argv) > 3 else os.path.basename(path)
    data = h.readfile(path)
    open(out, "wb").write(data)
    print(f"{path}: {len(data)} bytes -> {out}")


if __name__ == "__main__":
    main()
