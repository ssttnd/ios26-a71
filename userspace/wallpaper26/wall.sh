#!/bin/sh
# One-shot wallpaper setup (A71 iOS 26): legacy lock/home image + LegacyPoster selected (Bergamota sweetnet tools,
# as DC28088 did over SSH). Runs as root from launchd job org.a71.wallpaper-once; log /var/local/wall.log.
T=/usr/local/bin/toybox
[ -f /var/local/wall.done ] && exit 0
echo "wall: start"
$T sleep 150
n=0
while [ $n -lt 6 ]; do
	n=$((n + 1))
	/usr/local/bin/sweetlegacywall /var/local/wallpaper.png
	a=$?
	/usr/local/bin/sweetposterset com.apple.PaperBoard.LegacyPoster LegacyPoster
	b=$?
	echo "wall: try $n sweetlegacywall=$a sweetposterset=$b"
	if [ $a -eq 0 ] && [ $b -eq 0 ]; then
		$T touch /var/local/wall.done
		echo "wall: done"
		exit 0
	fi
	$T sleep 30
done
echo "wall: gave up after $n tries"
exit 1
