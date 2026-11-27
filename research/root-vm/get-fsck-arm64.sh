#!/bin/sh
# Fetch Ubuntu noble arm64 hfsprogs + glibc + libssl, unpack, and bundle fsck.hfsplus with its loader.
set -e
W=~/w/fsck-arm64
rm -rf "$W"; mkdir -p "$W/debs" "$W/root" "$W/out/lib"
cd "$W/debs"
BASE=http://ports.ubuntu.com/ubuntu-ports
curl -fsS "$BASE/dists/noble/main/binary-arm64/Packages.gz" | gunzip > ../Packages-main
curl -fsS "$BASE/dists/noble/universe/binary-arm64/Packages.gz" | gunzip > ../Packages-universe
curl -fsS "$BASE/dists/noble-updates/main/binary-arm64/Packages.gz" | gunzip > ../Packages-updates
for pkg in hfsprogs libc6 libssl3t64; do
  f=""
  for idx in ../Packages-updates ../Packages-main ../Packages-universe; do
    f=$(awk -v p="$pkg" '$1=="Package:"{m=($2==p)} m&&$1=="Filename:"{print $2; exit}' "$idx")
    [ -n "$f" ] && break
  done
  sum=""
  for idx in ../Packages-updates ../Packages-main ../Packages-universe; do
    sum=$(awk -v p="$pkg" '$1=="Package:"{m=($2==p)} m&&$1=="SHA256:"{print $2; exit}' "$idx")
    [ -n "$sum" ] && break
  done
  echo "$pkg $f"
  curl -fsS -o "$(basename "$f")" "$BASE/$f"
  echo "$sum  $(basename "$f")" | sha256sum -c -
  dpkg-deb -x "$(basename "$f")" ../root
done
cd ..
cp root/sbin/fsck.hfsplus out/ 2>/dev/null || cp root/usr/sbin/fsck.hfsplus out/
L=root/usr/lib/aarch64-linux-gnu
cp -L $L/ld-linux-aarch64.so.1 $L/libc.so.6 $L/libcrypto.so.3 out/lib/
file out/fsck.hfsplus
sha256sum out/fsck.hfsplus out/lib/*
tar -C out -czf fsck-arm64.tgz .
ls -l fsck-arm64.tgz
