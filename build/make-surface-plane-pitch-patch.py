from difflib import unified_diff
from pathlib import Path

name = 'iokit/Kernel/arm/SweetSurface.cpp'
old = (Path('research/xnu-12377') / name).read_text(encoding='utf-8')
before = '''		s->planeCount = planes->getCount();
	}
'''
after = '''		s->planeCount = planes->getCount();
		/*
		 * CoreAnimation's render targets ('&BGA') are one plane whose rows it
		 * aligns to 256 bytes, while IOSurfaceBytesPerRow keeps 64-byte rows.
		 * At 1125 pixels that is 4608 against 4544: the GPU import refused the
		 * mismatch and the panel copy would read skewed rows. Nothing here
		 * compresses, so the plane is the whole surface: use its row pitch.
		 */
		if (s->planeCount == 1 && s->planes[0].offset == s->offset &&
		    s->planes[0].width == s->width && s->planes[0].height == s->height &&
		    s->planes[0].bytesPerRow > s->bytesPerRow) {
			s->bytesPerRow = s->planes[0].bytesPerRow;
		}
	}
'''
assert old.count(before) == 1
new = old.replace(before, after)
header = '''A71 display: one-plane IOSurfaces use the plane's row pitch.

The 1125x2436 canvas gave a black screen. backboardd and Mercury render into
'&BGA' surfaces with IOSurfaceBytesPerRow 4544 and plane 0 bytes per row 4608.
SweetNativeMetal refuses that mismatch, so no frame was drawn. At 1080 pixels
both are 4352. For a single plane covering the surface, take the plane pitch.

'''
diff = unified_diff(old.splitlines(True), new.splitlines(True), 'a/' + name, 'b/' + name)
body = ''.join(diff)
out = Path('xnu/patches-12377-adreno/2143-a71-surface-single-plane-pitch.patch')
out.write_text(header + 'diff --git a/' + name + ' b/' + name + chr(10) + body, encoding='utf-8', newline=chr(10))
print(out, len(body))
