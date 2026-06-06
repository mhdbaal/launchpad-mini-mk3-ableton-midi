# Launchpad Pro MK3 SysEx identity + firmware layout bytes.
# Values lifted from the decompiled factory script
# (midi-remote-scripts/Launchpad_Pro_MK3/sysex_ids.py).
from __future__ import absolute_import, print_function, unicode_literals

LP_PRO_MK3_FAMILY_CODE = (35, 1)
LP_PRO_MK3_ID = 14

# Firmware layout selectors (3-byte tuples on the Pro, unlike the Mini's
# single byte). Only SESSION_LAYOUT_BYTES is referenced by this script
# (Elements.default_layout); the rest are kept for future DAW-mode work
# (the custom script runs in Programmer mode and bypasses layouts).
SESSION_LAYOUT_BYTES = (0, 0, 0)
CHORD_LAYOUT_BYTES = (2, 0, 0)
NOTE_LAYOUT_BYTES = (4, 0, 0)
FADER_LAYOUT_BYTE = 1
SCALE_LAYOUT_BYTES = (1, )
DRUM_LAYOUT_BYTES = (2, )
