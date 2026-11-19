#!/usr/bin/env python3
"""Package an A71 XNU 26 Android boot image from explicit local inputs."""

import argparse
import hashlib
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
    'debug=0xc serial=3 keepsyms=1 -noprogress cpus=8 '
    'unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin wdt=-1 '
    'sweetarm64e=1 sweetearlyfb=1 -v sweetfb_noconsole=0 '
    'sweetbattery=0 sweetusb=0 sweetcpufreq=0 sweetfb_flip=0'
)
SMOKE_ARGS = BASE_ARGS + ' rd=md0 sweetlog=0 -enable_kprintf_spam'
ROOT_ARGS = BASE_ARGS + ' rd=ufsroot0 ufsrw=1 rootrw=1 sweetfb_scale=1 launchd_unsecure_cache=1 launchd_disable_all_timeouts=1'
ADRENO_ARGS = ' sweetgpu=9 sweetgpukhz=650000 sweetfb_dcsbl=0 sweetfb_direct=0 sweetddr=0 sweetcharge=0'


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
    parser.add_argument('--touch', action='store_true', help='enable the Samsung SEC_TS driver in an A71 kernel build')
    parser.add_argument('--keys', action='store_true', help='enable the power and volume key driver')
    parser.add_argument('--adreno-firmware', type=Path, help='enable A618 stage 9 using firmware from this A71')
    parser.add_argument('--metal', action='store_true', help='select the installed SweetMetal2 bundle')
    parser.add_argument('--payload', action='store_true', help='apply a verified raw package on this boot')
    parser.add_argument('-o', '--output', required=True, type=Path)
    args = parser.parse_args()

    kernel = args.kernel.read_bytes()
    if b'xnu-12377.' not in kernel:
        parser.error('expected an XNU 12377 kernel')
    if args.touch and b'Samsung S6SY771 (sec_ts)' not in kernel:
        parser.error('--touch requires an XNU build with the A71 SEC_TS patch')
    if args.metal and not args.adreno_firmware:
        parser.error('--metal requires --adreno-firmware')
    if args.ramdisk and (args.adreno_firmware or args.payload):
        parser.error('Adreno and payload installation require the UFS root')
    if args.adreno_firmware and b'SWEET GPU: GPUCC audit v2' not in kernel:
        parser.error('expected a kernel built with the Adreno option')
    if args.payload and b'SWEET PAYLOAD: finished' not in kernel:
        parser.error('expected an A71 kernel with the raw installer')
    cmdline = ROOT_ARGS
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
    cmdline += ADRENO_ARGS if args.adreno_firmware else ' sweetgpu=0'
    if args.metal:
        cmdline += ' sweetmtl=2 sweetgles=0'
    if args.payload:
        cmdline += ' sweetpayload=1'

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output.parent) as temp:
        temp = Path(temp)
        tree = temp / 'a71.adt'
        tree.write_bytes(adt.serialize(mkadt.build(highmem=True, ios26=True, product_adt=args.product_adt)))
        if args.adreno_firmware:
            tree = add_adreno_firmware(tree, args.adreno_firmware)
        payload, info = mkpayload.build(args.kernel, tree, cmdline, args.ramdisk)
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
