#!/usr/bin/env python3
"""Package an A71 XNU 26 Android boot image from explicit local inputs."""

import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import adt
import mkadt
import mkbootv2
import mkpayload
from hfsread import HFS


BASE_ARGS = (
    'debug=0xc serial=1 keepsyms=1 -noprogress cpus=8 '
    'unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin wdt=-1 '
    'sweetarm64e=1 sweetearlyfb=1 -v '
    'sweetbattery=0 sweetusb=0 sweetcpufreq=0'
)
SMOKE_ARGS = BASE_ARGS + ' rd=md0 sweetlog=0 -enable_kprintf_spam'
ROOT_ARGS = BASE_ARGS + ' rd=ufsroot0 ufsrw=1 rootrw=1 sweetfb_scale=1 launchd_unsecure_cache=1 launchd_disable_all_timeouts=1'
ADRENO_ARGS = ' sweetgpu=9 sweetgpukhz=650000 sweetfb_dcsbl=0 sweetddr=0 sweetcharge=0 sweetjetsamlimits=0'


SHIM_LINE_MAX = 607      # mkpayload cmdline[608] incl. the terminator
KERNEL_LINE_MAX = 1023   # XNU 12377 arm64 boot_args CommandLine[1024]


def split_cmdline(cmdline):
    """Keep the line for the shim if it fits; otherwise move whole arguments from the end into the
    ADT part (xnu 2140 appends /chosen sweet-boot-args after SecureDTInit). The early arguments
    (debug, serial, -v, rd=, sweetearlyfb, sweetusb...) come first in the line, so they stay."""
    if len(cmdline.encode()) <= SHIM_LINE_MAX:
        return cmdline, ''
    if len(cmdline.encode()) > KERNEL_LINE_MAX:
        raise SystemExit(f'command line is {len(cmdline.encode())} bytes, the kernel limit is {KERNEL_LINE_MAX}')
    words = cmdline.split(' ')
    main = []
    for i, w in enumerate(words):
        if len(' '.join(main + [w]).encode()) > SHIM_LINE_MAX:
            return ' '.join(main), ' '.join(words[i:])
        main.append(w)
    return cmdline, ''


def add_adreno_firmware(tree, directory):
    gmu = directory / 'a618_gmu.bin'
    output = tree.with_name('a71-adreno.adt')
    command = [sys.executable, str(Path(__file__).with_name('a71-adreno-firmware.py')),
               str(tree), str(gmu), str(output), '--sha256', hashlib.sha256(gmu.read_bytes()).hexdigest()]
    for flag, name in (('sqe-firmware', 'a630_sqe.fw'), ('zap-metadata', 'a615_zap.mdt'), ('zap-code', 'a615_zap.b02')):
        path = directory / name
        command.extend((f'--{flag}', str(path), f'--{flag.removesuffix("-firmware")}-sha256',
                        hashlib.sha256(path.read_bytes()).hexdigest()))
    subprocess.run(command, check=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', required=True, type=Path, help='kernel.development.sweet, XNU 12377')
    parser.add_argument('--shim', required=True, type=Path, help='the verified A71 shim Image')
    parser.add_argument('--dtb', required=True, type=Path, help='the verified Android boot DTB')
    root = parser.add_mutually_exclusive_group(required=True)
    root.add_argument('--ramdisk', type=Path, help='raw HFSX volume containing the diagnostic PID 1')
    root.add_argument('--product-adt', type=Path, help='N104AP ADT for booting an installed iOS 26 root from userdata')
    parser.add_argument('--native-width', nargs='?', const='1080x2340', choices=('1080x2340', '1125x2436'),
                        help='3x canvas for the installed iOS 26 root: 1080x2340 (360x780 pt, panel width 1:1) '
                             'or 1125x2436 (375x812 pt, iPhone X-class layout, scaled to the panel)')
    parser.add_argument('--touch', action='store_true', help='enable the Samsung SEC_TS driver in an A71 kernel build')
    parser.add_argument('--keys', action='store_true', help='enable the power and volume key driver')
    parser.add_argument('--wifi', action='store_true', help='enable the A71 WLAN device tree and wland kernel interfaces')
    parser.add_argument('--bluetooth', type=Path, metavar='FWDIR',
                        help='sweetbt=1 and /arm-io/bluetooth with crbtfw21.tlv + crnv21.bin from FWDIR '
                             '(the A71 vendor files apbtfw11.tlv/apnv11.bin under the driver\'s fallback names)')
    parser.add_argument('--adreno-firmware', type=Path, help='enable A618 stage 9 using firmware from this A71')
    parser.add_argument('--metal', action='store_true', help='select the installed SweetMetal2 bundle')
    parser.add_argument('--payload', action='store_true', help='apply a verified raw package on this boot')
    parser.add_argument('--payload-delay-ms', type=int, help='delay installing the package after root mount (10000–600000 ms)')
    parser.add_argument('--cpufreq', action='store_true', help='SM7150 cpufreq-hw: highest non-boost row (donor 2000; Adreno build)')
    parser.add_argument('--rtcoff', type=int, help='seconds to add to the PM6150 RTC (now - /sys/class/rtc/rtc0/since_epoch in TWRP)')
    parser.add_argument('--dtlog', help='sweetdtlog=NAME[,NAME]: their os_log on the console (donor 0205)')
    parser.add_argument('--no-noprogress', action='store_true',
                        help='drop -noprogress (no effect with -v) to free 12 bytes of the 607-byte boot line')
    parser.add_argument('--sample', help='sample the user stacks of NAME[,NAME]')
    parser.add_argument('--sample-interval-ms', type=int, help='time between user stack samples (minimum 50 ms)')
    parser.add_argument('--fb-hz', type=int, choices=(0, 10, 15, 20, 30, 60), help='limit copies to the panel to this rate (0 = 60, one byte shorter)')
    parser.add_argument('--fb-scale', type=int, choices=(1, 2), default=1,
                        help='1 fits the canvas inside the panel, 2 fills the panel')
    parser.add_argument('--usb', action='store_true', help='sweetusb=3: power USB up and stream the kernel log as a serial port (xnu 2101)')
    parser.add_argument('--usb-shot', action='store_true',
                        help='allow scanout snapshots over USB ACM (xnu 2126; requires --usb)')
    parser.add_argument('--usb-ui', action='store_true',
                        help='allow the A71 Cover Sheet test gesture (xnu 2127; requires --usb-shot)')
    parser.add_argument('--arg', action='append', default=[], metavar='NAME=VALUE',
                        help='append a boot-arg (repeatable), e.g. sweetbtlog=600')
    parser.add_argument('-o', '--output', required=True, type=Path)
    args = parser.parse_args()
    if args.native_width and args.ramdisk:
        parser.error('--native-width requires the installed iOS 26 root')

    kernel = args.kernel.read_bytes()
    if b'xnu-12377.' not in kernel:
        parser.error('expected an XNU 12377 kernel')
    if args.touch and b'Samsung S6SY771 (sec_ts)' not in kernel:
        parser.error('--touch requires an XNU build with the A71 SEC_TS patch')
    if args.wifi and (args.ramdisk or b'flame wlan: /dev/wlan ready' not in kernel or b'sweetsmmuwlan' not in kernel):
        parser.error('--wifi requires the installed root and an A71 WLAN kernel')
    if args.bluetooth and (args.ramdisk or b'SWEET BT: stage %u starts in %u s' not in kernel):
        parser.error('--bluetooth requires the installed root and a kernel with bsd/dev/sweet_bt.c')
    if args.metal and not args.adreno_firmware:
        parser.error('--metal requires --adreno-firmware')
    if args.ramdisk and (args.adreno_firmware or args.payload):
        parser.error('Adreno and payload installation require the UFS root')
    if args.adreno_firmware and b'SWEET GPU: GPUCC audit v2' not in kernel:
        parser.error('expected a kernel built with the Adreno option')
    if args.payload and b'SWEET PAYLOAD: finished' not in kernel:
        parser.error('expected an A71 kernel with the raw installer')
    if args.payload_delay_ms is not None and (
            not args.payload or not 10000 <= args.payload_delay_ms <= 600000 or b'sweetpayloaddelay' not in kernel):
        parser.error('--payload-delay-ms requires --payload, XNU patch 2120 and a delay of 10000–600000 ms')
    if args.usb and b'Sweet iOS (USB log)' not in kernel:
        parser.error('--usb requires a kernel with xnu 2101')
    if args.cpufreq and b'SWEET CPUFREQ: domain %u hardware not enabled' not in kernel:
        parser.error('--cpufreq requires a kernel with the SM7150 cpufreq patch')
    if args.sample_interval_ms is not None and (not args.sample or args.sample_interval_ms < 50):
        parser.error('--sample-interval-ms requires --sample and a value of at least 50')
    if args.sample and b'SMP: sampling %s' not in kernel:
        parser.error('--sample requires a kernel with the SWEET process sampler')
    cmdline = ROOT_ARGS.replace('sweetfb_scale=1', f'sweetfb_scale={args.fb_scale}')
    if args.no_noprogress:
        cmdline = cmdline.replace(' -noprogress', '')
    if args.ramdisk:
        ramdisk = HFS(args.ramdisk)
        with ramdisk.f:
            pid1 = ramdisk.info('/sbin/launchd')
            if ramdisk.sig != b'HX' or not pid1 or pid1['type'] != 'file':
                parser.error('expected a raw HFSX volume with /sbin/launchd')
            if b'SWEET userspace: init running as PID' not in ramdisk.readfile('/sbin/launchd'):
                parser.error('/sbin/launchd must be the diagnostic from tools/sweet-init.S')
        cmdline = SMOKE_ARGS
    cmdline += ' sweettouch=1 sweettouchdelay=3' if args.touch else ' sweettouch=0'
    cmdline += ' sweetkeys=1' if args.keys else ' sweetkeys=0'
    if args.wifi:
        # sweetsmmuwlan maps the WLAN stream 0x240 only inside the sweetsmmuprobe thread;
        # without the probe the firmware's first DMA after "12 rings programmed" resets the
        # SoC (iOS 16 wave5/wave6; iOS 26 Wi-Fi boots 2026-11-20 had no SWEET SMMU line).
        cmdline += ' sweetpmem=1 sweetsmmuwlan=1 sweetsmmuprobe=1 sweetnull=wland,backboardd,SpringBoard'
    if args.bluetooth:
        cmdline += ' sweetbt=1'
    cmdline += ADRENO_ARGS if args.adreno_firmware else ' sweetgpu=0'
    if args.metal:
        cmdline += ' sweetmtl=2 sweetgles=0'
    if args.payload:
        cmdline += ' sweetpayload=1'
    if args.payload_delay_ms is not None:
        cmdline += f' sweetpayloaddelay={args.payload_delay_ms}'
    if args.cpufreq:  # the first copy of a boot-arg wins: replace, do not append
        cmdline = cmdline.replace('sweetcpufreq=0', 'sweetcpufreq=1')
    if args.usb_shot and not args.usb:
        parser.error('--usb-shot requires --usb')
    if args.usb:
        cmdline = cmdline.replace('sweetusb=0', 'sweetusb=3')
    if args.usb_shot:
        cmdline += ' sweetusbshot=1'
    if args.usb_ui:
        if not args.usb_shot or b'a71:cover' not in kernel:
            parser.error('--usb-ui requires --usb-shot and the xnu 2127 Cover Sheet command')
        cmdline += ' sweetusbui=1'
    # A71 ports in the kernel (xnu 2108-2115) switch their boot-args on; the first copy of an argument wins.
    if args.adreno_firmware and b'SWEET RENDER: restarted SpringBoard' in kernel:
        cmdline += ' sweetm2restart=2'
    if args.adreno_firmware and b'DSI0 off or out of its mode' in kernel:
        cmdline = cmdline.replace(' sweetfb_dcsbl=0', '')
    if b'SWEET BATTERY: s2mu106' in kernel:
        cmdline = cmdline.replace('sweetbattery=0', 'sweetbattery=2').replace(' sweetcharge=0', '')
    if args.rtcoff:
        cmdline += f' sweetrtcoff={args.rtcoff}'
    if args.dtlog:
        cmdline += f' sweetdtlog={args.dtlog}'
    if args.sample:
        cmdline += f' sweetsample={args.sample}'
    if args.sample_interval_ms is not None:
        cmdline += f' sweetsamplems={args.sample_interval_ms}'
    if args.fb_hz is not None:
        cmdline += f' sweetfb_hz={args.fb_hz}'
    for extra in args.arg:
        if not extra or ' ' in extra:
            parser.error(f'--arg {extra!r}: one NAME=VALUE without spaces')
        cmdline += f' {extra}'

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output.parent) as temp:
        temp = Path(temp)
        tree = temp / 'a71.adt'
        tree.write_bytes(adt.serialize(mkadt.build(highmem=True, ios26=True, product_adt=args.product_adt,
                                                 native_width=args.native_width)))
        if args.wifi:
            wlan_tree = temp / 'a71-wlan.adt'
            subprocess.run([sys.executable, str(Path(__file__).with_name('adt-add-wlan.py')),
                            str(tree), str(wlan_tree)], check=True)
            tree = wlan_tree
        if args.bluetooth:
            bt_tree = temp / 'a71-bt.adt'
            env = dict(os.environ, SWEETBTFILES='crbtfw21.tlv crnv21.bin')
            subprocess.run([sys.executable, str(Path(__file__).with_name('adt-add-bluetooth.py')),
                            str(tree), str(bt_tree), str(args.bluetooth)], check=True, env=env)
            tree = bt_tree
        if args.adreno_firmware:
            tree = add_adreno_firmware(tree, args.adreno_firmware)
        main_line, ext_line = split_cmdline(cmdline)
        if ext_line:
            if b'sweet-boot-args' not in kernel:
                parser.error(f'command line is {len(cmdline.encode())} bytes (limit {SHIM_LINE_MAX}) and this kernel '
                             'has no xnu 2140 (/chosen sweet-boot-args)')
            ext_tree = temp / 'a71-ext.adt'
            root, end = adt.parse(tree.read_bytes())
            chosen = [c for c in root.children if c.name == 'chosen']
            if len(chosen) != 1:
                parser.error('ADT has no single /chosen')
            chosen[0].props.append(('sweet-boot-args', 0, ext_line.encode() + b'\0'))
            ext_tree.write_bytes(adt.serialize(root))
            tree = ext_tree
            print(f'boot-args: {len(main_line.encode())} bytes in the shim line, {len(ext_line.encode())} bytes in '
                  f'/chosen sweet-boot-args: {ext_line}')
        payload, info = mkpayload.build(args.kernel, tree, main_line, args.ramdisk)
        if info['cputype'] != '0x100000c' or info['cpusub'] != 0:
            parser.error('A71 requires a plain arm64 kernel')
        (temp / 'payload.bin').write_bytes(payload)
        image = temp / 'boot.img'
        mkbootv2.pack_boot_v2(args.shim, temp / 'payload.bin', args.dtb, image, cmdline='console=null')
        if image.stat().st_size >= 64 << 20:
            parser.error('boot image exceeds 64 MiB partition limit')
        digest = hashlib.sha256(image.read_bytes()).hexdigest()
        image.replace(args.output)

    print(f"XNU entry {info['entry']}, fixups {info['fixups']}, RAM disk {info['ramdisk']}")
    print(f'{digest}  {args.output}')


if __name__ == '__main__':
    main()
