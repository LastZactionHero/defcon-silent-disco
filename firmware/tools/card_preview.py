#!/usr/bin/env python3
"""Preview what a set of tracks will look like on the badge.

Imports the REAL disco.py (via hostshim), so theme/animation assignment can
never drift from the firmware.  Channel order, LED theme, animation and
brightness are all decided by the filename -- rename a file, change its look.

    python3 tools/card_preview.py <file-or-name> [...]
    python3 tools/card_preview.py /Volumes/CARD/*.mp3
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hostshim import fw  # noqa: E402

disco = fw.disco

SWATCH = {
    (255, 0, 0): "R", (255, 255, 0): "Y", (0, 255, 0): "G",
    (0, 255, 255): "C", (0, 0, 255): "B", (255, 0, 255): "M",
    (255, 255, 255): "W", (0, 0, 0): ".",
}


def main(argv):
    names = sorted(os.path.basename(a) for a in argv
                   if a.lower().endswith((".mp3", ".wav")))
    if not names:
        print(__doc__)
        return 2
    looks = disco.assign_looks(names)
    total_min = 0
    print("ch  %-40s %-10s %-10s %-4s LEDs" % ("track", "theme", "anim", "brt"))
    for i, (nm, (t, b, a)) in enumerate(zip(names, looks), 1):
        leds = " ".join(SWATCH.get(c, "?") for c in disco.THEMES[t])
        print("%2d  %-40s %-10s %-10s %-4d %s"
              % (i, nm[:40], disco.THEME_NAMES[t], disco.ANIM_NAMES[a], b, leds))
    dup = len(names) - len(set(looks))
    print("\n%d channel(s), %s"
          % (len(names),
             "all looks distinct" if dup == 0 else "%d DUPLICATE looks!" % dup))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
