# iOS 26 on Galaxy A71 4G

Target hardware is the Samsung Galaxy A71 4G (`SM-A715F`, `a71`), with a
Snapdragon 730 (`SM7150`). The target system is iOS 26.6.2 (`23G90`) for
iPhone 11 (`iPhone12,1`), using XNU `12377.121.6`.

XNU 12377 reached a diagnostic PID 1 from a small HFSX RAM disk on the A71.
The full iOS 26 filesystem and UI are pending. See [NOTES.md](NOTES.md) for
builds and observed results. The [iOS 16 port](docs/ios16-README.md) documents
the existing shim, A71 hardware, and working system.

The manual **A71 XNU 26** workflow produces `xnu26-kernel` and `a71-ramdisk`.
The kernel starts from [Bergamota's XNU 12377 series][berg], the same base
used to reach the home screen on [Redmi Note 10 Pro][sweet]. A71 changes to
that series go in `xnu/patches-12377/`. Device-specific inputs and build outputs
belong in ignored directories.

## Build a diagnostic boot image on Windows

Download `xnu26-kernel` and `a71-ramdisk` from the same Actions run. Extract
the shim and stock DTB from a known-good A71 iOS boot image with
`python tools/unpack_bootv2.py BOOT_BACKUP research/known-boot`.

```powershell
python tools/a71-pack-ios26.py --kernel research/ci/kernel.development.sweet `
    --shim research/known-boot/kernel --dtb research/known-boot/dtb `
    --ramdisk research/ci/a71-smoke.hfs -o build/a71-xnu26-smoke.img
```

The RAM disk contains a small `/sbin/launchd` built from `tools/sweet-init.S`.
It logs `init running as PID 1` when `/dev/console` is available. A kernel
trace showing a syscall from `launchd[1]` also confirms the process ran.
The command above produces an image for the A71 `boot` partition.

For a full iOS 26 root already installed on `userdata`, replace `--ramdisk`
with `--product-adt research/ios26/n104ap.adt`, extracted from the iPhone 11
IPSW. The test build leaves hardware acceleration, keys, charging telemetry,
USB, and CPU clock changes off. `--touch` opts in to the A71 SEC_TS driver
when the selected kernel includes the A71 patch.

[berg]: https://github.com/ry-diffusion/Bergamota/tree/37a7a7a917fc09945ed2f7d1ae68b84d4525b4cb/xnu/patches-12377
[sweet]: https://github.com/DC28088/ios-sweet/blob/4ff9b8ea41812307b867c334c77f4c290ccf1dd8/NOTES.md
