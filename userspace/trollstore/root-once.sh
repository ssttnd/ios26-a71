#!/bin/sh
# Run by launchd job org.a71.root-once (root, RunAtLoad). Does its work once per marker.
# Installs TrollStore with its own helper: trollstorehelper install-trollstore TrollStore.tar
# copies the app into /var/containers/Bundle/Application and registers it with LaunchServices.
# Everything is also written to /dev/console, so it shows in the USB log (the HFS journal is not
# replayed by tools/a71-hfs-get.py, so the log file read from TWRP can be stale).
TS=/private/var/local/ts
MARK=$TS/installed.done
say() {
	echo "root-once: $*"
	echo "root-once: $*" > /dev/console 2>/dev/null
}
say "start $(date)"
if [ -e "$MARK" ]; then
	say "already done"
	exit 0
fi
# Give lsd, installd and containermanagerd time to come up after boot.
sleep 90
say "install-trollstore"
"$TS/trollstorehelper" install-trollstore "$TS/TrollStore.tar" > "$TS/helper.out" 2>&1
rc=$?
while IFS= read -r l; do say "helper: $l"; done < "$TS/helper.out"
say "install-trollstore rc=$rc"
if [ "$rc" = 0 ]; then
	: > "$MARK"
fi
say "end $(date)"
exit 0
