# iOS 26 on Galaxy A71 (SM-A715F)

## 2026-11-20 — repo made public (Actions minutes)

- Observed on github.com/settings/billing: GitHub Free, included Actions compute $12.00 / $12.00 used in November,
  all of it by private `ios26-a71`; `ios-a71` (public) $58.91 fully discounted. Reset in 11 days (2026-12-01).
- User request: `ssttnd/ios26-a71` made **public** (API confirms `visibility=public`) so CI is free again.
- Known in history: `a618_gmu.bin` (Qualcomm firmware, 32 KB), added `9b05f9c`, removed in `55c5ede`. User chose
  to publish without rewriting history. Actions logs are now public too: keep secrets and serials out of them.

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

## 2026-11-19 22:30 — all-b panicked; USB SMMU bank translates (guess at the corruption); all-c flashed

- all-b first boot (owner: panic, back in TWRP). USB log: package `finished 25/25 errno=0`, then cut off at
  backboardd start. TWRP ring (`logs/ios26-all-b-panic.txt`, 1872 lines) ends in text XNU does not print:
  `Exit EBS [ 5459] UEFI End`, format strings with literal `%s`, `Log Flush : 0 m`: memory holding the log ring was
  overwritten. No panic text saved.
- Pattern so far: all three corrupt boots (metal-b shim blue screen, metal-c eventhandler assert, all-b) were
  sweetusb=3 images on the first boot after a TWRP flash; metal-a (no USB) and the second boots did not corrupt.
- Every sweetusb=3 log: `SWEET USB: SMMU SMR3 0x80000540 S2CR 0x00000001 already matches the stream`: S2CR type 0 =
  translate through bank 1, whose page tables are whatever the last kernel (TWRP's Linux) left; sweet_usb DMA uses
  physical addresses. Guess (not proven): USB DMA lands in the wrong memory. xnu 2117 turns that bank's translation
  off (SCTLR.M = 0) if only USB uses it, else moves the stream to its own pass-through bank, and logs which.
  Kernel CI `44575804195` (8cf9a40) building.
- `build/a71-ios26-all-c.img` = all-b without --usb (sweetusb=0), VERIFY OK `12f7bb58...`. The wall package was
  applied in the all-b boot (25/25), so the wallpaper job, MobileGestalt 0644 override and the Control Center
  reset are on the root. Settings os_log (sweetdtlog=Preferences) goes to the UFS ring only (TWRP).

## 2026-11-19 22:45 — all-c result, Settings os_log, dynamic posters; all-d flashed (USB SMMU fix)

- all-c (owner): Control Center works and stays (MobileGestalt override root 0644 holds); Settings hang; no
  wallpaper; home screen icons vanish and come back. Owner: no static wallpaper, dynamic posters only.
- TWRP ring `logs/ios26-all-c.txt`: wall.log only "wall: start" (the job was still in its sleep). PosterBoard,
  PhotosPosterProvider, CollectionsPoster exec, no crashes. Settings os_log (sweetdtlog=Preferences): last calls
  before the hang open com.apple.AudioAccessoryServices, managedconfiguration.profiled, com.apple.HearingModeService
  and com.apple.DeviceAccess.xpc (deviceaccessd), plus many "bootstrap_look_up of WiFiManager server failed" (no
  wifid). Which one blocks: not known (needs a stack).
- Userland time is wrong: Preferences' os_log stamps read `1969-12-31 16:02:40-0800` although the kernel logs
  `calendar set from the PM6150 RTC: 1795107806 s`. Not explained yet.
- Poster providers on the root: CollectionsPoster, GradientPosterExtension, KaleidoscopePoster, AegirPoster, Unity
  posters, WeatherPoster, EmojiPoster, LegacyPoster, PhotosPosterProvider, ... (com.apple.posterkit.provider).
- Package `build/a71-ios26-poster.payload` (`6f18488e...`): /var/local/poster.sh (userspace/wallpaper26/poster.sh)
  run by launchd job org.a71.poster-probe as mobile: after 120 s lists configurations and the descriptors of the
  dynamic providers, then selects GradientPoster darkBlue.preset1 (or /var/local/poster.want); log
  /var/local/poster.log (pre-created 0666). The wallpaper-once job is removed. Job runs from the second boot.
- Kernel CI `44575804195` (8cf9a40, 2100-2117) succeeded; GitHub artifact downloads from here were reset, the owner
  downloaded it in the browser; kernel hash matches SHA256SUMS.
- `build/a71-ios26-all-d.img` = that kernel + all-b options with --usb and sweetdtlog=PosterBoard,GradientPosterExtension
  (cmdline 580 bytes), VERIFY OK `7ce69769...`. Expect `SWEET USB: SMMU bank ...` lines. USB log `logs/usb-ios26-all-d.txt`.

## 2026-11-19 22:52 — all-d booted; the SMMU guess was wrong

- all-d first boot after the TWRP flash: booted (owner). USB log `logs/usb-ios26-all-d.txt` (3.5 MB): Metal published.
- 2117 logged `SMMU SMR3 0x80000540 S2CR 0x00000001 matches the stream (type 0 bank 1)` and
  `SMMU bank 1 SCTLR 0x000000e0: translation already off`: bank 1 does not translate, USB DMA was already physical.
  So the USB SMMU is NOT the cause of the corrupt boots (my guess in the 22:30 entry is refuted); 2117 changes
  nothing on this phone and stays as a check. One clean first boot proves nothing (metal-a was clean too).
  Open: what overwrites memory on some first boots after a TWRP flash (shim blue screen before XNU, eventhandler
  assert, UEFI text in the log ring). Candidates not checked: RAM the bootloader/TZ still uses inside XNU's
  map (ADT memory map vs the A71 reserved-memory nodes), USB ACM log thread reading the ring while it wraps,
  DMA of other devices TWRP left running.
- Pending on all-d: second boot runs org.a71.poster-probe (poster list, dynamic descriptors, gradient select).

## 2026-11-19 — Settings hang traced to InterfaceNamer

- Owner reports broken Liquid Glass and frozen Settings. Donor 26bF reports similar glass artifacts. In all-d,
  build 36 returns `nil` for same-format BGRA8 2D views of mip level 1. The log also shows `flushticks=6` on
  the 59–60 Hz display, effectively a 10 Hz limit on framebuffer copies. These are separate observations.
- Built `build/a71-ios26-settings-glass.img` with the unchanged CI `44575804195` kernel
  (`db13e924739d982a67e83c86a0e2b448307f32538a6d51b96ac200e59235c138`), `sweetfb_hz=30`,
  `sweetdtlog=Preferences`, `sweetsample=Preferences sweetsamplems=8000`, and no payload replay. TWRP verified
  the 22,478,848-byte boot readback against `bc7f38621d9bac2bcfa6fe0a3ce417e07454b796cbef772511bb4ae409f20b7e`.
  USB capture `logs/usb-ios26-all-d-boot2.txt` is this diagnostic boot (it acquired COM7 before the new logger).
  Metal started. `flushticks=2`, one measured copy window reached 22.89/s. Visual comparison is pending.
- Repeated `Preferences[400]` t0 stack on 23G90: `__SCNetworkInterfaceCopyAllWithPreferences` →
  `SCDynamicStoreNotifyWait` → `mach_msg2_trap` (symbolicated against the local root's shared cache).
  `configd` starts and configures loopback. The SWEET tree already skips the IOKit daemon hold, but the donor
  Wi-Fi path's `MiniIONetworkStackStart` is a stub and the actual `IONetworkStack` only publishes with USB
  Ethernet, not serial-only USB. Patch 2118 moves publication of that existing service to UFS boot init.
  Patch applies to the staged source. Hardware verification pending. Owner reported an exit during testing;
  the captured segment kept sampling the same PID with no Preferences crash line. The exit remains unexplained.
- The new boot also repeats `hfs_getnewvnode` sanity-check failures (`hfs_cnode.c:946`, reason 0), seen in
  all-d. Cause and impact are unverified. No filesystem repair was attempted.

## 2026-11-19 — full-panel mode verified; dynamic poster inventory

- Settings fix is `60c653d` (xnu 2118) on `codex/a71-settings`. Actions run `44583376344` is building
  the Adreno kernel. The HFS ring and USB log show Preferences eventually leaving the InterfaceNamer wait
  on the old kernel, after several minutes, consistent with the fallback timeout.
- Owner reported bars across the top and bottom. The old run measured `scale 1 (pad 0,31)` for an
  828×1792 canvas on the 1080×2400 panel. `build/a71-ios26-full-panel.img` uses the same 44575804195 kernel
  and diagnostic args with `--fb-scale 2`. TWRP verified the 22,478,848-byte boot readback SHA-256
  `184ab2f62455ad598ec30b3db811cc4e865911496e078958fbf011c27d853b5b`. USB reported `scale 2 (pad 0,0)`
  and the owner confirmed both bars disappeared. This setting slightly stretches the canvas vertically.
- Read `/private/var/local/poster.log` in TWRP (5,866 bytes, saved in ignored `research/wall/`). Lock role
  has a Mercury `space.dynamic` config and a selected CollectionsPoster `5010`. Home role has zero
  configs (`-2203`). GradientPoster descriptors fail `-2218`, creation fails `-2220`; old USB trace lists
  `darkBlue.preset1.DOWNLOADABLE`. Owner clarified they want the stock iOS 26 wallpaper. The 23G90 root
  contains MercuryPosterExtension.appex (`com.apple.MercuryPoster`) and its `default.fluidity` resource.
  PosterBoard advertised `fluidity.dynamic` and four fixed variants in all-d. The recipe now requests
  `fluidity.dynamic`. Selection and visible wallpaper still need verification. The full-panel boot did
  not replay a payload.
- Owner also requested Dynamic Island. The phone cache was read in TWRP and stored under ignored
  `research/mg/`. It has `ArtworkDeviceSubType=1792` and the `SupportsDynamicIsland` override is absent.
  Plan to test the targeted capability override with a restore payload before changing the artwork subtype.
- Added `TODO.md` at the owner's request to track the five UI items and their acceptance checks.

## 2026-11-19 — Metal mip views in CI; wallpaper and Island test packages prepared

- `a91329b` adds a pinned iOS 26 Metal build using Redmi `4ff9b8e` plus an A71 patch for same-format, 2D
  views of mip ranges. Views keep the original Gallium resource and translate the relative level for texture
  sampling, image bindings, CPU transfers, rendering and clears. Locally verified that the patch applies
  to the generated source with `git apply --check --whitespace=error`. Actions `44584865459` is building the
  `SweetMetal2` compatibility bundle. Compiled and visual results pending. This patch does not address all
  Metal features, including render pass attachment level on a parent texture.
- `build/a71-ios26-stock-dynamic-wall.payload` sets the existing poster probe's `poster.want` to Mercury
  `fluidity.dynamic`. SHA-256 `c874a5801805ffc32346783b1fdc49a35398b96135afb185a726665a8cc65ac1`.
  Check whether `poster.want` exists in TWRP and preserve any existing file before applying. Mercury being
  listed as a descriptor does not verify rendering. The root recipe skipped Bergamota's Mercury-specific
  renderer because its dylibs were absent. Test on the current NativeMetal first.
- `build/a71-ios26-island-test.payload` appends just `SupportsDynamicIsland=true` to the real cache and copies
  the original into root-only `/private/var/local/mg-backup/MobileGestalt.plist.before-island`. Validated binary
  plist round trip and exact preservation of all other keys. Test SHA-256
  `aea963f7c08f9e8c6cfd61609ddd68a602db87ec11542581a817224a488b2eaf`, restore payload
  `5cd50f06f7d6b7efbeff7c8b9caad1d9a737c5fcc5f346aab73de0d55324369d`. Recheck cache hash in TWRP before applying.
- No wallpaper or Island test payload was written. The verified full-panel image is on `boot`. Settings CI
  `44583376344` and Metal CI `44584865459` were still building as of 23:11 local. Next hardware run should
  isolate settings kernel behavior, then verify wallpaper selection/appearance and Dynamic Island.

## 2026-11-19 — stock wallpaper picker check

- Owner checked the wallpaper gallery and reports old iOS 8-style choices instead of the stock iOS 26 Dynamic option. This verifies the gallery symptom only. Direct `fluidity.dynamic` selection remains pending.
- Built `build/a71-ios26-poster-test.img` (22,478,848 bytes, SHA-256 `d1f705896597904fc0ab71afea090c1f49dde3bb1f61be399153ddf20df43a57`) using CI `44575804195`, `--fb-scale 2 --fb-hz 30 --payload --dtlog PosterBoard,MercuryPosterExtension`. Requested TWRP and confirmation to write the verified wallpaper payload. Neither image nor package was written yet.
- Owner clarified that the iOS 26 wallpaper can be selected manually but appears black. Existing USB capture shows MercuryPosterExtension launches but no cause. Built boot-only trace `build/a71-ios26-mercury-trace.img` (22,478,848 bytes, SHA-256 `b65e9b2aaf27400f4abc9cfd9d7cb0225a97f3d92645639e8180b380260b0025`) using the same kernel and boot options without `--payload`. Awaiting TWRP for manual reproduction. No write to the phone this turn.
- TWRP flashed only `boot` with `a71-ios26-mercury-trace.img` and verified SHA-256 `b65e9b2aaf27400f4abc9cfd9d7cb0225a97f3d92645639e8180b380260b0025`. Boot reached launchd, PosterBoard and a SpringBoard wallpaper client (USB log `logs/usb-ios26-all-d-boot2.txt`, new boot args `sweetdtlog=PosterBoard,MercuryPosterExtension`). Waiting for manual wallpaper selection and visual result. No wallpaper payload written.
- Mercury trace shows `NativeAdreno ABI + Metal discovery published` before the extension starts. MercuryPosterExtension PID 286 loads SweetNativeMetal but reports `native A618 backend unavailable: ... no msm device to open`. PosterBoard and SpringBoard report the same error in this boot. The GPU is live for backboardd. Next trace the service match and open return for the wallpaper process. A manual repro result for this new boot is still pending.
- Owner reports black on the wallpaper test and that the old wallpaper remains. USB COM7 stayed up and GPU submissions continued. Mercury repeated `no msm device to open`. The kernel only allows backboardd and AegirPoster. Patch 2119 adds MercuryPosterExtension to the bounded extra slots. Apply check passed. Hardware result pending.
- Patch 2119 commit `ad17b72` is building in Actions `44586441232`. No change to the phone after the Mercury trace boot.
- Metal CI `44584865459` succeeded. Downloaded artifact `14560783206` and verified SHA-256 for all six bundle files against `build.json`. Installation and visual check pending. Kernel CI `44583376344` (Settings) and `44586441232` (Settings plus Mercury) are still compiling XNU.
- Settings CI 44583376344 succeeded and kernel hash a9ca1d30e6017fb0ac2455cbf33e75faa571ccc2eefc6327522b82e436b6860c was verified. Flashed only boot with build/a71-ios26-settings-2118.img, verified SHA-256 7c797242df365287724e18525ba6faa4d80c34faa31ad6f4e85816c6e0f54cf4, and requested reboot. No payload. Boot and Settings results pending.
- Built the verified Metal test package `build/a71-ios26-metal-mip-test.payload`, SHA-256 `d5690cad4fb932ef5fd530109d8139a31c30fad63373a41894ce8b865ac79d15`. Owner requests installation. Old build 36 package is available as rollback. Awaiting TWRP before installation.
- CI 44583376344 booted and USB verified `IONetworkStack published`, `configd opened IONetworkStack user client (type 0): 0x0`, and `exec Preferences`. UI result pending. Built `a71-ios26-settings-metal-mip.img` (SHA-256 `1d0c436af5980ccf7e098fa544345a0e489200294e80024583312b1007b80b79`) with 2118 and payload enabled. Waiting for TWRP.
- Owner confirmed Settings works on 2118. On old Metal build 36, blur and gradients still appear gray, black, or otherwise wrong. COM7 present, TWRP ADB absent; new Metal install pending.
- TWRP verified the staged mip Metal payload and 2118 payload-enabled boot hashes given above. Reboot requested. Wait for SWEET PAYLOAD and visual blur check.
- USB log `logs/usb-ios26-settings-glass.txt` confirms 2118 published IONetworkStack, the mip bundle installed 9/9 entries with errno=0 and Metal discovery published on A618. Visual result pending. Combined 2118+2119 CI 44586441232 was still building.
- Owner reports no substantial visual improvement with the installed mip-view bundle. New USB capture has no logged `a texture view is not implemented` refusals so far, but the general request trace covers only the first 48 calls and is not matched scene-for-scene. Next collect a targeted CoreAnimation draw trace of one bad blur and check the destination attachment level. Mercury kernel CI 44586441232 still compiling.
- TWRP backed up existing poster.sh and verified diagnostics payload 769651505A4E7BAB293DA1CE4031716C913831CA53972D497E8808F1F7FC72FA. Existing 2118 payload-enabled boot verified again; reboot requested. Wrapper waits 150 seconds, then changes the drawlog flag before invoking the original job. Awaiting capture.
- CI 44586441232 succeeded; verified kernel SHA-256 9af42db32279362cc3fbd9e9476f0a01c32a53a5d923ca5f4056be4a64ab3872. Packed mercury-2119 boot SHA-256 5365E374937BF16EEDFB14BC12DC5FE8DDCCC8219056349749F6F92F83815879, pending flash.
- Draw trace boot succeeded, diagnostics package installed 4/4. First boot showed shell jobs starting before payload application; no DRAWLOG marker through 219 s despite compositor activity. Next boot should pick up the installed wrapper. Owner asked to enter TWRP for combined 2119 boot and a new capture.
- TWRP verified and rebooted mercury-2119.img; awaiting logs.
- 2119 USB confirmed `MercuryPosterExtension open type=0x4147` and NativeAdreno ABI1 A618. Mercury coordinator now fails to compile an AIR intrinsic (`argument 3 is not a constant`, block 0 instruction 26 opcode 17). Wallpaper rendering still blocked; GPU access is verified.
- Through 232 s on 2119, draw trace did not arm despite compositor swaps. Mercury specifically fails compiling VariableBlurrer::downsample (non-constant intrinsic argument 3) and VTMTSComputeFunction1x1 (unsupported llvm.umax.i32). 2119 was verified and booted; shader failures remain. Next read poster.log and marker from TWRP to see whether the wrapper ran, then restore or revise it.
- TWRP readback after 2119: poster.sh wrapper is present mode 0755, trace flag is mode 0666 but still contains initial 1500. poster.log only has earlier job output. Requested a normal reboot on the same 2119 boot without writes to see whether the wrapper works while the phone remains awake.
- Second 2119 boot after read-only TWRP inspection: owner sees prolonged Apple logo. USB stays online; SpringBoard repeatedly execs through 148 s and framebuffer remains at 2 swaps. No kernel panic line. Draw trace not armed. Return to previously verified 2118 boot to recover UI; TWRP needed.
- Owner reports touching the display during the stuck boot. USB still shows repeated SpringBoard execs and 2 swaps through 168 s. No evidence ties those restarts to touch. TWRP ADB still unavailable for 2118 rollback.
- Recovery: TWRP verified 2118 boot SHA-256 7c797242df365287724e18525ba6faa4d80c34faa31ad6f4e85816c6e0f54cf4 and reboot requested. Awaiting visible UI.
- Owner clarified they wanted to boot with 2119 and did not want a rollback. The 2118 write and reboot had already completed by the time the interruption arrived. Stop any further writes; report actual 2118 state.
- 2118 rollback also stalls at Apple logo (owner), COM7 and repeated SpringBoard execs, 2 swaps through 99 s. Prepared recovery payload restoring donor Metal build 36 and original poster.sh and removing only the temporary drawlog flag. Awaiting TWRP to apply.
- TWRP verified recovery payload SHA-256 822cbe870bd79a95d1e067431dfccc4acbb4e2b89b31f9111b1c984f88af27ab and 2118 payload-enabled boot SHA-256 1d0c436af5980ccf7e098fa544345a0e489200294e80024583312b1007b80b79. Reboot requested; checking installer and UI.
- First recovery boot reported panic by owner. Saved `logs/ios26-recover-ui-panic.txt` (479549 bytes, flush 9) is an earlier boot ending in power-key shutdown; no fresh panic text. TWRP confirmed trace wrapper and marker still installed. Requested normal reboot without flashing again so pending recovery payload can run.
- Recovery package applied 12/12 (errno=0), GPU opened, but owner still reports Apple logo and USB shows SpringBoard repeatedly launching with 2 swaps through 88 s. Built 2118 CPU-only recovery image SHA-256 1A6FD6DF0F12646B62E317708A86394A26CD617E0ACEABCAAEC8B6896689BCFB (touch, keys, USB, no payload). TWRP needed.
- TWRP verified CPU-only 2118 boot readback SHA-256 1a6fd6df0f12646b62e317708a86394a26cd617e0aceabcaaec8b6896689bcfb. Reboot requested.
- CPU-only 2118 reached launchd/backboardd/SpringBoard but repeated SpringBoard starts and remained at 2 swaps through at least 78 s. Observed HFS runtime inconsistency warnings again. Neither removing the draw trace and restoring build 36 nor disabling GPU restored the UI. No filesystem repair attempted. Next collect fresh TWRP ring and investigate persistent state/read-only filesystem checks.
- Fresh CPU ring `logs/ios26-recover-cpu-stall.txt` shows repeated SpringBoard voluntary exits on SQLite 8458/ERANGE reading `_ATXInfoSuggestionStore.db-wal`. Built reversible package 90ffcbf4fe847dbc3d4c83bb6ba25852efff102d8ead1142edeb8b1d2744dc5c moving the db/wal/shm each to a previously absent `.a71-backup-20261119` sibling. TWRP verified package and boot image ae8da3bff51501b77396d722c70a54397ae44050d76b619f817f30b6f7d6ac92 (2119; existing Metal build 36). Reboot requested. No fsck repair.
- Owner confirmed A71 reached iOS again on the 2119/ATX recovery boot. USB recorded all three rename ops with return 0 and framebuffer resumed (42 swaps at 79 s). Original ATX files remain under the backup suffix. Build 36 remains installed. Owner clarified they want blur draw tracing, not a watchdog.
- Prepared 2120 for blur tracing: optional `sweetpayloaddelay` boot arg delays verified package installation after root mount, default unchanged. Next run can install a temporary drawlog marker after backboardd starts, without changing the poster job. Local patch application check passed.
- Diagnostic kernel 2120 at fa4a06f, Actions 44593327297, queued. Prepared but not flashed.
- Owner returned to TWRP. Read-only check verified archived ATX db/wal/shm and recreated live database. Requested normal reboot on 2119 without writing. Marker package SHA-256 63649c1473ff4ba8d4a1f243b07e1d8e262c8c12318e48908da191b85e223e8e; not staged, pending 2120.
- Owner declined to wait for diagnostic kernel 2120. Continue with current 2119; no 2120 or drawlog marker installed.
- Owner asks for substantive blur fixes and Wi-Fi, and declines the trace-only kernel. On 2119 second boot USB observed frames resuming at uptime 92 s. Native Metal patch fixes render/clear honoring colour attachment mip levels (including view offsets and framebuffer cache key) and lowers LLVM unsigned maximum; staged patch applies after mip-view patch. Metal CI needed. Wi-Fi diagnosis started.
- Native Metal CI 44594040990 at 3c6a578, queued.
- Wi-Fi: current USB log has `/dev/wlan ready` but no `exec wland` or `exec wifid`. Local launchd plist gates wifid on a WLAN ADT node. Added packer `--wifi` (same ADT helper, pmem, WLAN SMMU and wland log). `build/a71-ios26-wifi-2119.img` SHA-256 307338d043e76f511053c5a5886cebc7634d4effd46759771331a01bf324b02e. Verified wifi30 wland/netsvc manifests. Prepared 85-entry `build/a71-ios26-wifi-2119.payload` SHA-256 0580d264b45d1cc7ddccecdd558e9383106789f5be5bd7832115b7c518d3dfc5 with local A71 firmware and rmtfs FILE copies only (no modem partition writes), merged launchd and original backup. Before flashing compare live launchd.plist to research/wall/launchd.plist.poster, rebase if different, and preserve existing WLAN files. TWRP requested. No package installed.
- Wi-Fi TWRP: live launchd hash matched base dcc5a39dc892a75dbfee3e102852fefb3cae411d2e03b161fdb82b5f132ac1f8, no existing wland/netsvc/rmtfs/modem files. Verified Wi-Fi payload and boot readbacks against exact hashes above, requested system reboot. wland launch job is expected on second boot.
- First Wi-Fi boot: USB confirmed `exec wifid` and verified installer 85/85 errno=0; wland job will be read on next normal reboot. Owner asked to reboot after reaching the screen. No en0 or association yet.
- Metal CI 44594040990 succeeded; verified the bundle hashes against the manifest. TWRP staged 9-entry Metal package d2f709472dd5077184ccc7ffb051da5f75e3001b1acd9265408d9e9f254e5469 and verified Wi-Fi 2119 boot readback. Reboot requested. Pre-reboot TWRP inspection: wland executable exists, no /var/local/wland.log and no wland.off.
- Latest captured Wi-Fi boot reaches WLFW FW READY, WMI mission mode and 12 CE rings, then `bridge: /dev/wlan open: en0 and wifid` with no subsequent kernel `flame wlan: the radio is up` / FW_HELLO or en0 publication. Early TFTP misses are recoverable (wlanmdsp requested from /readonly/firmware/image and FW READY followed). USB not present after Metal reboot yet, cannot verify Metal installer from USB.
- Subsequent USB log confirms revised Metal payload installed 9/9 errno=0 on Wi-Fi 2119. Visual verification pending.

## 2026-11-20 — Wi-Fi resets the phone; first Liquid Glass in Control Center; no-Wi-Fi Metal image flashed

- Owner on Wi-Fi 2119 + Metal 3c6a578 (blur attachments): lock screen almost invisible and flickering; **Control
  Center shows glass for the first time**; then everything went down and the phone restarted.
- Observed: in `logs/usb-ios26-settings-glass.txt`, three Wi-Fi boots (lines 728560, 733698, 738848) end right after
  `wlfw: wlan config sent, mission mode on` / `radio: ce: host memory f0000000..f00a5000` / `12 rings programmed, rx
  buffers posted` / `bridge: /dev/wlan open`. The next lines are a fresh `Darwin Kernel Version` or UEFI ABL text: an
  instant reset with no panic text, twice confirmed, the third capture just stops. TWRP ring of the last boot
  (`logs/ios26-metal-blur-crash.txt`, seq #7) also stops without panic. Guess: WLAN firmware DMA into the CE host
  memory at 0xf0000000 (or an XPU/SMMU violation) makes TZ reset the SoC. Not proven.
- Also in every recent boot: `hfs: BlockMarkFreeInternal() trying to free unallocated blocks on volume iOSRoot` and
  `Runtime corruption detected on iOSRoot` (hfs_cnode.c:946, VolumeAllocation.c:3362). No fsck attempted.
- No Metal userspace errors in the last boots because sweetdtlog was not set. Earlier 2119 boot: Mercury refused
  `llvm.umax.i32` (lowered in 3c6a578) and `VariableBlurrer::downsample` "intrinsic: argument 3 is not a constant"
  (block 0, instr 26, opcode 17), not addressed yet; donor source in `research/ios26/native-glass-src/donor/tools/mesa/air/`.
- `build/a71-ios26-metal-nowifi-2119.img` = same CI 44586441232 kernel (9af42db3...) and options as wifi-2119
  without `--wifi` and without `--payload`, plus `--dtlog MercuryPosterExtension`. TWRP boot readback SHA-256
  `86fa6155b16a26d622e38eafb99d014923029ac20c58bd083f08b440bf146568`. `adb reboot` from TWRP came back to TWRP (ring unchanged, seq #7: iOS never ran), so reboot from the TWRP menu (Reboot -> System). USB log to
  `logs/usb-ios26-metal-nowifi.txt`. The wland launchd job and Wi-Fi files from the wifi payload stay on the root.
- no-Wi-Fi boot (owner rebooted from TWRP; `logs/usb-ios26-metal-nowifi.txt`): Metal published, but backboardd
  traps (sig 5) three times, heap strings `IOHIDEventSystem creation failed` and a dlopen of
  `/System/Library/HIDPlugins/SessionFilters/TactSwitchHIDSessionFilter.plugin/TactSwitchHIDSessionFilter`
  (message cut). Never seen in earlier boots. Also crashing: cryptexd, CommCenter, audiomxd, liveactivitiesd,
  UserEventAgent, chronod ("Too many corpses"). launchd then logged `Rebooting to device recovery environment`.
  Owner: the next boot restarted before the Apple logo, then a panic. Panic text not captured yet.
- Guess (not proven): the root filesystem was damaged by the repeated hard resets during the Wi-Fi boots; the
  HFS `Runtime corruption detected on iOSRoot` / `freeing unallocated blocks` lines support it. Next: in TWRP,
  read the TactSwitch plugin with `tools/a71-hfs-get.py` and compare with the reference root; a read-only fsck
  if TWRP has one. Any repair needs the owner's OK.
- Correction (log survey, all logs/ files): HFS `Runtime corruption detected on iOSRoot` is NOT new. The first iOS 26
  boot (`ios26-full-cpu-first.txt`) has none; every later boot has it, from the second boot
  (`ios26-touch-springboard.txt`, 2026-11-19 20:51) on, long before Wi-Fi. So the Wi-Fi resets did not start it.
  Read-only compare in TWRP: TactSwitchHIDSessionFilter (binary + Info.plist), backboardd, audiomxd and
  UserEventAgent are byte-identical to `build/ios26-root-a71-23G90.img`. Damaged files are not shown. The
  backboardd loop is so far only seen on the no-Wi-Fi image, so the image difference (no sweetpmem /
  sweetsmmuwlan / sweetnull=wland / sweetpayload, no WLAN ADT node, sweetdtlog=MercuryPosterExtension) is an
  equal suspect. dyld shared cache compare in progress.
- dyld shared cache: all 75 files on the phone byte-identical to the reference root. No damaged system file found.
- `build/a71-ios26-nowifi-b-2119.img` = wifi-2119 options minus `--wifi` only (keeps `--payload`, no dtlog), to
  split the backboardd loop between the Wi-Fi args and payload/dtlog. TWRP boot readback SHA-256
  `7158452737401877f97a9a9510e8fae0e3293281dd9a77c943d48bcf1d8dc726`. USB logger still appending to
  `logs/usb-ios26-metal-nowifi.txt`. Result pending.
- nowifi-b booted (rebooted by `adb shell twrp reboot system`, which works; plain `adb reboot` returns to TWRP).
  No backboardd crash, no IOHIDEventSystem failure, Metal up: the loop on the first no-Wi-Fi image came from
  `sweetdtlog=MercuryPosterExtension` or the missing `sweetpayload=1`, not from the root. Owner: everything
  flickers, lock screen not visible, Control Center appears briefly and vanishes. No reset so far without Wi-Fi.
- Cause found in the USB log: backboardd `the draw failed` 389 times, always `colour attachment 1 is 2W x 2H and
  attachment 0 is W x H` (256/128, 128/64, 448x960/224x480 ...): CoreAnimation's blur writes level 1 of one
  target and level 0 of another in one pass. Metal draws such a pass into the smallest common area; our check
  (air_metal.c) refused it, so those passes vanished (3c6a578 made the levels real, which exposed it).
  Fix: render size = MIN over colour (and depth) attachments, regenerated
  `userspace/native-metal/ios26-blur-attachments.patch` with `research/ios26/make-attachment-patch.py`;
  air_metal.c part applies to the local donor tree. Commit 34846e7, Metal CI `44690309011` (public repo, free minutes) building.
- Wallpaper (Mercury `fluidity.dynamic`, black): `research/mercury/default.metallib` (ignored; read from the
  reference root) has `VariableBlurrer::downsample` = `air.write_texture_2d.i16.v4f16` + `air.sample_texture_2d`.
  "argument 3 is not a constant" is the write's mip level (tex, coord, value, lod): the kernel writes a
  computed level. air_intrinsics.c only takes a constant 0, and an image binding is a single level
  (`pipe_image_view.u.tex.level = first_level`, air_metal.c ~3911). Planned fix: for a non-constant lod emit an
  if-ladder of image stores, branch k storing to an extra image slot bound by the host to level k of the same
  texture (new air_resource fields: level slot base and count). Not written yet.
- Metal CI `44690309011` (34846e7, attachment size fix) succeeded; artifact `14608602053`, all six bundle files
  match build.json. Package `build/a71-ios26-metal-attsize.payload` (9 entries) TWRP VERIFY OK
  `26835c7ccecb65b6e121a67af04772477776dbf5ad3edff7c81102fcfc6c9168` (owner asked to install it). Boot is
  nowifi-b (`71584527...`, sweetpayload=1). Rebooted with `twrp reboot system`. Result pending.
- Wallpaper fix written: `userspace/native-metal/ios26-image-write-levels.patch` (generator
  `research/ios26/make-image-level-patch.py`), applied in CI after the blur patch. Checked: applies alone and
  stacked on the blur patch to the donor air files. Commit da20e9a, Metal CI `44690970901` building. Not compiled
  before this run.
- **Attachment-size Metal works (owner: flicker gone).** USB: payload 9/9 errno=0, Metal published, `the draw failed`
  0 times this boot (389 before), swaps up to ~24/s, no backboardd crash. Lock screen / CC glass visual detail
  not yet reported.
- Owner on attachment-size Metal: glass in the Settings search bar disappears now and then. USB for this boot: no
  `the draw failed`, no refused pipeline, GPU completion failures 0, gpu/latch timeouts 0; swap_wait_timeouts
  674 and late_scheduled ~160-200 per 5 s window. No logged cause; needs a draw trace of the moment it vanishes.
- Metal CI `44690970901` (da20e9a, + image write levels) succeeded; artifact `14608981486`, 6/6 files match
  build.json. Package `build/a71-ios26-metal-levels-sync.payload` (12 entries: bundle + empty
  `/var/local/sweet-native-sync-commit`, owner OK for the race test) TWRP VERIFY OK
  `b335b8316546f9de3b9be641f67336264720db51c305a5667fe4138f1a825d53`. Boot unchanged (nowifi-b). Pitfall: in Git
  Bash run a71-payload.py with MSYS_NO_PATHCONV=1, or `/System/...` becomes `C:/Program Files/Git/System/...`.
  To undo the race test: rm `/var/local/sweet-native-sync-commit` (payload `rm:`).
- First boot after writing levels-sync: owner saw a panic; nothing on USB (log stops at the 11:58 power-off), TWRP
  ring (`logs/ios26-levels-sync-panic.txt`) is the previous boot. The payload area still holds the whole
  levels-sync package (magic + sha b335b831), so the panic came before root mount / payload install: not the new
  Metal. Matches the known random early panics on a first boot after TWRP. Rebooted unchanged.
- Second boot: payload `finished 12/12 errno=0`; backboardd `command buffers wait for the GPU at commit` (race test
  active); Metal published; MercuryPosterExtension opened the GPU; `the draw failed` 0. Mercury's own shader errors
  are not on the console (no sweetdtlog). Visual result (wallpaper, Settings/CC glass) pending from owner.
- Owner: wallpaper still black with the image-level Metal. Mercury's shader result is not on the console.
  Built `build/a71-ios26-nowifi-mercurylog.img` = nowifi-b + `--dtlog MercuryPosterExtension,PosterBoard` (keeps --payload),
  SHA-256 `e47ec7a986b068e2d00fe8987d3a342862c115b931f627514aa2c2e608cfe28b`, TWRP boot readback verified. Also
  tells whether dtlog or the missing sweetpayload caused the earlier backboardd loop.
- Owner on levels-sync: iOS 26 wallpapers vanished from the wallpaper list; Settings search glass still vanishes;
  CC a bit better, but pressing a button makes the buttons around it lose glass, sometimes all of them. So waiting
  at commit (sweet-native-sync-commit) does NOT fix it: a CPU-side completion race is unlikely. Flag still on.
- levels-sync boot: PosterBoard aborts twice (sig 6, same pc), never seen before; likely why iOS 26 wallpapers left the list.
- mercurylog boot (dtlog MercuryPosterExtension,PosterBoard + payload): no backboardd loop (so the earlier loop was
  the missing sweetpayload=1 / no-payload image, not dtlog), but ~10k console lines in 100 s; owner: touch not
  working (kernel touch init identical to good boots; guess: console flood). Mercury: "argument 3 is not a
  constant" is gone (level slots work); new refusal `a bitcast from 1 x 32 bits to 4 x 8 bits` (4x, block 1434)
  -> coordinator not set up ("trying to update environment for a coordinator that isn't there" x398).
  Fix: any same-size bitcast via nir_bitcast_vector, added to ios26-image-write-levels.patch (0f18b42, Metal CI `44693533395`).
- Metal CI `44693533395` (0f18b42, + bitcast) succeeded, 6/6 files match. Package `build/a71-ios26-metal-bitcast.payload`
  (bundle + rm of /var/local/sweet-native-sync-commit) VERIFY OK `689e9eab...d38b`. Boot
  `build/a71-ios26-nowifi-mercuryonly.img` (nowifi-b + dtlog MercuryPosterExtension only) readback
  `23eebb59439172f6fc88e1e703a69ad3a0f194c75836beba35d6a64eacd9aeb6`. Rebooted.
- bitcast boot: payload 10/10; bitcast refusal gone. Next Mercury refusal: `intrinsic: air.pack.unorm.rgb10a2.v4f32`
  (4x). Added pack/unpack unorm rgb10a2 (saturate, x1023/x3, round-even; R low bits, A top two) to
  ios26-image-write-levels.patch.
  Commit 5973a66, Metal CI `44694428663`.
- Owner: transparency still vanishes (bitcast build, sync flag removed). No logged error. Plan: driver draw log
  (`/var/local/sweet-native-drawlog`, SweetNativeDrawLog.inc) arms only when the file appears or changes after
  backboardd started, so it needs the delayed payload of kernel 2120. CI 44593327297 (fa4a06f, 2118-2120)
  kernel downloaded, SHA256SUMS OK, `research/ci-44593327297/`. Prepared, not written:
  `build/a71-ios26-2120-drawlog.img` (nowifi-b options, 2120 kernel, `--payload-delay-ms 150000`) SHA-256
  `f1f759c1f6817164c6429a3db6bbe9b36472f166497bb3f959a9b0b5d204f06b`, and `build/a71-ios26-drawlog-on.payload`
  (text /var/local/sweet-native-drawlog=1500) `7585fd0dc658353d2ff458d2845030e8eee8506b69c9ef1e52c2f4d6e58b7be8`.
  Order: first install the rgb10a2 Metal normally, then this.
- Metal CI `44694428663` (5973a66, + rgb10a2) succeeded, 6/6 match. `build/a71-ios26-metal-rgb10a2.payload`
  `b426046a9d485f9492ccfa62e93c3707cec23c3470ce81df33d23ceff250ca2e` written in TWRP; boot still mercuryonly (23eebb59).
- rgb10a2 boot: payload 9/9; rgb10a2 refusal gone. Next: `intrinsic: air.pack.unorm4x8.v4f32`. Added pack
  unorm/snorm 4x8 and 2x16 and unpack snorm4x8, unorm/snorm2x16 (NIR opcodes) to the levels patch.
  Owner: same problems (black wallpaper, glass vanishing).
  Commit 61fddec, Metal CI `44695495470`. Next TWRP: this bundle + drawlog flag in one package with the 2120 delayed image; boot 1 traces the glass (old bundle loaded), boot 2 runs the new bundle for Mercury.
- Instead of one refusal per build: listed every air./llvm. function in Mercury's default.metallib and
  VideoToolbox's default.metallib (both from the reference root, in ignored `research/mercury/`) and checked each
  against the frontend. Missing were only: llvm.smax (Mercury, i16), llvm.bswap (VideoToolbox), air.fast_sincos;
  plus the pack family already added. Added sincos (pointer or struct result), llvm.smax/smin/umin, llvm.bswap.
  Cancelled 44695495470 (lacked these). Caveat: this checks names only; an argument shape the frontend does not
  take can still be refused.
  Commit 1ff2038, Metal CI `44695754790`.
- Metal CI `44695754790` (1ff2038) succeeded, 6/6 match. Prepared for the next TWRP visit (not written yet):
  `build/a71-ios26-metal-all-drawlog.payload` (bundle + /var/local/sweet-native-drawlog=1500)
  `0c3e6d4c3716b681651fbaf29fd5a217ec73a503746d22e5524c1a2478665ee3`; boot `build/a71-ios26-2120-drawlog.img`
  (2120 kernel, payload delay 150 s, dtlog MercuryPosterExtension) `3e439df5ada2195ae74c5d3d11ada9c43fd1ff25b929bd51a4462da6c36168c2`.
  Boot 1: package lands at ~150 s, the drawlog file appears after backboardd started -> trace (old bundle loaded).
  Boot 2: new bundle for Mercury. Afterwards remove the drawlog file (it re-arms only on change, harmless).
- Written in TWRP: metal-all-drawlog payload VERIFY OK, boot 2120-drawlog readback 3e439df5 OK. Rebooted.
- **All Mercury shaders compile now** (1ff2038 boot 2: compute pipelines for VTMTSComputeFunction1x1,
  VariableBlurrer::downsample/fallbackCopy, no `pipeline refused`). New blocker: `couldn't set up coordinator:
  ... makeTexture failed for format astc_6x6_srgb` (albedo-a.ktx). The format table had no ASTC. Added ASTC LDR
  (Metal 186-200 sRGB, 204-218 LDR -> PIPE_FORMAT_ASTC_*), caller row stride and slice size counted in blocks.
- Draw trace (`logs/drawlog-glass-20261120.txt`, 1501 draws, ~8 frames, owner pressed CC buttons): every frame
  has 2 `glass_background_no_bleed` draws and a downsample/narrow_blur chain; no failed draws. Early frames blur
  through separate 192x384 / 320x704 textures; later frames blur 640x1408 -> 640x1408 (rt and sampled texture the
  same size: probably the same texture, different mip levels). The log shows neither texture identity nor level,
  so this is a guess. Added `#id/L<level>+<levels>` to rt and tex entries of the draw log for the next trace.
  Commit c146e30, Metal CI `44698113596`.
- Metal CI `44698113596` (c146e30, ASTC + draw log ids) succeeded, 6/6 match. TWRP: `build/a71-ios26-metal-astc.payload`
  VERIFY OK `917bb91b...3f2e`, boot back to mercuryonly (23eebb59, no payload delay) so the new bundle runs on
  the first boot. Draw trace with ids is the next TWRP visit (2120 image + a payload that rewrites the drawlog file).
- ASTC boot (c146e30, mercuryonly image): payload 9/9; makeTexture astc_6x6_srgb passes now. Next Mercury error:
  `albedo-a.ktx: textureCreationFailed("Failed to create staging buffer")` with no driver line before it:
  `newBufferWithBytesNoCopy:` always returned nil. Implemented as copy into our own buffer, caller's deallocator
  run when that buffer is freed (associated object). Owner: transparency still vanishes (trace with ids next).
  Commit 083a576, Metal CI `44699219394`. Next TWRP: 2120-drawlog image + payload (this bundle + rewritten drawlog file): boot 1 traces with ids (ASTC bundle loaded), boot 2 runs NoCopy for Mercury.
- Owner asked for a shorter wait: `build/a71-ios26-2120-drawlog75.img` (payload delay 75 s; last time 150 s landed at uptime ~180 s, Metal restart of backboardd ~60 s) SHA-256 `5ec226ee862bcd91de6d079068309793e9ea017081fbee996e551f2552946b0f`. Not written yet.
- Metal CI `44699219394` (083a576) 6/6 match. TWRP: `build/a71-ios26-metal-nocopy-drawlog.payload` VERIFY OK `7ec690aa...345e`, boot 2120-drawlog75 readback 5ec226ee OK. Rebooted.
- **Glass cause found** (trace with ids, `logs/drawlog-glass-ids-20261120.txt`; console lines are split, rejoin
  `|backboardd|` pieces to read it): CoreAnimation's variable blur builds its mip chain IN PLACE.
  DRAW 7 renders texture #c298 (448x960, 3 levels) from #c288; DRAW 8/9 `variable_blur_downsample_frag` render
  into #c298 while sampling #c298 (L0+3) in the same draw; then `glass_background(_sdf)_no_bleed` samples all 3
  levels of #c298. Same resource as colour target and texture in one draw: no ordering guaranteed on the
  Adreno. Fix (in ios26-image-write-levels.patch): render_draw records its colour targets; bind_stage gives a
  texture that is also a target a GPU copy of all its levels (resource_copy_region just before the draw,
  copy resource kept per texture). Logs "a draw samples its own colour target" (first 4).
  Commit 08d807d, Metal CI `44700658186`.
- NoCopy boot: staging buffer works (`newBufferWithBytesNoCopy: N bytes copied`). Next Mercury error:
  `Failed to create blit encoder for private texture upload`: the driver had NO blit encoder
  (-blitCommandEncoder returned nil). Added SweetNativeMetalBlitEncoder: buffer->texture, texture->buffer,
  texture->texture (via a 16 B/texel temp), buffer->buffer, fillBuffer, no-op fences/sync, generateMipmaps
  not done (logged), unknown selectors swallowed (logged once). Copies run at encode time through the
  replaceRegion path. Also blitCommandEncoderWithDescriptor:. Cancelled 44700658186 (glass only).
  Commit 6a0e11f, Metal CI `44701198795` (glass copy + blit encoder).
- Metal CI `44701198795` 6/6 match. TWRP: `build/a71-ios26-metal-blit-glass.payload` VERIFY OK `36aaf7b7...edeb`, boot mercuryonly (23eebb59). Rebooted.
- **Two panics in a row after writing blit-glass** (owner saw "exit code 5"). TWRP ring (`logs/ios26-blit-panic.txt`):
  root mounts (dirty, non-journaled), then 43x `hfs_swap_BTNode: offset #0 invalid (0x0000) (blockSize 0x2000
  numRecords 98)` `node=28370 fileID=4` (catalog), tzinit `force_system_dataset() failed: Input/output error`,
  `pid 18 exited ... exit 5`. Payload area still holds blit-glass (not applied): not the new Metal.
  Raw read in TWRP: catalog node 28370 (fs blocks 3851251-3851252, catalog extent 7) is valid on disk: kind -1,
  height 1, num 98, offsets 14,106,184..., sha256 aaf024b9... Volume not journaled. So iOS's kernel gets the
  node's second 4 KiB as zeros while Linux reads it fine. Guess: our UFS driver mishandles that LBA (e.g. a read
  with recovered-error sense), not proven. Proposed: rewrite those two blocks with the identical bytes (auto
  mode refused without explicit owner OK); asked the owner.
- Owner OK: rewrote catalog node 28370 (fs blocks 3851251-3851252) with the identical bytes, readback sha aaf024b9 same. Rebooted.
- Panic 3 (after identical rewrite): same node 28370 / tzinit exit 5 (`logs/ios26-blit-panic2.txt`). Last good boots were on the 2120 kernel; flashed 2120-drawlog75 (5ec226ee) back to test.
- 2120 kernel panics the same way, so not the kernel version. UFS driver (xnu 0028/0030/0034) reads through a
  1 MiB bounce buffer in <=1 MiB pieces; nothing obviously wrong found yet. The phone has no working boot now.
  Options put to the owner: (1) rewrite the iOS root (first 24 GiB of userdata) from
  `build/ios26-root-a71-23G90.img` and replay the setup payloads (reliable, destructive, loses runtime state);
  (2) keep debugging why XNU reads catalog node 28370's second half as zeros (kernel CI per try).
- **Correction: catalog node 28370 IS corrupt on disk.** Offsets 0..93 valid; table entries 94..98 are
  51739, 61467, 5660, 0, 0 (98 = free-space offset = 0, which is what XNU reports as "offset #0 invalid").
  Record data from byte 7076 (record 93) on is zero: records 93..97 (thread records, CNIDs after 609266) lost.
  Likely cause: the in-kernel payload installer adding catalog records during the LIVE delayed install
  (2120 sweetpayloaddelay, NoCopy boot) overfilled the node instead of splitting it. Do not use delayed payloads
  again until the installer is checked. Proposed minimal repair (needs owner OK): numRecords 93, offsets
  0..92 unchanged, free-space offset 7076, zero the rest; keep the current node as a backup to undo.
- Owner OK: repaired catalog node 28370 in place. Backup `research/hfs-repair/node28370-before.bin` (aaf024b9),
  repaired `node28370-repaired.bin` (numRecords 93, offsets 0..92 kept, free space 7076, rest zero) written to
  fs blocks 3851251-3851252, readback 44487a98 OK. Lost: 5 thread records (CNIDs after 609266). Header
  leafRecords not adjusted. Boot `build/a71-ios26-nopayload-2119.img` (no sweetpayload, no dtlog) readback
  ca6839df OK, to check the FS before the pending blit-glass package is applied.
- **Repaired boot works.** tzinit passes, no BTNode errors, Metal published, frames (15.8 swaps/s). Expected side
  effect: `cat_delete() failed to delete thread record id=609270/609274/609283` (the lost thread records),
  handled without a crash. Usual `hfs_cnode.c:946` warnings (old). blit-glass package still pending in the
  payload area (this image has no sweetpayload). Next: install it with a NON-delayed image (mercuryonly).
  Root cause to fix later: the in-kernel installer (2100/2120) inserting catalog records into a full node.
- Before install: node 28370 now 67 records, table valid (kernel rewrote it during the repaired boot). Flashed mercuryonly (23eebb59, install at mount) to apply pending blit-glass (36aaf7b7). Rebooted.
- blit-glass boot (install at mount, 9/9): glass copy active (`a draw samples its own colour target (256x192,
  5 levels)`); owner: Settings glass vanishes less often, CC / App Library / dock still lose it. backboardd calls
  `generateMipmapsForTexture:`, which the blit encoder skipped. Mercury: blit upload passes; next refusal
  `this render pipeline is refused: a phi between pointers that name different places`.
- Next Metal (in ios26-image-write-levels.patch): (1) blits are queued as command-buffer work (block in
  SweetNativeMetalWork.nativeBlit) and run in order at commit, not at encode time; (2) generateMipmaps via
  util_gen_mipmap (rwa_texture_generate_mipmap); (3) pointer phis between different BUFFERS: a 32-bit selector
  register stored on each edge + the existing AIR_VAL_PTR_SELECT chain (textures/samplers/argbuf still refused).
  Commit 55996bf, Metal CI `44705378496`.
- Metal CI `44705378496` 6/6 match. TWRP: `build/a71-ios26-metal-mips-phi.payload` VERIFY OK `c61457c9...c355`, boot mercuryonly (23eebb59, install at mount). Rebooted.
- mips-phi boot (9/9): generateMipmaps runs now (no "not done" line). Owner: glass unchanged. Mercury still
  refuses the pointer phi: so it is between textures/samplers (not buffers). Also `air.is_null_texture_2d`
  (called by Mercury) was not translated at all. Added: pointer phis between textures/samplers/null allowed
  (argbuf still refused); texture_op splits a texture/sampler chosen at run time into one op per place and
  selects the results (writes refused, a null side takes the other's result); is_null_texture on resolved and
  run-time-chosen pointers.

## 2026-11-20 evening — HANDOFF (owner stopped for the day)

State of the phone: boots iOS 26 on `build/a71-ios26-nowifi-mercuryonly.img` (2119 kernel, no Wi-Fi, payload at
mount, dtlog MercuryPosterExtension). Installed Metal: CI 44705378496 (55996bf: queued blits + util_gen_mipmap +
buffer pointer phis + everything before). Catalog node 28370 was repaired by hand today (backup in
`research/hfs-repair/`).

Running when stopped (results NOT checked):
- Metal CI `44706701933` (6dce3a5): textures chosen at run time (pointer phis between textures/samplers/null;
  texture_op split per place) + `is_null_texture`. Goal: Mercury wallpaper. Install with a package at mount
  (mercuryonly image), never with sweetpayloaddelay.
- Kernel CI `44707209045` (ad4cbb2): xnu 2121 makes `ufsverify=1` (read back every UFS write, retry) the default.
  Untested. Expect slower writes. Pack with the usual options; `ufsverify=0` turns it off.

Done today and verified on the phone: flicker fixed (attachment size MIN); Settings works; Mercury shaders all
compile; ASTC, NoCopy buffers, blit encoder; Wi-Fi resets the phone (keep `--wifi` off).
Open:
1. Glass still vanishes (Settings rarely; CC, dock, App Library often). Copy-on-self-sample and real mipmaps did
   not fix it. Next: a draw trace with ids at the moment it vanishes (`logs/drawlog-glass-ids-20261120.txt` is
   from before those fixes), compare frames with and without glass; check sampler LOD clamps on the
   variable blur and whether `glass_background` draws are skipped by CoreAnimation itself.
2. Wallpaper: after 44706701933, read Mercury's next error (`grep Mercury` in the USB log).
3. Root cause of the catalog corruption is unknown (B-tree code would panic before writing a bad node, UFS
   strategy is locked): candidates are a device-level bad write (2121 checks) or memory corruption.
4. Wi-Fi: phone resets right after `mission mode on` / CE rings at 0xf0000000.

## 2026-11-20 night — texture-phi Metal installed; 2121 image packed

- Both CIs from the handoff succeeded: Metal `44706701933` (6dce3a5) artifact `14616085754`, 6/6 files match
  build.json; kernel `44707209045` (ad4cbb2, xnu 2121) artifact `14617185412`, kernel SHA-256 `7392a6b7...b443`
  matches SHA256SUMS (both in ignored `research/ci-*`). `gh` is not installed here: use `tools/flow/ghauth.py`
  with `ghauth.API = ".../repos/ssttnd/ios26-a71"`. adb is `misc\misc\71stuff\Minimal ADB and Fastboot\adb.exe`.
- Phone was in TWRP with mercuryonly on boot (readback 23eebb59 OK). Wrote `build/a71-ios26-metal-texphi.payload`
  (9 entries) VERIFY OK `2b15803f9dbae98722abf4800ccbcf598354eb950ae48277866e9be23ff1277b`, `twrp reboot system`.
  USB log `logs/usb-ios26-texphi.txt`: payload `finished 9/9 errno=0`, Metal published.
- Packer recipe for mercuryonly (repack differs only in the ADT random-seed, by design): `a71-pack-ios26.py
  --shim research/a71-boot-before/kernel --dtb research/a71-boot-before/dtb --product-adt build/a71-ios26-n104.adt
  --touch --keys --adreno-firmware ../ios-a71/research/a71-firmware --metal --payload --cpufreq --usb
  --rtcoff 1778420636 --dtlog MercuryPosterExtension --fb-hz 30 --fb-scale 2`.
  `build/a71-ios26-mercuryonly-2121.img` = that with the 2121 kernel, SHA-256 `3a3f0342...77be5`. Not flashed.
- texphi boot: the texture-phi refusal is gone. Next Mercury refusal: `a call passing a pointer chosen at run time
  as argument 14` (translate_callee). Fix 9e38959 (in ios26-image-write-levels.patch, generator
  `research/ios26/make-image-level-patch.py`, now tracked with -f): the call is split by nir_goto_if on the choice,
  one specialised call per side, join block after (unstructured CFG, like the switch lowering). Metal CI
  `44788805733` succeeded, 6/6 match; package `build/a71-ios26-metal-callsplit.payload`
  `11d46130ae547cf008c4e3bfecd6aec6ad78318bd6852d2bb4b000bb8f63ea8b`. Not written.
- Owner asked for fewer one-error-per-flash rounds. Plan: donor's offline `air2nir --report` (host build) over every
  metallib, giving all refusals at once. All 210 AIR metallibs of the reference root extracted to ignored
  `research/metallibs/` (index.txt maps numbers to paths; 31 more are GPU binary archives, skipped). Building
  host Mesa + air2nir in the local VM (`research/root-vm/start.py`, new overlay disk, ssh port 2227, use a fresh
  known_hosts: the host key changed). Donor sources under research/ios26 are CRLF: convert to LF before git apply
  on Linux. QuartzCore's glass shaders are not on disk as .metallib (embedded in the dyld cache): carve MTLB
  containers from the cache next, then audit them for approximations (glass vanishing has no refusals).
- **Offline air2nir report done** (host build in the VM: `~/w/work/build-host/src/compiler/air/air2nir`, Mesa
  25.0.7 + donor + blur + levels patches incl. 9e38959, `-Dgallium-drivers=` is enough for air2nir). Whole root:
  9144 modules translate, 14947 refused, mostly irrelevant (8988 air.visible library functions, ray tracing,
  tessellation, imageblock).
  - Mercury (`research/metallibs/0018.metallib`): 29/44 translate. **All space::* (the selected poster) and all
    fluidity::* (stock iOS 26 wallpaper) translate** with 9e38959, so call-split should unblock their shaders.
    Still refused (other Mercury posters): Ajisai/Jurin frag "an externally initialized variable that is not a
    function constant", Flocon colour frag "a struct where a number belongs", shippou compute stores function
    pointers in memory ("function value used before it is defined"), tori::four vertex "array where a number
    belongs".
  - CoreAnimation glass: `/System/Library/Frameworks/QuartzCore.framework/default.metallib` is a fat file (cafebabe);
    its first MTLB at +48 (1,552,128 bytes) is CA's AIR. Carved to ignored `research/metallibs-wrapped/w0000_0.metallib`.
    173/189 translate; the 16 refusals are all imageblock tile shaders. Every glass/blur shader translates (glass_
    background*/foreground*, variable_blur*, downsample*, narrow_blur*), with no approximation note. Glass samples
    the blur chain with an explicit level (txl) through an inline sampler: linear/linear/mip linear, lod 0..65504,
    decoded correctly. setVertexBytes/setFragmentBytes copy at once; viewport and scissor are applied
    (air_metal.c ~7086, rasterizer scissor=1). So the vanishing glass is NOT a translation problem.
- 0b083bf adds GLASSSTAT (always on, no file): once a second each process logs `GLASSSTAT ... draws N glass_bg
  N glass_fg N blur N`. With the owner opening CC and pressing buttons, this tells whether CA stops sending glass
  draws when it vanishes (CA's own choice, e.g. late frames: swap_wait_timeouts 674 in a boot) or keeps sending
  them (our rendering). Combined Metal CI `44791373178` (call-split + GLASSSTAT) building.
- CI `44791373178` OK, 6/6. Phone was in TWRP, boot mercuryonly (23eebb59) verified; wrote
  `build/a71-ios26-metal-glassstat.payload` VERIFY OK `9ae80ea0...b32eb`, rebooted. Pitfall: the logger from the
  previous boot (a71-usblog.py, appending to `logs/usb-ios26-texphi.txt`) still held COM7, so this boot is in that
  file from line 13338 (copy `logs/usb-ios26-glassstat-part.txt`). Stop old loggers before starting a new one.
  Payload 9/9, Metal published. Mercury: the argument-14 refusal is gone; next refusal (render pipeline)
  `a phi of pointers one of whose operands is itself a pointer chosen at run time`. Not seen offline even with all
  function constants = 1 (VM air2nir has a local `AIR2NIR_FC_ONES=1` sweep), so it comes from a specialisation or
  another library. Fixed generally in a871a6b (phi operands flattened to leaf places; the edge stores a bcsel
  index); offline corpus: that refusal 32 -> 0, +6 modules translate, no regressions; Metal CI `44794161842`.
- GLASSSTAT in that boot (backboardd, per second): CoreAnimation sends glass all the time while the UI is used:
  glass_bg 150-730 and blur 30-290 per second, total draws 3000-6700 per second. Owner: glass DID vanish in that
  boot, so CoreAnimation keeps sending glass draws and the fault is in our rendering.
- 24d92d5: periodic draw log (`/var/local/sweet-native-drawlog-every` = "SECONDS DRAWS PROCESS", read once at
  process start; installed at mount, no delayed package). Metal CI `44794565128` OK 6/6; package
  `build/a71-ios26-metal-glasstrace.payload` (bundle + that file = "30 1200 backboardd") VERIFY OK `a4d7ab9f...e108`,
  boot mercuryonly unchanged. Boot: payload 11/11, `DRAWLOG every 30 s, 1200 draws`; USB log
  `logs/usb-ios26-glasstrace.txt`. Owner: bigger clock, wallpaper black (no glass test result yet).
- Mercury now builds every pipeline (no refusal). Black wallpaper causes in the log: (1) `colour attachment 0 asks for
  a multisample resolve ... this driver resolves nothing` (~250x): Mercury renders, resolves into a resolveTexture,
  and the driver never resolved, so the shown texture stayed black; (2) unimplemented blit
  `copyFromTexture:sourceSlice:sourceLevel:toTexture:destinationSlice:destinationLevel:sliceCount:levelCount:`.
  fa83a3d: resolve queued at render -endEncoding as a GPU pipe->blit (rwa_texture_resolve, in order at commit), and
  the slice/level-count copy. Applies; not compiled locally. Metal CI `44796529125`.
- Glass trace boot (`logs/usb-ios26-glasstrace.txt`, 5 windows; rejoin `|backboardd|` pieces before parsing): every
  window has 55-95 glass_background draws; each samples (slot 3, source_texture) a blur texture that
  variable_blur_downsample rendered just before; no draw failed. Some of those blur textures report
  mipmapLevelCount 0 (texture made with 1 level). Which window was the vanished state is unknown (no marker).
- Resolve build CI `44796529125` OK, installed (`build/a71-ios26-metal-resolve.payload` `1328dc41...c6ee`), boot
  mercuryonly; payload 9/9, log `logs/usb-ios26-resolve.txt`. Resolve/blit messages gone. Owner: still no wallpaper,
  glass still vanishes (no volume-key markers in the log).
- Wallpaper cause now: Mercury never draws (no GLASSSTAT line from it): `no drawable: interface: Metal format 53 /
  IOSurface 0x42475241 (207x448 pitch 832) is not a supported linear import` (redwooddrawable.m). 9869ff6 lets
  R32Uint/Sint/Float view a 4-byte BGRA/RGBA IOSurface, and logs textures created with mipmapLevelCount 0 (first 16,
  with descriptor class). Metal CI `44798290743`.
- Drawable fix CI `44798290743` installed (`build/a71-ios26-metal-drawable.payload` `8fc24515...577f`, includes the
  trace file "10 800 backboardd"), log `logs/usb-ios26-drawable.txt`: payload 11/11, drawable error gone. Next
  Mercury stop: `the dispatch failed: VTMTSComputeFunction1x1 writes texture 0 and that texture was made without
  MTLTextureUsageShaderWrite` (VideoToolbox writes a CVMetalTextureCache IOSurface texture). cde0f53: an imported
  IOSurface is writable when the GPU can bind its format as an image. Metal CI `44800087775`.
- In the resolve boot, marker presses were all `SWEET KEYS: key=1` (= volup per tools/a71-dbg.py KEYS); key=2
  (voldown) never appeared. GLASSSTAT between/after the presses: 130-470 glass draws/s, so CoreAnimation keeps
  drawing glass while it is invisible.
- **xnu 2122** (97d2aeb): USB ACM bulk OUT bytes are scanned for "a71:recovery" / "a71:reboot" / "a71:bootloader";
  a kernel thread calls sweet_reboot_set_mode + reboot_kernel(RB_AUTOBOOT). sweet_reboot_init now also runs on
  samsung,a71 (before it returned early: only xiaomi,sweet), so restarts on the A71 now go through
  sweet_reboot_restart (UFS flush, PON spare 0x88f, IMEM 0x146aa65c = 0x77665502 for recovery, PSCI reset).
  Untested. Kernel CI `44799888353`. PC side: tools/a71-usblog.py opens COM read+write and sends the content of
  `logs/usb-command.txt` once (e.g. `a71:recovery`). Restart the logger to get the new code.
- Glass marker test on the drawable boot (`logs/usb-ios26-drawable.txt`): one volup at line 19995 = "glass gone".
  For ~10 s after it CA sent 130-330 glass draws/s, then the screen went static (~130 draws/s, glass 0): the
  vanished picture is the result of those glass draws (trace window at line 20159). Window contents look like the
  windows where glass was visible: variable_blur_downsample -> glass_background(_sdf)_no_bleed, every pass has two
  colour attachments (80 BGRA8 + 115 RGBA16F, same size). No visible-state marker yet.
- 8c577e4 TEXSTAT: for each logged glass_background draw, the slot-3 blur texture is read back per level (mean
  BGRA, % alpha 0). Superseded Metal CI 44800087775 cancelled; new Metal CI `44800819116` (IOSurface write +
  TEXSTAT).
- 2122 first CI failed (two printf strings broken by a real newline from the generator script); fixed in de31684,
  kernel CI `44802195088`.
- TEXSTAT boot (`build/a71-ios26-metal-texstat.payload` `b76f7731...c52c`, log `logs/usb-ios26-texstat.txt`): blur
  textures sampled by glass are NOT empty: after the "gone" marker uniform dark grey (~39,39,39,255), earlier up to
  130 grey; at boot black (black wallpaper). So the blur chain works; glass over a black/dark backdrop may simply
  be near invisible, or glass_background output is wrong. Fix the wallpaper first.
- Mercury: no more refusals, but every compute dispatch was dropped: `207x448x1 threads do not divide into groups
  of 32x32x1 ... partial-group support` (dispatchThreads, VariableBlurrer/VTMTS/space). freedreno ignores
  pipe_grid_info.last_block. 38c5652 rounds groups up (extra edge threads; Adreno drops OOB image/IBO stores).
  Metal CI `44802843341`.
- Partial-group Metal (CI `44802843341`, `build/a71-ios26-metal-groups.payload` `35e340b1...30f9`) installed: no more
  dispatch refusals. Mercury still draws nothing: RunningBoard refuses its rendering assertions ~2500x, "Assertion's
  invalidation time is in the past". Cause: userland clock is 1969-12-31 (epoch + uptime). 2108 sets the calendar
  from the PM6150 RTC early, then IOKitInitializeTime() waits up to 30 s for IORTC (none here) and
  clock_initialize_calendar() overwrites it from PEGetUTCTimeOfDay. **xnu 2123** (fc2dff8): re-read the RTC right after
  clock_initialize_calendar, IORTC wait 30 -> 2 s on sweet boards. Kernel CI `44805072035`.
- **xnu 2122 verified on the phone.** `build/a71-ios26-2122.img` (CI 44802195088 kernel `2222d86c...b51d`, mercuryonly
  options) readback `d7ab4015...e410`. First boot hung after `SWEET EARLY 9` (red shim screen, no USB; the known random
  first-boot fault), second boot fine: `SWEET REBOOT: ... IMEM mapped, PON spare write ready`. Writing `a71:recovery` to
  `logs/usb-command.txt` (new a71-usblog.py running) -> `SWEET USB: host asked for a reboot into recovery` and TWRP came
  up by itself. The PC can now go iOS -> TWRP without the owner.
- Pitfall: in bash heredocs `\\n` reaches Python as `\n` (a real newline in C strings). Use raw strings or chr(92).
- Marker protocol for the next glass test: Volume Up when glass is gone, Volume Down when visible (`SWEET KEYS:
  key=` lines land in the same USB log as the 30 s draw-trace windows).
