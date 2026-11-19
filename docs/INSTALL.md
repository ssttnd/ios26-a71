# Installing from scratch

From a stock Galaxy A71 4G (`SM-A715F`) to the iOS home screen with GPU, Wi-Fi and sound. Windows does
everything except one Linux step (building the HFS+ root). The steps that write to the phone are run by
`tools/a71-install.py`, which checks each write by reading it back.

**This erases the phone's data** (`userdata`, the internal storage). Apple's security model is mostly off:
do not put anything personal on it.

## 0. What you need

- An SM-A715F. Other A71 models (5G, A716) are different hardware and will not boot this.
- Bootloader unlocked (Developer options -> OEM unlocking, then the long Volume Up in Download mode) and
  TWRP for the SM-A715F in `recovery`, flashed with Odin, with vbmeta verification off. Check: holding Power +
  Volume Up from off boots TWRP, and `adb get-state` prints `recovery`.
- Windows with Python 3.9 or newer and adb (Android platform-tools). `git` with a stored GitHub login.
- A fork of this repository on GitHub with Actions enabled.
- A Linux machine, VM or live USB for step 3, with `apfs-fuse`, `hfsprogs` (`mkfs.hfsplus`, `fsck.hfsplus`),
  `rsync`, `python3` and `aarch64-linux-gnu-gcc`, and 40 GB free.
- The iOS 16.7.16 IPSW for the iPhone X GSM, `iPhone10,3`, build `20H392` (from Apple's update servers;
  ipsw.me lists the link). It is Apple's and is not distributed here.

Set adb once per PowerShell window (or pass `--adb` to every command):

```powershell
$env:A71_ADB = "C:\platform-tools\adb.exe"
```

## 1. Build the kernel and userland in GitHub Actions

In your fork, Actions tab, run these workflows on your branch (Run workflow). Each takes 5-30 minutes:

| Workflow | Artifact | What it is |
|---|---|---|
| `xnu` | `xnu-kernel` | the kernel |
| `sweet-native-metal` | `sweet-native-metal-ios16` | Metal driver (`SweetMetal2.bundle`) |
| `sweet-wifi` | `sweet-wifi-ios16` | `wland`, `netsvc` |
| `sweet-audio` | `sweet-audio-ios16` | `adspboot`, `SunfishAudio.driver`, `sweetdbg` |
| `sweet-wallpaper` | `sweet-wallpaper-ios16` | one-time LaunchServices/wallpaper rebuild helper (optional) |

Then download them:

```powershell
python tools\a71-install.py fetch
```

It takes the newest successful run of each on the current branch and saves `research\ci\<artifact>.zip`.
Without a stored GitHub login, set `$env:GITHUB_TOKEN`, or download the zips from the run pages by hand
under those names.

## 2. Back up the phone and copy its firmware (TWRP)

Boot TWRP, connect USB, then:

```powershell
python tools\a71-install.py pull
```

This reads only. It writes:

- `backup\<date>\` — `boot`, `recovery`, `dtbo`, `vbmeta*`, `persist`, `efs`, `sec_efs`, `modemst1/2`, `fsg`,
  `fsc`, `param`. Keep it: `boot.img` is the way back to Android, and `efs`/`persist` hold the IMEI and
  calibration. Never commit it.
- `research\a71-firmware\` — GPU (`a630_sqe.fw`, `a618_gmu.bin`, `a615_zap.*`), modem, ADSP and WLAN firmware
  from `apnhlos`, `modem` and `/vendor`. It is this phone's firmware and goes only onto this phone.
- `dtb\boot_unpacked\` — the device tree from the stock boot image.

Run `python tools\a71-install.py check`. Everything but `shim/out/Image` and `build/install.payload` should be
there now. If `/vendor` did not mount, mount Vendor in TWRP's Mount menu and run `pull` again.

## 3. Build the iOS root and the shim (Linux, once)

Copy the repository and the IPSW to the Linux machine. Unzip the IPSW. `BuildManifest.plist` names three
disk images: `OS` (the largest .dmg), `Cryptex1,SystemOS` and `Cryptex1,AppOS`. Then:

```sh
tools/mkiosroot.sh <OS>.dmg <SystemOS>.dmg <AppOS>.dmg ios-root.img      # 16 GiB image
fsck.hfsplus -fy ios-root.img
sudo mkdir -p /mnt/ios && sudo mount -t hfsplus -o loop,force ios-root.img /mnt/ios
sudo python3 tools/sweet-root-tweaks.py /mnt/ios
sudo umount /mnt/ios && fsck.hfsplus -fy ios-root.img
shim/build.sh                                                            # makes shim/out/Image
```

`sweet-root-tweaks.py` is required: without it the boot stops at the Apple logo near 99%.

Copy `ios-root.img` and `shim/out/Image` back into the Windows folder (`backup\ios-root.img` and
`shim\out\Image`; both are gitignored). Keep a copy of the untouched image: it is the clean restore image.

## 4. Write the root (TWRP, erases userdata)

```powershell
python tools\a71-install.py write-root backup\ios-root.img
```

16 GiB over USB takes a while. It writes 1 GiB chunks, checks each, then reads the whole 16 GiB back. If it
stops, run the same command again: correct chunks are skipped.

## 5. Build the install package

```powershell
python tools\a71-install.py package backup\ios-root.img --tz Europe/Moscow
```

Reads the root image (does not change it) and makes `build\install.payload`: Metal driver, Wi-Fi daemon and
firmware, audio, `sweetdbg`, the launchd and lockdownd fixes, the network service and the app moves. The full
list is at the top of `tools/a71-install.py`. `--tz` takes a name under `/usr/share/zoneinfo`; leave it out to
keep the iOS default. `--no-audio` keeps the ADSP off at boot.

## 6. Flash the boot image (TWRP)

```powershell
python tools\a71-install.py boot
```

It builds `shim\out\shim-boot.img` from the kernel with the current boot line (`README.md`), with the phone's
RTC offset, writes the package to the raw area at the end of `userdata`, writes `boot`, reads both back, and
reboots only after `VERIFY OK`.

## 7. First boots

1. **First boot:** verbose text, then the Apple logo, then the lock screen. The kernel applies the package
   about 10 s after the root is mounted. Swipe up; there is no passcode.
2. **Reboot once** (hold Power + Volume Down, or power off and on). launchd read its jobs before the package was
   applied, so Wi-Fi, sound and `sweetdbg` start from the second boot on.
3. Settings -> Wi-Fi: join your network. The phone rejoins it at later boots.
4. Optional, from Windows over Wi-Fi: `python tools\a71-dbg.py ps`, `shot out.png` (the PC must be on the same
   network; the key is `build\sweetdbg.key`).

Kernel log over USB at any time: `python tools\a71-usblog.py logs\usb-install.txt`, and
`python tools\a71-bootcheck.py logs\usb-install.txt` to check a boot from it.

What works and what does not: the State table in `README.md`.

## Back to Android

Boot TWRP (Power + Volume Up) and write `backup\<date>\boot.img` back to `boot`:

```powershell
& $env:A71_ADB push backup\<date>\boot.img /tmp/boot.img
```

```powershell
& $env:A71_ADB shell "dd if=/tmp/boot.img of=/dev/block/by-name/boot bs=4096 conv=fsync; sha256sum /tmp/boot.img /dev/block/by-name/boot"
```

Both hashes must match the `boot.img` line in `backup\<date>\SHA256-phone.txt`. Then format Data in TWRP
(Wipe -> Format Data): Android cannot read the HFS+ `userdata`.

## When something fails

| Symptom | Likely cause | What to do |
|---|---|---|
| Stops at the Apple logo with the bar near 99% | `sweet-root-tweaks.py` not run on the image | step 3, then 4 again |
| Phone returns to TWRP after `adb reboot` | Samsung reboot reason | the scripts use `setprop sys.powerctl reboot` |
| No Wi-Fi after the first boot | expected | reboot once more |
| Boot loop right after flashing | look at the USB log first | in TWRP, `python tools\a71-payload.py clear <adb>` removes a package the kernel has not applied yet; `boot --no-package` reflashes only the boot image |
| `write-root` chunk keeps failing | USB or TWRP `dd` | other cable/port; run it again (it resumes) |

More detail on each part: `NOTES.md` (current state), `docs/galaxy-a71-port.md`, `docs/a71-radio-port.md`.
