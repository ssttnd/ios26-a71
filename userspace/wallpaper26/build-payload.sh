#!/bin/sh
# Usage: build-payload.sh MG_CACHE_FROM_PHONE  -> build/a71-ios26-wall.payload (run from the repo root)
set -e
export MSYS_NO_PATHCONV=1
M=/private/var/containers/Shared/SystemGroup/systemgroup.com.apple.mobilegestaltcache/Library/Caches/com.apple.MobileGestalt.plist
python -I - "$1" <<'PY'
import plistlib, sys
d = plistlib.load(open(sys.argv[1], 'rb'))
d['CacheExtra']['li+w2foswFu0srn5UxdOug'] = True   # arm64e
d['CacheExtra']['jdLgKT+0BZmGrzd9J0cuPA'] = True   # camera-flash
plistlib.dump(d, open('research/wall/MobileGestalt.plist.cc', 'wb'), fmt=plistlib.FMT_BINARY, sort_keys=False)
PY
python -X utf8 tools/a71-payload.py build build/a71-ios26-wall.payload \
  "file:$1=/private/var/local/mg-backup/com.apple.MobileGestalt.plist.rebuilt" \
  "file:research/wall/MobileGestalt.plist.cc=$M@644" \
  "file:research/wall/sweetfp.dylib.ios18=/private/var/local/pb-backup/sweetfp.dylib.ios18" \
  "file:research/sweetnet26/sweetfp26.dylib=/usr/local/lib/sweetfp.dylib@755" \
  "file:research/sweetnet26/sweetlegacywall=/usr/local/bin/sweetlegacywall@755" \
  "file:research/sweetnet26/sweetposterset=/usr/local/bin/sweetposterset@755" \
  "file:research/wall/wallpaper.png=/private/var/local/wallpaper.png" \
  "file:research/wall/wall.sh=/private/var/local/wall.sh@755" \
  "file:research/wall/launchd.plist.wall=/System/Library/xpc/launchd.plist" \
  "mv:/private/var/mobile/Library/ControlCenter/ControlsIconState.plist=/private/var/local/cc-backup/ControlsIconState.3empty.plist" \
  "mv:/private/var/mobile/Library/ControlCenter/ControlsMigrationSettings.plist=/private/var/local/cc-backup/ControlsMigrationSettings.3empty.plist"
