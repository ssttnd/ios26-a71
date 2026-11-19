#!/usr/bin/env python3
"""Install iOS on a Samsung Galaxy A71 (SM-A715F) from scratch, from Windows. Full guide: docs/INSTALL.md.

  a71-install.py check                     what is present locally and on the phone
  a71-install.py pull                      TWRP: back up partitions, copy the phone's firmware, stock DTB
  a71-install.py fetch [--branch B]        download the newest successful CI artifacts of this fork
  a71-install.py write-root IMAGE          TWRP: write the iOS root to userdata (ERASES userdata)
  a71-install.py package IMAGE [--tz Z]    build build/install.payload (drivers, Wi-Fi, audio, fixes)
  a71-install.py boot                      TWRP: build the boot image, write the package, flash boot

Run the steps in this order. Everything needs the phone in TWRP (`adb get-state` = recovery), except
fetch and package. adb: --adb PATH, or A71_ADB, or adb on PATH. Steps that write to the phone ask for
"yes" unless --yes is given. Python 3 standard library only; no WSL.

What the package installs on the root (all of it learned on this phone, see NOTES.md):
  Metal driver   /System/Library/Extensions/SweetMetal2.bundle + /var/local/sweet-native-env
  Wi-Fi          /var/local/bin/{wland,netsvc}, modem and WLAN firmware, rmtfs copies of this phone's
                 modemst1/2, fsg, fsc, launchd job org.sweet.wland, a Wi-Fi network service
  Audio          adspboot (started by wland once per boot), ADSP firmware, SunfishAudio.driver,
                 VirtualAudio.plugin back in HAL
  Debugging      sweetdbg (started by wland; key in build/sweetdbg.key) for tools/a71-dbg.py
  Fixes          launchd.plist without com.apple.fairplayd.H2, lockdownd with FairPlay timeouts,
                 32 removable apps moved from /var/staged_system_apps to /Applications,
                 optional time zone, optional wallpaper/LaunchServices rebuild job
Originals of the replaced Apple files go to /var/local/apple-orig on the phone.
"""
import argparse, datetime, hashlib, importlib.util, io, json, os, plistlib, shutil, subprocess, sys, time, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
FW = os.path.join(ROOT, "research", "a71-firmware")
CI = os.path.join(ROOT, "research", "ci")
STAGE = os.path.join(ROOT, "build", "install")
PAYLOAD = os.path.join(ROOT, "build", "install.payload")
BOOT_IMG = os.path.join(ROOT, "shim", "out", "shim-boot.img")
NW = 0x08000000 if os.name == "nt" else 0  # no console windows

BACKUP_PARTS = ["boot", "recovery", "dtbo", "vbmeta", "vbmeta_samsung", "persist", "efs", "sec_efs",
                "modemst1", "modemst2", "fsg", "fsc", "param"]
RMTFS = ["modemst1", "modemst2", "fsg", "fsc"]
GPU_FW = ["a630_sqe.fw", "a618_gmu.bin", "a615_zap.mdt", "a615_zap.b00", "a615_zap.b01", "a615_zap.b02"]
ARTIFACTS = {  # workflow file -> artifact name
    "xnu.yml": "xnu-kernel",
    "native-metal.yml": "sweet-native-metal-ios16",
    "wifi.yml": "sweet-wifi-ios16",
    "audio.yml": "sweet-audio-ios16",
    "wallpaper.yml": "sweet-wallpaper-ios16",
}
STAGED_APPS = ["AppleTV", "Books", "Bridge", "Calculator", "Compass", "Contacts", "FaceTime", "Files", "FindMy",
               "Fitness", "Freeform", "Health", "Home", "Magnifier", "Maps", "Measure", "MobileCal", "MobileMail",
               "MobileNotes", "MobileStore", "MobileTimer", "Music", "News", "Passbook", "Podcasts", "Reminders",
               "SequoiaTranslator", "Shortcuts", "Stocks", "Tips", "VoiceMemos", "Weather"]
NATIVE_ENV = "FD_MESA_DEBUG=sysmem\nMESA_SHADER_CACHE_DIR=/var/tmp/sweet-mesa-cache"
ADSP_ARGS = "boot --audio-fifo /var/run/sunfish-audio --amp-addr 0x4c --amp-db -20 --pcm-pa kernel --watch 0"
# Boot line in use (README.md); sweetpayload=1 makes the kernel apply the package, sweetrtcoff is added at flash time.
BOOT_ENV = {"SWEETGPU": "9", "SWEETNULL": "wland", "SWEETWLAN": "1", "SWEETBATTERY": "2",
            "SWEETBACKLIGHT": "1", "SWEETKEEPSYMS": "0"}
BOOT_ARGS = ("sweetgpukhz=700000 sweetmtl=2 sweetpresentwait=1 sweetswapwait=3 sweetpresentfence=1 sweetamfi=1 "
             "sweetpmem=1 sweetsmmuwlan=1 sweetsmmuprobe=1 sweetm2restart=2 sweetpayload=1 sweetrtc=1")
PAYLOAD_LIMIT = 65536 * 4096  # the raw area at the end of userdata (tools/a71-payload.py)


def die(msg):
    sys.exit("error: " + msg)


def load_tool(name):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(TOOLS, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def confirm(args, what):
    if args.yes:
        return
    print(f"\n{what}\nType yes to continue: ", end="", flush=True)
    if input().strip().lower() != "yes":
        die("stopped by the user")


def run_py(script, *a, env=None):
    """Run a repository tool, output straight to this console; return its exit code."""
    return subprocess.run([sys.executable, "-X", "utf8", os.path.join(TOOLS, script), *a],
                          cwd=ROOT, env=env, creationflags=NW).returncode


# --- adb --------------------------------------------------------------------------------------------

class Phone:
    def __init__(self, adb):
        self.adb = adb

    def run(self, *a, timeout=600):
        return subprocess.run([self.adb, *a], capture_output=True, timeout=timeout, creationflags=NW)

    def sh(self, cmd, timeout=600):
        return self.run("shell", cmd, timeout=timeout).stdout.decode(errors="replace").strip()

    def state(self):
        try:
            return self.run("get-state", timeout=20).stdout.decode().strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def need_twrp(self):
        if self.state() != "recovery":
            die("the phone is not in TWRP (adb get-state is not 'recovery'). Boot TWRP: Power + Volume Up.")

    def pull(self, remote, local):
        os.makedirs(os.path.dirname(local), exist_ok=True)
        r = self.run("pull", remote, local)
        return r.returncode == 0 and os.path.exists(local)


def find_adb(args):
    for c in (args.adb, os.environ.get("A71_ADB"), shutil.which("adb")):
        if c and os.path.exists(c):
            return c
    die("adb not found: pass --adb PATH\\adb.exe or set A71_ADB")


# --- check ------------------------------------------------------------------------------------------

def cmd_check(args):
    ok = True

    def item(cond, text, hint=""):
        nonlocal ok
        ok &= bool(cond)
        print(("  ok   " if cond else "  MISS ") + text + ("" if cond or not hint else "   -> " + hint))

    print("Local files:")
    item(sys.version_info >= (3, 8), f"Python {sys.version.split()[0]}")
    item(os.path.exists(os.path.join(ROOT, "dtb", "boot_unpacked", "dtb")), "dtb/boot_unpacked/dtb", "a71-install.py pull")
    item(os.path.exists(os.path.join(ROOT, "shim", "out", "Image")), "shim/out/Image", "shim/build.sh on Linux (docs/INSTALL.md)")
    item(all(os.path.exists(os.path.join(FW, n)) for n in GPU_FW), "GPU firmware in research/a71-firmware", "a71-install.py pull")
    item(os.path.isdir(os.path.join(FW, "modem")) and os.path.exists(os.path.join(FW, "apnhlos", "adsp.mdt")),
         "modem and apnhlos firmware", "a71-install.py pull")
    item(os.path.exists(os.path.join(FW, "vendor-wifi", "firmware_wlan_qca_cld_bdwlan.bin")), "vendor Wi-Fi board file", "a71-install.py pull")
    item(latest_backup() is not None, "partition backup in backup/", "a71-install.py pull")
    for wf, name in ARTIFACTS.items():
        item(os.path.exists(os.path.join(CI, name + ".zip")), f"CI artifact {name}",
             "a71-install.py fetch, or download it from the Actions page to research/ci/" + name + ".zip")
    item(os.path.exists(PAYLOAD), "build/install.payload", "a71-install.py package IMAGE")
    adb = args.adb or os.environ.get("A71_ADB") or shutil.which("adb")
    print("Phone:")
    if adb and os.path.exists(adb):
        st = Phone(adb).state()
        item(st == "recovery", f"adb state: {st or 'no device'}", "boot TWRP and connect USB")
    else:
        item(False, "adb", "pass --adb or set A71_ADB")
    print("\nall present" if ok else "\nsome items are missing (fine if a later step makes them)")


# --- pull: backup, firmware, DTB -------------------------------------------------------------------

def latest_backup():
    d = os.path.join(ROOT, "backup")
    if not os.path.isdir(d):
        return None
    dirs = sorted(x for x in os.listdir(d) if os.path.exists(os.path.join(d, x, "boot.img")))
    return os.path.join(d, dirs[-1]) if dirs else None


def cmd_pull(args):
    ph = Phone(find_adb(args))
    ph.need_twrp()
    names = set(ph.sh("ls /dev/block/by-name").split())
    out = os.path.join(ROOT, "backup", datetime.date.today().isoformat())
    if os.path.exists(os.path.join(out, "boot.img")) and not args.force:
        print(f"backup {out} exists, kept (--force to make it again)")
    else:
        print(f"Backing up partitions to {out} (stays local, never in git: holds IMEI and calibration)")
        sums = []
        for p in BACKUP_PARTS:
            if p not in names:
                print(f"  {p}: no such partition, skipped")
                continue
            ph.sh(f"dd if=/dev/block/by-name/{p} of=/tmp/{p}.img bs=1048576 2>/dev/null")
            remote = ph.sh(f"sha256sum /tmp/{p}.img").split()[0]
            local = os.path.join(out, p + ".img")
            if not ph.pull(f"/tmp/{p}.img", local) or sha256_file(local) != remote:
                die(f"pulling {p} failed")
            ph.sh(f"rm -f /tmp/{p}.img")
            sums.append(f"{remote}  {p}.img")
            print(f"  {p}: {os.path.getsize(local)} bytes, {remote[:16]}")
        open(os.path.join(out, "SHA256-phone.txt"), "w").write("\n".join(sums) + "\n")
        print("Keep this backup: boot.img is the way back to Android.")

    print("\nFirmware -> research/a71-firmware (local only, never in git)")
    for part, sub in (("apnhlos", "apnhlos"), ("modem", "modem")):
        mnt = f"/tmp/fw-{part}"
        ph.sh(f"mkdir -p {mnt}; mount -t vfat -o ro /dev/block/by-name/{part} {mnt} 2>&1")
        files = [f for f in ph.sh(f"ls {mnt}/image 2>/dev/null").split() if f]
        base = f"{mnt}/image"
        if not files:
            files, base = [f for f in ph.sh(f"ls {mnt} 2>/dev/null").split() if f], mnt
        for f in files:
            if part == "modem" and not f.lower().startswith("modem"):
                continue
            if not ph.pull(f"{base}/{f}", os.path.join(FW, sub, f.lower())):
                print(f"  could not pull {part}/{f}")
        ph.sh(f"umount {mnt}")
        print(f"  {part}: {len(files)} files")
    ph.sh("mount -o ro /vendor 2>/dev/null")
    vendor = {
        "a630_sqe.fw": "/vendor/firmware/a630_sqe.fw",
        "a618_gmu.bin": "/vendor/firmware/a618_gmu.bin",
        "vendor-wifi/firmware_wlan_qca_cld_bdwlan.bin": "/vendor/firmware/wlan/qca_cld/bdwlan.bin",
        "vendor-wifi/regdb.bin": "/vendor/firmware/wlan/qca_cld/regdb.bin",
    }
    for local, remote in vendor.items():
        print(f"  {local}: {'ok' if ph.pull(remote, os.path.join(FW, *local.split('/'))) else 'NOT FOUND at ' + remote}")
    ph.sh("umount /vendor 2>/dev/null")
    for n in ("a615_zap.mdt", "a615_zap.b00", "a615_zap.b01", "a615_zap.b02"):
        src = os.path.join(FW, "apnhlos", n)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(FW, n))
    missing = [n for n in GPU_FW if not os.path.exists(os.path.join(FW, n))]
    if missing:
        print("  missing GPU firmware:", ", ".join(missing))

    bk = latest_backup()
    dtb_dir = os.path.join(ROOT, "dtb", "boot_unpacked")
    if bk and not os.path.exists(os.path.join(dtb_dir, "dtb")):
        run_py("unpack_bootv2.py", os.path.join(bk, "boot.img"), dtb_dir)
    print("\nDTB:", "ok" if os.path.exists(os.path.join(dtb_dir, "dtb")) else "MISSING (unpack a stock boot.img with tools/unpack_bootv2.py)")


# --- fetch: CI artifacts ---------------------------------------------------------------------------

def github():
    import urllib.request, urllib.error
    url = subprocess.run(["git", "remote", "get-url", "origin"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    repo = url.split("github.com")[-1].lstrip(":/").removesuffix(".git")
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        p = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", capture_output=True,
                           text=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        token = next((l[9:] for l in p.stdout.splitlines() if l.startswith("password=")), None)
    if not token:
        die("no GitHub token: set GITHUB_TOKEN, or download the artifacts by hand (docs/INSTALL.md)")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    def get(path, binary=False):
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}{path}", headers={
            "User-Agent": "ios-a71-install", "Accept": "application/vnd.github+json", "Authorization": "Bearer " + token})
        try:
            data = urllib.request.build_opener(NoRedirect).open(req, timeout=120).read()
        except urllib.error.HTTPError as e:
            if e.code != 302:
                raise
            # The token goes only to api.github.com, not to the storage host of the redirect.
            data = urllib.request.urlopen(urllib.request.Request(e.headers["Location"], headers={"User-Agent": "ios-a71-install"}), timeout=600).read()
        return data if binary else json.loads(data)
    return repo, get


def cmd_fetch(args):
    repo, get = github()
    branch = args.branch or subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    os.makedirs(CI, exist_ok=True)
    info = {}
    for wf, name in ARTIFACTS.items():
        runs = get(f"/actions/workflows/{wf}/runs?branch={branch}&status=success&per_page=10")["workflow_runs"]
        found = None
        for r in runs:
            arts = [a for a in get(f"/actions/runs/{r['id']}/artifacts")["artifacts"] if a["name"] == name and not a["expired"]]
            if arts:
                found = r, arts[0]
                break
        if not found:
            print(f"  {name}: no successful run with this artifact on {branch}; run workflow {wf} in Actions")
            continue
        r, a = found
        data = get(f"/actions/artifacts/{a['id']}/zip", binary=True)
        if len(data) != a["size_in_bytes"]:
            die(f"{name}: download size differs")
        open(os.path.join(CI, name + ".zip"), "wb").write(data)
        info[name] = {"run": r["id"], "commit": r["head_sha"], "sha256": hashlib.sha256(data).hexdigest()}
        print(f"  {name}: run {r['id']} commit {r['head_sha'][:7]}, {len(data)} bytes")
    json.dump(info, open(os.path.join(CI, "fetched.json"), "w"), indent=1)
    print(f"artifacts of {repo}@{branch} in research/ci")


# --- write-root ------------------------------------------------------------------------------------

def cmd_write_root(args):
    ph = Phone(find_adb(args))
    ph.need_twrp()
    img = os.path.abspath(args.image)
    if os.path.getsize(img) != 16 << 30:
        die("the root image should be 16 GiB (tools/mkiosroot.sh default)")
    print("hashing the image ...", flush=True)
    h = sha256_file(img)
    print("image", h)
    confirm(args, "This ERASES userdata (Android data, internal storage) and writes the iOS root to it.")
    ph.sh("umount /sdcard 2>/dev/null; umount /data 2>/dev/null")  # TWRP mounts userdata; a71-write-root.py refuses then
    work = os.path.join(ROOT, "build", "write-root")
    os.makedirs(work, exist_ok=True)
    rc = subprocess.run([sys.executable, "-X", "utf8", os.path.join(TOOLS, "a71-write-root.py"), ph.adb, img, h],
                        cwd=work, creationflags=NW).returncode
    if rc:
        die("root write failed; run the same command again: it resumes and rewrites only wrong chunks")
    open(os.path.join(ROOT, "build", "root-written.txt"), "w").write(f"{h}  {img}\n")


# --- package ---------------------------------------------------------------------------------------

def artifact(name):
    path = os.path.join(CI, name + ".zip")
    if not os.path.exists(path):
        die(f"missing {path}: run `a71-install.py fetch` or download the {name} artifact from Actions")
    return zipfile.ZipFile(path)


def put(rel, data):
    p = os.path.join(STAGE, *rel.strip("/").split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(data)


def extract_tree(z, prefix, dest_rel):
    n = 0
    for name in z.namelist():
        if name.startswith(prefix) and not name.endswith("/"):
            put(dest_rel + "/" + name[len(prefix):], z.read(name))
            n += 1
    if not n:
        die(f"nothing under {prefix} in the artifact")
    return n


def cmd_package(args):
    hfs = load_tool("hfsread").HFS(os.path.abspath(args.image))
    shutil.rmtree(STAGE, ignore_errors=True)
    items = []

    # Metal driver
    z = artifact("sweet-native-metal-ios16")
    pre = next(n for n in z.namelist() if n.endswith("native-legacy/build.json"))[:-len("build.json")]
    build = json.loads(z.read(pre + "build.json"))
    for rel, h in build["files"].items():
        if hashlib.sha256(z.read(pre + "SweetMetal2.bundle/" + rel)).hexdigest() != h:
            die("Metal bundle file differs from build.json: " + rel)
    bundle = os.path.join(ROOT, "build", "install-bundle")
    shutil.rmtree(bundle, ignore_errors=True)
    os.makedirs(bundle)
    for name in z.namelist():
        if name.startswith(pre + "SweetMetal2.bundle/") and not name.endswith("/"):
            p = os.path.join(bundle, *name[len(pre + "SweetMetal2.bundle/"):].split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(z.read(name))
    items.append(f"tree:{bundle}=/System/Library/Extensions/SweetMetal2.bundle")
    put("/private/var/local/sweet-native-env", NATIVE_ENV.encode() + b"\n")
    print(f"Metal bundle {build.get('source_commit', '?')[:7]}: {len(build['files'])} files")

    # Wi-Fi: wland, netsvc, firmware, this phone's rmtfs data
    z = artifact("sweet-wifi-ios16")
    for n in ("wland", "netsvc"):
        put(f"/private/var/local/bin/{n}", z.read(n))
    modem = os.path.join(FW, "modem")
    for n in sorted(os.listdir(modem)):
        if n.startswith("modem"):
            put(f"/private/var/local/fw/modem/{n}", open(os.path.join(modem, n), "rb").read())
    apn = os.path.join(FW, "apnhlos")
    for n in sorted(os.listdir(apn)):
        if n.startswith(("bdwlan", "wlanmdsp", "regdb", "modemuw")):
            put(f"/private/var/local/fw/modem/{n}", open(os.path.join(apn, n), "rb").read())
    # The board file and regulatory database from /vendor are the ones Wi-Fi joins with (NOTES.md, wave21-23).
    put("/private/var/local/fw/modem/bdwlan.b00", open(os.path.join(FW, "vendor-wifi", "firmware_wlan_qca_cld_bdwlan.bin"), "rb").read())
    put("/private/var/local/fw/modem/regdb.bin", open(os.path.join(FW, "vendor-wifi", "regdb.bin"), "rb").read())
    put("/private/var/local/wlan-bdf-host", b"")
    put("/private/var/local/fw/rw/.keep", b"")
    bk = latest_backup() or die("no partition backup: run `a71-install.py pull` first")
    for n in RMTFS:
        put(f"/private/var/local/fw/rmtfs/{n}.img", open(os.path.join(bk, n + ".img"), "rb").read())
    print("Wi-Fi: wland, netsvc, modem and WLAN firmware, rmtfs from", os.path.relpath(bk, ROOT))

    # Audio and sweetdbg
    z = artifact("sweet-audio-ios16")
    for n in ("adspboot", "tasprobe", "sweetdbg"):
        put(f"/private/var/local/bin/{n}", z.read(n))
    extract_tree(z, "SunfishAudio.driver/", "/System/Library/Audio/Plug-Ins/HAL/SunfishAudio.driver")
    for n in sorted(os.listdir(apn)):
        if n.startswith("adsp.") and (n.endswith(".mdt") or n[-4:-2] == ".b"):
            put(f"/private/var/local/fw/adsp/{n}", open(os.path.join(apn, n), "rb").read())
    if args.no_audio:
        put("/private/var/local/adsp-off", b"")
    else:
        put("/private/var/local/adspboot.args", ADSP_ARGS.encode() + b"\n")
    items.append("mv:/Library/Audio/Plug-Ins/HAL.disabled/VirtualAudio.plugin=/Library/Audio/Plug-Ins/HAL/VirtualAudio.plugin")
    keyf = os.path.join(ROOT, "build", "sweetdbg.key")
    if not os.path.exists(keyf):
        os.makedirs(os.path.dirname(keyf), exist_ok=True)
        open(keyf, "w").write(os.urandom(32).hex() + "\n")
    put("/private/var/local/sweetdbg.key", open(keyf).read().strip().encode() + b"\n")
    print("Audio: adspboot", "(off: adsp-off)" if args.no_audio else "(starts at boot)", "+ SunfishAudio.driver; sweetdbg key build/sweetdbg.key")

    # launchd.plist: no fairplayd.H2 (its clients block forever), wland job, optional rebuild job
    raw = hfs.readfile("/System/Library/xpc/launchd.plist")
    put("/private/var/local/apple-orig/launchd.plist", raw)
    d = plistlib.loads(raw)
    jobs = d["LaunchDaemons"]
    if not any(isinstance(j, dict) and "_PanicOnCrasX" in j for j in jobs.values()):
        die("this root has not been through tools/sweet-root-tweaks.py (docs/INSTALL.md, Linux step)")
    for k in [k for k, j in jobs.items() if isinstance(j, dict) and j.get("Label") == "com.apple.fairplayd.H2"]:
        del jobs[k]
    jobs["/System/Library/LaunchDaemons/org.sweet.wland.plist"] = {
        "Label": "org.sweet.wland", "ProgramArguments": ["/var/local/bin/wland", "auto"], "RunAtLoad": True,
        "UserName": "root", "EnvironmentVariables": {"PATH": "/var/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"}}
    if os.path.exists(os.path.join(CI, "sweet-wallpaper-ios16.zip")) and not args.no_rebuild:
        put("/usr/local/libexec/sweet-wallpaper-register", artifact("sweet-wallpaper-ios16").read("sweet-wallpaper-register"))
        jobs["/System/Library/LaunchDaemons/org.sweet.wallpaper-rebuild.plist"] = {
            "Label": "org.sweet.wallpaper-rebuild", "ProgramArguments": ["/usr/local/libexec/sweet-wallpaper-register", "--rebuild-once"],
            "UserName": "root", "RunAtLoad": False, "StartInterval": 180, "ProcessType": "Background"}
        print("LaunchServices/wallpaper rebuild job: once, 180 s after the second boot")
    put("/System/Library/xpc/launchd.plist", plistlib.dumps(d, fmt=plistlib.FMT_BINARY, sort_keys=False))
    print("launchd.plist:", len(jobs), "jobs")

    # lockdownd with timeouts on its FairPlay calls
    raw = hfs.readfile("/usr/libexec/lockdownd")
    put("/private/var/local/apple-orig/lockdownd", raw)
    tmp_in, tmp_out = os.path.join(ROOT, "build", "lockdownd.orig"), os.path.join(ROOT, "build", "lockdownd.patched")
    open(tmp_in, "wb").write(raw)
    if run_py("a71-patch-lockdownd.py", tmp_in, tmp_out):
        die("lockdownd patch failed")
    put("/usr/libexec/lockdownd", open(tmp_out, "rb").read())
    for p in (tmp_in, tmp_out):
        os.remove(p)

    # Wi-Fi network service for configd (en0, DHCP)
    PREFS = "/private/var/preferences/SystemConfiguration/preferences.plist"
    try:
        p = plistlib.loads(hfs.readfile(PREFS))
    except Exception:
        p = {}
    svc, set_ = "5EE7C0DE-5EE7-4000-8000-00000000E000", "5EE7C0DE-5EE7-4000-8000-00000000A000"
    p.setdefault("NetworkServices", {})[svc] = {
        "DNS": {}, "IPv4": {"ConfigMethod": "DHCP"}, "IPv6": {"ConfigMethod": "Automatic"},
        "Proxies": {"ExceptionsList": ["*.local", "169.254/16"], "FTPPassive": 1},
        "Interface": {"DeviceName": "en0", "Hardware": "AirPort", "Type": "Ethernet", "UserDefinedName": "Wi-Fi"},
        "UserDefinedName": "Wi-Fi"}
    p.setdefault("Sets", {})[set_] = {
        "Network": {"Global": {"IPv4": {"ServiceOrder": [svc]}},
                    "Interface": {"en0": {"AirPort": {"JoinModeFallback": ["DoNothing"], "PowerEnabled": True}}},
                    "Service": {svc: {"__LINK__": "/NetworkServices/" + svc}}},
        "UserDefinedName": "Automatic"}
    p["CurrentSet"] = "/Sets/" + set_
    put(PREFS, plistlib.dumps(p, fmt=plistlib.FMT_BINARY))

    items.insert(1, f"tree:{STAGE}=")
    items += [f"mv:/private/var/staged_system_apps/{n}.app=/Applications/{n}.app" for n in STAGED_APPS]
    if args.tz:
        items.append(f"link:/private/var/db/timezone/localtime=/usr/share/zoneinfo.default/{args.tz}")
    if os.path.exists(PAYLOAD):
        os.remove(PAYLOAD)
    if run_py("a71-payload.py", "build", PAYLOAD, *items):
        die("package build failed")
    size = os.path.getsize(PAYLOAD)
    if size > PAYLOAD_LIMIT:
        die(f"package is {size} bytes, the area holds {PAYLOAD_LIMIT}")
    print(f"\nbuild/install.payload: {size >> 20} MiB, sha256 {sha256_file(PAYLOAD)}")


# --- boot ------------------------------------------------------------------------------------------

def cmd_boot(args):
    ph = Phone(find_adb(args))
    ph.need_twrp()
    for need in ("shim/out/Image", "dtb/boot_unpacked/dtb"):
        if not os.path.exists(os.path.join(ROOT, *need.split("/"))):
            die(f"missing {need} (docs/INSTALL.md)")
    kz = os.path.join(CI, "xnu-kernel.zip")
    if not os.path.exists(kz):
        die("missing research/ci/xnu-kernel.zip: run `a71-install.py fetch`")
    if not all(os.path.exists(os.path.join(FW, n)) for n in GPU_FW):
        die("GPU firmware missing in research/a71-firmware: run `a71-install.py pull`")
    # The phone's RTC counts from an arbitrary base; the kernel adds this offset to get the real date.
    epoch = ph.sh("cat /sys/class/rtc/rtc0/since_epoch")
    off = int(time.time()) - int(epoch) if epoch.isdigit() else 0
    env = dict(os.environ, **BOOT_ENV, SWEETARGS=f"{BOOT_ARGS} sweetrtcoff={off}")
    if os.path.exists(BOOT_IMG):
        os.remove(BOOT_IMG)
    if run_py("package_gpu_boot.py", kz, env=env) or not os.path.exists(BOOT_IMG):
        die("boot image build failed")
    h = sha256_file(BOOT_IMG)
    print("boot image", h)
    pay = not args.no_package
    if pay and not os.path.exists(PAYLOAD):
        die("missing build/install.payload: run `a71-install.py package IMAGE` (or pass --no-package)")
    confirm(args, ("Writes build/install.payload to the end of userdata, then " if pay else "") +
            "writes the iOS boot image to `boot` and reboots. Your Android boot.img backup is the way back.")
    if pay:
        p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(TOOLS, "a71-payload.py"), "write", ph.adb, PAYLOAD],
                           cwd=ROOT, capture_output=True, text=True, creationflags=NW)
        print(p.stdout.strip()[-300:], p.stderr.strip()[-300:])
        if "VERIFY OK" not in p.stdout:
            die("package write failed; boot not flashed")
    p = subprocess.run([sys.executable, "-X", "utf8", os.path.join(TOOLS, "a71-flash-boot.py"), ph.adb, BOOT_IMG, h],
                       cwd=ROOT, capture_output=True, text=True, creationflags=NW)
    print(p.stdout.strip(), p.stderr.strip()[-300:])
    if "VERIFY OK" not in p.stdout:
        die("boot flash failed: do not reboot; restore boot from the backup in TWRP")
    print("\nFlashed. First boot applies the package (log: SWEET PAYLOAD). Reboot once more after the lock screen")
    print("appears: launchd reads its jobs before the package is applied, so Wi-Fi, audio and sweetdbg start")
    print("from the second boot. Kernel log over USB: python tools\\a71-usblog.py logs\\usb-install.txt")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adb", help="path to adb.exe")
    ap.add_argument("--yes", action="store_true", help="do not ask before writing to the phone")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    s = sub.add_parser("pull")
    s.add_argument("--force", action="store_true", help="make a new backup even if today's exists")
    s = sub.add_parser("fetch")
    s.add_argument("--branch")
    s = sub.add_parser("write-root")
    s.add_argument("image")
    s = sub.add_parser("package")
    s.add_argument("image", help="the same root image that was written (read only)")
    s.add_argument("--tz", help="time zone, e.g. Europe/Moscow (default: iOS default)")
    s.add_argument("--no-audio", action="store_true", help="do not start the ADSP at boot (/var/local/adsp-off)")
    s.add_argument("--no-rebuild", action="store_true", help="leave out the LaunchServices/wallpaper rebuild job")
    s = sub.add_parser("boot")
    s.add_argument("--no-package", action="store_true", help="only build and flash the boot image")
    a = ap.parse_args()
    {"check": cmd_check, "pull": cmd_pull, "fetch": cmd_fetch, "write-root": cmd_write_root,
     "package": cmd_package, "boot": cmd_boot}[a.cmd](a)


if __name__ == "__main__":
    main()
