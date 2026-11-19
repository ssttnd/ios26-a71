# iOS 26 on Galaxy A71 4G

Target hardware is the Samsung Galaxy A71 4G (`SM-A715F`, `a71`), with a
Snapdragon 730 (`SM7150`). The target system is iOS 26.6.2 (`23G90`) for
iPhone 11 (`iPhone12,1`), using XNU `12377.121.6`.

The first milestone is an XNU boot with a small HFSX RAM disk and a diagnostic
PID 1. This runs entirely from `boot` and RAM. See [NOTES.md](NOTES.md) for
builds and observed results. The [iOS 16 port](docs/ios16-README.md) documents
the existing shim, A71 hardware, and working system.

The manual **A71 XNU 26** workflow produces `xnu26-kernel` and `a71-ramdisk`.
The kernel starts from [Bergamota's XNU 12377 series][berg], the same base
used to reach the home screen on [Redmi Note 10 Pro][sweet]. A71 changes to
that series go in `xnu/patches-12377/`. Device-specific inputs and build outputs
belong in ignored directories.

[berg]: https://github.com/ry-diffusion/Bergamota/tree/37a7a7a917fc09945ed2f7d1ae68b84d4525b4cb/xnu/patches-12377
[sweet]: https://github.com/DC28088/ios-sweet/blob/4ff9b8ea41812307b867c334c77f4c290ccf1dd8/NOTES.md
