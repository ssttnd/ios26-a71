from pathlib import Path
import shutil
import sys

air = Path(sys.argv[1]) / "src/compiler/air"
include = Path(__file__).with_name("vbcap-replay.inc")
if include.is_file():
    shutil.copyfile(include, air / include.name)
path = air / "air_metal_test.c"
source = path.read_text()
marker = "int\nmain(int argc, char **argv)\n{\n"
if '#include "vbcap-replay.inc"' not in source:
    if source.count(marker) != 1:
        raise SystemExit("unexpected main signature")
    source = source.replace(marker, '#include "vbcap-replay.inc"\n\n' + marker + r"""
   if (argc >= 2 && !strcmp(argv[1], "--vbcap")) {
      if (argc != 7) {
         fputs("usage: air_metal_test --vbcap LIB VERT FRAG CAPTURE OUT.pam\n", stderr);
         return 2;
      }
      return run_vbcap(argv[2], argv[3], argv[4], argv[5], argv[6]);
   }
""")
    path.write_text(source)

native = air / "sweet_native_ext.c"
source = native.read_text()
start = "static unsigned native_cpu(void)\n{\n"
stop = "   return (unsigned)(v&0xfff)&7;\n"
if start + "#if defined(__aarch64__)\n" not in source:
    if source.count(start) != 1 or source.count(stop) != 1:
        raise SystemExit("unexpected native_cpu implementation")
    source = source.replace(start, start + "#if defined(__aarch64__)\n")
    source = source.replace(stop, stop + "#else\n   return 0;\n#endif\n")

host_marker = "/* Host replay uses synchronous draws without the A71 transport. */"
if host_marker not in source:
    source += """

/* Host replay uses synchronous draws without the A71 transport. */
#if !defined(__APPLE__)
int sweet_transport_command_begin(void) { return ENOTSUP; }
void sweet_transport_command_end(void) {}
uint64_t sweet_transport_submitted_fence(void) { return 0; }
int sweet_transport_poll_fence(uint64_t fence) { return ENOTSUP; }
#endif
"""
if native.read_text() != source:
    native.write_text(source)

backend = air / "air_metal.c"
source = backend.read_text()
if '#include "softpipe/sp_public.h"' not in source:
    includes = '#include "sweet_native_ext.h"\n'
    flag = "   bool software = false;\n"
    screen = "   if (!device->screen) {\n      say(why, why_size, \"no Gallium screen"
    if any(source.count(text) != 1 for text in (includes, flag, screen)):
        raise SystemExit("unexpected device initialization")
    source = source.replace(includes, includes + """
#if defined(GALLIUM_SOFTPIPE) && !defined(__APPLE__)
#include "softpipe/sp_public.h"
#include "null/null_sw_winsys.h"
#endif
""")
    source = source.replace(flag, flag + """#if defined(GALLIUM_SOFTPIPE) && !defined(__APPLE__)
   const char *software_env = getenv("RWA_SOFTWARE");
   software = software_env && !strcmp(software_env, "1");
#endif
""")
    source = source.replace(screen, """#if defined(GALLIUM_SOFTPIPE) && !defined(__APPLE__)
   if (software)
      device->screen = softpipe_create_screen(null_sw_create());
#endif
""" + screen)
    backend.write_text(source)
