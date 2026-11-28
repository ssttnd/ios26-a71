"""Make xnu patch 2144 (USB key/tap/swipe commands) against sweet_usb.c as staged after 2137.

usage: make-usb-input-patch.py STAGED_SWEET_USB_C
"""
import sys
from difflib import unified_diff
from pathlib import Path

name = 'bsd/dev/sweet_usb.c'
old = Path(sys.argv[1]).read_text(encoding='utf-8')
new = old


def sub(before, after):
    global new
    assert new.count(before) == 1, before
    new = new.replace(before, after)


sub('''extern void sweet_reboot_set_mode(int mode);    /* bsd/dev/sweet_reboot.c (2122) */''',
    '''/*
 * 2144: "a71:key:N[:MS]" presses a button (0 power, 1 volume up, 2 volume down, 3 home) for MS ms
 * (default 100), "a71:tap:X,Y" and "a71:swipe:X1,Y1,X2,Y2[,MS]" (default 300 ms) touch in A71 panel
 * pixels (1080x2400, the same space the SEC_TS driver reports). Lets the PC wake the screen and unlock it.
 */
extern void sweet_hid_key(int key, int down);
static int ud_input[6];         /* key: kind 1, key, ms; tap: kind 2, x, y; swipe: kind 3, x1, y1, x2, y2, ms */
static int ud_input_kind;

static uint32_t
ud_parse_ints(const char *p, uint32_t len, int *out, unsigned max)
{
	unsigned n = 0;
	int have = 0, v = 0;
	for (uint32_t c = 0; c < len; c++) {
		char ch = p[c];
		if (ch >= '0' && ch <= '9') {
			if (v < 100000) {
				v = v * 10 + (ch - '0');
			}
			have = 1;
		} else if ((ch == ',' || ch == ':') && have && n < max) {
			out[n++] = v;
			v = 0;
			have = 0;
		} else {
			break;
		}
	}
	if (have && n < max) {
		out[n++] = v;
	}
	return n;
}

static void
ud_acm_input(void)
{
	int *a = ud_input;
	if (ud_input_kind == 1) {
		int ms = a[1] > 0 && a[1] <= 10000 ? a[1] : 100;
		printf("SWEET USB: host key %d for %d ms\\n", a[0], ms);
		sweet_hid_key(a[0], 1);
		ud_sleep_ms(ms);
		sweet_hid_key(a[0], 0);
	} else if (ud_input_kind == 2) {
		printf("SWEET USB: host tap %d,%d\\n", a[0], a[1]);
		sweet_hid_touch(0, 1, a[0], a[1]);
		ud_sleep_ms(60);
		sweet_hid_touch(0, 0, a[0], a[1]);
	} else if (ud_input_kind == 3) {
		int ms = a[4] >= 50 && a[4] <= 5000 ? a[4] : 300;
		int steps = ms / 16;
		printf("SWEET USB: host swipe %d,%d -> %d,%d in %d ms\\n", a[0], a[1], a[2], a[3], ms);
		for (int i = 0; i <= steps; i++) {
			sweet_hid_touch(0, 1, a[0] + (a[2] - a[0]) * i / steps, a[1] + (a[3] - a[1]) * i / steps);
			ud_sleep_ms(16);
		}
		sweet_hid_touch(0, 0, a[2], a[3]);
	}
}

extern void sweet_reboot_set_mode(int mode);    /* bsd/dev/sweet_reboot.c (2122) */''')

sub('''	static const char kill_word[] = "a71:kill:";
	for (uint32_t i = 0; i < len; i++) {
''', '''	static const char kill_word[] = "a71:kill:";
	static const struct { const char *word; int kind, min, max; } inputs[] = {
		{ "a71:key:", 1, 1, 2 }, { "a71:tap:", 2, 2, 2 }, { "a71:swipe:", 3, 4, 5 },
	};
	for (uint32_t i = 0; i < len; i++) {
		for (unsigned w = 0; w < sizeof(inputs) / sizeof(inputs[0]); w++) {
			size_t n = strlen(inputs[w].word);
			if (len - i > n && memcmp(p + i, inputs[w].word, n) == 0) {
				int v[6] = { 0 };
				uint32_t got = ud_parse_ints(p + i + n, len - i - (uint32_t)n, v, 5);
				if (got >= (uint32_t)inputs[w].min && got <= (uint32_t)inputs[w].max && ud_cmd == 0) {
					memcpy(ud_input, v, sizeof(ud_input));
					ud_input_kind = inputs[w].kind;
					ud_cmd = 7;
				}
				return;
			}
		}
''')

sub('''		if (cmd == 6) {
			ud_acm_kill();
			continue;
		}
''', '''		if (cmd == 6) {
			ud_acm_kill();
			continue;
		}
		if (cmd == 7) {
			ud_acm_input();
			continue;
		}
''')

header = '''A71: USB commands to press buttons and touch the screen.

"a71:key:N[:MS]" (0 power, 1 volume up, 2 volume down, 3 home), "a71:tap:X,Y" and
"a71:swipe:X1,Y1,X2,Y2[,MS]" in panel pixels (1080x2400) go through sweet_hid_key and
sweet_hid_touch, the same entry points as the real buttons and SEC_TS. The PC can wake the
screen and swipe the lock screen up without the owner.

'''
diff = ''.join(unified_diff(old.splitlines(True), new.splitlines(True), 'a/' + name, 'b/' + name))
out = Path('xnu/patches-12377-adreno/2144-a71-usb-key-touch-commands.patch')
out.write_text(header + 'diff --git a/' + name + ' b/' + name + chr(10) + diff, encoding='utf-8', newline=chr(10))
print(out, len(diff))
