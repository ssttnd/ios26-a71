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

- `2000-a71-sec-ts-touch.patch` adds the iOS 16 Samsung touchscreen power,
  reset, ID probe and event handling to the 12377 driver. It reuses the
  XNU 12377 HID event queue and GPIO I2C paths, selects Samsung via
  `samsung,a71`, and is opt-in during bring-up. Its diff applies to the
  staged donor source. Compilation and device validation are pending.
