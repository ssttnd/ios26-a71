#!/bin/sh
# Run by launchd job org.a71.root-once (root, RunAtLoad). Does its work once per marker.
# Installs TrollStore with its own helper: trollstorehelper install-trollstore TrollStore.tar
# copies the app into /var/containers/Bundle/Application and registers it with LaunchServices.
TS=/private/var/local/ts
MARK=$TS/installed.done
echo "root-once: start $(date)"
if [ -e "$MARK" ]; then
	echo "root-once: already done"
	exit 0
fi
# Give lsd, installd and containermanagerd time to come up after boot.
sleep 90
echo "root-once: install-trollstore"
"$TS/trollstorehelper" install-trollstore "$TS/TrollStore.tar"
rc=$?
echo "root-once: install-trollstore rc=$rc"
if [ "$rc" = 0 ]; then
	: > "$MARK"
fi
echo "root-once: end $(date)"
exit 0
