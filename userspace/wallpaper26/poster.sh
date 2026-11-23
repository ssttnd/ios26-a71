#!/bin/sh
# Poster probe (A71 iOS 26): list PosterBoard configurations and available descriptors.
# Runs as mobile from launchd job org.a71.poster-probe; log /var/local/poster.log (readable from TWRP).
# To select a poster explicitly, invoke this script with --select PROVIDER DESCRIPTOR.
T=/usr/local/bin/toybox
P=/usr/local/bin/sweetposterset
case $# in
	0) ;;
	3)
		if [ "$1" != "--select" ]; then
			echo "usage: $0 [--select PROVIDER DESCRIPTOR]" >&2
			exit 2
		fi
		;;
	*)
		echo "usage: $0 [--select PROVIDER DESCRIPTOR]" >&2
		exit 2
		;;
esac
echo "poster: start uid=$(id -u 2>/dev/null)"
$T sleep 120
echo "== list"
$P --list
for prov in com.apple.MercuryPoster com.apple.WallpaperKit.CollectionsPoster com.apple.GradientPoster.GradientPosterExtension \
	com.apple.Posters.KaleidoscopePosterApp.KaleidoscopePoster com.apple.NanoUniverse.AegirProxyApp.AegirPoster \
	com.apple.Posters.UnityPosterApp.UnityPosterExtension com.apple.Posters.WeatherPosterApp.WeatherPoster \
	com.apple.EmojiPoster.EmojiPosterExtension; do
	echo "== descriptors $prov"
	$P --descriptors $prov
done
[ "$#" -eq 0 ] && exit 0
n=0
while [ $n -lt 4 ]; do
	n=$((n + 1))
	echo "== select $2 $3 (try $n)"
	$P "$2" "$3"
	r=$?
	echo "select rc=$r"
	[ $r -eq 0 ] && break
	$T sleep 30
done
echo "== list after"
$P --list
echo "poster: end"
exit "$r"
