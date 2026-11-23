# Working with the A71 (iOS 26): how-to

Practical reference for driving the phone, the builds and the logs from this Windows folder. Facts here were
checked on the phone; the dated history is in `NOTES.md`. Keep this file current when a procedure changes.

## Commits and continuing work

- Push every project commit to the current GitHub branch after committing. Verify that the remote branch contains
  the commit. If a push fails, diagnose and retry it without overwriting remote history.
- Continue authorized work through the next build, test, diagnosis and fix without waiting for another command.
  Treat CI and device progress as part of the task. Keep working on independent steps while a build runs or a
  specific action is blocked. Ask the owner only for a required authorization or input, or when an external
  blocker prevents further progress.
- Update `NOTES.md` after each milestone so the next session can pick up from the last verified result.

## Tools on this PC

- adb: `C:\Users\qqstee\Desktop\misc\misc\71stuff\Minimal ADB and Fastboot\adb.exe` (not in PATH). Python scripts
  want the Windows form of the path; in Git Bash call it as `"/c/Users/qqstee/Desktop/misc/misc/71stuff/Minimal ADB
  and Fastboot/adb.exe"`.
- `gh` is not installed. GitHub API calls go through `tools/flow/ghauth.py` (token from `git credential fill`, never
  printed). Its `API` points at `ssttnd/ios-a71`; set `ghauth.API = "https://api.github.com/repos/ssttnd/ios26-a71"`
  for this repo. The repo is public: no secrets, serials or Apple files in commits or Actions logs.
- Python: run standalone tools with `python -I -X utf8`. Use `python -X utf8` for the boot packer so it can import
  sibling modules from `tools/`. In Git Bash, run `tools/a71-payload.py` with
  `MSYS_NO_PATHCONV=1`, or `/System/...` turns into `C:/Program Files/Git/System/...`.
- Bash heredocs: `\\n` reaches Python as `\n`, i.e. a real newline inside generated C strings (this broke xnu 2122
  once). Use raw strings (`r'''...'''`) or `chr(92)` in generator scripts.

## Phone states and how to move between them

| From | To | How |
|---|---|---|
| iOS | TWRP | **From the PC (xnu 2122, needs `sweetusb=3`):** with `tools/a71-usblog.py` running, write `a71:recovery` to `logs/usb-command.txt`. The logger sends it once and deletes the file; the log shows `SWEET USB: host asked for a reboot into recovery`, then TWRP appears in `adb devices` as `recovery` within ~1 min. `a71:reboot` (normal) and `a71:bootloader` also exist. Without 2122: owner's key combo. |
| TWRP | iOS | `adb shell twrp reboot system`. Plain `adb reboot` returns to TWRP. |
| hung boot | anything | Owner: long power press. |

Known fault: the **first boot after writing to the phone from TWRP sometimes hangs or panics early** (red shim
screen stuck after `SWEET EARLY 9`, shim blue `PANIC SYNC`, eventhandler assert, nothing on USB). Cause unknown.
Reboot once before concluding a build is broken; it has always booted the second time so far.

## Logs

- **USB console (primary):** `python -I -X utf8 tools/a71-usblog.py logs/usb-NAME.txt` as a background job. It finds
  the port by USB ID (usually COM7), reconnects across reboots and appends. Run **one** logger at a time: Windows
  gives the port to one process, and an old logger keeps writing the new boot into its own (old) file. Stop the old
  one before starting another. Only the new logger (2026-11-21 or later) can send commands.
- **Persistent ring from TWRP:** `python -I -X utf8 tools/pull_log.py` writes `latest_log.bin` / `latest_log.txt`
  (last 4 MiB of userdata). It holds the last boot that got far enough to write it; a boot that died very early
  leaves the previous boot there.
- Userland os_log pieces arrive split as `|process| text`; rejoin the `|backboardd|` (or other) pieces before parsing
  multi-part lines (draw traces).
- Kernel stack sampling (`--sample` in the packer) matches the exact short process name from `proc_name()`,
  limited to 16 characters. Use `--sample MercuryPosterExt` for MercuryPosterExtension. Look for `SMP: sampling`
  to confirm the filter and `SMP <name>[<pid>]` for a captured stack. The first sample comes about 90 s after boot.

## Writing to the phone (from TWRP)

- **Boot image** (allowed without asking while debugging, verified by hash):
  `python -I -X utf8 tools/a71-flash-boot.py ADB_EXE IMAGE SHA256 --no-reboot`, then `twrp reboot system`.
  Check what is on `boot` first: `adb shell 'head -c SIZE /dev/block/by-name/boot | sha256sum'`.
- **Packages** into the root (raw area at the end of userdata, applied by the kernel at the next boot when the
  image has `sweetpayload=1`):
  `MSYS_NO_PATHCONV=1 python -I -X utf8 tools/a71-payload.py build OUT.payload ITEM...` then
  `... a71-payload.py write ADB_EXE OUT.payload` (prints `VERIFY OK sha256`). Items: `tree:DIR=/dest`,
  `text:/dest=CONTENT`, `file:LOCAL=/dest[@MODE]`, `rm:`, `mv:`, `link:`. The log shows
  `SWEET PAYLOAD: finished N/N errno=0` on the next boot.
- **Never use a delayed package** (`sweetpayloaddelay`, xnu 2120): a live install corrupted an HFS catalog node
  (2026-11-20). Install at mount only.
- Do not touch bootloaders, recovery, modem, persist or the backups. Other destructive steps need the owner's OK.

## Wallpaper diagnostics

- The launchd job `org.a71.poster-probe` runs `/private/var/local/poster.sh`
  without arguments and lists the lock and home configurations after 120 s.
  It writes `/private/var/local/poster.log`. To set a poster deliberately, run
  the script as mobile with `--select PROVIDER DESCRIPTOR`.
- For a variant-switch test, keep the existing snapshots and cache. Capture
  the lock screen, home screen and cover sheet after the switch and match
  PosterBoard's configuration and role to the USB log. In TWRP,
  `tools/a71-hfs-get.py` can read the probe log without mounting userdata.
- For a Liquid Glass test on 2125, compare a home-page swipe with a return
  from App Library. Correlate the visible change with `GLASSSTAT` and
  `recopies` in the same USB capture. The counters cover different events
  and are not frame identifiers.

## Boot images

Packer (repack differs only in the ADT random seed, by design):

```
python -X utf8 tools/a71-pack-ios26.py --kernel KERNEL --shim research/a71-boot-before/kernel \
  --dtb research/a71-boot-before/dtb --product-adt build/a71-ios26-n104.adt --touch --keys \
  --adreno-firmware ../ios-a71/research/a71-firmware --metal --payload --cpufreq --usb \
  --rtcoff 1778420636 --dtlog MercuryPosterExtension --fb-hz 30 --fb-scale 2 -o build/NAME.img
```

`--usb` (sweetusb=3) is required for the USB log and for PC commands. Leave `--wifi` off: Wi-Fi resets the phone.

## CI (GitHub Actions, repo ssttnd/ios26-a71, branch `codex/a71-settings`)

- Kernel: workflow `xnu26.yml`, dispatch with input `adreno=true`. Patches are every
  `xnu/patches-12377-adreno/*.patch` in name order, applied after the donor 2000-2011 series. Artifact
  `xnu26-kernel` (`kernel.development.sweet` + `SHA256SUMS`; check the hash). ~20 min.
- Metal: workflow `native-metal.yml`, dispatch with input `ios26=true`. It applies
  `userspace/native-metal/ios26-mip-views.patch`, `ios26-blur-attachments.patch`, `ios26-image-write-levels.patch`
  to the pinned donor. The last one is generated by `research/ios26/make-image-level-patch.py` (tracked with
  `git add -f`; `research/` is ignored); edit the generator, regenerate, never hand-edit the patch. The generator
  diffs against `research/ios26/native-glass-src/base-mip-blur` (ignored, LF): a copy of `donor/userland` and
  `donor/tools` (donor already has mip-views) with `ios26-blur-attachments.patch` applied. Rebuild it that way if it is
  missing; diffing against `donor` itself broke CI once (hunks next to blur lines). Before pushing, check the series:
  LF copy of donor, `git apply -R ios26-mip-views.patch`, then apply all three in order. Artifact
  `a71-sweet-metal26`: check all six files against `build.json`, then package
  `tree:.../SweetMetal2.bundle=/System/Library/Extensions/SweetMetal2.bundle`.
- Making a kernel patch: copy the touched files from `research/xnu-12377` (CRLF: convert to LF), apply the earlier
  `21xx` patches that touch them (`git apply --include=...`), edit, `git diff`, add a header paragraph, and check the
  series applies again before pushing.
- Cancel a superseded run instead of letting two builds race for the same purpose.

## Offline shader checks (no phone)

- Local Linux VM (QEMU/WHPX, headless): `python research/root-vm/start.py`; ssh `builder@127.0.0.1 -p 2227` with
  `research/root-vm/id_ed25519` and a fresh known_hosts file (the overlay disk is recreated, so the host key
  changes). Host `air2nir` is built in `~/w/work/build-host` from Mesa 25.0.7 + donor + our Metal patches
  (`-Dgallium-drivers=` is enough). Donor sources under `research/ios26` are CRLF: convert before `git apply`.
- `air2nir --report FILE.metallib` translates every function and prints one line each with `translate=ok|fail`,
  `error=`, `notes=` (approximations). Function constants are all 0; the VM copy has a local
  `AIR2NIR_FC_ONES=1` sweep. A pipeline specialised with other values can still fail on the phone.
- System metallibs from the reference root (Apple files, ignored, never commit): `research/metallibs/` (index.txt),
  wrapped/fat ones such as QuartzCore's in `research/metallibs-wrapped/`.

## Diagnostics built into the Metal driver

- `GLASSSTAT` (always on): once a second per process, draws executed and how many were CoreAnimation glass/blur.
- Periodic draw trace: file `/var/local/sweet-native-drawlog-every` = `SECONDS DRAWS PROCESS` (install with a
  package), e.g. `10 800 backboardd`. Each window logs `DRAW` lines with texture ids/levels; glass draws also log
  `TEXSTAT` (readback of the sampled blur texture).
- Owner markers: volume-up presses appear as `SWEET KEYS: key=1` in the same USB log (key=2, volume down, has
  never been seen). Agreed code: one press = glass gone, two presses = glass visible.
