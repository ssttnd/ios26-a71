#!/bin/sh
# Poster probe (A71 iOS 26): what PosterBoard has and offers, then select a dynamic poster.
# Runs as mobile from launchd job org.a71.poster-probe; log /var/local/poster.log (readable from TWRP).
# The selection is in /var/local/poster.want: "PROVIDER DESCRIPTOR" (default: the animated gradient).
T=/usr/local/bin/toybox
P=/usr/local/bin/sweetposterset
echo "poster: start uid=$(id -u 2>/dev/null)"
$T sleep 120
echo "== list"
$P --list
for prov in com.apple.WallpaperKit.CollectionsPoster com.apple.GradientPoster.GradientPosterExtension \
	com.apple.Posters.KaleidoscopePosterApp.KaleidoscopePoster com.apple.NanoUniverse.AegirProxyApp.AegirPoster \
	com.apple.Posters.UnityPosterApp.UnityPosterExtension com.apple.Posters.WeatherPosterApp.WeatherPoster \
	com.apple.EmojiPoster.EmojiPosterExtension; do
	echo "== descriptors $prov"
	$P --descriptors $prov
done
want="com.apple.GradientPoster.GradientPosterExtension darkBlue.preset1"
[ -f /var/local/poster.want ] && want=$($T cat /var/local/poster.want)
n=0
while [ $n -lt 4 ]; do
	n=$((n + 1))
	echo "== select $want (try $n)"
	$P $want
	r=$?
	echo "select rc=$r"
	[ $r -eq 0 ] && break
	$T sleep 30
done
echo "== list after"
$P --list
echo "poster: end"
