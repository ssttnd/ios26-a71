#!/usr/bin/env python3
"""Build the minimal Apple Device Tree that the SWEET xnu needs to boot.

Only what the early boot path reads. Usage:
    mkadt.py OUT.adt [--dump] [--qemu] [--highmem] [--ios26] [--product-adt N104AP.adt]
"""
import argparse, hashlib, os, struct, sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adt  # noqa: E402

# Kernel-managed RAM: above every Qualcomm XPU carve-out (see NOTES.md)
PHYS_BASE = 0xb0000000
MEM_SIZE = 0x4d000000
# Panic log buffer, carved from the TOP of the dram range and exposed to XNU as
# /pram + /chosen/embedded-panic-log-size. Without it, pe_init.c's
# check_for_panic_log() leaves gPanicBase == 0, debug_log_init() bails out twice
# and the kernel hangs right after "kdp_core zlib memory" — reproduced on QEMU
# and independently on ios-fajita.
PANIC_LOG_SIZE = 0x100000
# --highmem (phone only): the whole upper DDR bank. The live FDT memory node is
# <0x80000000 2G>, <0x1_00000000 0xfcc00000>; every fixed reserved-memory
# carve-out is in the low bank and the dynamic pools are limited below 4G.
HIGH_PHYS_BASE = 0x100000000
HIGH_MEM_SIZE = 0xc0000000
# /arm-io children are relative to this; it must not be 0 (serial_init bails)
SOC_BASE = 0x01000000

GICD, GICD_SIZE = 0x17a00000, 0x10000
GICR, GICR_SIZE = 0x17a60000, 0x100000
FB, FB_SIZE = 0x9c000000, 0x1700000
SWEET_ECID = 0x5357454554000001  # 'SWEET' + 1, synthetic
# MobileGestalt identity placeholders. These do not publish a hardware radio.
SWEET_MG_MACS = {
    'mac-address-wifi0': bytes.fromhex('025357454554'),
    'mac-address-bluetooth0': bytes.fromhex('025357454555'),
    'mac-address-ethernet0': bytes.fromhex('02005e77ee02'),
}
FB_W, FB_H, FB_STRIDE = 1080, 2400, 1080 * 4
# Internal UFS host (ufshc@1d84000 "ufs_mem"); QEMU virt has none
UFS, UFS_SIZE = 0x01d84000, 0x3000
TIMEBASE = 19200000
VTIMER_INTID = 19
# QEMU virt (-M virt,gic-version=3 -cpu cortex-a76): GICD/GICR and the generic timer's CNTFRQ
QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE = 0x08000000, 0x080a0000, 62500000
QEMU_VTIMER_INTID = 27

BOOT_MANIFEST_HASH = hashlib.sha384(b'sweet boot manifest').digest()

# The iOS userland is the iPhone X (iPhone10,3 / D22AP) IPSW. MobileGestalt
# derives product type, device class, home-button-less UI, artwork etc. from
# the root identity and /product of the real D22AP device tree. That tree is
# an Apple artifact (kept out of git): extract it from the IPSW with
#   tools/remotezip.py URL DeviceTree.d22ap.im4p DIR
#   ipsw img4 im4p extract DIR/Firmware/all_flash/DeviceTree.d22ap.im4p -o d22ap.adt
D22AP_ADT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../research/ipsw-x/d22ap.adt')


def read_product(path, target):
    """Read /product without syscfg placeholders and node bookkeeping."""
    root, _ = adt.parse(Path(path).read_bytes())
    compatible = (root.prop('compatible') or b'').split(b'\0')
    if target.encode().lower() not in [value.lower() for value in compatible]:
        raise SystemExit(f'{path}: expected a {target} device tree')
    for c in root.children:
        if c.name == 'product':
            return [(k, v) for k, f, v in c.props if not f and k not in ('name', 'AAPL,phandle')]
    raise SystemExit(f'{path}: no /product node')

u32 = lambda *v: struct.pack('<%dI' % len(v), *v)
u64 = lambda *v: struct.pack('<%dQ' % len(v), *v)
cstr = lambda s: s.encode() + b'\0'


def node(name, props=(), children=()):
    n = adt.Node()
    n.props = [('name', 0, cstr(name))] + [(k, 0, v) for k, v in props]
    n.children = list(children)
    return n


def build(seed=None, qemu=False, highmem=False, ios26=False, product_adt=None, native_width=False):
    """qemu=True: same tree, but with QEMU virt's GIC addresses and CNTFRQ (tools/qemu-sweet.py)."""
    target, machine, target_type = ('N104AP', 'iPhone12,1', 'N104') if ios26 else ('D22AP', 'iPhone10,3', 'D22')
    canvas_width, canvas_height, display_scale = (828, 1792, 2) if ios26 else (1125, 2436, 3)
    if native_width:
        if not ios26 or qemu:
            raise ValueError('native-width mode requires the iOS 26 phone device tree')
        canvas_width, canvas_height, display_scale = 1080, 2340, 3
    phys_base, mem_size = (HIGH_PHYS_BASE, HIGH_MEM_SIZE) if highmem else (PHYS_BASE, MEM_SIZE)
    # XNU 8796's QEMU path needs /pram. The XNU 12377 donor boots without it.
    # On A71, 12377 faults in PE_create_console while zeroing the I/O mapping.
    panic_properties = []
    if not ios26:
        mem_size -= PANIC_LOG_SIZE
        panic_properties.append(('embedded-panic-log-size', u32(PANIC_LOG_SIZE)))
    gicd, gicr, timebase = (QEMU_GICD, QEMU_GICR, QEMU_TIMEBASE) if qemu else (GICD, GICR, TIMEBASE)
    seed = seed if seed is not None else os.urandom(256 if ios26 else 64)
    if ios26 and len(seed) != 256:
        raise ValueError('XNU 12377 requires a 256-byte random seed')
    phandle = iter(range(1, 1000))
    ph = lambda: ('AAPL,phandle', u32(next(phandle)))

    chosen = node('chosen', [
        ph(),
        ('dram-base', u64(phys_base)),
        ('dram-size', u64(mem_size)),
        ('random-seed', seed),
        *([('kernel-ctrr-to-be-enabled', u32(1))] if ios26 else []),
        ('debug-enabled', u32(1)),
        *panic_properties,
        ('firmware-version', cstr('sweet-shim')),
        ('system-firmware-version', cstr('sweet-shim')),
        # iBoot's SHA-384 of the boot manifest; /sbin/mount -P 1 exits unless
        # it exists (bind mounts /private/preboot/<hex>/usr/standalone/firmware,
        # tolerating a missing directory). Fixed stand-in value.
        ('boot-manifest-hash', BOOT_MANIFEST_HASH),
        # libimg4 (cryptexd) aborts "failed to get crypto algorithm" without
        # it; real A11+ device trees say sha2-384.
        ('crypto-hash-method', cstr('sha2-384')),
        # MobileGestalt's screen class: display-scale (u32, default 0) comes
        # from /chosen, the pixel size from IOMobileFramebuffer. Scale 0 makes
        # SpringBoard's FBSDisplayMode "infxinf@0x" invalid.
        ('display-scale', u32(display_scale)),
        # XNU derives IOPlatformUUID (gethostuuid) from these on arm; without
        # them CFPreferences cannot use kCFPreferencesCurrentHost (no ByHost
        # files), so e.g. DataMigration never records LastSystemVersion and
        # migrates on every boot. Use a synthetic ECID and the target chip-id.
        ('unique-chip-id', struct.pack('<Q', SWEET_ECID)),
        ('chip-id', u32(0x8030 if ios26 else 0x8015)),
        # MobileGestalt's legacy device identity otherwise waits for a WLAN
        # IOService for each bundle scanned by MobileInstallation. These are
        # stable, locally administered placeholders, not factory radio MACs.
        *list(SWEET_MG_MACS.items()),
        # Security status as on a dev-fused, undemoted board (tuple 0,0,1,1):
        # MobileGestalt reads these from /chosen, and mobileactivationd's
        # DeviceType then takes its native "Hactivation" branch (state
        # Activated without an activation record; no SEP, no baseband here).
        ('certificate-production-status', u32(0)),
        ('effective-production-status-ap', u32(0)),
        ('certificate-security-mode', u32(1)),
        ('effective-security-mode-sep', u32(1)),
    ], [node('memory-map', [ph()]),
        # Local boot policy (kern_csr.c): SIP relaxed like `csrutil disable`
        # (lp-sip0: untrusted kexts, unrestricted FS, task_for_pid, kernel
        # debugger, dtrace, nvram), lp-sip1: unauthenticated (unsealed) root.
        # The iOS shared cache is in no trust cache, so dyld can only map it
        # with CSR_ALLOW_UNRESTRICTED_FS (vm_unix.c shared region checks).
        node('asmb', [ph(), ('lp-sip0', u64(0x6f)), ('lp-sip1', u32(1))])])
    if ios26:
        chosen.children.append(node('manifest-properties', [ph()]))
        chosen.props.extend([(key, 0, u32(0)) for key in ('board-id', 'chip-epoch', 'security-domain')])

    # SWEET SMP: all eight cores in physical-core order (0-5 Cortex-A55,
    # 6-7 Cortex-A76), one homogeneous cluster. The kernel defaults to one
    # and uses cpus=N to select an initial prefix (N <= 8).
    # QEMU retains its original single-CPU tree: its MPIDRs differ from sweet.
    cpu_nodes = []
    for core in range(1 if qemu else 8):
        cpu_nodes.append(node(f'cpu{core}', [
            ph(),
            ('device_type', cstr('cpu')),
            ('compatible', cstr('qcom,kryo470') + cstr('ARM,v8')),
            ('reg', u32(core << 8)),  # actual MPIDR Aff1:Aff0, NOT logical ID
            ('cpu-id', u32(core)),   # descriptive: XNU assigns IDs by DT order
            ('cluster-id', u32(0)),  # descriptive; see ml_parse_cpu_topology
            ('cluster-type', u32(0)),  # homogeneous CLUSTER_TYPE_SMP, not AMP
            ('die-cluster-id', u32(0)),
            ('cluster-core-id', u32(core)),
            ('l2-cache-id', u32(core)),  # distinct per-core L2 nodes in live FDT
            ('l3-cache-id', u32(0)),     # shared L3
            ('state', cstr('running' if core == 0 else 'stopped')),
            ('timebase-frequency', u32(timebase)),
            ('clock-frequency', u32(2304000000 if core >= 6 else 1804800000)),
            ('bus-frequency', u32(100000000)),
            ('memory-frequency', u32(1866000000)),
            ('peripheral-frequency', u32(timebase)),
            ('fixed-frequency', u32(timebase)),
        ]))
    cpus = node('cpus', [ph(), ('#address-cells', u32(1)),
                         ('#size-cells', u32(0))], cpu_nodes)

    gic = node('gic', [
        ph(),
        ('compatible', cstr('arm,gic-v3')),
        ('interrupt-controller', b''),
        ('virtual-timer-intid', u32(QEMU_VTIMER_INTID if qemu else VTIMER_INTID)),
        ('reg', u64(gicd - SOC_BASE, GICD_SIZE, gicr - SOC_BASE, GICR_SIZE)),
    ])
    arm_io = node('arm-io', [
        ph(),
        ('device_type', cstr('sweet-io')),
        ('compatible', cstr('sweet-io') + cstr('arm-io')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
        ('ranges', u64(0, SOC_BASE, 0x100000000 - SOC_BASE)),
    ], [gic,
        # No hardware: watchdogd checks IODeviceTree:/arm-io/wdt for no-pmu and
        # otherwise crashes trying to set the PMU boot stage (customer builds
        # ignore the -wdt_no_pmu boot-arg).
        node('wdt', [ph(), ('no-pmu', u32(1))]),
        # Main display: IOMobileFramebuffer.framework counts /arm-io children
        # with this device_type and reads the canvas size from the node
        # (the presented iPhone X size, see SweetFramebuffer.cpp);
        # the kernel's AppleCLCD matches the compatible string.
        node('disp0', [
            ph(),
            ('device_type', cstr('display-subsystem')),
            ('compatible', cstr('sweet,display')),
            ('canvas-width', u32(canvas_width)),
            ('canvas-height', u32(canvas_height)),
        ])])

    fbcon = node('sweet-fbcon', [
        ph(),
        ('reg', u64(FB, FB_SIZE)),
        ('width', u32(FB_W)),
        ('height', u32(FB_H)),
        ('stride', u32(FB_STRIDE)),
    ])

    # bsd/dev/sweet_ufs.c: the UFS host ABL leaves running (absolute physical reg).
    ufs = node('sweet-ufs', [
        ph(),
        ('compatible', cstr('qcom,ufshc')),
        ('reg', u64(UFS, UFS_SIZE)),
    ])

    # pmap_compute_max_asids requires the node even when no overrides are set.
    # An absent pmap-max-asids property selects XNU's own MAX_ASIDS default.
    # No effaceable storage: keybagd then reads /private/var/keybags/systembag.kb
    # as a plain plist instead of decrypting it with the effaceable key.
    defaults = node('defaults', [ph(), ('no-effaceable-storage', u32(1))])

    # MobileGestalt HomeButtonType = IODeviceTree:/buttons home-button-type
    # (D22AP: 2, no Home button; absent = 0 = Home-button device).
    buttons = node('buttons', [
        ph(),
        ('button-names', cstr('volup') + cstr('voldown') + cstr('hold')),
        ('home-button-type', u32(2)),
        ('opposed-power-vol-buttons', u32(1)),
    ])

    if product_adt is None and not ios26:
        if os.path.exists(D22AP_ADT):
            product_adt = D22AP_ADT
        else:
            print(f'warning: {D22AP_ADT} missing, no /product node', file=sys.stderr)
    product_props = read_product(product_adt, target) if product_adt else []
    # Match the 8-bit BGRA framebuffer. P3 makes CoreAnimation request b3a8/w30r
    # render targets, which the display and GPU paths do not support.
    if product_props:
        product_props = [(k, cstr('sRGB') if k in ('artwork-display-gamut', 'display-gamut') else v)
                         for k, v in product_props]
        if native_width:
            product_props = [(k, u32(display_scale) if k == 'artwork-scale-factor' else v)
                             for k, v in product_props]
    product = [node('product', [ph()] + product_props)] if product_props else []

    # /pram has an absolute <phys, size> just outside kernel-managed DRAM.
    pram = [] if ios26 else [node('pram', [ph(), ('reg', u64(phys_base + mem_size, PANIC_LOG_SIZE))])]

    # compatible[0] is hw.model/hw.target. model is hw.machine/hw.product.
    # Keep the inherited sweet alias for driver matching on SM7150.
    boards = ('samsung,a71', 'xiaomi,sweet') if ios26 and not qemu else ('xiaomi,sweet',)
    return node('device-tree', [
        ph(),
        ('compatible', b''.join(map(cstr, (target, machine, *boards, 'qcom,sm7150', 'AppleARM')))),
        ('model', cstr(machine)),
        ('target-type', cstr(target_type)),
        ('target-sub-type', cstr(target)),
        ('manufacturer', cstr('Apple Inc.')),
        ('#address-cells', u32(2)),
        ('#size-cells', u32(2)),
    ], [chosen, defaults, cpus, arm_io, fbcon, buttons] + pram + product + ([] if qemu else [ufs]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--qemu', action='store_true')
    parser.add_argument('--highmem', action='store_true')
    parser.add_argument('--ios26', action='store_true')
    parser.add_argument('--product-adt', type=Path)
    parser.add_argument('--dump', action='store_true')
    args = parser.parse_args()
    root = build(qemu=args.qemu, highmem=args.highmem, ios26=args.ios26, product_adt=args.product_adt)
    blob = adt.serialize(root)
    args.output.write_bytes(blob)
    if args.dump:
        adt.dump(adt.parse(blob)[0])
    print(f'{args.output}: {len(blob)} bytes', file=sys.stderr)
