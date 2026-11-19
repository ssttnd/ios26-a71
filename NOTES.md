# iOS 26 on Galaxy A71 (SM-A715F)

## 2026-11-19 — donor located

- The iOS 16 checkout for this port starts at `ff6e898`. Its handoff is in
  `docs/ios16-notes.md`. The sibling `ios-a71` contains the A71 shim, stock DTB
  and recovery backups. TWRP ADB confirmed `a71` and a 64 MiB `boot` partition.
  Before the first test, saved the current partition to the ignored
  `backup/ios26-first-boot/boot.img` and matched SHA-256 to on-device readback
  (`5ca7519303163fdc81b25c4db3b1ef38599d7add5c44d84f6c5b2514afdd5793`).
- DC28088 reported iOS 26.6.2 (23G90, iPhone12,1) reaching the home screen on
  Redmi Note 10 Pro (`sweet`, SM7150). Donor `4ff9b8e` documents the home-screen
  boot `26r8` and the HFS RAM disk boot `26g` that reached PID 1. Both used
  donor Actions run `43444092685`, which GitHub reports succeeded at `7efa2c8`.
  The kernel uses Bergamota `37a7a7a` on XNU `12377.121.6`.
- Start with the HFS RAM disk diagnostic and the A71 memory map. It can test
  XNU and PID 1 independently of the existing system on `userdata`. The Redmi
  report used eight cores and needed `sweetearlyfb=1` for the framebuffer log.
  Use Samsung-specific touch and USB code before enabling those peripherals.

## 2026-11-19 — first A71 test image

- `a7615dd` is on the separate private remote `ssttnd/ios26-a71`. Actions
  `44545515578` built and verified the 16 MiB HFSX diagnostic RAM disk
  (`d4de664d61f3548a946be84798a666285448d5f6eaf94f2f8276725ce54b52f6`).
  The XNU job was running when the first test image was built.
- `build/a71-xnu26-smoke.img` is 38,494,208 bytes. It carries the verified
  donor kernel from `43444092685`, HFSX RAM disk, and the exact shim and stock
  DTB extracted from the A71's saved `boot`. XNU entry `0xfffffe00075c6488`,
  zero chained fixups, diagnostic volume at physical `0x1029b4000`.
- TWRP wrote only `boot` and verified the 38,494,208-byte readback against
  `48002e40afb98066618910b310098640d7420b119d2ec0b7bfd36d4ad0f789e7`.
  Requested normal reboot. Awaiting the physical display result. This image
  uses `rd=md0` with UFS logging disabled and has no iOS root filesystem.

## 2026-11-19 — early panic diagnosed and second image flashed

- Owner's photo shows `SWEET EARLY 20: kprintf startup complete`, then an early
  panic. Kernel symbols put PC `0xfffffe0007d6e784` at `bzero+0x44` (`DC ZVA,
  X3`) and LR `0xfffffe0007c919bc` at `PE_create_console+0x130`. ESR
  `0x96000061` is an alignment fault on a store to `0xfffffe000ce00040` while
  clearing the legacy 1 MiB `/pram` panic region.
- Removed `/pram` and `embedded-panic-log-size` from the 12377 ADT, matching
  the donor. The second image `build/a71-xnu26-smoke-v2.img` uses the same
  kernel, shim, DTB and RAM disk. TWRP readback verified
  `b1c177217f6dbb6f3c51d45ca0fc5d623f8f48fb4ed9ff0a1d25d2d8aea31a13`.
  Owner photo confirms this boot reached PID 1. Kernel trace shows
  `launchd[1/... u0] open(5) e=2 "/dev/console"`, followed by framebuffer
  stats through 160 s uptime. The diagnostic HFSX mounted and its executable
  ran. The first RAM disk omitted the `/dev` mountpoint, so the diagnostic
  could not print. The revised builder includes `/dev` and its PID 1 sleeps
  even when opening the console fails.
- Apple's N104AP tree was extracted from the iOS 26.6.2 IPSW with its ZIP CRC
  verified. Generated the full iPhone 11 identity ADT with Samsung A71
  addresses. Full iOS root preparation and installation remain pending.
- Restored all 64 MiB of the original `boot` and matched the complete
  readback to `5ca7519303163fdc81b25c4db3b1ef38599d7add5c44d84f6c5b2514afdd5793`.
  Owner confirmed iOS 16 booted. `userdata` was untouched.

## A71 hardware port

- `b058eab` adds `2000-a71-sec-ts-touch.patch` with the Samsung power,
  reset, ID probe and event handling to the 12377 driver. It reuses the
  XNU 12377 HID event queue and GPIO I2C paths, selects Samsung via
  `samsung,a71`, and is opt-in during bring-up. Its diff applies to the
  staged donor source. Actions `44550850053` on `codex/a71-touch-build`
  builds it at `66ae7b1` and regenerates the diagnostic RAM disk with `/dev`.
  Compilation and device validation are pending.

## Full iOS 26.6.2 root preparation

- iPhone12,1 IPSW `23G90` downloaded from Apple. Its SHA-256 matched the CDN
  header (`02d1f0774bac11889483d372b0ecc094ad53681aa85beed9fd56634197effab3`).
- Root build runs in a headless Ubuntu 24.04 VM under QEMU/WHPX launched from
  the Windows workspace, without WSL. `research/root-vm/build-ios26-root.log`
  holds its progress. Bergamota `37a7a7a` Renegade, apfs-fuse `66b86bd`,
  ipsw `3.1.749`, berga-tools v3. Raw 24 GiB HFSX, with jailbreak and
  Bergamota renderer payload disabled. This root has not yet booted.
- Owner authorized replacing `userdata` only after a verified backup.
  A71 is in TWRP. Backup of the entire 117,732,929,536-byte partition is
  underway in `backup/ios16-before-ios26-userdata/`, with separately verified
  1 GiB chunks and a manifest on completion. The existing HFSX filesystem
  is 16 GiB by its volume header. Full iOS 26 image has not been written.

## Ready for first full iOS 26 boot

- The private A71 Actions run `44545515578` succeeded at `a7615dd`, including
  the XNU 12377 kernel (`b5c5424644f056908b880a723a8d54bd1cc98bfde5c0a5fccdea50c361bb76e8`,
  downloaded and hash checked) and its initial RAM disk. The updated RAM disk job
  (with `/dev`) also passed in `44550850053`. Its A71 SEC_TS kernel job is
  passed as well. The touch kernel artifact is `14546595630`.
- `build/ios26-root-a71-23G90.img` is the verified 24 GiB raw HFSX root.
  SHA-256 `54f7898e050730a21073b98a6af79769592d092dce4a6ffa60b1ffd60d7a59f3`.
  HFS fsck passed, boot-task paths and shared-cache signatures passed, and
  Windows read the expected `26.6.2` / `23G90` from SystemVersion.plist.
  The two redundant working copies (Apple IPSW download and the temporary
  VM disk) were removed after their respective outputs were verified.
- `build/a71-ios26-full-cpu.img` (21,721,088 bytes) boots `rd=ufsroot0`.
  SHA-256 `3f2b27496fbda3cdb49130a5f37e5edc370a4dcd3dbb39a74bd6dafd43e11727`.
  It uses the same donor kernel that reached diagnostic PID 1 on A71,
  verified Samsung shim/DTB, and the N104AP product ADT. Touch, GPU and USB
  are disabled for this first full boot.

## Verified iOS 16 backup, first install started

- The 110-chunk backup from TWRP passed SHA-256 checks against all
  117,732,929,536 bytes of `userdata`. Nonzero chunks are stored as 9,022,081,211
  compressed bytes in `backup/ios16-before-ios26-userdata/`. The adjacent
  `userdata-verified.json` describes all offsets, including zero ranges, and
  has a separate SHA-256 file. Rechecked the first GiB against the attached
  phone and confirmed the restored iOS 16 `boot` hash before starting.
- `tools/a71-write-root.py --gzip` keeps per-chunk and whole-image readbacks
  while compressing the USB transfer. Verified the compressed stream against
  a checksum in TWRP without writing partitions before starting the real
  write. Install log is `logs/ios26-first-userdata-write.log` (gitignored).
- The full root write completed in TWRP. Nineteen chunks were written on the
  first attempt and five matched already. The entire 24 GiB readback matched
  SHA-256 `54f7898e050730a21073b98a6af79769592d092dce4a6ffa60b1ffd60d7a59f3`.
- Flashed the full CPU-only boot image, verified the 21,721,088-byte readback
  against `3f2b27496fbda3cdb49130a5f37e5edc370a4dcd3dbb39a74bd6dafd43e11727`,
  and requested a system reboot.
- Owner confirmed the full iOS 26.6.2 boot reached the lock screen. The owner
  saw red clock digits on a black background. This image had touch disabled.
  A long power-button hold turned the display off. Next test the A71 SEC_TS
  build by replacing only `boot`.
- TWRP log `logs/ios26-full-cpu-first.txt` (flush 27, 709,127 bytes) confirms
  Darwin 25.5.0, 8/8 cores, HFS mounted on `ufsroot0`, and execution of
  `launchd`, `SpringBoard`, and `backboardd`. No `panic(cpu` line.

## Samsung touch image

- Actions `44550850053` succeeded. The verified kernel SHA-256 was
  `69cf90672f532a08602e1ee99d6b064ef7b8ed2fb70da778ed0f983eaa690a57`.
- `build/a71-ios26-touch.img` enables `sweettouch=1 sweettouchdelay=3`.
  TWRP wrote only `boot` and verified the 21,737,472-byte readback against
  `bce68159404842a28022d858c8112ac44081ffea94802b1c1c0e0aeb345660ae`.
  Requested normal reboot. Owner confirmed the system started, swipe-up
  unlocked the phone, and Settings opened. The phone is on iOS 26.6.2 with
  this image. GPU acceleration, radio, audio and USB remain outside the
  verified result. The first CPU-only boot showed a black wallpaper.

## 2026-11-19 — first CPU renderer abort

- Owner reported a SpringBoard reload. The TWRP log
  `logs/ios26-touch-springboard.txt` (flush 19, 701,826 bytes) confirms the
  Samsung S6SY771 driver attached. `backboardd[64]` aborted with signal 6 on
  `push_surface`, `ogl-context.cpp:1186` (`found != slist->end()`). The log
  shows both backboardd and SpringBoard executing again. No kernel panic or
  separate SpringBoard crash was recorded for this event.
- DC28088's iOS 26 log records the same assertion on the Bergamota-only
  Redmi kernel with CPU rendering (boot 26c8b). The Metal path avoids this
  renderer on Redmi. A71 Adreno 618/Metal has not been brought up on iOS 26.
- After a normal reboot from TWRP without changing `boot`, the owner
  reported that Settings opens and immediately freezes. There is no log
  for this separate event yet. Whether it is the same compositor abort
  remains unverified.

## 2026-11-19 — button test and Metal preparation

- `logs/ios26-settings-freeze.txt` (flush 48, 1,417,276 bytes) captured the
  second boot. `Preferences` started and framebuffer swaps continued. No
  `CRASH Preferences`, `CRASH backboardd`, `CRASH SpringBoard`, or panic
  appears in the recovered ring. The reported Settings stall is unexplained.
- The touch image had `sweetkeys=0`. `build/a71-ios26-keys.img` uses the
  same verified touch kernel with `sweetkeys=1`. After owner authorization,
  TWRP verified its `boot` readback SHA-256
  `1ae8e60bbd90139821c2d872ac4eef63980bae8452fecf630fedd3a975d38638`.
  Announced and requested reboot. Button behavior is pending confirmation.
- Commit `2f36327` builds an optional Adreno kernel using DC28088 `4ff9b8e`
  through patch 2011 on the same Bergamota base. The Redmi touch diff is
  omitted in favor of A71 SEC_TS. Patch 2100 ports the A71 raw package
  installer and requires both `samsung,a71` and `sweetpayload=1`. Local
  patch checks passed. Actions run `44560785792` is building it.
- Donor Metal build 36, CI `44101448882` at `19236822`, passed its bundle
  hash manifest check. Package `build/a71-ios26-metal36.payload` has 11 entries,
  8,966,144 bytes, SHA-256
  `51c0a91d059d384f4d60483015fdfb9f673c78865222735213995c059fd9debe`.
  It installs `SweetMetal2.bundle` and `FD_MESA_DEBUG=sysmem`. Neither is
  in the original iOS 26 root. The package has not been written. A71 GMU,
  SQE and signed ZAP files were checked by the ADT packer offline.

## 2026-11-19 21:10 — keys confirmed; handoff to a new agent; next: Adreno + Metal

- Owner: `build/a71-ios26-keys.img` (sweetkeys=1) boots, slowly (long Apple logo); power and volume
  buttons work. Boot time not measured, no log of that boot pulled yet. The second agent was stopped.
- Goal set by the owner: everything that worked on the iOS 16 port works on iOS 26. Reference for the A71
  side: `ios-a71` patches 0184-0229 (touch, USB ACM, RTC, payload, battery/charge, panel and brightness,
  torch, PSCI halt, PMEM, Wi-Fi SMMU and link events, ADSP/SMMU audio, GPU 700 MHz, LLCC, swap wait).
  Donor for the SoC side: DC28088 NOTES (iOS 26 on sweet: GPU, Metal builds to 36, wallpaper, Control
  Centre via MobileGestalt arm64e override, Bluetooth, sound; Wi-Fi blocked on wlan_pd UNINIT).
- Found in the donor NOTES (2026-11-17 08:20 IST): `serial=3` starts `serial_keyboard_poll` at kernel
  priority 95 and it spins a whole core (cyclic gPESF list); their fix was `serial=1` and patch 2008.
  `tools/a71-pack-ios26.py` now uses `serial=1` (guess: part of the slow boot here; not measured).
- Plan: (1) Adreno kernel CI 44560785792 (2000-2011 + 2100) + touch + keys + A71 GPU firmware +
  `--metal --payload` with `build/a71-ios26-metal36.payload`; (2) USB console (0187 port); (3) Wi-Fi;
  (4) audio; (5) battery, brightness, torch, RTC; (6) sweetdbg and the launchd/lockdownd fixes.

## 2026-11-19 21:25 — first Metal image flashed (metal-a)

- Kernel: Actions `44560785792` (2f36327) succeeded in 19 min; kernel SHA-256
  `96a56929a53fca541266534439c70da324025bad237bf0ff77c85327e2cd4a3d` (matches its SHA256SUMS), in
  `research/ci-44560785792/` (ignored). Has SEC_TS, keys, GPUCC audit v2, Metal plugin, payload, donor 2000 cpufreq.
- `logs/ios26-keys-boot.txt` (keys image boot, 859,728 bytes): `SWEET KEYS` key events, no panic; daemons
  gamepolicyd, liveactivitiesd, nehelper killed with sig 9. Why that boot was slow was not measured.
- `build/a71-ios26-metal-a.img` = that kernel + `--touch --keys --adreno-firmware <ios-a71 research/a71-firmware>
  --metal --payload --cpufreq`, `serial=1`; cmdline 503 bytes. TWRP: package `build/a71-ios26-metal36.payload`
  VERIFY OK `51c0a91d...`, then boot VERIFY OK `4f6bf224cf650e047cfc6c2e7e7ada3a5f4421964f870fff5f0032e3c4b5cea4`,
  reboot requested. Fallback: `build/a71-ios26-keys.img` (1ae8e60b...). Result pending.
- Not in this image: sweetm2restart (iOS 16 0200; SpringBoard restart when the GPU comes up) and A71 battery,
  brightness, USB, Wi-Fi, audio.

## 2026-11-19 21:40 — metal-a result, GPU firmware fix, metal-b flashed, combined kernel building

- metal-a (owner): a little smoother, Metal not active, Settings froze again. TWRP log `logs/ios26-metal-a.txt`:
  cpufreq A55 1804.8 MHz, A76 2208 MHz (was 300), L3 1459.2; 8/8 CPUs; payload 11/11; GMU and HFI up, then
  `CP firmware properties errno=22 SQE=32304 MDT=6860 ZAP=1968` and `rendering unavailable`: donor sizes are
  Redmi's. Also SiriAUSP/MauiAUSP/MacinTalkAUSP/KonaSynthesizer abort (sig 6) in a loop (donor saw the same).
- Kernel CI `44565383497` (ed4492b: 2100-2107 = payload, USB ACM 2101, A71 GPU firmware facts 2102 = iOS 16
  0190, 0202, 0216, 0218, 0220, 0222) succeeded; kernel `7e4eeae2...b943`, series hashes match the repo.
- `build/a71-ios26-metal-b.img` = that kernel + touch, keys, A71 GPU firmware, `--metal --payload --cpufreq --usb`
  (sweetusb=3); package `build/a71-ios26-noausp.payload` (moves the four speech synthesizer .appex from
  /System/Library/ExtensionKit/Extensions to /private/var/local/disabled-appex; reversible) VERIFY OK `9d057494...`,
  boot VERIFY OK `95561ac06e89dcd34f5531175c0b04cdc65141e92584cb4d85dfd49a55a13884`. USB log recording to
  `logs/usb-ios26-metal-b.txt`. Result pending.
- Combined kernel CI `44568269777` (fc3b49e) building: 2108-2115 hand ports (battery, power off, charger, torch,
  pmem injection, privileges, Wi-Fi/ADSP, command-mode brightness). Series checked with git apply in order on the
  staged tree (scratch copy of research/xnu-12377); not compiled before this run.
- Resolution: iOS draws 828x1792 (iPhone 11 @2x) scaled to 1080x2400 (`presented as 828x1792, scale 1`). Plan
  after Metal works: canvas 1242x2688 + MobileGestalt scale 3 (same 414x896 points), ADT and MG only.

## 2026-11-19 21:45 — metal-b: Metal runs; USB log works; package mv missing

- USB ACM works on iOS 26: Windows `USB Serial Device (COM7)`, `logs/usb-ios26-metal-b.txt` (tools/a71-usblog.py).
- Observed in it: `CP firmware properties errno=0 SQE=32304 MDT=6860 ZAP=1968` (2102 works), `NativeAdreno ABI + Metal
  discovery published on live A618 context`, `restarted backboardd for Metal discovery`; then backboardd renders through
  SweetNativeMetal (5 s window: 58 commands, 3287 draws, transport submits 90, failures 0). SpringBoard exec once after
  the restart; no SpringBoard/backboardd CRASH after it. Owner saw SpringBoard go down once ("crashed at once") and
  "no Metal": guess = the planned backboardd restart at GPU publish (sweetm2restart default 1; 2 is in 2109).
- FB stats right after: copy mode, swaps 10.9/s, copy_us ~10.6 ms per frame (CPU copy to the panel).
- Package: `op 5 ... KonaSynthesizer.appex -> 22`, `finished 3/7`: no SP_MOVE in 2100 -> xnu 2116 (0196 installer part).
  Combined run 44568269777 cancelled; rerun `44568994432` (978c888 = 2101-2116).
- Owner photo before this boot (first boot after the TWRP flash): shim blue screen `PANIC SYNC`, STAGE loader,
  ESR 0x96000000, ELR 0x801EA5A0, FAR 0x6C207369C1952320, X30 0x3030454646464646 (ASCII "00EFFFFF"); reset, next boot
  fine. Cause unknown (guess: a pointer read from stale RAM in the first stage; ELR is outside the 180 KiB shim image).

## 2026-11-19 21:50 — metal-c with jetsam limits off and the Control Center fix (old kernel)

- Owner on metal-b: Metal visible (dock outline = Liquid Glass), Settings hangs, Control Center blur but no
  modules. USB log: many `sig 9` jetsam kills (`ns 1 code 0x7`): lsd, linkd, donotdisturbd, deviceaccessd ...
  Guess: Settings waits on a killed lsd. Donor fix `sweetjetsamlimits=0` (2006, in the Adreno kernel) now on
  every Adreno image.
- Read from the phone in TWRP with the new `tools/a71-hfs-get.py` (raw reads, no mount; files in research/mg,
  ignored: the MobileGestalt cache holds device identifiers): MobileGestalt cache 9678 bytes, CacheExtra had
  neither `li+w2foswFu0srn5UxdOug` (arm64e) nor `jdLgKT+0BZmGrzd9J0cuPA` (camera-flash); ControlsIconState.plist
  289 bytes, empty layout (as the donor had).
- `build/a71-ios26-cc-old.payload` (15 entries, `f04f4994...`): originals to /var/local/mg-backup and
  /var/local/cc-backup, MobileGestalt cache with both keys true (mode 0666), rm of ControlsIconState.plist and
  ControlsMigrationSettings.plist (this kernel has no package mv). `build/a71-ios26-metal-c.img` = metal-b +
  sweetjetsamlimits=0, boot VERIFY OK `40ccca6a...`. Result pending.
- RTC offset read in TWRP: 1778420636 s (rtc0 since_epoch 16686302), for --rtcoff with the 2108 kernel.
- Prepared for the combined kernel: `build/a71-ios26-cc.payload` (20 entries: the same with mv, plus the four
  speech synthesizers moved).

## 2026-11-19 22:05 — metal-c result; combined kernel built; all-a flashed

- metal-c first boot: early kernel panic photo `assertion failed: strlen(name) <= (sizeof(new_list->el_name) - 1)`
  (subr_eventhandler.c:125, assfail in uipc_socket.c:8260), during the cpufreq prints; nothing reached the UFS log
  or USB. Same kernel as metal-b; the only new arg (sweetjetsamlimits=0) sets one flag. Rebooted from TWRP without
  changes: booted. Guess: random memory corruption, like the shim blue screen before metal-b (both first boots right
  after a TWRP flash). Not explained.
- metal-c second boot (owner): Control Center has its modules (MobileGestalt arm64e/camera-flash override works);
  no `sig 9` jetsam kills in `logs/usb-ios26-metal-c.txt` (154 in the metal-b boot, incl. lsd x5); Settings still
  hangs. Preferences logs nothing; fairplayd.H2 respawns in a loop (as on iOS 16, where removing its launchd job
  unblocked the FairPlay clients).
- Phone `/System/Library/xpc/launchd.plist` read in TWRP: identical to the image (692 jobs). Package
  `build/a71-ios26-fp.payload` (`c9c54edd...`): original to /var/local/apple-orig/launchd.plist, plist without
  com.apple.fairplayd.H2 (691 jobs), the four speech synthesizers moved (needs 2116). Takes effect at the second boot.
- Combined kernel CI `44568994432` (978c888, 2100-2116) succeeded at the first build; kernel `539bc512...`.
- `build/a71-ios26-all-a.img`: that kernel + touch, keys, GPU firmware, metal, payload, cpufreq, usb,
  rtcoff 1778420636; packer added sweetbattery=2, sweetm2restart=2, DCS brightness on, sweetcharge default;
  cmdline 533 bytes. Package VERIFY OK, boot VERIFY OK `3bc04ed8a20a0a5929d1cf8b7e0562dada9b8e03d04cd06ec96e1b9ecad0f14b`.
  Fallback: metal-c (`40ccca6a...`).

## 2026-11-19 22:20 — all-a results; MobileGestalt override protected; wallpaper; all-b flashed

- all-a (owner, two boots): battery right (log `s2mu106 66% 3988mV 21mA`), torch ok, gestures ok after the GPU
  restart (sweetm2restart=2), power off by holding the key not reported. Settings still hang on the second boot
  although fairplayd.H2 is gone there (0 lines) and the speech synthesizers no longer crash (package 11/11).
  Control Center back to 3 empty buttons, home screen icons vanish. Lock screen date "31 Dec 04:00": the kernel
  set the calendar right (`calendar set from the PM6150 RTC: 1795107806 s`) and no SWEET TIME setter appeared;
  Scion reports the same lock screen date on iOS 27 (guess: lock screen rendering, not the clock).
- Cause of the lost override (read in TWRP): the cache now uid 501 gid 0 mode 0666, same CacheUUID and 23G90, our
  two CacheExtra keys gone: MobileGestaltHelper (runs as mobile) rewrote the file in place, which my mode 0666
  allowed (its directory is root 0755). Now written root 0644.
- Package `build/a71-ios26-wall.payload` (25 entries, `13d7bd1d...`, recipe userspace/wallpaper26/build-payload.sh):
  MobileGestalt override root 0644, Control Center layout moved aside again, Bergamota sweetnet26 tools from
  CI 44573984243 (sweetfp26.dylib replaces /usr/local/lib/sweetfp.dylib, old one in /var/local/pb-backup;
  sweetlegacywall, sweetposterset), a gradient /var/local/wallpaper.png, /var/local/wall.sh run once by the new
  launchd job org.a71.wallpaper-once (log /var/local/wall.log, marker /var/local/wall.done); launchd.plist without
  fairplayd.H2, with that job (692 jobs). The job runs from the second boot.
- `build/a71-ios26-all-b.img` = all-a + `sweetdtlog=Preferences` (Settings os_log on the console), VERIFY OK
  `3e069f06...`. USB log `logs/usb-ios26-all-b.txt`.
