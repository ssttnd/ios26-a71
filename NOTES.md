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
- A71 iOS 26 build and device boot are pending. No partitions were written.
